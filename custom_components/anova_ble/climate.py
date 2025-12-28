"""Climate platform for Anova BLE integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .ble_client import AnovaBLEClient
from .const import DOMAIN, STATUS_RUNNING, STATUS_TEMP, STATUS_TARGET_TEMP, STATUS_UNITS
from .sensor import AnovaDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Anova BLE climate entity from a config entry."""
    client: AnovaBLEClient = hass.data[DOMAIN][entry.entry_id]
    coordinator: AnovaDataUpdateCoordinator = hass.data[DOMAIN][
        f"{entry.entry_id}_coordinator"
    ]

    entities = [AnovaClimate(coordinator, client)]

    async_add_entities(entities)


class AnovaClimate(CoordinatorEntity, ClimateEntity):
    """Climate entity for Anova Precision Cooker."""

    _attr_hvac_modes = [HVACMode.HEAT, HVACMode.OFF]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_min_temp = 0.0
    _attr_max_temp = 100.0
    _attr_target_temperature_step = 0.1

    def __init__(
        self,
        coordinator: AnovaDataUpdateCoordinator,
        client: AnovaBLEClient,
    ) -> None:
        """Initialize the climate entity."""
        super().__init__(coordinator)
        self._client = client
        self._attr_unique_id = f"{client.address}_climate"
        self._attr_name = f"{client.name} Thermostat"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, client.address)},
            "name": client.name,
            "manufacturer": "Anova",
            "model": "Precision Cooker A2/A3",
        }

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        if self.coordinator.data is None:
            return None
        
        status = self.coordinator.data
        units = status.get(STATUS_UNITS, "C")
        temp = status.get(STATUS_TEMP)

        if temp is None:
            return None

        # Convert to Celsius if needed
        if units == "F":
            return (temp - 32) * 5 / 9
        return temp

    @property
    def target_temperature(self) -> float | None:
        """Return the target temperature."""
        if self.coordinator.data is None:
            return None
        
        status = self.coordinator.data
        units = status.get(STATUS_UNITS, "C")
        temp = status.get(STATUS_TARGET_TEMP)

        if temp is None:
            return None

        # Convert to Celsius if needed
        if units == "F":
            return (temp - 32) * 5 / 9
        return temp

    @property
    def hvac_mode(self) -> HVACMode:
        """Return the current HVAC mode."""
        if self.coordinator.data is None:
            return HVACMode.OFF
        
        running = self.coordinator.data.get(STATUS_RUNNING, False)
        return HVACMode.HEAT if running else HVACMode.OFF

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set the target temperature."""
        if (target_temp := kwargs.get(ATTR_TEMPERATURE)) is None:
            return

        # Get current units
        status = await self._client.get_status()
        units = status.get(STATUS_UNITS, "C")

        # Convert to device units if needed
        if units == "F":
            target_temp = (target_temp * 9 / 5) + 32

        await self._client.set_temperature(target_temp)
        await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set the HVAC mode."""
        if hvac_mode == HVACMode.HEAT:
            await self._client.start()
        elif hvac_mode == HVACMode.OFF:
            await self._client.stop()
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self) -> None:
        """Turn the entity on."""
        await self.async_set_hvac_mode(HVACMode.HEAT)

    async def async_turn_off(self) -> None:
        """Turn the entity off."""
        await self.async_set_hvac_mode(HVACMode.OFF)

