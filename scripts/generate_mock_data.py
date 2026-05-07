"""Generate mock cases.json so the frontend works without any API keys.

The cases below are inspired by real X調查 episodes (titles seen in public search
results) plus plausible fictional fillers, with believable structured fields so
all 5 visualisations have enough variety to render.

Run:
    python scripts/generate_mock_data.py

Writes to: frontend/public/data/cases.json
"""
from __future__ import annotations

import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

random.seed(42)

# (caseName, country, city, lat, lon, type, status, crimeYear, resolveYear, isReal)
RAW = [
    # Real / observed-in-public episodes
    ("名古屋卡拉OK店事件", "日本", "名古屋", 35.1815, 136.9066, "murder", "solved", 2023, 2024, True),
    ("金鰲島汽車墜海事件", "韓國", "金鰲島", 34.7574, 127.7424, "mystery", "unknown", 2018, None, True),
    ("華麗號郵輪失蹤案", "美國", "邁阿密", 25.7617, -80.1918, "missing", "cold", 2017, None, True),
    ("澳洲金礦大救援", "澳洲", "塔斯曼尼亞", -41.4545, 145.9707, "disaster", "solved", 2006, 2006, True),
    ("釜山草原莊旅館殺人事件", "韓國", "釜山", 35.1796, 129.0756, "murder", "cold", 2002, None, True),
    ("法國斯蒂芬·迪特里希案", "法國", "史特拉斯堡", 48.5734, 7.7521, "murder", "solved", 1996, 2017, True),
    ("威利湖畔豪宅迷案", "美國", "西雅圖", 47.6062, -122.3321, "murder", "partial", 2010, 2015, True),
    ("DNA證據40年懸案", "英國", "倫敦", 51.5074, -0.1278, "murder", "solved", 1985, 2024, True),
    # Plausible fictional fillers (matches the channel's repertoire)
    ("洛杉磯山區連環失蹤案", "美國", "洛杉磯", 34.0522, -118.2437, "serial", "cold", 1992, None, False),
    ("北海道溫泉旅館命案", "日本", "札幌", 43.0618, 141.3545, "murder", "solved", 2015, 2019, False),
    ("曼谷邪教集體失蹤", "泰國", "曼谷", 13.7563, 100.5018, "cult", "partial", 2008, 2013, False),
    ("莫斯科地鐵爆炸案", "俄羅斯", "莫斯科", 55.7558, 37.6173, "disaster", "solved", 2010, 2011, False),
    ("布宜諾斯艾利斯古宅謀殺", "阿根廷", "布宜諾斯艾利斯", -34.6037, -58.3816, "murder", "exonerated", 1988, 2005, False),
    ("德里少女失蹤事件", "印度", "新德里", 28.6139, 77.2090, "missing", "cold", 2014, None, False),
    ("開普敦海岸線命案", "南非", "開普敦", -33.9249, 18.4241, "murder", "ongoing", 2021, None, False),
    ("漢城江南整形連環詐騙", "韓國", "首爾", 37.5665, 126.9780, "fraud", "solved", 2018, 2020, False),
    ("溫哥華華人區綁架案", "加拿大", "溫哥華", 49.2827, -123.1207, "kidnap", "solved", 2003, 2004, False),
    ("墨西哥城販毒集團解碼", "墨西哥", "墨西哥城", 19.4326, -99.1332, "serial", "ongoing", 2019, None, False),
    ("斯德哥爾摩公寓神秘血案", "瑞典", "斯德哥爾摩", 59.3293, 18.0686, "mystery", "cold", 1976, None, False),
    ("雅典衛城古文物盜竊", "希臘", "雅典", 37.9838, 23.7275, "fraud", "solved", 2012, 2014, False),
    ("羅馬地下室囚禁少女", "義大利", "羅馬", 41.9028, 12.4964, "kidnap", "solved", 1998, 2007, False),
    ("柏林冷戰時期間諜疑雲", "德國", "柏林", 52.5200, 13.4050, "mystery", "cold", 1985, None, False),
    ("奈洛比商人離奇身亡", "肯亞", "奈洛比", -1.2921, 36.8219, "murder", "ongoing", 2020, None, False),
    ("孟買貧民窟連環姦殺", "印度", "孟買", 19.0760, 72.8777, "serial", "solved", 1995, 2002, False),
    ("聖保羅大火幕後", "巴西", "聖保羅", -23.5505, -46.6333, "disaster", "partial", 2004, 2009, False),
    ("胡志明市豪門遺產謎案", "越南", "胡志明市", 10.8231, 106.6297, "fraud", "ongoing", 2017, None, False),
    ("清邁夜市少女失蹤", "泰國", "清邁", 18.7883, 98.9853, "missing", "cold", 2016, None, False),
    ("奧斯陸雪地裸屍", "挪威", "奧斯陸", 59.9139, 10.7522, "mystery", "solved", 2009, 2014, False),
    ("台北廢墟連環縱火", "台灣", "台北", 25.0330, 121.5654, "serial", "solved", 2011, 2013, False),
    ("仰光僧侶神秘事件", "緬甸", "仰光", 16.8409, 96.1735, "curio", "unknown", 2007, None, False),
    ("赫爾辛基極光下的謀殺", "芬蘭", "赫爾辛基", 60.1699, 24.9384, "murder", "cold", 2013, None, False),
    ("布拉格百年公寓詛咒", "捷克", "布拉格", 50.0755, 14.4378, "curio", "unknown", 1923, None, False),
    ("伊斯坦堡市集自殺炸彈", "土耳其", "伊斯坦堡", 41.0082, 28.9784, "disaster", "solved", 2016, 2018, False),
    ("利馬安第斯山脈失蹤客", "秘魯", "利馬", -12.0464, -77.0428, "missing", "cold", 2005, None, False),
]

CASE_TYPE_LABEL = {
    "murder": "謀殺",
    "missing": "失蹤",
    "serial": "連環",
    "cult": "邪教",
    "fraud": "詐欺",
    "disaster": "災難",
    "mystery": "未解之謎",
    "kidnap": "綁架",
    "curio": "奇人異事",
    "other": "其他",
}


def make_video_id(idx: int) -> str:
    """Generate a fake but plausible 11-char YT video id."""
    rng = random.Random(idx * 1000 + 7)
    chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
    return "".join(rng.choice(chars) for _ in range(11))


def main() -> None:
    cases = []
    base_publish = datetime(2023, 1, 7, tzinfo=timezone.utc)
    for idx, (case_name, country, city, lat, lon, ctype, status, cyear, ryear, real) in enumerate(RAW):
        published = base_publish + timedelta(days=idx * 7 + random.randint(-2, 2))
        # Simulate engagement: some viral, some niche
        base_views = random.randint(80_000, 1_200_000)
        viral_boost = random.choice([1, 1, 1, 1, 1, 1, 2.5, 4])
        view_count = int(base_views * viral_boost)
        like_count = int(view_count * random.uniform(0.025, 0.06))
        comment_count = int(view_count * random.uniform(0.002, 0.008))

        title_label = "懸案" if status == "cold" else ("DNA" if random.random() < 0.2 else "案件")
        hook_phrases = [
            "真相出乎所有人意料",
            "兇手竟然是他",
            "完美犯罪",
            "21年後冷案告破",
            "深夜離奇事件",
            "萬萬沒想到",
        ]
        title = f"【{title_label}】{random.choice(hook_phrases)}，{case_name} | X調查"

        vid = make_video_id(idx)
        cases.append({
            "id": vid,
            "title": title,
            "caseName": case_name,
            "description": f"X調查 第{idx + 1}集 — 介紹{country}{city}的{CASE_TYPE_LABEL[ctype]}案件，發生於{cyear}年。",
            "thumbnail": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
            "url": f"https://www.youtube.com/watch?v={vid}",
            "publishedAt": published.isoformat(),
            "viewCount": view_count,
            "likeCount": like_count,
            "commentCount": comment_count,
            "crimeYear": cyear,
            "resolveYear": ryear,
            "country": country,
            "city": city,
            "lat": lat,
            "lon": lon,
            "caseType": ctype,
            "status": status,
            "memberOnly": idx % 11 == 7,
            "tags": [title_label] + (["DNA"] if "DNA" in title else []),
            "milestones": [],
        })

    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "source": "mock",
        "channel": {
            "id": "UCOyshL6rKK1GqwoEfy_ehBg",
            "handle": "@xdiaocha",
            "title": "X調查",
        },
        "cases": cases,
    }

    out_path = Path(__file__).parent.parent / "frontend" / "public" / "data" / "cases.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(cases)} mock cases → {out_path}")


if __name__ == "__main__":
    main()
