"""Constants for the Aqara Studio integration."""

from homeassistant.const import Platform

DOMAIN = "aqara_studio"
PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    Platform.EVENT,
    Platform.LIGHT,
    Platform.SWITCH,
]

CONF_TOKEN = "token"
CONF_GATEWAY_ID = "gateway_id"
CONF_GATEWAY_IDS = "gateway_ids"
CONF_POLL_INTERVAL = "poll_interval"
CONF_RECONCILE_INTERVAL = "reconcile_interval"
CONF_INVENTORY_INTERVAL = "inventory_interval"
CONF_ENABLE_WEBSOCKET = "enable_websocket"
CONF_ENABLE_BUTTON_EVENTS = "enable_button_events"
CONF_ENABLE_CONTROLS = "enable_controls"
CONF_EXCLUDED_DEVICES = "excluded_devices"
CONF_CONTACT_POLARITY = "contact_polarity"
CONF_LEAK_POLARITY = "leak_polarity"

CONTACT_POLARITIES = ["unconfirmed", "true_is_open", "false_is_open"]
LEAK_POLARITIES = ["unconfirmed", "true_is_wet", "false_is_wet"]

DEFAULT_OPTIONS = {
    CONF_POLL_INTERVAL: 15,
    CONF_RECONCILE_INTERVAL: 300,
    CONF_INVENTORY_INTERVAL: 300,
    CONF_ENABLE_WEBSOCKET: True,
    CONF_ENABLE_BUTTON_EVENTS: False,
    CONF_ENABLE_CONTROLS: False,
    CONF_EXCLUDED_DEVICES: [],
    CONF_CONTACT_POLARITY: "unconfirmed",
    CONF_LEAK_POLARITY: "unconfirmed",
}

DEFINITION_REFRESH_SECONDS = 21600
MIN_DISCOVERY_SECONDS = 30
STATE_BATCH_SIZE = 50
MAX_RETRY_SECONDS = 300
