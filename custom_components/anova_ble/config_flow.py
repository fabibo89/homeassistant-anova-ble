"""Config flow for Anova BLE integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.data_entry_flow import FlowResult

from .ble_client import AnovaBLEClient
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class AnovaBLEConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Anova BLE."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovered_devices: dict[str, str] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        try:
            if user_input is not None:
                # Check if user wants manual entry
                if user_input.get("manual_entry"):
                    return await self.async_step_manual()
                
                # User has selected a device
                address = user_input.get(CONF_ADDRESS)
                if not address:
                    return await self.async_step_manual()
                
                name = self._discovered_devices.get(address, "Anova Precision Cooker")

                await self.async_set_unique_id(address, raise_on_progress=False)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=name,
                    data={CONF_ADDRESS: address, CONF_NAME: name},
                )

            # Discover devices (this will take ~15 seconds)
            _LOGGER.info("Discovering Anova devices...")
            
            try:
                devices = await AnovaBLEClient.discover_devices(timeout=15.0)
            except Exception as e:
                _LOGGER.error("Error during discovery: %s", e, exc_info=True)
                devices = []

            # Build device list
            self._discovered_devices = {}
            try:
                for device in devices:
                    if device and hasattr(device, 'address') and device.address:
                        device_name = device.name or f"Anova {device.address[-5:]}"
                        self._discovered_devices[device.address] = device_name
            except Exception as e:
                _LOGGER.error("Error building device list: %s", e, exc_info=True)
                self._discovered_devices = {}

            # If no devices found, offer manual entry
            if not self._discovered_devices:
                return await self.async_step_manual()

            # Show device selection form
            try:
                schema_dict = {
                    vol.Required(CONF_ADDRESS): vol.In(
                        {
                            address: f"{name} ({address})"
                            for address, name in self._discovered_devices.items()
                        }
                    ),
                    vol.Optional("manual_entry", default=False): bool
                }

                return self.async_show_form(
                    step_id="user",
                    data_schema=vol.Schema(schema_dict),
                )
            except Exception as e:
                _LOGGER.error("Error showing form: %s", e, exc_info=True)
                # Fallback to manual entry if form fails
                return await self.async_step_manual()
        except Exception as e:
            _LOGGER.error("Unexpected error in async_step_user: %s", e, exc_info=True)
            # Fallback to manual entry on any error
            return await self.async_step_manual()


    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle manual device entry."""
        errors = {}
        
        if user_input is not None:
            address = user_input[CONF_ADDRESS].strip().upper()
            name = user_input.get(CONF_NAME, "Anova Precision Cooker").strip()
            
            # Normalize MAC address (remove colons, dashes, spaces)
            address_clean = address.replace(":", "").replace("-", "").replace(" ", "")
            
            # Validate MAC address format (should be 12 hex characters)
            if not address_clean or len(address_clean) != 12:
                errors[CONF_ADDRESS] = "invalid_address"
            elif not all(c in "0123456789ABCDEF" for c in address_clean):
                errors[CONF_ADDRESS] = "invalid_address"
            else:
                # Format as standard MAC address (XX:XX:XX:XX:XX:XX)
                formatted_address = ":".join(
                    address_clean[i:i+2] for i in range(0, 12, 2)
                )
                
                await self.async_set_unique_id(formatted_address, raise_on_progress=False)
                self._abort_if_unique_id_configured()
                
                return self.async_create_entry(
                    title=name,
                    data={CONF_ADDRESS: formatted_address, CONF_NAME: name},
                )

        return self.async_show_form(
            step_id="manual",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): str,
                    vol.Optional(CONF_NAME, default="Anova Precision Cooker"): str,
                }
            ),
            errors=errors,
        )

    async def async_step_bluetooth(
        self, discovery_info: Any
    ) -> FlowResult:
        """Handle bluetooth discovery."""
        address = discovery_info.address
        name = discovery_info.name or "Anova Precision Cooker"

        await self.async_set_unique_id(address)
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title=name,
            data={CONF_ADDRESS: address, CONF_NAME: name},
        )

