import logging
import time

from grafana_api.grafana_face import GrafanaFace
from twilio.rest import Client

from bitcoin_mining_manager.config import (
    ALERT_COOLDOWN,
    GRAFANA_API_KEY, GRAFANA_HOST,
    TWILIO_SID, TWILIO_TOKEN, TWILIO_FROM, TWILIO_TO,
)

logger = logging.getLogger(__name__)

twilio_client = None
_last_alert_times = {}
_active_alerts = set()


def init_alerts():
    """Initialize Twilio client if configured."""
    global twilio_client
    if TWILIO_SID and TWILIO_TOKEN:
        twilio_client = Client(TWILIO_SID, TWILIO_TOKEN)
        logger.info("Twilio client configured")


def send_alert(message, alert_type=None):
    """Send alerts via Grafana and/or Twilio SMS.

    Uses alert_type (or the message itself) as a cooldown key to prevent
    flooding. The same alert type won't fire more than once per
    ALERT_COOLDOWN seconds.
    """
    key = alert_type or message
    now = time.time()
    if key in _last_alert_times and now - _last_alert_times[key] < ALERT_COOLDOWN:
        return
    _last_alert_times[key] = now
    _active_alerts.add(key)

    _dispatch(message)


def clear_alert(alert_type, message=None):
    """Send a recovery notification when an alert condition clears.

    Only sends if the alert_type was previously active.
    """
    if alert_type not in _active_alerts:
        return
    _active_alerts.discard(alert_type)
    _last_alert_times.pop(alert_type, None)
    _dispatch(message or f"Resolved: {alert_type}")


def _dispatch(message):
    """Send message via configured channels."""
    try:
        if GRAFANA_API_KEY:
            grafana = GrafanaFace(auth=GRAFANA_API_KEY, host=GRAFANA_HOST)
            grafana.alerts.create_alert({"message": message})
        if twilio_client:
            twilio_client.messages.create(body=message, from_=TWILIO_FROM, to=TWILIO_TO)
        logger.info(f"Alert sent: {message}")
    except Exception as e:
        logger.error(f"Error sending alert: {e}")
