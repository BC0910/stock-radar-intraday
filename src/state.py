"""讀寫 data/state/*.json：
- history.json：每個交易日的前30名代號集合(用當天最近一次執行結果覆寫，所以到收盤後就是13:00那次的
  結果)，只保留最近 HISTORY_MAX_DAYS 天，供未來擴充用(目前 compare.py 主要靠 entrants.json 判斷連續
  天數，history.json 保留當備查/除錯用)。
- entrants.json：追蹤「曾被標記為新上榜」的股票，各自目前連續留榜天數(用來判斷是否要觸發「連續第3
  天」提醒)。只要某天不在前30名內就會被移除追蹤。
- last_pushed.json：上一次「實際推播過」的前30名代號集合，用來判斷這次組合是否完全沒變(去重複)。
- announced_today.json：今天已經播報過的新上榜代號(避免11:00播過、13:00沒有新東西時又重播一次)，
  日期跟今天不同就視為空清單重新開始。
"""
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
STATE_DIR = BASE_DIR / "data" / "state"

HISTORY_PATH = STATE_DIR / "history.json"
ENTRANTS_PATH = STATE_DIR / "entrants.json"
LAST_PUSHED_PATH = STATE_DIR / "last_pushed.json"
ANNOUNCED_TODAY_PATH = STATE_DIR / "announced_today.json"

HISTORY_MAX_DAYS = 15


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


def load_history() -> dict:
    return _load_json(HISTORY_PATH, {"trading_days": []})


def upsert_today_history(history: dict, today_iso: str, top30_codes: list) -> dict:
    days = [d for d in history["trading_days"] if d["date"] != today_iso]
    days.append({"date": today_iso, "top30_codes": top30_codes})
    days.sort(key=lambda d: d["date"])
    history["trading_days"] = days[-HISTORY_MAX_DAYS:]
    return history


def save_history(history: dict):
    _save_json(HISTORY_PATH, history)


def load_entrants() -> dict:
    return _load_json(ENTRANTS_PATH, {})


def save_entrants(entrants: dict):
    _save_json(ENTRANTS_PATH, entrants)


def load_last_pushed() -> dict:
    return _load_json(LAST_PUSHED_PATH, {"date": None, "codes": []})


def save_last_pushed(today_iso: str, codes: list):
    _save_json(LAST_PUSHED_PATH, {"date": today_iso, "codes": sorted(codes)})


def load_announced_today(today_iso: str) -> set:
    data = _load_json(ANNOUNCED_TODAY_PATH, {"date": None, "codes": []})
    if data.get("date") != today_iso:
        return set()
    return set(data.get("codes", []))


def save_announced_today(today_iso: str, codes: set):
    _save_json(ANNOUNCED_TODAY_PATH, {"date": today_iso, "codes": sorted(codes)})
