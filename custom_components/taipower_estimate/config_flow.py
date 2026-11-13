"""UI 設定精靈：選電表 sensor、電價類別、抄表週期；之後可在「選項」改。"""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_DAY,
    CONF_INITIAL_USED,
    CONF_MONTHS,
    CONF_PARITY,
    CONF_PROFILE,
    CONF_SOURCE,
    DEFAULT_DAY,
    DEFAULT_MONTHS,
    DEFAULT_PARITY,
    DEFAULT_PROFILE,
    DOMAIN,
    PARITIES,
    PROFILES,
)

TITLE = "台電電費估算"


def _cycle_fields(d: dict) -> dict:
    """電價類別與抄表週期（初次設定與選項共用）。"""
    return {
        vol.Required(CONF_PROFILE, default=d.get(CONF_PROFILE, DEFAULT_PROFILE)): selector.SelectSelector(
            selector.SelectSelectorConfig(options=PROFILES, translation_key="profile",
                                          mode=selector.SelectSelectorMode.LIST)
        ),
        vol.Required(CONF_MONTHS, default=str(d.get(CONF_MONTHS, DEFAULT_MONTHS))): selector.SelectSelector(
            selector.SelectSelectorConfig(options=["2", "1"], translation_key="months",
                                          mode=selector.SelectSelectorMode.LIST)
        ),
        vol.Required(CONF_DAY, default=d.get(CONF_DAY, DEFAULT_DAY)): selector.NumberSelector(
            selector.NumberSelectorConfig(min=1, max=31, step=1, mode=selector.NumberSelectorMode.BOX)
        ),
        vol.Required(CONF_PARITY, default=d.get(CONF_PARITY, DEFAULT_PARITY)): selector.SelectSelector(
            selector.SelectSelectorConfig(options=PARITIES, translation_key="parity",
                                          mode=selector.SelectSelectorMode.LIST)
        ),
    }


def _source_field(default: str | None = None) -> dict:
    key = vol.Required(CONF_SOURCE, default=default) if default else vol.Required(CONF_SOURCE)
    return {key: selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor", device_class="energy"))}


def _normalize(user_input: dict) -> dict:
    out = dict(user_input)
    out[CONF_MONTHS] = int(out[CONF_MONTHS])
    out[CONF_DAY] = int(out[CONF_DAY])
    if out.get(CONF_INITIAL_USED) is not None:
        out[CONF_INITIAL_USED] = float(out[CONF_INITIAL_USED])
    return out


class TaipowerConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_SOURCE])
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=TITLE, data=_normalize(user_input))

        schema = {
            **_source_field(),
            **_cycle_fields({}),
            vol.Optional(CONF_INITIAL_USED): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, step=0.1, unit_of_measurement="kWh",
                                              mode=selector.NumberSelectorMode.BOX)
            ),
        }
        return self.async_show_form(step_id="user", data_schema=vol.Schema(schema))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return TaipowerOptionsFlow()


class TaipowerOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=_normalize(user_input))
        current = {**self.config_entry.data, **self.config_entry.options}
        schema = {**_source_field(current[CONF_SOURCE]), **_cycle_fields(current)}
        return self.async_show_form(step_id="init", data_schema=vol.Schema(schema))
