"""把 packages/taipower_estimate.yaml 裡真正的 Jinja 模板拿出來，用假的 HA 函式渲染，
結果必須等於 tools/taipower_calc.py 的答案。也檢查 YAML 與 rates.json 沒有脫鉤。

需要 PyYAML 與 Jinja2（HA 本身就用 Jinja2）：pip install pyyaml jinja2
"""
import sys
import unittest
from datetime import datetime, timedelta, timezone

TPE = timezone(timedelta(hours=8))  # 台北；HA 的 as_local 在測試裡以此模擬
from pathlib import Path

import jinja2
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import gen_package  # noqa: E402
import taipower_calc as calc  # noqa: E402

PKG = ROOT / "packages" / "taipower_estimate.yaml"
UTC = timezone.utc


def load_sensors(path=PKG):
    doc = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return {s["name"]: s for s in doc["template"][0]["sensor"]}, doc


class FakeHA:
    """最小的 HA 模板環境：states / state_attr / has_value / now / as_datetime。"""

    def __init__(self, now, states=None, attrs=None):
        self.now_ = now
        self.st = dict(states or {})
        self.at = dict(attrs or {})
        env = jinja2.Environment()
        env.globals.update(
            states=lambda e: self.st.get(e, "unknown"),
            state_attr=lambda e, a: self.at.get((e, a)),
            has_value=lambda e: self.st.get(e, "unknown") not in ("unknown", "unavailable", "none", None),
            now=lambda: self.now_,
            timedelta=timedelta,
        )
        env.filters["as_datetime"] = lambda v: v if isinstance(v, datetime) else datetime.fromisoformat(v)
        env.filters["as_local"] = lambda v: v.astimezone(TPE)
        self.env = env

    def render(self, tmpl: str) -> str:
        return self.env.from_string(tmpl).render().strip()

    def run_sensor(self, sensor: dict, entity: str):
        """依 availability → state 的順序算，把結果寫回 self.st。"""
        avail = self.render(sensor["availability"]) if "availability" in sensor else "True"
        if avail != "True":
            self.st[entity] = "unavailable"
            return
        self.st[entity] = self.render(sensor["state"])


ORDER = [
    ("Power cycle days", "sensor.power_cycle_days"),
    ("Power cycle progress", "sensor.power_cycle_progress"),
    ("Power cycle estimate", "sensor.power_cycle_estimate"),
    ("Power cycle summer ratio", "sensor.power_cycle_summer_ratio"),
    ("Power tier price", "sensor.power_tier_price"),
    ("Power cycle bill", "sensor.power_cycle_bill"),
]


def evaluate(sensors, reset: datetime, now: datetime, kwh_so_far: float):
    ha = FakeHA(
        now,
        states={"sensor.power_cycle_energy": str(kwh_so_far)},
        attrs={("sensor.power_cycle_energy", "last_reset"): reset.isoformat()},
    )
    for name, ent in ORDER:
        ha.run_sensor(sensors[name], ent)
    return ha


class PackageMatchesReference(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sensors, cls.doc = load_sensors()

    def check(self, reset, days_elapsed, kwh_so_far):
        now = reset + timedelta(days=days_elapsed)
        ha = evaluate(self.sensors, reset, now, kwh_so_far)
        est = round(kwh_so_far / days_elapsed * 60)
        r = calc.summer_ratio(reset.astimezone(TPE).date(), 60)
        self.assertAlmostEqual(float(ha.st["sensor.power_cycle_days"]), days_elapsed, places=2)
        self.assertEqual(float(ha.st["sensor.power_cycle_estimate"]), est)
        self.assertAlmostEqual(float(ha.st["sensor.power_cycle_summer_ratio"]), r, places=4)
        self.assertAlmostEqual(float(ha.st["sensor.power_tier_price"]), calc.tier_price(est, r), places=2)
        self.assertEqual(float(ha.st["sensor.power_cycle_bill"]), calc.bill(est, r))
        return ha

    def test_all_summer(self):
        # 7/13 起算，走到第 20 天用了 270 度 → 外推 810 度
        self.check(datetime(2026, 7, 13, tzinfo=UTC), 20, 270)

    def test_all_non_summer(self):
        self.check(datetime(2026, 11, 13, tzinfo=UTC), 30, 400)

    def test_straddles_summer_start(self):
        # 5/13 起算：41 天夏月、19 天非夏月
        ha = self.check(datetime(2026, 5, 13, tzinfo=UTC), 25, 300)
        self.assertAlmostEqual(float(ha.st["sensor.power_cycle_summer_ratio"]), round(41 / 60, 4), places=4)

    def test_straddles_summer_end(self):
        self.check(datetime(2026, 9, 13, tzinfo=UTC), 45, 900)

    def test_top_tier(self):
        self.check(datetime(2026, 7, 13, tzinfo=UTC), 15, 600)  # 外推 2400 度

    def test_utc_last_reset_is_converted_to_local_date(self):
        # 台北 10/1 00:00 歸零，HA 的 last_reset 常以 UTC 表示＝9/30 16:00。
        # 不轉本地時間會被算成 9/30（夏月）→ 占比 1/60，應為 0（10/1 起全非夏月）。
        reset = datetime(2026, 9, 30, 16, 0, tzinfo=UTC)
        ha = self.check(reset, 20, 200)
        self.assertEqual(float(ha.st["sensor.power_cycle_summer_ratio"]), 0.0)
        # 台北 6/1 00:00 歸零（UTC 5/31 16:00）→ 60 天全夏月 → 占比 1.0
        reset = datetime(2026, 5, 31, 16, 0, tzinfo=UTC)
        ha = self.check(reset, 20, 200)
        self.assertEqual(float(ha.st["sensor.power_cycle_summer_ratio"]), 1.0)

    def test_progress(self):
        ha = evaluate(self.sensors, datetime(2026, 7, 13, tzinfo=UTC),
                      datetime(2026, 7, 13, tzinfo=UTC) + timedelta(days=15), 100)
        self.assertEqual(float(ha.st["sensor.power_cycle_progress"]), 25.0)

    def test_progress_capped_at_100(self):
        ha = evaluate(self.sensors, datetime(2026, 7, 13, tzinfo=UTC),
                      datetime(2026, 7, 13, tzinfo=UTC) + timedelta(days=64), 100)
        self.assertEqual(float(ha.st["sensor.power_cycle_progress"]), 100.0)


class DenominatorGuard(unittest.TestCase):
    """分母不到 3 天不給數字（避免元旦 00:01 預估碰到最高級的老問題）。"""

    @classmethod
    def setUpClass(cls):
        cls.sensors, _ = load_sensors()

    def test_under_min_days_everything_unavailable(self):
        reset = datetime(2026, 7, 13, tzinfo=UTC)
        ha = evaluate(self.sensors, reset, reset + timedelta(minutes=1), 0.01)
        for ent in ("sensor.power_cycle_estimate", "sensor.power_tier_price", "sensor.power_cycle_bill"):
            self.assertEqual(ha.st[ent], "unavailable", ent)
        self.assertNotEqual(ha.st["sensor.power_cycle_days"], "unavailable")  # 分母本身看得到

    def test_two_days_still_unavailable_three_days_ok(self):
        reset = datetime(2026, 7, 13, tzinfo=UTC)
        self.assertEqual(evaluate(self.sensors, reset, reset + timedelta(days=2.9), 30).st["sensor.power_cycle_estimate"], "unavailable")
        self.assertNotEqual(evaluate(self.sensors, reset, reset + timedelta(days=3), 30).st["sensor.power_cycle_estimate"], "unavailable")

    def test_confidence_levels(self):
        reset = datetime(2026, 7, 13, tzinfo=UTC)
        for days, want in ((5, "low"), (10, "medium"), (30, "high")):
            ha = FakeHA(reset, states={"sensor.power_cycle_days": str(days)})
            got = ha.render(self.sensors["Power cycle estimate"]["attributes"]["confidence"])
            self.assertEqual(got, want, days)

    def test_no_last_reset_means_unavailable(self):
        ha = FakeHA(datetime(2026, 7, 13, tzinfo=UTC), states={"sensor.power_cycle_energy": "10"})
        for name, ent in ORDER:
            ha.run_sensor(self.sensors[name], ent)
        self.assertEqual(ha.st["sensor.power_cycle_days"], "unavailable")
        self.assertEqual(ha.st["sensor.power_cycle_bill"], "unavailable")


class StructureAndDrift(unittest.TestCase):
    def test_committed_package_matches_generator(self):
        # 已 commit 的 YAML == 用預設參數從 rates.json 重產的結果（防止手改 YAML 或只改 rates.json）
        expected = gen_package.render(**gen_package.DEFAULTS)
        self.assertEqual(PKG.read_text(encoding="utf-8"), expected)

    def test_only_one_reset_mechanism(self):
        _, doc = load_sensors()
        um = doc["utility_meter"]
        self.assertEqual(list(um), ["power_cycle_energy"])
        self.assertIn("cron", um["power_cycle_energy"])

    def test_unique_ids_present_and_unique(self):
        sensors, _ = load_sensors()
        ids = [s["unique_id"] for s in sensors.values()]
        self.assertEqual(len(ids), len(set(ids)))

    def test_tier_table_in_yaml_equals_rates_json(self):
        text = PKG.read_text(encoding="utf-8")
        for upper, s, n in calc.bands("residential", 2):
            self.assertIn(f"({upper}, {s:g}, {n:g})", text)

    def test_generator_options_flow_into_yaml(self):
        text = gen_package.render("commercial", 1, "sensor.meter_kwh", "0 0 5 * *", 5)
        doc = yaml.safe_load(text)
        self.assertEqual(doc["utility_meter"]["power_cycle_energy"]["source"], "sensor.meter_kwh")
        self.assertEqual(doc["utility_meter"]["power_cycle_energy"]["cron"], "0 0 5 * *")
        self.assertIn("(330, 2.71, 2.28)", text)
        self.assertIn("range(30)", text)
        self.assertIn(">= 5 }}", text)

    def test_monthly_commercial_package_matches_reference(self):
        # 換 profile／months 後，Jinja 結果仍等於參考實作
        text = gen_package.render("commercial", 1, "sensor.m", "0 0 1 * *", 3)
        tmp = ROOT / "tests" / "_tmp_commercial.yaml"
        try:
            tmp.write_text(text, encoding="utf-8")
            sensors, _ = load_sensors(tmp)
        finally:
            tmp.unlink(missing_ok=True)
        reset = datetime(2026, 7, 1, tzinfo=UTC)
        ha = evaluate(sensors, reset, reset + timedelta(days=10), 140)   # 外推 420 度/月
        r = calc.summer_ratio(reset.date(), 30)
        self.assertEqual(float(ha.st["sensor.power_cycle_estimate"]), 420)
        self.assertEqual(float(ha.st["sensor.power_cycle_bill"]), calc.bill(420, r, "commercial", months=1))


if __name__ == "__main__":
    unittest.main()
