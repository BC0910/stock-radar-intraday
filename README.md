# stock-radar-intraday

盤中即時上市(TWSE)/上櫃(TPEx)成交值排行工具。跟前一交易日收盤前30名比較，找出「新上榜」股票，
用 Telegram 推播異動、GitHub Pages 顯示目前完整排行。全程跑在 GitHub Actions，不需要本機常駐。

跟收盤後工具 `stock-radar` 是刻意分開、不整合的獨立專案，只有 `config/groups.json`（族群分類設定）
是從 `stock-radar/config/groups.json` **手動複製**過來當參考。`stock-radar` 那邊的分類若有更動，
要跟著手動複製更新這份檔案（目前沒有自動同步機制，因為 `stock-radar` 還不是 git repo）。

## 執行方式

```bash
pip install -r requirements.txt
python src/main.py --dry-run   # 本機測試：抓真實資料、印出結果，但不推播 Telegram、不寫回 state/docs
python src/main.py             # 正式執行：完整跑一次抓取→比對→推播→寫檔
```

## 環境變數

- `TELEGRAM_BOT_TOKEN`：Telegram Bot API token
- `TELEGRAM_CHAT_ID`：要推播到的 chat ID

本機測試時用 `--dry-run` 可以不設這兩個變數。正式執行（含 GitHub Actions）需要設定，GitHub Actions
是從 repo 的 Secrets 讀進來。

## 排程

GitHub Actions 一天跑兩次：台灣時間 11:00、13:00（週一到週五），對應 `.github/workflows/intraday.yml`
裡的 UTC cron `0 3 * * 1-5` 與 `0 5 * * 1-5`。非交易日（週末/假日/尚未開盤）會偵測即時報價時間戳不
是今天，自動跳過、不推播不寫檔。

## GitHub Pages

repo 設定 Settings → Pages → Deploy from branch: `main` / `/docs`，之後排行頁面固定網址是
`https://<你的帳號>.github.io/stock-radar-intraday/`，可以加到手機主畫面當捷徑。

## 資料夾說明

- `config/groups.json`：族群分類（參考版本，見上）
- `src/`：程式碼
- `docs/`：GitHub Pages 靜態頁面 + 給頁面讀的 JSON
- `data/close_cache/`：前一交易日官方收盤成交值快取
- `data/state/`：新上榜/連續留榜天數/去重複推播用的狀態檔（由 GitHub Actions 執行後寫回 repo）
