import asyncio
import json
import logging
import threading

import paho.mqtt.client as mqtt
import pymodbus.client as modbus

from bitcoin_mining_manager.config import GRID_SENSOR_IP, MQTT_BROKER, MQTT_TOPIC, MOCK_MODE

logger = logging.getLogger(__name__)

# Thread-safe storage for latest MQTT sensor readings
_sensor_lock = threading.Lock()
_sensor_data = {"current": 0.0, "voltage": 0.0}

modbus_client = None
mqtt_client = None


def init_sensors():
    """Initialize Modbus and MQTT clients."""
    global modbus_client, mqtt_client

    modbus_client = modbus.ModbusTcpClient(GRID_SENSOR_IP, port=502)
    logger.info(f"Modbus client configured for {GRID_SENSOR_IP}")

    mqtt_client = mqtt.Client()
    mqtt_client.on_connect = _on_mqtt_connect
    mqtt_client.on_message = _on_mqtt_message
    mqtt_client.connect(MQTT_BROKER, 1883, 60)
    logger.info(f"MQTT connected to {MQTT_BROKER}")


def _on_mqtt_connect(client, userdata, flags, rc, properties=None):
    """Handle MQTT broker connection."""
    logger.info(f"Connected to MQTT broker with code {rc}")
    client.subscribe(MQTT_TOPIC)


def _on_mqtt_message(client, userdata, msg):
    """Store incoming MQTT sensor readings in a thread-safe variable."""
    global _sensor_data
    try:
        payload = json.loads(msg.payload.decode())
        with _sensor_lock:
            _sensor_data = {
                "current": float(payload.get("current", 0)),
                "voltage": float(payload.get("voltage", 0)),
            }
        logger.debug(f"Sensor update: {_sensor_data}")
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"Invalid MQTT sensor payload: {e}")


async def read_grid_frequency():
    """Read grid frequency from SEL-735 via Modbus TCP."""
    if MOCK_MODE:
        return 50.0
    try:
        result = await asyncio.get_event_loop().run_in_executor(
            None, lambda: modbus_client.read_holding_registers(100, 1)
        )
        freq = result.registers[0] / 100.0
        logger.info(f"Grid frequency: {freq} Hz")
        return freq
    except Exception as e:
        logger.error(f"Error reading grid frequency: {e}")
        return 50.0


def read_power_sensors():
    """Read latest power data from MQTT sensor readings."""
    if MOCK_MODE:
        return 560.0  # Simulate full capacity (160 ASICs * 3.5 kW)
    try:
        with _sensor_lock:
            current = _sensor_data["current"]
            voltage = _sensor_data["voltage"]
        power = current * voltage / 1000  # kW
        logger.info(f"Power available: {power} kW")
        return power
    except Exception as e:
        logger.error(f"Error reading power sensors: {e}")
        return 0.0
