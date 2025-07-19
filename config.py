# config.py - v4.4.6 (Debug Print for Device Name)

# --- Add these imports at the very top ---
import machine
import binascii

VERSION = "4.4.6"

# ---------------------------------------------------------------------------
# Hardware Configuration
# ---------------------------------------------------------------------------
PIN_NEOPIXEL = 5
NUM_PIXELS = 96

# --- I2C and Sensor Configuration ---
I2C_ID = 1
I2C_SCL_PIN = 27
I2C_SDA_PIN = 26
I2C_FREQUENCY = 100000

# --- Sensor Enable Flags & Addresses ---
SCD4X_ENABLED = True
SCD4X_I2C_ADDR = 0x62
MPL3115A2_ENABLED = True
MPL3115A2_I2C_ADDR = 0x60
VEML7700_ENABLED = True
VEML7700_I2C_ADDR = 0x10

# --- Sensor Timing ---
# CRITICAL: Delay for SCD4x sensor to stabilize after starting. Used by unified_sensor.py.
SENSOR_INIT_DELAY_S = 5
# How often the main loop reads all sensors (in milliseconds)
SENSOR_READ_INTERVAL_MS = 300000  # 5 minutes
# Optional delay after all sensors are initialized in main.py
SENSOR_POST_INIT_DELAY_MS = 1000 # 1 second

# ---------------------------------------------------------------------------
# Bluetooth Settings
# ---------------------------------------------------------------------------
# --- Generate a unique device name from the Pico's hardware ID ---
# Get the unique ID (returns bytes), convert to hex, and decode to a string
unique_id_hex = binascii.hexlify(machine.unique_id()).decode('utf-8')
# Create a name like "Pico-e6648f03" using the first 8 characters of the ID
BT_DEVICE_NAME = f"Pico-{unique_id_hex[:8]}"

# --- ADD THIS LINE FOR DEBUGGING ---
print("INFO [config.py]: Generated BT_DEVICE_NAME =", BT_DEVICE_NAME)
# ------------------------------------

BT_ADV_INTERVAL_US = 100000

# --- Bluetooth UUIDs (MUST MATCH WEB UI) ---
BLE_SERVICE_UUID = "19b10000-e8f2-537e-4f6c-d104768a1214"
BLE_RECIPE_CHAR_UUID = "19b10001-e8f2-537e-4f6c-d104768a1214"
BLE_CUSTOM_CHAR_UUID = "19b10002-e8f2-537e-4f6c-d104768a1214"
BLE_CONTROL_CHAR_UUID = "19b10003-e8f2-537e-4f6c-d104768a1214"
BLE_COMBINED_SENSOR_CHAR_UUID = "a1b2c3d4-e5f6-4789-a0b1-c2d3e4f5a601"
BLE_SCHEDULE_CHAR_UUID = "12345678-1234-1234-1234-123456789abd"

# ---------------------------------------------------------------------------
# Light & Schedule Settings
# ---------------------------------------------------------------------------
ACTIVE_RECIPE = 'daylight'
LIGHT_RECIPES = {
    'off': (0, 0, 0, 0), 'warm': (255, 140, 20, 255), 'cool': (180, 200, 255, 255),
    'balanced': (255, 64, 128, 255), 'daylight': (255, 230, 210, 255),
    'veg_growth': (50, 255, 70, 200), 'bloom': (255, 100, 10, 150),
    'seedling': (100, 100, 200, 150), 'succulent': (220, 180, 40, 200),
    'purple_glow': (180, 0, 255, 0), 'sunrise': (255, 50, 20, 100),
    'sunset': (255, 30, 0, 50), 'forest': (30, 200, 30, 120),
    'aquarium': (0, 200, 255, 50), 'night_light': (50, 20, 0, 30),
    'inspection': (255, 255, 255, 255),
}
RECIPE_CODES = {
    'off': 0, 'warm': 1, 'cool': 2, 'aquarium': 3, 'veg_growth': 4, 'sunset': 5, 'balanced': 6,
    'daylight': 7, 'bloom': 8, 'seedling': 9, 'succulent': 10, 'purple_glow': 11, 'sunrise': 12,
    'forest': 13, 'night_light': 14, 'inspection': 15
}
CODE_TO_RECIPE = {v: k for k, v in RECIPE_CODES.items()}

# --- Advanced Schedule Settings ---
SCHEDULE_STORAGE_FILE = "schedule.json"
MAX_SCHEDULE_BLOCKS = 20
SCHEDULE_CHECK_INTERVAL_MS = 30000
SCHEDULE_RESUME_AFTER_MANUAL = True
SCHEDULE_RESUME_DELAY_SEC = 300
FADE_DURATION = 3.0
SCHEDULE_TRANSITION_FADE_SEC = 3.0

# ---------------------------------------------------------------------------
# System & Logging
# ---------------------------------------------------------------------------
MAIN_LOOP_DELAY_MS = 200
LOGS_DIRECTORY = "/logs"
LOG_EVENT_FILE = f"{LOGS_DIRECTORY}/pico_log.txt"
SENSOR_LIGHT_LOG_FILE = "sensor_light_log.csv"
CSV_LOG_INTERVAL_MS = 300000