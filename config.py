# config.py - Configuration settings for Pi Pico LED light controller with Bluetooth support

# Hardware configuration
PIN_NEOPIXEL = 5         # GPIO pin number connected to NeoPixels (Check your wiring!)
NUM_PIXELS = 96          # Total number of pixels in the strip

# Daily schedule (in hours) - THESE ARE NOW DEFAULTS, overridden by saved settings
# They are used only if the 'schedule_settings.txt' file is missing or corrupted.
LIGHTS_ON_HOURS = 12     # Default hours to stay on if no saved setting exists
LIGHTS_OFF_HOURS = 12    # Default hours to stay off if no saved setting exists

# Transition settings (in seconds)
FADE_DURATION = 10       # Default time to fade between states (can be overridden in function calls)

# Light recipes as (R, G, B, W) tuples
# Ensure 'off' recipe exists. Names should match the 'recipes' array in the HTML exactly.
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
    'off': (0, 0, 0, 0),                # *** IMPORTANT: Ensure 'off' recipe exists ***
}

# List of recipe keys in the order they should appear in the BLE interface/dropdown
# This MUST match the order in the 'recipes' array in the HTML file.
RECIPE_KEYS = [
    "balanced", "warm", "cool", "daylight",
    "veg_growth", "bloom", "seedling", "succulent",
    "purple_glow", "sunrise", "sunset", "forest", "aquarium",
    "night_light", "inspection", "off",
]

# Active recipe to use when lights turn ON during auto-cycle mode
# Must be a valid key from LIGHT_RECIPES above.
ACTIVE_RECIPE = 'veg_growth'

# Pi Pico specific settings
ENABLE_ONBOARD_LED = True    # Use onboard LED as a status indicator (True/False)
LED_STATUS_FLASH = True      # Flash the LED on state changes/connections (True/False)
WATCHDOG_TIMEOUT = 0      # Watchdog timeout in milliseconds (e.g., 8000 for 8 seconds). 0 to disable.
                             # MUST be longer than the longest expected sleep/blocking operation.

# Bluetooth settings
BT_ENABLED = True            # Enable Bluetooth functionality (True/False)
BT_DEVICE_NAME = 'PicoLight 215' # Bluetooth device name (Keep concise)
# Initial state for auto-cycling. Can be toggled via BLE command 2 if implemented in UI.
BT_AUTO_CYCLE = True        # Start in manual mode (False) or auto-cycle mode (True) on boot?


# --- SERVICE UUID ---
# This should be UNIQUE for this device.
BLE_SERVICE_UUID = "19b10000-e8f2-537e-4f6c-d104768a1215"

# --- CHARACTERISTIC UUIDs ---
# These should be the SAME as your Other Light Panels, defining the standard
# endpoints *within* the PicoLight service.
BLE_RECIPE_CHAR_UUID = "19b10001-e8f2-537e-4f6c-d104768a1214"  # Should end in 1214
BLE_CUSTOM_CHAR_UUID = "19b10002-e8f2-537e-4f6c-d104768a1214"  # Should end in 1214
BLE_CONTROL_CHAR_UUID = "19b10003-e8f2-537e-4f6c-d104768a1214" # Should end in 1214



# --- Internal Calculations (Do not change these directly) ---
# These initial durations are calculated from the default hours above.
# They will be immediately overwritten by values loaded from 'schedule_settings.txt' at runtime.
LIGHTS_ON_DURATION = LIGHTS_ON_HOURS * 60 * 60
LIGHTS_OFF_DURATION = LIGHTS_OFF_HOURS * 60 * 60

