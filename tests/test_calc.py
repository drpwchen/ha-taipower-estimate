"""費率計算測試。預期值是台電官方範例或手算（算式寫在註解），不是從被測程式反推。"""
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import taipower_calc as c  # noqa: E402


class OfficialExamples(unittest.TestCase):
    """台電《各類電價表及計算範例》（114-10-01 版）的官方算例。"""

    def test_residential_august_400_kwh_monthly(self):
        # 官方：1.78×120 + 2.55×(330−120) + 3.80×(400−330) = 1,015 元
        self.assertEqual(c.bill(400, 1.0, "residential", months=1), 1015)

    def test_non_commercial_august_800_kwh_monthly(self):
        # 官方：1.78×120 + 2.55×210 + 3.80×170 + 5.14×200 + 6.44×100 = 3,067 元
        self.assertEqual(c.bill(800, 1.0, "non_commercial", months=1), 3067)


class Bimonthly(unittest.TestCase):
    """兩個月抄表：各段度數加倍（官方註記）。"""

    def test_bands_doubled(self):
        uppers = [b[0] for b in c.bands("residential", 2)]
        self.assertEqual(uppers, [240, 660, 1000, 1400, 2000, c.BIG])

    def test_summer_800(self):
        # 1.78×240 + 2.55×420 + 3.80×140 = 427.2 + 1071 + 532 = 2030.2
        self.assertEqual(c.bill(800, 1.0), 2030)

    def test_non_summer_800(self):
        # 1.78×240 + 2.26×420 + 3.13×140 = 427.2 + 949.2 + 438.2 = 1814.6
        self.assertEqual(c.bill(800, 0.0), 1815)

    def test_half_summer_is_average(self):
        # 費率線性混合 → (2030.2 + 1814.6) / 2 = 1922.4
        self.assertEqual(c.bill(800, 0.5), 1922)

    def test_top_tier_summer_2500(self):
        # 427.2 + 420×2.55 + 340×3.80 + 400×5.14 + 600×6.44 + 500×8.86
        # = 427.2 + 1071 + 1292 + 2056 + 3864 + 4430 = 13140.2
        self.assertEqual(c.bill(2500, 1.0), 13140)

    def test_zero(self):
        self.assertEqual(c.bill(0, 1.0), 0)

    def test_boundary_240_and_241(self):
        self.assertEqual(c.bill(240, 1.0), 427)   # 1.78×240 = 427.2
        self.assertEqual(c.bill(241, 1.0), 430)   # 427.2 + 2.55 = 429.75

    def test_bill_is_continuous_and_monotonic(self):
        prev = -1
        for kwh in range(0, 2600, 7):
            b = c.bill(kwh, 0.3)
            self.assertGreaterEqual(b, prev)
            prev = b


class TierPrice(unittest.TestCase):
    def test_tiers_summer(self):
        self.assertEqual(c.tier_price(100, 1.0), 1.78)
        self.assertEqual(c.tier_price(240, 1.0), 1.78)   # 邊界歸下一段之前
        self.assertEqual(c.tier_price(241, 1.0), 2.55)
        self.assertEqual(c.tier_price(660, 1.0), 2.55)
        self.assertEqual(c.tier_price(800, 1.0), 3.80)
        self.assertEqual(c.tier_price(2500, 1.0), 8.86)

    def test_tiers_non_summer(self):
        self.assertEqual(c.tier_price(800, 0.0), 3.13)
        self.assertEqual(c.tier_price(2500, 0.0), 7.03)

    def test_blend(self):
        # 0.25×3.80 + 0.75×3.13 = 3.2975 → 3.3
        self.assertAlmostEqual(c.tier_price(800, 0.25), 3.30, places=2)


class Commercial(unittest.TestCase):
    def test_monthly_410_summer(self):
        # 2.71×330 + 3.76×80 = 894.3 + 300.8 = 1195.1
        self.assertEqual(c.bill(410, 1.0, "commercial", months=1), 1195)

    def test_bimonthly_bands(self):
        self.assertEqual([b[0] for b in c.bands("commercial", 2)], [660, 1400, 3000, 6000, c.BIG])


class SummerRatio(unittest.TestCase):
    """夏月＝6/1–9/30。週期從 reset 起算 60 天。"""

    def days(self, d):
        return round(c.summer_ratio(d, 60) * 60)

    def test_cycles(self):
        self.assertEqual(self.days(date(2026, 3, 13)), 0)    # 3/13 → 5/11，全非夏月
        self.assertEqual(self.days(date(2026, 5, 13)), 41)   # 5/13–5/31 非夏 19 天，6/1–7/11 夏月 41 天
        self.assertEqual(self.days(date(2026, 7, 13)), 60)   # 7/13 → 9/10，全夏月
        self.assertEqual(self.days(date(2026, 9, 13)), 18)   # 9/13–9/30 夏月 18 天，之後非夏月
        self.assertEqual(self.days(date(2026, 11, 13)), 0)

    def test_summer_months_match_official(self):
        self.assertEqual(c.load_rates()["summer_months"], [6, 7, 8, 9])


class RatesFile(unittest.TestCase):
    def test_bands_sorted_and_last_unbounded(self):
        for name, p in c.load_rates()["profiles"].items():
            ups = [b["upto"] for b in p["bands"]]
            self.assertIsNone(ups[-1], name)
            finite = ups[:-1]
            self.assertEqual(finite, sorted(finite), name)

    def test_rates_non_decreasing(self):
        for name, p in c.load_rates()["profiles"].items():
            for key in ("summer", "non_summer"):
                v = [b[key] for b in p["bands"]]
                self.assertEqual(v, sorted(v), f"{name}.{key}")

    def test_effective_date_recorded(self):
        r = c.load_rates()
        self.assertEqual(r["effective_date"], "2025-10-01")
        self.assertTrue(r["sources"])


if __name__ == "__main__":
    unittest.main()
