# Cloudflare Worker 部署步驟

這支 Worker 讓你傳一則 Telegram 訊息「跑一次」就能觸發 GitHub Actions 執行盤中即時檢查
(`mode=intraday_check`)。以下每一步都在 Cloudflare/Telegram/cron-job.org 的網頁上操作，**任何密鑰
值都由你自己貼進網頁欄位，不會有人（包含 Claude）幫你在網頁表單裡輸入密鑰**。

## 1. 建立 Worker、貼上程式碼

1. 登入 Cloudflare Dashboard → Workers & Pages → Create → Create Worker
2. 取個名字(例如 `stock-radar-intraday-trigger`)，Deploy 一次產生預設頁面
3. 進入該 Worker → Edit code(線上編輯器)→ 把整份 `index.js` 的內容貼進去，取代預設內容 → Save and deploy

## 2. 設定 Secret 環境變數

該 Worker 頁面 → Settings → Variables → Environment Variables → Add variable，**每一個都要點選
「Encrypt」變成 Secret**(不要用一般 Variable，一般 Variable 是明文可見的)：

| 名稱 | 值 | 說明 |
|---|---|---|
| `GITHUB_PAT` | 你自己申請的 fine-grained PAT | 範圍：只勾 `stock-radar-intraday` 這個 repo，權限只給 `Actions: Read and write`，建議設 90 天到期 |
| `TELEGRAM_CHAT_ID` | 你的 Telegram chat id | 跟 GitHub Actions Secrets 裡 `TELEGRAM_CHAT_ID` 同一組數字 |
| `TELEGRAM_BOT_TOKEN` | (選填)你的 Bot Token | 有設定的話，觸發成功/失敗都會收到一則確認訊息；不設也完全能動，只是收不到確認 |

加完存檔會自動重新部署。

## 3. 把 Telegram Webhook 指到這支 Worker

Worker 部署後會有一個網址，例如 `https://stock-radar-intraday-trigger.<你的帳號>.workers.dev`。

在瀏覽器網址列直接打開下面這個網址(把 `<BOT_TOKEN>` 換成你的 Bot Token、`<WORKER_URL>` 換成上面那
個網址)，看到回應裡 `"ok":true` 就代表設定成功：

```
https://api.telegram.org/bot<BOT_TOKEN>/setWebhook?url=<WORKER_URL>
```

（這一步只是打開一個網址、不是登入任何網站表單，所以你自己在瀏覽器貼著打開就好，不需要額外工具。）

## 4. cron-job.org：17:00 收盤後統計

建立一個新的 cron job：

- URL：`https://api.github.com/repos/BC0910/stock-radar-intraday/actions/workflows/intraday.yml/dispatches`
- Method：`POST`
- Schedule：週一到週五，台灣時間 17:00（cron-job.org 通常用 UTC，換算成 UTC 09:00）
- Headers：
  - `Authorization: Bearer <你的 GitHub PAT>`（貼在 cron-job.org 後台的 Header 欄位，跟上面同一組
    PAT 或另外申請一組都可以）
  - `Accept: application/vnd.github+json`
  - `Content-Type: application/json`
- Body：
  ```json
  {"ref": "main", "inputs": {"mode": "postclose_stats"}}
  ```

## 驗證

- 傳「跑一次」給你的 Telegram Bot，幾秒內應該會收到「已收到，開始執行...」(如果你設定了
  `TELEGRAM_BOT_TOKEN`)，接著到 repo 的 Actions 分頁應該會看到一筆新的 `workflow_dispatch` run，
  `mode` 是 `intraday_check`。
- cron-job.org 那筆要等到週一到週五 17:00 才會自然觸發；也可以在 cron-job.org 後台手動按一次
  「Run now」立即測試。
