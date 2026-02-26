import logging
import os

from dotenv import load_dotenv
from prometheus_client import Gauge

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
API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("API_PORT", "5000"))
MAX_POWER = float(os.getenv("MAX_POWER", "560"))  # kW — safety ceiling (160 ASICs * 3.5 kW)
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
grid_freq_gauge = Gauge("grid_frequency", "Grid frequency in Hz")
asic_count_gauge = Gauge("active_asics", "Number of active ASICs")
power_usage_gauge = Gauge("power_usage", "Total power usage in kW")
network_status_gauge = Gauge("network_status", "Internet connectivity (1=up, 0=down)")

# Latest metric values (mutable dict — safe to import and mutate from other modules)
metrics = {
    "freq": 0.0,
    "active_asics": 0,
    "power": 0.0,
    "network": 0,
}


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

    # Detect placeholder credentials left from copy-paste
    placeholders = {"your_twilio_sid", "your_twilio_token", "your_grafana_api_key"}
    if TWILIO_SID in placeholders or TWILIO_TOKEN in placeholders:
        errors.append("Twilio credentials contain placeholder values — update .env or clear them")
    if GRAFANA_API_KEY in placeholders:
        errors.append("Grafana API key contains a placeholder value — update .env or clear it")
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
