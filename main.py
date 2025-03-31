# main.py - LED Light Controller for Pi Pico with Bluetooth support
import time
import machine
import neopixel
import gc
import sys
import bluetooth
import struct
import os

# Import configuration
import config

# ---------------------------------------------------------------------------
# Global Variables
# ---------------------------------------------------------------------------
# Schedule settings (will be updated from saved settings)
current_lights_on_duration = config.LIGHTS_ON_DURATION
current_lights_off_duration = config.LIGHTS_OFF_DURATION
current_on_hours = config.LIGHTS_ON_HOURS
current_off_hours = config.LIGHTS_OFF_HOURS
# Active recipe setting (will be updated from saved settings)
current_active_recipe_name = config.ACTIVE_RECIPE # Default from config

# Global instances (initialized in main)
light_controller_instance = None
bt_instance = None

# ---------------------------------------------------------------------------
# Persistence Functions (MODIFIED)
# ---------------------------------------------------------------------------
SETTINGS_FILE = "controller_settings.txt" # Renamed for clarity

def save_settings(on_hours, off_hours, active_recipe_name):
    """Saves ON/OFF hours and active recipe name to a file."""
    global current_lights_on_duration, current_lights_off_duration
    global current_on_hours, current_off_hours, current_active_recipe_name
    global bt_instance

    # Validate schedule hours
    try:
        on_h = int(on_hours)
        off_h = int(off_hours)
        on_h = max(0, min(24, on_h))
        off_h = max(0, min(24, off_h))
    except ValueError:
        print("Error: Invalid non-integer value for schedule hours.")
        return False

    # Validate active recipe name (must be a key in LIGHT_RECIPES)
    if active_recipe_name not in config.LIGHT_RECIPES:
        print(f"Error: Invalid active_recipe_name '{active_recipe_name}'. Must be in config.LIGHT_RECIPES.")
        # Optionally revert to default or the previous valid one? For now, fail save.
        return False

    try:
        with open(SETTINGS_FILE, "w") as f:
            f.write(f"ON_HOURS={on_h}\n")
            f.write(f"OFF_HOURS={off_h}\n")
            f.write(f"ACTIVE_RECIPE={active_recipe_name}\n") # Save recipe name
        print(f"Saved settings: ON={on_h}h, OFF={off_h}h, ActiveRecipe='{active_recipe_name}'")

        # Update global runtime variables
        current_on_hours = on_h
        current_off_hours = off_h
        current_lights_on_duration = on_h * 3600
        current_lights_off_duration = off_h * 3600
        current_active_recipe_name = active_recipe_name # Update active recipe

        # Update readable BLE characteristic if connected
        if bt_instance is not None and bt_instance.connected:
             bt_instance._update_readable_characteristics() # Update all readable values

        return True
    except Exception as e:
        print(f"Error saving settings: {e}")
        return False

def load_settings():
    """Loads settings from file, falling back to config defaults."""
    global current_lights_on_duration, current_lights_off_duration
    global current_on_hours, current_off_hours, current_active_recipe_name

    # Start with config defaults
    on_h = config.LIGHTS_ON_HOURS
    off_h = config.LIGHTS_OFF_HOURS
    active_recipe = config.ACTIVE_RECIPE

    try:
        os.stat(SETTINGS_FILE) # Check if file exists

        with open(SETTINGS_FILE, "r") as f:
            lines = f.readlines()
            settings = {}
            for line in lines:
                line = line.strip()
                if '=' in line:
                    key, value = line.split('=', 1)
                    settings[key.strip().upper()] = value.strip() # Keep value as string initially

            # Load ON hours
            if 'ON_HOURS' in settings:
                try: on_h = max(0, min(24, int(settings['ON_HOURS'])))
                except ValueError: print("Warning: Invalid ON_HOURS in settings file.")
            # Load OFF hours
            if 'OFF_HOURS' in settings:
                try: off_h = max(0, min(24, int(settings['OFF_HOURS'])))
                except ValueError: print("Warning: Invalid OFF_HOURS in settings file.")
            # Load ACTIVE_RECIPE name
            if 'ACTIVE_RECIPE' in settings:
                loaded_recipe_name = settings['ACTIVE_RECIPE']
                if loaded_recipe_name in config.LIGHT_RECIPES:
                    active_recipe = loaded_recipe_name
                else:
                     print(f"Warning: Saved ACTIVE_RECIPE '{loaded_recipe_name}' not found in config.LIGHT_RECIPES. Using default.")
                     # Keep the default from config

        print(f"Loaded settings: ON={on_h}h, OFF={off_h}h, ActiveRecipe='{active_recipe}'")

    except OSError:
        # File does not exist
        print(f"Settings file '{SETTINGS_FILE}' not found. Using config defaults and creating file.")
        # Save defaults to create the file
        save_settings(on_h, off_h, active_recipe)

    except Exception as e:
        print(f"Error loading settings: {e}. Using defaults.")
        # Attempt to save defaults if loading failed
        save_settings(on_h, off_h, active_recipe)

    # Update global runtime variables with the final determined values
    current_on_hours = on_h
    current_off_hours = off_h
    current_active_recipe_name = active_recipe # Use the validated/defaulted name
    current_lights_on_duration = on_h * 3600
    current_lights_off_duration = off_h * 3600


# ---------------------------------------------------------------------------
# Onboard LED Setup (No change)
# ---------------------------------------------------------------------------
led_onboard = None
if config.ENABLE_ONBOARD_LED:
    # ... (code as before) ...
    try:
        led_onboard = machine.Pin("LED", machine.Pin.OUT)
        led_onboard.off()
        def blink(times=1, delay=0.1):
            if led_onboard:
                for _ in range(times):
                    led_onboard.on(); time.sleep(delay); led_onboard.off(); time.sleep(delay)
            else: pass
    except Exception as e:
        print(f"Could not initialize onboard LED: {e}")
        def blink(times=1, delay=0.1): pass
else:
    def blink(times=1, delay=0.1): pass

# ---------------------------------------------------------------------------
# Watchdog Setup (No change)
# ---------------------------------------------------------------------------
wdt = None
if config.WATCHDOG_TIMEOUT > 0:
    # ... (code as before) ...
    try:
        wdt = machine.WDT(timeout=config.WATCHDOG_TIMEOUT)
        print(f"Watchdog enabled with timeout: {config.WATCHDOG_TIMEOUT}ms")
    except Exception as e:
         print(f"Could not initialize Watchdog: {e}")
         wdt = None
else:
     print("Watchdog disabled.")

# ---------------------------------------------------------------------------
# Initialize NeoPixel strip (No change)
# ---------------------------------------------------------------------------
np = None
try:
    # ... (code as before) ...
    np = neopixel.NeoPixel(machine.Pin(config.PIN_NEOPIXEL), config.NUM_PIXELS, bpp=4)
    np.fill((0, 0, 0, 0)); np.write()
    print(f"NeoPixel initialized on pin {config.PIN_NEOPIXEL} with {config.NUM_PIXELS} LEDs")
    blink(2)
except Exception as e:
    print(f"FATAL: Error initializing NeoPixel: {e}")
    blink(10, 0.05)
    raise

# ---------------------------------------------------------------------------
# Light Controller Class (No significant change needed)
# ---------------------------------------------------------------------------
class LightController:
    # ... (code as before, uses global current_active_recipe_name implicitly via main loop) ...
    def __init__(self, neopixel_obj):
        if not neopixel_obj: raise ValueError("NeoPixel object required")
        self.np = neopixel_obj; self.num_pixels = self.np.n
        self.current_recipe = config.LIGHT_RECIPES.get('off', (0,0,0,0))
        self.auto_cycle_enabled = config.BT_AUTO_CYCLE
    def set_all(self, r, g, b, w): # ... (as before) ...
        r,g,b,w=max(0,min(255,int(r))),max(0,min(255,int(g))),max(0,min(255,int(b))),max(0,min(255,int(w)))
        ct=(r,g,b,w);
        if self.current_recipe==ct:
           if wdt:wdt.feed();return
        for i in range(self.num_pixels): self.np[i]=ct
        irq=machine.disable_irq()
        try: self.np.write();self.current_recipe=ct
        except Exception as e: print(f"NP Write Err:{e}")
        finally: machine.enable_irq(irq)
        if wdt:wdt.feed()
    def fade_to(self, target_recipe, duration_sec=None): # ... (as before) ...
        if duration_sec is None: duration_sec=config.FADE_DURATION
        if not isinstance(target_recipe,tuple) or len(target_recipe)!=4:
           print(f"Err: Invalid fade target format: {target_recipe}");target_recipe=config.LIGHT_RECIPES.get('off',(0,0,0,0))
        try: tr,tg,tb,tw=[max(0,min(255,int(c))) for c in target_recipe]; target_recipe=(tr,tg,tb,tw)
        except(ValueError,TypeError): print(f"Err: Non-num in fade target: {target_recipe}");target_recipe=config.LIGHT_RECIPES.get('off',(0,0,0,0))
        start_recipe=self.current_recipe
        if not isinstance(start_recipe,tuple) or len(start_recipe)!=4:
           print(f"Warn: Invalid start state: {start_recipe}");start_recipe=config.LIGHT_RECIPES.get('off',(0,0,0,0));self.current_recipe=start_recipe
        if start_recipe==target_recipe: self.set_all(*target_recipe);return
        if duration_sec<0.1: self.set_all(*target_recipe);return
        steps=max(1,int(duration_sec*10));step_time_ms=max(1,int((duration_sec/steps)*1000))
        sr,sg,sb,sw=start_recipe;tr,tg,tb,tw=target_recipe
        dr,dg,db,dw=tr-sr,tg-sg,tb-sb,tw-sw
        for step in range(steps+1):
           prog=step/steps;r,g,b,w=max(0,min(255,int(sr+dr*prog))),max(0,min(255,int(sg+dg*prog))),max(0,min(255,int(sb+db*prog))),max(0,min(255,int(sw+dw*prog)))
           csc=(r,g,b,w)
           for i in range(self.num_pixels): self.np[i]=csc
           irq=machine.disable_irq()
           try: self.np.write()
           finally: machine.enable_irq(irq)
           if wdt:wdt.feed()
           if step<steps: time.sleep_ms(step_time_ms)
           if step>0 and step%20==0: gc.collect()
        self.set_all(*target_recipe)
    def set_recipe_by_name(self, recipe_name, fade_duration=None): # ... (as before) ...
        if recipe_name in config.LIGHT_RECIPES:
           target=config.LIGHT_RECIPES[recipe_name]; print(f"Set recipe: {recipe_name} {target}"); self.fade_to(target,fade_duration); return True
        else: print(f"Recipe '{recipe_name}' not found. Set OFF."); self.fade_to(config.LIGHT_RECIPES.get('off',(0,0,0,0)),fade_duration); return False
    def set_recipe_by_index(self, index, fade_duration=None): # ... (as before) ...
        if 0<=index<len(config.RECIPE_KEYS): return self.set_recipe_by_name(config.RECIPE_KEYS[index],fade_duration)
        else: print(f"Recipe index {index} out of range."); return False
    def set_custom_rgbw(self, r, g, b, w, fade_duration=None): # ... (as before) ...
        target=(int(r),int(g),int(b),int(w)); print(f"Set custom RGBW: {target}"); self.fade_to(target,fade_duration); return True
    def toggle_auto_cycle(self): # ... (as before) ...
        self.auto_cycle_enabled=not self.auto_cycle_enabled; print(f"Auto cycle {'enabled' if self.auto_cycle_enabled else 'disabled'}"); return self.auto_cycle_enabled
    def get_current_rgbw(self): # ... (as before) ...
        if isinstance(self.current_recipe,tuple) and len(self.current_recipe)==4: return self.current_recipe
        else: print(f"Warn: Corrupted state {self.current_recipe}. Ret OFF.");self.current_recipe=config.LIGHT_RECIPES.get('off',(0,0,0,0));return self.current_recipe
    def get_recipe_list(self): return config.RECIPE_KEYS


# ---------------------------------------------------------------------------
# Bluetooth Controller Class (MODIFIED)
# ---------------------------------------------------------------------------
class BluetoothController:
    # ... ( __init__ , _register_services, _start_advertising, _irq_handler as before ) ...
    def __init__(self, light_controller_ref):
        global bt_instance
        self.lights = light_controller_ref
        if not self.lights: raise ValueError("LightController required")
        self.ble = bluetooth.BLE(); self.ble.active(False); time.sleep_ms(100); self.ble.active(True)
        print("BLE Radio Active"); self.connected = False; self.conn_handle = None
        self.svc_uuid=bluetooth.UUID(config.BLE_SERVICE_UUID); self.recipe_char_uuid=bluetooth.UUID(config.BLE_RECIPE_CHAR_UUID)
        self.custom_char_uuid=bluetooth.UUID(config.BLE_CUSTOM_CHAR_UUID); self.control_char_uuid=bluetooth.UUID(config.BLE_CONTROL_CHAR_UUID)
        self._register_services(); self.ble.irq(self._irq_handler); print("BLE IRQ handler registered")
        self._start_advertising(); bt_instance = self
    def _register_services(self):
        recipe_char=(self.recipe_char_uuid,bluetooth.FLAG_WRITE|bluetooth.FLAG_READ,)
        custom_char=(self.custom_char_uuid,bluetooth.FLAG_WRITE|bluetooth.FLAG_READ,)
        control_char=(self.control_char_uuid,bluetooth.FLAG_WRITE|bluetooth.FLAG_READ|bluetooth.FLAG_NOTIFY,)
        light_service=(self.svc_uuid,(recipe_char,custom_char,control_char),); services=(light_service,)
        try:
            ((self.recipe_handle,self.custom_handle,self.control_handle),)=self.ble.gatts_register_services(services)
            print("BLE Services Registered (Handles): Recipe={}, Custom={}, Control={}".format(self.recipe_handle, self.custom_handle, self.control_handle))
        except Exception as e: print(f"FATAL: BLE Service Reg Err: {e}"); raise
        self._update_readable_characteristics()
    def _start_advertising(self):
        try:
            name=config.BT_DEVICE_NAME; payload=bytearray(); payload+=b'\x02\x01\x06'; payload+=bytes([len(name)+1,0x09]); payload+=name.encode('utf-8')
            self.ble.gap_advertise(100000,payload); print(f"BLE advertising started as '{name}'"); blink(1)
        except Exception as e: print(f"BLE Adv Err: {e}"); blink(5,0.1)
    def _irq_handler(self, event, data):
        if event == 1: # CONNECT
            conn, _, addr = data; self.connected = True; self.conn_handle = conn; print(f"BLE Connected, H:{self.conn_handle}"); blink(3, 0.1); self._update_readable_characteristics()
        elif event == 2: # DISCONNECT
             conn, _, _ = data
             if conn == self.conn_handle: self.connected=False; self.conn_handle=None; print("BLE Disconnected"); self._start_advertising(); blink(1, 0.3)
        elif event == 3: # WRITE
             conn, handle = data
             if conn == self.conn_handle:
                 if handle == self.recipe_handle: self._handle_recipe_write()
                 elif handle == self.custom_handle: self._handle_custom_write()
                 elif handle == self.control_handle: self._handle_control_write()

    # MODIFIED: Update readable characteristics including active recipe index
    def _update_readable_characteristics(self):
         """Writes current state (recipe, custom, schedule, active recipe) to readable characteristics."""
         try:
            # Recipe Index
            current_rgbw = self.lights.get_current_rgbw()
            current_recipe_name_for_idx = None
            for name, rgbw in config.LIGHT_RECIPES.items():
                 if rgbw == current_rgbw: current_recipe_name_for_idx = name; break
            recipe_idx = config.RECIPE_KEYS.index('off') # Default
            if current_recipe_name_for_idx in config.RECIPE_KEYS:
                 try: recipe_idx = config.RECIPE_KEYS.index(current_recipe_name_for_idx)
                 except ValueError: pass
            self.ble.gatts_write(self.recipe_handle, struct.pack('<B', recipe_idx))

            # Custom RGBA
            self.ble.gatts_write(self.custom_handle, struct.pack('<BBBB', *current_rgbw))

            # Control Characteristic (Now includes Active Recipe Index)
            # Find index of the *globally stored* current_active_recipe_name
            active_recipe_idx = config.RECIPE_KEYS.index('off') # Default if not found
            if current_active_recipe_name in config.RECIPE_KEYS:
                 try: active_recipe_idx = config.RECIPE_KEYS.index(current_active_recipe_name)
                 except ValueError: print(f"Warn: current_active_recipe_name '{current_active_recipe_name}' not in keys.")
            # Format: [0]=CmdCode(0), [1]=ON_Hours, [2]=OFF_Hours, [3]=ActiveRecipeIndex
            control_val = struct.pack('<BBBB', 0, current_on_hours, current_off_hours, active_recipe_idx)
            self.ble.gatts_write(self.control_handle, control_val)
            # print("Updated readable characteristic values.") # Less verbose

         except Exception as e:
              print(f"Warning: Failed to update readable BLE characteristics: {e}")

    # ... (_handle_recipe_write, _handle_custom_write as before) ...
    def _handle_recipe_write(self):
        try:
            val=self.ble.gatts_read(self.recipe_handle)
            if len(val)==1:
               idx=val[0]; print(f"BLE Rx Recipe Idx: {idx}")
               if self.lights.auto_cycle_enabled:
                  if self.lights.toggle_auto_cycle():pass;self._send_notification(struct.pack('<B',103))
               if not self.lights.set_recipe_by_index(idx): print(f"Invalid recipe idx: {idx}")
               self._update_readable_characteristics()
            else: print(f"Invalid recipe val fmt: {val}")
        except Exception as e: print(f"Recipe write err: {e}")
    def _handle_custom_write(self):
        try:
            val=self.ble.gatts_read(self.custom_handle)
            if len(val)==4:
               r,g,b,w=struct.unpack('<BBBB',val); print(f"BLE Rx Custom RGBW:({r},{g},{b},{w})")
               if self.lights.auto_cycle_enabled:
                  if self.lights.toggle_auto_cycle():pass;self._send_notification(struct.pack('<B',103))
               self.lights.set_custom_rgbw(r,g,b,w); self._update_readable_characteristics()
            else: print(f"Invalid custom val fmt: {val}")
        except Exception as e: print(f"Custom write err: {e}")

    # ... (_handle_control_write as before) ...
    def _handle_control_write(self):
         try:
            val=self.ble.gatts_read(self.control_handle)
            if len(val)>=1: cmd=val[0]; payload=val[1:]; self._process_control_command(cmd,payload)
            else: print("Empty control write.")
         except Exception as e: print(f"Control write err: {e}")

    # MODIFIED: Process control commands, including new command 13
    def _process_control_command(self, command, payload):
        """Process control commands based on command code."""
        global current_on_hours, current_off_hours, current_active_recipe_name # Allow modification via save_settings

        # Command Codes:
        # 0: Lights OFF
        # 1: Lights ON (to active_recipe)
        # 2: Toggle Auto Cycle
        # 10: Set ON Hours (Payload: 1 byte [0-24])
        # 11: Set OFF Hours (Payload: 1 byte [0-24])
        # 12: Request Current Schedule (& Active Recipe) -> Sends Notification 112
        # 13: Set Active Recipe (Payload: 1 byte [recipe_index])
        # 20: Request Current RGBW Status -> Sends Notification 120

        print(f"Processing CMD {command}...") # Debug

        if command == 0: # Lights OFF
            print("BLE Cmd: Lights OFF")
            if self.lights.auto_cycle_enabled:
                if self.lights.toggle_auto_cycle(): pass # Toggle off
                self._send_notification(struct.pack('<B', 103)) # Notify auto OFF
            self.lights.set_recipe_by_name('off')
            self._update_readable_characteristics() # Update state

        elif command == 1: # Lights ON
            print("BLE Cmd: Lights ON")
            if self.lights.auto_cycle_enabled:
                if self.lights.toggle_auto_cycle(): pass # Toggle off
                self._send_notification(struct.pack('<B', 103)) # Notify auto OFF
            # Use the *current* active recipe name (could have been changed)
            self.lights.set_recipe_by_name(current_active_recipe_name)
            self._update_readable_characteristics() # Update state

        elif command == 2: # Toggle auto cycle
            print("BLE Cmd: Toggle auto cycle")
            auto_enabled = self.lights.toggle_auto_cycle()
            notify_code = 102 if auto_enabled else 103
            self._send_notification(struct.pack('<B', notify_code))

        elif command == 10: # Set ON Hours
             if len(payload) == 1:
                 on_h = payload[0]
                 print(f"BLE Cmd: Set ON hours to {on_h}")
                 # Save settings preserves current active recipe
                 if save_settings(on_h, current_off_hours, current_active_recipe_name):
                     blink(1); self._send_schedule_update_notification()
                 else: print("Failed to save ON hours")
             else: print("Invalid payload length for Set ON Hours")

        elif command == 11: # Set OFF Hours
             if len(payload) == 1:
                 off_h = payload[0]
                 print(f"BLE Cmd: Set OFF hours to {off_h}")
                 # Save settings preserves current active recipe
                 if save_settings(current_on_hours, off_h, current_active_recipe_name):
                     blink(1); self._send_schedule_update_notification()
                 else: print("Failed to save OFF hours")
             else: print("Invalid payload length for Set OFF Hours")

        elif command == 12: # Request Current Schedule
             print("BLE Cmd: Request current schedule/active recipe")
             self._send_schedule_update_notification() # Sends schedule + active index

        elif command == 13: # Set Active Recipe Index
            if len(payload) == 1:
                recipe_idx = payload[0]
                print(f"BLE Cmd: Set Active Recipe Index to {recipe_idx}")
                if 0 <= recipe_idx < len(config.RECIPE_KEYS):
                    new_active_recipe_name = config.RECIPE_KEYS[recipe_idx]
                    print(f"  -> Recipe Name: '{new_active_recipe_name}'")
                    # Save settings preserves current schedule hours
                    if save_settings(current_on_hours, current_off_hours, new_active_recipe_name):
                         blink(1) # Blink on success
                         self._send_schedule_update_notification() # Confirm change
                    else:
                         print(f"Failed to save new active recipe: {new_active_recipe_name}")
                else:
                     print(f"Invalid recipe index received: {recipe_idx}")
            else:
                print("Invalid payload length for Set Active Recipe")


        elif command == 20: # Request Current RGBW Status
            print("BLE Cmd: Request current RGBW status")
            rgbw = self.lights.get_current_rgbw()
            status_data = struct.pack('<BBBBB', 120, *rgbw) # Use code 120 for response
            self._send_notification(status_data)

        else:
            print(f"Unknown control command received: {command}")

    # MODIFIED: Send schedule notification including active recipe index
    def _send_schedule_update_notification(self):
        """Sends current schedule and active recipe index via notification (Code 112)."""
        active_recipe_idx = config.RECIPE_KEYS.index('off') # Default
        if current_active_recipe_name in config.RECIPE_KEYS:
             try: active_recipe_idx = config.RECIPE_KEYS.index(current_active_recipe_name)
             except ValueError: pass
        # Format: [0]=NotifyCode(112), [1]=ON_Hours, [2]=OFF_Hours, [3]=ActiveRecipeIndex
        schedule_data = struct.pack('<BBBB', 112, current_on_hours, current_off_hours, active_recipe_idx)
        self._send_notification(schedule_data)
        # print(f"Sent Schedule Update Notification: ON={current_on_hours}h, OFF={current_off_hours}h, ActiveIdx={active_recipe_idx}")


    def _send_notification(self, data):
        """Helper function to send notifications."""
        # ... (code as before) ...
        if self.connected and self.conn_handle is not None:
            try: self.ble.gatts_notify(self.conn_handle, self.control_handle, data)
            except OSError as e: print(f"Notify Err (OSError:{e.args[0]}):{e}"); # Handle disconnect etc.
            except Exception as e: print(f"Unexpected Notify Err:{e}")


    def cleanup(self):
        """Deactivate BLE cleanly."""
        # ... (code as before) ...
        try:
             if self.connected and self.conn_handle is not None: print("Disconnecting BLE..."); self.ble.gap_disconnect(self.conn_handle); time.sleep_ms(100)
             print("Deactivating BLE radio..."); self.ble.active(False); print("BLE Radio Deactivated.")
        except Exception as e: print(f"BLE cleanup err: {e}")


# ---------------------------------------------------------------------------
# Main Entry Point (MODIFIED to use stored active recipe)
# ---------------------------------------------------------------------------
def main():
    global light_controller_instance, bt_instance # Make instances accessible

    print(f"--- PicoLight Controller v3.2 Starting ---")
    # ... (print firmware, memory, blink) ...
    if 'version' in dir(sys): print(f"Firmware: {sys.version}")
    else: print(f"Firmware: {sys.implementation.name} {sys.implementation.version}")
    print(f"Initial Free Memory: {gc.mem_free()} bytes"); blink(3)

    # --- Load ALL persistent settings ---
    load_settings() # Loads schedule AND active recipe, or creates file with defaults

    # --- Initialize Hardware ---
    if np is None: print("FATAL: NeoPixel init failed. Halting."); return
    try:
        light_controller_instance = LightController(np); print("LightController initialized.")
    except Exception as e: print(f"FATAL: LightController init err: {e}"); return

    # --- Initialize Bluetooth (conditionally) ---
    bt_instance = None
    if config.BT_ENABLED:
        try: bt_instance = BluetoothController(light_controller_instance); print("BluetoothController initialized.")
        except Exception as e: print(f"ERROR: Bluetooth init err: {e}"); blink(5, 0.1); bt_instance = None
    else: print("Bluetooth is disabled in config.")

    # --- Set Initial Light State ---
    # Auto-cycle state is now managed within LightController instance based on config value
    print(f"Initial Auto Cycle state: {'Enabled' if light_controller_instance.auto_cycle_enabled else 'Disabled'}")

    if light_controller_instance.auto_cycle_enabled:
        # Use the active recipe loaded from settings (or default)
        print(f"Auto-cycle enabled. Setting initial state to '{current_active_recipe_name}'.")
        light_controller_instance.set_recipe_by_name(current_active_recipe_name, fade_duration=1)
        if config.ENABLE_ONBOARD_LED and led_onboard: led_onboard.on()
    else:
        print("Auto-cycle disabled. Setting initial state to 'off'.")
        light_controller_instance.set_recipe_by_name('off', fade_duration=0.5)
        if config.ENABLE_ONBOARD_LED and led_onboard: led_onboard.off()

    gc.collect()
    print(f"Memory after setup: {gc.mem_free()} bytes")
    print("--- System Ready ---")

    # --- Main Loop ---
    try:
        last_wdt_feed_time = time.ticks_ms()
        cycle_state = 'UNKNOWN'
        cycle_end_time = 0

        # Determine initial cycle state if auto-cycling
        if light_controller_instance.auto_cycle_enabled:
             is_currently_off = light_controller_instance.get_current_rgbw() == config.LIGHT_RECIPES.get('off', (0,0,0,0))
             current_ticks_init = time.ticks_ms()
             if is_currently_off:
                  cycle_state = 'OFF'
                  cycle_end_time = time.ticks_add(current_ticks_init, current_lights_off_duration * 1000)
                  print(f"Auto starting in OFF state for {current_lights_off_duration / 3600:.2f}h.")
             else:
                  cycle_state = 'ON'
                  cycle_end_time = time.ticks_add(current_ticks_init, current_lights_on_duration * 1000)
                  print(f"Auto starting in ON state for {current_lights_on_duration / 3600:.2f}h.")

        while True:
            current_ticks = time.ticks_ms()

            # Feed watchdog periodically
            if wdt and time.ticks_diff(current_ticks, last_wdt_feed_time) >= 1000:
                wdt.feed(); last_wdt_feed_time = current_ticks

            # Check if mode changed
            if not light_controller_instance.auto_cycle_enabled:
                if cycle_state != 'MANUAL': print("Switched to Manual Mode."); cycle_state = 'MANUAL'
                time.sleep_ms(200); continue # Yield in manual mode

            # --- AUTO CYCLE MODE ---
            if cycle_state == 'MANUAL': # Just switched back to auto? Re-evaluate.
                 is_off = light_controller_instance.get_current_rgbw() == config.LIGHT_RECIPES.get('off',(0,0,0,0))
                 cycle_state = 'OFF' if is_off else 'ON'
                 # Reset timer based on current state to start the new period
                 duration_ms = current_lights_off_duration * 1000 if is_off else current_lights_on_duration * 1000
                 cycle_end_time = time.ticks_add(current_ticks, duration_ms)
                 print(f"Switched to Auto Mode. Current state: {cycle_state}. Next change in {duration_ms / 3600000:.2f}h.")


            # Check if the current cycle period has ended
            if time.ticks_diff(current_ticks, cycle_end_time) >= 0:
                print(f"Auto-cycle: End of {cycle_state} period reached.") # Debug

                if cycle_state == 'OFF':
                    # --- Transition to ON ---
                    # Use the globally stored current_active_recipe_name
                    print(f"Auto: Fading ON to '{current_active_recipe_name}'.")
                    if config.ENABLE_ONBOARD_LED and led_onboard: led_onboard.on()
                    light_controller_instance.fade_to(config.LIGHT_RECIPES[current_active_recipe_name], config.FADE_DURATION)
                    cycle_state = 'ON'
                    cycle_end_time = time.ticks_add(current_ticks, current_lights_on_duration * 1000)
                    print(f"Auto: Now ON for {current_lights_on_duration / 3600:.2f} hours.")

                elif cycle_state == 'ON':
                    # --- Transition to OFF ---
                    print("Auto: Fading OFF.")
                    if config.ENABLE_ONBOARD_LED and led_onboard: led_onboard.off()
                    light_controller_instance.fade_to(config.LIGHT_RECIPES['off'], config.FADE_DURATION)
                    cycle_state = 'OFF'
                    cycle_end_time = time.ticks_add(current_ticks, current_lights_off_duration * 1000)
                    print(f"Auto: Now OFF for {current_lights_off_duration / 3600:.2f} hours.")

            # Yield processor briefly
            time.sleep_ms(500) # Check cycle time etc twice per second

    # ... (except KeyboardInterrupt, Exception, finally block as before) ...
    except KeyboardInterrupt: print("\nKeyboardInterrupt. Exiting.")
    except Exception as e: print(f"\nRuntime Error:"); sys.print_exception(e); print("----")
    finally:
        print("--- Cleaning up ---")
        if light_controller_instance and np:
           try: print("Turning off NeoPixels..."); np.fill((0,0,0,0)); np.write()
           except Exception as e: print(f"NeoPixel cleanup err: {e}")
        if config.ENABLE_ONBOARD_LED and led_onboard:
           try: led_onboard.off(); print("Turned off onboard LED.")
           except Exception as e: print(f"LED cleanup err: {e}")
        if bt_instance:
           try: print("Cleaning up Bluetooth..."); bt_instance.cleanup()
           except Exception as e: print(f"BLE cleanup err: {e}")
        print("Cleanup complete.")

if __name__ == "__main__":
    main()

