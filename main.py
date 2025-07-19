# main.py - v4.1.13-syntax-fix
"""
Core control script for the PicoLightSen project. This script manages:
- Hardware initialization (NeoPixels, I2C sensors via UnifiedSensor driver)
- Bluetooth Low Energy (BLE) communication for control and data reporting (Simplified Reconnect)
- Scheduled light control based on ON/OFF times and selected recipe
- Manual light control via BLE commands
- Persistent storage of schedule settings
- Dual logging (general events and sensor/light CSV data)
- System tasks like Watchdog Timer feeding and Garbage Collection

Target Platform: Raspberry Pi Pico W with MicroPython
Required Modules: neopixel, bluetooth, unified_sensor, config
"""

# --- Standard Library Imports ---
import time
import machine
import gc
import sys
import struct
import os
import io         # Used for capturing tracebacks as strings for logging

# --- Third-Party/Custom Imports ---
import neopixel   # For controlling NeoPixel LEDs
import bluetooth  # For BLE communication (uses MicroPython's 'bluetooth' module)
import config     # Project-specific configuration constants (pins, UUIDs, etc.)

# --- Unified Sensor Driver Import ---
try:
    from unified_sensor import UnifiedSensor
    sensor_driver_available = True
except ImportError:
    print("WARN: UnifiedSensor driver ('unified_sensor.py') not found. Sensor functionality disabled.")
    UnifiedSensor = None
    sensor_driver_available = False
except Exception as e:
    print(f"WARN: Error importing UnifiedSensor: {e}. Sensor functionality disabled.")
    UnifiedSensor = None
    sensor_driver_available = False
    # Log traceback if possible (before log_event is fully ready)
    try:
        s = io.StringIO()
        sys.print_exception(e, s)
        print("Traceback:\n" + s.getvalue())
    except: pass


# ---------------------------------------------------------------------------
# Global Variables - Runtime State and Configuration Cache
# ---------------------------------------------------------------------------

# Schedule and Recipe State
current_on_time_str = config.LIGHTS_ON_TIME
current_off_time_str = config.LIGHTS_OFF_TIME
current_active_recipe_name = config.ACTIVE_RECIPE

# --- Persistence File Definition ---
SETTINGS_FILE = "controller_settings.txt"

# Hardware/System Object Instances
light_controller_instance = None
bt_instance = None
rtc = machine.RTC()
sensor_manager = None

# Sensor Data Cache
last_sensor_read_ms = 0
last_temp_c = None
last_humidity = None
last_co2 = None
last_pressure = None
last_lux = None

# Logging Globals
event_log_file_handle = None
csv_log_file_path = None # Will be constructed like /logs/sensor_data.csv

# Auto Cycle Runtime State
auto_cycle_light_should_be_on = False # Tracks the *expected* state based on time

# --- BLE Reconnect Flag ---
# This flag signals the main loop to attempt restarting advertising
ble_needs_restart = False


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------

def ensure_directory(dir_path):
    """ Checks if a directory exists, creates it if not. Essential for logging. """
    try:
        os.stat(dir_path)
    except OSError as e:
        if e.args[0] == 2: # errno.ENOENT
            print(f"Directory '{dir_path}' not found, attempting to create.")
            try:
                os.mkdir(dir_path)
                print(f"Successfully created directory: {dir_path}")
                try: log_event("SYSTEM", f"Created directory: {dir_path}")
                except Exception as log_ex: print(f"WARN: Created '{dir_path}' but failed to log: {log_ex}")
            except OSError as mkdir_e:
                print(f"!!! CRITICAL: Error creating directory {dir_path}: {mkdir_e}")
                try: log_event("ERROR", f"Failed create directory {dir_path}: {mkdir_e}")
                except Exception as log_err_ex: print(f"WARN: Failed creating '{dir_path}' AND failed to log error: {log_err_ex}")
                raise mkdir_e # Re-raise critical error
        else:
            print(f"!!! ERROR: Error accessing directory {dir_path}: {e}")
            try: log_event("ERROR", f"Error accessing directory {dir_path}: {e}")
            except Exception: pass
            raise e
    except Exception as general_e:
        print(f"!!! UNEXPECTED ERROR checking/creating directory {dir_path}: {general_e}")
        try: log_event("ERROR", f"Unexpected error with directory {dir_path}: {general_e}")
        except Exception: pass
        raise general_e

def log_event(category, message):
    """ Appends a timestamped message to the main event log file. """
    global event_log_file_handle
    event_log_path = config.LOG_EVENT_FILE
    try:
        ensure_directory(config.LOGS_DIRECTORY) # Ensure directory exists

        if event_log_file_handle is None:
            event_log_file_handle = open(event_log_path, "a")

        now_tuple = rtc.datetime()
        timestamp = f"{now_tuple[0]}-{now_tuple[1]:02d}-{now_tuple[2]:02d} {now_tuple[4]:02d}:{now_tuple[5]:02d}:{now_tuple[6]:02d}"
        log_line = f"{timestamp} [{category}] {message}\n"
        event_log_file_handle.write(log_line)
        event_log_file_handle.flush()

    except Exception as e:
        print(f"!!! Event Logging Error to {event_log_path}: {e}")
        if event_log_file_handle is not None:
            try: event_log_file_handle.close()
            except Exception: pass
            event_log_file_handle = None

def log_sensor_light_csv(temp, humid, co2, pressure, lux, r, g, b, w):
    """ Logs sensor readings and current light state to a CSV file. """
    global csv_log_file_path
    if csv_log_file_path is None:
        csv_log_file_path = f"{config.LOGS_DIRECTORY}/{config.SENSOR_LIGHT_LOG_FILE}"

    file_handle = None
    try:
        ensure_directory(config.LOGS_DIRECTORY)
        header_needed = False
        try:
            os.stat(csv_log_file_path)
        except OSError as e:
            if e.args[0] == 2: header_needed = True
            else: raise

        file_handle = open(csv_log_file_path, "a")

        if header_needed:
            file_handle.write("Timestamp,TempC,Humidity%,CO2ppm,Pressure_hPa,Lux,R,G,B,W\n")
            print(f"Created new CSV log file: {csv_log_file_path}")
            log_event("LOGGER", f"Created new CSV log: {config.SENSOR_LIGHT_LOG_FILE}")

        now_tuple = rtc.datetime()
        timestamp = f"{now_tuple[0]}-{now_tuple[1]:02d}-{now_tuple[2]:02d} {now_tuple[4]:02d}:{now_tuple[5]:02d}:{now_tuple[6]:02d}"

        temp_str = f"{temp:.1f}" if temp is not None else "N/A"
        humid_str = f"{humid:.1f}" if humid is not None else "N/A"
        co2_str = f"{co2}" if co2 is not None else "N/A"
        pressure_str = f"{pressure:.2f}" if pressure is not None else "N/A"
        lux_str = f"{lux:.2f}" if lux is not None else "N/A"
        r_str, g_str, b_str, w_str = f"{r}", f"{g}", f"{b}", f"{w}"

        log_line = f"{timestamp},{temp_str},{humid_str},{co2_str},{pressure_str},{lux_str},{r_str},{g_str},{b_str},{w_str}\n"
        file_handle.write(log_line)
        file_handle.flush()

    except Exception as e:
        print(f"!!! CSV Logging Error to {csv_log_file_path}: {e}")
        log_event("ERROR", f"CSV Logging failed: {e}")
    finally:
        if file_handle is not None:
            try: file_handle.close()
            except Exception: pass

def validate_time_format(time_str):
    """ Validates if a string is in 'HH:MM' format (24-hour). """
    if isinstance(time_str, str) and len(time_str) == 5 and time_str[2] == ':':
        try:
            h, m = map(int, time_str.split(':'))
            return 0 <= h <= 23 and 0 <= m <= 59
        except ValueError: return False
    return False

def save_settings(on_time_str, off_time_str, active_recipe_name):
    """ Saves schedule settings. Returns True on success, False on failure. """
    global current_on_time_str, current_off_time_str, current_active_recipe_name, bt_instance

    if not validate_time_format(on_time_str):
        log_event("ERROR", f"SaveSettings: Invalid ON time format '{on_time_str}'")
        return False
    if not validate_time_format(off_time_str):
        log_event("ERROR", f"SaveSettings: Invalid OFF time format '{off_time_str}'")
        return False
    if active_recipe_name not in config.LIGHT_RECIPES:
        log_event("ERROR", f"SaveSettings: Invalid recipe name '{active_recipe_name}'")
        return False
    if active_recipe_name == 'off':
        log_event("WARN", "SaveSettings: Attempted to save 'off' as active recipe. Denied.")
        return False

    try:
        with open(SETTINGS_FILE, "w") as f:
            f.write(f"ON_TIME={on_time_str}\n")
            f.write(f"OFF_TIME={off_time_str}\n")
            f.write(f"ACTIVE_RECIPE={active_recipe_name}\n")
        log_event("CONFIG", f"Settings Saved: ON={on_time_str}, OFF={off_time_str}, Recipe='{active_recipe_name}'")

        current_on_time_str = on_time_str
        current_off_time_str = off_time_str
        current_active_recipe_name = active_recipe_name

        if bt_instance and bt_instance.connected and hasattr(bt_instance, '_send_settings_update_notification'):
            bt_instance._send_settings_update_notification()
        return True

    except Exception as e:
        log_event("ERROR", f"Failed to save settings to {SETTINGS_FILE}: {e}")
        print(f"!!! ERROR: Could not save settings: {e}")
        s = io.StringIO(); sys.print_exception(e, s); log_event("ERROR", "Traceback:\n" + s.getvalue())
        return False

def load_settings():
    """ Loads schedule settings from file or creates defaults. """
    global current_on_time_str, current_off_time_str, current_active_recipe_name

    default_on_t = config.LIGHTS_ON_TIME
    default_off_t = config.LIGHTS_OFF_TIME
    default_active_recipe = config.ACTIVE_RECIPE
    on_t, off_t, active_recipe = default_on_t, default_off_t, default_active_recipe

    try:
        os.stat(SETTINGS_FILE)
        print(f"Reading settings from '{SETTINGS_FILE}'...")
        settings = {}
        with open(SETTINGS_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line: continue
                try:
                    key, value = line.split('=', 1)
                    settings[key.strip().upper()] = value.strip()
                except Exception as read_err:
                    log_event("WARN", f"LoadSettings: Skipped malformed line '{line}': {read_err}")

        loaded_on_time = settings.get('ON_TIME', default_on_t)
        on_t = loaded_on_time if validate_time_format(loaded_on_time) else default_on_t
        if on_t != loaded_on_time: log_event("WARN", f"LoadSettings: Invalid ON_TIME '{loaded_on_time}'. Using default.")

        loaded_off_time = settings.get('OFF_TIME', default_off_t)
        off_t = loaded_off_time if validate_time_format(loaded_off_time) else default_off_t
        if off_t != loaded_off_time: log_event("WARN", f"LoadSettings: Invalid OFF_TIME '{loaded_off_time}'. Using default.")

        loaded_recipe = settings.get('ACTIVE_RECIPE', default_active_recipe)
        active_recipe = loaded_recipe if (loaded_recipe in config.LIGHT_RECIPES and loaded_recipe != 'off') else default_active_recipe
        if active_recipe != loaded_recipe: log_event("WARN", f"LoadSettings: Invalid ACTIVE_RECIPE '{loaded_recipe}'. Using default.")

        print(f"Loaded settings: ON={on_t}, OFF={off_t}, Recipe='{active_recipe}'")

    except OSError as e:
        if e.args[0] == 2: # ENOENT
            print(f"Settings file '{SETTINGS_FILE}' not found. Creating with defaults.")
            log_event("CONFIG", f"Settings file '{SETTINGS_FILE}' not found. Creating defaults.")
            if not save_settings(default_on_t, default_off_t, default_active_recipe):
                 print(f"!!! CRITICAL: Failed to save default settings. Using defaults in memory.")
                 log_event("ERROR", "Failed to save initial default settings.")
                 on_t, off_t, active_recipe = default_on_t, default_off_t, default_active_recipe
            # Globals set by save_settings or fallback above
            current_on_time_str = on_t
            current_off_time_str = off_t
            current_active_recipe_name = active_recipe
            log_event("CONFIG", f"Runtime Settings Initialized: ON={on_t}, OFF={off_t}, Recipe='{active_recipe}'")
            return # Exit function

        else:
            print(f"!!! ERROR: OS error reading settings file {SETTINGS_FILE}: {e}. Using defaults.")
            log_event("ERROR", f"LoadSettings: OS error: {e}. Using defaults.")
            on_t, off_t, active_recipe = default_on_t, default_off_t, default_active_recipe

    except Exception as e:
        print(f"!!! ERROR: Unexpected error loading settings: {e}. Using defaults.")
        log_event("ERROR", f"LoadSettings: Unexpected error: {e}. Using defaults.")
        s = io.StringIO(); sys.print_exception(e, s); log_event("ERROR", "Traceback:\n" + s.getvalue())
        on_t, off_t, active_recipe = default_on_t, default_off_t, default_active_recipe

    current_on_time_str = on_t
    current_off_time_str = off_t
    current_active_recipe_name = active_recipe
    log_event("CONFIG", f"Runtime Settings Initialized: ON={on_t}, OFF={off_t}, Recipe='{active_recipe}'")

def is_time_between(current_hm_tuple, start_hm_tuple, end_hm_tuple):
    """ Checks if current time (HH, MM) is within the interval [start, end). Handles midnight crossing. """
    ch, cm = current_hm_tuple
    sh, sm = start_hm_tuple
    eh, em = end_hm_tuple
    current_mins = ch * 60 + cm
    start_mins = sh * 60 + sm
    end_mins = eh * 60 + em

    if start_mins <= end_mins: # Doesn't cross midnight
        return start_mins <= current_mins < end_mins
    else: # Crosses midnight
        return current_mins >= start_mins or current_mins < end_mins

# ---------------------------------------------------------------------------
# Onboard LED & Watchdog Setup
# ---------------------------------------------------------------------------
led_onboard = None
if config.ENABLE_ONBOARD_LED:
    try:
        led_onboard = machine.Pin("LED", machine.Pin.OUT)
        led_onboard.off()
        print("Onboard LED enabled.")
    except Exception as e:
        print(f"WARN: Failed to initialize Onboard LED: {e}")
        led_onboard = None
else:
    print("Onboard LED disabled by config.")

def blink(t=1, d=0.1):
    """ Blinks the onboard LED 't' times. """
    if led_onboard:
        for _ in range(t):
            led_onboard.on(); time.sleep(d)
            led_onboard.off(); time.sleep(d)

wdt = None
if config.WATCHDOG_TIMEOUT > 0:
    try:
        wdt = machine.WDT(timeout=config.WATCHDOG_TIMEOUT)
        wdt.feed()
        print(f"WDT Enabled: Timeout {config.WATCHDOG_TIMEOUT}ms")
    except Exception as e:
        print(f"!!! ERROR: Failed to initialize WDT: {e}")
        wdt = None
else:
    print("WDT Disabled by config.")

# ---------------------------------------------------------------------------
# NeoPixel Initialization
# ---------------------------------------------------------------------------
np = None
try:
    np = neopixel.NeoPixel(machine.Pin(config.PIN_NEOPIXEL), config.NUM_PIXELS, bpp=4)
    np.fill((0, 0, 0, 0)); np.write()
    print(f"NeoPixel ({config.NUM_PIXELS} LEDs on Pin {config.PIN_NEOPIXEL}, RGBW) Initialized OK.")
    blink(2, 0.05)
except Exception as e:
    print(f"!!! FATAL: NeoPixel Initialization Error on Pin {config.PIN_NEOPIXEL}: {e}")
    try: log_event("ERROR", f"NeoPixel Init FAILED: {e}")
    except: pass
    for _ in range(10): blink(1, 0.05)
    raise RuntimeError(f"NeoPixel failed to initialize: {e}")

# ---------------------------------------------------------------------------
# Light Controller Class Definition
# ---------------------------------------------------------------------------
class LightController:
    """Manages NeoPixel settings, recipes, fades, and auto-cycle state."""
    def __init__(self, neopixel_instance):
        if not neopixel_instance: raise ValueError("NeoPixel instance required.")
        self.np = neopixel_instance
        self.num_pixels = self.np.n
        self.current_recipe_tuple = config.LIGHT_RECIPES.get('off', (0,0,0,0))
        self.current_recipe_name = 'off'
        self.auto_cycle_enabled = config.BT_AUTO_CYCLE

    def set_all(self, r, g, b, w):
        """ Immediately sets all pixels to the specified RGBW color. """
        r_int = max(0, min(255, int(r)))
        g_int = max(0, min(255, int(g)))
        b_int = max(0, min(255, int(b)))
        w_int = max(0, min(255, int(w)))
        target_tuple = (r_int, g_int, b_int, w_int)

        if self.current_recipe_tuple == target_tuple:
            if wdt: wdt.feed()
            return

        new_recipe_name = 'custom'
        for name, rgbw_tuple in config.LIGHT_RECIPES.items():
            if rgbw_tuple == target_tuple:
                new_recipe_name = name; break

        try:
            self.np.fill(target_tuple)
            self.np.write()
            self.current_recipe_tuple = target_tuple
            self.current_recipe_name = new_recipe_name
        except Exception as e:
            log_event("ERROR", f"NeoPixel write error in set_all: {e}")
            print(f"!!! ERROR: NeoPixel write failed in set_all: {e}")
        finally:
            if wdt: wdt.feed()

    def fade_to(self, target_rgbw_tuple, duration_sec=None):
        """ Smoothly fades all pixels from the current color to the target RGBW color. """
        if duration_sec is None: duration_sec = config.FADE_DURATION
        if not isinstance(target_rgbw_tuple, tuple) or len(target_rgbw_tuple) != 4:
            log_event("WARN", f"FadeTo: Invalid target tuple {target_rgbw_tuple}. Fading to OFF.")
            target_rgbw_tuple = config.LIGHT_RECIPES.get('off', (0,0,0,0))

        try:
            t_r, t_g, t_b, t_w = [max(0, min(255, int(c))) for c in target_rgbw_tuple]
            target_tuple = (t_r, t_g, t_b, t_w)
        except (ValueError, TypeError) as e:
            log_event("ERROR", f"FadeTo: Error processing target tuple {target_rgbw_tuple}: {e}. Fading to OFF.")
            target_tuple = config.LIGHT_RECIPES.get('off', (0,0,0,0))
            t_r, t_g, t_b, t_w = target_tuple

        start_tuple = self.get_current_rgbw()
        s_r, s_g, s_b, s_w = start_tuple

        if start_tuple == target_tuple:
            self.set_all(*target_tuple); return
        if duration_sec < 0.05:
            self.set_all(*target_tuple); return

        num_steps = max(1, int(duration_sec * config.FADE_STEPS_PER_SECOND))
        step_duration_ms = max(1, int((duration_sec / num_steps) * 1000))
        delta_r = (t_r - s_r) / num_steps
        delta_g = (t_g - s_g) / num_steps
        delta_b = (t_b - s_b) / num_steps
        delta_w = (t_w - s_w) / num_steps

        # log_event("LIGHT", f"Fading from {start_tuple} to {target_tuple} over {duration_sec}s ({num_steps} steps)")

        for step in range(num_steps + 1):
            r = max(0, min(255, int(s_r + delta_r * step + 0.5)))
            g = max(0, min(255, int(s_g + delta_g * step + 0.5)))
            b = max(0, min(255, int(s_b + delta_b * step + 0.5)))
            w = max(0, min(255, int(s_w + delta_w * step + 0.5)))
            current_step_color = (r, g, b, w)

            try:
                self.np.fill(current_step_color)
                self.np.write()
            except Exception as e:
                log_event("ERROR", f"NP write error during fade step {step}: {e}")
            finally:
                if wdt: wdt.feed()

            if step < num_steps: time.sleep_ms(step_duration_ms)
            if step > 0 and step % 50 == 0: gc.collect()

        self.set_all(*target_tuple) # Ensure final state is set correctly
        # log_event("LIGHT", f"Fade complete. State: {self.get_current_recipe_name()} {self.get_current_rgbw()}")

    def set_recipe_by_name(self, recipe_name, duration_sec=None):
        """ Sets the lights to a predefined recipe, optionally fading. """
        if recipe_name in config.LIGHT_RECIPES:
            target_tuple = config.LIGHT_RECIPES[recipe_name]
            log_event("LIGHT", f"Set recipe requested: '{recipe_name}' -> {target_tuple}")
            print(f"Setting recipe by name: '{recipe_name}' -> {target_tuple}")
            self.fade_to(target_tuple, duration_sec)
            return True
        else:
            log_event("WARN", f"Recipe '{recipe_name}' not found. Setting to OFF.")
            self.fade_to(config.LIGHT_RECIPES.get('off', (0,0,0,0)), duration_sec)
            return False

    def set_recipe_by_index(self, recipe_index, duration_sec=None):
        """ Sets the lights based on the index in config.RECIPE_KEYS. """
        if 0 <= recipe_index < len(config.RECIPE_KEYS):
            recipe_name = config.RECIPE_KEYS[recipe_index]
            print(f"Setting recipe by index: {recipe_index} -> '{recipe_name}'")
            return self.set_recipe_by_name(recipe_name, duration_sec)
        else:
            print(f"Error: Recipe Index {recipe_index} out of range. Setting OFF.")
            log_event("ERROR", f"Recipe Index {recipe_index} out of range. Turning OFF.")
            self.fade_to(config.LIGHT_RECIPES.get('off', (0,0,0,0)), duration_sec)
            return False

    def set_custom_rgbw(self, r, g, b, w, duration_sec=None):
        """ Sets a custom RGBW color, optionally fading. """
        try:
            target_tuple = (int(r), int(g), int(b), int(w))
            log_event("LIGHT", f"Set custom RGBW requested -> {target_tuple}")
            print(f"Setting custom RGBW -> {target_tuple}")
            self.fade_to(target_tuple, duration_sec)
            return True
        except (ValueError, TypeError) as e:
            log_event("ERROR", f"Set custom RGBW failed: Invalid values {r},{g},{b},{w}. {e}")
            print(f"Error: Invalid custom RGBW values: {r},{g},{b},{w} ({e})")
            return False

    def toggle_auto_cycle(self):
        """ Enables or disables the automatic light schedule control. """
        self.auto_cycle_enabled = not self.auto_cycle_enabled
        state_str = 'ENABLED' if self.auto_cycle_enabled else 'DISABLED'
        print(f"Automatic light cycle {state_str}.")
        log_event("CONFIG", f"Auto Cycle Toggled: {state_str}")
        return self.auto_cycle_enabled

    def get_current_rgbw(self):
        """ Returns the current RGBW tuple state of the lights. """
        if isinstance(self.current_recipe_tuple, tuple) and len(self.current_recipe_tuple) == 4:
            return self.current_recipe_tuple
        else:
            log_event("WARN", f"Corrupted light state detected: {self.current_recipe_tuple}. Returning OFF.")
            self.current_recipe_tuple = config.LIGHT_RECIPES.get('off', (0,0,0,0))
            self.current_recipe_name = 'off'
            return self.current_recipe_tuple

    def get_current_recipe_name(self):
        """ Returns the name of the current recipe ('custom' if not named). """
        current_tuple = self.get_current_rgbw()
        found_name = 'custom'
        for name, rgbw in config.LIGHT_RECIPES.items():
            if rgbw == current_tuple: found_name = name; break
        if self.current_recipe_name != found_name: self.current_recipe_name = found_name
        return self.current_recipe_name

    def get_recipe_list(self):
        """ Returns the list of available recipe names (keys). """
        return config.RECIPE_KEYS


# ---------------------------------------------------------------------------
# Bluetooth Controller Class Definition (Simplified Reconnect)
# ---------------------------------------------------------------------------
class BluetoothController:
    """Handles BLE communication, services, characteristics, and commands."""
    # --- Notification Codes ---
    NTF_ACK_COMMAND_RECEIVED = 100
    NTF_ERROR_INVALID_COMMAND = 101
    NTF_AUTO_CYCLE_ENABLED = 102
    NTF_AUTO_CYCLE_DISABLED = 103
    NTF_SETTINGS_UPDATE = 113
    NTF_STATUS_UPDATE = 120
    NTF_MEMORY_UPDATE = 121
    NTF_TIME_UPDATE = 131

    def __init__(self, light_controller):
        global bt_instance
        if not light_controller: raise ValueError("LightController required.")
        self.lights = light_controller
        self.ble = bluetooth.BLE()

        try: # Initial activation
            print("Initializing BLE Radio...")
            self.ble.active(False); time.sleep_ms(200)
            self.ble.active(True); time.sleep_ms(100)
            print("BLE Radio Activated.")
            log_event("BLE", "Radio Activated.")
        except Exception as e:
            print(f"!!! FATAL: BLE Activation Error: {e}")
            log_event("ERROR", f"BLE Activation failed: {e}")
            s = io.StringIO(); sys.print_exception(e, s); log_event("ERROR", "Traceback:\n" + s.getvalue())
            raise

        self.connected = False
        self.conn_handle = None
        # UUIDs
        self.svc_uuid = bluetooth.UUID(config.BLE_SERVICE_UUID)
        self.recipe_char_uuid = bluetooth.UUID(config.BLE_RECIPE_CHAR_UUID)
        self.custom_char_uuid = bluetooth.UUID(config.BLE_CUSTOM_CHAR_UUID)
        self.control_char_uuid = bluetooth.UUID(config.BLE_CONTROL_CHAR_UUID)
        self.illuminance_char_uuid = bluetooth.UUID(config.BLE_ILLUMINANCE_CHAR_UUID)
        self.combined_sensor_char_uuid = bluetooth.UUID(config.BLE_COMBINED_SENSOR_CHAR_UUID)
        # Handles
        self.recipe_handle = None
        self.custom_handle = None
        self.control_handle = None
        self.illuminance_handle = None
        self.combined_sensor_handle = None

        self._register_services() # Assigns handles
        self.ble.irq(self._irq_handler)
        print("BLE IRQ Handler Registered.")
        self._start_advertising()
        bt_instance = self

    def _register_services(self):
        """Defines and registers GATT services and characteristics."""
        # NOTE: This function might be called again if BLE radio is cycled later
        # It should be safe to re-register services.
        print("Registering BLE GATT services...")
        light_chars = []
        any_env_sensor = (config.SCD4X_ENABLED or config.MPL3115A2_ENABLED)
        any_sensor = any_env_sensor or (config.VEML7700_ENABLED and sensor_driver_available)

        # --- Define Characteristics in Order ---
        light_chars.append((self.recipe_char_uuid, bluetooth.FLAG_WRITE | bluetooth.FLAG_READ))
        light_chars.append((self.custom_char_uuid, bluetooth.FLAG_WRITE | bluetooth.FLAG_READ))
        light_chars.append((self.control_char_uuid, bluetooth.FLAG_WRITE | bluetooth.FLAG_NOTIFY | bluetooth.FLAG_READ))
        if config.VEML7700_ENABLED and sensor_driver_available:
            light_chars.append((self.illuminance_char_uuid, bluetooth.FLAG_READ | bluetooth.FLAG_NOTIFY))
        if any_sensor:
            light_chars.append((self.combined_sensor_char_uuid, bluetooth.FLAG_READ | bluetooth.FLAG_NOTIFY))

        light_service_def = (self.svc_uuid, tuple(light_chars))
        services_tuple = (light_service_def,)
        # log_event("BLE", f"Registering Service UUID: {config.BLE_SERVICE_UUID}") # Reduce logging noise if called often
        # print(f"DEBUG Service Definition: {services_tuple}")

        # --- Attempt Registration ---
        try:
            # Deactivate/Reactivate BLE before registering (might help clear state)
            # self.ble.active(False)
            # time.sleep_ms(100)
            # self.ble.active(True)
            # time.sleep_ms(100)

            registered_handles_nested = self.ble.gatts_register_services(services_tuple)
            print(f"BLE Services Registered. Handles returned: {registered_handles_nested}")
            log_event("BLE", f"Services registered. Handles: {registered_handles_nested}")

            if registered_handles_nested and len(registered_handles_nested[0]) > 0:
                handles = registered_handles_nested[0]
                handle_idx = 0
                # Assign handles in the same order they were defined
                self.recipe_handle = handles[handle_idx]; handle_idx += 1
                self.custom_handle = handles[handle_idx]; handle_idx += 1
                self.control_handle = handles[handle_idx]; handle_idx += 1
                if config.VEML7700_ENABLED and sensor_driver_available:
                    if len(handles) > handle_idx: self.illuminance_handle = handles[handle_idx]; handle_idx += 1
                    else: log_event("ERROR", "BLE Reg: Missing Illuminance handle!"); self.illuminance_handle = None
                if any_sensor:
                    if len(handles) > handle_idx: self.combined_sensor_handle = handles[handle_idx]; handle_idx += 1
                    else: log_event("ERROR", "BLE Reg: Missing Combined Sensor handle!"); self.combined_sensor_handle = None

                print(f"   Handles Assigned: R={self.recipe_handle}, C={self.custom_handle}, Ctrl={self.control_handle}, Lux={self.illuminance_handle}, Comb={self.combined_sensor_handle}")
                log_event("BLE", f"Handles assigned: R={self.recipe_handle}, C={self.custom_handle}, Ctrl={self.control_handle}, Lux={self.illuminance_handle}, Comb={self.combined_sensor_handle}")

                # Set Initial Characteristic Values (only needed on first registration?)
                # If this is called again on reconnect, these might not need resetting unless values changed while disconnected
                # print("Setting initial characteristic values...")
                # self._update_light_characteristics()
                # if self.combined_sensor_handle is not None:
                #     self.ble.gatts_write(self.combined_sensor_handle, self.get_formatted_sensor_string())
                # if self.illuminance_handle is not None:
                #     self.ble.gatts_write(self.illuminance_handle, struct.pack('<f', 0.0))
                # print("Initial characteristic values set.")
            else:
                raise RuntimeError("gatts_register_services returned no handles.")

        except MemoryError as me_reg:
             log_event("ERROR", f"MemoryError during service registration: {me_reg}")
             print(f"!!! MemoryError registering services: {me_reg}")
             # Critical failure, likely need reset
             raise me_reg # Re-raise MemoryError
        except Exception as e:
            log_event("ERROR", f"FATAL: BLE Service Registration FAILED: {e}")
            print(f"!!! FATAL: BLE Service Registration Error: {e}")
            s = io.StringIO(); sys.print_exception(e, s); log_event("ERROR", "Traceback:\n" + s.getvalue())
            raise RuntimeError(f"Failed to register BLE services: {e}")

    def _start_advertising(self):
        """Starts BLE advertising. MUST be called from main context or carefully."""
        global ble_needs_restart

        # --- Pre-Advertising Memory Check ---
        gc.collect()
        mem_before_adv = gc.mem_free()
        print(f"DEBUG: Mem before advertising attempt: {mem_before_adv}")
        if mem_before_adv < config.MIN_MEM_ADV: # Define a threshold in config.py, e.g., 15000
            log_event("WARN", f"Low memory ({mem_before_adv} bytes) before advertising. Skipping attempt.")
            print(f"WARN: Low memory ({mem_before_adv} < {config.MIN_MEM_ADV}). Advertising skipped.")
            ble_needs_restart = True # Keep flag set to retry later
            return # Skip advertising attempt

        # --- Proceed with Advertising ---
        try:
            name = config.BT_DEVICE_NAME
            payload = bytearray(b'\x02\x01\x06')
            name_bytes = name.encode('utf-8')
            payload += bytes([len(name_bytes) + 1, 0x09])
            payload += name_bytes

            try: # Stop previous advertising
                self.ble.gap_advertise(None); time.sleep_ms(50)
            except OSError as ose:
                 if ose.args[0] != 22: print(f"Warn: Error stopping prev adv (ignored): {ose}")

            # --- Perform Advertising (Memory Critical Point) ---
            self.ble.gap_advertise(config.BT_ADV_INTERVAL_US, adv_data=payload)
            # --- Advertising Started ---

            print(f"BLE advertising started as '{name}'")
            log_event("BLE", f"Advertising started as '{name}'")
            blink(1)
            ble_needs_restart = False # Success, clear flag

        except MemoryError as me:
            log_event("ERROR", f"MemoryError during _start_advertising: {me}")
            print(f"!!! MemoryError starting advertising: {me}")
            ble_needs_restart = True # Keep flag set to retry later
            gc.collect() # Attempt to free memory
            print(f"!!! Advertising failed (MemoryError). Free Mem: {gc.mem_free()}. Will retry later.")
            log_event("ERROR", f"Advertising failed (MemoryError). Mem Free: {gc.mem_free()}. Will retry.")

        except Exception as e:
            log_event("ERROR", f"BLE Advertising Start Error: {e}")
            print(f"!!! ERROR: BLE Advertising Start Failed: {e}")
            s = io.StringIO(); sys.print_exception(e, s); log_event("ERROR", "Traceback:\n" + s.getvalue())
            blink(5, 0.1)
            ble_needs_restart = True # Set flag to retry later


    def _irq_handler(self, event, data):
        """Handles Bluetooth interrupt requests (connect, disconnect, writes)."""
        global ble_needs_restart

        _IRQ_CENTRAL_CONNECT = 1
        _IRQ_CENTRAL_DISCONNECT = 2
        _IRQ_GATTS_WRITE = 3

        if event == _IRQ_CENTRAL_CONNECT:
            conn_handle, addr_type, addr = data
            self.connected = True
            self.conn_handle = conn_handle
            ble_needs_restart = False # Clear flag
            addr_str = ':'.join(['{:02X}'.format(b) for b in addr])
            print(f"BLE CONNECTED: Handle={self.conn_handle}, Address={addr_str}")
            log_event("BLE", f"Connected: H={self.conn_handle}, Addr={addr_str}")
            blink(3, 0.1)
            try: self.ble.gap_advertise(None) # Stop advertising
            except Exception: pass

            # Send initial state (consider delaying slightly if connection is slow)
            # time.sleep_ms(100)
            print("Sending initial state notifications...")
            self._send_settings_update_notification(); time.sleep_ms(20)
            self.update_combined_sensor_characteristic(); time.sleep_ms(20)
            if self.illuminance_handle is not None: self.update_illuminance_characteristic(); time.sleep_ms(20)
            self._send_memory_update_notification(); time.sleep_ms(20)
            self._send_time_update_notification(); time.sleep_ms(20)
            self._update_light_characteristics()
            print("Initial state sent.")

        elif event == _IRQ_CENTRAL_DISCONNECT:
            conn_handle, addr_type, addr = data
            if conn_handle == self.conn_handle or self.conn_handle is None:
                self.connected = False
                self.conn_handle = None
                addr_str = ':'.join(['{:02X}'.format(b) for b in addr]) if addr else "Unknown"
                print(f"BLE DISCONNECTED: Handle={conn_handle}, Address={addr_str}")
                log_event("BLE", f"Disconnected: H={conn_handle}, Addr={addr_str}")
                blink(1, 0.3)

                # --- Simplified Reconnect ---
                print("Signaling main loop to restart advertising.")
                log_event("BLE", "Disconnected. Signaling main loop for advertising restart.")
                ble_needs_restart = True
                # --- Main loop handles the restart attempt ---

        elif event == _IRQ_GATTS_WRITE:
            conn_handle, value_handle = data
            if conn_handle == self.conn_handle:
                if value_handle == self.recipe_handle: self._handle_recipe_write()
                elif value_handle == self.custom_handle: self._handle_custom_write()
                elif value_handle == self.control_handle: self._handle_control_write()

    def _update_light_characteristics(self):
        """Writes current light state to BLE characteristics."""
        if not self.ble.active(): return
        if self.recipe_handle is not None:
            try:
                current_name = self.lights.get_current_recipe_name()
                idx = config.RECIPE_KEYS.index('off')
                try: idx = config.RECIPE_KEYS.index(current_name)
                except ValueError: pass
                self.ble.gatts_write(self.recipe_handle, struct.pack('<B', idx))
            except Exception as e: log_event("ERROR", f"BLE Recipe Char Update Err: {e}")
        if self.custom_handle is not None:
            try:
                rgbw_tuple = self.lights.get_current_rgbw()
                self.ble.gatts_write(self.custom_handle, struct.pack('<BBBB', *rgbw_tuple))
            except Exception as e: log_event("ERROR", f"BLE Custom RGBW Char Update Err: {e}")

    def get_formatted_sensor_string(self):
        temp_str = f"{last_temp_c:.1f}" if last_temp_c is not None else "N/A"
        humid_str = f"{last_humidity:.1f}" if last_humidity is not None else "N/A"
        co2_str = f"{last_co2}" if last_co2 is not None else "N/A"
        pressure_str = f"{last_pressure:.2f}" if last_pressure is not None else "N/A"
        lux_str = f"{last_lux:.2f}" if last_lux is not None else "N/A"
        return f"{temp_str},{humid_str},{co2_str},{pressure_str},{lux_str}"

    def update_combined_sensor_characteristic(self):
        if self.combined_sensor_handle is None or not self.ble.active(): return
        sensor_string = self.get_formatted_sensor_string()
        try:
            self.ble.gatts_write(self.combined_sensor_handle, sensor_string)
            if self.connected and self.conn_handle is not None:
                 self._send_notification(sensor_string, handle=self.combined_sensor_handle)
        except OSError as e_write: self._handle_ble_os_error(e_write, "Combined Sensor Write")
        except Exception as e: log_event("ERROR", f"Unexpected Combined Sensor Write Err: {e}")

    def update_illuminance_characteristic(self):
        if self.illuminance_handle is None or not self.ble.active(): return
        lux_value = last_lux if last_lux is not None else 0.0
        lux_data = struct.pack('<f', lux_value)
        try:
            self.ble.gatts_write(self.illuminance_handle, lux_data)
            if self.connected and self.conn_handle is not None:
                 self._send_notification(lux_data, handle=self.illuminance_handle)
        except OSError as e_write: self._handle_ble_os_error(e_write, "Illuminance Write")
        except Exception as e: log_event("ERROR", f"Unexpected Illuminance Write Err: {e}")

    def _handle_recipe_write(self):
        if self.recipe_handle is None: return
        try:
            val = self.ble.gatts_read(self.recipe_handle)
            if val and len(val) == 1:
                idx = val[0]; print(f"BLE Rx: Set Recipe Index = {idx}"); log_event("BLE", f"Rx Recipe Index: {idx}")
                if self.lights.auto_cycle_enabled:
                    self.lights.toggle_auto_cycle(); self._send_notification(struct.pack('<B', self.NTF_AUTO_CYCLE_DISABLED)); time.sleep_ms(30)
                success = self.lights.set_recipe_by_index(idx)
                self._send_notification(struct.pack('<B', self.NTF_ACK_COMMAND_RECEIVED if success else self.NTF_ERROR_INVALID_COMMAND))
            else:
                log_event("WARN", f"Invalid BLE Recipe Write: Len={len(val) if val else 'None'}")
                self._send_notification(struct.pack('<B', self.NTF_ERROR_INVALID_COMMAND))
        except Exception as e:
            log_event("ERROR", f"Error handling Recipe write: {e}")
            try: self._send_notification(struct.pack('<B', self.NTF_ERROR_INVALID_COMMAND))
            except: pass

    def _handle_custom_write(self):
        if self.custom_handle is None: return
        try:
            val = self.ble.gatts_read(self.custom_handle)
            if val and len(val) == 4:
                r, g, b, w = struct.unpack('<BBBB', val); print(f"BLE Rx: Set Custom RGBW = ({r},{g},{b},{w})"); log_event("BLE", f"Rx Custom RGBW: R={r}, G={g}, B={b}, W={w}")
                if self.lights.auto_cycle_enabled:
                    self.lights.toggle_auto_cycle(); self._send_notification(struct.pack('<B', self.NTF_AUTO_CYCLE_DISABLED)); time.sleep_ms(30)
                success = self.lights.set_custom_rgbw(r, g, b, w)
                self._send_notification(struct.pack('<B', self.NTF_ACK_COMMAND_RECEIVED if success else self.NTF_ERROR_INVALID_COMMAND))
            else:
                log_event("WARN", f"Invalid BLE Custom RGBW Write: Len={len(val) if val else 'None'}")
                self._send_notification(struct.pack('<B', self.NTF_ERROR_INVALID_COMMAND))
        except Exception as e:
            log_event("ERROR", f"Error handling Custom RGBW write: {e}")
            try: self._send_notification(struct.pack('<B', self.NTF_ERROR_INVALID_COMMAND))
            except: pass

    def _handle_control_write(self):
        if self.control_handle is None: return
        try:
            cmd_bytes = self.ble.gatts_read(self.control_handle)
            if cmd_bytes and len(cmd_bytes) >= 1:
                cmd_code = cmd_bytes[0]; payload = cmd_bytes[1:]
                self._process_control_command(cmd_code, payload)
            else: log_event("WARN", f"Empty/Invalid BLE Control Write (len={len(cmd_bytes) if cmd_bytes else 'None'}).")
        except Exception as e:
            log_event("ERROR", f"Error handling Control write: {e}")
            try: self._send_notification(struct.pack('<B', self.NTF_ERROR_INVALID_COMMAND))
            except: pass

    def _process_control_command(self, cmd_code, payload):
        global current_on_time_str, current_off_time_str, current_active_recipe_name
        CMD_SET_OFF = 0; CMD_SET_ON_ACTIVE_RECIPE = 1; CMD_TOGGLE_AUTO_CYCLE = 2
        CMD_REQUEST_SETTINGS = 12; CMD_SET_ACTIVE_RECIPE_IDX = 13; CMD_SET_ON_TIME = 14
        CMD_SET_OFF_TIME = 15; CMD_REQUEST_STATUS = 20; CMD_SET_RTC_TIME = 30
        print(f"Processing BLE Control Command: Code={cmd_code}, PayloadLen={len(payload)}")
        log_event("BLE", f"Rx Ctrl Cmd: Code={cmd_code}, PayloadLen={len(payload)}")
        cmd_handled = False; send_ack = True
        try:
            if cmd_code == CMD_SET_OFF:
                cmd_handled = True; log_event("BLE", "Cmd: Lights OFF")
                if self.lights.auto_cycle_enabled: self.lights.toggle_auto_cycle(); self._send_notification(struct.pack('<B', self.NTF_AUTO_CYCLE_DISABLED)); time.sleep_ms(30)
                self.lights.set_recipe_by_name('off')
            elif cmd_code == CMD_SET_ON_ACTIVE_RECIPE:
                cmd_handled = True; log_event("BLE", f"Cmd: Lights ON (Recipe: {current_active_recipe_name})")
                if self.lights.auto_cycle_enabled: self.lights.toggle_auto_cycle(); self._send_notification(struct.pack('<B', self.NTF_AUTO_CYCLE_DISABLED)); time.sleep_ms(30)
                self.lights.set_recipe_by_name(current_active_recipe_name)
            elif cmd_code == CMD_TOGGLE_AUTO_CYCLE:
                cmd_handled = True; send_ack = False; log_event("BLE", "Cmd: Toggle Auto Cycle")
                is_enabled = self.lights.toggle_auto_cycle(); n_code = self.NTF_AUTO_CYCLE_ENABLED if is_enabled else self.NTF_AUTO_CYCLE_DISABLED
                self._send_notification(struct.pack('<B', n_code))
            elif cmd_code == CMD_SET_ACTIVE_RECIPE_IDX:
                cmd_handled = True; send_ack = False
                if len(payload) == 1:
                    idx = payload[0]; log_event("BLE", f"Cmd: Set Active Recipe Index = {idx}")
                    if 0 <= idx < len(config.RECIPE_KEYS):
                        if not save_settings(current_on_time_str, current_off_time_str, config.RECIPE_KEYS[idx]): self._send_notification(struct.pack('<B', self.NTF_ERROR_INVALID_COMMAND))
                    else: self._send_notification(struct.pack('<B', self.NTF_ERROR_INVALID_COMMAND))
                else: self._send_notification(struct.pack('<B', self.NTF_ERROR_INVALID_COMMAND))
            elif cmd_code == CMD_SET_ON_TIME:
                cmd_handled = True; send_ack = False
                if len(payload) == 2:
                    time_str = f"{payload[0]:02d}:{payload[1]:02d}"; log_event("BLE", f"Cmd: Set ON Time = {time_str}")
                    if not save_settings(time_str, current_off_time_str, current_active_recipe_name): self._send_notification(struct.pack('<B', self.NTF_ERROR_INVALID_COMMAND))
                else: self._send_notification(struct.pack('<B', self.NTF_ERROR_INVALID_COMMAND))
            elif cmd_code == CMD_SET_OFF_TIME:
                cmd_handled = True; send_ack = False
                if len(payload) == 2:
                    time_str = f"{payload[0]:02d}:{payload[1]:02d}"; log_event("BLE", f"Cmd: Set OFF Time = {time_str}")
                    if not save_settings(current_on_time_str, time_str, current_active_recipe_name): self._send_notification(struct.pack('<B', self.NTF_ERROR_INVALID_COMMAND))
                else: self._send_notification(struct.pack('<B', self.NTF_ERROR_INVALID_COMMAND))
            elif cmd_code == CMD_REQUEST_SETTINGS:
                cmd_handled = True; send_ack = False; log_event("BLE", "Cmd: Request Settings")
                self._send_settings_update_notification(); time.sleep_ms(20); self.update_combined_sensor_characteristic(); time.sleep_ms(20)
                if self.illuminance_handle is not None: self.update_illuminance_characteristic(); time.sleep_ms(20)
                self._send_memory_update_notification(); time.sleep_ms(20); self._send_time_update_notification()
            elif cmd_code == CMD_REQUEST_STATUS:
                cmd_handled = True; send_ack = False; log_event("BLE", "Cmd: Request Status")
                rgbw = self.lights.get_current_rgbw(); self._send_notification(struct.pack('<BBBBB', self.NTF_STATUS_UPDATE, *rgbw))
            elif cmd_code == CMD_SET_RTC_TIME:
                cmd_handled = True; send_ack = False; log_event("BLE", "Cmd: Set Pico Time")
                if len(payload) == 8:
                    try:
                        yr, mo, d, hr, mn, sc, wdjs = struct.unpack('<HBBBBBB', payload)
                        if not (2023<=yr<=2100 and 1<=mo<=12 and 1<=d<=31 and 0<=hr<=23 and 0<=mn<=59 and 0<=sc<=59 and 0<=wdjs<=6): raise ValueError("Invalid date/time component")
                        wdmp = (wdjs - 1 + 7) % 7; dt_tuple = (yr, mo, d, wdmp, hr, mn, sc, 0)
                        rtc.datetime(dt_tuple); log_event("SYSTEM", f"Time set via BLE: {dt_tuple}"); blink(2, 0.05); self._send_time_update_notification()
                    except Exception as e: log_event("ERROR", f"RTC Set BLE Error: {e}. Rx: {payload}"); self._send_notification(struct.pack('<B', self.NTF_ERROR_INVALID_COMMAND))
                else: log_event("ERROR", f"Invalid payload len {len(payload)} for CMD_SET_RTC_TIME"); self._send_notification(struct.pack('<B', self.NTF_ERROR_INVALID_COMMAND))
            if not cmd_handled: log_event("WARN", f"Unknown BLE Control Command Code: {cmd_code}"); self._send_notification(struct.pack('<B', self.NTF_ERROR_INVALID_COMMAND)); send_ack = False
            if send_ack: self._send_notification(struct.pack('<B', self.NTF_ACK_COMMAND_RECEIVED))
        except Exception as e:
            log_event("ERROR", f"Unexpected error processing BLE cmd {cmd_code}: {e}"); s = io.StringIO(); sys.print_exception(e, s); log_event("ERROR", "Traceback:\n" + s.getvalue())
            try: self._send_notification(struct.pack('<B', self.NTF_ERROR_INVALID_COMMAND))
            except: pass

    def _send_settings_update_notification(self):
        if not self.connected or self.control_handle is None: return
        try:
            on_h, on_m = map(int, current_on_time_str.split(':')); off_h, off_m = map(int, current_off_time_str.split(':'))
            active_idx = config.RECIPE_KEYS.index('off');
            try:
                 if current_active_recipe_name in config.RECIPE_KEYS: active_idx = config.RECIPE_KEYS.index(current_active_recipe_name)
            except ValueError: pass
            data = struct.pack('<BBBBBB', self.NTF_SETTINGS_UPDATE, on_h, on_m, off_h, off_m, active_idx); self._send_notification(data)
            # log_event("BLE", f"Tx Settings Notify: ON={on_h:02d}:{on_m:02d}, OFF={off_h:02d}:{off_m:02d}, Idx={active_idx}")
        except Exception as e: log_event("ERROR", f"Failed send settings notify: {e}")

    def _send_memory_update_notification(self):
        if not self.connected or self.control_handle is None: return
        try: mem_free = gc.mem_free(); data = struct.pack('<BI', self.NTF_MEMORY_UPDATE, mem_free); self._send_notification(data)
        except Exception as e: log_event("ERROR", f"Failed send memory notify: {e}")

    def _send_time_update_notification(self):
        if not self.connected or self.control_handle is None: return
        try: now = rtc.datetime(); wdjs = (now[3] + 1) % 7; data = struct.pack('<BHBBBBBB', self.NTF_TIME_UPDATE, now[0], now[1], now[2], now[4], now[5], now[6], wdjs); self._send_notification(data)
        except Exception as e: log_event("ERROR", f"Failed send time notify: {e}")

    def _send_notification(self, data, handle=None):
        global ble_needs_restart
        if handle is None: handle = self.control_handle
        if self.connected and self.conn_handle is not None and handle is not None:
            try: self.ble.gatts_notify(self.conn_handle, handle, data)
            except OSError as e: self._handle_ble_os_error(e, f"Notification (H={handle})")
            except Exception as e: log_event("ERROR", f"Unexpected BLE Notify Error (H={handle}): {e}"); s = io.StringIO(); sys.print_exception(e, s); log_event("ERROR", "Traceback:\n" + s.getvalue())

    def _handle_ble_os_error(self, os_error, context="BLE Operation"):
        global ble_needs_restart
        log_event("ERROR", f"{context} OSError {os_error.args[0]}: {os_error}")
        print(f"{context} Error (OSCode {os_error.args[0]}): {os_error}")
        disconnect_codes = [10, 11, 19, 104, 128]
        if os_error.args[0] in disconnect_codes:
            print(f"OS Error {os_error.args[0]} suggests disconnection.")
            if self.connected:
                print("Forcing disconnect state due to OS error..."); log_event("BLE", f"Forcing disconnect state due to OSError {os_error.args[0]} during {context}")
                self.connected = False; self.conn_handle = None
                log_event("BLE", f"Signaling main loop for advertising restart after OSError {os_error.args[0]}.")
                ble_needs_restart = True

    def cleanup(self):
        print("--- Starting BLE Cleanup ---")
        if self.connected and self.conn_handle is not None:
            print(f"BLE Cleanup: Disconnecting handle {self.conn_handle}")
            try: self.ble.gap_disconnect(self.conn_handle); time.sleep_ms(500)
            except OSError as e: print(f"BLE Cleanup: Disconnect error (ignored): {e}")
        print("BLE Cleanup: Stopping advertising...")
        try: self.ble.gap_advertise(None); time.sleep_ms(100)
        except Exception as e: print(f"BLE Cleanup: Error stopping advertising (ignored): {e}")
        print("BLE Cleanup: Deactivating radio...")
        try: self.ble.active(False)
        except Exception as e: log_event("ERROR", f"Error during BLE radio deactivation: {e}")
        self.connected = False; self.conn_handle = None
        print("--- BLE Cleanup Complete ---")

# ---------------------------------------------------------------------------
# --- Main Execution Block ---
# ---------------------------------------------------------------------------
def main():
    global light_controller_instance, bt_instance, rtc, event_log_file_handle
    global last_sensor_read_ms, last_temp_c, last_humidity, last_co2, last_pressure, last_lux
    global auto_cycle_light_should_be_on, sensor_manager
    global csv_log_file_path, ble_needs_restart

    controller_version = "4.1.13-syntax-fix" # Updated version number

    try: # Early init
        ensure_directory(config.LOGS_DIRECTORY)
        csv_log_file_path = f"{config.LOGS_DIRECTORY}/{config.SENSOR_LIGHT_LOG_FILE}"
        if event_log_file_handle is None: event_log_file_handle = open(config.LOG_EVENT_FILE, "a")
    except Exception as e: print(f"!!! CRITICAL: Failed early log/dir init: {e}")

    log_event("SYSTEM", f"--- Controller Startup v{controller_version} ---")
    print(f"\n--- PicoLight Controller v{controller_version} ---")
    try:
        fw_version = f"{sys.implementation.name} v{sys.implementation.version} on {sys.platform}"
        print(f"Firmware: {fw_version}"); log_event("SYSTEM", f"Firmware: {fw_version}")
    except Exception as e: log_event("WARN", f"Could not get fw version: {e}")
    gc.collect()
    mem_initial = gc.mem_free()
    print(f"Initial Memory Free: {mem_initial} bytes"); log_event("SYSTEM", f"Initial Memory Free: {mem_initial} bytes")
    blink(1)

    load_settings()

    try: # RTC Init
        current_dt = rtc.datetime()
        if current_dt[0] < 2023:
            print("RTC year invalid, resetting."); rtc.datetime((2023, 1, 1, 0, 0, 0, 0, 0))
            log_event("SYSTEM", "RTC reset to default.")
            current_dt = rtc.datetime()
        log_event("SYSTEM", f"RTC OK. Time: {current_dt}")
        print(f"RTC Time: {current_dt[0]}-{current_dt[1]:02d}-{current_dt[2]:02d} {current_dt[4]:02d}:{current_dt[5]:02d}:{current_dt[6]:02d}")
    except Exception as rtc_e: log_event("ERROR", f"RTC init failed: {rtc_e}")

    if wdt: log_event("SYSTEM", f"WDT Enabled ({config.WATCHDOG_TIMEOUT}ms)")
    else: log_event("SYSTEM", "WDT Disabled")

    # --- Initialize Hardware Controllers ---
    if np is None: log_event("ERROR", "NeoPixel None. Halting."); return
    try:
        light_controller_instance = LightController(np)
        log_event("LIGHT", f"LightController init OK. State='{light_controller_instance.get_current_recipe_name()}', Auto={light_controller_instance.auto_cycle_enabled}")
    except Exception as e: log_event("ERROR", f"FATAL LightController Error: {e}"); return

    sensor_manager = None
    any_sensor_enabled = (config.SCD4X_ENABLED or config.MPL3115A2_ENABLED or config.VEML7700_ENABLED)
    if sensor_driver_available and UnifiedSensor is not None and any_sensor_enabled:
        log_event("SENSOR", "Attempting Unified Sensor Init...")
        try:
            sensor_manager = UnifiedSensor()
            log_event("SENSOR", "Unified Sensor Init OK.")
        except Exception as e:
            log_event("ERROR", f"Unified Sensor Init FAILED: {e}")
            s = io.StringIO(); sys.print_exception(e, s); log_event("ERROR", "Traceback:\n" + s.getvalue())
    elif not any_sensor_enabled: log_event("SYSTEM", "Sensors disabled in config.")
    else: log_event("SYSTEM", "Sensor driver unavailable.")

    bt_instance = None
    if config.BT_ENABLED:
        log_event("BLE", "Attempting Bluetooth Init...")
        try:
            bt_instance = BluetoothController(light_controller_instance)
            log_event("BLE", "Bluetooth Init OK.")
        except Exception as e:
            log_event("ERROR", f"Bluetooth Init FAILED: {e}")
            s = io.StringIO(); sys.print_exception(e, s); log_event("ERROR", "Traceback:\n" + s.getvalue())
            blink(5, 0.1)
    else: log_event("SYSTEM", "Bluetooth Disabled.")

    # --- Initial Sensor Read & BLE Update ---
    if sensor_manager and bt_instance:
        log_event("SYSTEM", "Initial sensor read for BLE...")
        try:
            time.sleep_ms(config.SENSOR_POST_INIT_DELAY_MS)
            initial_sensor_data = sensor_manager.read_all()
            last_temp_c = initial_sensor_data.get('temperature'); last_humidity = initial_sensor_data.get('humidity')
            last_co2 = initial_sensor_data.get('co2'); last_pressure = initial_sensor_data.get('pressure')
            last_lux = initial_sensor_data.get('lux')
            temp_str=f"{last_temp_c:.1f}C" if last_temp_c else "N/A"; hum_str=f"{last_humidity:.1f}%" if last_humidity else "N/A"
            co2_str=f"{last_co2}ppm" if last_co2 else "N/A"; press_str=f"{last_pressure:.2f}hPa" if last_pressure else "N/A"
            lux_str=f"{last_lux:.2f}lx" if last_lux else "N/A"
            log_event("SENSOR", f"Initial Read: T={temp_str}, H={hum_str}, CO2={co2_str}, P={press_str}, L={lux_str}")
            bt_instance.update_combined_sensor_characteristic()
            if bt_instance.illuminance_handle: bt_instance.update_illuminance_characteristic()
            log_event("SYSTEM", "Initial BLE sensor chars populated.")
        except Exception as init_read_e: log_event("WARN", f"Initial sensor read failed: {init_read_e}")

    # --- Set Initial Light State ---
    log_event("SYSTEM", f"Initial Auto Cycle Mode: {'ENABLED' if light_controller_instance.auto_cycle_enabled else 'DISABLED'}")
    if light_controller_instance.auto_cycle_enabled:
        try:
            now_tuple = rtc.datetime(); current_hm = (now_tuple[4], now_tuple[5])
            on_h, on_m = map(int, current_on_time_str.split(':')); on_hm = (on_h, on_m)
            off_h, off_m = map(int, current_off_time_str.split(':')); off_hm = (off_h, off_m)
            auto_cycle_light_should_be_on = is_time_between(current_hm, on_hm, off_hm)
            target_recipe = current_active_recipe_name if auto_cycle_light_should_be_on else 'off'
            log_event("AUTO", f"Startup Auto Check: Now={current_hm} -> ShouldBeON: {auto_cycle_light_should_be_on}")
            log_event("LIGHT", f"Startup state set by Auto Cycle: Recipe='{target_recipe}'")
            light_controller_instance.set_recipe_by_name(target_recipe, config.STARTUP_FADE_DURATION)
            if led_onboard: led_onboard.value(auto_cycle_light_should_be_on)
        except Exception as e:
            log_event("ERROR", f"Error setting initial auto state: {e}. Turning OFF.")
            light_controller_instance.set_recipe_by_name('off', 0.5); auto_cycle_light_should_be_on = False
            if led_onboard: led_onboard.off()
    else: # Manual mode
        if light_controller_instance.get_current_recipe_name() != 'off':
             log_event("SYSTEM", "Manual Mode startup. Setting lights OFF.")
             light_controller_instance.set_recipe_by_name('off', config.STARTUP_FADE_DURATION)
        else: log_event("SYSTEM", "Manual Mode startup. Lights already OFF.")
        auto_cycle_light_should_be_on = False
        if led_onboard: led_onboard.off()

    gc.collect()
    mem_ready = gc.mem_free()
    print(f"--- System Ready --- (Mem Free: {mem_ready} bytes)")
    log_event("SYSTEM", f"System Ready (Mem Free: {mem_ready}). Entering main loop.")
    print("--- Starting Main Loop ---")

    last_wdt_feed_time = time.ticks_ms()
    last_gc_collect_time = time.ticks_ms()
    last_bt_sensor_update_time = time.ticks_ms()
    last_auto_cycle_check_time = time.ticks_ms()
    last_csv_log_time = time.ticks_ms()
    last_ble_restart_check = time.ticks_ms() # Timer for checking restart flag

    # --- Main Loop ---
    try:
        while True:
            current_ticks = time.ticks_ms()

            # 1. Feed WDT
            if wdt and time.ticks_diff(current_ticks, last_wdt_feed_time) >= (config.WATCHDOG_TIMEOUT // 3):
                wdt.feed(); last_wdt_feed_time = current_ticks

            # 2. Sensor Reading
            if (sensor_manager and time.ticks_diff(current_ticks, last_sensor_read_ms) >= config.SENSOR_READ_INTERVAL_MS):
                last_sensor_read_ms = current_ticks
                try:
                    sensor_data = sensor_manager.read_all()
                    last_temp_c = sensor_data.get('temperature', last_temp_c)
                    last_humidity = sensor_data.get('humidity', last_humidity)
                    last_co2 = sensor_data.get('co2', last_co2)
                    last_pressure = sensor_data.get('pressure', last_pressure)
                    last_lux = sensor_data.get('lux', last_lux)
                except Exception as e: log_event("ERROR", f"Err Sensor Read block: {e}")

            # 3. CSV Logging
            if time.ticks_diff(current_ticks, last_csv_log_time) >= config.CSV_LOG_INTERVAL_MS:
                 last_csv_log_time = current_ticks
                 try:
                     r_now, g_now, b_now, w_now = light_controller_instance.get_current_rgbw()
                     log_sensor_light_csv(last_temp_c, last_humidity, last_co2, last_pressure, last_lux, r_now, g_now, b_now, w_now)
                 except Exception as e: log_event("ERROR", f"Err CSV logging trigger: {e}")

            # 4. Bluetooth Periodic Tasks (Sensor Updates & Restart Check)
            if bt_instance:
                # Sensor Updates (if connected)
                if (bt_instance.connected and time.ticks_diff(current_ticks, last_bt_sensor_update_time) >= config.BT_SENSOR_UPDATE_INTERVAL_MS):
                    last_bt_sensor_update_time = current_ticks
                    try:
                        if bt_instance.combined_sensor_handle: bt_instance.update_combined_sensor_characteristic(); time.sleep_ms(10)
                        if bt_instance.illuminance_handle: bt_instance.update_illuminance_characteristic()
                    except Exception as ble_e: log_event("ERROR", f"Main loop BLE sensor update err: {ble_e}")

                # Advertising Restart Check (runs periodically whether connected or not)
                if time.ticks_diff(current_ticks, last_ble_restart_check) >= config.BT_RESTART_CHECK_INTERVAL_MS: # e.g., 5000ms
                    last_ble_restart_check = current_ticks
                    if ble_needs_restart:
                        if not bt_instance.connected: # Only restart if not connected
                            print("Attempting BLE advertising restart from main loop...")
                            log_event("BLE", "Attempting advertising restart from main loop")
                            try:
                                # Clear flag *before* attempting restart
                                ble_needs_restart = False
                                # Run GC before attempting memory-intensive operation
                                gc.collect()
                                time.sleep_ms(50) # Short delay after GC
                                bt_instance._start_advertising()
                                # Flag is cleared inside _start_advertising on success,
                                # but needs to be set again if it fails (done in _start_advertising)
                            except Exception as e:
                                log_event("ERROR", f"Error restarting advertising from main loop: {e}")
                                print(f"!!! Error restarting advertising: {e}")
                                ble_needs_restart = True # Set flag again to retry later if error occurred
                        else:
                            # If connected, but flag was set somehow, clear it.
                            ble_needs_restart = False

            # 5. Auto Cycle Logic (Schedule Check)
            if (light_controller_instance.auto_cycle_enabled and
                time.ticks_diff(current_ticks, last_auto_cycle_check_time) >= config.AUTO_CYCLE_CHECK_INTERVAL_MS):
                last_auto_cycle_check_time = current_ticks
                try:
                    now_tuple = rtc.datetime(); current_hm = (now_tuple[4], now_tuple[5])
                    on_h, on_m = map(int, current_on_time_str.split(':')); on_hm = (on_h, on_m)
                    off_h, off_m = map(int, current_off_time_str.split(':')); off_hm = (off_h, off_m)
                    desired_on_state = is_time_between(current_hm, on_hm, off_hm)

                    if desired_on_state != auto_cycle_light_should_be_on:
                        auto_cycle_light_should_be_on = desired_on_state
                        new_state_str = "ON" if desired_on_state else "OFF"
                        target_recipe = current_active_recipe_name if desired_on_state else 'off'
                        log_event("AUTO", f"Schedule Transition -> Turn {new_state_str} using '{target_recipe}'")
                        print(f"Auto Cycle: Time {current_hm[0]:02d}:{current_hm[1]:02d} -> Turn {new_state_str} ('{target_recipe}')")
                        light_controller_instance.set_recipe_by_name(target_recipe, config.FADE_DURATION)
                        if led_onboard: led_onboard.value(desired_on_state)
                        if bt_instance and bt_instance.connected:
                             time.sleep_ms(50); bt_instance._update_light_characteristics()
                except Exception as e: log_event("ERROR", f"Auto-Cycle logic err: {e}")

            # 6. Garbage Collection
            if time.ticks_diff(current_ticks, last_gc_collect_time) >= config.GC_INTERVAL_MS:
                mem_before = gc.mem_free(); gc.collect(); mem_after = gc.mem_free()
                last_gc_collect_time = current_ticks; freed = mem_before - mem_after
                if freed > 500: log_event("SYSTEM", f"GC ran. Freed: {freed} bytes. Free: {mem_after}")

            # --- Loop Delay ---
            time.sleep_ms(config.MAIN_LOOP_DELAY_MS)

    except KeyboardInterrupt: print("\nKeyboardInterrupt. Exiting."); log_event("SYSTEM", "Shutdown via KeyboardInterrupt.")
    except Exception as e:
        print("\n--- !!! FATAL RUNTIME ERROR !!! ---")
        log_event("ERROR", f"Fatal Runtime Error: {type(e).__name__}: {e}")
        try:
            s = io.StringIO(); sys.print_exception(e, s); print(s.getvalue())
            log_event("ERROR", "Traceback:\n" + s.getvalue())
        except Exception as log_tb_err: log_event("ERROR", f"Could not log traceback: {log_tb_err}")

    finally: # Cleanup Sequence
        print("\n--- Starting Cleanup Sequence ---"); log_event("SYSTEM", "Cleanup sequence started.")
        if sensor_manager and hasattr(sensor_manager, 'scd4x') and sensor_manager.scd4x:
            try: print("Stopping SCD4X..."); sensor_manager.scd4x.stop_periodic_measurement(); time.sleep(0.6); log_event("SENSOR", "SCD4X stop sent")
            except Exception as e: log_event("ERROR", f"SCD4X cleanup err: {e}")
        if light_controller_instance and np:
            try: print("NeoPixels OFF..."); light_controller_instance.set_recipe_by_name('off', 0.1); log_event("LIGHT", "NeoPixels OFF cleanup")
            except Exception as e: log_event("ERROR", f"NeoPixel cleanup err: {e}")
        if led_onboard:
            try: led_onboard.off(); print("Onboard LED OFF.")
            except Exception: pass
        if bt_instance:
            try: print("Cleaning up Bluetooth..."); bt_instance.cleanup()
            except Exception as e: log_event("ERROR", f"Bluetooth cleanup err: {e}")
        if event_log_file_handle is not None:
            try:
                # --- CORRECTED LINES START ---
                gc.collect() # Run GC before getting final memory
                mem_final = gc.mem_free()
                log_event("SYSTEM", f"--- Controller Stop (Mem Free: {mem_final}) ---")

                event_log_file_handle.close()
                print("Event log closed.")
                # --- CORRECTED LINES END ---
                event_log_file_handle = None # Clear handle
            except Exception as e:
                print(f"Event log close err: {e}")

        # --- CORRECTED LINES START ---
        print("--- Cleanup Complete. ---")
        gc.collect() # Final GC
        # --- CORRECTED LINES END ---

# ---------------------------------------------------------------------------
# --- Script Entry Point ---
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    main()

# --- END OF FILE main.py v4.1.13-syntax-fix ---