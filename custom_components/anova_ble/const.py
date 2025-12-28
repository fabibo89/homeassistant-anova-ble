"""Constants for the Anova BLE integration."""
DOMAIN = "anova_ble"

# BLE Service and Characteristic UUIDs for A2/A3
ANOVA_SERVICE_UUID = "0000ffe0-0000-1000-8000-00805f9b34fb"
ANOVA_CHARACTERISTIC_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"

# Device name patterns
ANOVA_DEVICE_NAME_PREFIX = "Anova"

# Command prefixes
CMD_GET_STATUS = "status"
CMD_READ_TARGET_TEMP = "read set temp"
CMD_READ_CURRENT_TEMP = "read temp"
CMD_READ_UNIT = "read unit"
CMD_SET_TEMP = "set temp "
CMD_SET_TIMER = "set timer "
CMD_START = "start"
CMD_STOP = "stop"
CMD_UNITS_C = "set units C"
CMD_UNITS_F = "set units F"

# Status response keys
STATUS_TEMP = "temp"
STATUS_TARGET_TEMP = "target temp"
STATUS_TIMER = "timer"
STATUS_RUNNING = "running"
STATUS_UNITS = "units"

