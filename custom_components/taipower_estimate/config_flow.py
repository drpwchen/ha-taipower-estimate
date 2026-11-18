"""UI 設定精靈：選電表 sensor、電價類別、抄表週期；之後可在「選項」改。"""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
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
HELPER_DOC_URL = "https://github.com/drpwchen/ha-taipower-estimate#只有功率-sensor-或用-emporia-vue"


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


POWER_UNITS = {"W", "kW", "MW", "GW", "mW"}
NON_KWH_ENERGY_UNITS = {"Wh", "MWh", "GWh", "mWh"}


def _source_field(default: str | None = None) -> dict:
    # 也列出功率（power）sensor：新手常只有「每分鐘平均功率」，選了以後給明確的下一步，
    # 而不是在清單裡找不到自己的 sensor。
    key = vol.Required(CONF_SOURCE, default=default) if default else vol.Required(CONF_SOURCE)
    return {key: selector.EntitySelector(
        selector.EntitySelectorConfig(domain="sensor", device_class=["energy", "power"]))}


VUE_PLATFORM = "emporia_vue"
# emporia_vue 的 unique_id：sensor.emporia_vue.<scale>.<device_gid>-<channel>；分鐘版的 scale 寫成 "instant"，
# 日／月版是 pyemvue 的 Scale 值（"1D"、"1MON"）。出處見 README「用 Emporia Vue 的人」。
VUE_MONTH, VUE_DAY, VUE_MINUTE = "1mon", "1d", "instant"
VUE_WHOLE_HOME_CHANNEL = "1,2,3"


def _vue_scale(entry: er.RegistryEntry | None) -> str | None:
    """emporia_vue 的 sensor 是哪個時間窗口（小寫）；不是 Vue 或認不出來回 None。"""
    if entry is None or entry.platform != VUE_PLATFORM or entry.domain != "sensor":
        return None
    parts = (entry.unique_id or "").split(".", 3)
    if len(parts) < 4 or parts[0] != "sensor" or parts[1] != VUE_PLATFORM:
        return None
    return parts[2].lower()


def vue_month_sibling(hass: HomeAssistant, entity_id: str) -> tuple[str | None, str | None]:
    """(這個 sensor 的 Vue 時間窗口, 同一迴路的 `_1mon` entity_id)；不是 Vue 的 sensor 回 (None, None)。"""
    reg = er.async_get(hass)
    entry = reg.async_get(entity_id)
    scale = _vue_scale(entry)
    if scale is None or entry.device_id is None:
        return scale, None
    for sib in er.async_entries_for_device(reg, entry.device_id):
        if _vue_scale(sib) == VUE_MONTH and not sib.disabled_by:
            return scale, sib.entity_id
    return scale, None


def vue_default_source(hass: HomeAssistant) -> str | None:
    """有 Emporia Vue 時，精靈預設的來源：整戶頻道（`1,2,3`）的 `_1mon`；只有一個符合才預設，不猜。"""
    months = [e for e in er.async_get(hass).entities.values()
              if _vue_scale(e) == VUE_MONTH and not e.disabled_by]
    whole = [e for e in months if e.unique_id.rsplit("-", 1)[-1] == VUE_WHOLE_HOME_CHANNEL]
    pool = whole or months
    return pool[0].entity_id if len(pool) == 1 else None


def source_error(hass: HomeAssistant, entity_id: str) -> tuple[str, str] | None:
    """選到的 sensor 不能直接當來源時回傳 (錯誤鍵, 建議的 entity_id 或空字串)；可以用或查不到屬性就回 None。

    錯誤鍵對應 translations 的 error。只擋「確定是錯的」：功率 sensor（要先用 Integration helper 積成 kWh）、
    單位是 Wh／MWh（程式不換算，會差 1000 倍）。Emporia Vue 另外：功率版（`_1min`）與每日版（`_1d`，一天歸零一次、
    漏的時間是月版的 30 倍）只要同迴路找得到 `_1mon`，就擋下並指名建議選哪個。
    沒有屬性（還沒有狀態）就放行，不阻擋設定。
    """
    scale, month = vue_month_sibling(hass, entity_id)
    if month and month != entity_id:
        if scale == VUE_DAY:
            return "source_vue_day", month
        if scale == VUE_MINUTE:
            return "source_vue_power", month
    st = hass.states.get(entity_id)
    if st is None:
        return None
    unit = st.attributes.get("unit_of_measurement")
    if st.attributes.get("device_class") == "power" or unit in POWER_UNITS:
        return "source_is_power", ""
    if unit in NON_KWH_ENERGY_UNITS:
        return "source_not_kwh", ""
    return None


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
        errors: dict[str, str] = {}
        suggestion = ""
        if user_input is not None:
            if err := source_error(self.hass, user_input[CONF_SOURCE]):
                errors["source"], suggestion = err
            else:
                await self.async_set_unique_id(user_input[CONF_SOURCE])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=TITLE, data=_normalize(user_input))

        # 預設來源：剛被擋時改填建議的 `_1mon`；第一次開表單時，有整戶頻道的 Vue `_1mon` 就預設它。
        default = suggestion or (user_input or {}).get(CONF_SOURCE) or vue_default_source(self.hass)
        schema = {
            **_source_field(default),
            **_cycle_fields(user_input or {}),
            vol.Optional(CONF_INITIAL_USED): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, step=0.1, unit_of_measurement="kWh",
                                              mode=selector.NumberSelectorMode.BOX)
            ),
        }
        return self.async_show_form(step_id="user", data_schema=vol.Schema(schema), errors=errors,
                                    description_placeholders={"integration_doc": HELPER_DOC_URL,
                                                              "suggestion": suggestion})

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return TaipowerOptionsFlow()


class TaipowerOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        suggestion = ""
        if user_input is not None:
            if err := source_error(self.hass, user_input[CONF_SOURCE]):
                errors["source"], suggestion = err
            else:
                return self.async_create_entry(data=_normalize(user_input))
        current = {**self.config_entry.data, **self.config_entry.options, **(user_input or {})}
        schema = {**_source_field(suggestion or current[CONF_SOURCE]), **_cycle_fields(current)}
        return self.async_show_form(step_id="init", data_schema=vol.Schema(schema), errors=errors,
                                    description_placeholders={"integration_doc": HELPER_DOC_URL,
                                                              "suggestion": suggestion})
