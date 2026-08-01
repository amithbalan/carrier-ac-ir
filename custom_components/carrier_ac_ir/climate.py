from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.components.climate.const import (
    ATTR_PRESET_MODE,
    FAN_AUTO,
    PRESET_BOOST,
    PRESET_NONE,
    SWING_OFF,
    SWING_VERTICAL,
)
from homeassistant.components.infrared import async_send_command
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_TEMPERATURE,
    CONF_NAME,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfTemperature,
)
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.restore_state import RestoreEntity

from .const import CONF_EMITTER, CONF_TEMPERATURE_SENSOR, DEFAULT_NAME, DOMAIN
from .midea import (
    FAN_BYTE,
    MAX_TEMP,
    MIN_TEMP,
    SWING,
    TURBO,
    CarrierCommand,
    build_command_bytes,
    build_special_bytes,
    build_timings,
    encode,
)

SWING_MODES = [SWING_OFF, SWING_VERTICAL]
PRESET_MODES = [PRESET_NONE, PRESET_BOOST]

DEFAULT_TEMPERATURE = 24
DEFAULT_ACTIVE_MODE = HVACMode.COOL

# Carrier Midea India units are cooling-only — their remotes have no heat button.
# MODE_NIBBLE still carries the heat encoding for units that do offer it, but it
# is not exposed here.
EXPOSED_MODES = ("cool", "dry", "auto", "fan_only")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([CarrierAcClimate(entry)])


class CarrierAcClimate(ClimateEntity, RestoreEntity):
    """Carrier (Carrier Midea India) AC driven by raw Midea IR frames.

    The Midea frame is stateful: mode, temperature and fan all travel in every
    transmission, so any single change re-sends the complete state.
    """

    _attr_has_entity_name = True
    _attr_name = None
    _attr_should_poll = False
    _attr_assumed_state = True
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 1
    _attr_min_temp = MIN_TEMP
    _attr_max_temp = MAX_TEMP
    _attr_fan_modes = list(FAN_BYTE)
    _attr_swing_modes = SWING_MODES
    _attr_preset_modes = PRESET_MODES
    _attr_hvac_modes = [HVACMode.OFF] + [HVACMode(mode) for mode in EXPOSED_MODES]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.SWING_MODE
        | ClimateEntityFeature.PRESET_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )

    def __init__(self, entry: ConfigEntry) -> None:
        self._emitter_id: str = entry.data[CONF_EMITTER]
        self._sensor_id: str | None = entry.options.get(
            CONF_TEMPERATURE_SENSOR, entry.data.get(CONF_TEMPERATURE_SENSOR)
        )
        self._attr_unique_id = entry.entry_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data.get(CONF_NAME, DEFAULT_NAME),
            manufacturer="Carrier",
            model="Air Conditioner (IR)",
        )
        self._attr_hvac_mode = HVACMode.OFF
        self._attr_target_temperature: float = DEFAULT_TEMPERATURE
        self._attr_fan_mode = FAN_AUTO
        self._attr_swing_mode = SWING_OFF
        self._attr_preset_mode = PRESET_NONE
        self._last_active_mode = DEFAULT_ACTIVE_MODE

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        if self._sensor_id:
            self.async_on_remove(
                async_track_state_change_event(
                    self.hass, [self._sensor_id], self._async_sensor_changed
                )
            )
            self._read_sensor()

        if (last_state := await self.async_get_last_state()) is None:
            return

        try:
            self._attr_hvac_mode = HVACMode(last_state.state)
        except ValueError:
            pass
        if self._attr_hvac_mode != HVACMode.OFF:
            self._last_active_mode = self._attr_hvac_mode

        if (temperature := last_state.attributes.get(ATTR_TEMPERATURE)) is not None:
            self._attr_target_temperature = temperature
        if (fan_mode := last_state.attributes.get("fan_mode")) in FAN_BYTE:
            self._attr_fan_mode = fan_mode
        if (swing_mode := last_state.attributes.get("swing_mode")) in SWING_MODES:
            self._attr_swing_mode = swing_mode
        if (preset := last_state.attributes.get(ATTR_PRESET_MODE)) in PRESET_MODES:
            self._attr_preset_mode = preset

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        self._attr_hvac_mode = hvac_mode
        if hvac_mode != HVACMode.OFF:
            self._last_active_mode = hvac_mode
        await self._async_transmit()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is not None:
            self._attr_target_temperature = temperature
        if (hvac_mode := kwargs.get(ATTR_HVAC_MODE)) is not None:
            self._attr_hvac_mode = HVACMode(hvac_mode)
            if self._attr_hvac_mode != HVACMode.OFF:
                self._last_active_mode = self._attr_hvac_mode
        await self._async_transmit()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        self._attr_fan_mode = fan_mode
        await self._async_transmit()

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        """Swing is a toggle, so only transmit when the value actually flips."""
        if swing_mode == self._attr_swing_mode:
            return
        self._attr_swing_mode = swing_mode
        await self._async_send(build_command_bytes(SWING))

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Boost maps to the remote's Turbo button, which is also a toggle."""
        if preset_mode == self._attr_preset_mode:
            return
        self._attr_preset_mode = preset_mode
        await self._async_send(build_special_bytes(TURBO))

    async def async_turn_on(self) -> None:
        await self.async_set_hvac_mode(self._last_active_mode)

    async def async_turn_off(self) -> None:
        await self.async_set_hvac_mode(HVACMode.OFF)

    @callback
    def _read_sensor(self) -> None:
        state = self.hass.states.get(self._sensor_id)
        if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            return
        try:
            self._attr_current_temperature = float(state.state)
        except ValueError:
            pass

    async def _async_sensor_changed(self, event: Event[EventStateChangedData]) -> None:
        previous = self._attr_current_temperature
        self._read_sensor()
        if self._attr_current_temperature != previous:
            self.async_write_ha_state()

    async def _async_send(self, frame: list[int]) -> None:
        """Transmit one six-byte frame and publish the assumed state."""
        await async_send_command(
            self.hass, self._emitter_id, CarrierCommand(build_timings(frame))
        )
        self.async_write_ha_state()

    async def _async_transmit(self) -> None:
        timings = encode(
            power=self._attr_hvac_mode != HVACMode.OFF,
            mode=self._attr_hvac_mode.value,
            temperature=self._attr_target_temperature,
            fan=self._attr_fan_mode or FAN_AUTO,
        )
        await async_send_command(self.hass, self._emitter_id, CarrierCommand(timings))
        self.async_write_ha_state()
