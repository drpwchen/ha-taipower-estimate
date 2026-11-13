"""台電電費估算（Taipower bill estimate）— Home Assistant custom integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN, STORAGE_VERSION, load_rates
from .tracker import CycleTracker

PLATFORMS = [Platform.SENSOR]

type TaipowerConfigEntry = ConfigEntry[CycleTracker]


async def async_setup_entry(hass: HomeAssistant, entry: TaipowerConfigEntry) -> bool:
    rates = await hass.async_add_executor_job(load_rates)
    tracker = CycleTracker(hass, entry, rates)
    await tracker.async_start()
    entry.runtime_data = tracker
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: TaipowerConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        await entry.runtime_data.async_stop()
    return ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """刪掉 integration 時一併刪掉週期存檔。"""
    await Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}").async_remove()


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
