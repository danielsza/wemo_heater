"""Support for WeMo heater devices."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
    PRESET_NONE,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .heater_device import Heater, Mode, Temperature

_LOGGER = logging.getLogger(__name__)

# Map WeMo modes to HVAC modes (for basic on/off/heat)
WEMO_MODE_TO_HVAC = {
    Mode.Off: HVACMode.OFF,
    Mode.Frostprotect: HVACMode.HEAT,
    Mode.Low: HVACMode.HEAT,
    Mode.High: HVACMode.HEAT,
    Mode.Eco: HVACMode.HEAT,
}

# Preset mode names
PRESET_FROST_PROTECT = "Frost Protect"
PRESET_LOW = "Low"
PRESET_HIGH = "High"
PRESET_ECO = "Eco"

# Map preset modes to WeMo modes
PRESET_TO_WEMO_MODE = {
    PRESET_FROST_PROTECT: Mode.Frostprotect,
    PRESET_LOW: Mode.Low,
    PRESET_HIGH: Mode.High,
    PRESET_ECO: Mode.Eco,
}

# Map WeMo modes to preset modes
WEMO_MODE_TO_PRESET = {
    Mode.Frostprotect: PRESET_FROST_PROTECT,
    Mode.Low: PRESET_LOW,
    Mode.High: PRESET_HIGH,
    Mode.Eco: PRESET_ECO,
    Mode.Off: PRESET_NONE,
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up WeMo heater climate entities."""
    device = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities([WemoHeater(device)])


class WemoHeater(ClimateEntity):
    """Representation of a WeMo heater."""

    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
    _attr_preset_modes = [
        PRESET_FROST_PROTECT,
        PRESET_LOW,
        PRESET_HIGH,
        PRESET_ECO,
    ]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.PRESET_MODE
        | ClimateEntityFeature.TURN_OFF
        | ClimateEntityFeature.TURN_ON
    )
    _enable_turn_on_off_backwards_compatibility = False

    def __init__(self, device: Heater) -> None:
        """Initialize the WeMo heater."""
        self._device = device
        self._attr_name = device.name
        self._attr_unique_id = device.serial_number
        self._attr_temperature_unit = (
            UnitOfTemperature.CELSIUS
            if device.temperature_unit == Temperature.Celsius
            else UnitOfTemperature.FAHRENHEIT
        )

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        return self._device.current_temperature

    @property
    def target_temperature(self) -> float | None:
        """Return the temperature we try to reach."""
        return self._device.target_temperature

    @property
    def hvac_mode(self) -> HVACMode:
        """Return current HVAC mode."""
        return WEMO_MODE_TO_HVAC.get(self._device.mode, HVACMode.OFF)

    @property
    def hvac_action(self) -> HVACAction:
        """Return current HVAC action."""
        if self._device.mode == Mode.Off:
            return HVACAction.OFF
        if self._device.heating_status:
            return HVACAction.HEATING
        return HVACAction.IDLE

    @property
    def preset_mode(self) -> str | None:
        """Return current preset mode."""
        return WEMO_MODE_TO_PRESET.get(self._device.mode, PRESET_NONE)

    @property
    def min_temp(self) -> float:
        """Return the minimum temperature."""
        if self._attr_temperature_unit == UnitOfTemperature.CELSIUS:
            return 5.0
        return 41.0

    @property
    def max_temp(self) -> float:
        """Return the maximum temperature."""
        if self._attr_temperature_unit == UnitOfTemperature.CELSIUS:
            return 35.0
        return 95.0

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is None:
            return

        await self.hass.async_add_executor_job(
            self._device.set_target_temperature, temperature
        )
        self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new target HVAC mode."""
        if hvac_mode == HVACMode.OFF:
            await self.hass.async_add_executor_job(self._device.set_mode, Mode.Off)
        elif hvac_mode == HVACMode.HEAT:
            # When turning on heating, use Eco mode as default
            await self.hass.async_add_executor_job(self._device.set_mode, Mode.Eco)
        else:
            _LOGGER.warning("Unsupported HVAC mode: %s", hvac_mode)
            return
        
        self.async_write_ha_state()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set new preset mode."""
        if preset_mode not in PRESET_TO_WEMO_MODE:
            _LOGGER.warning("Unsupported preset mode: %s", preset_mode)
            return

        wemo_mode = PRESET_TO_WEMO_MODE[preset_mode]
        await self.hass.async_add_executor_job(self._device.set_mode, wemo_mode)
        self.async_write_ha_state()

    async def async_update(self) -> None:
        """Update the entity."""
        await self.hass.async_add_executor_job(self._device.update_attributes)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return device specific state attributes."""
        return {
            "heater_mode": self._device.mode_string,
            "auto_off_time": self._device.auto_off_time,
            "time_remaining": self._device.time_remaining,
        }
