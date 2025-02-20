# Import built-in modules
import sys, time
import json
import datetime
import math

# MQTT Module
import paho.mqtt.publish as publish

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
scd30_enable = False
scd30 = None
scd30_measurement_interval = 2

# Create sensor object, communicating over the board's default I2C bus
i2c = None   # uses board.SCL and board.SDA
bme680_enable = True
bme680 = None
bme680_slp = 1013.25
bme680_burn_in_duration = 300
bme680_burn_in_data = []
bme680_gas_baseline = 0.0
bme680_hum_baseline = 40.0 # Set the humidity baseline to 40%, an optimal indoor humidity.
bme680_hum_weighting = 0.25 # This sets the balance between humidity and gas reading in the calculation of air_quality_score (25:75, humidity:gas)

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
        print("[I] [SCD30] Begin initializing SCD30 sensor")
        global scd30
        scd30 = adafruit_scd30.SCD30(i2c)

        if (scd30 == None):
            print("[E] [SCD30] Failed to initialize SCD30")
        else:
            print("[I] [SCD30] SCD30 initialized")


    if (bme680_enable):
        print("[I] [BME680] Begin initializing BME680 sensor")
        global bme680
        bme680 = adafruit_bme680.Adafruit_BME680_I2C(i2c, 0x76)

        print(f"[I] [BME680] Set sea level pressure to {bme680_slp} hPa")
        bme680.sea_level_pressure = bme680_slp

        # Collect gas resistance burn-in values, then use the average
        # of the last 50 values to set the upper limit for calculating
        # gas_baseline.
        print('[I] [BME680] Collecting gas resistance burn-in data for 5 mins')
        # Time variables for burn-in calculation of the BME680 sensor.
        start_time = time.time()
        curr_time = time.time()
        while curr_time - start_time < bme680_burn_in_duration:
            curr_time = time.time()
            gas = bme680.gas
            bme680_burn_in_data.append(gas)
            print('[I] [BME680] Gas: {0} Ohms'.format(gas))
            time.sleep(1)

        print('[I] [BME680] Burn-in completed')
        global bme680_gas_baseline
        bme680_gas_baseline = sum(bme680_burn_in_data[-50:]) / 50.0

        print('[I] [BME680] Gas baseline: {0} Ohms, humidity baseline: {1:.2f} %RH'.format(bme680_gas_baseline, bme680_hum_baseline))

        if (bme680 == None):
            print("[E] [BME680] Failed to initialize BME680")
        else:
            print("[I] [BME680] BME680 initialized")

    print("[I] Sensors successfull initialized.")
    return True

def get_air_quality_score(t, h, g):
    """Calculate the air quality score (0-100) based on the gas, humidity and temperature values."""
    gas = g
    hum = h
    temp = t

    # Calculate gas contribution to IAQ index
    gas_offset = bme680_gas_baseline - gas

    # Calculate humidity contribution to IAQ index
    hum_offset = hum - bme680_hum_baseline

    if hum_offset > 0:
        hum_score = (100 - bme680_hum_baseline - hum_offset) / (100 - bme680_hum_baseline) * (bme680_hum_weighting * 100)
    else:
        hum_score = (bme680_hum_baseline + hum_offset) / bme680_hum_baseline * (bme680_hum_weighting * 100)

    # Calculate air_quality_score
    air_quality_score = hum_score + (100 - bme680_hum_weighting * 100)

    return air_quality_score

def get_dew_point(temperature, humidity):
    """Compute the dew point in degrees Celsius
    :param temperature: current ambient temperature in degrees Celsius
    :type temperature: float
    :param humidity: relative humidity in %
    :type humidity: float
    :return: the dew point in degrees Celsius
    :rtype: float
    """
    A = 17.27
    B = 237.7
    alpha = ((A * temperature) / (B + temperature)) + math.log(humidity/100.0)
    return (B * alpha) / (A - alpha)

def get_frost_point(temperature, dew_point):
    """Compute the frost point in degrees Celsius
    :param temperature: current ambient temperature in degrees Celsius
    :type temperature: float
    :param dew_point: current dew point in degrees Celsius
    :type dew_point: float
    :return: the frost point in degrees Celsius
    :rtype: float
    """
    dew_point_k = 273.15 + dew_point
    t_air_k = 273.15 + temperature
    frost_point_k = dew_point_k - t_air_k + 2671.02 / ((2954.61 / t_air_k) + 2.193665 * math.log(t_air_k) - 13.3448)
    return frost_point_k - 273.15

def get_heat_index(temperature, humidity):
    """Compute the heat index in degrees Celsius
    :param temperature: current ambient temperature in degrees Celsius
    :type temperature: float
    :param humidity: relative humidity in %
    :type humidity: float
    :return: the heat index in degrees Celsius
    :rtype: float
    """
    c1 = -8.78469475556
    c2 = 1.61139411
    c3 = 2.33854883889
    c4 = -0.14611605
    c5 = -0.012308094
    c6 = -0.0164248277778
    c7 = 0.002211732
    c8 = 0.00072546
    c9 = -0.000003582
    heat_index = c1 + (c2 * temperature) + (c3 * humidity) + (c4 * temperature * humidity) + (c5 * temperature**2) + (c6 * humidity**2) + (c7 * temperature**2 * humidity) + (c8 * temperature * humidity**2) + (c9 * temperature**2 * humidity**2)
    return heat_index

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
        json_dict = {}
        json_dict["timestamp"] = datetime.datetime.now().isoformat()

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

            # Calculate the air quality score
            air_quality_score = get_air_quality_score(bme680_temperature, bme680_humidity, bme680_gas)
            dew_point = get_dew_point(bme680_temperature, bme680_humidity)
            frost_point = get_frost_point(bme680_temperature, dew_point)
            heat_index = get_heat_index(bme680_temperature, bme680_humidity)

            json_dict["bme680"] = {}
            json_dict["bme680"]["temperature"] = bme680_temperature
            json_dict["bme680"]["dew_point"] = dew_point
            json_dict["bme680"]["frost_point"] = frost_point
            json_dict["bme680"]["heat_index"] = heat_index
            json_dict["bme680"]["humidity"] = bme680_humidity
            json_dict["bme680"]["pressure"] = bme680_pressure
            json_dict["bme680"]["altitude"] = bme680_altitude
            json_dict["bme680"]["gas"] = bme680_gas
            json_dict["bme680"]["air_quality_score"] = air_quality_score
            json_dict["bme680"]["gas_baseline"] = bme680_gas_baseline
            json_dict["bme680"]["hum_baseline"] = bme680_hum_baseline
            json_dict["bme680"]["hum_weighting"] = bme680_hum_weighting

            print(f"[I] [BME680] Temperature: {bme680_temperature}; Humidity: {bme680_humidity}; Pressure: {bme680_pressure}; Altitude: {bme680_altitude}; Gas: {bme680_gas}; Air Quality Score: {air_quality_score}")

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

            dew_point = get_dew_point(scd30_temperature, scd30_humidity)
            frost_point = get_frost_point(scd30_temperature, dew_point)
            heat_index = get_heat_index(scd30_temperature, scd30_humidity)

            json_dict["scd30"] = {}
            json_dict["scd30"]["temperature"] =  scd30_temperature
            json_dict["scd30"]["dew_point"] = dew_point
            json_dict["scd30"]["frost_point"] = frost_point
            json_dict["scd30"]["heat_index"] = heat_index
            json_dict["scd30"]["humidity"] = scd30_humidity
            json_dict["scd30"]["co2"] = scd30_co2

            print(f"[I] [SCD30] CO2: {scd30_co2}; Temperature: {scd30_temperature}; Humidity: {scd30_humidity}; ")
        
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