"""Show before/after for the 7 cases that got drilled down."""
import json, sys
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
cases = json.load(open(ROOT / "frontend/public/data/cases.json", encoding="utf-8"))["cases"]

DRILLED_IDS = {
    # From the run log
    # 釜山母女, 釜山公寓墜樓, 三浦和義, 大阪卡拉OK, 格力高森永, 首爾酒店連環, 小野悅男
}

# Find the 7 cases with refined coords by their case names
NAMES = [
    "釜山母女在家遭遇不測案",
    "釜山公寓墜樓案",
    "三浦和義事件",
    "大阪卡拉OK酒吧女店主遇害案",
    "格力高森永案",
    "首爾酒店連環案",
    "小野悅男事件",
]

print("=== 細化後位置 ===")
for c in cases:
    if c["caseName"] in NAMES:
        print(f"  {c['caseName']!r}")
        print(f"    城市: {c['country']} / {c['city']}")
        print(f"    lat/lon: ({c['lat']}, {c['lon']})")
        print()
