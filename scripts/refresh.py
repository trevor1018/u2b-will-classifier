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

# Windows cmd / PowerShell often defaults to cp950 which can't encode emoji.
# Force UTF-8 so we never crash on print statements.
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"
load_dotenv(ENV_PATH)

YT_API_KEY = os.environ.get("YOUTUBE_API_KEY", "").strip()
YT_CHANNEL_ID = os.environ.get("YT_CHANNEL_ID", "UCOyshL6rKK1GqwoEfy_ehBg").strip()
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001").strip()

OUTPUT = ROOT / "frontend" / "public" / "data" / "cases.json"
RAW_CACHE = ROOT / "scripts" / ".cache" / "raw_videos.json"
# Persistent classification cache keyed by video id. Only videos not in cache
# hit the LLM, so weekly incremental refreshes cost ~$0.0005 instead of $0.05.
CLASSIFICATION_CACHE = ROOT / "scripts" / ".cache" / "classifications.json"


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

地理欄位特別重要：
- 永遠優先給「具體到城市/縣/州」的地點，不要只給國家。
- 標題中的地名（例：釜山、洛杉磯、福岡、北海道、巴黎、倫敦）就是答案，直接用。
- 即使描述沒明說，根據案件名稱（例：「奧斯汀酸奶店案」→Austin TX、「光明市母子事件」
  →光明市）、人名地名線索，盡量推斷最具體的城市。
- lat/lon 必須給數字（你已知道主要城市座標）；只有真的無法判斷時才給 null。
- 若是跨國案件（受害者一國、犯案地另一國），country/city 用「實際案發地」，不用受害者國籍。

Schema:
{
  "caseName": str,           // 從標題抽出的案件正式名稱（去掉【標籤】、戲劇化 hook）
  "country": str | null,     // 中文國名，如「日本」「美國」「韓國」「英國」「不明」
  "city": str | null,        // 具體中文城市/地區名（不要回「不明」，盡量給）
  "lat": number | null,      // 城市級緯度（不要給國家中心點）
  "lon": number | null,      // 城市級經度
  "crimeYear": int | null,   // 案件實際發生年份
  "resolveYear": int | null, // 結案/判決年份（若已破案）
  "caseType": str,           // murder|missing|serial|cult|fraud|robbery|escape|disaster|mystery|kidnap|curio|other
  "status": str,             // solved|cold|partial|exonerated|ongoing|unknown
  "tags": [str]              // 標題【】內的標籤
}
"""


def load_classification_cache() -> dict[str, dict[str, Any]]:
    """Two-tier cache:
       1. scripts/.cache/classifications.json — local dev fast path (gitignored)
       2. frontend/public/data/cases.json     — committed, lets CI runners hit
          cache too without needing the .cache/ dir checked in
    """
    if CLASSIFICATION_CACHE.exists():
        return json.loads(CLASSIFICATION_CACHE.read_text(encoding="utf-8"))

    if OUTPUT.exists():
        # Reconstruct {vid: classified_fields} from previously committed cases.json
        prev = json.loads(OUTPUT.read_text(encoding="utf-8"))
        derived: dict[str, dict[str, Any]] = {}
        classified_fields = (
            "caseName", "country", "city", "lat", "lon",
            "crimeYear", "resolveYear", "caseType", "status", "tags",
        )
        for c in prev.get("cases", []):
            vid = c.get("id")
            if not vid:
                continue
            # Skip "uncached" rows (default-only fields suggest never classified)
            if c.get("caseType") in (None, "other") and c.get("country") is None:
                continue
            derived[vid] = {k: c.get(k) for k in classified_fields}
        if derived:
            print(f"  (derived {len(derived)} cache entries from committed cases.json)")
        return derived

    return {}


def save_classification_cache(cache: dict[str, dict[str, Any]]) -> None:
    CLASSIFICATION_CACHE.parent.mkdir(parents=True, exist_ok=True)
    CLASSIFICATION_CACHE.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def classify_with_anthropic(
    items: list[dict[str, Any]], force: bool = False
) -> dict[str, dict[str, Any]]:
    """Returns {video_id: classified_dict}.

    Persistent cache keyed by video id. Only cache misses hit the LLM, so
    weekly incremental refreshes cost ~$0.0005 instead of $0.05 (full batch).
    Pass force=True to re-classify everything (e.g. after schema change).
    """
    cache = {} if force else load_classification_cache()
    todo = [v for v in items if v["id"] not in cache]
    cached_n = len(items) - len(todo)
    print(
        f"Classification: {cached_n} cached, {len(todo)} need LLM "
        f"({'force' if force else 'incremental'} mode)"
    )

    if not todo:
        return {v["id"]: cache[v["id"]] for v in items if v["id"] in cache}

    if not ANTHROPIC_API_KEY:
        print("⚠ ANTHROPIC_API_KEY missing — skipping classification of new videos", file=sys.stderr)
        return {v["id"]: cache[v["id"]] for v in items if v["id"] in cache}

    from anthropic import Anthropic

    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    print(f"Classifying {len(todo)} new videos via {ANTHROPIC_MODEL}…")

    # Errors that mean "no point retrying — bail out, save progress, ask user"
    fatal_substrings = (
        "credit_balance_too_low",
        "insufficient_quota",
        "invalid_api_key",
        "authentication_error",
        "permission_error",
    )

    save_every = 10  # checkpoint cache periodically so a crash doesn't lose progress
    for idx, video in enumerate(todo, 1):
        vid = video["id"]
        sn = video.get("snippet", {})
        title = sn.get("title", "")
        # Bumped from 600 → 2000: longer descriptions sometimes carry the
        # specific city / year that title alone doesn't reveal.
        desc = (sn.get("description", "") or "")[:2000]

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
            cache[vid] = parsed
            if idx % 5 == 0 or idx == len(todo):
                print(f"  [{idx}/{len(todo)}] {title[:50]}…")
            if idx % save_every == 0:
                save_classification_cache(cache)
        except Exception as e:
            err = str(e)
            if any(s in err for s in fatal_substrings):
                print(
                    f"\n!! Fatal API error after {idx-1}/{len(todo)} successful "
                    f"({len(cache)} total in cache):\n   {err}\n"
                    f"   Saving cache and bailing out. Top up and re-run to "
                    f"continue from where we left off.",
                    file=sys.stderr,
                )
                save_classification_cache(cache)
                return {v["id"]: cache[v["id"]] for v in items if v["id"] in cache}
            print(f"  ! failed for {vid}: {err}", file=sys.stderr)
            continue

    save_classification_cache(cache)
    print(f"  cache now holds {len(cache)} classifications")
    return {v["id"]: cache[v["id"]] for v in items if v["id"] in cache}


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


# Frontend's known case types — anything outside this is normalised below.
KNOWN_CASE_TYPES = {
    "murder", "missing", "serial", "cult", "fraud", "robbery", "escape",
    "disaster", "mystery", "kidnap", "curio", "other",
}
# Maps LLM-invented synonyms onto our supported set.
CASE_TYPE_ALIASES = {
    "theft": "robbery",
    "rescue": "disaster",
    "attack": "murder",
    "child_abuse": "other",
    "poison": "murder",
    "stalking": "other",
    "arson": "other",
    "extortion": "fraud",
    "abduction": "kidnap",
    "assault": "murder",
    "homicide": "murder",
    "scam": "fraud",
    "jailbreak": "escape",
    "prison_break": "escape",
    "fugitive": "escape",
}
KNOWN_STATUSES = {"solved", "cold", "partial", "exonerated", "ongoing", "unknown"}

# Strong keywords (anything containing these = escape case, no further check)
ESCAPE_KEYWORDS = ("越獄", "越狱", "逃獄", "脫獄", "脱獄", "越牢", "獄逃")
# Weaker keywords — only count as escape when paired with prison context
ESCAPE_CONTEXT_KEYWORDS = ("逃亡", "逃跑", "逃離", "潜逃", "潛逃")
PRISON_KEYWORDS = ("監獄", "监狱", "囚犯", "獄友", "獄卒", "牢", "監禁", "服刑", "犯人", "罪犯")


def post_classify_escape(title: str, case_name: str, current_type: str) -> str:
    """Override LLM classification to 'escape' when title or caseName clearly
    indicates a jailbreak / fugitive case. Bucketing fugitive-from-prison
    cases as 'other' was a recurring miss in the first-pass LLM run.
    """
    if current_type == "escape":
        return current_type
    haystack = f"{title} {case_name}"
    if any(k in haystack for k in ESCAPE_KEYWORDS):
        return "escape"
    # caseName usually distils the case essence — if 逃亡 ends up there, this
    # is almost always a fugitive case (X調查's content domain is crime, not
    # refugees / war). So treat caseName-level 逃亡 as a strong signal.
    if any(k in case_name for k in ESCAPE_CONTEXT_KEYWORDS):
        return "escape"
    # Title-level 逃亡 is weaker — pair with prison context to avoid false
    # positives.
    if any(k in title for k in ESCAPE_CONTEXT_KEYWORDS) and any(
        k in title for k in PRISON_KEYWORDS
    ):
        return "escape"
    return current_type


# Different writings of the same country — collapse to a canonical zh-Hant form
COUNTRY_CANONICAL = {
    # 簡 → 繁
    "美国": "美國",
    "英国": "英國",
    "德国": "德國",
    "中国": "中國",
    "法国": "法國",
    "韩国": "韓國",
    "俄罗斯": "俄羅斯",
    "意大利": "義大利",
    "葡萄牙": "葡萄牙",
    "西班牙": "西班牙",
    "印度": "印度",
    "希腊": "希臘",
    "希腊": "希臘",
    # 同義異名
    "澳大利亞": "澳洲",
    "澳大利亚": "澳洲",
    "新西蘭": "紐西蘭",
    "新西兰": "紐西蘭",
    "印尼": "印尼",
    "印度尼西亞": "印尼",
    "印度尼西亚": "印尼",
    "孟加拉國": "孟加拉",
    "孟加拉国": "孟加拉",
    "老撾": "寮國",
    "老挝": "寮國",
    "比利时": "比利時",
    "瑞典": "瑞典",
    "挪威": "挪威",
    "丹麦": "丹麥",
    "捷克": "捷克",
    "波兰": "波蘭",
    "匈牙利": "匈牙利",
    "土耳其": "土耳其",
    "墨西哥": "墨西哥",
    "巴西": "巴西",
    "阿根廷": "阿根廷",
    "智利": "智利",
    "秘鲁": "秘魯",
    "哥伦比亚": "哥倫比亞",
    "委內瑞拉": "委內瑞拉",
    "南非": "南非",
    "肯尼亚": "肯亞",
    "肯亚": "肯亞",
    "尼日利亚": "奈及利亞",
    "尼日利亞": "奈及利亞",
    "奈及利亚": "奈及利亞",
    "埃及": "埃及",
    "摩洛哥": "摩洛哥",
    "尼泊尔": "尼泊爾",
    "巴基斯坦": "巴基斯坦",
    "伊朗": "伊朗",
    "伊拉克": "伊拉克",
    "以色列": "以色列",
    "沙特阿拉伯": "沙烏地阿拉伯",
    "沙乌地阿拉伯": "沙烏地阿拉伯",
    "阿联酋": "阿聯",
    "阿聯酋": "阿聯",
    "缅甸": "緬甸",
    "柬埔寨": "柬埔寨",
    "越南": "越南",
    "马来西亚": "馬來西亞",
    "新加坡": "新加坡",
    "菲律宾": "菲律賓",
    "台湾": "台灣",
    "臺灣": "台灣",
    "香港": "香港",
    "澳门": "澳門",
    "蘇聯": "蘇聯",
    "苏联": "蘇聯",
    "南斯拉夫": "南斯拉夫",
    "羅馬尼亞": "羅馬尼亞",
    "罗马尼亚": "羅馬尼亞",
    "保加利亞": "保加利亞",
    "保加利亚": "保加利亞",
    "烏克蘭": "烏克蘭",
    "乌克兰": "烏克蘭",
    "白俄羅斯": "白俄羅斯",
    "白俄罗斯": "白俄羅斯",
    "波蘭": "波蘭",
    "塞爾維亞": "塞爾維亞",
    "塞尔维亚": "塞爾維亞",
}


def normalize_country(c: str | None) -> str | None:
    if not c:
        return None
    c = c.strip()
    if not c:
        return None
    # Sometimes LLM returns "美國加州" — strip suffix to canonical country name
    for canonical in set(COUNTRY_CANONICAL.values()):
        if c.startswith(canonical) and len(c) > len(canonical):
            return canonical
    return COUNTRY_CANONICAL.get(c, c)


def normalize_case_type(t: str | None) -> str:
    if not t:
        return "other"
    t = t.lower().strip()
    if t in KNOWN_CASE_TYPES:
        return t
    if t in CASE_TYPE_ALIASES:
        return CASE_TYPE_ALIASES[t]
    return "other"


def normalize_status(s: str | None) -> str:
    if not s:
        return "unknown"
    s = s.lower().strip()
    return s if s in KNOWN_STATUSES else "unknown"


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
        country = normalize_country(cl.get("country"))

        # If the LLM didn't give us coords, fall back to country centroid so
        # the case still appears on the map.
        lat = cl.get("lat")
        lon = cl.get("lon")
        if (lat is None or lon is None) and country:
            fb = geo_lookup(country, cl.get("city"))
            if fb:
                lat, lon = fb

        case_type = normalize_case_type(cl.get("caseType"))
        # Title/caseName-keyword fallback for the escape category — LLM tended
        # to bucket 越獄/逃亡 as "other" since the original schema didn't have
        # escape as a separate type.
        case_type = post_classify_escape(
            sn.get("title", ""),
            cl.get("caseName") or "",
            case_type,
        )

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
                "country": country,
                "city": cl.get("city"),
                "lat": lat,
                "lon": lon,
                "caseType": case_type,
                "status": normalize_status(cl.get("status")),
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
    p.add_argument(
        "--reclassify",
        action="store_true",
        help="Force re-classification of all videos (ignore classification cache). "
             "Use after changing the schema/prompt.",
    )
    p.add_argument(
        "--refine-geo",
        action="store_true",
        help="Re-classify only cases whose cache entry lacks a specific city "
             "or LLM-given lat/lon. Cheap (~$0.12 for ~110 cases) but greatly "
             "reduces country-centroid stacking on the map.",
    )
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
    if args.refine_geo and not args.skip_classify:
        # Evict cache entries that lack a specific city + LLM lat/lon so the
        # next pass through classify_with_anthropic re-runs only those.
        cache = load_classification_cache()
        before = len(cache)
        evicted = 0
        for vid, cl in list(cache.items()):
            city_ok = bool(cl.get("city")) and cl.get("city") not in ("不明", "未知", "未明")
            coord_ok = cl.get("lat") is not None and cl.get("lon") is not None
            if not (city_ok and coord_ok):
                del cache[vid]
                evicted += 1
        save_classification_cache(cache)
        print(f"--refine-geo: evicted {evicted}/{before} cache entries lacking specific geo")

    if not args.skip_classify:
        classifications = classify_with_anthropic(videos, force=args.reclassify)

    payload = build_payload(videos, classifications)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✓ Wrote {len(payload['cases'])} cases → {OUTPUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
