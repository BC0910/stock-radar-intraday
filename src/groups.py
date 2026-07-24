"""讀 config/groups.json(從 stock-radar 手動複製過來的參考版本)，提供 code -> 族群名稱 查詢；
另外讀 config/defensive_sector.json(同樣手動複製自 stock-radar)，提供族群排名要排除的防禦板塊清單。
"""
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_GROUPS_PATH = BASE_DIR / "config" / "groups.json"
DEFAULT_DEFENSIVE_SECTOR_PATH = BASE_DIR / "config" / "defensive_sector.json"
UNCLASSIFIED_LABEL = "未分類"


def load_groups(path=None) -> list:
    path = Path(path) if path else DEFAULT_GROUPS_PATH
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_defensive_codes(path=None) -> set:
    path = Path(path) if path else DEFAULT_DEFENSIVE_SECTOR_PATH
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {s["code"] for s in data["defensive_sector"]}


def build_code_to_group(groups: list) -> dict:
    code_to_group = {}
    for group in groups:
        for stock in group["stocks"]:
            code_to_group[stock["code"]] = group["name"]
    return code_to_group


def get_group_name(code_to_group: dict, code: str) -> str:
    return code_to_group.get(code, UNCLASSIFIED_LABEL)
