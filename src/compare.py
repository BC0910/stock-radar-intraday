"""新上榜偵測 + 連續留榜第3天提醒 + 去重複推播判斷。

演算法(對應規格書的比對邏輯，細節已跟使用者對過)：
1. new_entrant_candidates = 今天前30名中，不在「前一交易日收盤前30名」內的代號。
2. 去重複規則：若今天前30名代號集合(不看順序) == 上一次實際推播過的集合，就不會有新上榜可以播
   (new_entrants_to_announce 會是空的)——但這只影響「新上榜」這類內容，不影響下面的連續第3天提醒。
3. new_entrants_to_announce = new_entrant_candidates 扣掉「今天稍早已經播過的」，因此同一個交易日內
   11:00 播過的新上榜，13:00 不會重複播，除非中間又有新的擠進來。
4. entrants_state 追蹤「曾被標記過新上榜」的股票的連續留榜天數：這次還在前30名內就 +1(同一天內執行
   兩次只算一次)，不在前30名內就整個移除追蹤(規格書寫明：本來就長期在榜的股票不會被追蹤)。天數滿3
   且還沒提醒過時，觸發一次「連續第3天」提醒，這個提醒不受第2點的去重複規則限制(即使組合跟上次推播
   時完全相同，只要天數剛好在這次滿3天，一樣要提醒)。
5. push_needed = new_entrants_to_announce 或 day3_alerts 任一非空；只要有推播，就更新 last_pushed 為
   今天完整前30名代號集合，並把 new_entrants_to_announce 併入 announced_today。
"""


def compute_new_entrant_candidates(today_top30_codes: set, prev_close_top30_codes: set) -> set:
    return today_top30_codes - prev_close_top30_codes


def update_entrants_streak(entrants_state: dict, today_iso: str, today_top30_codes: set,
                            new_entrant_candidates: set) -> list:
    """就地更新 entrants_state，回傳這次新達成「連續第3天」的代號清單。"""
    for code in today_top30_codes:
        if code in entrants_state:
            st = entrants_state[code]
            if st["last_seen_date"] != today_iso:
                st["consecutive_days"] += 1
                st["last_seen_date"] = today_iso
        elif code in new_entrant_candidates:
            entrants_state[code] = {
                "first_seen_date": today_iso,
                "consecutive_days": 1,
                "last_seen_date": today_iso,
                "day3_alerted": False,
            }

    for code in list(entrants_state.keys()):
        if code not in today_top30_codes:
            del entrants_state[code]

    day3_alerts = []
    for code, st in entrants_state.items():
        if st["consecutive_days"] >= 3 and not st["day3_alerted"]:
            day3_alerts.append(code)
            st["day3_alerted"] = True

    return day3_alerts


def build_push_decision(today_top30_codes: set, prev_close_top30_codes: set,
                         last_pushed_codes: set, announced_today_codes: set,
                         entrants_state: dict, today_iso: str) -> dict:
    """整合上面幾個步驟，回傳這次執行要不要推播、播什麼。"""
    new_entrant_candidates = compute_new_entrant_candidates(today_top30_codes, prev_close_top30_codes)

    is_same_as_last_pushed = today_top30_codes == last_pushed_codes
    if is_same_as_last_pushed:
        new_entrants_to_announce = set()
    else:
        new_entrants_to_announce = new_entrant_candidates - announced_today_codes

    day3_alerts = update_entrants_streak(entrants_state, today_iso, today_top30_codes, new_entrant_candidates)

    push_needed = bool(new_entrants_to_announce) or bool(day3_alerts)

    return {
        "new_entrant_candidates": new_entrant_candidates,
        "new_entrants_to_announce": new_entrants_to_announce,
        "day3_alerts": set(day3_alerts),
        "push_needed": push_needed,
        "dedup_skipped": is_same_as_last_pushed,
    }
