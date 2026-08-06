"""Web-search year lookup — the year analogue of refresh.py's
web_search_geo_lookup. For cases whose crime/resolve year the LLM couldn't get
from title+description (the channel has no subtitles), ask Claude with
web_search to find the real years, with a citable source.

Targets (union), highest viewCount first:
  - crimeYear is null, OR
  - resolveYear is null AND status in {solved, partial}   (unsolved/cold cases
    legitimately have no resolve year, so we don't chase those).

Only fills a year when confidence is high/medium AND a source is given — a
wrong year silently corrupts the timeline, so we prefer null over a guess.

Cost: ~$0.09 per case (real web_search cost). Use --limit to cap a batch
(default 55 ≈ ~$5, matching the geo web_search batch size).

Run:
    python scripts/extract_years_websearch.py --limit 55
    python scripts/extract_years_websearch.py --limit 55 --offset 55   # next batch
Then:
    python scripts/refresh.py --skip-classify   # rebuild cases.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001").strip()

CACHE_PATH = ROOT / "scripts/.cache/classifications.json"
RAW_PATH = ROOT / "scripts/.cache/raw_videos.json"
REPORT_PATH = ROOT / "scripts/.cache/year_websearch_report.txt"

INTER_CALL_DELAY = 2.0  # web_search inflates input tokens; stay under rate cap

SYS = """你是案件年代研究員。給你一個案件名稱與影片標題，你會用 web_search
工具找出該案件的「實際發生年」與「結案/判決年」，並附上來源。

回傳純 JSON，只有 JSON、不要任何解釋文字。Schema：
{
  "crimeYear": int | null,    // 案件實際發生年（不是影片發布年）
  "resolveYear": int | null,  // 破案/判決/平反年；案件未破或未結 → null
  "confidence": "high" | "medium" | "low",
  "source": str | null        // 佐證來源（網站/媒體/維基條目名），供人工查證
}

規則：
- 只有搜到可靠來源、且該來源明確給出年份時才給數字。
- 搜不到、或只能猜 → 對應欄位回 null，confidence 給 "low"。
- crimeYear 是案件發生的那一年，不是影片發布年。
- 跨國案件用實際案發地/案發時間。
- 寧可 null 也不要給錯誤年份。"""


def lookup(client, title: str, case_name: str, country: str | None, max_retries: int = 3):
    user_msg = (
        f"案件名稱：{case_name}\n"
        f"影片完整標題：{title}\n"
        f"案發國家（粗略）：{country or '不明'}\n\n"
        f"請用 web_search 找出該案件的發生年與結案年，回傳 JSON。"
    )
    backoff = 30
    for attempt in range(max_retries):
        try:
            msg = client.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=500,
                tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 2}],
                system=SYS,
                messages=[{"role": "user", "content": user_msg}],
            )
            break
        except Exception as e:
            s = str(e)
            if "rate_limit_error" in s or "429" in s:
                print(f"  ! 429 — sleeping {backoff}s ({attempt+1}/{max_retries})", file=sys.stderr)
                time.sleep(backoff)
                backoff *= 2
                continue
            print(f"  ! call failed: {e}", file=sys.stderr)
            return None
    else:
        return None

    text = "".join(b.text for b in msg.content if hasattr(b, "text")).strip()
    if not text:
        return None
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
        print(f"  ! parse fail: {text[:150]!r}", file=sys.stderr)
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=55, help="Max cases this batch (~$0.09 each)")
    ap.add_argument("--offset", type=int, default=0, help="Skip the first N priority targets")
    ap.add_argument("--dry-run", action="store_true", help="List targets, no API calls")
    args = ap.parse_args()

    if not ANTHROPIC_API_KEY and not args.dry_run:
        print("ANTHROPIC_API_KEY missing", file=sys.stderr)
        return 1

    cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    raw = {v["id"]: v for v in json.loads(RAW_PATH.read_text(encoding="utf-8"))}

    def views(vid):
        st = raw.get(vid, {}).get("statistics", {})
        try:
            return int(st.get("viewCount") or 0)
        except (TypeError, ValueError):
            return 0

    # Priority target set: needs crimeYear, or resolveYear for a solved/partial case.
    targets = []
    for vid, cl in cache.items():
        need_crime = cl.get("crimeYear") is None
        need_resolve = cl.get("resolveYear") is None and cl.get("status") in ("solved", "partial")
        if (need_crime or need_resolve) and vid in raw:
            targets.append(vid)
    targets.sort(key=views, reverse=True)  # prominent cases first
    total = len(targets)
    targets = targets[args.offset:args.offset + args.limit]

    print(f"Priority targets: {total} total; this batch = {len(targets)} "
          f"(offset {args.offset}, limit {args.limit})")
    if args.dry_run:
        for vid in targets:
            print(f"  {vid}  views={views(vid):>9}  {cache[vid].get('caseName','')[:34]}  "
                  f"cy={cache[vid].get('crimeYear')} ry={cache[vid].get('resolveYear')}")
        return 0

    from anthropic import Anthropic
    client = Anthropic(api_key=ANTHROPIC_API_KEY)

    filled_c = filled_r = 0
    report = []
    for idx, vid in enumerate(targets, 1):
        cl = cache[vid]
        sn = raw[vid].get("snippet", {})
        title = sn.get("title", "")
        name = cl.get("caseName") or title
        r = lookup(client, title, name, cl.get("country"))
        if not r:
            print(f"  [{idx}/{len(targets)}] {name[:26]:26s} -> no answer")
            if idx < len(targets):
                time.sleep(INTER_CALL_DELAY)
            continue

        conf = (r.get("confidence") or "low").lower()
        src = (r.get("source") or "")
        cy, ry = r.get("crimeYear"), r.get("resolveYear")
        msgs = []
        # Only accept high/medium-confidence, sourced years; never overwrite existing.
        if isinstance(cy, int) and cl.get("crimeYear") is None and conf in ("high", "medium") and src:
            cl["crimeYear"] = cy
            filled_c += 1
            msgs.append(f"crime={cy}")
        if isinstance(ry, int) and cl.get("resolveYear") is None and conf in ("high", "medium") and src:
            cl["resolveYear"] = ry
            filled_r += 1
            msgs.append(f"resolve={ry}")

        tag = " ".join(msgs) if msgs else f"skip (conf={conf})"
        line = f"  [{idx}/{len(targets)}] {name[:26]:26s} -> {tag}  «{src[:40]}»"
        print(line)
        report.append(f"{vid}\t{name}\tcy={cy} ry={ry} conf={conf}\tsrc={src}")

        if idx % 5 == 0:
            CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
        if idx < len(targets):
            time.sleep(INTER_CALL_DELAY)

    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    REPORT_PATH.write_text("\n".join(report), encoding="utf-8")
    print(f"\nDone. filled crimeYear={filled_c}, resolveYear={filled_r} "
          f"(of {len(targets)} searched). Report → {REPORT_PATH}")
    print("Rebuild: python scripts/refresh.py --skip-classify")
    return 0


if __name__ == "__main__":
    sys.exit(main())
