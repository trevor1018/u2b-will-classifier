"""Fetch every video on the X調查 channel via YouTube Data API v3, then
classify each one with Claude Haiku 4.5 to produce structured case records.

Output: frontend/public/data/cases.json   (consumed by the frontend)

Usage:
    # First time:
    cp .env.example .env   # then fill in YOUTUBE_API_KEY + ANTHROPIC_API_KEY
    python -m venv .venv && .venv/Scripts/activate
    pip install -r scripts/requirements.txt

    python scripts/refresh.py            # full refresh
    python scripts/refresh.py --limit 10 # quick test on a handful
    python scripts/refresh.py --skip-classify  # only fetch raw, no LLM

If YOUTUBE_API_KEY is missing, falls back to running generate_mock_data.py
so the frontend still has data to display.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"
load_dotenv(ENV_PATH)

YT_API_KEY = os.environ.get("YOUTUBE_API_KEY", "").strip()
YT_CHANNEL_ID = os.environ.get("YT_CHANNEL_ID", "UCOyshL6rKK1GqwoEfy_ehBg").strip()
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001").strip()

OUTPUT = ROOT / "frontend" / "public" / "data" / "cases.json"
RAW_CACHE = ROOT / "scripts" / ".cache" / "raw_videos.json"


# --------------------------------------------------------------------------
# YouTube Data API v3 client
# --------------------------------------------------------------------------

def yt_get(client: httpx.Client, path: str, params: dict[str, Any]) -> dict[str, Any]:
    params = {**params, "key": YT_API_KEY}
    r = client.get(f"https://www.googleapis.com/youtube/v3/{path}", params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def fetch_uploads_playlist_id(client: httpx.Client, channel_id: str) -> str:
    data = yt_get(client, "channels", {"part": "contentDetails", "id": channel_id})
    items = data.get("items") or []
    if not items:
        raise RuntimeError(f"Channel {channel_id} not found")
    return items[0]["contentDetails"]["relatedPlaylists"]["uploads"]


def fetch_playlist_video_ids(client: httpx.Client, playlist_id: str) -> list[str]:
    ids: list[str] = []
    page_token = None
    while True:
        params: dict[str, Any] = {
            "part": "contentDetails",
            "playlistId": playlist_id,
            "maxResults": 50,
        }
        if page_token:
            params["pageToken"] = page_token
        data = yt_get(client, "playlistItems", params)
        for item in data.get("items", []):
            vid = item.get("contentDetails", {}).get("videoId")
            if vid:
                ids.append(vid)
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return ids


def chunked(seq: list[str], n: int) -> Iterable[list[str]]:
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


def fetch_video_details(client: httpx.Client, video_ids: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for batch in chunked(video_ids, 50):
        data = yt_get(
            client,
            "videos",
            {
                "part": "snippet,statistics,contentDetails,status",
                "id": ",".join(batch),
            },
        )
        out.extend(data.get("items", []))
    return out


# --------------------------------------------------------------------------
# LLM classifier (Anthropic Haiku)
# --------------------------------------------------------------------------

CLASSIFIER_SYSTEM = """你是 YouTube 影片元資料分析師，專門處理「X調查」頻道（中文真實犯罪/懸案）。
給你一支影片的標題與描述，抽取結構化資訊並回傳 JSON。
只回傳一個 JSON 物件，不要任何解釋文字。

Schema:
{
  "caseName": str,           // 從標題抽出的案件正式名稱（去掉【標籤】、戲劇化 hook）
  "country": str | null,     // 中文國名，如「日本」「美國」「韓國」「英國」「不明」
  "city": str | null,        // 中文城市/地區名
  "lat": number | null,      // 緯度 (best estimate)
  "lon": number | null,      // 經度
  "crimeYear": int | null,   // 案件實際發生年份
  "resolveYear": int | null, // 結案/判決年份（若已破案）
  "caseType": str,           // murder|missing|serial|cult|fraud|disaster|mystery|kidnap|curio|other
  "status": str,             // solved|cold|partial|exonerated|ongoing|unknown
  "tags": [str]              // 標題【】內的標籤
}
"""


def classify_with_anthropic(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Returns {video_id: classified_dict}."""
    if not ANTHROPIC_API_KEY:
        print("⚠ ANTHROPIC_API_KEY missing — skipping classification", file=sys.stderr)
        return {}

    from anthropic import Anthropic

    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    results: dict[str, dict[str, Any]] = {}
    print(f"Classifying {len(items)} videos via {ANTHROPIC_MODEL}…")

    for idx, video in enumerate(items, 1):
        vid = video["id"]
        sn = video.get("snippet", {})
        title = sn.get("title", "")
        desc = (sn.get("description", "") or "")[:600]

        try:
            msg = client.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=400,
                system=CLASSIFIER_SYSTEM,
                messages=[
                    {
                        "role": "user",
                        "content": f"標題：{title}\n\n描述：{desc}",
                    }
                ],
            )
            text = "".join(b.text for b in msg.content if hasattr(b, "text")).strip()
            if text.startswith("```"):
                text = text.strip("`")
                if text.startswith("json"):
                    text = text[4:].strip()
            parsed = json.loads(text)
            results[vid] = parsed
            if idx % 5 == 0 or idx == len(items):
                print(f"  [{idx}/{len(items)}] {title[:50]}…")
        except Exception as e:
            print(f"  ! failed for {vid}: {e}", file=sys.stderr)
            continue

    return results


# --------------------------------------------------------------------------
# Build final payload
# --------------------------------------------------------------------------

def parse_iso8601_duration(s: str) -> int:
    """PT1H2M3S → 3723 seconds. (We don't really need this but keep around.)"""
    import re

    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", s)
    if not m:
        return 0
    h, mi, se = m.groups(default="0")
    return int(h) * 3600 + int(mi) * 60 + int(se)


def to_int(s: Any) -> int:
    try:
        return int(s)
    except (TypeError, ValueError):
        return 0


def build_payload(videos: list[dict[str, Any]], classifications: dict[str, dict[str, Any]]) -> dict[str, Any]:
    from country_centroids import lookup as geo_lookup

    cases = []
    for v in videos:
        vid = v["id"]
        sn = v.get("snippet", {})
        st = v.get("statistics", {})
        cl = classifications.get(vid, {})
        thumbs = sn.get("thumbnails", {})
        thumb_url = (
            thumbs.get("maxres", {}).get("url")
            or thumbs.get("high", {}).get("url")
            or thumbs.get("default", {}).get("url")
            or f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
        )
        # If the LLM didn't give us coords, fall back to country centroid so
        # the case still appears on the map.
        lat = cl.get("lat")
        lon = cl.get("lon")
        if (lat is None or lon is None) and cl.get("country"):
            fb = geo_lookup(cl.get("country"), cl.get("city"))
            if fb:
                lat, lon = fb

        cases.append(
            {
                "id": vid,
                "title": sn.get("title", ""),
                "caseName": cl.get("caseName") or sn.get("title", ""),
                "description": (sn.get("description") or "")[:400],
                "thumbnail": thumb_url,
                "url": f"https://www.youtube.com/watch?v={vid}",
                "publishedAt": sn.get("publishedAt", ""),
                "viewCount": to_int(st.get("viewCount")),
                "likeCount": to_int(st.get("likeCount")),
                "commentCount": to_int(st.get("commentCount")),
                "crimeYear": cl.get("crimeYear"),
                "resolveYear": cl.get("resolveYear"),
                "country": cl.get("country"),
                "city": cl.get("city"),
                "lat": lat,
                "lon": lon,
                "caseType": cl.get("caseType") or "other",
                "status": cl.get("status") or "unknown",
                "memberOnly": False,  # API does not directly expose this
                "tags": cl.get("tags") or [],
                "milestones": [],
            }
        )
    cases.sort(key=lambda c: c["publishedAt"], reverse=True)
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "source": "youtube-api",
        "channel": {
            "id": YT_CHANNEL_ID,
            "handle": "@xdiaocha",
            "title": "X調查",
        },
        "cases": cases,
    }


# --------------------------------------------------------------------------
# Entry
# --------------------------------------------------------------------------

def fallback_to_mock() -> None:
    print("→ Falling back to mock data generator", file=sys.stderr)
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_mock", ROOT / "scripts" / "generate_mock_data.py"
    )
    if spec is None or spec.loader is None:
        print("Cannot load mock generator", file=sys.stderr)
        sys.exit(2)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.main()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=0, help="Process only first N videos")
    p.add_argument("--skip-classify", action="store_true", help="Skip LLM classification")
    p.add_argument("--no-cache", action="store_true", help="Re-fetch even if raw cache exists")
    args = p.parse_args()

    if not YT_API_KEY:
        print("⚠ YOUTUBE_API_KEY missing in .env — using mock data instead.", file=sys.stderr)
        fallback_to_mock()
        return 0

    RAW_CACHE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    if RAW_CACHE.exists() and not args.no_cache:
        print(f"Using cached raw videos ← {RAW_CACHE}")
        videos = json.loads(RAW_CACHE.read_text(encoding="utf-8"))
    else:
        print(f"Fetching from YouTube Data API v3 (channel {YT_CHANNEL_ID})…")
        with httpx.Client() as client:
            uploads = fetch_uploads_playlist_id(client, YT_CHANNEL_ID)
            print(f"  uploads playlist: {uploads}")
            ids = fetch_playlist_video_ids(client, uploads)
            print(f"  found {len(ids)} videos")
            videos = fetch_video_details(client, ids)
        RAW_CACHE.write_text(json.dumps(videos, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.limit > 0:
        videos = videos[: args.limit]
        print(f"  limited to first {len(videos)} videos")

    classifications: dict[str, dict[str, Any]] = {}
    if not args.skip_classify:
        classifications = classify_with_anthropic(videos)

    payload = build_payload(videos, classifications)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✓ Wrote {len(payload['cases'])} cases → {OUTPUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
