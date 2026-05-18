"""Targeted year extraction for cases whose first-pass classification
returned crimeYear=null. Goes back to the title + full description and
asks Haiku once more with a tighter prompt focused only on the year.

Honours the prefer-null-over-guess rule — model is instructed to
return null unless the year is explicit or strongly implied.

Cost: ~$0.20 for 250 cases (no web_search, just metadata).
Rate: ~5-7 min with 50k input-tok/min Tier-1 ceiling.
"""
from __future__ import annotations

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

SYS = """你是案件年代研究員，專門從影片標題與描述抽取「案件實際發生」與
「破案/判決」的年份。

回傳純 JSON，無前後文字。Schema:
{
  "crimeYear": int | null,    // 案件實際發生年（不是影片發布年）
  "resolveYear": int | null,  // 結案 / 判決 / 平反年
  "evidence": str | null      // 文本中提及年份的關鍵字 (供人工檢查)
}

關鍵規則：
- 必須有明確文本證據才給數字（例如「1985 年」「2010 年 3 月」「20 年後」等）
- 「20 年後告破」這種相對描述也接受推算（影片發布年 - 20）
- 任何不確定 → null
- 不要把影片發布日當作 crimeYear
- 寧可 null 也不要錯
"""


def call_llm(client, title: str, description: str, published_year: int) -> dict | None:
    user_msg = (
        f"影片發布年份：{published_year}（不是案件發生年）\n\n"
        f"標題：{title}\n\n"
        f"描述：\n{description[:3000]}\n\n"
        f"請回傳 JSON。"
    )
    backoff = 30
    for attempt in range(3):
        try:
            msg = client.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=200,
                system=SYS,
                messages=[{"role": "user", "content": user_msg}],
            )
            break
        except Exception as e:
            if "rate_limit_error" in str(e) or "429" in str(e):
                print(f"  ! 429, sleeping {backoff}s", file=sys.stderr)
                time.sleep(backoff)
                backoff *= 2
                continue
            print(f"  ! API error: {e}", file=sys.stderr)
            return None
    else:
        return None

    text = "".join(b.text for b in msg.content if hasattr(b, "text")).strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{[^{}]*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
        return None


def main() -> int:
    if not ANTHROPIC_API_KEY:
        print("ANTHROPIC_API_KEY missing", file=sys.stderr)
        return 1

    cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    raw = {v["id"]: v for v in json.loads(RAW_PATH.read_text(encoding="utf-8"))}

    targets = [vid for vid, cl in cache.items() if cl.get("crimeYear") is None]
    print(f"Targets: {len(targets)} cases with crimeYear=null")

    from anthropic import Anthropic

    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    filled_crime = 0
    filled_resolve = 0
    INTER_CALL = 0.4  # ~150 RPM ceiling, stays within 50k tok/min

    for idx, vid in enumerate(targets, 1):
        v = raw.get(vid)
        if not v:
            continue
        sn = v.get("snippet", {})
        title = sn.get("title", "")
        desc = (sn.get("description") or "")
        pub_year = int((sn.get("publishedAt") or "0000")[:4])
        if pub_year == 0:
            continue

        result = call_llm(client, title, desc, pub_year)
        if not result:
            print(f"  [{idx}/{len(targets)}] {title[:40]:40s} -> no response")
            continue

        cy = result.get("crimeYear")
        ry = result.get("resolveYear")
        evidence = (result.get("evidence") or "")[:50]

        msgs = []
        if isinstance(cy, int) and cache[vid].get("crimeYear") is None:
            cache[vid]["crimeYear"] = cy
            filled_crime += 1
            msgs.append(f"crime={cy}")
        if isinstance(ry, int) and cache[vid].get("resolveYear") is None:
            cache[vid]["resolveYear"] = ry
            filled_resolve += 1
            msgs.append(f"resolve={ry}")

        if msgs:
            print(
                f"  [{idx}/{len(targets)}] {title[:35]:35s} -> "
                f"{' '.join(msgs)}  «{evidence}»"
            )
        else:
            print(f"  [{idx}/{len(targets)}] {title[:35]:35s} -> null (no evidence)")

        if idx % 10 == 0:
            CACHE_PATH.write_text(
                json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        if idx < len(targets):
            time.sleep(INTER_CALL)

    CACHE_PATH.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nDone. filled crimeYear={filled_crime}, resolveYear={filled_resolve}")
    print("Run: python scripts/refresh.py --skip-classify  to rebuild cases.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
