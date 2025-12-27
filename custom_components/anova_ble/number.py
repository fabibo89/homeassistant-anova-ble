"""Number platform for Anova BLE integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .ble_client import AnovaBLEClient
from .const import DOMAIN, STATUS_TARGET_TEMP, STATUS_TIMER, STATUS_UNITS
from .sensor import AnovaDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Anova BLE number entities from a config entry."""
    client: AnovaBLEClient = hass.data[DOMAIN][entry.entry_id]
    coordinator: AnovaDataUpdateCoordinator = hass.data[DOMAIN][
        f"{entry.entry_id}_coordinator"
    ]

    entities = [
        AnovaTargetTemperatureNumber(coordinator, client),
        AnovaTimerNumber(coordinator, client),
    ]

    async_add_entities(entities)


class AnovaNumberBase(CoordinatorEntity, NumberEntity):
    """Base class for Anova number entities."""

    def __init__(
        self,
        coordinator: AnovaDataUpdateCoordinator,
        client: AnovaBLEClient,
        number_type: str,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator)
        self._client = client
        self._number_type = number_type
        self._attr_unique_id = f"{client.address}_{number_type}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, client.address)},
            "name": client.name,
            "manufacturer": "Anova",
            "model": "Precision Cooker A2/A3",
        }

    @property
    def name(self) -> str:
        """Return the name of the number entity."""
        return f"{self._client.name} {self._number_type.replace('_', ' ').title()}"


class AnovaTargetTemperatureNumber(AnovaNumberBase):
    """Number entity for setting target temperature."""

    def __init__(
        self,
        coordinator: AnovaDataUpdateCoordinator,
        client: AnovaBLEClient,
    ) -> None:
        """Initialize the target temperature number entity."""
        super().__init__(coordinator, client, "target_temperature")
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_mode = NumberMode.BOX
        self._attr_native_min_value = 0.0
        self._attr_native_max_value = 100.0
        self._attr_native_step = 0.1

    @property
    def native_value(self) -> float | None:
        """Return the current target temperature."""
        status = self.coordinator.data
        units = status.get(STATUS_UNITS, "C")
        temp = status.get(STATUS_TARGET_TEMP)

        if temp is None:
            return None

        # Convert to Celsius if needed
        if units == "F":
            return (temp - 32) * 5 / 9
        return temp

    async def async_set_native_value(self, value: float) -> None:
        """Set the target temperature."""
        # Get current units
        status = await self._client.get_status()
        units = status.get(STATUS_UNITS, "C")

        # Convert to device units if needed
        if units == "F":
            value = (value * 9 / 5) + 32

        await self._client.set_temperature(value)
        await self.coordinator.async_request_refresh()


class AnovaTimerNumber(AnovaNumberBase):
    """Number entity for setting timer."""

    def __init__(
        self,
        coordinator: AnovaDataUpdateCoordinator,
        client: AnovaBLEClient,
    ) -> None:
        """Initialize the timer number entity."""
        super().__init__(coordinator, client, "timer")
        self._attr_native_unit_of_measurement = UnitOfTime.MINUTES
        self._attr_mode = NumberMode.BOX
        self._attr_native_min_value = 0
        self._attr_native_max_value = 999
        self._attr_native_step = 1

    @property
    def native_value(self) -> int | None:
        """Return the current timer value."""
        return self.coordinator.data.get(STATUS_TIMER)

    async def async_set_native_value(self, value: float) -> None:
        """Set the timer value."""
        await self._client.set_timer(int(value))
        await self.coordinator.async_request_refresh()

