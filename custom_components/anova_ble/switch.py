"""Switch platform for Anova BLE integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .ble_client import AnovaBLEClient
from .const import DOMAIN, STATUS_RUNNING
from .sensor import AnovaDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Anova BLE switch entities from a config entry."""
    client: AnovaBLEClient = hass.data[DOMAIN][entry.entry_id]
    coordinator: AnovaDataUpdateCoordinator = hass.data[DOMAIN][
        f"{entry.entry_id}_coordinator"
    ]

    entities = [AnovaRunningSwitch(coordinator, client)]

    async_add_entities(entities)


class AnovaSwitchBase(CoordinatorEntity, SwitchEntity):
    """Base class for Anova switch entities."""

    def __init__(
        self,
        coordinator: AnovaDataUpdateCoordinator,
        client: AnovaBLEClient,
        switch_type: str,
    ) -> None:
        """Initialize the switch entity."""
        super().__init__(coordinator)
        self._client = client
        self._switch_type = switch_type
        self._attr_unique_id = f"{client.address}_{switch_type}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, client.address)},
            "name": client.name,
            "manufacturer": "Anova",
            "model": "Precision Cooker A2/A3",
        }

    @property
    def name(self) -> str:
        """Return the name of the switch."""
        return f"{self._client.name} {self._switch_type.replace('_', ' ').title()}"


class AnovaRunningSwitch(AnovaSwitchBase):
    """Switch entity for starting/stopping the cooker."""

    def __init__(
        self,
        coordinator: AnovaDataUpdateCoordinator,
        client: AnovaBLEClient,
    ) -> None:
        """Initialize the running switch."""
        super().__init__(coordinator, client, "running")

    @property
    def is_on(self) -> bool:
        """Return if the cooker is running."""
        return self.coordinator.data.get(STATUS_RUNNING, False)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the cooker."""
        await self._client.start()
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the cooker."""
        await self._client.stop()
        await self.coordinator.async_request_refresh()

