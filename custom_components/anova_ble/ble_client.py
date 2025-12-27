"""BLE client for Anova Precision Cooker A2/A3."""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice

from .const import (
    ANOVA_CHARACTERISTIC_UUID,
    ANOVA_DEVICE_NAME_PREFIX,
    ANOVA_SERVICE_UUID,
    CMD_GET_STATUS,
    CMD_SET_TEMP,
    CMD_SET_TIMER,
    CMD_START,
    CMD_STOP,
    CMD_UNITS_C,
    CMD_UNITS_F,
    STATUS_RUNNING,
    STATUS_TARGET_TEMP,
    STATUS_TEMP,
    STATUS_TIMER,
    STATUS_UNITS,
)

_LOGGER = logging.getLogger(__name__)


class AnovaBLEClient:
    """Handle BLE communication with Anova Precision Cooker."""

    def __init__(self, address: str, name: str = "Anova") -> None:
        """Initialize the Anova BLE client."""
        # Normalize address
        address_upper = address.upper().replace("-", ":")
        self._address = address_upper
        self._name = name
        self._client: BleakClient | None = None
        self._lock = asyncio.Lock()
        self._status: dict[str, Any] = {}
        self._connected = False
        self._response_event: asyncio.Event | None = None
        self._response_data: str | None = None
        
        # Warn if placeholder address
        if "AA:BB:CC:DD:EE:FF" in address_upper or "00:00:00:00:00:00" in address_upper:
            _LOGGER.warning(
                "Placeholder MAC address detected: %s. Please use the actual MAC address of your Anova device.",
                address
            )

    @property
    def is_connected(self) -> bool:
        """Return connection status."""
        return self._connected and self._client is not None and self._client.is_connected

    @property
    def address(self) -> str:
        """Return device address."""
        return self._address

    @property
    def name(self) -> str:
        """Return device name."""
        return self._name

    def _notification_handler(self, sender: int, data: bytearray) -> None:
        """Handle notifications from the device."""
        try:
            response = data.decode("utf-8").strip()
            _LOGGER.debug("Received notification: %s", response)
            self._response_data = response
            if self._response_event:
                self._response_event.set()
        except Exception as e:
            _LOGGER.error("Error handling notification: %s", e)

    async def connect(self, retries: int = 3, timeout: float = 10.0) -> bool:
        """Connect to the Anova device with retry logic."""
        if self.is_connected:
            return True
        
        for attempt in range(1, retries + 1):
            try:
                _LOGGER.info("Connecting to Anova device at %s (attempt %d/%d)...", 
                            self._address, attempt, retries)
                
                # Check if device is available first
                try:
                    scanner = BleakScanner()
                    await scanner.start()
                    await asyncio.sleep(2)  # Brief scan
                    devices = await scanner.get_discovered_devices()
                    await scanner.stop()
                    
                    # Check if our device is in the list
                    found = any(d.address.upper() == self._address.upper() for d in devices)
                    if not found:
                        _LOGGER.warning("Device %s not found in scan, trying direct connection anyway...", 
                                      self._address)
                except Exception as scan_error:
                    _LOGGER.debug("Could not scan for device: %s", scan_error)
                
                # Try to connect
                self._client = BleakClient(self._address, timeout=timeout)
                await asyncio.wait_for(self._client.connect(), timeout=timeout)
                
                # Enable notifications
                try:
                    await self._client.start_notify(
                        ANOVA_CHARACTERISTIC_UUID, self._notification_handler
                    )
                except Exception as notify_error:
                    _LOGGER.warning("Could not enable notifications: %s. Continuing anyway...", notify_error)
                
                self._connected = True
                _LOGGER.info("Successfully connected to Anova device at %s", self._address)
                
                # Try to get initial status (don't fail if this doesn't work)
                try:
                    await asyncio.wait_for(self.get_status(), timeout=5.0)
                except Exception as status_error:
                    _LOGGER.warning("Could not get initial status: %s", status_error)
                
                return True
                
            except asyncio.TimeoutError:
                _LOGGER.warning("Connection timeout (attempt %d/%d)", attempt, retries)
                if attempt < retries:
                    await asyncio.sleep(2)  # Wait before retry
            except Exception as e:
                _LOGGER.warning("Connection attempt %d/%d failed: %s", attempt, retries, e)
                if attempt < retries:
                    await asyncio.sleep(2)  # Wait before retry
                else:
                    _LOGGER.error("Failed to connect to Anova device after %d attempts: %s", retries, e)
        
        self._connected = False
        return False

    async def disconnect(self) -> None:
        """Disconnect from the Anova device."""
        if self._client and self._client.is_connected:
            try:
                await self._client.stop_notify(ANOVA_CHARACTERISTIC_UUID)
            except Exception:
                pass
            await self._client.disconnect()
        self._connected = False
        _LOGGER.info("Disconnected from Anova device")

    async def _send_command(self, command: str) -> str | None:
        """Send a command to the device and wait for response."""
        if not self.is_connected:
            _LOGGER.error("Not connected to device")
            return None

        async with self._lock:
            try:
                # Create event for response
                self._response_event = asyncio.Event()
                self._response_data = None

                # Send command
                _LOGGER.debug("Sending command: %s", command)
                await self._client.write_gatt_char(
                    ANOVA_CHARACTERISTIC_UUID, command.encode("utf-8"), response=True
                )

                # Wait for notification response
                try:
                    await asyncio.wait_for(self._response_event.wait(), timeout=5.0)
                    response = self._response_data
                    return response
                except asyncio.TimeoutError:
                    _LOGGER.warning("Timeout waiting for response to command: %s", command)
                    # Fallback: try reading directly
                    try:
                        response = await asyncio.wait_for(
                            self._client.read_gatt_char(ANOVA_CHARACTERISTIC_UUID),
                            timeout=2.0,
                        )
                        return response.decode("utf-8").strip()
                    except Exception:
                        return None
            except Exception as e:
                _LOGGER.error("Error sending command %s: %s", command, e)
                return None
            finally:
                self._response_event = None
                self._response_data = None

    def _parse_status(self, response: str) -> dict[str, Any]:
        """Parse status response from device."""
        status: dict[str, Any] = {}

        # Parse temperature
        temp_match = re.search(r"temp[:\s]+([\d.]+)", response, re.IGNORECASE)
        if temp_match:
            try:
                status[STATUS_TEMP] = float(temp_match.group(1))
            except ValueError:
                pass

        # Parse target temperature
        target_match = re.search(r"target[:\s]+([\d.]+)", response, re.IGNORECASE)
        if target_match:
            try:
                status[STATUS_TARGET_TEMP] = float(target_match.group(1))
            except ValueError:
                pass

        # Parse timer
        timer_match = re.search(r"timer[:\s]+(\d+)", response, re.IGNORECASE)
        if timer_match:
            try:
                status[STATUS_TIMER] = int(timer_match.group(1))
            except ValueError:
                pass

        # Parse running state
        if re.search(r"running|on", response, re.IGNORECASE):
            status[STATUS_RUNNING] = True
        elif re.search(r"stopped|off|idle", response, re.IGNORECASE):
            status[STATUS_RUNNING] = False

        # Parse units
        if re.search(r"units[:\s]+[CF]", response, re.IGNORECASE):
            if "F" in response.upper():
                status[STATUS_UNITS] = "F"
            else:
                status[STATUS_UNITS] = "C"

        return status

    async def get_status(self) -> dict[str, Any]:
        """Get current status from device."""
        # Ensure connection
        if not self.is_connected:
            _LOGGER.debug("Not connected, attempting to reconnect...")
            await self.connect(retries=1, timeout=5.0)
        
        if not self.is_connected:
            _LOGGER.debug("Cannot get status: not connected")
            return self._status.copy()
        
        response = await self._send_command(CMD_GET_STATUS)
        if response:
            self._status = self._parse_status(response)
            _LOGGER.debug("Status: %s", self._status)
        return self._status.copy()

    @property
    def status(self) -> dict[str, Any]:
        """Return cached status."""
        return self._status.copy()

    async def set_temperature(self, temperature: float) -> bool:
        """Set target temperature."""
        command = f"{CMD_SET_TEMP}{temperature:.1f}"
        response = await self._send_command(command)
        if response:
            await self.get_status()  # Refresh status
            return True
        return False

    async def set_timer(self, minutes: int) -> bool:
        """Set timer in minutes."""
        command = f"{CMD_SET_TIMER}{minutes}"
        response = await self._send_command(command)
        if response:
            await self.get_status()  # Refresh status
            return True
        return False

    async def start(self) -> bool:
        """Start the cooker."""
        response = await self._send_command(CMD_START)
        if response:
            await self.get_status()  # Refresh status
            return True
        return False

    async def stop(self) -> bool:
        """Stop the cooker."""
        response = await self._send_command(CMD_STOP)
        if response:
            await self.get_status()  # Refresh status
            return True
        return False

    async def set_units_celsius(self) -> bool:
        """Set temperature units to Celsius."""
        response = await self._send_command(CMD_UNITS_C)
        if response:
            await self.get_status()  # Refresh status
            return True
        return False

    async def set_units_fahrenheit(self) -> bool:
        """Set temperature units to Fahrenheit."""
        response = await self._send_command(CMD_UNITS_F)
        if response:
            await self.get_status()  # Refresh status
            return True
        return False

    @staticmethod
    async def discover_devices(timeout: float = 15.0) -> list[BLEDevice]:
        """Discover Anova devices."""
        _LOGGER.info("Starting BLE scan for Anova devices (timeout: %s seconds)...", timeout)
        
        devices = []
        try:
            # Use BleakScanner.discover with timeout
            devices = await BleakScanner.discover(timeout=timeout)
            _LOGGER.info("Found %d BLE devices total", len(devices) if devices else 0)
        except Exception as e:
            _LOGGER.error("Error during BLE scan: %s", e, exc_info=True)
            return []
        
        if not devices:
            _LOGGER.warning("No BLE devices found during scan")
            return []
        
        anova_devices = []
        try:
            for device in devices:
                if not device:
                    continue
                    
                try:
                    device_name = device.name or "" if hasattr(device, 'name') else ""
                    device_address = device.address or "" if hasattr(device, 'address') else ""
                    
                    if not device_address:
                        continue
                    
                    # Check by name (case-insensitive)
                    if device_name and ANOVA_DEVICE_NAME_PREFIX.lower() in device_name.lower():
                        _LOGGER.info("Found Anova device by name: %s (%s)", device_name, device_address)
                        anova_devices.append(device)
                        continue
                    
                    # Check by service UUID (if metadata available)
                    if hasattr(device, 'metadata') and device.metadata:
                        try:
                            services = device.metadata.get('uuids', [])
                            if services and ANOVA_SERVICE_UUID.lower() in [s.lower() for s in services]:
                                _LOGGER.info("Found Anova device by service UUID: %s (%s)", device_name or "Unknown", device_address)
                                anova_devices.append(device)
                                continue
                        except Exception as e:
                            _LOGGER.debug("Error checking service UUID: %s", e)
                    
                    # Log all devices for debugging (only first 10 to avoid spam)
                    if len(anova_devices) < 10:
                        _LOGGER.debug("Scanned device: %s (%s)", device_name or "Unknown", device_address)
                except Exception as e:
                    _LOGGER.debug("Error processing device: %s", e)
                    continue
        except Exception as e:
            _LOGGER.error("Error processing device list: %s", e, exc_info=True)
        
        _LOGGER.info("Found %d Anova device(s) out of %d total devices", len(anova_devices), len(devices))
        return anova_devices

