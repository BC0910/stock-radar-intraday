"""前50名依 groups.json 分組(先排除防禦板塊)，取前7大族群 + 漲跌多數決 + 跟前一交易日比較的排名趨勢。

沒歸類到 groups.json 任何族群的股票，併入既有的「其他」族群(groups.json 裡本來就有這個分類)。防禦板塊
(金融/塑化/生技等，見 config/defensive_sector.json)由呼叫端(main.py)先從輸入名單濾掉，這裡不處理。
"""
from collections import defaultdict

TOP_GROUPS_COUNT = 7
REPRESENTATIVE_STOCKS_COUNT = 3
UNCLASSIFIED_GROUP = "其他"


def _direction(change):
    if change is None or change == 0:
        return "flat"
    return "up" if change > 0 else "down"


def summarize_groups(top50: list, code_to_group: dict) -> list:
    """top50: 依成交值排序好的前50名(每筆含 code/name/value/change，防禦板塊已由呼叫端濾掉)。回傳每
    個至少有1檔進前50的族群彙總，依「族群內成分股成交值加總」由多到少排序(用總金額而不是檔數，避免
    檔數多但個股偏中小型的族群，排名壓過檔數少但由權值股撐場的族群)：
    { name, count, total_value, direction("up"/"down"/"flat"，該族群前50成分股漲跌家數多數決，平手
      記flat), representative_stocks(前 REPRESENTATIVE_STOCKS_COUNT 檔，已經是排名最高的，因為輸入
      名單本身就是排序好的) }
    """
    by_group = defaultdict(list)
    for stock in top50:
        group_name = code_to_group.get(stock["code"], UNCLASSIFIED_GROUP)
        by_group[group_name].append(stock)

    summaries = []
    for group_name, stocks in by_group.items():
        up = sum(1 for s in stocks if _direction(s.get("change")) == "up")
        down = sum(1 for s in stocks if _direction(s.get("change")) == "down")
        direction = "up" if up > down else "down" if down > up else "flat"
        summaries.append({
            "name": group_name,
            "count": len(stocks),
            "total_value": sum(s["value"] for s in stocks),
            "direction": direction,
            "representative_stocks": stocks[:REPRESENTATIVE_STOCKS_COUNT],
        })

    summaries.sort(key=lambda g: g["total_value"], reverse=True)
    return summaries


def build_full_ranking_for_history(summaries: list) -> list:
    """存進 data/state/group_history.json 用：完整族群排名(不限前7)，只存名稱+名次。"""
    return [{"name": g["name"], "rank": i} for i, g in enumerate(summaries, start=1)]


def attach_trend(summaries: list, yesterday_ranking: list, n: int = TOP_GROUPS_COUNT) -> tuple:
    """summaries: summarize_groups() 的結果(已依 count 排序)。yesterday_ranking:
    build_full_ranking_for_history() 存起來、隔天讀回來的內容(可能是 None/空 list，代表沒有歷史)。

    回傳 (top_n_with_trend, declined_group_names)：
    - top_n_with_trend: 前 n 大族群，每筆加 rank(1起) 跟 trend —
      trend = "new"(昨天前n沒有) 或整數(正值=名次進步幾名，0=持平，負值=退步幾名)
    - declined_group_names: 昨天前n有、今天前n沒有的族群名稱(依名稱排序)
    """
    yesterday_rank_map = {g["name"]: g["rank"] for g in (yesterday_ranking or [])}
    yesterday_top_names = {name for name, rank in yesterday_rank_map.items() if rank <= n}

    top_n = summaries[:n]
    today_names = {g["name"] for g in top_n}

    enriched = []
    for rank, g in enumerate(top_n, start=1):
        prev_rank = yesterday_rank_map.get(g["name"])
        trend = "new" if prev_rank is None else (prev_rank - rank)
        enriched.append({**g, "rank": rank, "trend": trend})

    declined_group_names = sorted(yesterday_top_names - today_names)
    return enriched, declined_group_names
