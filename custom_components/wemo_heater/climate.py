"""Support for WeMo heater devices."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.components.climate import (
    PRESET_ECO,
    PRESET_NONE,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .heater_device import Heater, Mode, Temperature

_LOGGER = logging.getLogger(__name__)

# Custom preset names
PRESET_HIGH = "high"
PRESET_LOW = "low"
PRESET_FROSTPROTECT = "frost_protect"

# Map heater modes to HVAC modes (simplified to just on/off)
WEMO_MODE_TO_HVAC = {
    Mode.Off: HVACMode.OFF,
    Mode.Frostprotect: HVACMode.HEAT,
    Mode.Low: HVACMode.HEAT,
    Mode.High: HVACMode.HEAT,
    Mode.Eco: HVACMode.HEAT,
}

# Map heater modes to preset modes
WEMO_MODE_TO_PRESET = {
    Mode.Off: PRESET_NONE,
    Mode.Frostprotect: PRESET_FROSTPROTECT,
    Mode.Low: PRESET_LOW,
    Mode.High: PRESET_HIGH,
    Mode.Eco: PRESET_ECO,
}

# Reverse mapping for setting modes
PRESET_TO_WEMO_MODE = {
    PRESET_NONE: Mode.Off,
    PRESET_FROSTPROTECT: Mode.Frostprotect,
    PRESET_LOW: Mode.Low,
    PRESET_HIGH: Mode.High,
    PRESET_ECO: Mode.Eco,
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
        PRESET_HIGH,
        PRESET_LOW,
        PRESET_ECO,
        PRESET_FROSTPROTECT,
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
        # Temperature step is 1.0 degree (full degrees only)
        self._attr_target_temperature_step = 1.0

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
        """Return the current preset mode."""
        return WEMO_MODE_TO_PRESET.get(self._device.mode, PRESET_NONE)

    @property
    def min_temp(self) -> float:
        """Return the minimum temperature."""
        # Frost protect mode: 4°C, Normal modes: 16°C
        if self._device.mode == Mode.Frostprotect:
            if self._attr_temperature_unit == UnitOfTemperature.CELSIUS:
                return 4.0
            return 39.0  # ~4°C in Fahrenheit
        
        # Normal heating modes
        if self._attr_temperature_unit == UnitOfTemperature.CELSIUS:
            return 16.0
        return 61.0  # ~16°C in Fahrenheit

    @property
    def max_temp(self) -> float:
        """Return the maximum temperature."""
        # All modes: 29°C maximum
        if self._attr_temperature_unit == UnitOfTemperature.CELSIUS:
            return 29.0
        return 84.0  # ~29°C in Fahrenheit

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is None:
            return

        _LOGGER.debug("Setting temperature to: %s", temperature)
        
        # Set temperature on device
        await self.hass.async_add_executor_job(
            self._device.set_target_temperature, temperature
        )
        
        # Give device time to process the command
        await asyncio.sleep(0.5)
        
        # Update from device to get confirmed value
        await self.hass.async_add_executor_job(self._device.update_attributes)
        
        _LOGGER.debug("Temperature confirmed as: %s", self._device.target_temperature)
        
        # Update HA state
        self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new target HVAC mode."""
        if hvac_mode == HVACMode.OFF:
            await self.hass.async_add_executor_job(self._device.set_mode, Mode.Off)
        elif hvac_mode == HVACMode.HEAT:
            # When turning on, default to High mode
            await self.hass.async_add_executor_job(self._device.set_mode, Mode.High)
        else:
            _LOGGER.warning("Unsupported HVAC mode: %s", hvac_mode)
            return

        # Give device time to process
        await asyncio.sleep(0.3)
        
        # Wait for device to update
        await self.hass.async_add_executor_job(self._device.update_attributes)
        self.async_write_ha_state()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set new preset mode."""
        if preset_mode not in PRESET_TO_WEMO_MODE:
            _LOGGER.warning("Unsupported preset mode: %s", preset_mode)
            return

        wemo_mode = PRESET_TO_WEMO_MODE[preset_mode]
        await self.hass.async_add_executor_job(self._device.set_mode, wemo_mode)
        
        # Give device time to process
        await asyncio.sleep(0.3)
        
        # Wait for device to update
        await self.hass.async_add_executor_job(self._device.update_attributes)
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
