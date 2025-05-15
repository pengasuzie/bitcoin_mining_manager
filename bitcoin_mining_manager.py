import aiohttp
import asyncio
import logging
import paho.mqtt.client as mqtt
import pymodbus.client as modbus
import redis
import sqlite3
import time
from datetime import datetime
from flask import Flask, jsonify
from grafana_api.grafana_face import GrafanaFace
from prometheus_client import Gauge, start_http_server
from twilio.rest import Client
from dotenv import load_dotenv
import os
import subprocess

# Load environment variables
load_dotenv()

# Configuration
GRID_SENSOR_IP = os.getenv("GRID_SENSOR_IP", "192.168.1.100")  # SEL-735
ASIC_API_URL = os.getenv("ASIC_API_URL", "http://192.168.1.200:4028")  # CGMiner API
MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
GRAFANA_HOST = os.getenv("GRAFANA_HOST", "localhost:3000")
GRAFANA_API_KEY = os.getenv("GRAFANA_API_KEY", "your_grafana_api_key")
TWILIO_SID = os.getenv("TWILIO_SID", "your_twilio_sid")
TWILIO_TOKEN = os.getenv("TWILIO_TOKEN", "your_twilio_token")
TWILIO_FROM = os.getenv("TWILIO_FROM", "+1234567890")
TWILIO_TO = os.getenv("TWILIO_TO", "+0987654321")
ALERT_THRESHOLD = float(os.getenv("ALERT_THRESHOLD", 49.5))  # Grid frequency (Hz)
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", 10))  # Seconds
ASIC_POWER = float(os.getenv("ASIC_POWER", 3.5))  # kW per ASIC

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("mining_manager.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# Prometheus metrics
grid_freq = Gauge("grid_frequency", "Grid frequency in Hz")
asic_count = Gauge("active_asics", "Number of active ASICs")
power_usage = Gauge("power_usage", "Total power usage in kW")
network_status = Gauge("network_status", "Internet connectivity (1=up, 0=down)")

# SQLite setup
conn = sqlite3.connect("asic_cycles.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute(
    """
    CREATE TABLE IF NOT EXISTS asics (
        id TEXT PRIMARY KEY,
        cycles INTEGER DEFAULT 0,
        last_off TIMESTAMP
    )
"""
)
conn.commit()

# Redis setup
redis_client = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)

# Modbus client for grid frequency
modbus_client = modbus.ModbusTcpClient(GRID_SENSOR_IP, port=502)

# MQTT client for power sensors
mqtt_client = mqtt.Client()

def on_mqtt_connect(client, userdata, flags, rc, properties=None):
    logger.info(f"Connected to MQTT broker with code {rc}")
    client.subscribe("power/sensors")

mqtt_client.on_connect = on_mqtt_connect
mqtt_client.connect(MQTT_BROKER, 1883, 60)

# Twilio client for SMS alerts
twilio_client = Client(TWILIO_SID, TWILIO_TOKEN)

# Flask app for dashboard API
app = Flask(__name__)

async def read_grid_frequency():
    """Read grid frequency from SEL-735 via Modbus TCP."""
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
    """Read power supply sensors via MQTT (placeholder)."""
    try:
        # TODO: Implement MQTT message parsing for current/voltage
        power_data = {"current": 0, "voltage": 0}  # Replace with actual data
        power = power_data["current"] * power_data["voltage"] / 1000  # kW
        logger.info(f"Power usage: {power} kW")
        return power
    except Exception as e:
        logger.error(f"Error reading power sensors: {e}")
        return 0.0  # Fallback

async def control_asics(grid_freq, power_available, session):
    """Adjust ASIC on/off based on grid frequency and power availability."""
    try:
        cursor.execute("SELECT id, cycles FROM asics ORDER BY cycles ASC, last_off ASC")
        asics = cursor.fetchall()
        active_count = 0
        max_asics = min(len(asics), int(power_available / ASIC_POWER))

        for asic_id, cycles in asics:
            cache_key = f"asic:{asic_id}:status"
            should_be_active = active_count < max_asics and grid_freq > ALERT_THRESHOLD

            if should_be_active:
                # Check cache to avoid redundant API calls
                if redis_client.get(cache_key) != "on":
                    async with session.get(f"{ASIC_API_URL}/start?asic={asic_id}") as resp:
                        if resp.status == 200:
                            redis_client.setex(cache_key, 60, "on")
                            active_count += 1
                            logger.info(f"Started ASIC {asic_id}")
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

def run_dummy_pool():
    """Start local Stratum server if internet is down."""
    try:
        subprocess.run(["ping", "-c", "1", "pool.example.com"], timeout=5, check=True)
        network_status.set(1)
        return
    except subprocess.SubprocessError:
        network_status.set(0)
        logger.warning("Internet down, starting local Stratum server")
        subprocess.Popen(
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
    """Send alerts via Grafana and Twilio SMS."""
    try:
        grafana = GrafanaFace(auth=GRAFANA_API_KEY, host=GRAFANA_HOST)
        grafana.alerts.create_alert({"message": message})
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

                # Manage connectivity
                bond_internet()
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
    # Start Prometheus metrics server
    start_http_server(8000)
    logger.info("Prometheus metrics server started on port 8000")

    # Start Flask API in a separate thread
    from threading import Thread
    flask_thread = Thread(target=lambda: app.run(host="0.0.0.0", port=5000, threaded=True))
    flask_thread.daemon = True
    flask_thread.start()
    logger.info("Flask API started on port 5000")

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
        modbus_client.close()
        conn.close()
        mqtt_client.disconnect()
    except Exception as e:
        logger.critical(f"Fatal error: {e}")
        raise
