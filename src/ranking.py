"""把 quotes.fetch_all_quotes() 的 records 依估算成交值(value)排序，取前 N 名。"""

TOP_N = 30


def top_n_by_value(records: list, n: int = TOP_N) -> list:
    return sorted(records, key=lambda r: r["value"], reverse=True)[:n]
