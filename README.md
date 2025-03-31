# PicoLight Controller v3.5

**A responsive web-based Bluetooth LE controller for RGBW (NeoPixel) LED lights powered by a Raspberry Pi Pico W.**
<img width="369" alt="Screenshot 2025-03-31 at 2 51 42 PM" src="https://github.com/user-attachments/assets/f594eaf6-6217-474b-9209-eb5b57f22d8b" />

## Overview

PicoLight Controller allows you to wirelessly control RGBW LED strips connected to a Raspberry Pi Pico W microcontroller using any modern web browser that supports the Web Bluetooth API. Set presets, create custom colors, save local recipes, configure automatic schedules, manage multiple devices, and more.


## Features

*   **Wireless Control**: Uses Web Bluetooth for connection (no app install required).
*   **Multiple Device Support**: Connect to different PicoLight devices, identified by name.
*   **In-App Device Renaming**: Assign custom names to your devices (saved in your browser's local storage).
*   **Preset Light Recipes**: Quickly apply predefined lighting scenes categorized by use (Basic, Plants, Mood).
*   **Custom Color Control**: Fine-tune Red, Green, Blue, and White channels using sliders.
*   **Local Recipe Saving**: Save your custom color mixes in your browser for easy recall.
*   **Persistent Auto-Cycle Settings**:
    *   Set daily ON/OFF durations for the automatic schedule.
    *   Select which *predefined* recipe is used when the auto-cycle turns lights ON.
    *   These settings are saved *on the Pico device* and persist across reboots.
*   **On/Off Controls**: Simple buttons to turn lights fully on or off.
*   **Auto-Reconnect Option**: Toggle attempting to reconnect to the last used device on page load.
*   **Responsive Design**: Adapts to desktop and mobile browser sizes.
*   **Light/Dark Theme**: Toggle theme preference (saved locally).

## Requirements

### Hardware
1.  **Raspberry Pi Pico W**: Must be the 'W' version with WiFi/Bluetooth capability.
2.  **RGBW LED Strip**: NeoPixel (WS2812B type with an extra White channel) compatible strip.
3.  **Power Supply**: Adequate power supply for your *LED strip* (often 5V, check strip requirements). LEDs can draw significant current; **do not** typically power a long strip directly from the Pico's 3.3V or VBUS pin.
4.  **Logic Level Shifter (Recommended)**: If using 5V LEDs, a level shifter (e.g., 74AHCT125) is recommended to convert the Pico's 3.3V data signal to 5V for the LED strip's data input.
5.  **Jumper Wires & Connectors**.

### Software (Pico)
1.  **MicroPython Firmware**: Version specifically for Pico W (v1.20 or later recommended). [Download here](https://micropython.org/download/RPI_PICO_W/).
2.  **Project Files**:
    *   `main.py` (The main controller script)
    *   `config.py` (Configuration for hardware pins, default settings, UUIDs)

### Software (Controller Device)
1.  **Web Browser**: A browser supporting Web Bluetooth:
    *   **Recommended**: Google Chrome (Desktop/Android), Microsoft Edge (Desktop).
    *   Others: Opera, Brave, Vivaldi (Chromium-based).
    *   *Not Supported*: Firefox, Safari (standard versions on iOS/macOS often lack full support).
2.  **Operating System**: Windows 10/11, macOS, Linux, Android (iOS/iPadOS have limited Web Bluetooth support).
3.  **Bluetooth**: Enabled on your controlling device.

## Hardware Setup

1.  **LED Power**: Connect your LED strip's VCC and GND to your separate, appropriately rated power supply. **Ensure the power supply GND is also connected to one of the Pico W's GND pins.**
2.  **LED Data**:
    *   **Without Level Shifter (Not Ideal for 5V LEDs)**: Connect the LED strip's Data Input (DI) pin directly to the GPIO pin specified by `PIN_NEOPIXEL` in `config.py` (default is `GP5`). This *might* work for short strips close to the Pico, but can be unreliable.
    *   **With Level Shifter (Recommended for 5V LEDs)**: Connect the Pico's `PIN_NEOPIXEL` GPIO to the *input* of a logic level shifter channel. Connect the shifter's output to the LED strip's Data Input. Power the shifter correctly (usually requires both 3.3V from Pico and 5V from LED supply).
3.  **Pico Power**: Power the Pico W via its micro-USB port.

## Software Setup (Pico)

1.  **Flash MicroPython**: Install the latest Pico W MicroPython firmware onto your device.
2.  **Connect IDE**: Use an IDE like Thonny to connect to your Pico W.
3.  **Upload Files**: Copy `main.py` and `config.py` to the root directory of the Pico W's filesystem.
4.  **Configure `config.py`**:
    *   Verify `PIN_NEOPIXEL` matches the GPIO pin connected to your LED data line (or level shifter input).
    *   Set `NUM_PIXELS` to the correct number of LEDs on your strip.
    *   **Multiple Devices**: If setting up multiple PicoLights, **assign a unique `BLE_SERVICE_UUID`** to each device in its `config.py`. The **Characteristic UUIDs** (`BLE_RECIPE_CHAR_UUID`, `BLE_CUSTOM_CHAR_UUID`, `BLE_CONTROL_CHAR_UUID`) **should remain identical** across all devices using this firmware version.
    *   Set `BT_DEVICE_NAME` (e.g., 'PicoLight Grow Tent', 'PicoLight Desk'). The web app finds devices where the name *starts* with 'PicoLight'.
    *   Review other settings like `ACTIVE_RECIPE` (default for auto-cycle), `BT_AUTO_CYCLE` (initial state), `WATCHDOG_TIMEOUT`.
5.  **Run `main.py`**: Execute `main.py` from Thonny or configure it to run automatically on boot (e.g., by renaming it to `main.py`). Check the Thonny console ("Shell" or "REPL") for "Bluetooth advertising started..." and any error messages.

## Software Setup (Web App)

1.  **Get the HTML File**: Use the `BLEwithMemandReconect.html` file.
2.  **Access the File**:
    *   **Option A (Simple):** Open the `.html` file directly in a compatible web browser (`file:///path/to/your/file.html`).
    *   **Option B (Better):** Serve the file using a simple local web server (e.g., Python's `http.server`, Node.js `live-server`, VS Code Live Server extension) and access it via `http://localhost:PORT`. This often works better with Web Bluetooth permissions.
3.  **Ensure `knownServiceUUIDs` is Correct**: In the `<script>` section of the HTML file, make sure the `knownServiceUUIDs` array includes *all* the unique `BLE_SERVICE_UUID` values used by your Pico devices.

## Usage Instructions

1.  **Power On**: Ensure your PicoLight device(s) are powered on and running the firmware.
2.  **Open Web App**: Open the `LocalConnectingCode.html file in your compatible browser.
3.  **Connect**: Click the "Connect" button. Your browser should show a popup listing nearby Bluetooth devices whose names start with "PicoLight".
4.  **Select Device**: Choose the desired PicoLight device from the list and click "Pair" or "Connect".
5.  **Wait**: The status should change to "Connected", and the device name (or your custom name) will appear. Controls will become enabled.
6.  **Rename (Optional)**: Once connected, click the <i class="fas fa-edit"></i> icon next to the device name in the connection widget to give it a memorable name (saved in your browser).
7.  **Control Lights**:
    *   **Recipes**: Click icons in the "Light Recipes" card.
    *   **Custom**: Use sliders in the "Custom Color" card and click "Apply Color".
    *   **On/Off**: Use the dedicated buttons.
8.  **Configure Auto-Cycle**:
    *   Enter desired ON/OFF hours (0-24) in the "Auto-Cycle Settings" card. Click "Save Durations".
    *   Select a *predefined* recipe from the "ON Recipe" dropdown. Click "Set Auto Recipe".
    *   These settings are saved on the Pico. Click "Refresh Settings" to fetch the current values from the device. (Note: Auto-cycle only runs if `BT_AUTO_CYCLE=True` in the Pico's `config.py`).
9.  **Manage Custom Recipes**: Use the "Save as Recipe" button in the Custom Color card. Apply or delete saved recipes from the "My Custom Recipes" section (stored in your browser).
10. **Disconnect**: Click the "Disconnect" button.
11. **Auto-Reconnect**: If enabled, the next time you load the page, a prompt/toast will appear. Clicking "Connect" will then attempt connection to the last device.

## Predefined Light Recipes

(List remains the same as your original README)
- Balanced, Warm, Cool, Daylight, Veg Growth, Bloom, Seedling, Succulent, Purple Glow, Sunrise, Sunset, Forest, Aquarium, Night Light, Inspection, Off.

## Configuration Explained

*   **`config.py` (on Pico)**: Defines hardware pins, default behaviors (like initial auto-cycle state, default auto-cycle recipe), device name, and crucial **UUIDs**. You generally set this up once per device.
*   **`controller_settings.txt` (on Pico)**: Automatically created/updated by `main.py`. Stores the user-configured schedule durations (ON/OFF hours) and the selected auto-cycle "ON Recipe". These settings **override** the defaults from `config.py` on subsequent boots.
*   **Browser Local Storage**: Used by the HTML/JavaScript to store your custom *color* recipes and the custom *names* you assign to devices. These are specific to the browser you use.

## Troubleshooting

*   **Cannot Find Device During Scan**:
    *   Verify Pico is powered and `main.py` is running without errors (check Thonny console).
    *   Ensure `BT_DEVICE_NAME` in `config.py` starts with "PicoLight".
    *   Check OS/Browser Bluetooth is ON and permissions are granted (including Location Services if needed).
    *   Make sure the Pico isn't already connected to another device/browser. Reboot Pico.
    *   Try simplifying the name in `config.py` (e.g., just `PicoLight`).
*   **"No Compatible Service Found" Error**:
    *   The `BLE_SERVICE_UUID` in the Pico's `config.py` does **not** match any UUID listed in the `knownServiceUUIDs` array in the HTML file. Verify both.
*   **"No Characteristics matching UUID..." Error**:
    *   The `BLE_SERVICE_UUID` **matched**, but the **Characteristic UUIDs** (Recipe, Custom, Control) defined in the Pico's `config.py` do **not** match the `recipeCharUUID`, `customCharUUID`, `controlCharUUID` constants in the HTML file. Ensure characteristics UUIDs end in `...1214` (or your standard value) on the Pico.
*   **Connection Drops**: Check power supplies (Pico and LEDs), reduce distance, check for Bluetooth interference.
*   **Renaming Not Saved**: Check browser's Developer Tools (F12 -> Application -> Local Storage) to see if `picolight-saved-devices` is being updated correctly. Ensure you're not in Incognito/Private mode.
*   **Auto-Cycle Settings Not Working**:
    *   Ensure you clicked "Save Durations" and "Set Auto Recipe" after making changes.
    *   Verify `BT_AUTO_CYCLE` is set to `True` in the Pico's `config.py` if you want the schedule to run automatically.
    *   Click "Refresh Settings" to confirm the Pico received the values.

## License

[Link to your chosen license, e.g., MIT License](<!-- Add a LICENSE.md file or link to an online one -->

## Acknowledgments

*   Web Bluetooth API documentation
*   FontAwesome for icons
*   MicroPython community
*   Created with ❤️ for Fairchild Tropical Botanic Garden

---
