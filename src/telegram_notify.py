"""組出 Telegram 推播訊息(v2: 族群/個股趨勢版，共3則) + 呼叫 Telegram Bot API 送出。

訊息1：前7大族群(前50名，依族群總成交值排序) + 昨日對比趨勢
訊息2：前50名次異動(新上榜/持續上榜/快速上升)
訊息3：可直接複製貼到 Claude App 的查詢題詞(合併成一則，各題詞空行分隔)；只給新進榜的族群/個股
"""
import os

import requests

TELEGRAM_API_BASE = "https://api.telegram.org"

_DIRECTION_EMOJI = {"up": "🔴", "down": "🟢", "flat": "⚪"}


def _trend_text(trend) -> str:
    if trend == "new":
        return "新進榜"
    if trend > 0:
        return f"↑{trend}"
    if trend < 0:
        return f"↓{-trend}"
    return "→"


def build_message1(top_groups_with_trend: list, declined_group_names: list) -> str:
    """top_groups_with_trend: group_analysis.attach_trend() 的第一個回傳值。"""
    lines = ["前7大族群（前50名）"]
    for g in top_groups_with_trend:
        names = "、".join(s["name"] for s in g["representative_stocks"])
        emoji = _DIRECTION_EMOJI[g["direction"]]
        lines.append(f"{g['rank']}. {g['name']}（{g['count']}檔）{emoji} {names}　{_trend_text(g['trend'])}")

    if declined_group_names:
        lines.append("")
        lines.append(f"📉 趨勢下降：{'、'.join(declined_group_names)}（昨日前7，今日掉出）")

    return "\n".join(lines)


def _format_stock_line2(stock: dict, extra: str = "") -> str:
    group_part = f"〔{stock['group']}〕" if stock.get("group") else ""
    return f"・{stock['name']}（{stock['code']}）{group_part}{extra}"


def build_message2(new_entrants: list, persistent_rise: list, fast_rise: list) -> str:
    lines = ["前50名次異動"]

    if new_entrants:
        lines.append("新上榜（首日出現）")
        for s in new_entrants:
            lines.append(_format_stock_line2(s))
        lines.append("")

    if persistent_rise:
        lines.append("持續上榜")
        for s in persistent_rise:
            lines.append(_format_stock_line2(s, f"連續{s['streak_days']}天留在前20名"))
        lines.append("")

    if fast_rise:
        lines.append("快速上升")
        for s in fast_rise:
            lines.append(_format_stock_line2(s, f"單日由{s['prev_rank']}名衝進{s['rank']}名"))
        lines.append("")

    return "\n".join(lines).rstrip()


def build_message3(top_groups_with_trend: list, flagged_stocks: list) -> str:
    """top_groups_with_trend: 訊息1 的前7大族群(每組附代表股)。flagged_stocks: 訊息2 挑出的股票
    (new_entrants+persistent_rise+fast_rise，已依代號去重)。兩邊都各自出一則查詢題詞、合併成一則訊
    息(空行分隔)；哪個先拆開發送比較好用，等實際跑起來再依使用者回饋調整。"""
    prompts = []

    for g in top_groups_with_trend:
        names = "、".join(s["name"] for s in g["representative_stocks"])
        prompts.append(f"{g['name']}族群（{names}） 國際金流/供需/缺貨/漲價新聞")

    for s in flagged_stocks:
        prompts.append(f"{s['name']}({s['code']}) 今日盤中成交值大增原因")

    return "\n\n".join(prompts)


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
