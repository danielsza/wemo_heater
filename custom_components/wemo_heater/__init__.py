"""The WeMo Heater integration."""
from __future__ import annotations

import logging
from typing import Any

import pywemo

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.CLIMATE]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up WeMo Heater from a config entry."""
    host = entry.data[CONF_HOST]
    
    # Connect to heater
    url = await hass.async_add_executor_job(
        pywemo.setup_url_for_address, host
    )
    
    if not url:
        raise ConfigEntryNotReady(f"Unable to connect to heater at {host}")
    
    try:
        device = await hass.async_add_executor_job(
            pywemo.discovery.device_from_description, url
        )
    except Exception as err:
        raise ConfigEntryNotReady(f"Unable to setup heater: {err}") from err
    
    if not isinstance(device, pywemo.Heater):
        _LOGGER.error("Device at %s is not a heater", host)
        return False
    
    # Store device
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = device
    
    # Setup platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    
    return unload_ok
