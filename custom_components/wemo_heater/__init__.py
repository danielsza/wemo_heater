"""The WeMo Heater integration."""
from __future__ import annotations

import logging

import pywemo

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN
from .heater_device import Heater

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.CLIMATE]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up WeMo Heater from a config entry."""
    host = entry.data[CONF_HOST]
    
    # Connect to heater using our bundled Heater class
    url = await hass.async_add_executor_job(
        pywemo.setup_url_for_address, host
    )
    
    if not url:
        raise ConfigEntryNotReady(f"Unable to connect to heater at {host}")
    
    try:
        # Create heater instance using our bundled class
        device = await hass.async_add_executor_job(Heater, url)
    except Exception as err:
        _LOGGER.error("Error setting up heater: %s", err, exc_info=True)
        raise ConfigEntryNotReady(f"Unable to setup heater: {err}") from err
    
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
