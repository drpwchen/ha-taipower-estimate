"""七個 sensor，語意對齊 YAML package（README「會多出哪些 sensor」）。"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfEnergy, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import async_generate_entity_id
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, signal_update
from .cycle import Snapshot
from .tracker import CycleTracker


@dataclass(frozen=True, kw_only=True)
class TaipowerSensorDescription(SensorEntityDescription):
    value_fn: Callable[[Snapshot], Any]
    attrs_fn: Callable[[Snapshot], dict] | None = None


def _cycle_attrs(s: Snapshot) -> dict:
    return {
        "period_start": s.period_start.isoformat(),
        "measure_start": s.measure_start.isoformat(),
        "next_reset": s.next_reset.isoformat(),
        "partial_cycle": s.partial,
    }


SENSORS: tuple[TaipowerSensorDescription, ...] = (
    TaipowerSensorDescription(
        key="cycle_energy",
        translation_key="cycle_energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=1,
        value_fn=lambda s: s.energy,
        attrs_fn=_cycle_attrs,
    ),
    TaipowerSensorDescription(
        key="cycle_days",
        translation_key="cycle_days",
        native_unit_of_measurement=UnitOfTime.DAYS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda s: s.days,
    ),
    TaipowerSensorDescription(
        key="cycle_progress",
        translation_key="cycle_progress",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda s: s.progress,
    ),
    TaipowerSensorDescription(
        key="cycle_estimate",
        translation_key="cycle_estimate",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda s: s.estimate,
        attrs_fn=lambda s: {"confidence": s.confidence},
    ),
    TaipowerSensorDescription(
        key="cycle_summer_ratio",
        translation_key="cycle_summer_ratio",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=4,
        value_fn=lambda s: s.summer_ratio,
    ),
    TaipowerSensorDescription(
        key="tier_price",
        translation_key="tier_price",
        native_unit_of_measurement="TWD/kWh",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda s: s.tier_price,
    ),
    TaipowerSensorDescription(
        key="cycle_bill",
        translation_key="cycle_bill",
        native_unit_of_measurement="TWD",
        device_class=SensorDeviceClass.MONETARY,
        # monetary 只允許 total；有 state_class 才有長期統計（statistics-graph 用 stat_types: state）
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=0,
        value_fn=lambda s: s.bill,
    ),
)


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    tracker: CycleTracker = entry.runtime_data
    async_add_entities(TaipowerSensor(hass, tracker, d) for d in SENSORS)


class TaipowerSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, hass: HomeAssistant, tracker: CycleTracker, description: TaipowerSensorDescription) -> None:
        self.entity_description = description
        self._tracker = tracker
        entry = tracker.entry
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        # entity_id 固定用英文（不受 HA 介面語言影響）：sensor.taipower_cycle_bill …
        self.entity_id = async_generate_entity_id("sensor.{}", f"taipower_{description.key}", hass=hass)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="ha-taipower-estimate",
            model=tracker.rates["profiles"][tracker.profile]["label"],
            sw_version=f"費率 {tracker.rates['effective_date']} 起實施",
            entry_type=DeviceEntryType.SERVICE,
        )
        self._snap: Snapshot | None = None

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(self.hass, signal_update(self._tracker.entry.entry_id), self._refresh)
        )
        self._snap = self._tracker.snapshot()

    @callback
    def _refresh(self) -> None:
        self._snap = self._tracker.snapshot()
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        return self._snap is not None and self.entity_description.value_fn(self._snap) is not None

    @property
    def native_value(self):
        return None if self._snap is None else self.entity_description.value_fn(self._snap)

    @property
    def extra_state_attributes(self) -> dict | None:
        fn = self.entity_description.attrs_fn
        return fn(self._snap) if fn and self._snap else None
