"""前50名個股趨勢：新上榜／持續上升／快速上升，比對 data/state/stock_rank_history.json 裡的歷史排名。

stock_rank_history.json 格式：{ code: [{"date": "2026-07-20", "rank": 12}, ...] }，依日期由舊到新排
列，只保留「連續留在前50名」的股票——只要某天不在前50名內就整個移除追蹤，隔天重新出現會被當成新上
榜(這點跟 v1 entrants.json 的設計精神一致)。
"""

PERSISTENT_RISE_MIN_STREAK = 2
FAST_RISE_RANK_THRESHOLD = 30
HISTORY_MAX_DAYS_PER_CODE = 15


def compute_trends(today_top50: list, stock_rank_history: dict) -> dict:
    """today_top50: 依成交值排序好的前50名(每筆至少含 code/name)。stock_rank_history: 呼叫端先用
    state.load_stock_rank_history() 讀進來、還沒寫入今天資料的版本。

    回傳 { new_entrants, persistent_rise, fast_rise }，每筆都是原始 stock dict 再加上 rank(1起)：
    - persistent_rise 另外附 streak_days(連續幾天排名比前一天進步，含今天)
    - fast_rise 另外附 prev_rank(前一交易日排名)
    """
    new_entrants, persistent_rise, fast_rise = [], [], []

    for rank, stock in enumerate(today_top50, start=1):
        code = stock["code"]
        history = stock_rank_history.get(code, [])

        if not history:
            new_entrants.append({**stock, "rank": rank})
            continue

        prev_rank = history[-1]["rank"]

        if rank < prev_rank:
            ranks_chronological = [e["rank"] for e in history] + [rank]
            streak = 1
            for i in range(len(ranks_chronological) - 1, 0, -1):
                if ranks_chronological[i] < ranks_chronological[i - 1]:
                    streak += 1
                else:
                    break
            if streak >= PERSISTENT_RISE_MIN_STREAK:
                persistent_rise.append({**stock, "rank": rank, "streak_days": streak})

        if prev_rank > FAST_RISE_RANK_THRESHOLD and rank <= FAST_RISE_RANK_THRESHOLD:
            fast_rise.append({**stock, "rank": rank, "prev_rank": prev_rank})

    return {
        "new_entrants": new_entrants,
        "persistent_rise": persistent_rise,
        "fast_rise": fast_rise,
    }


def update_history(stock_rank_history: dict, today_iso: str, today_top50: list) -> dict:
    """就地更新 stock_rank_history：今天前50名的每檔股票 append 今天的排名(同一天重跑會覆寫掉今天那
    筆，不重複累加)，不在前50名內的股票整個移除追蹤。回傳更新後的 dict。"""
    today_codes = {stock["code"] for stock in today_top50}
    rank_by_code = {stock["code"]: rank for rank, stock in enumerate(today_top50, start=1)}

    for code in list(stock_rank_history.keys()):
        if code not in today_codes:
            del stock_rank_history[code]

    for code in today_codes:
        entries = [e for e in stock_rank_history.get(code, []) if e["date"] != today_iso]
        entries.append({"date": today_iso, "rank": rank_by_code[code]})
        stock_rank_history[code] = entries[-HISTORY_MAX_DAYS_PER_CODE:]

    return stock_rank_history
