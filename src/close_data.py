"""前一交易日官方收盤成交值（TWSE+TPEx）：當作「新上榜」比對基準，同時也提供完整上市+上櫃代號清單
（不用再另外去 ISIN 頁面爬蟲）。

在盤中（11:00/13:00）呼叫這幾支「不帶日期參數」的官方介面時，因為當天的正式收盤資料要到收盤後才會
公告，回傳的自然就是「前一交易日」的收盤資料，剛好符合我們要的比對基準，不需要額外處理日期位移。

來源跟 stock-radar/src/fetch.py 相同（同一批公開資料，兩個專案各自獨立實作，不共用程式碼）：
- TWSE 主要來源: https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX (較即時)
- TWSE 備援來源: https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL (較穩定但可能延遲)
- TPEx: https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parent.parent
CACHE_DIR = BASE_DIR / "data" / "close_cache"
TAIWAN_TZ = timezone(timedelta(hours=8))

TWSE_AFTERTRADING_MI_INDEX = "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"
TWSE_STOCK_DAY_ALL = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
TPEX_MAINBOARD_QUOTES = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes"

_HEADERS = {"User-Agent": "Mozilla/5.0 (stock-radar-intraday/1.0)"}


def _roc_to_iso(roc_date: str) -> str:
    roc_date = roc_date.strip()
    year = int(roc_date[:-4]) + 1911
    month = roc_date[-4:-2]
    day = roc_date[-2:]
    return f"{year:04d}-{month}-{day}"


def _yyyymmdd_to_iso(ymd: str) -> str:
    ymd = ymd.strip()
    return f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:8]}"


def _to_number(value):
    if value is None:
        return None
    cleaned = str(value).replace(",", "").strip()
    if cleaned in ("", "--", "-"):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _signed_change(sign_html: str, magnitude: str):
    """www.twse.com.tw afterTrading 回傳的漲跌是「HTML 顏色標記(方向) + 絕對值」分開兩欄，這裡合成
    有號數字(跟 stock-radar/src/fetch.py 同一招，各自獨立實作)。"""
    value = _to_number(magnitude)
    if value is None:
        return None
    if "color:red" in (sign_html or ""):
        return value
    if "color:green" in (sign_html or ""):
        return -value
    return 0.0 if value == 0 else value


def _fetch_twse_aftertrading():
    resp = requests.get(TWSE_AFTERTRADING_MI_INDEX, params={"type": "ALLBUT0999", "response": "json"},
                         headers=_HEADERS, timeout=30)
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("stat") != "OK":
        raise RuntimeError(f"www.twse.com.tw afterTrading 回傳非成功狀態: {payload.get('stat')}")

    tables = payload.get("tables", [])
    stock_table = next((t for t in tables if t.get("title") and "每日收盤行情" in t["title"]), None)
    if stock_table is None or not stock_table.get("data"):
        raise RuntimeError("www.twse.com.tw afterTrading 回傳內容中找不到「每日收盤行情」個股資料表")

    date_iso = _yyyymmdd_to_iso(payload["date"])
    records = []
    for row in stock_table["data"]:
        code = row[0].strip()
        name = row[1].strip()
        trade_value = _to_number(row[4])
        if not code or trade_value is None:
            continue
        records.append({
            "code": code, "name": name, "market": "TWSE", "trade_value": trade_value,
            "close_price": _to_number(row[8]), "change": _signed_change(row[9], row[10]),
        })
    return date_iso, records


def _fetch_twse_stock_day_all():
    resp = requests.get(TWSE_STOCK_DAY_ALL, headers=_HEADERS, timeout=30)
    resp.raise_for_status()
    rows = resp.json()
    if not rows:
        raise RuntimeError("TWSE STOCK_DAY_ALL 回傳空資料")

    dates = {_roc_to_iso(r["Date"]) for r in rows if r.get("Date")}
    date_iso = max(dates) if dates else None
    records = []
    for r in rows:
        trade_value = _to_number(r.get("TradeValue"))
        code = (r.get("Code") or "").strip()
        if not code or trade_value is None:
            continue
        records.append({
            "code": code, "name": (r.get("Name") or "").strip(), "market": "TWSE",
            "trade_value": trade_value,
            "close_price": _to_number(r.get("ClosingPrice")), "change": _to_number(r.get("Change")),
        })
    return date_iso, records


def _fetch_twse_close():
    try:
        return _fetch_twse_aftertrading()
    except Exception as exc:
        print(f"[警告] TWSE 主要來源(www.twse.com.tw)取得失敗: {exc}，改用備援來源 openapi.twse.com.tw")
        return _fetch_twse_stock_day_all()


def _fetch_tpex_close():
    resp = requests.get(TPEX_MAINBOARD_QUOTES, headers=_HEADERS, timeout=30)
    resp.raise_for_status()
    rows = resp.json()
    if not rows:
        raise RuntimeError("TPEx tpex_mainboard_quotes 回傳空資料")

    dates = {_roc_to_iso(r["Date"]) for r in rows if r.get("Date")}
    date_iso = max(dates) if dates else None
    records = []
    for r in rows:
        trade_value = _to_number(r.get("TransactionAmount"))
        code = (r.get("SecuritiesCompanyCode") or "").strip()
        if not code or trade_value is None:
            continue
        records.append({
            "code": code, "name": (r.get("CompanyName") or "").strip(), "market": "TPEx",
            "trade_value": trade_value,
            "close_price": _to_number(r.get("Close")), "change": _to_number(r.get("Change")),
        })
    return date_iso, records


def _fetch_fresh() -> dict:
    twse_date, twse_records = _fetch_twse_close()
    tpex_date, tpex_records = _fetch_tpex_close()
    if tpex_date and twse_date and tpex_date != twse_date:
        print(f"[警告] TWSE({twse_date}) 與 TPEx({tpex_date}) 收盤資料日期不一致，各自保留原始資料")
    return {
        "twse_date": twse_date,
        "tpex_date": tpex_date,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "records": twse_records + tpex_records,
    }


def get_close_snapshot(run_date_iso: str, force_refresh: bool = False) -> dict:
    """回傳「前一交易日收盤」快照(records 含 code/name/market/trade_value)。用 run_date_iso(今天的日
    期，不是資料本身的日期)當快取檔名，同一天內(如11:00跟13:00兩次執行)只打一次官方API。"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / f"{run_date_iso}.json"
    if not force_refresh and cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))

    snapshot = _fetch_fresh()
    cache_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    return snapshot


def get_today_official_snapshot(today_iso: str, force_refresh: bool = False) -> dict:
    """給 postclose_stats 模式用：單純抓「目前官方公布的最新收盤資料」，不像 get_close_snapshot() 那樣
    預設語意是「前一交易日」。呼叫端要自己檢查回傳的 twse_date/tpex_date 是不是等於 today_iso，藉此判
    斷「今天的收盤資料公布了沒」——17:00 執行時通常已經公布，若 cron-job.org 誤觸發在收盤前，這裡就會
    抓到還是前一天的資料，呼叫端可以據此判斷資料還沒準備好、不寫入不推播。跟 get_close_snapshot() 用
    不同的快取檔名(postclose_ 前綴)，避免互相覆蓋。"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / f"postclose_{today_iso}.json"
    if not force_refresh and cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))

    snapshot = _fetch_fresh()
    cache_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    return snapshot


def top_n_by_value(snapshot: dict, n: int = 30) -> list:
    return sorted(snapshot["records"], key=lambda r: r["trade_value"], reverse=True)[:n]


def universe_codes(snapshot: dict) -> list:
    """回傳 [(code, name, market), ...] 完整清單，供盤中即時查詢用。"""
    return [(r["code"], r["name"], r["market"]) for r in snapshot["records"]]
