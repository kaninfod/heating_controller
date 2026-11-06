"""Constants for the Heating Controller integration."""

DOMAIN = "heating_controller"

# Hard-coded modes
HARD_MODES = [
    "default",
    "stay_home",
    "eco",
    "manual",
    "heating_off",
]

# Configuration keys
CONF_MQTT_TOPIC_BASE = "mqtt_topic_base"
CONF_AREAS = "areas"
CONF_DAY_TYPES = "day_types"
CONF_SCHEDULES = "schedules"
CONF_HEATING_MODES = "heating_modes"
CONF_VALVE_OPENING_DEGREE = "valve_opening_degree"
CONF_VALVE_CLOSING_DEGREE = "valve_closing_degree"
CONF_TEMPERATURE_ACCURACY = "temperature_accuracy"
CONF_SMART_TEMPERATURE_CONTROL = "smart_temperature_control"
CONF_DEVICE_SETTINGS = "device_settings"
CONF_TEMPERATURE_SENSOR = "temperature_sensor"
CONF_DEFAULT_MODE = "default_mode"
CONF_MIDNIGHT_RESET = "midnight_reset"

# Default values
DEFAULT_MQTT_TOPIC_BASE = "zigbee2mqtt"
