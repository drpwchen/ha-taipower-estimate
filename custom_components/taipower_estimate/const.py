"""常數與設定鍵。"""
from __future__ import annotations

import json
from pathlib import Path

DOMAIN = "taipower_estimate"

CONF_SOURCE = "source"
CONF_PROFILE = "profile"
CONF_MONTHS = "months"
CONF_DAY = "reading_day"
CONF_PARITY = "reading_parity"
CONF_INITIAL_USED = "initial_used"

PROFILES = ["residential", "non_commercial", "commercial"]
PARITIES = ["odd", "even"]

DEFAULT_PROFILE = "residential"
DEFAULT_MONTHS = 2
DEFAULT_DAY = 13
DEFAULT_PARITY = "odd"

MIN_DAYS = 3                 # 分母不到這麼多天：預估、電價、電費都 unavailable
TICK_MINUTES = 5             # 沒有新讀數時，多久更新一次天數／進度
STORAGE_VERSION = 1
SAVE_DELAY = 30              # 秒；讀數更新後延遲寫檔，避免每秒寫一次

RATES_FILE = Path(__file__).parent / "rates.json"


def load_rates() -> dict:
    """讀 integration 內附的 rates.json（由 tools/gen_package.py 從 tariff/rates.json 複製；不要手改）。"""
    return json.loads(RATES_FILE.read_text(encoding="utf-8"))


def signal_update(entry_id: str) -> str:
    return f"{DOMAIN}_update_{entry_id}"
