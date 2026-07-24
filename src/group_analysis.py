"""前100名依 groups.json 分組，取前7大族群 + 漲跌多數決 + 跟前一交易日比較的排名趨勢。

沒歸類到 groups.json 任何族群的股票，併入既有的「其他」族群(groups.json 裡本來就有這個分類)。
"""
from collections import defaultdict

TOP_GROUPS_COUNT = 7
REPRESENTATIVE_STOCKS_COUNT = 3
UNCLASSIFIED_GROUP = "其他"


def _direction(change):
    if change is None or change == 0:
        return "flat"
    return "up" if change > 0 else "down"


def summarize_groups(top100: list, code_to_group: dict) -> list:
    """top100: 依成交值排序好的前100名(每筆含 code/name/change)。回傳每個至少有1檔進前100的族群彙
    總，依「擠進前100的檔數」由多到少排序：
    { name, count, direction("up"/"down"/"flat"，該族群前100成分股漲跌家數多數決，平手記flat),
      representative_stocks(前 REPRESENTATIVE_STOCKS_COUNT 檔) }
    """
    by_group = defaultdict(list)
    for stock in top100:
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
            "direction": direction,
            "representative_stocks": stocks[:REPRESENTATIVE_STOCKS_COUNT],
        })

    summaries.sort(key=lambda g: g["count"], reverse=True)
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
