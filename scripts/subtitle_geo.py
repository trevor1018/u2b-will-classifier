"""Download YouTube auto-CC for cases that don't have a confident location
yet, then ask Claude Haiku to extract the real-world location from the
transcript.

Targets:
  - cases with no lat/lon (the 27 unpinned)
  - the top city-stack groups (where many cases share the same city centre
    coords because the LLM didn't go past city-level)

Usage:
    python scripts/subtitle_geo.py            # default targets above
    python scripts/subtitle_geo.py --all-stacks   # include all 33 stack groups

Honours user constraint: prefer null over guessing wrong.

Costs roughly $0.007 per case at Haiku 4.5 prices (8k transcript +
short prompt). Plus a few minutes of yt-dlp downloads.

⚠ KNOWN LIMITATION (as of 2026-05): the X調查 channel has neither
manual subtitles nor YouTube auto-CC enabled on any of its videos.
This script will detect that and skip every case. Re-runs are still
worth it if Will ever enables CC. For now the only paths to richer
geo metadata are:
  - OpenAI Whisper API (~$2-3 to transcribe all 27 unpinned)
  - Local faster-whisper (free, ~9 h CPU)
Both deliberately not wired up.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from country_centroids import COUNTRY_CENTROIDS

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001").strip()

CACHE_PATH = ROOT / "scripts/.cache/classifications.json"
SUBS_DIR = ROOT / "scripts/.cache/subs"
OUTPUT_PATH = ROOT / "frontend/public/data/cases.json"
SUBS_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Subtitle download via yt-dlp
# ---------------------------------------------------------------------------

LANG_PREFS = ["zh-Hant", "zh-TW", "zh-Hans", "zh-CN", "zh", "en"]


def vtt_path_for(vid: str) -> Path | None:
    """Find a downloaded VTT file for this video, preferring zh-Hant > zh-Hans > en."""
    for lang in LANG_PREFS:
        p = SUBS_DIR / f"{vid}.{lang}.vtt"
        if p.exists() and p.stat().st_size > 0:
            return p
    # yt-dlp sometimes uses just .zh
    for p in SUBS_DIR.glob(f"{vid}.*.vtt"):
        if p.stat().st_size > 0:
            return p
    return None


def download_subtitle(vid: str) -> Path | None:
    """Returns path to a VTT file or None if no subs available."""
    cached = vtt_path_for(vid)
    if cached:
        return cached

    import yt_dlp

    opts = {
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": LANG_PREFS,
        "subtitlesformat": "vtt",
        "skip_download": True,
        "outtmpl": str(SUBS_DIR / "%(id)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([f"https://www.youtube.com/watch?v={vid}"])
    except Exception as e:
        print(f"  ! yt-dlp error for {vid}: {e}", file=sys.stderr)
        return None
    return vtt_path_for(vid)


def vtt_to_text(path: Path) -> str:
    """Strip VTT cues / timestamps / tags, return plain transcript."""
    raw = path.read_text(encoding="utf-8", errors="replace")
    out_lines: list[str] = []
    seen_lines: set[str] = set()
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("WEBVTT") or line.startswith("NOTE") or line.startswith("Kind:") or line.startswith("Language:"):
            continue
        if "-->" in line:
            continue
        # Cue identifier (numeric)
        if re.fullmatch(r"\d+", line):
            continue
        # Strip HTML/VTT inline tags <c.colorXxxx>...</c>, <00:00:00.000>
        clean = re.sub(r"<[^>]+>", "", line).strip()
        if not clean:
            continue
        # YouTube auto-CC repeats lines for fade-in effects — dedupe consecutive
        if clean in seen_lines:
            continue
        seen_lines.add(clean)
        out_lines.append(clean)
    return "\n".join(out_lines)


# ---------------------------------------------------------------------------
# LLM geo extraction from transcript
# ---------------------------------------------------------------------------

GEO_SYSTEM = """你是地理研究員，從中文真實犯罪影片的字幕中找案件「實際發生地點」。

回傳 JSON 物件，只有 JSON、不要任何解釋。Schema：
{
  "city": str | null,     // 具體中文城市/區/小鎮 (e.g. 「澀谷」「洛杉磯」「茨城縣築波市」)
  "country": str | null,  // 中文國名
  "lat": number | null,
  "lon": number | null,
  "evidence": str | null  // 字幕中提及該地點的關鍵字 (供人工檢查)
}

關鍵規則：
- 字幕沒明確提及具體地點 → 全部 null（**寧可 null 也不要瞎猜**）
- 多地案件 → 找最主要的一個地點
- 跨國案件 → 用實際案發地，不是受害者國籍
- 跳過抽象/合集影片（多案件、無單一地點、純概念解析）→ 全部 null
- lat/lon 給城市/區級精度，不是國家中心點
"""


def call_haiku_with_transcript(
    client, title: str, case_name: str, transcript: str, max_retries: int = 3
) -> dict[str, Any] | None:
    # Cap transcript size to keep token cost bounded
    transcript = transcript[:8000]
    user_msg = (
        f"案件名稱：{case_name}\n"
        f"影片標題：{title}\n\n"
        f"=== 字幕節錄（前 8000 字）===\n"
        f"{transcript}\n"
        f"=== 結束 ===\n\n"
        f"請只回傳 JSON。"
    )
    backoff = 30
    for attempt in range(max_retries):
        try:
            msg = client.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=400,
                system=GEO_SYSTEM,
                messages=[{"role": "user", "content": user_msg}],
            )
            break
        except Exception as e:
            err = str(e)
            if "rate_limit_error" in err or "429" in err:
                print(f"  ! 429 — sleeping {backoff}s ({attempt + 1}/{max_retries})", file=sys.stderr)
                time.sleep(backoff)
                backoff *= 2
                continue
            print(f"  ! Anthropic error: {e}", file=sys.stderr)
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
        m = re.search(r"\{[^{}]*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    print(f"  ! couldn't parse: {text[:200]!r}", file=sys.stderr)
    return None


# ---------------------------------------------------------------------------
# Target selection
# ---------------------------------------------------------------------------

def is_at_country_centroid(lat: float | None, lon: float | None, country: str | None) -> bool:
    if lat is None or lon is None or not country:
        return False
    cc = COUNTRY_CENTROIDS.get(country)
    if cc is None:
        return False
    return abs(lat - cc[0]) < 0.001 and abs(lon - cc[1]) < 0.001


def collect_targets(cases: list[dict], all_stacks: bool) -> list[str]:
    """Return list of video IDs to process.

    By default:
      - Cases with no lat/lon
      - Cases at country-centroid (LLM gave up on city)
      - Cases in the top 6 city-stack groups (Tokyo, LA, London, Busan, NY,
        Sydney) — where multiple cases share the exact same city-centre
        coords and we'd benefit most from district-level resolution

    With --all-stacks: every group with >1 case at the same city-centre.
    """
    target_ids: set[str] = set()

    # Bucket 1: no lat/lon
    for c in cases:
        if c["lat"] is None or c["lon"] is None:
            target_ids.add(c["id"])

    # Bucket 2: at country centroid
    for c in cases:
        if is_at_country_centroid(c["lat"], c["lon"], c.get("country")):
            target_ids.add(c["id"])

    # Bucket 3: city-stack groups
    groups: dict[tuple[float, float], list[dict]] = defaultdict(list)
    country_centroid_set = {
        (round(v[0], 4), round(v[1], 4))
        for v in COUNTRY_CENTROIDS.values()
        if v is not None
    }
    for c in cases:
        if c["lat"] is None or c["lon"] is None:
            continue
        key = (round(c["lat"], 2), round(c["lon"], 2))
        if key in {(round(k[0], 2), round(k[1], 2)) for k in country_centroid_set}:
            continue
        groups[key].append(c)

    multi = [(k, v) for k, v in groups.items() if len(v) > 1]
    multi.sort(key=lambda x: -len(x[1]))

    if all_stacks:
        for _, cs in multi:
            for c in cs:
                target_ids.add(c["id"])
    else:
        # top 6 groups by case count
        for _, cs in multi[:6]:
            for c in cs:
                target_ids.add(c["id"])

    return sorted(target_ids)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--all-stacks", action="store_true",
                   help="Process every city-stack group (n>1), not just the top 6.")
    p.add_argument("--limit", type=int, default=0,
                   help="Cap number of cases processed (debugging)")
    p.add_argument("--no-download", action="store_true",
                   help="Skip yt-dlp; use only already-downloaded subs")
    args = p.parse_args()

    if not ANTHROPIC_API_KEY:
        print("ANTHROPIC_API_KEY missing in .env", file=sys.stderr)
        return 1

    # Load cases (for selecting targets) and cache (to update)
    cases = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))["cases"]
    cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))

    raw_path = ROOT / "scripts/.cache/raw_videos.json"
    raw_videos = {v["id"]: v for v in json.loads(raw_path.read_text(encoding="utf-8"))}

    targets = collect_targets(cases, args.all_stacks)
    if args.limit > 0:
        targets = targets[: args.limit]
    print(f"Subtitle geo: {len(targets)} target videos")
    print(
        "Note: as of 2026-05, X調查 has CC disabled on all videos. "
        "This script will skip everything until that changes.\n",
        file=sys.stderr,
    )

    from anthropic import Anthropic
    client = Anthropic(api_key=ANTHROPIC_API_KEY)

    fixed = 0
    skipped_nosub = 0
    skipped_nullout = 0
    INTER_CALL_DELAY = 12  # ~5K-10K tokens per transcript, 50K/min limit

    for idx, vid in enumerate(targets, 1):
        v = raw_videos.get(vid)
        if not v:
            continue
        title = v.get("snippet", {}).get("title", "")
        cl = cache.get(vid, {})
        case_name = cl.get("caseName") or title

        # Step 1: get subtitle
        sub_path = vtt_path_for(vid)
        if not sub_path and not args.no_download:
            sub_path = download_subtitle(vid)
        if not sub_path:
            print(f"  [{idx}/{len(targets)}] {case_name[:30]} -> no subs available")
            skipped_nosub += 1
            continue

        transcript = vtt_to_text(sub_path)
        if len(transcript) < 200:
            print(f"  [{idx}/{len(targets)}] {case_name[:30]} -> transcript too short")
            skipped_nosub += 1
            continue

        # Step 2: ask Haiku
        result = call_haiku_with_transcript(client, title, case_name, transcript)
        if not result:
            print(f"  [{idx}/{len(targets)}] {case_name[:30]} -> LLM no result")
            continue

        # Step 3: update cache only if LLM confidently gave coords
        if result.get("lat") is not None and result.get("lon") is not None:
            cache.setdefault(vid, {})
            cache[vid]["lat"] = result["lat"]
            cache[vid]["lon"] = result["lon"]
            if result.get("city"):
                cache[vid]["city"] = result["city"]
            if result.get("country"):
                cache[vid]["country"] = result["country"]
            fixed += 1
            ev = (result.get("evidence") or "")[:40]
            print(
                f"  [{idx}/{len(targets)}] {case_name[:25]} -> "
                f"{result.get('city')} ({result['lat']:.3f}, {result['lon']:.3f})  «{ev}»"
            )
        else:
            skipped_nullout += 1
            print(f"  [{idx}/{len(targets)}] {case_name[:30]} -> LLM said null (no clear location)")

        # Save every 5
        if idx % 5 == 0:
            CACHE_PATH.write_text(
                json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        if idx < len(targets):
            time.sleep(INTER_CALL_DELAY)

    CACHE_PATH.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nDone. fixed={fixed}  no_sub={skipped_nosub}  llm_null={skipped_nullout}")
    print(f"\nNow run:  python scripts/refresh.py --skip-classify  to rebuild cases.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
