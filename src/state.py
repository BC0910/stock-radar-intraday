"""讀寫 data/state/*.json（v2 訊息格式用）：
- group_history.json：每個交易日的完整族群排名(不限前7大)，用當天最近一次執行結果覆寫，供
  group_analysis.attach_trend() 算「今天前7 vs 昨天前7」用。
- stock_rank_history.json：每檔股票最近幾個交易日的排名序列(見 stock_trends.py 說明)。
- last_pushed_msg1.json／last_pushed_msg2.json：訊息1(前7大族群)、訊息2(新上榜/持續上升/快速上升)
  各自上一次「實際推播過」的內容集合，用來判斷這次組合是否完全沒變(去重複，兩則訊息各自獨立判斷)。
"""
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
STATE_DIR = BASE_DIR / "data" / "state"

GROUP_HISTORY_PATH = STATE_DIR / "group_history.json"
STOCK_RANK_HISTORY_PATH = STATE_DIR / "stock_rank_history.json"
LAST_PUSHED_MSG1_PATH = STATE_DIR / "last_pushed_msg1.json"
LAST_PUSHED_MSG2_PATH = STATE_DIR / "last_pushed_msg2.json"

GROUP_HISTORY_MAX_DAYS = 10


def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def _save_json(path: Path, data):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_group_history() -> dict:
    return _load_json(GROUP_HISTORY_PATH, {"trading_days": []})


def get_yesterday_group_ranking(group_history: dict, today_iso: str):
    """回傳最近一筆日期早於今天的族群排名(list of {name, rank})，找不到就回傳 None。"""
    days = [d for d in group_history.get("trading_days", []) if d["date"] < today_iso]
    if not days:
        return None
    return max(days, key=lambda d: d["date"])["ranking"]


def upsert_today_group_history(group_history: dict, today_iso: str, ranking: list) -> dict:
    days = [d for d in group_history.get("trading_days", []) if d["date"] != today_iso]
    days.append({"date": today_iso, "ranking": ranking})
    days.sort(key=lambda d: d["date"])
    group_history["trading_days"] = days[-GROUP_HISTORY_MAX_DAYS:]
    return group_history


def save_group_history(group_history: dict):
    _save_json(GROUP_HISTORY_PATH, group_history)


def load_stock_rank_history() -> dict:
    return _load_json(STOCK_RANK_HISTORY_PATH, {})


def save_stock_rank_history(stock_rank_history: dict):
    _save_json(STOCK_RANK_HISTORY_PATH, stock_rank_history)


def load_last_pushed_msg1() -> set:
    data = _load_json(LAST_PUSHED_MSG1_PATH, {"group_names": []})
    return set(data.get("group_names", []))


def save_last_pushed_msg1(group_names: set):
    _save_json(LAST_PUSHED_MSG1_PATH, {"group_names": sorted(group_names)})


def load_last_pushed_msg2() -> set:
    data = _load_json(LAST_PUSHED_MSG2_PATH, {"codes": []})
    return set(data.get("codes", []))


def save_last_pushed_msg2(codes: set):
    _save_json(LAST_PUSHED_MSG2_PATH, {"codes": sorted(codes)})
