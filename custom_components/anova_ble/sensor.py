"""Sensor platform for Anova BLE integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .ble_client import AnovaBLEClient
from .const import DOMAIN, STATUS_RUNNING, STATUS_TEMP, STATUS_TIMER, STATUS_UNITS

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Anova BLE sensors from a config entry."""
    client: AnovaBLEClient = hass.data[DOMAIN][entry.entry_id]
    coordinator: AnovaDataUpdateCoordinator = hass.data[DOMAIN][
        f"{entry.entry_id}_coordinator"
    ]

    sensors = [
        AnovaTemperatureSensor(coordinator, client),
        AnovaTargetTemperatureSensor(coordinator, client),
        AnovaTimerSensor(coordinator, client),
        AnovaRunningSensor(coordinator, client),
        AnovaUnitsSensor(coordinator, client),
    ]

    async_add_entities(sensors)


class AnovaDataUpdateCoordinator(DataUpdateCoordinator):
    """Coordinator for updating Anova device data."""

    def __init__(self, hass: HomeAssistant, client: AnovaBLEClient) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=10,  # Update every 10 seconds
        )
        self.client = client

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the device."""
        # Ensure we're connected
        if not self.client.is_connected:
            _LOGGER.info("Not connected, attempting to reconnect...")
            await self.client.connect(retries=1, timeout=5.0)
        
        if not self.client.is_connected:
            _LOGGER.debug("Still not connected, returning cached status")
            return self.client.status
        
        try:
            return await self.client.get_status()
        except Exception as e:
            _LOGGER.warning("Error getting status: %s. Returning cached status.", e)
            # Mark as disconnected so we retry connection next time
            self.client._connected = False
            return self.client.status


class AnovaSensorBase(CoordinatorEntity, SensorEntity):
    """Base class for Anova sensors."""

    def __init__(
        self,
        coordinator: AnovaDataUpdateCoordinator,
        client: AnovaBLEClient,
        sensor_type: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._client = client
        self._sensor_type = sensor_type
        self._attr_unique_id = f"{client.address}_{sensor_type}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, client.address)},
            "name": client.name,
            "manufacturer": "Anova",
            "model": "Precision Cooker A2/A3",
        }

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return f"{self._client.name} {self._sensor_type.replace('_', ' ').title()}"


class AnovaTemperatureSensor(AnovaSensorBase):
    """Sensor for current water temperature."""

    def __init__(
        self,
        coordinator: AnovaDataUpdateCoordinator,
        client: AnovaBLEClient,
    ) -> None:
        """Initialize the temperature sensor."""
        super().__init__(coordinator, client, "water_temperature")
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> float | None:
        """Return the current temperature."""
        status = self.coordinator.data
        units = status.get(STATUS_UNITS, "C")
        temp = status.get(STATUS_TEMP)

        if temp is None:
            return None

        # Convert to Celsius if needed
        if units == "F":
            return (temp - 32) * 5 / 9
        return temp


class AnovaTargetTemperatureSensor(AnovaSensorBase):
    """Sensor for target temperature."""

    def __init__(
        self,
        coordinator: AnovaDataUpdateCoordinator,
        client: AnovaBLEClient,
    ) -> None:
        """Initialize the target temperature sensor."""
        super().__init__(coordinator, client, "target_temperature")
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> float | None:
        """Return the target temperature."""
        status = self.coordinator.data
        units = status.get(STATUS_UNITS, "C")
        temp = status.get(STATUS_TARGET_TEMP)

        if temp is None:
            return None

        # Convert to Celsius if needed
        if units == "F":
            return (temp - 32) * 5 / 9
        return temp


class AnovaTimerSensor(AnovaSensorBase):
    """Sensor for remaining timer."""

    def __init__(
        self,
        coordinator: AnovaDataUpdateCoordinator,
        client: AnovaBLEClient,
    ) -> None:
        """Initialize the timer sensor."""
        super().__init__(coordinator, client, "timer")
        self._attr_native_unit_of_measurement = UnitOfTime.MINUTES
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> int | None:
        """Return the remaining timer in minutes."""
        return self.coordinator.data.get(STATUS_TIMER)


class AnovaRunningSensor(AnovaSensorBase):
    """Sensor for running state."""

    def __init__(
        self,
        coordinator: AnovaDataUpdateCoordinator,
        client: AnovaBLEClient,
    ) -> None:
        """Initialize the running sensor."""
        super().__init__(coordinator, client, "running")

    @property
    def native_value(self) -> str:
        """Return the running state."""
        running = self.coordinator.data.get(STATUS_RUNNING, False)
        return "on" if running else "off"


class AnovaUnitsSensor(AnovaSensorBase):
    """Sensor for temperature units."""

    def __init__(
        self,
        coordinator: AnovaDataUpdateCoordinator,
        client: AnovaBLEClient,
    ) -> None:
        """Initialize the units sensor."""
        super().__init__(coordinator, client, "units")

    @property
    def native_value(self) -> str | None:
        """Return the temperature units."""
        return self.coordinator.data.get(STATUS_UNITS, "C")

