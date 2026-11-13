"""費率計算（純 Python，不 import Home Assistant）。

這是整個 repo 的計算核心：integration 直接用；`tools/taipower_calc.py` 以檔案路徑載入本檔，
作為 YAML package 測試的對照答案。邏輯：
  - 級距上限 = 每月上限 × months（兩個月抄表 → 各段度數加倍，台電電價表註記）
  - 週期跨夏月／非夏月時，每度電價 = 夏月價 × r + 非夏月價 × (1 − r)，
    r = 週期內夏月天數 / 週期天數。這是近似，不是台電帳單的逐字算法（見 README「限制」）。
"""
from __future__ import annotations

from datetime import date, timedelta

BIG = 999999  # 「無上限」的哨兵值（跟 YAML 一致）


def bands(rates: dict, profile: str = "residential", months: int = 2) -> list[tuple[int, float, float]]:
    """回傳 [(upper_kwh, summer_rate, non_summer_rate), ...]，最後一段 upper 為 BIG。"""
    out = []
    for b in rates["profiles"][profile]["bands"]:
        upper = BIG if b["upto"] is None else b["upto"] * months
        out.append((upper, b["summer"], b["non_summer"]))
    return out


def summer_ratio(start: date, cycle_days: int, summer_months=(6, 7, 8, 9)) -> float:
    """週期（從 start 起算 cycle_days 天）內夏月天數占比，四捨五入到 4 位。"""
    n = sum(1 for i in range(cycle_days) if (start + timedelta(days=i)).month in summer_months)
    return round(n / cycle_days, 4)


def tier_price(kwh: float, ratio: float, band_table) -> float:
    """用電 kwh 所在級距的（夏月／非夏月加權）每度電價，四捨五入到 2 位。"""
    for upper, s, n in band_table:
        if kwh <= upper:
            return round(s * ratio + n * (1 - ratio), 2)
    raise AssertionError("unreachable: last band is unbounded")


def bill(kwh: float, ratio: float, band_table) -> int:
    """逐級累進電費（元，四捨五入到整數）。不含底度／最低 100 元規則。"""
    total, left, prev = 0.0, kwh, 0
    for upper, s, n in band_table:
        if left <= 0:
            break
        use = min(left, upper - prev)
        total += use * (s * ratio + n * (1 - ratio))
        left -= use
        prev = upper
    return int(round(total, 0))
