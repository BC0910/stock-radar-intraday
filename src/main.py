"""盤中即時成交值排行 主流程。

命令列執行:
    python src/main.py              # 正式執行：抓資料 -> 比對 -> (視情況)推播 Telegram -> 寫檔
    python src/main.py --dry-run    # 本機測試：一樣抓真實資料、一樣寫檔，但不會真的呼叫 Telegram API

排程設計:
    GitHub Actions 一天跑兩次(11:00, 13:00 台灣時間)，執行這支程式；跑完後由 workflow 把有異動的
    data/、docs/ commit 回 repo(GitHub Actions runner 本身用完即丟，狀態要靠寫回 repo 才留得住)。
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
import state
import compare
import telegram_notify
import pages_build

TAIWAN_TZ = timezone(timedelta(hours=8))
MIN_SUCCESS_RATE = 0.9
DEFAULT_PAGES_URL = "https://YOUR_GITHUB_USERNAME.github.io/stock-radar-intraday/"


def _stock_lookup(top30_records: list) -> dict:
    return {r["code"]: r for r in top30_records}


def _enrich_for_message(codes: set, stock_by_code: dict, code_to_group: dict, entrants_state: dict) -> list:
    result = []
    for code in codes:
        rec = stock_by_code.get(code)
        if rec is None:
            continue
        streak = entrants_state.get(code)
        result.append({
            "code": code,
            "name": rec["name"],
            "group": groups_module.get_group_name(code_to_group, code),
            "consecutive_days": streak["consecutive_days"] if streak else 1,
        })
    result.sort(key=lambda s: s["code"])
    return result


def run(dry_run: bool = False, pages_url: str = None) -> dict:
    pages_url = pages_url or DEFAULT_PAGES_URL
    now = datetime.now(TAIWAN_TZ)
    today_iso = now.date().isoformat()
    session_label = now.strftime("%H:%M")

    print(f"[1/7] 載入族群設定檔...")
    groups_data = groups_module.load_groups()
    code_to_group = groups_module.build_code_to_group(groups_data)
    print(f"      {len(groups_data)} 個族群、{len(code_to_group)} 檔成分股")

    print(f"[2/7] 取得前一交易日收盤成交值(比對基準 + 完整代號清單)...")
    close_snapshot = close_data.get_close_snapshot(today_iso)
    universe = close_data.universe_codes(close_snapshot)
    prev_close_top30 = close_data.top_n_by_value(close_snapshot, ranking.TOP_N)
    prev_close_top30_codes = {r["code"] for r in prev_close_top30}
    print(f"      全市場 {len(universe)} 檔(TWSE+TPEx) | 前一交易日收盤前{ranking.TOP_N}名已取得")

    print(f"[3/7] 批次查詢盤中即時報價...")
    quote_result = quotes.fetch_all_quotes(universe, today_iso=today_iso)
    if not quote_result["trading_day_ok"]:
        print("      今天非交易日或尚未開盤，結束執行(不寫入 state、不推播)。")
        return {"skipped": "not_trading_day"}

    success_rate = quote_result["responded"] / quote_result["requested"] if quote_result["requested"] else 0
    print(f"      回應 {quote_result['responded']}/{quote_result['requested']} 檔 (成功率 {success_rate:.1%})")
    if success_rate < MIN_SUCCESS_RATE:
        print(f"      [錯誤] 成功率低於門檻 {MIN_SUCCESS_RATE:.0%}，判定本次執行失敗，不寫入/不推播。")
        raise RuntimeError(f"即時報價查詢成功率過低: {success_rate:.1%}")

    print(f"[4/7] 計算前{ranking.TOP_N}名排行...")
    today_top30 = ranking.top_n_by_value(quote_result["records"], ranking.TOP_N)
    today_top30_codes = {r["code"] for r in today_top30}
    stock_by_code = _stock_lookup(today_top30)
    print(f"      前{ranking.TOP_N}名計算完成")

    print(f"[5/7] 讀取狀態、比對新上榜/連續留榜天數...")
    history = state.load_history()
    entrants_state = state.load_entrants()
    last_pushed = state.load_last_pushed()
    announced_today = state.load_announced_today(today_iso)

    decision = compare.build_push_decision(
        today_top30_codes=today_top30_codes,
        prev_close_top30_codes=prev_close_top30_codes,
        last_pushed_codes=set(last_pushed.get("codes", [])),
        announced_today_codes=announced_today,
        entrants_state=entrants_state,
        today_iso=today_iso,
    )
    print(f"      新上榜候選 {len(decision['new_entrant_candidates'])} 檔 | "
          f"這次要播的新上榜 {len(decision['new_entrants_to_announce'])} 檔 | "
          f"連續第3天 {len(decision['day3_alerts'])} 檔 | "
          f"去重複跳過={decision['dedup_skipped']}")

    history = state.upsert_today_history(history, today_iso, sorted(today_top30_codes))
    state.save_history(history)
    state.save_entrants(entrants_state)

    print(f"[6/7] 寫出 GitHub Pages 資料(docs/data/latest.json)...")
    ranking_payload = pages_build.build_ranking_payload(
        today_top30, code_to_group, entrants_state, decision["new_entrant_candidates"])
    pages_build.write_pages_data(
        generated_at_iso=now.isoformat(),
        date_iso=today_iso,
        session_label=session_label,
        trading_day=True,
        ranking=ranking_payload,
    )
    print(f"      已寫出")

    print(f"[7/7] 判斷是否推播 Telegram...")
    if decision["push_needed"]:
        new_entrants_msg = _enrich_for_message(
            decision["new_entrants_to_announce"], stock_by_code, code_to_group, entrants_state)
        day3_msg = _enrich_for_message(
            decision["day3_alerts"], stock_by_code, code_to_group, entrants_state)
        message = telegram_notify.build_message(session_label, new_entrants_msg, day3_msg, pages_url)

        print(f"      {'[dry-run] 不會真的呼叫 Telegram API，' if dry_run else ''}訊息內容：")
        print("      ----------------------------------------")
        print(message)
        print("      ----------------------------------------")
        if not dry_run:
            telegram_notify.send_message(message)
            print("      已推播 Telegram")

        state.save_last_pushed(today_iso, today_top30_codes)
        state.save_announced_today(today_iso, announced_today | decision["new_entrants_to_announce"])
    else:
        print("      這次沒有新上榜或連續第3天要播的內容，不推播。")

    return {
        "date": today_iso,
        "session_label": session_label,
        "push_needed": decision["push_needed"],
        "top30_codes": sorted(today_top30_codes),
    }


def main():
    parser = argparse.ArgumentParser(description="盤中即時成交值排行")
    parser.add_argument("--dry-run", action="store_true", help="不真的呼叫 Telegram API，只印出預計訊息")
    parser.add_argument("--pages-url", default=None, help="推播訊息裡附的 GitHub Pages 連結")
    args = parser.parse_args()

    try:
        run(dry_run=args.dry_run, pages_url=args.pages_url)
    except Exception as exc:
        print(f"[錯誤] 執行失敗: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
