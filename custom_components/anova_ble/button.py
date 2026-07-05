"""Button platform for Anova BLE integration."""
from __future__ import annotations

import logging
from collections.abc import Callable

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .ble_client import AnovaBLEClient
from .const import CONNECTION_STATE_CONNECTING, DOMAIN
from .sensor import AnovaDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Anova BLE buttons from a config entry."""
    client: AnovaBLEClient = hass.data[DOMAIN][entry.entry_id]
    coordinator: AnovaDataUpdateCoordinator = hass.data[DOMAIN][
        f"{entry.entry_id}_coordinator"
    ]

    async_add_entities([AnovaConnectButton(coordinator, client)])


class AnovaConnectButton(ButtonEntity):
    """Button to manually connect to the Anova device."""

    _attr_icon = "mdi:bluetooth-connect"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: AnovaDataUpdateCoordinator,
        client: AnovaBLEClient,
    ) -> None:
        """Initialize the connect button."""
        self._coordinator = coordinator
        self._client = client
        self._attr_unique_id = f"{client.address}_connect"
        self._attr_name = f"{client.name} Connect"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, client.address)},
            "name": client.name,
            "manufacturer": "Anova",
            "model": "Precision Cooker A2/A3",
        }
        self._remove_listener: Callable[[], None] | None = None

    @property
    def available(self) -> bool:
        """Connect button is always available."""
        return True

    async def async_added_to_hass(self) -> None:
        """Register for connection state updates."""
        await super().async_added_to_hass()
        self._remove_listener = self._client.register_state_listener(
            self._handle_state_update
        )

    async def async_will_remove_from_hass(self) -> None:
        """Unregister listener."""
        if self._remove_listener:
            self._remove_listener()
        await super().async_will_remove_from_hass()

    @callback
    def _handle_state_update(self) -> None:
        """Handle connection state changes."""
        self.async_write_ha_state()

    async def async_press(self) -> None:
        """Connect to the Anova device."""
        if self._client.connection_state == CONNECTION_STATE_CONNECTING:
            return

        _LOGGER.debug("Manual connect requested for %s", self._client.address)
        self.async_write_ha_state()

        success = await self._client.async_connect_manual()

        if success:
            await self._coordinator.async_request_refresh()

        self.async_write_ha_state()
