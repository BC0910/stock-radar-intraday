"""組出 Telegram 推播訊息內容 + 呼叫 Telegram Bot API 送出。

訊息內容(依規格)：時段、新上榜股票清單(代號/名稱/族群/連續留榜天數)、連續第3天的額外標註、一段可
直接複製貼到 Claude App 查詢的題詞、GitHub Pages 連結。
"""
import os

import requests

TELEGRAM_API_BASE = "https://api.telegram.org"


def _format_stock_line(stock: dict, tag: str = "") -> str:
    return f"• {stock['code']} {stock['name']}（{stock['group']}，連續第{stock['consecutive_days']}天）{tag}"


def build_claude_query_prompt(stocks: list) -> str:
    if not stocks:
        return ""
    names = "、".join(f"{s['name']}({s['code']})" for s in stocks)
    groups = sorted({s["group"] for s in stocks if s["group"] != "未分類"})
    prompt = f"{names} 最近為什麼成交值大增？有什麼相關新聞或題材？"
    if groups:
        prompt += f"（所屬族群：{'/'.join(groups)}）"
    return prompt


def build_message(session_label: str, new_entrants: list, day3_entrants: list, pages_url: str) -> str:
    lines = [f"📡 盤中成交值排行異動（{session_label}）"]

    day3_codes = {s["code"] for s in day3_entrants}

    if new_entrants:
        lines.append("")
        lines.append(f"新上榜 {len(new_entrants)} 檔：")
        for s in new_entrants:
            tag = "🔥連續第3天" if s["code"] in day3_codes else ""
            lines.append(_format_stock_line(s, tag))

    extra_day3 = [s for s in day3_entrants if s["code"] not in {n["code"] for n in new_entrants}]
    if extra_day3:
        lines.append("")
        lines.append(f"連續留榜滿3天 {len(extra_day3)} 檔：")
        for s in extra_day3:
            lines.append(_format_stock_line(s, "🔥"))

    all_flagged = new_entrants + extra_day3
    prompt = build_claude_query_prompt(all_flagged)
    if prompt:
        lines.append("")
        lines.append("📋 可複製貼到 Claude App 的查詢題詞：")
        lines.append(prompt)

    lines.append("")
    lines.append(f"🔗 完整排行：{pages_url}")

    return "\n".join(lines)


def send_message(text: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise RuntimeError("缺少 TELEGRAM_BOT_TOKEN 或 TELEGRAM_CHAT_ID 環境變數，無法推播")

    url = f"{TELEGRAM_API_BASE}/bot{token}/sendMessage"
    resp = requests.post(url, data={"chat_id": chat_id, "text": text}, timeout=15)
    resp.raise_for_status()
    payload = resp.json()
    if not payload.get("ok"):
        raise RuntimeError(f"Telegram 推播失敗: {payload}")
