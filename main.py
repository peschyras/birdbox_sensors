# Import built-in modules
import sys, time
import json
import datetime


# MQTT Module
import paho.mqtt.client as mqtt

# Import sensor modules
import board
import busio
import adafruit_scd30
import adafruit_bme680

# MQTT variables
mqtt_client = None

# The interval time in seconds for collecting data from all sensors.
measurement_inmterval = 60

# Onboard I2C Device.
i2c = None
i2c_transceiver = None
channel = None

# SCD30 sensor.
scd30_enable = True
scd30 = None
scd30_measurement_interval = 2

# Create sensor object, communicating over the board's default I2C bus
i2c = None   # uses board.SCL and board.SDA
bme680_enable = True
bme680 = None
bme680_slp = 1013.25

# Initialize sensors.
def init_sensors():
    # Create a I2C instance
    global i2c
    i2c = busio.I2C(board.SCL, board.SDA, frequency=50000)

    if (i2c == None):
        print("[E] Faild to initialize I2C")
        return False

    print("[I] I2C intialized")

    if (scd30_enable):
        global scd30
        scd30 = adafruit_scd30.SCD30(i2c)

        if (scd30 == None):
            print("[E] [SCD30] Failed to initialize SCD30")
        else:
            print("[I] [SCD30] SCD30 initialized")


    if (bme680_enable):
        global bme680
        bme680 = adafruit_bme680.Adafruit_BME680_I2C(i2c, 0x76)
        bme680.sea_level_pressure = bme680_slp

        if (bme680 == None):
            print("[E] [BME680] Failed to initialize BME680")
        else:
            print("[I] [BME680] BME680 initialized")

    print("[I] Sensors successfull initialized.")
    return True


# Begins to read sensor data.
def start_measurement():
    exit_code = 0
    # A counter for failed to get data from sensors.
    fail_counter = 0

    # Local variables for SCD30 sensor
    scd30_temperature = 0
    scd30_humidity = 0
    scd30_co2 = 0

    bme680_temperature = 0
    bme680_humidity = 0
    bme680_pressure = 0
    bme680_altitude = 0
    bme680_gas = 0

    while (True):
        # Power nap
        time.sleep(measurement_inmterval)

        # Read from BME680
        if (bme680_enable):
            try:
                bme680_temperature = bme680.temperature
                bme680_gas = bme680.gas
                bme680_humidity = bme680.relative_humidity
                bme680_pressure = bme680.pressure
                bme680_altitude = bme680.altitude
            except:
                print("[E] [BME680] Failed to get BME680 data.")
                exit_code = 1
                break

            print(f"[I] [BME680] Temperature: {bme680_temperature}; Humidity: {bme680_humidity}; Pressure: {bme680_pressure}; Altitude: {bme680_altitude}; Gas: {bme680_gas}")

        if (scd30_enable):
            # since the measurement interval is long (2+ seconds) we check for new data before reading
            # the values, to ensure current readings.
            try:
                if scd30.data_available:
                    scd30_temperature = scd30.temperature
                    scd30_humidity = scd30.relative_humidity
                    scd30_co2 = scd30.CO2
            except:
                print("[E] [BME680] Failed to get BME680 data.")
                exit_code = 1
                break

            print(f"[I] [SCD30] CO2: {scd30_co2}; Temperature: {scd30_temperature}; Humidity: {scd30_humidity}; ")
        
        
        json_dict = {
            "timestamp": datetime.datetime.now().isoformat(),
            "bem680": {
                "temperature":  bme680_temperature,
                "humidity": bme680_humidity,
                "pressure": bme680_pressure,
                "altitude": bme680_altitude,
                "gas": bme680_gas
            },
            "scd30": {
                "temperature":  scd30_temperature,
                "humidity": scd30_humidity,
                "co2": scd30_co2
            }
        }
        
        publish.single("birdbox/sensor_data", json.dumps(json_dict), hostname="192.168.178.2")
        print("[I] [MQTT] Data sent")
    
    terminate(exit_code)


def terminate(code :int):
    """
    Exit Code:
    0 = Exit without error.
    1 = Exit due to a problem with sensors.
    2 = Exit due to a problem with MQTT broker.
    """
    print(f"Exiting the program with return code {code}")
    sys.exit(code)

# Main
if __name__ == '__main__':
    print("[I] BirdBox Sensors Script")
    if (init_sensors()):
        start_measurement()