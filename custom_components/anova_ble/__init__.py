"""The Anova Precision Cooker BLE integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .ble_client import AnovaBLEClient
from .const import DOMAIN
from .sensor import AnovaDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.NUMBER, Platform.SWITCH, Platform.CLIMATE]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Anova BLE from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Create BLE client
    client = AnovaBLEClient(entry.data["address"], entry.data.get("name", "Anova"))
    
    # Try to connect, but don't fail setup if it doesn't work immediately
    # The coordinator will retry on first update
    try:
        await client.connect(retries=2, timeout=10.0)
    except Exception as e:
        _LOGGER.warning("Initial connection attempt failed: %s. Will retry on first update.", e)

    # Create coordinator (it will handle reconnection attempts)
    coordinator = AnovaDataUpdateCoordinator(hass, client)
    
    # Store client and coordinator
    hass.data[DOMAIN][entry.entry_id] = client
    hass.data[DOMAIN][f"{entry.entry_id}_coordinator"] = coordinator

    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    # Trigger initial refresh in background (non-blocking)
    hass.async_create_task(coordinator.async_config_entry_first_refresh())

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if entry.entry_id in hass.data[DOMAIN]:
        client = hass.data[DOMAIN][entry.entry_id]
        await client.disconnect()
        del hass.data[DOMAIN][entry.entry_id]

    coordinator_key = f"{entry.entry_id}_coordinator"
    if coordinator_key in hass.data[DOMAIN]:
        del hass.data[DOMAIN][coordinator_key]

    unload_ok = await hass.config_entries.async_unload_entry_platforms(entry, PLATFORMS)
    return unload_ok

