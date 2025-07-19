# --- START OF FILE config.py ---

# config.py - Configuration settings for Pi Pico LED light controller with Bluetooth & Unified Sensor support

# ---------------------------------------------------------------------------
# Hardware Configuration
# ---------------------------------------------------------------------------
PIN_NEOPIXEL = 5         # GPIO pin number connected to NeoPixels (Check your wiring!)
NUM_PIXELS = 96          # Total number of pixels in the strip

# --- I2C and Sensor Configuration ---
I2C_ID = 1                        # I2C bus ID (0 or 1 - Pico W usually uses 1 for GP26/27)
I2C_SCL_PIN = 27                  # GPIO pin for I2C SCL (Check your wiring!)
I2C_SDA_PIN = 26                  # GPIO pin for I2C SDA (Check your wiring!)
I2C_FREQUENCY = 100000           # I2C bus frequency (100kHz recommended)

# --- Sensor Enable Flags & Addresses ---
# Set to True to enable initialization and reading for each sensor
SCD4X_ENABLED = True              # Enable SCD4X CO2/Temp/Humidity Sensor
SCD4X_I2C_ADDR = 0x62             # SCD4X default I2C address

MPL3115A2_ENABLED = True          # Enable MPL3115A2 Pressure Sensor
MPL3115A2_I2C_ADDR = 0x60         # MPL3115A2 default I2C address

VEML7700_ENABLED = True           # Enable VEML7700 Light Sensor
VEML7700_I2C_ADDR = 0x10          # VEML7700 default I2C address

# How often the main loop attempts to read all sensors (in milliseconds)
SENSOR_READ_INTERVAL_MS = 300000  # Read sensors every 5 minutes (300000ms) (was 10 seconds before)

# Delay after starting sensor init (especially SCD4X) for sensors to stabilize (in milliseconds)
SENSOR_POST_INIT_DELAY_MS = 1000 # 1 second delay after init before first read

# NOTE: The SENSOR_INIT_DELAY_S below seems unused in the current main.py (v4.1.14)
#       It might be from an older version or intended for unified_sensor.py internal use.
# Delay after starting SCD4X measurement for the sensor to stabilize (in seconds) - Possibly Obsolete
SENSOR_INIT_DELAY_S = 5

# ---------------------------------------------------------------------------
# Schedule & Light Settings
# ---------------------------------------------------------------------------
LIGHTS_ON_TIME = "10:50"         # Default time to turn lights ON (HH:MM, 24hr) - Overridden by saved settings
LIGHTS_OFF_TIME = "20:00"        # Default time to turn lights OFF (HH:MM, 24hr) - Overridden by saved settings
ACTIVE_RECIPE = 'veg_growth'     # Default recipe for auto-on cycle - Overridden by saved settings

# --- Fading ---
FADE_DURATION = 5.0              # Default fade time in seconds when changing states manually or via schedule
STARTUP_FADE_DURATION = 0.5    # Fade duration when setting initial state on boot (seconds)
FADE_STEPS_PER_SECOND = 25       # Steps per second for fade calculations (higher = smoother but more CPU)

# Light recipes as (R, G, B, W) tuples (0-255)
LIGHT_RECIPES = {
    'balanced': (255, 64, 128, 255), 'warm': (255, 140, 20, 255), 'cool': (180, 200, 255, 255),
    'daylight': (255, 230, 210, 255), 'veg_growth': (50, 255, 70, 200), 'bloom': (255, 100, 10, 150),
    'seedling': (100, 100, 200, 150), 'succulent': (220, 180, 40, 200), 'purple_glow': (180, 0, 255, 0),
    'sunrise': (255, 50, 20, 100), 'sunset': (255, 30, 0, 50), 'forest': (30, 200, 30, 120),
    'aquarium': (0, 200, 255, 50), 'night_light': (50, 20, 0, 30), 'inspection': (255, 255, 255, 255),
    'off': (0, 0, 0, 0), # *** IMPORTANT: Ensure 'off' recipe exists ***
}

# Order for BLE interface/dropdown - MUST match any web UI or app list order
RECIPE_KEYS = [
    "balanced", "warm", "cool", "daylight", "veg_growth", "bloom", "seedling", "succulent",
    "purple_glow", "sunrise", "sunset", "forest", "aquarium", "night_light", "inspection", "off",
]

# ---------------------------------------------------------------------------
# Pi Pico Specific Settings
# ---------------------------------------------------------------------------
ENABLE_ONBOARD_LED = True    # Use onboard LED as status indicator (True/False)
WATCHDOG_TIMEOUT = 0         # Watchdog timeout in milliseconds (0 to disable). Use ~8000 for stability if needed.

# --- Main Loop Timing ---
MAIN_LOOP_DELAY_MS = 200     # Small delay at the end of the main loop (milliseconds) to yield CPU time
GC_INTERVAL_MS = 30000       # How often (milliseconds) to run garbage collection (e.g., 30 seconds)
# How often to check if the auto on/off schedule time has been crossed (milliseconds)
AUTO_CYCLE_CHECK_INTERVAL_MS = 10000 # Check every 10 seconds

# ---------------------------------------------------------------------------
# Bluetooth Settings
# ---------------------------------------------------------------------------
BT_ENABLED = True            # Enable Bluetooth functionality (True/False)
BT_DEVICE_NAME = 'PicoLightSen' # Bluetooth device name advertised
BT_AUTO_CYCLE = True         # Start in auto-cycle mode on boot? (True/False)

# --- BLE Timing & Memory ---
# How often (milliseconds) to send sensor data via BLE notify when connected
BT_SENSOR_UPDATE_INTERVAL_MS = 5000 # e.g., 5 seconds
# How often main loop checks if BLE advertising needs a restart attempt (milliseconds)
BT_RESTART_CHECK_INTERVAL_MS = 5000 # Check every 5 seconds
# BLE Advertising Interval (microseconds) - Lower values advertise more often
BT_ADV_INTERVAL_US = 100000 # 100ms is default
# Minimum free memory required before attempting BLE advertising (bytes) - Helps prevent MemoryErrors
MIN_MEM_ADV = 15000 # Adjust based on observation if MemoryErrors occur

# --- Bluetooth UUIDs ---
# Generate your own unique UUIDs for production/public projects!
# Online UUID Generator: https://www.uuidgenerator.net/ (Use version 4)
# Custom Light Service & Characteristics
BLE_SERVICE_UUID = "19b10000-e8f2-537e-4f6c-d104768a1214"
BLE_RECIPE_CHAR_UUID = "19b10001-e8f2-537e-4f6c-d104768a1214" # Write/Read: Recipe Index (uint8)
BLE_CUSTOM_CHAR_UUID = "19b10002-e8f2-537e-4f6c-d104768a1214" # Write/Read: Custom Color (R,G,B,W as uint8)
BLE_CONTROL_CHAR_UUID = "19b10003-e8f2-537e-4f6c-d104768a1214" # Write/Notify/Read: Commands & Status Updates
BLE_ILLUMINANCE_CHAR_UUID = "f8a3b2c1-d4e5-4f67-8a9b-c1d2e3f4a501"  # Read/Notify: Illuminance / Lux (VEML7700) - CUSTOM UUID
# Combined Sensor Data Characteristic (under Light Service)
BLE_COMBINED_SENSOR_CHAR_UUID = "a1b2c3d4-e5f6-4789-a0b1-c2d3e4f5a601" # Read/Notify: Sensor CSV String


# ---------------------------------------------------------------------------
# Logging Settings
# ---------------------------------------------------------------------------
LOGS_DIRECTORY = "/logs"                 # Directory for log files (Must exist or be creatable)
LOG_EVENT_FILE = f"{LOGS_DIRECTORY}/pico_log.txt"     # General event log file path
SENSOR_LIGHT_LOG_FILE = "sensor_light_log.csv" # Specific CSV log filename (in LOGS_DIRECTORY)

# Interval for writing sensor/light data to CSV log file (milliseconds)
CSV_LOG_INTERVAL_MS = 60000 # Log every 1 minute


# --- End of config.py ---