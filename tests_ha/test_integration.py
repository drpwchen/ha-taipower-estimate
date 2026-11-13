"""config flow、sensor 建立、讀數累積、抄表日歸零、重啟還原、選項修改。

跑法：.venv 裝 pytest-homeassistant-custom-component 後 `python -m pytest`（見 README「開發與測試」）。
"""
from datetime import datetime, timedelta

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.taipower_estimate.const import DOMAIN

SRC = "sensor.meter_total"
DATA = {"source": SRC, "profile": "residential", "months": 2, "reading_day": 13, "reading_parity": "odd"}


@pytest.fixture
async def tz(hass: HomeAssistant):
    await hass.config.async_set_time_zone("Asia/Taipei")


def local(y, m, d, h=0, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=dt_util.get_default_time_zone())


async def setup_entry(hass, data=None, options=None) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, title="台電電費估算", data=data or DATA, options=options or {},
                            unique_id=(data or DATA)["source"])
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def val(hass, key):
    return hass.states.get(f"sensor.taipower_{key}").state


async def test_config_flow_creates_entry(hass: HomeAssistant, tz) -> None:
    hass.states.async_set(SRC, "1000", {"unit_of_measurement": "kWh", "device_class": "energy"})
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"source": SRC, "profile": "commercial", "months": "1", "reading_day": 5.0,
         "reading_parity": "odd", "initial_used": 42},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {"source": SRC, "profile": "commercial", "months": 1, "reading_day": 5,
                              "reading_parity": "odd", "initial_used": 42.0}
    await hass.async_block_till_done()
    assert hass.states.get("sensor.taipower_cycle_energy").state == "42.0"

    # 同一個電表 sensor 不能設定兩次
    again = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    again = await hass.config_entries.flow.async_configure(
        again["flow_id"],
        {"source": SRC, "profile": "residential", "months": "2", "reading_day": 13, "reading_parity": "odd"},
    )
    assert again["type"] is FlowResultType.ABORT
    assert again["reason"] == "already_configured"


async def test_accumulates_and_extrapolates(hass: HomeAssistant, tz, freezer: FrozenDateTimeFactory) -> None:
    freezer.move_to(local(2026, 7, 13, 0, 0))
    hass.states.async_set(SRC, "8000")
    await setup_entry(hass)
    states = {k: hass.states.get(f"sensor.taipower_{k}") for k in
              ("cycle_energy", "cycle_days", "cycle_progress", "cycle_estimate",
               "cycle_summer_ratio", "tier_price", "cycle_bill")}
    assert all(states.values()), states
    assert val(hass, "cycle_energy") == "0.0"
    assert val(hass, "cycle_estimate") == "unavailable"           # 分母 0 天

    freezer.move_to(local(2026, 8, 2, 0, 0))                      # 第 20 天
    hass.states.async_set(SRC, "8270")                           # 用了 270 度
    await hass.async_block_till_done()
    assert val(hass, "cycle_energy") == "270.0"
    assert float(val(hass, "cycle_days")) == 20.0
    assert val(hass, "cycle_estimate") == "810"                  # 270/20×60
    assert float(val(hass, "cycle_summer_ratio")) == 1.0
    assert float(val(hass, "tier_price")) == 3.80
    assert val(hass, "cycle_bill") == "2068"                     # 1.78×240 + 2.55×420 + 3.80×150 = 2068.2
    est = hass.states.get("sensor.taipower_cycle_estimate")
    assert est.attributes["confidence"] == "medium"
    assert hass.states.get("sensor.taipower_cycle_energy").attributes["partial_cycle"] is False


async def test_unavailable_source_is_ignored(hass: HomeAssistant, tz, freezer) -> None:
    freezer.move_to(local(2026, 11, 13, 0, 0))
    hass.states.async_set(SRC, "100")
    await setup_entry(hass)
    for v in ("unavailable", "unknown", "garbage", "103"):
        hass.states.async_set(SRC, v)
        await hass.async_block_till_done()
    assert val(hass, "cycle_energy") == "3.0"                    # 停電期間的度數在下一個讀數補回


async def test_resets_on_reading_day(hass: HomeAssistant, tz, freezer) -> None:
    freezer.move_to(local(2026, 9, 13, 0, 0))
    hass.states.async_set(SRC, "8000")
    await setup_entry(hass)
    freezer.move_to(local(2026, 11, 12, 23, 0))
    hass.states.async_set(SRC, "8700")
    await hass.async_block_till_done()
    assert val(hass, "cycle_energy") == "700.0"

    freezer.move_to(local(2026, 11, 13, 0, 0) + timedelta(seconds=1))
    async_fire_time_changed(hass, local(2026, 11, 13, 0, 0) + timedelta(seconds=1))
    await hass.async_block_till_done()
    assert val(hass, "cycle_energy") == "0.0"
    attrs = hass.states.get("sensor.taipower_cycle_energy").attributes
    assert attrs["period_start"].startswith("2026-11-13T00:00:00")
    assert attrs["next_reset"].startswith("2027-01-13T00:00:00")

    hass.states.async_set(SRC, "8705")
    await hass.async_block_till_done()
    assert val(hass, "cycle_energy") == "5.0"                    # 歸零當下的讀數 8700 是新基準


async def test_state_survives_reload(hass: HomeAssistant, tz, freezer) -> None:
    freezer.move_to(local(2026, 11, 13, 0, 0))
    hass.states.async_set(SRC, "100")
    entry = await setup_entry(hass)
    hass.states.async_set(SRC, "150")
    await hass.async_block_till_done()
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert val(hass, "cycle_energy") == "50.0"
    hass.states.async_set(SRC, "160")                            # 停機時電表持續走 → 差值補回
    await hass.async_block_till_done()
    assert val(hass, "cycle_energy") == "60.0"


async def test_options_change_profile(hass: HomeAssistant, tz, freezer) -> None:
    freezer.move_to(local(2026, 7, 1, 0, 0))
    hass.states.async_set(SRC, "0")
    entry = await setup_entry(hass, data={**DATA, "months": 1, "reading_day": 1})
    freezer.move_to(local(2026, 7, 11, 0, 0))
    hass.states.async_set(SRC, "140")
    await hass.async_block_till_done()
    assert val(hass, "cycle_bill") == "1091"                     # 住宅單月 420 度：1.78×120 + 2.55×210 + 3.80×90 = 1091.1

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"source": SRC, "profile": "commercial", "months": "1", "reading_day": 1, "reading_parity": "odd"},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert val(hass, "cycle_energy") == "140.0"                  # 換類別不影響已量到的度數
    assert val(hass, "cycle_estimate") == "420"
    assert val(hass, "cycle_bill") == "1233"                     # 2.71×330 + 3.76×90 = 1232.7


async def test_remove_entry_deletes_storage(hass: HomeAssistant, tz, hass_storage) -> None:
    hass.states.async_set(SRC, "100")
    entry = await setup_entry(hass)
    await hass.async_block_till_done()
    key = f"{DOMAIN}.{entry.entry_id}"
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert key in hass_storage
    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert key not in hass_storage
