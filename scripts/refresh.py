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
import time
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


UNKNOWN_CITY = {
    "不明", "未知", "未明", "?", "未提及", "未明確指出", "未明確",
    "未說明", "未指明", "未特別說明",
}
# Strings that look like city names but really aren't a single point
# (oceans, polar regions, generic descriptors). Geocoding them produces
# random nonsense — e.g. Nominatim mapped "大西洋" to Osaka.
NON_CITY_KEYWORDS = (
    "大西洋", "太平洋", "印度洋", "北冰洋", "南冰洋",
    "北極", "南極", "海上", "公海", "海面", "深海",
    "山區", "沙漠", "森林", "鄉間", "郊外",
)


def is_geocodable_city(city: str | None) -> bool:
    if not city:
        return False
    if city in UNKNOWN_CITY:
        return False
    if any(kw in city for kw in NON_CITY_KEYWORDS):
        return False
    return True


def geocode_via_nominatim(
    client: httpx.Client, city: str, country: str | None
) -> tuple[float, float] | None:
    """Single Nominatim lookup. Returns (lat, lon) or None."""
    q = f"{city}, {country}" if country and country not in UNKNOWN_CITY else city
    try:
        r = client.get(
            "https://nominatim.openstreetmap.org/search",
            params={
                "q": q,
                "format": "json",
                "limit": 1,
                "accept-language": "zh-TW,zh,en",
            },
            headers={
                # Nominatim requires a UA identifying the app (see usage policy).
                "User-Agent": "u2b-will-classifier/0.1 (github.com/trevor1018/u2b-will-classifier)",
            },
            timeout=20,
        )
        r.raise_for_status()
        data = r.json()
        if data:
            return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception as e:
        print(f"  ! geocode failed for {q!r}: {e}", file=sys.stderr)
    return None


DRILL_DOWN_SYSTEM = """你是案件地點細化研究員。給你一個已知城市的案件，
你要用 web_search 把位置從「城市中心」細化到「街區/地標/飯店/車站」級。

回傳 JSON，只有 JSON、不要其他文字。Schema：
{
  "landmark": str | null,   // 中文地標名 (例: 「Cecil Hotel」「澀谷站」「歌舞伎町」)
  "city": str | null,       // 更具體的中文行政區 (例: 「洛杉磯市中心」「澀谷區」)
  "lat": number | null,     // 地標精度經緯度
  "lon": number | null,
  "evidence": str | null    // 搜尋摘要中的關鍵句
}

關鍵規則：
- 用 web_search 工具去查
- 找不到明確 landmark → 全部 null（保持現有 city 中心）
- 不要 hallucinate；寧可 null 也不要錯
- 跨國案件：用實際案發地點，不是受害者國籍
- lat/lon 必須在已知城市範圍內（合理性檢查）
"""


def drill_down_via_web_search(
    client,
    title: str,
    case_name: str,
    country: str | None,
    city: str | None,
    current_lat: float | None,
    current_lon: float | None,
    max_retries: int = 3,
) -> dict[str, Any] | None:
    """Use web_search to refine an already-pinned city to a landmark/district.
    Returns parsed dict (with lat/lon if found) or None.
    """
    user_msg = (
        f"案件名稱：{case_name}\n"
        f"影片標題：{title}\n"
        f"已知國家：{country}\n"
        f"已知城市：{city}\n\n"
        f"請用 web_search 找出該案件在 {city} 的具體地標/街區/飯店/車站位置，"
        f"回傳 JSON。"
    )
    backoff = 30
    for attempt in range(max_retries):
        try:
            msg = client.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=400,
                tools=[
                    {
                        "type": "web_search_20250305",
                        "name": "web_search",
                        "max_uses": 2,
                    }
                ],
                system=DRILL_DOWN_SYSTEM,
                messages=[{"role": "user", "content": user_msg}],
            )
            break
        except Exception as e:
            err_str = str(e)
            if "rate_limit_error" in err_str or "429" in err_str:
                print(
                    f"  ! 429 — sleeping {backoff}s ({attempt + 1}/{max_retries})",
                    file=sys.stderr,
                )
                time.sleep(backoff)
                backoff *= 2
                continue
            print(f"  ! drill-down call failed: {e}", file=sys.stderr)
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
        result = json.loads(text)
    except json.JSONDecodeError:
        import re

        m = re.search(r"\{[^{}]*\}", text, re.DOTALL)
        if not m:
            return None
        try:
            result = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None

    # Sanity check: if coords are >150km from current city centre, reject —
    # LLM probably got confused and returned a different city's landmark.
    if (
        result.get("lat") is not None
        and result.get("lon") is not None
        and current_lat is not None
        and current_lon is not None
    ):
        from math import cos, radians

        dlat = abs(result["lat"] - current_lat)
        dlon = abs(result["lon"] - current_lon) * cos(radians(current_lat))
        # Rough degrees → km. 1° ≈ 111 km
        dist_km = ((dlat ** 2 + dlon ** 2) ** 0.5) * 111
        if dist_km > 150:
            print(
                f"  ! drill-down rejected: {dist_km:.0f}km from current city (likely wrong)",
                file=sys.stderr,
            )
            return None

    return result


def drill_down_top_city_stacks(
    cache: dict[str, dict[str, Any]],
    cases: list[dict[str, Any]],
    raw_videos: dict[str, dict[str, Any]],
    top_n_groups: int = 6,
) -> int:
    """For the N largest city-coord stacks (multiple cases at exactly the
    same lat/lon), use web_search to drill down to landmark precision.
    """
    if not ANTHROPIC_API_KEY:
        print("⚠ ANTHROPIC_API_KEY missing — skipping drill-down", file=sys.stderr)
        return 0

    from collections import defaultdict
    from country_centroids import COUNTRY_CENTROIDS

    # Identify city-stack groups (exact same lat/lon, not country centroid)
    country_centroid_keys = {
        (round(v[0], 4), round(v[1], 4))
        for v in COUNTRY_CENTROIDS.values()
        if v is not None
    }
    groups: dict[tuple[float, float], list[dict]] = defaultdict(list)
    for c in cases:
        if c["lat"] is None or c["lon"] is None:
            continue
        key = (round(c["lat"], 4), round(c["lon"], 4))
        if key in country_centroid_keys:
            continue
        groups[key].append(c)

    # Filter to >1 case per group, sort by size descending
    multi = [(k, v) for k, v in groups.items() if len(v) > 1]
    multi.sort(key=lambda x: -len(x[1]))
    target_groups = multi[:top_n_groups]

    targets: list[dict] = []
    for _, group in target_groups:
        targets.extend(group)

    if not targets:
        print("Drill-down: no city stacks found.")
        return 0

    print(
        f"Drill-down: top {len(target_groups)} city-stack groups, "
        f"{len(targets)} cases. Pacing 16s/call to stay under 50k tok/min."
    )

    from anthropic import Anthropic

    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    fixed = 0
    INTER_CALL_DELAY = 16

    for idx, c in enumerate(targets, 1):
        vid = c["id"]
        v = raw_videos.get(vid)
        if not v:
            continue
        title = v.get("snippet", {}).get("title", "")
        case_name = c["caseName"]
        country = c.get("country")
        city = c.get("city")
        if not city or city in {"不明", "未知", "未明"}:
            print(f"  [{idx}/{len(targets)}] {case_name[:25]} -> no city to drill from")
            continue

        result = drill_down_via_web_search(
            client, title, case_name, country, city, c["lat"], c["lon"]
        )
        if result and result.get("lat") is not None and result.get("lon") is not None:
            cache.setdefault(vid, {})
            cache[vid]["lat"] = result["lat"]
            cache[vid]["lon"] = result["lon"]
            if result.get("city"):
                cache[vid]["city"] = result["city"]
            fixed += 1
            ev = (result.get("evidence") or "")[:30]
            print(
                f"  [{idx}/{len(targets)}] {case_name[:25]} -> "
                f"{result.get('landmark', '?')} "
                f"({result['lat']:.4f}, {result['lon']:.4f})  «{ev}»"
            )
        else:
            print(f"  [{idx}/{len(targets)}] {case_name[:25]} -> no landmark found")
        if idx % 5 == 0:
            save_classification_cache(cache)
        if idx < len(targets):
            time.sleep(INTER_CALL_DELAY)

    save_classification_cache(cache)
    print(f"Drill-down: {fixed}/{len(targets)} refined to landmark precision")
    return fixed


WEB_SEARCH_SYSTEM = """你是案件地點研究員。給你一個案件名稱與影片標題，
你會用 web_search 工具找出該案件的「具體發生地點」(city + 經緯度)。

回傳 JSON 物件，只有 JSON、不要任何解釋文字。Schema：
{
  "city": str | null,     // 中文城市/區名 (如「洛杉磯」「釜山」「茨城縣築波市」)
  "country": str | null,  // 中文國名
  "lat": number | null,
  "lon": number | null,
  "confidence": str       // "high" | "medium" | "low"
}

規則：
- 真的搜不到具體城市時，所有欄位都回 null（不要硬猜，不要用國家中心點）
- 跨國案件用「實際案發地」，不用受害者國籍
- lat/lon 必須是城市級精度（不是國家中心點）"""


def lookup_via_web_search(
    client,
    title: str,
    case_name: str,
    hint_country: str | None,
    max_retries: int = 3,
) -> dict[str, Any] | None:
    """One Claude call with web_search enabled. Returns parsed dict or None.

    Web-search results inflate the input-token budget fast, so this call is
    the place where the org rate limit (50k input tok/min on free tier) bites.
    Catches 429 and backs off — caller still does an additional inter-call
    sleep so we stay under the cap.
    """
    user_msg = (
        f"案件名稱：{case_name}\n"
        f"影片完整標題：{title}\n"
        f"目前粗略判斷國家：{hint_country or '不明'}\n\n"
        f"請搜尋並回傳該案件的具體地點 JSON。"
    )
    backoff = 30
    for attempt in range(max_retries):
        try:
            msg = client.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=400,
                tools=[
                    {
                        "type": "web_search_20250305",
                        "name": "web_search",
                        "max_uses": 2,  # smaller search budget = fewer input toks
                    }
                ],
                system=WEB_SEARCH_SYSTEM,
                messages=[{"role": "user", "content": user_msg}],
            )
            break
        except Exception as e:
            err_str = str(e)
            if "rate_limit_error" in err_str or "429" in err_str:
                print(
                    f"  ! 429 rate limit — sleeping {backoff}s "
                    f"(attempt {attempt + 1}/{max_retries})",
                    file=sys.stderr,
                )
                time.sleep(backoff)
                backoff *= 2
                continue
            print(f"  ! web_search call failed: {e}", file=sys.stderr)
            return None
    else:
        print("  ! gave up after retries", file=sys.stderr)
        return None

    # Concatenate all text blocks (web_search tool_use blocks are interleaved
    # but we just want the final JSON answer the model emits)
    text = "".join(
        b.text for b in msg.content if hasattr(b, "text")
    ).strip()

    if not text:
        return None
    # Strip markdown fences if present
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Model added prose around the JSON — find the first {...} block
        import re

        match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        print(f"  ! couldn't parse web_search response: {text[:200]!r}", file=sys.stderr)
        return None


def web_search_geo_lookup(
    cache: dict[str, dict[str, Any]],
    videos: list[dict[str, Any]],
) -> int:
    """For each cache entry that still lacks a specific city + lat/lon,
    ask Claude with web_search enabled to find the case's real location.

    Targets ~55 entries that LLM couldn't pin down from title+description
    alone. Costs roughly 0.005-0.01 USD per case.
    Returns number of entries successfully updated.
    """
    if not ANTHROPIC_API_KEY:
        print("⚠ ANTHROPIC_API_KEY missing — skipping web_search lookup", file=sys.stderr)
        return 0

    todo: list[tuple[str, str, str]] = []  # (vid, title, case_name)
    video_by_id = {v["id"]: v for v in videos}
    for vid, cl in cache.items():
        # Already has good geo → skip
        if (
            cl.get("lat") is not None
            and cl.get("lon") is not None
            and is_geocodable_city(cl.get("city"))
        ):
            continue
        v = video_by_id.get(vid)
        if not v:
            continue
        title = v.get("snippet", {}).get("title", "")
        case_name = cl.get("caseName") or title
        if not title:
            continue
        todo.append((vid, title, case_name))

    if not todo:
        print("Web search geo: nothing to look up.")
        return 0

    print(
        f"Web search geo: {len(todo)} cases to look up via Claude+web_search "
        f"(~{len(todo) * 16}s with rate-limit pacing)…"
    )
    from anthropic import Anthropic

    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    fixed = 0
    save_every = 5
    # Inter-call sleep — the free-tier limit is 50k input tok/min and each
    # web_search call easily pulls 5-10k tokens of result content. 16s
    # between calls keeps us safely under.
    INTER_CALL_DELAY = 16

    for idx, (vid, title, case_name) in enumerate(todo, 1):
        hint = cache[vid].get("country")
        result = lookup_via_web_search(client, title, case_name, hint)
        if result and result.get("lat") is not None and result.get("lon") is not None:
            cache[vid]["lat"] = result["lat"]
            cache[vid]["lon"] = result["lon"]
            if result.get("city"):
                cache[vid]["city"] = result["city"]
            if result.get("country"):
                cache[vid]["country"] = result["country"]
            fixed += 1
            print(
                f"  [{idx}/{len(todo)}] {case_name[:30]} -> "
                f"{result.get('city')} ({result.get('lat'):.4f}, {result.get('lon'):.4f}) "
                f"[{result.get('confidence', '?')}]"
            )
        else:
            print(f"  [{idx}/{len(todo)}] {case_name[:30]} -> nothing found")
        if idx % save_every == 0:
            save_classification_cache(cache)
        if idx < len(todo):
            time.sleep(INTER_CALL_DELAY)

    save_classification_cache(cache)
    print(f"Web search geo: {fixed}/{len(todo)} pinned")
    return fixed


def geocode_missing_coords(cache: dict[str, dict[str, Any]]) -> int:
    """Fill in lat/lon for cache entries where the LLM gave a real city
    string but couldn't / didn't return coordinates. Free (Nominatim/OSM),
    rate-limited at 1 req/sec per their usage policy.
    Returns number of entries newly fixed.
    """
    todo: list[tuple[str, str, str | None]] = []
    for vid, cl in cache.items():
        if cl.get("lat") is not None and cl.get("lon") is not None:
            continue
        city = cl.get("city")
        if not is_geocodable_city(city):
            continue
        todo.append((vid, city, cl.get("country")))

    if not todo:
        print("Geocode: nothing to do.")
        return 0

    print(f"Geocode: {len(todo)} entries need lat/lon — Nominatim @ 1 req/sec…")
    fixed = 0
    save_every = 5
    with httpx.Client() as client:
        for idx, (vid, city, country) in enumerate(todo, 1):
            coords = geocode_via_nominatim(client, city, country)
            if coords:
                cache[vid]["lat"] = coords[0]
                cache[vid]["lon"] = coords[1]
                fixed += 1
                print(
                    f"  [{idx}/{len(todo)}] {city}, {country} -> "
                    f"({coords[0]:.4f}, {coords[1]:.4f})"
                )
            else:
                print(f"  [{idx}/{len(todo)}] {city}, {country} -> no result")
            if idx % save_every == 0:
                save_classification_cache(cache)
            if idx < len(todo):
                time.sleep(1.1)  # be polite — slightly over 1 req/sec

    save_classification_cache(cache)
    print(f"Geocode: {fixed}/{len(todo)} successfully placed")
    return fixed


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
            "points",  # multi-pin list for compilation cases
        )
        for c in prev.get("cases", []):
            vid = c.get("id")
            if not vid:
                continue
            # Skip "uncached" rows (default-only fields suggest never classified)
            if c.get("caseType") in (None, "other") and c.get("country") is None:
                continue
            derived[vid] = {
                k: c.get(k) for k in classified_fields if c.get(k) is not None
            }
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
                # Pass through optional multi-pin list for compilation /
                # multi-incident cases (cruise overboard compilation, etc.)
                **({"points": cl["points"]} if cl.get("points") else {}),
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
    p.add_argument(
        "--geocode-only",
        action="store_true",
        help="Skip YouTube/LLM. Just run Nominatim geocoding for cache "
             "entries that have city but no lat/lon, then re-emit cases.json. "
             "Free; ~1s per missing entry.",
    )
    p.add_argument(
        "--web-search-geo",
        action="store_true",
        help="For cases the LLM couldn't pin down from title+description, "
             "use Claude's web_search tool to find the real location. "
             "Costs ~$0.01 per remaining case (~$0.40 total).",
    )
    p.add_argument(
        "--drill-down-cities",
        action="store_true",
        help="For top-6 city-stack groups (multiple cases at the same city "
             "centre), use web_search to find landmark/district precision. "
             "Costs ~$0.50 for ~49 cases.",
    )
    p.add_argument(
        "--drill-down-top",
        type=int,
        default=6,
        help="How many top city-stack groups to drill down (default 6). "
             "All 33 = ~111 cases ~$1.10.",
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

    # Standalone drill-down pass: refine city-stack cases to landmark precision
    if args.drill_down_cities:
        cache = load_classification_cache()
        cases = json.loads(OUTPUT.read_text(encoding="utf-8"))["cases"]
        raw_by_id = {v["id"]: v for v in videos}
        drill_down_top_city_stacks(cache, cases, raw_by_id, top_n_groups=args.drill_down_top)
        # Rebuild cases.json from updated cache
        classifications = {
            v["id"]: cache[v["id"]] for v in videos if v["id"] in cache
        }
        payload = build_payload(videos, classifications)
        OUTPUT.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"Wrote {len(payload['cases'])} cases -> {OUTPUT}")
        return 0

    # Standalone web-search lookup pass: for cases LLM couldn't pin down,
    # let Claude search the web for the real location. Costs ~$0.40 / 55 cases.
    if args.web_search_geo:
        cache = load_classification_cache()
        web_search_geo_lookup(cache, videos)
        # Then fall through to write cases.json with the updated cache.
        videos_for_payload = videos
        classifications = {
            v["id"]: cache[v["id"]] for v in videos_for_payload if v["id"] in cache
        }
        payload = build_payload(videos_for_payload, classifications)
        OUTPUT.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"Wrote {len(payload['cases'])} cases -> {OUTPUT}")
        return 0

    # Standalone geocoding pass: fix entries that already have a city but
    # no lat/lon. Free, just slow (1 req/sec to Nominatim).
    if args.geocode_only:
        cache = load_classification_cache()
        geocode_missing_coords(cache)
        # Build payload using only cached classifications (no YouTube fetch)
        videos_for_payload = videos if RAW_CACHE.exists() else []
        classifications = {
            v["id"]: cache[v["id"]] for v in videos_for_payload if v["id"] in cache
        }
        payload = build_payload(videos_for_payload, classifications)
        OUTPUT.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"Wrote {len(payload['cases'])} cases -> {OUTPUT}")
        return 0

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

    if args.skip_classify:
        # Use whatever the cache already has; no LLM calls.
        cache_now = load_classification_cache()
        classifications = {
            v["id"]: cache_now[v["id"]] for v in videos if v["id"] in cache_now
        }
        print(f"--skip-classify: using {len(classifications)} cached classifications")
    else:
        classifications = classify_with_anthropic(videos, force=args.reclassify)
        # After LLM classification, fill in any city-only entries via
        # Nominatim (free OSM geocoder, rate-limited at 1 req/sec).
        cache_now = load_classification_cache()
        if geocode_missing_coords(cache_now) > 0:
            classifications = {
                v["id"]: cache_now[v["id"]] for v in videos if v["id"] in cache_now
            }

    payload = build_payload(videos, classifications)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✓ Wrote {len(payload['cases'])} cases → {OUTPUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
