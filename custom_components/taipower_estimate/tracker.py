"""把 cycle.py 的純邏輯接上 Home Assistant：聽電表讀數、到抄表日歸零、存檔、通知 sensor。"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, State, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import (
    async_track_point_in_time,
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from . import cycle
from .const import (
    CONF_DAY,
    CONF_INITIAL_USED,
    CONF_MONTHS,
    CONF_PARITY,
    CONF_PROFILE,
    CONF_SOURCE,
    DEFAULT_PARITY,
    DOMAIN,
    MIN_DAYS,
    SAVE_DELAY,
    STORAGE_VERSION,
    TICK_MINUTES,
    signal_update,
)

_LOGGER = logging.getLogger(__name__)


def entry_options(entry: ConfigEntry) -> dict:
    """設定以 options 為準（options flow 改過的值），沒有就用初次設定的 data。"""
    return {**entry.data, **entry.options}


def schedule_from(opts: dict) -> cycle.Schedule:
    return cycle.Schedule(
        months=int(opts[CONF_MONTHS]),
        day=int(opts[CONF_DAY]),
        parity=opts.get(CONF_PARITY, DEFAULT_PARITY),
    )


class CycleTracker:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, rates: dict) -> None:
        self.hass = hass
        self.entry = entry
        self.rates = rates
        opts = entry_options(entry)
        self.source: str = opts[CONF_SOURCE]
        self.profile: str = opts[CONF_PROFILE]
        self.schedule = schedule_from(opts)
        self.state: cycle.CycleState | None = None
        self._store: Store = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")
        self._unsubs: list = []
        self._unsub_reset = None

    async def async_start(self) -> None:
        now = dt_util.now()
        saved = await self._store.async_load()
        if saved:
            self.state = cycle.CycleState.from_dict(saved)
            what = cycle.reconcile(self.state, self.schedule, now, self.source)
            _LOGGER.debug("%s restored cycle state: %s", self.entry.title, what)
        else:
            init = self.entry.data.get(CONF_INITIAL_USED)
            self.state = cycle.new_state(self.schedule, now, self.source,
                                         None if init in (None, "") else float(init))
        self._apply_state(self.hass.states.get(self.source))
        self._unsubs.append(async_track_state_change_event(self.hass, [self.source], self._on_source))
        self._unsubs.append(async_track_time_interval(self.hass, self._on_tick, timedelta(minutes=TICK_MINUTES)))
        self._schedule_reset()
        self._store.async_delay_save(self.state.to_dict, 0)

    async def async_stop(self) -> None:
        for u in self._unsubs:
            u()
        self._unsubs.clear()
        if self._unsub_reset:
            self._unsub_reset()
            self._unsub_reset = None
        if self.state:
            await self._store.async_save(self.state.to_dict())

    async def async_remove(self) -> None:
        await self._store.async_remove()

    # --- 事件 ---

    def _apply_state(self, st: State | None) -> bool:
        if st is None or st.state in (STATE_UNKNOWN, STATE_UNAVAILABLE, "", None):
            return False
        try:
            value = float(st.state)
        except ValueError:
            return False
        cycle.apply_reading(self.state, value)
        return True

    @callback
    def _on_source(self, event: Event[EventStateChangedData]) -> None:
        if self._apply_state(event.data["new_state"]):
            self._store.async_delay_save(self.state.to_dict, SAVE_DELAY)
            self._notify()

    @callback
    def _on_tick(self, _now: datetime) -> None:
        self._notify()

    def _schedule_reset(self) -> None:
        nxt = self.schedule.next_reset(dt_util.now())
        self._unsub_reset = async_track_point_in_time(self.hass, self._on_reset, nxt)

    @callback
    def _on_reset(self, now: datetime) -> None:
        cycle.roll_over(self.state, self.schedule, dt_util.as_local(now))
        _LOGGER.debug("%s new cycle from %s", self.entry.title, self.state.period_start)
        self._store.async_delay_save(self.state.to_dict, 0)
        self._schedule_reset()
        self._notify()

    @callback
    def _notify(self) -> None:
        async_dispatcher_send(self.hass, signal_update(self.entry.entry_id))

    def snapshot(self) -> cycle.Snapshot:
        return cycle.compute(self.state, self.schedule, dt_util.now(), self.rates, self.profile, MIN_DAYS)
