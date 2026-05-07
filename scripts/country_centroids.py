"""Fallback (country, city) → (lat, lon) lookup so cases still land on the map
even when the LLM didn't pull coordinates.

Coverage focuses on countries X調查 has historically featured — easy to extend.
"""
from __future__ import annotations

# Country centroid (rough geographic centre). Source: free-geographic-data.
COUNTRY_CENTROIDS: dict[str, tuple[float, float]] = {
    "日本": (36.2048, 138.2529),
    "韓國": (35.9078, 127.7669),
    "中國": (35.8617, 104.1954),
    "台灣": (23.6978, 120.9605),
    "美國": (37.0902, -95.7129),
    "加拿大": (56.1304, -106.3468),
    "墨西哥": (23.6345, -102.5528),
    "英國": (55.3781, -3.4360),
    "法國": (46.2276, 2.2137),
    "德國": (51.1657, 10.4515),
    "義大利": (41.8719, 12.5674),
    "西班牙": (40.4637, -3.7492),
    "葡萄牙": (39.3999, -8.2245),
    "荷蘭": (52.1326, 5.2913),
    "比利時": (50.5039, 4.4699),
    "瑞士": (46.8182, 8.2275),
    "奧地利": (47.5162, 14.5501),
    "瑞典": (60.1282, 18.6435),
    "挪威": (60.4720, 8.4689),
    "丹麥": (56.2639, 9.5018),
    "芬蘭": (61.9241, 25.7482),
    "波蘭": (51.9194, 19.1451),
    "捷克": (49.8175, 15.4730),
    "希臘": (39.0742, 21.8243),
    "土耳其": (38.9637, 35.2433),
    "俄羅斯": (61.5240, 105.3188),
    "烏克蘭": (48.3794, 31.1656),
    "印度": (20.5937, 78.9629),
    "巴基斯坦": (30.3753, 69.3451),
    "孟加拉": (23.6850, 90.3563),
    "泰國": (15.8700, 100.9925),
    "越南": (14.0583, 108.2772),
    "馬來西亞": (4.2105, 101.9758),
    "新加坡": (1.3521, 103.8198),
    "印尼": (-0.7893, 113.9213),
    "菲律賓": (12.8797, 121.7740),
    "緬甸": (21.9162, 95.9560),
    "柬埔寨": (12.5657, 104.9910),
    "澳洲": (-25.2744, 133.7751),
    "紐西蘭": (-40.9006, 174.8860),
    "巴西": (-14.2350, -51.9253),
    "阿根廷": (-38.4161, -63.6167),
    "智利": (-35.6751, -71.5430),
    "秘魯": (-9.1900, -75.0152),
    "哥倫比亞": (4.5709, -74.2973),
    "南非": (-30.5595, 22.9375),
    "肯亞": (-0.0236, 37.9062),
    "埃及": (26.0975, 31.2357),
    "奈及利亞": (9.0820, 8.6753),
    "摩洛哥": (31.7917, -7.0926),
    "沙烏地阿拉伯": (23.8859, 45.0792),
    "伊朗": (32.4279, 53.6880),
    "以色列": (31.0461, 34.8516),
    "阿聯": (23.4241, 53.8478),
    "不明": None,  # explicit unknown — return None
}


def lookup(country: str | None, city: str | None = None) -> tuple[float, float] | None:
    """Return (lat, lon) for the most specific known location, else None."""
    if not country:
        return None
    val = COUNTRY_CENTROIDS.get(country)
    if val is None:
        # try fuzzy: maybe LLM returned "美國加州" or "日本東京" — match prefix
        for k, v in COUNTRY_CENTROIDS.items():
            if v is None:
                continue
            if country.startswith(k):
                return v
        return None
    return val
