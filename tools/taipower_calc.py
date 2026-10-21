"""費率計算參考實作（給測試用，也是 YAML 模板的「對照答案」）。

邏輯跟 packages/taipower_estimate.yaml 裡的 Jinja 一一對應：
  - 級距上限 = 每月上限 × months（兩個月抄表 → 各段度數加倍）
  - 週期跨夏月／非夏月時，每度電價 = 夏月價 × r + 非夏月價 × (1 − r)，
    r = 週期內夏月天數 / 週期天數。這是近似，不是台電帳單的逐字算法（見 README「限制」）。
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

RATES_PATH = Path(__file__).resolve().parent.parent / "tariff" / "rates.json"
BIG = 999999  # YAML 裡「無上限」的哨兵值


def load_rates(path: Path = RATES_PATH) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def bands(profile: str = "residential", months: int = 2, rates: dict | None = None):
    """回傳 [(upper_kwh, summer_rate, non_summer_rate), ...]，最後一段 upper 為 BIG。"""
    rates = rates or load_rates()
    out = []
    for b in rates["profiles"][profile]["bands"]:
        upper = BIG if b["upto"] is None else b["upto"] * months
        out.append((upper, b["summer"], b["non_summer"]))
    return out


def summer_ratio(reset: date, cycle_days: int, summer_months=(6, 7, 8, 9)) -> float:
    """週期（從 reset 起算 cycle_days 天）內夏月天數占比，四捨五入到 4 位（同 YAML）。"""
    n = sum(1 for i in range(cycle_days) if (reset + timedelta(days=i)).month in summer_months)
    return round(n / cycle_days, 4)


def tier_price(kwh: float, ratio: float, profile: str = "residential", months: int = 2,
               rates: dict | None = None) -> float:
    """用電 kwh 所在級距的（夏月／非夏月加權）每度電價，四捨五入到 2 位。"""
    for upper, s, n in bands(profile, months, rates):
        if kwh <= upper:
            return round(s * ratio + n * (1 - ratio), 2)
    raise AssertionError("unreachable: last band is unbounded")


def bill(kwh: float, ratio: float, profile: str = "residential", months: int = 2,
         rates: dict | None = None) -> int:
    """逐級累進電費（元，四捨五入到整數）。不含底度／最低 100 元規則。"""
    total, left, prev = 0.0, kwh, 0
    for upper, s, n in bands(profile, months, rates):
        if left <= 0:
            break
        use = min(left, upper - prev)
        total += use * (s * ratio + n * (1 - ratio))
        left -= use
        prev = upper
    return int(round(total, 0))
