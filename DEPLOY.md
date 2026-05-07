# Deploy to GitHub Pages

Pure static frontend. Same flow as `mlb-tracker` / `ig-autopilot`.

```
本地跑 refresh.py  →  git push main  →  GitHub Actions  →  GitHub Pages
                                       (~1-2 min)
```

---

## One-time setup

### 1. 建 GitHub repo

```bash
cd D:\python\u2b-will-classifier
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin git@github.com:<你的帳號>/u2b-will-classifier.git
git push -u origin main
```

### 2. 啟用 GitHub Pages

1. 開 GitHub repo → **Settings** → **Pages**
2. **Build and deployment** → **Source** → 選 **GitHub Actions**

### 3. 確認 Vite base path

`frontend/vite.config.ts` 的 `base` 預設是 `/u2b-will-classifier/`。
如果你的 repo 名字不同（例如 fork 後改名），改成 `/<repo-name>/`。

---

## Auto-deploy

每次 push 到 `main` 觸發 `.github/workflows/deploy.yml`：

```
push main → checkout → setup-node 20 → npm ci → npm run build → upload-pages-artifact → deploy-pages
```

完成後網站會在：
```
https://<你的帳號>.github.io/u2b-will-classifier/
```

也可以從 GitHub repo → **Actions** → **Deploy to GitHub Pages** → **Run workflow** 手動觸發。

---

## 抓真實資料的流程

GitHub Actions 只負責「**靜態建置 + 部署**」，**不會自己抓 YouTube 資料** —— 因為那需要你自己的 API key。

### Local refresh + push

```powershell
# 1. (一次性) 安裝 Python 依賴
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r scripts/requirements.txt

# 2. 設定 keys
copy .env.example .env
# 編輯 .env 填入 YOUTUBE_API_KEY、ANTHROPIC_API_KEY

# 3. 抓資料
python scripts/refresh.py
# → 會更新 frontend/public/data/cases.json

# 4. push
git add frontend/public/data/cases.json
git commit -m "data: refresh from X調查"
git push
```

### CLI 選項

| 參數 | 用途 |
|---|---|
| `--limit N` | 只處理前 N 部影片（測試 LLM 用） |
| `--skip-classify` | 抓 YouTube metadata 但不跑 LLM 分類 |
| `--no-cache` | 忽略 `scripts/.cache/` 重新抓 |

### 如果沒設 keys？
`refresh.py` 偵測到 `YOUTUBE_API_KEY` 為空時會自動 fallback 跑 `generate_mock_data.py`，產生 34 筆假資料。前端照常運作。

---

## 排程：每週自動 refresh（選做）

可以加一個 GitHub Actions cron job，每週日凌晨自動跑 `refresh.py` 然後 commit 新資料。
範例：建立 `.github/workflows/weekly-refresh.yml`：

```yaml
name: Weekly refresh
on:
  schedule:
    - cron: "0 18 * * 6"   # 每週六 18:00 UTC = 週日凌晨 02:00 (UTC+8)
  workflow_dispatch:

jobs:
  refresh:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -r scripts/requirements.txt
      - run: python scripts/refresh.py
        env:
          YOUTUBE_API_KEY: ${{ secrets.YOUTUBE_API_KEY }}
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
      - name: Commit if changed
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add frontend/public/data/cases.json
          git diff --staged --quiet || git commit -m "data: weekly refresh"
          git push
```

API keys 設在 GitHub repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**。

---

## 費用

| 項目 | 月費 |
|---|---|
| GitHub Pages 託管 | $0 |
| GitHub Actions（部署 + 週更）| $0（免費 2000 min/月，這個專案用不到 1%） |
| YouTube Data API v3 | $0（10,000 units/天免費 quota） |
| Anthropic Haiku 4.5 分類 | ~$0.05 / 100 集（一次性，每週只增量） |

合計：**幾乎是 $0**。
