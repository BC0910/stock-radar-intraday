"""盤中即時報價：mis.twse.com.tw/stock/api/getStockInfo.jsp 批次查詢。

這支 API 沒有官方文件保證格式，已知特性(使用者研究+規格書提供)：
- 上市代號前綴 tse_，上櫃代號前綴 otc_，例如 tse_2330.tw、otc_xxxx.tw
- 可用 | 一次查多檔
- 更新頻率約5秒，隱性限流約每5秒3次請求
- 回傳欄位 c(代號) n(簡稱) z(現價，尚未成交當天時是'-') v(累積成交量) y(昨收) d(資料日期 yyyyMMdd)

用 v(累積成交量) × z(現價) 估算成交值(依規格書指定的近似公式，非官方成交值)。z 是 '-' 時(今天還沒
成交過)退回用昨收 y 估算，v 是 0 或缺值就直接跳過(視為今天還沒有成交量可排名)。
"""
import time
from datetime import datetime, timedelta, timezone

import requests

MIS_URL = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp"
_HEADERS = {"User-Agent": "Mozilla/5.0 (stock-radar-intraday/1.0)"}
TAIWAN_TZ = timezone(timedelta(hours=8))

BATCH_SIZE = 25
REQUEST_INTERVAL_SECONDS = 1.8
MAX_RETRIES = 2
RETRY_BACKOFF_SECONDS = 3.0


def _to_symbol(code: str, market: str) -> str:
    prefix = "tse" if market == "TWSE" else "otc"
    return f"{prefix}_{code}.tw"


def _to_number(value):
    if value is None:
        return None
    cleaned = str(value).replace(",", "").strip()
    if cleaned in ("", "-", "--"):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _chunk(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def _fetch_batch(symbols):
    ex_ch = "|".join(symbols)
    resp = requests.get(MIS_URL, params={"ex_ch": ex_ch, "json": "1", "delay": "0"},
                         headers=_HEADERS, timeout=15)
    resp.raise_for_status()
    payload = resp.json()
    return payload.get("msgArray", [])


def _fetch_batch_with_retry(symbols):
    last_exc = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            return _fetch_batch(symbols)
        except Exception as exc:
            last_exc = exc
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF_SECONDS)
    print(f"[警告] 批次查詢失敗(重試{MAX_RETRIES}次仍失敗): {last_exc}，這批 {len(symbols)} 檔跳過")
    return []


def _parse_item(item, code, name, market):
    prev_close = _to_number(item.get("y"))
    price = _to_number(item.get("z"))
    change = (price - prev_close) if (price is not None and prev_close is not None) else None
    if price is None:
        price = prev_close
    volume = _to_number(item.get("v"))
    if price is None or volume is None or volume <= 0:
        return None
    return {
        "code": code,
        "name": item.get("n") or name,
        "market": market,
        "price": price,
        "volume": volume,
        "value": price * volume,
        "change": change,
    }


def fetch_all_quotes(universe: list, today_iso: str = None) -> dict:
    """universe: [(code, name, market), ...]。回傳 dict:
    { records: [...], trading_day_ok: bool, requested: int, responded: int }

    trading_day_ok 用第一批有回應的資料的 'd' 欄位(yyyyMMdd)跟今天日期比對；若不是今天，代表現在不是
    交易時段(週末/假日/尚未開盤)，此時會直接停止後續批次查詢，避免打一堆無意義的請求。

    responded 只計「API 有回應這檔代號的資料」的數量(用來判斷批次查詢本身有沒有大量失敗)，不等於
    records 的數量——今天還沒成交過(無量)的股票會被排除在 records 之外，那是正常現象、不算查詢失敗。
    """
    today_iso = today_iso or datetime.now(TAIWAN_TZ).date().isoformat()
    today_yyyymmdd = today_iso.replace("-", "")

    batches = list(_chunk(universe, BATCH_SIZE))

    records = []
    requested = len(universe)
    responded = 0
    trading_day_ok = None

    for i, batch in enumerate(batches):
        symbols = [_to_symbol(code, market) for code, name, market in batch]
        items = _fetch_batch_with_retry(symbols)

        if trading_day_ok is None and items:
            sample_date = next((it.get("d") for it in items if it.get("d")), None)
            trading_day_ok = (sample_date == today_yyyymmdd)
            if not trading_day_ok:
                print(f"[非交易日] 即時報價日期({sample_date})不是今天({today_yyyymmdd})，"
                      f"視為尚未開盤/非交易日，停止後續批次查詢")
                break

        by_code = {}
        for it in items:
            c = (it.get("c") or "").strip()
            if c:
                by_code[c] = it

        for code, name, market in batch:
            item = by_code.get(code)
            if item is None:
                continue
            responded += 1
            parsed = _parse_item(item, code, name, market)
            if parsed is not None:
                records.append(parsed)

        if i < len(batches) - 1:
            time.sleep(REQUEST_INTERVAL_SECONDS)

    return {
        "records": records,
        "trading_day_ok": trading_day_ok if trading_day_ok is not None else False,
        "requested": requested,
        "responded": responded,
    }
