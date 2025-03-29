# PicoLight Controller v3

A web-based Bluetooth controller for RGBW LED lights powered by a Raspberry Pi Pico microcontroller.

## Overview

PicoLight Controller v3 is a responsive web application that allows wireless control of RGBW/NeoPixel (Red, Green, Blue, White) LED lights connected to a Raspberry Pi Pico microcontroller. The application utilizes the Web Bluetooth API to establish a connection with the microcontroller and send commands to adjust light settings.

## Features

- **Bluetooth Connectivity**: Connect wirelessly to your PicoLight device
- **Preset Light Recipes**: Quick access to common lighting configurations
- **Custom Color Control**: Adjust individual RGBW channels with precision sliders
- **Save Custom Recipes**: Create and save your favorite lighting configurations
- **On/Off Controls**: Easily turn lights on or off with dedicated buttons
- **Responsive Design**: Works on desktop and mobile devices

## Requirements

- A web browser that supports the Web Bluetooth API (Chrome, Edge, Opera)
- A Raspberry Pi Pico W with Bluetooth capability (e.g. Pico W / Pico W 2)
- RGBW LED lights connected to the Pico
- MicroPython firmware with the PicoLight BLE service

## Compatible Browsers

The Web Bluetooth API is currently supported by:
- Google Chrome (desktop & Android)
- Microsoft Edge
- Opera
- Samsung Internet

**Note**: Safari (iOS, iPadOS, macOS) and Firefox do not currently support Web Bluetooth.

## Hardware Setup

The PicoLight system requires:
1. Raspberry Pi Pico W (with Bluetooth capability)
2. RGBW LED strip/lights
3. Power supply appropriate for your LED setup



## Software Setup

### Pico Firmware
1. Raspberry Pi Pico W with MicroPython v1.24 or higher 
2. Copy main.py
3. Copy config.py
The firmware should be configured to advertise as "PicoLight" for the web app to discover it.

### Web Application

The web application can be:
1. Run locally from `file://` in Chrome with Web Bluetooth flags enabled
2. Served from a local development server

## Usage Instructions

1. **Connect to PicoLight**:
   - Press the "Connect to PicoLight" button
   - Select your PicoLight device from the Bluetooth device list
   - Wait for connection confirmation

2. **Apply a Preset Recipe**:
   - Choose from the dropdown menu or quick access buttons
   - Available presets include: Balanced, Warm, Cool, Daylight, and more

3. **Set Custom Colors**:
   - Adjust the Red, Green, Blue, and White sliders
   - Press "Apply Color" to send to the device
   - Save your custom settings with "Save as Recipe"

4. **Turn Lights On/Off**:
   - Use the dedicated on/off buttons for quick control

5. **Manage Custom Recipes**:
   - Access your saved recipes in the "My Custom Recipes" section
   - Apply saved recipes with a single click
   - Delete unwanted recipes as needed

## Predefined Light Recipes

The system includes the following preset recipes:
- **Balanced**: General purpose lighting with all channels
- **Warm**: Cozy warm white with amber tones
- **Cool**: Crisp, cool white light
- **Daylight**: Natural daylight simulation
- **Veg Growth**: Optimized for vegetative plant growth
- **Bloom**: Enhanced red spectrum for flowering plants
- **Seedling**: Gentle light suitable for young seedlings
- **Succulent**: Desert-like lighting for succulents
- **Purple Glow**: Ambient purple lighting effect
- **Sunrise**: Warm morning light simulation
- **Sunset**: Deep amber evening light
- **Forest**: Green-tinted nature-inspired lighting
- **Aquarium**: Blue-enhanced aquatic lighting
- **Night Light**: Low intensity warm light
- **Inspection**: Maximum brightness on all channels
- **Off**: Turns off all channels

## Troubleshooting

- **Cannot Connect**:
  - Ensure your browser supports Web Bluetooth
  - Check that Bluetooth is enabled on your device
  - Verify the Pico is powered and advertising as "PicoLight"

- **Connection Drops**:
  - Reduce distance between controller and Pico
  - Check Pico power supply is stable
  - Refresh the page and reconnect

- **Controls Not Responsive**:
  - Wait a few seconds between commands
  - Refresh connection if persistent

## Browser Compatibility Note

If you see "Bluetooth Not Available" message, your browser does not support Web Bluetooth. Try using Google Chrome or Microsoft Edge.


## License

[MIT License](LICENSE)

## Acknowledgments

- Web Bluetooth API documentation
- FontAwesome for icons
- MicroPython community

---

Created with ❤️ for Fairchld Tropical Gardens 
