# --- START OF FILE unified_sensor.py ---

# unified_sensor.py - Single unified driver for SCD4X, MPL3115A2, and VEML7700

import time
import struct
from micropython import const
import machine
import config  # external configuration file

# --- General Sensor Settings (from config) ---
SENSOR_READ_INTERVAL_MS = config.SENSOR_READ_INTERVAL_MS
SENSOR_INIT_DELAY_S = config.SENSOR_INIT_DELAY_S

# --- I2C Configuration (from config) ---
I2C_ID = config.I2C_ID
I2C_SCL_PIN = config.I2C_SCL_PIN
I2C_SDA_PIN = config.I2C_SDA_PIN
I2C_FREQUENCY = config.I2C_FREQUENCY

# --- Sensor Enable Flags & Addresses (from config) ---
SCD4X_ENABLED = config.SCD4X_ENABLED
SCD4X_I2C_ADDR = config.SCD4X_I2C_ADDR

MPL3115A2_ENABLED = config.MPL3115A2_ENABLED
MPL3115A2_I2C_ADDR = config.MPL3115A2_I2C_ADDR

VEML7700_ENABLED = config.VEML7700_ENABLED
VEML7700_I2C_ADDR = config.VEML7700_I2C_ADDR

# --- SCD4X Constants ---
_SCD4X_STOPPERIODICMEASUREMENT = const(0x3F86)
_SCD4X_STARTPERIODICMEASUREMENT = const(0x21B1)
_SCD4X_READMEASUREMENT = const(0xEC05)
_SCD4X_DATAREADY = const(0xE4B8)
_SCD4X_SET_AMBIENT_PRESSURE = const(0xE000)

class SCD4X_Simple:
    """Simplified driver for Sensirion SCD4X CO2 sensor."""
    def __init__(self, i2c, address=SCD4X_I2C_ADDR):
        print(f"SCD4X: Initializing at address {hex(address)}...")
        self.i2c = i2c
        self.address = address
        self._buffer = bytearray(18) # Increased buffer size just in case
        self._cmd = bytearray(2)
        self._crc_buffer = bytearray(2)
        self._temperature = None # Initialize as None
        self._relative_humidity = None
        self._co2 = None

        # Try to stop measurements first (in case it's running)
        try:
            self.stop_periodic_measurement()
            print(f"SCD4X: Stopped periodic measurement (if running).")
            # Wait for sensor to process stop command
            time.sleep(0.5)
        except OSError as e:
            # This is often expected if the sensor wasn't running
            print(f"SCD4X: Note - Could not stop measurement (may be normal on first boot): {e}")
        except Exception as e:
            print(f"SCD4X: Unexpected error during initial stop: {e}")

    def _send_command(self, cmd, cmd_delay=0.01):
        self._cmd[0] = (cmd >> 8) & 0xFF
        self._cmd[1] = cmd & 0xFF
        # print(f"SCD4X DBG: Sending cmd {hex(cmd)}") # Debug print
        try:
            self.i2c.writeto(self.address, self._cmd)
            time.sleep(cmd_delay)
        except OSError as e:
            print(f"SCD4X: I2C write error sending command {hex(cmd)}: {e}")
            raise # Re-raise error for caller to handle

    def _read_reply(self, num_bytes):
        try:
            read_data = self.i2c.readfrom(self.address, num_bytes)
            if len(read_data) != num_bytes:
                 print(f"SCD4X: I2C read error - Expected {num_bytes} bytes, got {len(read_data)}")
                 return False

            for i in range(num_bytes):
                self._buffer[i] = read_data[i]

            # CRC check for each 3-byte chunk
            valid = True
            for i in range(0, num_bytes, 3):
                if i + 2 < num_bytes: # Check there are enough bytes
                    if not self._check_buffer_crc(self._buffer[i : i + 3]):
                        valid = False
                        # Don't break immediately, log all CRC errors if multiple reads
            return valid
        except OSError as e:
            print(f"SCD4X: I2C read error: {e}")
            return False

    def _check_buffer_crc(self, buf):
        """Checks CRC of a 3-byte buffer (data_high, data_low, crc)."""
        if len(buf) != 3: return False
        calculated_crc = self._crc8(buf[0:2])
        received_crc = buf[2]
        if calculated_crc != received_crc:
            # print(f"SCD4X: CRC Error! Data: {buf[0:2]}, Calc CRC: {hex(calculated_crc)}, Recv CRC: {hex(received_crc)}") # Can be noisy
            return False
        return True

    @staticmethod
    def _crc8(buffer):
        """Calculates Sensirion's CRC-8 checksum."""
        crc = 0xFF
        for byte in buffer:
            crc ^= byte
            for _ in range(8):
                if crc & 0x80:
                    crc = (crc << 1) ^ 0x31
                else:
                    crc <<= 1
        return crc & 0xFF

    def start_periodic_measurement(self):
        """Starts periodic measurement mode."""
        print(f"SCD4X: Starting periodic measurement...")
        self._send_command(_SCD4X_STARTPERIODICMEASUREMENT, cmd_delay=0.01)

    def stop_periodic_measurement(self):
        """Stops periodic measurement mode."""
        print(f"SCD4X: Sending stop periodic measurement command...")
        self._send_command(_SCD4X_STOPPERIODICMEASUREMENT, cmd_delay=0.5) # Requires 500ms delay

    def set_ambient_pressure(self, pressure_hpa):
        """Sets ambient pressure compensation."""
        if pressure_hpa is None:
            print("SCD4X: Cannot set ambient pressure, value is None.")
            return # Don't try to set if pressure isn't available

        pressure_mbar = int(pressure_hpa)
        if not 700 <= pressure_mbar <= 1200:
             print(f"SCD4X: Warning - Pressure {pressure_mbar} mbar out of recommended range (700-1200)")

        print(f"SCD4X: Setting ambient pressure to {pressure_mbar} mbar")
        cmd = _SCD4X_SET_AMBIENT_PRESSURE
        value = pressure_mbar # uint16

        self._crc_buffer[0] = (value >> 8) & 0xFF # Value High
        self._crc_buffer[1] = value & 0xFF        # Value Low
        crc = self._crc8(self._crc_buffer)

        write_buf = bytearray(5)
        write_buf[0] = (cmd >> 8) & 0xFF
        write_buf[1] = cmd & 0xFF
        write_buf[2] = self._crc_buffer[0] # Value High
        write_buf[3] = self._crc_buffer[1] # Value Low
        write_buf[4] = crc                 # CRC of Value

        try:
            self.i2c.writeto(self.address, write_buf)
            time.sleep(0.01)
        except OSError as e:
            print(f"SCD4X: I2C write error setting pressure: {e}")
            # Don't raise, just log the error

    @property
    def data_ready(self):
        """Checks if new measurement data is available."""
        try:
            self._send_command(_SCD4X_DATAREADY, cmd_delay=0.001)
            if self._read_reply(3):
                status_word = struct.unpack_from(">H", self._buffer[0:2])[0]
                # Data ready status is in the lower 11 bits (mask 0x07FF)
                return (status_word & 0x07FF) != 0
            return False # Read failed
        except OSError as e:
            print(f"SCD4X: Error checking data ready status: {e}")
            return False
        except Exception as e:
            print(f"SCD4X: Unexpected error checking data ready: {e}")
            return False

    def read_measurement(self):
        """Reads and updates internal CO2, Temp, Humidity values. Returns True on success."""
        try:
            self._send_command(_SCD4X_READMEASUREMENT, cmd_delay=0.001)
            if not self._read_reply(9):
                print(f"SCD4X: Failed to read measurement data (I2C/CRC error).")
                self._co2 = None; self._temperature = None; self._relative_humidity = None # Invalidate readings
                return False

            self._co2 = struct.unpack_from(">H", self._buffer[0:2])[0]
            temp_raw = struct.unpack_from(">H", self._buffer[3:5])[0]
            humi_raw = struct.unpack_from(">H", self._buffer[6:8])[0]

            self._temperature = -45.0 + 175.0 * (temp_raw / 65535.0)
            self._relative_humidity = 100.0 * (humi_raw / 65535.0)
            self._relative_humidity = max(0.0, min(100.0, self._relative_humidity)) # Clamp RH

            # Basic range validation (optional, but good practice)
            # if not (0 <= self._co2 <= 40000): print(f"SCD4X Warning: CO2 {self._co2} ppm out of range")
            # if not (-10 <= self._temperature <= 60): print(f"SCD4X Warning: Temp {self._temperature:.1f} C out of range")

            return True # Indicate success
        except OSError as e:
            print(f"SCD4X: Error during read_measurement (I2C): {e}")
            self._co2 = None; self._temperature = None; self._relative_humidity = None
            return False
        except Exception as e:
            print(f"SCD4X: Unexpected error during read_measurement: {e}")
            self._co2 = None; self._temperature = None; self._relative_humidity = None
            return False

    @property
    def CO2(self): return self._co2
    @property
    def temperature(self): return self._temperature
    @property
    def relative_humidity(self): return self._relative_humidity

class MPL3115A2:
    """Driver for MPL3115A2 Pressure/Temperature sensor."""
    def __init__(self, i2c, addr=MPL3115A2_I2C_ADDR):
        print(f"MPL3115A2: Initializing at address {hex(addr)}...")
        self.i2c = i2c
        self.addr = addr
        self._buf = bytearray(6) # Buffer for reading data
        try:
            # Reset device? Not typically needed unless recovering from bad state.
            # Verify WHO_AM_I register
            who_am_i = self.i2c.readfrom_mem(self.addr, 0x0C, 1)
            if who_am_i != b'\xc4':
                print(f"MPL3115A2: Error - WHO_AM_I returned {hex(who_am_i[0])}, expected 0xC4")
                raise RuntimeError("MPL3115A2 WHO_AM_I mismatch")

            # Set Oversampling Rate (OSR) = 128 (register 0x26, bits 3-5 = 111)
            # Set ALT mode (bit 7 = 0)
            # Set RAW mode (bit 6 = 0)
            # Set Active mode (bit 0 = 1)
            # CTRL_REG1 (0x26): 0b00111001 = 0x39 (OSR=128, Active)
            self.i2c.writeto_mem(self.addr, 0x26, b'\x39')

            # Enable Data Flags in PT_DATA_CFG register (0x13)
            # Bit 2 PDEFE = 1 (Pressure Data Event Flag Enable)
            # Bit 1 TDEFE = 1 (Temperature Data Event Flag Enable)
            # Bit 0 DREM = 1 (Data Ready Event Mode Enable)
            # 0b00000111 = 0x07
            self.i2c.writeto_mem(self.addr, 0x13, b'\x07')
            print(f"MPL3115A2: Configured.")

        except OSError as e:
            print(f"MPL3115A2: I2C Error during initialization: {e}")
            raise # Re-raise error to halt UnifiedSensor init if critical

    @property
    def pressure(self):
        """Reads pressure in hPa."""
        try:
            # Check DR_STATUS register (0x06) for PTDR bit (bit 1)
            # Datasheet says wait for PTDR bit in STATUS (0x00) register (bit 2)
            status = self.i2c.readfrom_mem(self.addr, 0x00, 1)[0]
            # Optional: Add a timeout loop here instead of just checking once
            # max_wait = 10
            # while not (status & 0x04) and max_wait > 0:
            #    time.sleep(0.010) # Wait 10ms
            #    status = self.i2c.readfrom_mem(self.addr, 0x00, 1)[0]
            #    max_wait -= 1
            # if not (status & 0x04):
            #    print("MPL3115A2: Timeout waiting for data ready")
            #    return None

            if not (status & 0x04): # Check PDR bit (Pressure Data Ready)
                 # Data might not be ready yet, depending on OSR and loop timing
                 #print("MPL3115A2: Pressure data not ready yet.") # Can be noisy
                 return None # Return None if not ready

            # Read pressure registers (0x01 to 0x03)
            data = self.i2c.readfrom_mem(self.addr, 0x01, 3)
            # Format is MSB, CSB, LSB. Pressure is 20-bit signed Q16.4
            # Raw value = (data[0] << 16 | data[1] << 8 | data[2]) >> 4
            # LSB has 4 fractional bits. Result is in Pascals.
            raw_p = ((data[0] << 16) | (data[1] << 8) | data[2]) >> 4
            pressure_pa = raw_p / 4.0
            pressure_hpa = pressure_pa / 100.0
            return pressure_hpa

        except OSError as e:
            print(f"MPL3115A2: Error reading pressure: {e}")
            return None

    # Optional: Add temperature reading if needed
    # @property
    # def temperature(self):
    #     """Reads temperature in degrees Celsius."""
    #     try:
    #         status = self.i2c.readfrom_mem(self.addr, 0x00, 1)[0]
    #         if not (status & 0x02): # Check TDR bit (Temp Data Ready)
    #             return None
    #         data = self.i2c.readfrom_mem(self.addr, 0x04, 2)
    #         # Format is MSB, LSB. Temp is 12-bit signed Q8.4
    #         raw_t = ((data[0] << 8) | data[1]) >> 4
    #         # Handle negative temperatures (sign extend if MSB is 1)
    #         if raw_t & 0x800:
    #             raw_t = raw_t - 4096 # = raw_t - 2^12
    #         temp_c = raw_t / 16.0
    #         return temp_c
    #     except OSError as e:
    #         print(f"MPL3115A2: Error reading temperature: {e}")
    #         return None

class VEML7700:
    """Driver for VEML7700 Ambient Light Sensor."""
    # ALS Command Register Bits (Register 0x00)
    ALS_SD_MASK = 0x01 # ALS shut down setting (0=on, 1=off)
    ALS_INT_EN_MASK = 0x02 # ALS interrupt enable setting
    ALS_PERS_MASK = 0x0C # ALS persistence protect number setting
    ALS_IT_MASK = 0xF0 # ALS integration time setting
    ALS_GAIN_MASK = 0x1800 # ALS gain setting (within word for reg 0x00)

    # Default configuration: ALS ON, Int Off, Pers 1, IT 100ms, Gain x1
    # Config word = 0x0010 (Gain=x1, IT=100ms, Pers=1, Int=off, SD=off)
    DEFAULT_CONFIG = 0x0010

    # Resolution factor based on IT and Gain (from datasheet)
    # This needs to match the DEFAULT_CONFIG !!
    # For IT=100ms, Gain=x1, the resolution is 0.0576 lux/count
    DEFAULT_RESOLUTION = 0.0576

    def __init__(self, i2c, addr=VEML7700_I2C_ADDR):
        print(f"VEML7700: Initializing at address {hex(addr)}...")
        self.i2c = i2c
        self.addr = addr
        self._resolution = self.DEFAULT_RESOLUTION # Store resolution for current config

        try:
            # Apply default configuration
            config_bytes = self.DEFAULT_CONFIG.to_bytes(2, 'little')
            self.i2c.writeto_mem(self.addr, 0x00, config_bytes)
            print(f"VEML7700: Configured with {hex(self.DEFAULT_CONFIG)}")
            time.sleep(0.005) # Short delay after config write
        except OSError as e:
            print(f"VEML7700: I2C Error during initialization: {e}")
            raise # Re-raise error

    @property
    def lux(self):
        """Reads ambient light in lux."""
        try:
            # Read ALS data from register 0x04 (2 bytes, little-endian)
            data = self.i2c.readfrom_mem(self.addr, 0x04, 2)
            als_raw = int.from_bytes(data, 'little')

            # Apply resolution factor based on current configuration
            calculated_lux = als_raw * self._resolution
            # print(f"VEML7700 Raw ALS: {als_raw}, Calculated Lux: {calculated_lux:.2f}") # Debug print
            return calculated_lux
        except OSError as e:
            print(f"VEML7700: Error reading LUX data: {e}")
            return None # Return None on read error
        except Exception as e:
            print(f"VEML7700: Unexpected error reading LUX: {e}")
            return None

# ---------------------------------------------------------------------------
# --- Unified Sensor Class ---
# ---------------------------------------------------------------------------
class UnifiedSensor:
    """Manages multiple I2C sensors."""
    def __init__(self):
        print("UnifiedSensor: Initializing I2C Bus...")
        try:
            # Initialize I2C Bus
            self.i2c = machine.I2C(I2C_ID,
                                   scl=machine.Pin(I2C_SCL_PIN),
                                   sda=machine.Pin(I2C_SDA_PIN),
                                   freq=I2C_FREQUENCY)
            print(f"UnifiedSensor: I2C Bus {I2C_ID} OK.")

            # Scan bus for debugging
            print("UnifiedSensor: Scanning I2C bus...")
            devices = self.i2c.scan()
            device_hex = [hex(d) for d in devices]
            print(f"UnifiedSensor: Devices found: {device_hex}")

        except Exception as e:
            print(f"UnifiedSensor: FATAL - Failed to initialize I2C Bus: {e}")
            raise RuntimeError("I2C Bus Initialization Failed") from e

        # Initialize sensors based on config flags and check if found on bus
        self.scd4x = None
        if SCD4X_ENABLED:
            if SCD4X_I2C_ADDR in devices:
                try:
                    self.scd4x = SCD4X_Simple(self.i2c) # Address defaults in SCD4X class
                    # Start measurement after successful init
                    self.scd4x.start_periodic_measurement()
                    print(f"UnifiedSensor: Waiting {SENSOR_INIT_DELAY_S}s for SCD4X stabilization...")
                    time.sleep(SENSOR_INIT_DELAY_S)
                except Exception as e:
                    print(f"UnifiedSensor: Failed to initialize SCD4X: {e}")
                    self.scd4x = None # Ensure it's None on failure
            else:
                print(f"UnifiedSensor: SCD4X enabled in config but not found at {hex(SCD4X_I2C_ADDR)}")

        self.mpl = None
        if MPL3115A2_ENABLED:
            if MPL3115A2_I2C_ADDR in devices:
                try:
                    self.mpl = MPL3115A2(self.i2c) # Address defaults in MPL class
                except Exception as e:
                    print(f"UnifiedSensor: Failed to initialize MPL3115A2: {e}")
                    self.mpl = None
            else:
                print(f"UnifiedSensor: MPL3115A2 enabled in config but not found at {hex(MPL3115A2_I2C_ADDR)}")

        self.veml = None
        if VEML7700_ENABLED:
            if VEML7700_I2C_ADDR in devices:
                try:
                    self.veml = VEML7700(self.i2c) # Address defaults in VEML class
                except Exception as e:
                    print(f"UnifiedSensor: Failed to initialize VEML7700: {e}")
                    self.veml = None
            else:
                 print(f"UnifiedSensor: VEML7700 enabled in config but not found at {hex(VEML7700_I2C_ADDR)}")

        print("UnifiedSensor: Initialization complete.")

    def read_all(self):
        """Reads data from all enabled and initialized sensors."""
        sensor_data = {
            'co2': None,
            'temperature': None,
            'humidity': None,
            'pressure': None,
            'lux': None
        }

        # Read MPL3115A2 first (needed for SCD4X pressure compensation)
        if self.mpl:
            sensor_data['pressure'] = self.mpl.pressure
            # Optionally read MPL temperature here if needed/implemented

        # Read SCD4X (compensate pressure if available)
        if self.scd4x:
            try:
                # Set pressure compensation using the value read from MPL (if available)
                self.scd4x.set_ambient_pressure(sensor_data['pressure'])

                # Wait for data ready (with a timeout)
                ready_attempts = 5
                while not self.scd4x.data_ready and ready_attempts > 0:
                    # print("UnifiedSensor: Waiting for SCD4X data...") # Debug
                    time.sleep(0.1)
                    ready_attempts -= 1

                if self.scd4x.data_ready:
                    if self.scd4x.read_measurement():
                        sensor_data['co2'] = self.scd4x.CO2
                        sensor_data['temperature'] = self.scd4x.temperature
                        sensor_data['humidity'] = self.scd4x.relative_humidity
                    else:
                        print("UnifiedSensor: SCD4X read_measurement() failed.")
                        # Values will remain None
                else:
                    print("UnifiedSensor: SCD4X data not ready after waiting.")
                    # Values will remain None
            except Exception as e:
                print(f"UnifiedSensor: Error reading SCD4X: {e}")
                # Ensure values are None on error
                sensor_data['co2'] = None
                sensor_data['temperature'] = None
                sensor_data['humidity'] = None

        # Read VEML7700
        if self.veml:
            sensor_data['lux'] = self.veml.lux

        return sensor_data

# --- END OF FILE unified_sensor.py ---