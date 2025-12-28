"""BLE client for Anova Precision Cooker A2/A3."""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice
from bleak_retry_connector import establish_connection, BleakClientWithServiceCache

from .const import (
    ANOVA_CHARACTERISTIC_UUID,
    ANOVA_DEVICE_NAME_PREFIX,
    ANOVA_SERVICE_UUID,
    CMD_GET_STATUS,
    CMD_READ_CURRENT_TEMP,
    CMD_READ_TARGET_TEMP,
    CMD_READ_UNIT,
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
        self._response_parts: list[str] = []
        
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
x
    def _notification_handler(self, sender: int, data: bytearray) -> None:
        """Handle notifications from the device."""
        try:
            response = data.decode("utf-8").strip()
            _LOGGER.debug("Received notification (raw): %r, decoded: %s", data, response)
            
            # Accumulate multiple notifications (avoid duplicates)
            if response and response not in self._response_parts:
                self._response_parts.append(response)
                # Combine all parts with newline separator
                self._response_data = "\n".join(self._response_parts)
                _LOGGER.debug("Accumulated response (%d parts so far): %s", len(self._response_parts), self._response_data)
            elif response in self._response_parts:
                _LOGGER.debug("Received duplicate notification: %s", response)
            
            # Signal that we received data (even if more might come)
            if self._response_event:
                self._response_event.set()
        except Exception as e:
            _LOGGER.error("Error handling notification: %s", e, exc_info=True)

    async def connect(self, retries: int = 3, timeout: float = 10.0) -> bool:
        """Connect to the Anova device with retry logic using bleak-retry-connector."""
        if self.is_connected:
            return True
        
        # Ensure minimum timeout of 10 seconds for establish_connection
        connection_timeout = max(timeout, 10.0)
        
        for attempt in range(1, retries + 1):
            try:
                _LOGGER.info("Connecting to Anova device at %s (attempt %d/%d)...", 
                            self._address, attempt, retries)
                
                # Clean up any existing client
                if self._client:
                    try:
                        if self._client.is_connected:
                            await self._client.disconnect()
                    except Exception:
                        pass
                    self._client = None
                
                # Find device using BleakScanner.find_device_by_address
                # This is the recommended way and works with establish_connection
                device = await BleakScanner.find_device_by_address(
                    self._address,
                    timeout=connection_timeout,
                )
                
                if not device:
                    _LOGGER.warning("Device %s not found in initial scan, trying manual scan...", 
                                   self._address)
                    # Try a manual scan as fallback
                    try:
                        scanner = BleakScanner()
                        await scanner.start()
                        await asyncio.sleep(3)  # Scan for 3 seconds
                        devices = await scanner.get_discovered_devices()
                        await scanner.stop()
                        
                        for d in devices:
                            if d.address.upper() == self._address.upper():
                                device = d
                                _LOGGER.info("Found device in manual scan")
                                break
                    except Exception as scan_error:
                        _LOGGER.debug("Manual scan also failed: %s", scan_error)
                
                # Use establish_connection for reliable connection
                # Store device in a list to allow closure to access it properly
                device_container = [device]
                address_for_callback = self._address
                
                # ble_device_callback is used if device is None to find it
                async def get_device():
                    """Callback to get device if not already found."""
                    if device_container[0]:
                        return device_container[0]
                    _LOGGER.debug("Trying to find device via callback...")
                    found_device = await BleakScanner.find_device_by_address(address_for_callback, timeout=5.0)
                    if found_device:
                        device_container[0] = found_device
                    return found_device
                
                self._client = await establish_connection(
                    BleakClientWithServiceCache,
                    device,
                    self._name,
                    disconnected_callback=self._disconnected_callback,
                    timeout=connection_timeout,
                    ble_device_callback=get_device if not device else None,
                )
                
                # Validate connection
                if not self._client:
                    _LOGGER.error("establish_connection returned None!")
                    raise ConnectionError("Failed to establish connection - client is None")
                
                _LOGGER.info("establish_connection completed, client type: %s, connected: %s", 
                           type(self._client).__name__, self._client.is_connected)
                
                if not self._client.is_connected:
                    _LOGGER.warning("Client created but not connected yet, waiting...")
                    # Give it a moment to complete connection
                    await asyncio.sleep(1)
                    if not self._client.is_connected:
                        raise ConnectionError("Client created but connection not established")
                
                # Enable notifications
                try:
                    await self._client.start_notify(
                        ANOVA_CHARACTERISTIC_UUID, self._notification_handler
                    )
                    _LOGGER.debug("Notifications enabled successfully")
                except Exception as notify_error:
                    _LOGGER.warning("Could not enable notifications: %s. Continuing anyway...", notify_error)
                
                self._connected = True
                _LOGGER.info("Successfully connected to Anova device at %s", self._address)
                
                # Try to get initial status (don't fail if this doesn't work)
                # Give it more time for the initial status
                try:
                    await asyncio.wait_for(self.get_status(), timeout=10.0)
                except asyncio.TimeoutError:
                    _LOGGER.warning("Timeout getting initial status (this is non-critical)")
                except Exception as status_error:
                    _LOGGER.warning("Could not get initial status: %s", status_error)
                
                return True
                
            except asyncio.TimeoutError:
                _LOGGER.warning("Connection timeout (attempt %d/%d)", attempt, retries)
                if attempt < retries:
                    await asyncio.sleep(2)  # Wait before retry
            except Exception as e:
                _LOGGER.error("Connection attempt %d/%d failed: %s", attempt, retries, e, exc_info=True)
                if attempt < retries:
                    await asyncio.sleep(2)  # Wait before retry
                else:
                    _LOGGER.error("Failed to connect to Anova device after %d attempts", retries)
            
            # Clean up on failure
            if self._client:
                try:
                    if self._client.is_connected:
                        await self._client.disconnect()
                except Exception:
                    pass
                self._client = None
        
        self._connected = False
        return False
    
    def _disconnected_callback(self, client: BleakClient) -> None:
        """Handle disconnection callback."""
        _LOGGER.warning("Device disconnected: %s", self._address)
        self._connected = False

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

    async def _send_command(self, command: str, timeout: float = 10.0) -> str | None:
        """Send a command to the device and wait for response."""
        if not self.is_connected:
            _LOGGER.debug("Not connected to device, attempting reconnection...")
            # Try to reconnect
            await self.connect(retries=1, timeout=5.0)
            if not self.is_connected:
                _LOGGER.error("Not connected to device and reconnection failed")
                return None

        async with self._lock:
            try:
                # Create event for response
                self._response_event = asyncio.Event()
                self._response_data = None
                self._response_parts = []

                # Send command (Anova commands should end with \r according to documentation)
                _LOGGER.debug("Sending command: %s", command)
                command_with_terminator = command + "\r"
                command_bytes = command_with_terminator.encode("utf-8")
                await self._client.write_gatt_char(
                    ANOVA_CHARACTERISTIC_UUID, command_bytes, response=True
                )

                # Wait for notification responses - collect multiple notifications
                # The device may send status data in multiple notifications
                # Anova devices may send status updates over a longer period
                start_time = asyncio.get_event_loop().time()
                last_data_time = None
                # For status command, wait longer as device may send multiple notifications
                is_status_cmd = (command == CMD_GET_STATUS)
                no_data_timeout = 3.0 if is_status_cmd else 1.0  # Wait longer for status
                min_wait_time = 1.5 if is_status_cmd else 0.5  # Minimum wait time for status
                
                while True:
                    try:
                        # Wait for a notification (short timeout to allow checking)
                        wait_timeout = min(0.2, timeout)  # Check every 200ms
                        try:
                            await asyncio.wait_for(self._response_event.wait(), timeout=wait_timeout)
                            self._response_event.clear()
                            last_data_time = asyncio.get_event_loop().time()
                            _LOGGER.debug("Received notification part, continuing to collect...")
                        except asyncio.TimeoutError:
                            # No new notification in this interval
                            current_time = asyncio.get_event_loop().time()
                            elapsed = current_time - start_time
                            
                            # If we have data and no new notification for a while, assume complete
                            # Also ensure we wait at least min_wait_time to collect all notifications
                            if self._response_data:
                                elapsed_total = current_time - start_time
                                if last_data_time:
                                    time_since_last_data = current_time - last_data_time
                                    if time_since_last_data >= no_data_timeout and elapsed_total >= min_wait_time:
                                        response = self._response_data
                                        _LOGGER.debug("Complete response collected after %.2fs (last data: %.2fs ago, %d parts): %s", 
                                                    elapsed_total, time_since_last_data, len(self._response_parts), response)
                                        return response
                                elif elapsed_total >= min_wait_time:
                                    # Waited minimum time but might get more data
                                    if not is_status_cmd:
                                        # For non-status commands, return what we have
                                        response = self._response_data
                                        _LOGGER.debug("Response collected after minimum wait: %s", response)
                                        return response
                                    # For status, keep waiting
                            
                            # Check overall timeout
                            if elapsed >= timeout:
                                _LOGGER.debug("Overall timeout reached waiting for response to command: %s", command)
                                if self._response_data:
                                    _LOGGER.debug("Returning partial response: %s", self._response_data)
                                    return self._response_data
                                break
                            
                            # Continue waiting
                            continue
                    except Exception as wait_error:
                        _LOGGER.debug("Error waiting for response: %s", wait_error)
                        break
                
                # Fallback: try reading directly
                try:
                    _LOGGER.debug("Attempting direct read as fallback...")
                    response = await asyncio.wait_for(
                        self._client.read_gatt_char(ANOVA_CHARACTERISTIC_UUID),
                        timeout=2.0,
                    )
                    decoded = response.decode("utf-8").strip()
                    _LOGGER.debug("Read response: %s", decoded)
                    return decoded
                except Exception as read_error:
                    _LOGGER.debug("Direct read also failed: %s", read_error)
                    return None
            except Exception as e:
                _LOGGER.error("Error sending command %s: %s", command, e, exc_info=True)
                # Mark as disconnected if connection error
                if "not connected" in str(e).lower() or "disconnect" in str(e).lower():
                    self._connected = False
                return None
            finally:
                self._response_event = None
                self._response_data = None
                self._response_parts = []

    def _parse_response(self, command: str, response: str) -> dict[str, Any]:
        """Parse response from device based on the command sent."""
        parsed: dict[str, Any] = {}
        
        # Remove \r and whitespace
        response = response.strip()
        
        if command == CMD_GET_STATUS:
            # Status command returns "running" or "stopped"
            if "running" in response.lower():
                parsed[STATUS_RUNNING] = True
            elif "stopped" in response.lower():
                parsed[STATUS_RUNNING] = False
                
        elif command == CMD_READ_TARGET_TEMP:
            # "read set temp" returns just the temperature number
            try:
                # Remove any non-numeric chars except decimal point and minus
                temp_str = re.sub(r'[^\d.-]', '', response)
                if temp_str:
                    temp_value = float(temp_str)
                    # Convert to Celsius if device is in Fahrenheit
                    if self._status.get(STATUS_UNITS) == "F":
                        temp_value = (temp_value - 32) * 5 / 9
                    parsed[STATUS_TARGET_TEMP] = temp_value
            except (ValueError, TypeError):
                _LOGGER.debug("Could not parse target temp from: %s", response)
                
        elif command == CMD_READ_CURRENT_TEMP:
            # "read temp" returns just the temperature number
            try:
                temp_str = re.sub(r'[^\d.-]', '', response)
                if temp_str:
                    temp_value = float(temp_str)
                    # Convert to Celsius if device is in Fahrenheit (check cached status)
                    if self._status.get(STATUS_UNITS) == "F":
                        temp_value = (temp_value - 32) * 5 / 9
                    parsed[STATUS_TEMP] = temp_value
            except (ValueError, TypeError):
                _LOGGER.debug("Could not parse current temp from: %s", response)
                
        elif command == CMD_READ_UNIT:
            # "read unit" returns "c" or "f"
            if "f" in response.lower():
                parsed[STATUS_UNITS] = "F"
            else:
                parsed[STATUS_UNITS] = "C"
        
        return parsed

    async def get_status(self) -> dict[str, Any]:
        """Get current status from device by sending multiple commands."""
        # Ensure connection
        if not self.is_connected:
            _LOGGER.debug("Not connected, attempting to reconnect...")
            await self.connect(retries=1, timeout=10.0)
        
        if not self.is_connected:
            _LOGGER.debug("Cannot get status: not connected")
            return self._status.copy()
        
        # Send multiple commands to get all status values (like ESPHome does)
        # 1. Get units first (needed for temperature conversion)
        response = await self._send_command(CMD_READ_UNIT, timeout=5.0)
        if response:
            parsed = self._parse_response(CMD_READ_UNIT, response)
            self._status.update(parsed)
        
        # 2. Get running status
        await asyncio.sleep(0.2)  # Small delay between commands
        response = await self._send_command(CMD_GET_STATUS, timeout=5.0)
        if response:
            parsed = self._parse_response(CMD_GET_STATUS, response)
            self._status.update(parsed)
        
        # 3. Get target temperature
        await asyncio.sleep(0.2)
        response = await self._send_command(CMD_READ_TARGET_TEMP, timeout=5.0)
        if response:
            parsed = self._parse_response(CMD_READ_TARGET_TEMP, response)
            self._status.update(parsed)
        
        # 4. Get current temperature
        await asyncio.sleep(0.2)
        response = await self._send_command(CMD_READ_CURRENT_TEMP, timeout=5.0)
        if response:
            parsed = self._parse_response(CMD_READ_CURRENT_TEMP, response)
            self._status.update(parsed)
        
        _LOGGER.debug("Status collected: %s", self._status)
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

