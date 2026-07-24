# stock-radar-intraday

盤中即時上市(TWSE)/上櫃(TPEx)成交值排行工具。以 `config/groups.json` 族群分類為主軸，用 Telegram
推播「前7大族群動態」「前50名個股異動(新上榜/持續上升/快速上升)」「可貼去問 Claude 的查詢題詞」三
則訊息，GitHub Pages 顯示目前完整排行。全程跑在 GitHub Actions，不需要本機常駐。

跟收盤後工具 `stock-radar` 是刻意分開、不整合的獨立專案，只有 `config/groups.json`（族群分類設定）
是從 `stock-radar/config/groups.json` **手動複製**過來當參考。`stock-radar` 那邊的分類若有更動，
要跟著手動複製更新這份檔案（目前沒有自動同步機制，因為 `stock-radar` 還不是 git repo）。

## 執行方式

```bash
pip install -r requirements.txt
python src/main.py --mode intraday_check --dry-run    # 本機測試：抓即時報價，印出結果，不推播不寫回 state/docs
python src/main.py --mode postclose_stats --dry-run   # 本機測試：抓官方收盤值(要等收盤後資料才會齊)
python src/main.py --mode intraday_check               # 正式執行：完整跑一次抓取→分析→推播→寫檔
```

## 環境變數

- `TELEGRAM_BOT_TOKEN`：Telegram Bot API token
- `TELEGRAM_CHAT_ID`：要推播到的 chat ID

本機測試時用 `--dry-run` 可以不設這兩個變數。正式執行（含 GitHub Actions）需要設定，GitHub Actions
是從 repo 的 Secrets 讀進來。

## 觸發機制（v3：不再依賴 GitHub 內建 schedule）

實測發現 GitHub Actions 內建 `schedule:` cron 對剛建立/剛修改的 workflow 有無法預期的延遲、甚至完全
不觸發的問題（cron 語法、UTC 換算、Actions 權限、Telegram 發送都個別驗證過沒問題，純粹是 GitHub 排
程佇列本身不可靠），因此改成兩種外部觸發方式，都是呼叫同一支 `workflow_dispatch` API、用 `mode`
這個 input 參數區分行為：

- **`intraday_check`（盤中即時檢查）**：你自己傳一則 Telegram 訊息「跑一次」給 Bot，由
  Cloudflare Worker 驗證是本人後觸發。部署步驟見 [`cloudflare-worker/README.md`](cloudflare-worker/README.md)。
- **`postclose_stats`（收盤後統計）**：cron-job.org 每個交易日台灣時間 17:00 定時呼叫，用官方收盤
  成交值(比即時報價準確)重新算一次。設定步驟同樣在
  [`cloudflare-worker/README.md`](cloudflare-worker/README.md) 的第4節。

兩種模式都會偵測「資料還沒準備好」(非交易日/尚未開盤/收盤資料還沒公布)並自動跳過，不寫入 state、不
推播。

## GitHub Pages

repo 設定 Settings → Pages → Deploy from branch: `main` / `/docs`，之後排行頁面固定網址是
`https://<你的帳號>.github.io/stock-radar-intraday/`，可以加到手機主畫面當捷徑。

## 資料夾說明

- `config/groups.json`：族群分類（參考版本，見上）
- `src/`：程式碼
- `cloudflare-worker/`：Telegram「跑一次」觸發用的 Worker 程式碼 + 部署說明
- `docs/`：GitHub Pages 靜態頁面 + 給頁面讀的 JSON
- `data/close_cache/`：官方收盤成交值快取(前一交易日基準 + 當天收盤後統計用)
- `data/state/`：族群排名歷史、個股排名歷史、訊息去重複用的狀態檔（由 GitHub Actions 執行後寫回
  repo）
