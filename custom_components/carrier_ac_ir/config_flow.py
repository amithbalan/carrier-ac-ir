from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import CONF_EMITTER, CONF_TEMPERATURE_SENSOR, DEFAULT_NAME, DOMAIN

_SENSOR_SELECTOR = selector.EntitySelector(
    selector.EntitySelectorConfig(domain="sensor", device_class="temperature")
)


class CarrierAcConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 2

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> CarrierAcOptionsFlow:
        return CarrierAcOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_EMITTER])
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=user_input[CONF_NAME], data=user_input)

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
                vol.Required(CONF_EMITTER): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="infrared", device_class="emitter"
                    )
                ),
                vol.Optional(CONF_TEMPERATURE_SENSOR): _SENSOR_SELECTOR,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)


class CarrierAcOptionsFlow(OptionsFlow):
    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current = self.config_entry.options.get(
            CONF_TEMPERATURE_SENSOR,
            self.config_entry.data.get(CONF_TEMPERATURE_SENSOR),
        )
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_TEMPERATURE_SENSOR,
                    description={"suggested_value": current},
                ): _SENSOR_SELECTOR
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
