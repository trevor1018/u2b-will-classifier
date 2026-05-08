"""Targeted web_search test — does giving the LLM a manual location hint
let it find more precise coords than the user's hint alone?

User-provided hints:
  ZYTNb5ffhZw  麗貝卡分手赴約事件     -> 英國威爾士布里貞德 (Bridgend, Wales)
  JweVa9pQPYE  1998年男子冤獄案      -> 俄亥俄州巴柏頓市 (Barberton, Ohio)
  OUmFmt9X9rc  郵輪墜海事件集 (3 集) -> 3 條航線；建議標在路線中央海域

Cost: 3 × ~$0.09 = ~$0.27 (±50%).
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
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")

CACHE_PATH = ROOT / "scripts/.cache/classifications.json"
RAW_PATH = ROOT / "scripts/.cache/raw_videos.json"

HINTS = {
    "ZYTNb5ffhZw": {
        "case": "麗貝卡分手赴約事件",
        "hint": "案件發生於英國威爾士的布里貞德 (Bridgend, Wales, UK)。請用 web_search 找具體鎮/街/landmark。",
    },
    "JweVa9pQPYE": {
        "case": "1998年男子冤獄案",
        "hint": "案件發生於美國俄亥俄州巴柏頓市 (Barberton, Ohio, USA)。請用 web_search 找具體街/案發地點。",
    },
    "OUmFmt9X9rc": {
        "case": "郵輪墜海事件集 (合集)",
        "hint": (
            "這部影片講三個郵輪墜海故事，路線為:\n"
            "1) 邁阿密 -> 牙買加\n"
            "2) 克羅地亞 -> 威尼斯\n"
            "3) 紐奧良 -> 科蘇梅爾\n"
            "由於是合集無單一地點。請用 web_search 找出 3 個故事的「具體事件」"
            "(船名/年份/具體墜海座標) 後，回傳 3 條航線的平均中央海域 lat/lon "
            "(亦即 3 個起訖點中點的平均) 作為單一代表座標。"
        ),
    },
}

SYS = """你是案件地點研究員。給你一個案件 + 已知地點提示，
你會用 web_search 工具找該案件的具體精確位置。

回傳 JSON，只有 JSON、不要其他文字。Schema:
{
  "city": str | null,        // 中文具體城市/區/鎮名
  "country": str | null,
  "lat": number | null,      // 具體精度經緯度
  "lon": number | null,
  "confidence": "high" | "medium" | "low",
  "evidence": str | null     // 搜尋摘要中的關鍵句
}

規則：
- 先用 web_search 印證提示的地點，找具體位置
- 若搜尋結果不一致或找不到 → 全 null（寧可 null 也不錯標）
- lat/lon 必須是 city/landmark 級精度
"""


def call(client, video_id: str, title: str, info: dict) -> dict | None:
    user_msg = (
        f"案件：{info['case']}\n"
        f"影片標題：{title}\n\n"
        f"地點提示：{info['hint']}\n\n"
        f"請用 web_search 確認並回傳 JSON。"
    )
    backoff = 30
    for attempt in range(3):
        try:
            msg = client.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=500,
                tools=[
                    {"type": "web_search_20250305", "name": "web_search", "max_uses": 2}
                ],
                system=SYS,
                messages=[{"role": "user", "content": user_msg}],
            )
            break
        except Exception as e:
            if "rate_limit_error" in str(e) or "429" in str(e):
                print(f"  ! 429 — sleeping {backoff}s", file=sys.stderr)
                time.sleep(backoff)
                backoff *= 2
                continue
            print(f"  ! error: {e}", file=sys.stderr)
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
    print(f"  ! couldn't parse: {text[:200]!r}")
    return None


def main():
    cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    raw_by_id = {v["id"]: v for v in json.loads(RAW_PATH.read_text(encoding="utf-8"))}

    from anthropic import Anthropic

    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    print(f"=== Targeted web_search test (3 cases with manual hints) ===\n")

    for idx, (vid, info) in enumerate(HINTS.items(), 1):
        v = raw_by_id.get(vid)
        if not v:
            print(f"[{idx}/3] {info['case']} — NOT FOUND in raw cache!")
            continue
        title = v.get("snippet", {}).get("title", "")
        print(f"[{idx}/3] {info['case']}")
        print(f"  title: {title[:80]}")
        result = call(client, vid, title, info)
        if not result:
            print(f"  → FAILED to get a response\n")
            continue

        print(f"  → city={result.get('city')!r}  country={result.get('country')!r}")
        print(f"  → lat={result.get('lat')}  lon={result.get('lon')}")
        print(f"  → confidence={result.get('confidence')}")
        print(f"  → evidence: {(result.get('evidence') or '')[:100]}")

        if result.get("lat") is not None and result.get("lon") is not None:
            cache.setdefault(vid, {})
            cache[vid]["lat"] = result["lat"]
            cache[vid]["lon"] = result["lon"]
            if result.get("city"):
                cache[vid]["city"] = result["city"]
            if result.get("country"):
                cache[vid]["country"] = result["country"]
            print(f"  ✓ cache updated\n")
        else:
            print(f"  ⚠ no coords returned, cache unchanged\n")

        if idx < len(HINTS):
            time.sleep(16)  # rate-limit pacing

    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Done. Run `python scripts/refresh.py --skip-classify` to rebuild cases.json")


if __name__ == "__main__":
    main()
