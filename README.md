# u2b-will-classifier 🔍

> 非官方粉絲專案 — 把 YouTube 頻道 [X調查](https://www.youtube.com/@xdiaocha) 介紹過的所有案件，做成多維度互動資料視覺化儀表板。

致敬 X調查 主持人 **Will**（純巧合：作者也叫 Will）。本專案僅展示影片**標題、縮圖與 metadata** 並導回原影片，屬合理使用範圍，**絕無重製內容、非營利**。

---

## ✨ Features

| 視圖 | 用什麼 | 看什麼 |
|---|---|---|
| 🗺 **案件地圖** | Leaflet + CARTO Dark 底圖 | 每案件 = 一個圓點。**顏色** = 類型，**大小** = 觀看數 |
| 📅 **雙軌時間軸** | vis-timeline | 上軌「案件壽命」（發生年→破案年的長條）；下軌「影片發布」 |
| 🎯 **類型 × 狀態 Sunburst** | ECharts | 內圈 = 案件類型，外圈 = 破案狀態。點一下會 toggle 該分類過濾器 |
| 💎 **觀眾熱度氣泡圖** | ECharts | X = 發布日，Y = 觀看數（log 軸），氣泡大小 = 按讚數，顏色 = 類型 |
| 🕸 **案件關聯網路圖** | Cytoscape (cose layout) | 邊 = 同國家 ∧ 同類型 ∧ 同年代（≤5 年）。聚類自然浮現 |

🔗 **Cross-filter 全聯動**：篩選器、Sunburst、地圖任一互動 → 其他四圖同步更新
🔍 **案件詳情抽屜**：點任何元素 → 右側 drawer 嵌入 YouTube 播放器 + 全 metadata
🌒 **Dark Theme**：「案件偵探板」氛圍，Noto Sans TC + JetBrains Mono

---

## 🏗 Architecture

```
              GitHub Pages
            (static frontend)
                  │
        ┌─────────▼─────────┐
        │  React + Vite +   │
        │  TS + Tailwind    │
        │  ECharts/Leaflet/ │
        │  vis-timeline/    │
        │  Cytoscape +      │
        │  Zustand          │
        └─────────▲─────────┘
                  │ fetch /data/cases.json
                  │
        ┌─────────┴─────────┐
        │  本地 Python 腳本   │
        │  scripts/refresh.py│
        │  ① YouTube Data    │
        │     API v3         │
        │  ② Anthropic Haiku │
        │     4.5 分類器      │
        │  → 寫 cases.json   │
        └────────────────────┘
```

無資料庫、無常駐後端，跟 `mlb-tracker`、`ig-autopilot` 同款全靜態風格。資料抓取是「**離線批次**」：本地跑 `refresh.py` → commit → push → Actions 自動部署。

---

## 🚀 Quick start

```powershell
# 1. Frontend dev (自動讀 mock 資料，不需 API key)
cd frontend
npm install
npm run dev          # http://localhost:5173/

# 2. 抓真實資料
cd ..
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r scripts/requirements.txt
copy .env.example .env       # 填入 YOUTUBE_API_KEY + ANTHROPIC_API_KEY
python scripts/refresh.py    # 全頻道完整 refresh
# 想快速測試只跑前 5 部：python scripts/refresh.py --limit 5
```

---

## 📁 Project layout

```
u2b-will-classifier/
├── .github/workflows/deploy.yml   GitHub Actions (Pages auto-deploy)
├── frontend/
│   ├── src/
│   │   ├── lib/
│   │   │   ├── types.ts           CaseRecord schema + 類型/狀態色票
│   │   │   ├── store.ts           Zustand cross-filter store
│   │   │   └── dataLoader.ts      fetch /data/cases.json
│   │   ├── components/
│   │   │   ├── Header.tsx
│   │   │   ├── FilterBar.tsx
│   │   │   └── CaseDetailDrawer.tsx (YouTube embed)
│   │   ├── views/
│   │   │   ├── MapView.tsx        Leaflet
│   │   │   ├── SunburstView.tsx   ECharts
│   │   │   ├── TimelineView.tsx   vis-timeline (雙軌)
│   │   │   ├── BubbleView.tsx     ECharts scatter (log Y)
│   │   │   └── NetworkView.tsx    Cytoscape (cose layout)
│   │   ├── App.tsx
│   │   ├── main.tsx
│   │   └── index.css              dark theme + Leaflet/vis tweaks
│   ├── public/data/cases.json     → mock 或真實資料（gitignored 不適用）
│   ├── vite.config.ts             base + manual chunks
│   ├── tailwind.config.js
│   └── package.json
├── scripts/
│   ├── refresh.py                 主管線
│   ├── generate_mock_data.py      34 筆假資料（無 API key 時 fallback）
│   └── requirements.txt
├── .env.example
├── .gitignore
├── DEPLOY.md
└── README.md
```

---

## 🧠 Data schema (`cases.json`)

每筆 case 結構（見 `frontend/src/lib/types.ts`）：

```ts
interface CaseRecord {
  id: string;                // YouTube video id
  title: string;             // 原影片標題
  caseName: string;          // LLM 抽出的案件正式名稱
  description?: string;
  thumbnail: string;
  url: string;               // YouTube 連結
  publishedAt: string;       // ISO date
  viewCount: number;
  likeCount: number;
  commentCount: number;
  crimeYear?: number;        // 案件實際發生年
  resolveYear?: number;      // 結案年
  country?: string;          // 中文國名
  city?: string;
  lat?: number;
  lon?: number;
  caseType: CaseType;        // murder|missing|serial|cult|fraud|disaster|mystery|kidnap|curio|other
  status: CaseStatus;        // solved|cold|partial|exonerated|ongoing|unknown
  memberOnly?: boolean;
  tags?: string[];
  milestones?: Array<{ date: string; event: string }>;
}
```

LLM 從標題（已含【標籤】+ 案件正式名稱）+ 描述 抽出來。Haiku 4.5 約 $0.05 / 100 集。

---

## 🚢 Deployment

見 [`DEPLOY.md`](./DEPLOY.md)。要點：

- Push `main` → Actions auto-builds → 部署到 `https://<user>.github.io/u2b-will-classifier/`
- 想自動化每週 refresh：DEPLOY.md 有現成的 cron workflow 範本

---

## 📜 Credits / 授權

- **資料來源**：YouTube 頻道 [X調查](https://www.youtube.com/@xdiaocha) — by Will
- **底圖**：CARTO Dark Matter (free tier) + OpenStreetMap
- **字型**：Noto Sans TC, JetBrains Mono (Google Fonts)
- **Icons**：Lucide
- **本專案**：MIT License；對 X調查影片內容**不主張任何權利**，僅引用標題、縮圖與引導性 metadata（合理使用 / 致敬）

---

## 🛣 Roadmap (給未來的我)

- [ ] yt-dlp 抓自動字幕 → LLM 二輪抽 case milestones（每案的關鍵事件時間線）
- [ ] 受害者/加害者 Sankey 圖（需字幕資料）
- [ ] 「假如你是偵探」quiz 互動模式
- [ ] 個人化「你還沒看過的隱藏好片」（LocalStorage）
- [ ] 中英雙語切換
- [ ] PWA 離線模式
