"""產生 docs/data/latest.json，給 docs/index.html(GitHub Pages)讀取渲染完整前30名排行。"""
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DOCS_DATA_PATH = BASE_DIR / "docs" / "data" / "latest.json"


def build_ranking_payload(top30: list, code_to_group: dict, entrants_state: dict,
                           new_entrant_candidates: set) -> list:
    from groups import get_group_name

    payload = []
    for i, stock in enumerate(top30, start=1):
        code = stock["code"]
        streak = entrants_state.get(code)
        payload.append({
            "rank": i,
            "code": code,
            "name": stock["name"],
            "market": stock["market"],
            "value": stock["value"],
            "group": get_group_name(code_to_group, code),
            "consecutive_days": streak["consecutive_days"] if streak else None,
            "is_new_entrant": code in new_entrant_candidates,
            "is_day3_alert": bool(streak and streak["consecutive_days"] == 3 and streak.get("day3_alerted")),
        })
    return payload


def write_pages_data(generated_at_iso: str, date_iso: str, session_label: str, trading_day: bool,
                      ranking: list):
    DOCS_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "generated_at": generated_at_iso,
        "date": date_iso,
        "session_label": session_label,
        "trading_day": trading_day,
        "ranking": ranking,
    }
    DOCS_DATA_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data
