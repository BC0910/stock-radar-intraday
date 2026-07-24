/**
 * Telegram webhook -> GitHub Actions workflow_dispatch 觸發器。
 *
 * 使用者傳「跑一次」給 Telegram Bot -> Telegram 呼叫這支 Worker -> 驗證是本人、驗證觸發指令文字 ->
 * 呼叫 GitHub API 觸發 stock-radar-intraday 的 intraday.yml(mode=intraday_check)。
 *
 * 需要的 Secret(在 Cloudflare Dashboard 的 Settings -> Variables 加，型態選 Secret，不要選一般
 * Variable)：
 *   - GITHUB_PAT: 只有 Actions:Read/Write 權限、限定這個 repo 的 fine-grained PAT
 *   - TELEGRAM_CHAT_ID: 使用者自己的 Telegram chat id(跟 GitHub Actions Secrets 裡那組一樣)
 *   - TELEGRAM_BOT_TOKEN: 選填，設定了才會在觸發後回覆一則「已收到」訊息
 */

const TRIGGER_TEXT = "跑一次";
const GITHUB_OWNER = "BC0910";
const GITHUB_REPO = "stock-radar-intraday";
const WORKFLOW_FILE = "intraday.yml";

export default {
  async fetch(request, env) {
    if (request.method !== "POST") {
      return new Response("ok", { status: 200 });
    }

    let update;
    try {
      update = await request.json();
    } catch {
      return new Response("ok", { status: 200 });
    }

    const message = update.message;
    const chatId = message && message.chat && message.chat.id;
    const text = message && message.text;

    if (String(chatId) !== String(env.TELEGRAM_CHAT_ID) || text !== TRIGGER_TEXT) {
      // 不是本人或不是觸發指令，直接忽略，一律回 200 避免 Telegram 一直重送這個 webhook。
      return new Response("ignored", { status: 200 });
    }

    const dispatchResp = await fetch(
      `https://api.github.com/repos/${GITHUB_OWNER}/${GITHUB_REPO}/actions/workflows/${WORKFLOW_FILE}/dispatches`,
      {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${env.GITHUB_PAT}`,
          "Accept": "application/vnd.github+json",
          "User-Agent": "stock-radar-intraday-cloudflare-worker",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ ref: "main", inputs: { mode: "intraday_check" } }),
      }
    );

    const ok = dispatchResp.status === 204;

    if (env.TELEGRAM_BOT_TOKEN) {
      const replyText = ok
        ? "已收到，開始執行盤中即時檢查..."
        : `觸發失敗(GitHub API 回應 ${dispatchResp.status})，稍後再試一次。`;
      await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ chat_id: chatId, text: replyText }),
      });
    }

    return new Response(ok ? "dispatched" : "dispatch_failed", { status: 200 });
  },
};
