"""
main.py - v4.4.9 (Final Color Correction)

Removes the incorrect (G,R,B,W) color re-ordering. With bpp=4 set,
the neopixel library correctly expects the standard (R,G,B,W) tuple,
which is how the data is already formatted. This is the definitive fix.
"""

# --- Standard Library Imports ---
import gc, io, json, os, struct, sys, time, machine

# --- Third-Party/Custom Imports ---
import bluetooth, neopixel, config

# --- Unified Sensor Driver Import ---
try:
    from unified_sensor import UnifiedSensor
    SENSOR_DRIVER_AVAILABLE = True
except ImportError:
    print("WARN: UnifiedSensor driver not found."); UnifiedSensor, SENSOR_DRIVER_AVAILABLE = None, False
except Exception as e:
    print(f"WARN: Error importing UnifiedSensor: {e}"); UnifiedSensor, SENSOR_DRIVER_AVAILABLE = None, False

# ---------------------------------------------------------------------------
# Global State and Configuration
# ---------------------------------------------------------------------------
light_controller, ble_controller, sensor_manager, rtc = None, None, None, machine.RTC()
event_log_file_handle = None
ble_needs_restart = False
current_schedule = {"version": 1, "enabled": True, "blocks": []}
schedule_active_block = None
last_schedule_check_time = 0
schedule_override_until_ms = 0
last_sensor_read_ms, last_temp_c, last_humidity, last_co2, last_pressure, last_lux = 0, None, None, None, None, None

# ---------------------------------------------------------------------------
# Helper and Logging Functions
# ---------------------------------------------------------------------------
def ensure_directory(dir_path):
    try: os.stat(dir_path)
    except OSError as e:
        if e.args[0] == 2:
            try: os.mkdir(dir_path); log_event("SYSTEM", f"Created directory: {dir_path}")
            except OSError as mkdir_e: print(f"!!! CRITICAL: Failed to create directory {dir_path}: {mkdir_e}"); raise mkdir_e
        else: print(f"!!! ERROR: Could not access directory {dir_path}: {e}"); raise e

def log_event(category, message):
    global event_log_file_handle
    try:
        if event_log_file_handle is None:
            ensure_directory(config.LOGS_DIRECTORY)
            event_log_file_handle = open(config.LOG_EVENT_FILE, "a")
        now = rtc.datetime()
        timestamp = f"{now[0]}-{now[1]:02d}-{now[2]:02d} {now[4]:02d}:{now[5]:02d}:{now[6]:02d}"
        log_line = f"{timestamp} [{category.upper()}] {message}\n"
        event_log_file_handle.write(log_line); event_log_file_handle.flush()
    except Exception as e:
        print(f"!!! EVENT LOGGING FAILED: {e}")
        if event_log_file_handle:
            try: event_log_file_handle.close()
            except Exception: pass
            event_log_file_handle = None

def log_sensor_data_csv():
    try:
        full_path = f"{config.LOGS_DIRECTORY}/{config.SENSOR_LIGHT_LOG_FILE}"
        file_exists = False
        try: os.stat(full_path); file_exists = True
        except OSError: file_exists = False
        with open(full_path, "a") as f:
            if not file_exists: f.write("timestamp,temperature_c,humidity_rh,co2_ppm,pressure_hpa,lux,light_recipe\n")
            now = rtc.datetime()
            timestamp = f"{now[0]}-{now[1]:02d}-{now[2]:02d}T{now[4]:02d}:{now[5]:02d}:{now[6]:02d}"
            temp = f"{last_temp_c:.2f}" if last_temp_c is not None else ""
            hum = f"{last_humidity:.2f}" if last_humidity is not None else ""
            co2 = f"{last_co2}" if last_co2 is not None else ""
            press = f"{last_pressure:.2f}" if last_pressure is not None else ""
            lux = f"{last_lux:.2f}" if last_lux is not None else ""
            recipe = light_controller.get_current_recipe_name() if light_controller else "unknown"
            f.write(f"{timestamp},{temp},{hum},{co2},{press},{lux},{recipe}\n")
    except Exception as e: log_event("ERROR", f"Failed to write to CSV log: {e}")

# ---------------------------------------------------------------------------
# Advanced Schedule Functions
# ---------------------------------------------------------------------------
def save_schedule_to_storage(schedule_data):
    try:
        with open(config.SCHEDULE_STORAGE_FILE, "w") as f: json.dump(schedule_data, f)
        log_event("SCHEDULE", f"Schedule saved with {len(schedule_data.get('blocks', []))} blocks.")
        return True
    except Exception as e: log_event("ERROR", f"Failed to save schedule: {e}"); return False

def load_schedule_from_storage():
    global current_schedule
    try:
        with open(config.SCHEDULE_STORAGE_FILE, "r") as f: loaded_schedule = json.load(f)
        if validate_schedule_data(loaded_schedule):
            current_schedule = loaded_schedule
            log_event("SCHEDULE", f"Schedule loaded with {len(current_schedule.get('blocks', []))} blocks.")
        else: log_event("WARN", "Invalid schedule data in storage. Using defaults.")
    except OSError: log_event("SCHEDULE", "No schedule file found. Using defaults.")
    except Exception as e: log_event("ERROR", f"Unexpected error loading schedule: {e}")

def validate_schedule_data(data):
    if not isinstance(data, dict) or "blocks" not in data or not isinstance(data["blocks"], list): return False
    if len(data["blocks"]) > config.MAX_SCHEDULE_BLOCKS: return False
    for block in data["blocks"]:
        if not all(key in block for key in ["start", "end", "recipe", "enabled"]): return False
        if not (0 <= block["start"] <= 1439 and 0 <= block["end"] <= 1439): return False
        if block["recipe"] not in config.LIGHT_RECIPES: return False
    return True

def get_current_schedule_block():
    if not current_schedule.get("enabled", False): return None
    now = rtc.datetime()
    current_minutes = now[4] * 60 + now[5]
    for block in reversed(current_schedule.get("blocks", [])):
        if not block.get("enabled", True): continue
        start_min, end_min = block["start"], block["end"]
        if start_min <= end_min:
            if start_min <= current_minutes < end_min: return block
        else:
            if current_minutes >= start_min or current_minutes < end_min: return block
    return None

def apply_schedule_block(block):
    if schedule_override_until_ms > time.ticks_ms(): return
    recipe_name = block.get("recipe", "off") if block else "off"
    if light_controller and light_controller.get_current_recipe_name() != recipe_name:
        log_event("SCHEDULE", f"Applying recipe: '{recipe_name}'")
        fade = getattr(config, 'SCHEDULE_TRANSITION_FADE_SEC', config.FADE_DURATION)
        light_controller.set_recipe_by_name(recipe_name, fade)

def set_manual_override():
    global schedule_override_until_ms
    if getattr(config, 'SCHEDULE_RESUME_AFTER_MANUAL', True):
        delay_sec = getattr(config, 'SCHEDULE_RESUME_DELAY_SEC', 300)
        schedule_override_until_ms = time.ticks_add(time.ticks_ms(), delay_sec * 1000)
        log_event("SCHEDULE", f"Manual override set. Schedule paused for {delay_sec}s.")

def process_schedule_command(payload):
    global current_schedule
    try:
        if len(payload) < 2: return False
        version, num_blocks = payload[0], payload[1]
        if num_blocks <= config.MAX_SCHEDULE_BLOCKS and len(payload) >= (2 + num_blocks * 6):
            blocks = []
            for i in range(num_blocks):
                offset = 2 + (i * 6)
                start_h, start_m, end_h, end_m, recipe_code, enabled = struct.unpack_from('!BBBBBB', payload, offset)
                recipe_name = config.CODE_TO_RECIPE.get(recipe_code, 'off')
                blocks.append({
                    "start": start_h * 60 + start_m, "end": end_h * 60 + end_m,
                    "recipe": recipe_name, "enabled": bool(enabled)
                })
            new_schedule = {"version": version, "enabled": True, "blocks": blocks}
            if save_schedule_to_storage(new_schedule):
                current_schedule = new_schedule
                log_event("SCHEDULE", f"Saved new schedule via BLE with {len(blocks)} blocks.")
                check_and_apply_schedule(force=True)
                return True
    except Exception as e: log_event("ERROR", f"Failed processing schedule command: {e}"); return False

# ---------------------------------------------------------------------------
# Hardware Controller Classes
# ---------------------------------------------------------------------------
class LightController:
    def __init__(self, pin, num_pixels):
        # Initialize NeoPixel library in 4-channel (RGBW) mode
        self.np = neopixel.NeoPixel(machine.Pin(pin), num_pixels, bpp=4)
        self.current_recipe_name = 'off'
        
    def set_recipe_by_name(self, recipe_name, duration_sec=None):
        if recipe_name in config.LIGHT_RECIPES:
            # *** FIX: REMOVED incorrect color re-ordering ***
            # The library expects (R,G,B,W) when bpp=4, which matches our config.
            color_tuple = config.LIGHT_RECIPES[recipe_name]
            self.np.fill(color_tuple)
            self.np.write()
            self.current_recipe_name = recipe_name
            return True
        return False
        
    def get_current_recipe_name(self): return self.current_recipe_name

class BluetoothController:
    def __init__(self, light_ctrl):
        self.lights = light_ctrl
        self.ble = bluetooth.BLE(); self.ble.active(True); self.ble.irq(self._irq_handler)
        self.connected = False; self.conn_handle = None
        self._register_services(); self._start_advertising()

    def _register_services(self):
        svc_uuid = bluetooth.UUID(config.BLE_SERVICE_UUID)
        recipe_char = (bluetooth.UUID(config.BLE_RECIPE_CHAR_UUID), bluetooth.FLAG_WRITE)
        custom_char = (bluetooth.UUID(config.BLE_CUSTOM_CHAR_UUID), bluetooth.FLAG_WRITE)
        ctrl_char = (bluetooth.UUID(config.BLE_CONTROL_CHAR_UUID), bluetooth.FLAG_WRITE | bluetooth.FLAG_NOTIFY)
        sched_char = (bluetooth.UUID(config.BLE_SCHEDULE_CHAR_UUID), bluetooth.FLAG_WRITE)
        sensor_char = (bluetooth.UUID(config.BLE_COMBINED_SENSOR_CHAR_UUID), bluetooth.FLAG_READ | bluetooth.FLAG_NOTIFY)
        
        service_definition = (svc_uuid, (recipe_char, custom_char, ctrl_char, sched_char, sensor_char))
        handles = self.ble.gatts_register_services((service_definition,))
        
        (self.recipe_handle, self.custom_handle, self.control_handle, 
         self.schedule_handle, self.sensor_handle) = handles[0]
        log_event("BLE", "Services registered successfully.")

    def _start_advertising(self):
        global ble_needs_restart
        try:
            name = config.BT_DEVICE_NAME.encode()
            adv_payload = b'\x02\x01\x06' + bytes([len(name) + 1, 0x09]) + name
            self.ble.gap_advertise(config.BT_ADV_INTERVAL_US, adv_data=adv_payload)
            print(f"INFO: Advertising as '{config.BT_DEVICE_NAME}'..."); ble_needs_restart = False
        except Exception as e: log_event("ERROR", f"BLE advertising failed: {e}"); ble_needs_restart = True

    def _irq_handler(self, event, data):
        global ble_needs_restart
        _IRQ_CENTRAL_CONNECT, _IRQ_CENTRAL_DISCONNECT, _IRQ_GATTS_WRITE = 1, 2, 3
        if event == _IRQ_CENTRAL_CONNECT:
            self.conn_handle, _, _ = data; self.connected = True
            log_event("BLE", f"Connected (handle: {self.conn_handle})")
        elif event == _IRQ_CENTRAL_DISCONNECT:
            self.conn_handle, self.connected = None, False
            log_event("BLE", "Disconnected"); ble_needs_restart = True
        elif event == _IRQ_GATTS_WRITE:
            _, value_handle = data
            if value_handle == self.control_handle: self._handle_control_write()
            elif value_handle == self.schedule_handle: self._handle_schedule_write()
            elif value_handle == self.recipe_handle: self._handle_recipe_write()
            elif value_handle == self.custom_handle: self._handle_custom_write()

    def _handle_recipe_write(self):
        try:
            data = self.ble.gatts_read(self.recipe_handle)
            if data and len(data) > 0:
                recipe_idx = data[0]
                recipe_name = config.CODE_TO_RECIPE.get(recipe_idx, 'off')
                log_event("BLE", f"Received recipe command: idx={recipe_idx}, name='{recipe_name}'")
                set_manual_override()
                self.lights.set_recipe_by_name(recipe_name)
        except Exception as e: log_event("ERROR", f"Handling recipe write: {e}")

    def _handle_custom_write(self):
        try:
            data = self.ble.gatts_read(self.custom_handle)
            if data and len(data) == 4:
                r, g, b, w = struct.unpack('!BBBB', data)
                log_event("BLE", f"Received custom color: R={r} G={g} B={b} W={w}")
                set_manual_override()
                # *** FIX: REMOVED incorrect color re-ordering ***
                self.lights.np.fill((r, g, b, w))
                self.lights.np.write()
                self.lights.current_recipe_name = 'custom'
        except Exception as e: log_event("ERROR", f"Handling custom write: {e}")
            
    def _handle_control_write(self):
        try:
            data = self.ble.gatts_read(self.control_handle)
            if not data: return
            cmd_code, payload = data[0], data[1:]
            log_event("BLE", f"Received control command: code={cmd_code}")

            if cmd_code == 0:
                set_manual_override(); self.lights.set_recipe_by_name('off')
            elif cmd_code == 1:
                set_manual_override(); self.lights.set_recipe_by_name(config.ACTIVE_RECIPE)
            elif cmd_code == 12: # CMD_REQUEST_SETTINGS
                log_event("BLE", "Status requested. Sending all status notifications.")
                force_sensor_read_and_update_cache()
                self.notify_sensor_data()
                self.notify_memory_update()
                self.notify_time_update()
                self.notify_schedule_data()
            elif cmd_code == 30: # CMD_SET_RTC_TIME
                if len(payload) >= 8:
                    yr, mo, d, h, mi, s, wd_js = struct.unpack("<HBBBBBB", payload)
                    pico_weekday = wd_js if wd_js > 0 else 7
                    rtc.datetime((yr, mo, d, pico_weekday, h, mi, s, 0))
                    log_event("SYSTEM", f"RTC time set via BLE to: {yr}-{mo}-{d} {h}:{mi}:{s}")
                    self.notify_time_update()
        except Exception as e:
            log_event("ERROR", f"Handling control write: {e}")
            s = io.StringIO(); sys.print_exception(e, s); log_event("ERROR-TRACE", s.getvalue())
            
    def _handle_schedule_write(self):
        try:
            payload = self.ble.gatts_read(self.schedule_handle)
            if payload:
                log_event("BLE", f"Received {len(payload)} bytes on schedule characteristic.")
                process_schedule_command(payload)
        except Exception as e: log_event("ERROR", f"Handling schedule write: {e}")

    def notify_sensor_data(self):
        if not self.connected: return
        try:
            payload_str = f"{last_temp_c:.1f}" if last_temp_c is not None else "N/A"
            payload_str += f",{last_humidity:.1f}" if last_humidity is not None else ",N/A"
            payload_str += f",{last_co2}" if last_co2 is not None else ",N/A"
            payload_str += f",{last_pressure:.1f}" if last_pressure is not None else ",N/A"
            payload_str += f",{last_lux:.1f}" if last_lux is not None else ",N/A"
            self.ble.gatts_write(self.sensor_handle, payload_str.encode())
            self.ble.gatts_notify(self.conn_handle, self.sensor_handle)
        except Exception as e: log_event("ERROR", f"Failed to notify sensor data: {e}")

    def notify_memory_update(self):
        if not self.connected: return
        try:
            payload = struct.pack("<BI", 121, gc.mem_free())
            self.ble.gatts_write(self.control_handle, payload)
            self.ble.gatts_notify(self.conn_handle, self.control_handle)
        except Exception as e: log_event("ERROR", f"Failed to notify memory: {e}")

    def notify_time_update(self):
        if not self.connected: return
        try:
            now = rtc.datetime()
            js_weekday = now[3] if now[3] < 7 else 0
            payload = struct.pack("<BHBBBBBB", 131, now[0], now[1], now[2], now[4], now[5], now[6], js_weekday)
            self.ble.gatts_write(self.control_handle, payload)
            self.ble.gatts_notify(self.conn_handle, self.control_handle)
        except Exception as e: log_event("ERROR", f"Failed to notify time: {e}")

    def notify_schedule_data(self):
        if not self.connected: return
        try:
            blocks = current_schedule.get("blocks", [])
            num_blocks = len(blocks)
            payload = bytearray(3 + num_blocks * 6)
            payload[0] = 140
            payload[1] = current_schedule.get("version", 1)
            payload[2] = num_blocks
            
            offset = 3
            for block in blocks:
                start_mins = block.get("start", 0); end_mins = block.get("end", 0)
                recipe_name = block.get("recipe", "off"); enabled = 1 if block.get("enabled", False) else 0
                start_h, start_m = divmod(start_mins, 60); end_h, end_m = divmod(end_mins, 60)
                recipe_code = config.RECIPE_CODES.get(recipe_name, 0)
                struct.pack_into("!BBBBBB", payload, offset, start_h, start_m, end_h, end_m, recipe_code, enabled)
                offset += 6
            
            self.ble.gatts_write(self.control_handle, payload)
            self.ble.gatts_notify(self.conn_handle, self.control_handle)
            log_event("BLE", f"Notified schedule data with {num_blocks} blocks.")
        except Exception as e: log_event("ERROR", f"Failed to notify schedule: {e}")

# ---------------------------------------------------------------------------
# Main Execution Logic
# ---------------------------------------------------------------------------
def force_sensor_read_and_update_cache():
    global last_sensor_read_ms, last_temp_c, last_humidity, last_co2, last_pressure, last_lux
    if not sensor_manager: return
    try:
        sensor_data = sensor_manager.read_all()
        last_temp_c = sensor_data.get('temperature')
        last_humidity = sensor_data.get('humidity')
        last_co2 = sensor_data.get('co2')
        last_pressure = sensor_data.get('pressure')
        last_lux = sensor_data.get('lux')
        last_sensor_read_ms = time.ticks_ms()
        if any(v is not None for v in sensor_data.values()):
            log_sensor_data_csv()
    except Exception as e:
        log_event("ERROR", f"Failed during sensor read: {e}")

def check_and_apply_schedule(force=False):
    global last_schedule_check_time, schedule_active_block
    current_ticks = time.ticks_ms()
    if force or time.ticks_diff(current_ticks, last_schedule_check_time) >= config.SCHEDULE_CHECK_INTERVAL_MS:
        last_schedule_check_time = current_ticks
        new_block = get_current_schedule_block()
        if new_block != schedule_active_block:
            log_event("SCHEDULE", f"Block change detected. Old: {schedule_active_block}, New: {new_block}")
            schedule_active_block = new_block
            apply_schedule_block(schedule_active_block)

def main():
    global light_controller, ble_controller, sensor_manager
    log_event("SYSTEM", f"--- Controller Startup v{config.VERSION} ---")
    print(f"--- PicoLight Controller v{config.VERSION} ---"); gc.collect()
    print(f"Initial Memory: {gc.mem_free()} bytes free")
    load_schedule_from_storage()
    light_controller = LightController(config.PIN_NEOPIXEL, config.NUM_PIXELS)
    
    if SENSOR_DRIVER_AVAILABLE:
        try: 
            sensor_manager = UnifiedSensor()
            print("INFO: UnifiedSensor initialized successfully.")
        except Exception as e: 
            log_event("FATAL", f"Sensor init failed: {e}")
            print(f"!!! FATAL: Sensor system failed: {e}")
            sensor_manager = None
    
    print("INFO: Performing initial sensor read to populate cache...")
    force_sensor_read_and_update_cache()
    
    ble_controller = BluetoothController(light_controller)
    print("INFO: Applying initial schedule state..."); check_and_apply_schedule(force=True)
    print("--- System Initialized and Ready ---")
    try:
        while True:
            if ble_needs_restart and not ble_controller.connected:
                ble_controller._start_advertising()
            check_and_apply_schedule()
            if sensor_manager and time.ticks_diff(time.ticks_ms(), last_sensor_read_ms) >= config.SENSOR_READ_INTERVAL_MS:
                force_sensor_read_and_update_cache()
                if ble_controller and ble_controller.connected:
                    ble_controller.notify_sensor_data()
            time.sleep_ms(config.MAIN_LOOP_DELAY_MS)
            gc.collect()
    except KeyboardInterrupt: log_event("SYSTEM", "Shutdown via KeyboardInterrupt."); print("\nShutdown requested.")
    except Exception as e:
        log_event("FATAL", f"Runtime error: {e}")
        s = io.StringIO(); sys.print_exception(e, s); log_event("FATAL", "Traceback:\n" + s.getvalue())
        print(f"!!! FATAL RUNTIME ERROR: {e}")
    finally:
        if light_controller: light_controller.set_recipe_by_name('off')
        if event_log_file_handle: event_log_file_handle.close()
        print("--- Cleanup Complete. System Halted. ---")

if __name__ == "__main__":
    main()