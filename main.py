# main.py - LED Light Controller for Pi Pico with Bluetooth support
import time
import machine
import neopixel
import gc
import sys
import bluetooth
import struct

# Import configuration
import config

# ---------------------------------------------------------------------------
# Onboard LED Setup
# ---------------------------------------------------------------------------
if config.ENABLE_ONBOARD_LED:
    led_onboard = machine.Pin("LED", machine.Pin.OUT)

    def blink(times=1, delay=0.1):
        for _ in range(times):
            led_onboard.on()
            time.sleep(delay)
            led_onboard.off()
            time.sleep(delay)
else:
    def blink(times=1, delay=0.1):
        pass  # Do nothing if LED is disabled

# ---------------------------------------------------------------------------
# Watchdog Setup
# ---------------------------------------------------------------------------
if config.WATCHDOG_TIMEOUT > 0:
    wdt = machine.WDT(timeout=config.WATCHDOG_TIMEOUT)
else:
    wdt = None

# ---------------------------------------------------------------------------
# Initialize the NeoPixel strip
# ---------------------------------------------------------------------------
try:
    np = neopixel.NeoPixel(machine.Pin(config.PIN_NEOPIXEL), config.NUM_PIXELS, bpp=4)
    print(f"NeoPixel initialized on pin {config.PIN_NEOPIXEL} with {config.NUM_PIXELS} LEDs")
    blink(2)  # Double blink on successful initialization
except Exception as e:
    print(f"Error initializing NeoPixel: {e}")
    blink(10, 0.05)  # Rapid blinking indicates error
    raise

# ---------------------------------------------------------------------------
# Light Controller Class
# ---------------------------------------------------------------------------
class LightController:
    def __init__(self, neopixel_obj):
        self.np = neopixel_obj
        self.current_recipe = None  # Start with undefined state
        self.auto_cycle_enabled = config.BT_AUTO_CYCLE

    def set_all(self, r, g, b, w):
        """Set all pixels to the same color without flickering."""
        for i in range(config.NUM_PIXELS):
            self.np[i] = (r, g, b, w)

        irq_state = machine.disable_irq()
        try:
            self.np.write()
        finally:
            machine.enable_irq(irq_state)

        if wdt:
            wdt.feed()

    def fade_to(self, target_recipe, duration_sec=5):
        """
        Gradually fade from the current state to target_recipe over duration_sec.
        If current_recipe is None or the same as target_recipe, sets instantly.
        """
        if self.current_recipe is None or self.current_recipe == target_recipe:
            self.set_all(*target_recipe)
            self.current_recipe = target_recipe
            return

        # ADDED: Skip fade for very short durations
        if duration_sec < 0.5:
            self.set_all(*target_recipe)
            self.current_recipe = target_recipe
            return

        start_recipe = self.current_recipe
        steps = max(5, int(duration_sec * 5))  # 5 steps per second
        step_time = duration_sec / steps

        for step in range(steps + 1):
            if step == steps:  # final step hits the target exactly
                self.set_all(*target_recipe)
            else:
                progress = step / steps
                r = int(start_recipe[0] + (target_recipe[0] - start_recipe[0]) * progress)
                g = int(start_recipe[1] + (target_recipe[1] - start_recipe[1]) * progress)
                b = int(start_recipe[2] + (target_recipe[2] - start_recipe[2]) * progress)
                w = int(start_recipe[3] + (target_recipe[3] - start_recipe[3]) * progress)
                self.set_all(r, g, b, w)

            # Sleep between steps
            time.sleep(step_time)

            # ADDED: Occasionally collect garbage to prevent memory issues on large fades
            if step % 5 == 0:
                gc.collect()

            if wdt:
                wdt.feed()

        self.current_recipe = target_recipe

    def set_recipe_by_name(self, recipe_name, fade_duration=None):
        """Set lights using a recipe name."""
        if recipe_name in config.LIGHT_RECIPES:
            if fade_duration is None:
                fade_duration = config.FADE_DURATION
            print(f"Setting lights to recipe: {recipe_name}")
            self.fade_to(config.LIGHT_RECIPES[recipe_name], fade_duration)
            return True
        else:
            print(f"Recipe '{recipe_name}' not found.")
            return False

    def set_recipe_by_index(self, index, fade_duration=None):
        """Set lights using a recipe index (from config.RECIPE_KEYS)."""
        if 0 <= index < len(config.RECIPE_KEYS):
            recipe_name = config.RECIPE_KEYS[index]
            return self.set_recipe_by_name(recipe_name, fade_duration)
        else:
            print(f"Recipe index {index} out of range.")
            return False

    def set_custom_rgbw(self, r, g, b, w, fade_duration=None):
        """Set lights to custom RGBW values."""
        if fade_duration is None:
            fade_duration = config.FADE_DURATION

        # Ensure values are valid
        r = max(0, min(255, r))
        g = max(0, min(255, g))
        b = max(0, min(255, b))
        w = max(0, min(255, w))

        target = (r, g, b, w)
        print(f"Setting lights to custom RGBW: {target}")
        self.fade_to(target, fade_duration)
        return True

    def toggle_auto_cycle(self):
        """Toggle automatic light cycling."""
        self.auto_cycle_enabled = not self.auto_cycle_enabled
        print(f"Auto cycle {'enabled' if self.auto_cycle_enabled else 'disabled'}")
        return self.auto_cycle_enabled

    def get_current_rgbw(self):
        """Get current RGBW values as a tuple."""
        return self.current_recipe if self.current_recipe else (0, 0, 0, 0)

    def get_recipe_list(self):
        """Get the list of available recipes."""
        return list(config.LIGHT_RECIPES.keys())


# ---------------------------------------------------------------------------
# Bluetooth Controller Class
# ---------------------------------------------------------------------------
class BluetoothController:
    def __init__(self, light_controller):
        self.lights = light_controller
        self.ble = bluetooth.BLE()
        self.ble.active(True)
        self.connected = False
        self.conn_handle = None

        self.svc_uuid = bluetooth.UUID(config.BLE_SERVICE_UUID)
        self.recipe_char_uuid = bluetooth.UUID(config.BLE_RECIPE_CHAR_UUID)
        self.custom_char_uuid = bluetooth.UUID(config.BLE_CUSTOM_CHAR_UUID)
        self.control_char_uuid = bluetooth.UUID(config.BLE_CONTROL_CHAR_UUID)

        self._register_services()
        self._start_advertising()

    def _register_services(self):
        """Register BLE services and characteristics."""
        services = (
            (
                self.svc_uuid,
                (
                    (self.recipe_char_uuid, bluetooth.FLAG_WRITE | bluetooth.FLAG_READ),
                    (self.custom_char_uuid, bluetooth.FLAG_WRITE | bluetooth.FLAG_READ),
                    (self.control_char_uuid, bluetooth.FLAG_WRITE | bluetooth.FLAG_READ | bluetooth.FLAG_NOTIFY),
                ),
            ),
        )
        ((self.recipe_handle, self.custom_handle, self.control_handle),) = self.ble.gatts_register_services(services)

        # Set initial values
        self.ble.gatts_write(self.recipe_handle, struct.pack('<B', 0))
        self.ble.gatts_write(self.custom_handle, struct.pack('<BBBB', 0, 0, 0, 0))
        self.ble.gatts_write(self.control_handle, struct.pack('<B', 0))

        # Register IRQ
        self.ble.irq(self._irq_handler)

    def _start_advertising(self):
        """Start BLE advertising."""
        device_name = config.BT_DEVICE_NAME
        adv_payload = bytearray()
        adv_payload += b'\x02\x01\x06'  # Flags for general discovery
        adv_payload += bytes([len(device_name) + 1, 0x09]) + device_name.encode()

        # Advertise every 100ms (can adjust to conserve power)
        self.ble.gap_advertise(100, adv_payload)
        print(f"Bluetooth advertising started as '{device_name}'")

    def _irq_handler(self, event, data):
        """Handle BLE events."""
        if event == 1:  # _IRQ_CENTRAL_CONNECT
            self.connected = True
            self.conn_handle, _, _ = data
            print(f"BLE Connected, handle: {self.conn_handle}")
            blink(3, 0.1)

        elif event == 2:  # _IRQ_CENTRAL_DISCONNECT
            self.connected = False
            self.conn_handle = None
            print("BLE Disconnected")
            self._start_advertising()
            blink(1, 0.3)

        elif event == 3:  # _IRQ_GATTS_WRITE
            conn_handle, attr_handle = data

            if attr_handle == self.recipe_handle:
                value = self.ble.gatts_read(self.recipe_handle)
                if len(value) == 1:
                    recipe_idx = value[0]
                    print(f"BLE: Recipe index {recipe_idx} selected")
                    # ADDED: If user picks a recipe, disable auto-cycle
                    self.lights.auto_cycle_enabled = False

                    if 0 <= recipe_idx < len(config.RECIPE_KEYS):
                        recipe_name = config.RECIPE_KEYS[recipe_idx]
                        self.lights.set_recipe_by_name(recipe_name)
                    else:
                        print(f"Invalid recipe index: {recipe_idx}")
                else:
                    print(f"Invalid recipe value format: {value}")

            elif attr_handle == self.custom_handle:
                value = self.ble.gatts_read(self.custom_handle)
                if len(value) == 4:
                    r, g, b, w = struct.unpack('<BBBB', value)
                    print(f"BLE: Custom RGBW set to ({r}, {g}, {b}, {w})")
                    # ADDED: If user picks a custom color, disable auto-cycle
                    self.lights.auto_cycle_enabled = False
                    self.lights.set_custom_rgbw(r, g, b, w)

            elif attr_handle == self.control_handle:
                value = self.ble.gatts_read(self.control_handle)
                if len(value) == 1:
                    command = value[0]
                    print(f"BLE: Control command {command} received")
                    self._process_command(command)

    def _process_command(self, command):
        """Process control commands."""
        if command == 0:
            print("BLE Command: Lights OFF")
            # ADDED: Also disable auto-cycle if user explicitly turns off
            self.lights.auto_cycle_enabled = False
            self.lights.set_recipe_by_name('off')

        elif command == 1:
            print("BLE Command: Lights ON")
            # We'll turn lights on using ACTIVE_RECIPE or fallback
            self.lights.auto_cycle_enabled = False
            fallback = getattr(config, 'ACTIVE_RECIPE', 'balanced')
            if fallback not in config.LIGHT_RECIPES:
                fallback = 'balanced'
            self.lights.set_recipe_by_name(fallback)

        elif command == 2:
            print("BLE Command: Toggle auto cycle")
            auto_enabled = self.lights.toggle_auto_cycle()
            if self.conn_handle is not None:
                # Send back a small notification indicating new auto state
                self.ble.gatts_notify(self.conn_handle, self.control_handle, struct.pack('<B', 2 if auto_enabled else 3))

        elif command == 3:
            print("BLE Command: Request recipe list")
            # The web interface has them hardcoded, so just acknowledge
            if self.conn_handle is not None:
                self.ble.gatts_notify(self.conn_handle, self.control_handle, struct.pack('<B', 4))

        elif command == 4:
            print("BLE Command: Request current status")
            rgbw = self.lights.get_current_rgbw()
            # Format: command byte + 4 RGBW bytes
            status_data = struct.pack('<BBBBB', 5, *rgbw)
            if self.conn_handle is not None:
                self.ble.gatts_notify(self.conn_handle, self.control_handle, status_data)


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------
def main():
    print("Starting LED Light Controller with Bluetooth support")
    blink(3)

    # Check if 'off' is in LIGHT_RECIPES just in case (optional).
    if 'off' not in config.LIGHT_RECIPES:
        config.LIGHT_RECIPES['off'] = (0, 0, 0, 0)  # Ensure there's always an 'off'

    # Initialize LightController
    lights = LightController(np)

    # Initialize Bluetooth
    bt = None
    if config.BT_ENABLED:
        try:
            bt = BluetoothController(lights)
            print("Bluetooth controller initialized")
            blink(2, 0.2)
        except Exception as e:
            print(f"Error initializing Bluetooth: {e}")
            blink(5, 0.1)

    # ADDED: Safely pick an active recipe name or fallback
    active_recipe_name = getattr(config, 'ACTIVE_RECIPE', 'balanced')
    if active_recipe_name not in config.LIGHT_RECIPES:
        active_recipe_name = 'balanced'

    # Initial light state
    if config.BT_AUTO_CYCLE:
        # Start with lights on using the active recipe
        lights.set_recipe_by_name(active_recipe_name)
        if config.LED_STATUS_FLASH:
            led_onboard.on() if config.ENABLE_ONBOARD_LED else None
    else:
        # If not in auto-cycle, start with lights off
        lights.set_recipe_by_name('off')

    gc.collect()

    try:
        while True:
            # Manual mode
            if not lights.auto_cycle_enabled:
                time.sleep(5)
                if wdt:
                    wdt.feed()
                continue

            # AUTO CYCLE MODE
            if lights.current_recipe is None or lights.current_recipe == config.LIGHT_RECIPES['off']:
                print("Fading lights on (auto-cycle).")
                if config.LED_STATUS_FLASH and config.ENABLE_ONBOARD_LED:
                    led_onboard.on()
                lights.fade_to(config.LIGHT_RECIPES[active_recipe_name], config.FADE_DURATION)

            # On duration
            print(f"Lights on for {config.LIGHTS_ON_DURATION / 3600} hours (auto-cycle).")
            on_end_time = time.time() + config.LIGHTS_ON_DURATION
            while time.time() < on_end_time:
                if not lights.auto_cycle_enabled:
                    break
                time.sleep(5)
                if wdt:
                    wdt.feed()

            if not lights.auto_cycle_enabled:
                continue

            # Turn off
            print("Fading lights off (auto-cycle).")
            if config.LED_STATUS_FLASH and config.ENABLE_ONBOARD_LED:
                led_onboard.off()
            lights.fade_to(config.LIGHT_RECIPES['off'], config.FADE_DURATION)

            # Off duration
            print(f"Lights off for {config.LIGHTS_OFF_DURATION / 3600} hours (auto-cycle).")
            off_end_time = time.time() + config.LIGHTS_OFF_DURATION
            while time.time() < off_end_time:
                if not lights.auto_cycle_enabled:
                    break
                time.sleep(5)
                if wdt:
                    wdt.feed()

    except KeyboardInterrupt:
        print("Program interrupted, turning off lights.")
        lights.set_all(0, 0, 0, 0)
        if config.ENABLE_ONBOARD_LED:
            led_onboard.off()

    except Exception as e:
        print(f"Error occurred: {e}")
        try:
            lights.set_all(0, 0, 0, 0)
            if config.ENABLE_ONBOARD_LED:
                led_onboard.off()
            blink(5, 0.2)
        except:
            pass
        sys.print_exception(e)
        time.sleep(5)
        machine.reset()


if __name__ == "__main__":
    main()

