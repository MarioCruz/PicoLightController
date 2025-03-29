# config.py - Configuration settings for Pi Pico LED light controller with Bluetooth support

# Hardware configuration
PIN_NEOPIXEL = 5         # GPIO pin number connected to NeoPixels
NUM_PIXELS = 96          # Total number of pixels in the strip

# Daily schedule (in hours)
LIGHTS_ON_HOURS = 12     # Hours to stay on
LIGHTS_OFF_HOURS = 12    # Hours to stay off

# Transition settings (in seconds)
FADE_DURATION = 10       # Time to fade between states

# Light recipes as (R, G, B, W) tuples
LIGHT_RECIPES = {
    # General purpose light recipes
    'balanced': (255, 64, 128, 255),    # Red-leaning balanced light
    'warm': (255, 140, 20, 255),        # Warm light for cozy environments
    'cool': (180, 200, 255, 255),       # Cool blue light
    'daylight': (255, 230, 210, 255),   # Neutral daylight simulation
    
    # Plant-specific light recipes
    'veg_growth': (50, 255, 70, 200),   # Vegetative growth (blue-heavy)
    'bloom': (255, 100, 10, 150),       # Flowering/fruiting (red-heavy)
    'seedling': (100, 100, 200, 150),   # Gentle recipe for new plants
    'succulent': (220, 180, 40, 200),   # Good for succulents and cacti
    
    # Specialty light recipes
    'purple_glow': (180, 0, 255, 0),    # Purple glow effect
    'sunrise': (255, 50, 20, 100),      # Warm sunrise simulation
    'sunset': (255, 30, 0, 50),         # Deep sunset orange
    'forest': (30, 200, 30, 120),       # Forest-like green light
    'aquarium': (0, 200, 255, 50),      # Aquatic blue-green light
    
    # Utility recipes
    'night_light': (50, 20, 0, 30),     # Very dim warm light for night
    'inspection': (255, 255, 255, 255), # Maximum brightness for inspection
    'off': (0, 0, 0, 0),                # Off
}

# List of recipe keys for indexing via Bluetooth
RECIPE_KEYS = list(LIGHT_RECIPES.keys())

# Active recipe to use when lights are ON
ACTIVE_RECIPE = 'veg_growth'

# Pi Pico specific settings
ENABLE_ONBOARD_LED = True    # Use onboard LED as a status indicator
LED_STATUS_FLASH = True      # Flash the LED on state changes
WATCHDOG_TIMEOUT = 0         # Watchdog timeout in milliseconds (0 to disable)

# Bluetooth settings
BT_ENABLED = True            # Enable Bluetooth functionality
BT_DEVICE_NAME = 'PicoLight' # Bluetooth device name
BT_AUTO_CYCLE = False        # Whether to continue auto cycling (True) or maintain manual control (False)

# UUIDs for BLE services and characteristics
BLE_SERVICE_UUID = "19b10000-e8f2-537e-4f6c-d104768a1214"
BLE_RECIPE_CHAR_UUID = "19b10001-e8f2-537e-4f6c-d104768a1214"  # For selecting recipes
BLE_CUSTOM_CHAR_UUID = "19b10002-e8f2-537e-4f6c-d104768a1214"  # For setting custom RGBW values
BLE_CONTROL_CHAR_UUID = "19b10003-e8f2-537e-4f6c-d104768a1214"  # For control commands

# Convert hours to seconds for internal use
LIGHTS_ON_DURATION = LIGHTS_ON_HOURS * 60 * 60
LIGHTS_OFF_DURATION = LIGHTS_OFF_HOURS * 60 * 60