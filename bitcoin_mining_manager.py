import aiohttp
import asyncio
import json
import logging
import os
import subprocess
import threading
import time
from datetime import datetime

import paho.mqtt.client as mqtt
import pymodbus.client as modbus
import redis
import sqlite3
from flask import Flask, jsonify
from grafana_api.grafana_face import GrafanaFace
from prometheus_client import Gauge, start_http_server
from twilio.rest import Client
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
GRID_SENSOR_IP = os.getenv("GRID_SENSOR_IP", "192.168.1.100")
ASIC_API_URL = os.getenv("ASIC_API_URL", "http://192.168.1.200:4028")
MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "power/sensors")
GRAFANA_HOST = os.getenv("GRAFANA_HOST", "localhost:3000")
GRAFANA_API_KEY = os.getenv("GRAFANA_API_KEY", "")
TWILIO_SID = os.getenv("TWILIO_SID", "")
TWILIO_TOKEN = os.getenv("TWILIO_TOKEN", "")
TWILIO_FROM = os.getenv("TWILIO_FROM", "")
TWILIO_TO = os.getenv("TWILIO_TO", "")
ALERT_THRESHOLD = float(os.getenv("ALERT_THRESHOLD", "49.5"))
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "10"))
ASIC_POWER = float(os.getenv("ASIC_POWER", "3.5"))
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
MOCK_MODE = os.getenv("MOCK_MODE", "false").lower() == "true"
LOG_FILE = os.getenv("LOG_FILE", "mining_manager.log")
MINING_POOL_HOST = os.getenv("MINING_POOL_HOST", "pool.example.com")

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# Prometheus metrics
grid_freq = Gauge("grid_frequency", "Grid frequency in Hz")
asic_count = Gauge("active_asics", "Number of active ASICs")
power_usage = Gauge("power_usage", "Total power usage in kW")
network_status = Gauge("network_status", "Internet connectivity (1=up, 0=down)")

# Thread-safe storage for latest MQTT sensor readings
_sensor_lock = threading.Lock()
_sensor_data = {"current": 0.0, "voltage": 0.0}

# Service clients (initialized lazily in init_services())
conn = None
cursor = None
redis_client = None
modbus_client = None
mqtt_client = None
twilio_client = None

# Flask app
app = Flask(__name__)


def validate_config():
    """Validate configuration values at startup."""
    errors = []
    if ASIC_POWER <= 0:
        errors.append("ASIC_POWER must be positive")
    if POLL_INTERVAL <= 0:
        errors.append("POLL_INTERVAL must be positive")
    if ALERT_THRESHOLD <= 0:
        errors.append("ALERT_THRESHOLD must be positive")
    if errors:
        for err in errors:
            logger.error(f"Config error: {err}")
        raise SystemExit("Invalid configuration — see errors above")

    # Warnings for optional services
    if not TWILIO_SID or not TWILIO_TOKEN:
        logger.warning("Twilio not configured — SMS alerts disabled")
    if not GRAFANA_API_KEY:
        logger.warning("Grafana API key not configured — Grafana alerts disabled")
    if MOCK_MODE:
        logger.warning("MOCK_MODE enabled — using simulated sensor data")


def init_services():
    """Connect to all services. Called from main(), not at import time."""
    global conn, cursor, redis_client, modbus_client, mqtt_client, twilio_client

    # SQLite
    conn = sqlite3.connect("asic_cycles.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS asics (
            id TEXT PRIMARY KEY,
            cycles INTEGER DEFAULT 0,
            last_off TIMESTAMP
        )
    """)
    conn.commit()
    logger.info("SQLite connected")

    # Redis
    redis_client = redis.Redis(
        host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True
    )
    redis_client.ping()
    logger.info("Redis connected")

    # Modbus
    modbus_client = modbus.ModbusTcpClient(GRID_SENSOR_IP, port=502)
    logger.info(f"Modbus client configured for {GRID_SENSOR_IP}")

    # MQTT
    mqtt_client = mqtt.Client()
    mqtt_client.on_connect = _on_mqtt_connect
    mqtt_client.on_message = _on_mqtt_message
    mqtt_client.connect(MQTT_BROKER, 1883, 60)
    logger.info(f"MQTT connected to {MQTT_BROKER}")

    # Twilio (optional — skip if not configured)
    if TWILIO_SID and TWILIO_TOKEN:
        twilio_client = Client(TWILIO_SID, TWILIO_TOKEN)
        logger.info("Twilio client configured")


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
        return 50.0  # Fallback


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


async def control_asics(freq_value, power_available, session):
    """Adjust ASIC on/off based on grid frequency and power availability."""
    try:
        cursor.execute("SELECT id, cycles FROM asics ORDER BY cycles ASC, last_off ASC")
        asics = cursor.fetchall()
        max_asics = min(len(asics), int(power_available / ASIC_POWER))
        if freq_value <= ALERT_THRESHOLD:
            max_asics = 0

        active_count = 0
        for i, (asic_id, cycles) in enumerate(asics):
            cache_key = f"asic:{asic_id}:status"
            should_be_active = i < max_asics

            if should_be_active:
                if redis_client.get(cache_key) != "on":
                    async with session.get(f"{ASIC_API_URL}/start?asic={asic_id}") as resp:
                        if resp.status == 200:
                            redis_client.setex(cache_key, 60, "on")
                            logger.info(f"Started ASIC {asic_id}")
                active_count += 1
            else:
                if redis_client.get(cache_key) != "off":
                    async with session.get(f"{ASIC_API_URL}/stop?asic={asic_id}") as resp:
                        if resp.status == 200:
                            redis_client.setex(cache_key, 60, "off")
                            cursor.execute(
                                "UPDATE asics SET cycles = cycles + 1, last_off = ? WHERE id = ?",
                                (datetime.now(), asic_id),
                            )
                            logger.info(f"Stopped ASIC {asic_id}")
        conn.commit()
        asic_count.set(active_count)
    except Exception as e:
        logger.error(f"Error controlling ASICs: {e}")


_dummy_pool_proc = None


def run_dummy_pool():
    """Start local Stratum server if internet is down. Track the process to avoid duplicates."""
    global _dummy_pool_proc
    try:
        subprocess.run(["ping", "-c", "1", MINING_POOL_HOST], timeout=5, check=True)
        network_status.set(1)
        # Internet is back — stop dummy pool if running
        if _dummy_pool_proc and _dummy_pool_proc.poll() is None:
            _dummy_pool_proc.terminate()
            _dummy_pool_proc = None
            logger.info("Internet restored, stopped local Stratum server")
        return
    except subprocess.SubprocessError:
        network_status.set(0)
        # Only spawn if not already running
        if _dummy_pool_proc and _dummy_pool_proc.poll() is None:
            return
        logger.warning("Internet down, starting local Stratum server")
        _dummy_pool_proc = subprocess.Popen(
            ["stratum-mining", "--host", "localhost", "--port", "3333"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def bond_internet():
    """Configure internet bonding with OpenMPTCProuter."""
    try:
        subprocess.run(
            ["openmptcprouter", "bond", "eth0", "usb0"],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        logger.info("Internet bonding configured")
    except subprocess.SubprocessError as e:
        logger.error(f"Error bonding internet: {e}")


@app.route("/dashboard")
def dashboard():
    """Serve real-time dashboard data."""
    try:
        return jsonify({
            "grid_frequency": grid_freq._value.get(),
            "active_asics": asic_count._value.get(),
            "power_usage": power_usage._value.get(),
            "network_status": network_status._value.get(),
        })
    except Exception as e:
        logger.error(f"Error serving dashboard: {e}")
        return jsonify({"error": "Internal server error"}), 500


def send_alert(message):
    """Send alerts via Grafana and/or Twilio SMS."""
    try:
        if GRAFANA_API_KEY:
            grafana = GrafanaFace(auth=GRAFANA_API_KEY, host=GRAFANA_HOST)
            grafana.alerts.create_alert({"message": message})
        if twilio_client:
            twilio_client.messages.create(body=message, from_=TWILIO_FROM, to=TWILIO_TO)
        logger.info(f"Alert sent: {message}")
    except Exception as e:
        logger.error(f"Error sending alert: {e}")


async def main_loop():
    """Main loop for monitoring and control."""
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                # Monitor energy demand
                freq = await read_grid_frequency()
                grid_freq.set(freq)

                # Monitor power supply
                power = read_power_sensors()
                power_usage.set(power)

                # Control ASICs
                await control_asics(freq, power, session)

                # Check connectivity and manage fallback pool
                run_dummy_pool()

                # Alerts
                if freq < ALERT_THRESHOLD:
                    send_alert(f"Grid frequency dropped to {freq} Hz")
                if power_usage._value.get() > 560:  # 160 ASICs * 3.5 kW
                    send_alert("Power usage exceeded safe threshold")

            except Exception as e:
                logger.error(f"Main loop error: {e}")

            await asyncio.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    validate_config()
    init_services()

    # Start Prometheus metrics server
    start_http_server(8000)
    logger.info("Prometheus metrics server started on port 8000")

    # Start Flask API in a separate thread
    from threading import Thread
    flask_thread = Thread(target=lambda: app.run(host="0.0.0.0", port=5000, threaded=True))
    flask_thread.daemon = True
    flask_thread.start()
    logger.info("Flask API started on port 5000")

    # Configure internet bonding once at startup
    bond_internet()

    # Start MQTT client loop in a separate thread
    mqtt_thread = Thread(target=mqtt_client.loop_forever)
    mqtt_thread.daemon = True
    mqtt_thread.start()
    logger.info("MQTT client loop started")

    # Run main async loop
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        if _dummy_pool_proc and _dummy_pool_proc.poll() is None:
            _dummy_pool_proc.terminate()
        modbus_client.close()
        conn.close()
        mqtt_client.disconnect()
    except Exception as e:
        logger.critical(f"Fatal error: {e}")
        raise
