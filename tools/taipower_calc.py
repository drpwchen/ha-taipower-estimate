"""費率計算參考實作（給測試與產生器用，也是 YAML 模板的「對照答案」）。

計算本體在 `custom_components/taipower_estimate/calc.py`（integration 與 package 共用同一份邏輯）；
這裡以檔案路徑載入它（不經過 integration 的 `__init__.py`，所以不需要安裝 Home Assistant），
並保留原本「預設讀 tariff/rates.json」的介面。
"""
from __future__ import annotations

import importlib.util
import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RATES_PATH = ROOT / "tariff" / "rates.json"
_CALC_PATH = ROOT / "custom_components" / "taipower_estimate" / "calc.py"

_spec = importlib.util.spec_from_file_location("_taipower_core_calc", _CALC_PATH)
core = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(core)

BIG = core.BIG


def load_rates(path: Path = RATES_PATH) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def bands(profile: str = "residential", months: int = 2, rates: dict | None = None):
    """回傳 [(upper_kwh, summer_rate, non_summer_rate), ...]，最後一段 upper 為 BIG。"""
    return core.bands(rates or load_rates(), profile, months)


def summer_ratio(reset: date, cycle_days: int, summer_months=(6, 7, 8, 9)) -> float:
    return core.summer_ratio(reset, cycle_days, summer_months)


def tier_price(kwh: float, ratio: float, profile: str = "residential", months: int = 2,
               rates: dict | None = None) -> float:
    return core.tier_price(kwh, ratio, bands(profile, months, rates))


def bill(kwh: float, ratio: float, profile: str = "residential", months: int = 2,
         rates: dict | None = None) -> int:
    return core.bill(kwh, ratio, bands(profile, months, rates))
