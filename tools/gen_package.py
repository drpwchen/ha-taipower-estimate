"""由 tariff/rates.json + tools/package.yaml.tmpl 產生 packages/taipower_estimate.yaml。

用法：
  python tools/gen_package.py                       # 預設：住宅、兩個月、重寫 packages/taipower_estimate.yaml
  python tools/gen_package.py --source sensor.my_meter_kwh --cron "0 0 5 2,4,6,8,10,12 *"
  python tools/gen_package.py --profile commercial --out my_package.yaml
  python tools/gen_package.py --check               # 預設參數的輸出必須跟已 commit 的檔一致（測試用）
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import taipower_calc as calc  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TMPL = ROOT / "tools" / "package.yaml.tmpl"
DEFAULT_OUT = ROOT / "packages" / "taipower_estimate.yaml"
COMPONENT_RATES = ROOT / "custom_components" / "taipower_estimate" / "rates.json"

DEFAULTS = dict(
    profile="residential",
    months=2,
    source="sensor.your_total_energy_kwh",
    cron="0 0 13 1,3,5,7,9,11 *",
    min_days=3,
)


def _num(x: float) -> str:
    return f"{x:g}"


def render(profile: str, months: int, source: str, cron: str, min_days: int, rates: dict | None = None) -> str:
    rates = rates or calc.load_rates()
    if profile not in rates["profiles"]:
        raise SystemExit(f"unknown profile {profile!r}; choose from {list(rates['profiles'])}")
    if months not in (1, 2):
        raise SystemExit("--months must be 1 or 2 (台電只有單月／雙月抄表)")
    cycle_days = 30 * months
    tiers = ",\n                          ".join(
        f"({u}, {_num(s)}, {_num(n)})" for u, s, n in calc.bands(profile, months, rates)
    )
    sm = rates["summer_months"]
    cli = "python tools/gen_package.py"
    if (profile, months, source, cron, min_days) != tuple(DEFAULTS[k] for k in ("profile", "months", "source", "cron", "min_days")):
        cli += (f' --profile {profile} --months {months} --source {source}'
                f' --cron "{cron}" --min-days {min_days}')
    subs = {
        "TARIFF": rates["tariff"],
        "EFFECTIVE": rates["effective_date"],
        "VERIFIED": rates["verified_on"],
        "PROFILE_LABEL": rates["profiles"][profile]["label"],
        "MONTHS": str(months),
        "CYCLE_DAYS": str(cycle_days),
        "MIN_DAYS": str(min_days),
        "SOURCE": source,
        "CRON": cron,
        "SUMMER_MONTHS": "[" + ", ".join(str(m) for m in sm) + "]",
        "SUMMER_LABEL": f"{sm[0]}–{sm[-1]} 月",
        "TIERS": tiers,
        "CLI": cli,
    }
    text = TMPL.read_text(encoding="utf-8")
    for k, v in subs.items():
        text = text.replace(f"@@{k}@@", v)
    if "@@" in text:
        raise SystemExit("template has unfilled @@TOKEN@@")
    return text


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--profile", default=DEFAULTS["profile"])
    ap.add_argument("--months", type=int, default=DEFAULTS["months"])
    ap.add_argument("--source", default=DEFAULTS["source"])
    ap.add_argument("--cron", default=DEFAULTS["cron"])
    ap.add_argument("--min-days", type=int, default=DEFAULTS["min_days"])
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--check", action="store_true", help="只檢查 --out 是否與重產結果一致")
    a = ap.parse_args(argv)
    text = render(a.profile, a.months, a.source, a.cron, a.min_days)
    rates_src = calc.RATES_PATH.read_text(encoding="utf-8")
    if a.check:
        bad = 0
        if not a.out.exists() or a.out.read_text(encoding="utf-8") != text:
            print(f"DRIFT: {a.out} 與 rates.json／模板重產結果不同；重跑 python tools/gen_package.py", file=sys.stderr)
            bad = 1
        if not COMPONENT_RATES.exists() or COMPONENT_RATES.read_text(encoding="utf-8") != rates_src:
            print(f"DRIFT: {COMPONENT_RATES} 與 tariff/rates.json 不同；重跑 python tools/gen_package.py", file=sys.stderr)
            bad = 1
        if not bad:
            print("ok: package and integration match rates.json")
        return bad
    a.out.parent.mkdir(parents=True, exist_ok=True)
    with open(a.out, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print(f"wrote {a.out}")
    if a.out == DEFAULT_OUT:
        # integration 內附的費率：tariff/rates.json 的逐字複本（HACS 只發 custom_components/ 底下的檔）
        with open(COMPONENT_RATES, "w", encoding="utf-8", newline="") as f:
            f.write(rates_src)
        print(f"wrote {COMPONENT_RATES}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
