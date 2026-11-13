"""integration 的週期邏輯（cycle.py）。純 Python，不需要安裝 Home Assistant。

預期值是手算的日期與度數（算式寫在註解），不是從被測程式反推。
"""
import importlib.util
import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG_DIR = ROOT / "custom_components" / "taipower_estimate"

# 載入 integration 的子模組，但不執行它的 __init__.py（那裡 import homeassistant）
_spec = importlib.util.spec_from_file_location("te_pkg", PKG_DIR / "__init__.py",
                                               submodule_search_locations=[str(PKG_DIR)])
sys.modules["te_pkg"] = importlib.util.module_from_spec(_spec)
from te_pkg import cycle  # noqa: E402

sys.path.insert(0, str(ROOT / "tools"))
import taipower_calc as ref  # noqa: E402

TPE = timezone(timedelta(hours=8))
RATES = json.loads((PKG_DIR / "rates.json").read_text(encoding="utf-8"))
BI_ODD_13 = cycle.Schedule(months=2, day=13, parity="odd")


def t(y, m, d, h=0, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=TPE)


class ScheduleTests(unittest.TestCase):
    def test_bimonthly_odd(self):
        s = BI_ODD_13
        self.assertEqual(s.last_reset(t(2026, 11, 14)), t(2026, 11, 13))
        self.assertEqual(s.last_reset(t(2026, 11, 13)), t(2026, 11, 13))          # 剛好 00:00 算這期
        self.assertEqual(s.last_reset(t(2026, 11, 12, 23, 59)), t(2026, 9, 13))
        self.assertEqual(s.last_reset(t(2026, 12, 31)), t(2026, 11, 13))
        self.assertEqual(s.next_reset(t(2026, 11, 14)), t(2027, 1, 13))           # 跨年
        self.assertEqual(s.next_reset(t(2026, 11, 13)), t(2027, 1, 13))           # 不含當下
        self.assertEqual(s.last_reset(t(2027, 1, 5)), t(2026, 11, 13))

    def test_bimonthly_even(self):
        s = cycle.Schedule(months=2, day=5, parity="even")
        self.assertEqual(s.last_reset(t(2026, 11, 14)), t(2026, 10, 5))
        self.assertEqual(s.next_reset(t(2026, 11, 14)), t(2026, 12, 5))

    def test_monthly(self):
        s = cycle.Schedule(months=1, day=1)
        self.assertEqual(s.last_reset(t(2026, 11, 14)), t(2026, 11, 1))
        self.assertEqual(s.next_reset(t(2026, 11, 14)), t(2026, 12, 1))
        self.assertEqual(s.cycle_days, 30)

    def test_day_clamped_to_month_end(self):
        s = cycle.Schedule(months=1, day=31)
        self.assertEqual(s.next_reset(t(2027, 1, 31)), t(2027, 2, 28))   # 2027 不是閏年
        self.assertEqual(s.next_reset(t(2028, 1, 31)), t(2028, 2, 29))   # 2028 閏年
        self.assertEqual(s.last_reset(t(2026, 11, 14)), t(2026, 10, 31))


class ReadingTests(unittest.TestCase):
    def state(self):
        return cycle.CycleState(t(2026, 11, 13), t(2026, 11, 13), 0.0, None, BI_ODD_13.signature, "sensor.m")

    def test_first_reading_is_baseline(self):
        s = self.state()
        self.assertEqual(cycle.apply_reading(s, 12345.6), 0.0)
        self.assertEqual(s.used, 0.0)
        cycle.apply_reading(s, 12350.1)
        self.assertAlmostEqual(s.used, 4.5)

    def test_small_dip_ignored_without_double_count(self):
        s = self.state()
        for v in (1000.0, 1000.5, 1000.4, 1000.5, 1001.0):
            cycle.apply_reading(s, v)
        # 真實用量 1000.0 → 1001.0 ＝ 1.0；抖動 1000.5→1000.4→1000.5 不應多算
        self.assertAlmostEqual(s.used, 1.0)

    def test_meter_reset_counts_new_reading(self):
        s = self.state()
        for v in (5000.0, 5010.0, 2.0, 5.0):
            cycle.apply_reading(s, v)
        # 10（換表前）+ 2（新表從 0 到 2）+ 3 ＝ 15
        self.assertAlmostEqual(s.used, 15.0)


class LifecycleTests(unittest.TestCase):
    def test_new_install_without_initial_is_partial(self):
        now = t(2026, 11, 20, 10)
        s = cycle.new_state(BI_ODD_13, now, "sensor.m")
        self.assertEqual(s.period_start, t(2026, 11, 13))
        self.assertEqual(s.measure_start, now)

    def test_new_install_with_initial_counts_from_reading_day(self):
        s = cycle.new_state(BI_ODD_13, t(2026, 11, 20, 10), "sensor.m", initial_used=80)
        self.assertEqual(s.measure_start, t(2026, 11, 13))
        self.assertEqual(s.used, 80.0)

    def test_on_time_roll_over_keeps_baseline(self):
        s = cycle.CycleState(t(2026, 9, 13), t(2026, 9, 13), 700.0, 8000.0, BI_ODD_13.signature, "sensor.m")
        cycle.roll_over(s, BI_ODD_13, t(2026, 11, 13, 0, 0))
        self.assertEqual((s.period_start, s.measure_start, s.used, s.last_value),
                         (t(2026, 11, 13), t(2026, 11, 13), 0.0, 8000.0))
        cycle.apply_reading(s, 8003.0)
        self.assertAlmostEqual(s.used, 3.0)

    def test_restart_after_missed_reset_starts_fresh(self):
        # 存檔停在 9/13 那期，HA 停機到 11/15 才開 → 開新的一期，從現在量，基準重抓
        s = cycle.CycleState(t(2026, 9, 13), t(2026, 9, 13), 700.0, 8000.0, BI_ODD_13.signature, "sensor.m")
        what = cycle.reconcile(s, BI_ODD_13, t(2026, 11, 15, 9), "sensor.m")
        self.assertEqual(what, "rolled_over_late")
        self.assertEqual((s.period_start, s.measure_start, s.used, s.last_value),
                         (t(2026, 11, 13), t(2026, 11, 15, 9), 0.0, None))

    def test_restart_same_cycle_keeps_everything(self):
        s = cycle.CycleState(t(2026, 11, 13), t(2026, 11, 13), 50.0, 8050.0, BI_ODD_13.signature, "sensor.m")
        self.assertEqual(cycle.reconcile(s, BI_ODD_13, t(2026, 11, 20), "sensor.m"), "ok")
        self.assertEqual((s.used, s.last_value), (50.0, 8050.0))

    def test_source_changed_rebaselines(self):
        s = cycle.CycleState(t(2026, 11, 13), t(2026, 11, 13), 50.0, 8050.0, BI_ODD_13.signature, "sensor.old")
        self.assertEqual(cycle.reconcile(s, BI_ODD_13, t(2026, 11, 20), "sensor.new"), "source_changed")
        self.assertEqual((s.used, s.last_value, s.source), (50.0, None, "sensor.new"))

    def test_schedule_changed(self):
        # 原本 11/13 起算，改成奇數月 15 日 → 這期變成 9/15 起（比量測起點早）→ 保留用量
        s = cycle.CycleState(t(2026, 11, 13), t(2026, 11, 13), 50.0, 8050.0, BI_ODD_13.signature, "sensor.m")
        new = cycle.Schedule(months=2, day=15, parity="odd")
        cycle.reconcile(s, new, t(2026, 11, 14), "sensor.m")
        self.assertEqual((s.period_start, s.used), (t(2026, 9, 15), 50.0))
        s2 = cycle.CycleState(t(2026, 11, 13), t(2026, 11, 13), 50.0, 8050.0, BI_ODD_13.signature, "sensor.m")
        cycle.reconcile(s2, cycle.Schedule(months=1, day=14), t(2026, 11, 20), "sensor.m")
        # 改成每月 14 日 → 這期 11/14 起，晚於量測起點 11/13：舊用量不屬於這期 → 從現在重量
        self.assertEqual((s2.period_start, s2.measure_start, s2.used, s2.last_value),
                         (t(2026, 11, 14), t(2026, 11, 20), 0.0, None))

    def test_state_roundtrip(self):
        s = cycle.CycleState(t(2026, 11, 13), t(2026, 11, 15, 9, 30), 12.5, 8000.25, "2/13/odd", "sensor.m")
        self.assertEqual(cycle.CycleState.from_dict(json.loads(json.dumps(s.to_dict()))), s)


class ComputeTests(unittest.TestCase):
    def snap(self, start, now, used, measure_start=None, schedule=BI_ODD_13, profile="residential"):
        s = cycle.CycleState(start, measure_start or start, used, None, schedule.signature, "sensor.m")
        return cycle.compute(s, schedule, now, RATES, profile)

    def test_matches_reference_full_summer(self):
        # 7/13 起算第 20 天用了 270 度 → 外推 810 度，全夏月（同 test_package.test_all_summer）
        sn = self.snap(t(2026, 7, 13), t(2026, 8, 2), 270)
        self.assertEqual(sn.estimate, 810)
        self.assertEqual(sn.summer_ratio, 1.0)
        self.assertEqual(sn.bill, ref.bill(810, 1.0))
        self.assertEqual(sn.tier_price, ref.tier_price(810, 1.0))
        self.assertEqual((sn.days, sn.progress, sn.confidence), (20.0, 33.3, "medium"))
        self.assertEqual(sn.next_reset, t(2026, 9, 13))
        self.assertFalse(sn.partial)

    def test_straddle_summer_start(self):
        sn = self.snap(t(2026, 5, 13), t(2026, 6, 7), 300)   # 第 25 天
        self.assertEqual(sn.summer_ratio, round(41 / 60, 4))
        self.assertEqual(sn.estimate, 720)
        self.assertEqual(sn.bill, ref.bill(720, round(41 / 60, 4)))

    def test_under_min_days_unavailable(self):
        sn = self.snap(t(2026, 11, 13), t(2026, 11, 15, 23), 10)   # 2.96 天
        self.assertEqual((sn.estimate, sn.tier_price, sn.bill), (None, None, None))
        self.assertEqual(sn.days, 2.96)
        self.assertEqual(sn.energy, 10.0)

    def test_partial_cycle_extrapolates_measured_rate(self):
        # 週期 11/13 起，11/20 才裝；裝後 10 天用 150 度 → 15 度/天 × 60 ＝ 900 度
        sn = self.snap(t(2026, 11, 13), t(2026, 11, 30), 150, measure_start=t(2026, 11, 20))
        self.assertTrue(sn.partial)
        self.assertEqual(sn.days, 10.0)
        self.assertEqual(sn.estimate, 900)
        self.assertEqual(sn.progress, round(17 / 60 * 100, 1))   # 進度照週期算：17/60

    def test_monthly_commercial(self):
        s = cycle.Schedule(months=1, day=1)
        sn = self.snap(t(2026, 7, 1), t(2026, 7, 11), 140, schedule=s, profile="commercial")
        self.assertEqual(sn.estimate, 420)
        self.assertEqual(sn.bill, ref.bill(420, 1.0, "commercial", months=1))   # 2.71×330 + 3.76×90 = 1232.7
        self.assertEqual(sn.bill, 1233)

    def test_progress_capped(self):
        sn = self.snap(t(2026, 7, 13), t(2026, 9, 20), 100)
        self.assertEqual(sn.progress, 100.0)


class BundledRates(unittest.TestCase):
    def test_component_rates_is_copy_of_single_source(self):
        self.assertEqual((PKG_DIR / "rates.json").read_text(encoding="utf-8"),
                         (ROOT / "tariff" / "rates.json").read_text(encoding="utf-8"))

    def test_manifest_and_translations(self):
        m = json.loads((PKG_DIR / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(m["domain"], "taipower_estimate")
        self.assertTrue(m["config_flow"])
        en = json.loads((PKG_DIR / "translations" / "en.json").read_text(encoding="utf-8"))
        zh = json.loads((PKG_DIR / "translations" / "zh-Hant.json").read_text(encoding="utf-8"))

        def keys(d, p=""):
            return {p + k for k in d} | {x for k, v in d.items() if isinstance(v, dict) for x in keys(v, p + k + ".")}
        self.assertEqual(keys(en), keys(zh))


if __name__ == "__main__":
    unittest.main()
