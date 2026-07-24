"""盤中即時成交值排行 主流程 v2（族群/個股趨勢訊息 + mode 分流）。

命令列執行:
    python src/main.py --mode intraday_check           # 盤中即時檢查(即時報價)
    python src/main.py --mode postclose_stats          # 收盤後統計(官方收盤值)
    python src/main.py --mode intraday_check --dry-run # 本機測試：一樣抓真實資料、一樣寫檔，但不會真的呼叫 Telegram API

觸發方式(GitHub Actions 內建 schedule: 已移除，實測對新建立的 workflow 不可靠)：
    intraday_check  ← 使用者傳 Telegram「跑一次」→ Cloudflare Worker → workflow_dispatch
    postclose_stats ← cron-job.org 每個交易日 17:00(台灣時間) → workflow_dispatch
    兩者都是同一支 workflow 的 workflow_dispatch，差別只在 mode 這個 input 參數。
"""
import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# 非互動環境(如 GitHub Actions/工作排程器)下，stdout/stderr 預設編碼常是系統 codepage(如 Windows 的
# cp950)，印到中文或emoji會直接 UnicodeEncodeError 讓程式中斷，這裡強制改成 UTF-8。
for _stream in (sys.stdout, sys.stderr):
    if _stream.encoding.lower() not in ("utf-8", "utf8"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent))

import close_data
import quotes
import ranking
import groups as groups_module
import group_analysis
import stock_trends
import state
import telegram_notify
import pages_build

TAIWAN_TZ = timezone(timedelta(hours=8))
MIN_SUCCESS_RATE = 0.9
DEFAULT_PAGES_URL = "https://YOUR_GITHUB_USERNAME.github.io/stock-radar-intraday/"

MODE_INTRADAY = "intraday_check"
MODE_POSTCLOSE = "postclose_stats"


def _normalize_close_records(snapshot: dict) -> list:
    """把 close_data 的欄位名稱對齊 quotes.py 的形狀(value/price)，讓 ranking/group_analysis/
    stock_trends 不用分 mode 處理。"""
    return [
        {
            "code": r["code"], "name": r["name"], "market": r["market"],
            "value": r["trade_value"], "price": r.get("close_price"), "change": r.get("change"),
        }
        for r in snapshot["records"]
    ]


def _attach_group(stocks: list, code_to_group: dict) -> list:
    return [{**s, "group": groups_module.get_group_name(code_to_group, s["code"])} for s in stocks]


def _dedupe_by_code(*stock_lists) -> list:
    seen = {}
    for stocks in stock_lists:
        for s in stocks:
            seen.setdefault(s["code"], s)
    return list(seen.values())


def _fetch_intraday_records(today_iso: str):
    """回傳前100/50/30名要用的完整 records，或 None(非交易日/尚未開盤，呼叫端會提早結束)。"""
    close_snapshot = close_data.get_close_snapshot(today_iso)
    universe = close_data.universe_codes(close_snapshot)
    print(f"      全市場 {len(universe)} 檔(TWSE+TPEx)")

    quote_result = quotes.fetch_all_quotes(universe, today_iso=today_iso)
    if not quote_result["trading_day_ok"]:
        print("      即時報價日期不是今天，視為非交易日/尚未開盤，結束執行(不寫入 state、不推播)。")
        return None

    success_rate = quote_result["responded"] / quote_result["requested"] if quote_result["requested"] else 0
    print(f"      回應 {quote_result['responded']}/{quote_result['requested']} 檔 (成功率 {success_rate:.1%})")
    if success_rate < MIN_SUCCESS_RATE:
        raise RuntimeError(f"即時報價查詢成功率過低: {success_rate:.1%}")

    return quote_result["records"]


def _fetch_postclose_records(today_iso: str):
    """回傳 records 或 None(官方收盤資料還沒公布，呼叫端會提早結束)。"""
    snapshot = close_data.get_today_official_snapshot(today_iso)
    if snapshot.get("twse_date") != today_iso and snapshot.get("tpex_date") != today_iso:
        print(f"      官方收盤資料還是 {snapshot.get('twse_date')}／{snapshot.get('tpex_date')}，"
              f"還沒有今天({today_iso})的收盤資料，結束執行(不寫入 state、不推播)。")
        return None
    return _normalize_close_records(snapshot)


def run(mode: str, dry_run: bool = False, pages_url: str = None) -> dict:
    pages_url = pages_url or DEFAULT_PAGES_URL
    now = datetime.now(TAIWAN_TZ)
    today_iso = now.date().isoformat()
    session_label = now.strftime("%H:%M")

    print(f"[1/6] 模式={mode} | 載入族群設定檔...")
    groups_data = groups_module.load_groups()
    code_to_group = groups_module.build_code_to_group(groups_data)
    print(f"      {len(groups_data)} 個族群、{len(code_to_group)} 檔成分股")

    print(f"[2/6] 抓取資料...")
    if mode == MODE_INTRADAY:
        records = _fetch_intraday_records(today_iso)
    elif mode == MODE_POSTCLOSE:
        records = _fetch_postclose_records(today_iso)
    else:
        raise ValueError(f"未知的 mode: {mode}")

    if records is None:
        return {"skipped": "data_not_ready"}

    print(f"[3/6] 計算前100/50/30名排行...")
    top100 = ranking.top_n_by_value(records, 100)
    top50 = ranking.top_n_by_value(records, 50)
    top30 = ranking.top_n_by_value(records, 30)
    print(f"      前100/50/30名計算完成(共 {len(records)} 檔有效資料)")

    print(f"[4/6] 族群彙總 + 個股趨勢分析...")
    group_summaries = group_analysis.summarize_groups(top100, code_to_group)
    group_history = state.load_group_history()
    yesterday_group_ranking = state.get_yesterday_group_ranking(group_history, today_iso)
    top_groups_with_trend, declined_groups = group_analysis.attach_trend(group_summaries, yesterday_group_ranking)
    group_history = state.upsert_today_group_history(
        group_history, today_iso, group_analysis.build_full_ranking_for_history(group_summaries))
    state.save_group_history(group_history)

    stock_rank_history = state.load_stock_rank_history()
    trends = stock_trends.compute_trends(top50, stock_rank_history)
    stock_rank_history = stock_trends.update_history(stock_rank_history, today_iso, top50)
    state.save_stock_rank_history(stock_rank_history)

    new_entrants = _attach_group(trends["new_entrants"], code_to_group)
    persistent_rise = _attach_group(trends["persistent_rise"], code_to_group)
    fast_rise = _attach_group(trends["fast_rise"], code_to_group)
    print(f"      前7大族群: {[g['name'] for g in top_groups_with_trend]} | 趨勢下降: {declined_groups}")
    print(f"      新上榜 {len(new_entrants)} | 持續上升 {len(persistent_rise)} | 快速上升 {len(fast_rise)}")

    print(f"[5/6] 寫出 GitHub Pages 資料(docs/data/latest.json)...")
    today_streaks = {s["code"]: {"consecutive_days": s["streak_days"]} for s in persistent_rise}
    new_entrant_codes = {s["code"] for s in new_entrants}
    ranking_payload = pages_build.build_ranking_payload(top30, code_to_group, today_streaks, new_entrant_codes)
    pages_build.write_pages_data(
        generated_at_iso=now.isoformat(), date_iso=today_iso, session_label=f"{session_label}（{mode}）",
        trading_day=True, ranking=ranking_payload,
    )
    print(f"      已寫出")

    print(f"[6/6] 判斷去重複、組訊息、視情況推播 Telegram...")
    today_group_names = {g["name"] for g in top_groups_with_trend}
    last_pushed_msg1 = state.load_last_pushed_msg1()
    send_msg1 = today_group_names != last_pushed_msg1

    flagged_stocks = _dedupe_by_code(new_entrants, persistent_rise, fast_rise)
    today_msg2_codes = {s["code"] for s in flagged_stocks}
    last_pushed_msg2 = state.load_last_pushed_msg2()
    send_msg2 = bool(today_msg2_codes) and today_msg2_codes != last_pushed_msg2

    messages = []
    if send_msg1:
        messages.append(telegram_notify.build_message1(top_groups_with_trend, declined_groups))
    if send_msg2:
        messages.append(telegram_notify.build_message2(new_entrants, persistent_rise, fast_rise))
    if send_msg1 or send_msg2:
        msg3 = telegram_notify.build_message3(top_groups_with_trend, flagged_stocks)
        if msg3:
            messages.append(msg3)

    for i, message in enumerate(messages, start=1):
        print(f"      {'[dry-run] ' if dry_run else ''}訊息{i}：")
        print("      ----------------------------------------")
        print(message)
        print("      ----------------------------------------")
        if not dry_run:
            telegram_notify.send_message(message)

    if messages and not dry_run:
        print(f"      已推播 {len(messages)} 則 Telegram 訊息")
    elif not messages:
        print("      這次沒有新內容要播(訊息1、2 組合都跟上次推播時相同)。")

    if send_msg1:
        state.save_last_pushed_msg1(today_group_names)
    if send_msg2:
        state.save_last_pushed_msg2(today_msg2_codes)

    return {
        "date": today_iso, "mode": mode, "session_label": session_label,
        "sent_messages": len(messages),
    }


def main():
    parser = argparse.ArgumentParser(description="盤中即時成交值排行 v2")
    parser.add_argument("--mode", choices=[MODE_INTRADAY, MODE_POSTCLOSE], default=MODE_INTRADAY,
                         help="intraday_check(即時報價) 或 postclose_stats(官方收盤值)")
    parser.add_argument("--dry-run", action="store_true", help="不真的呼叫 Telegram API，只印出預計訊息")
    parser.add_argument("--pages-url", default=None, help="推播訊息裡附的 GitHub Pages 連結")
    args = parser.parse_args()

    try:
        run(mode=args.mode, dry_run=args.dry_run, pages_url=args.pages_url)
    except Exception as exc:
        print(f"[錯誤] 執行失敗: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
