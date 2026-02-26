import logging

from grafana_api.grafana_face import GrafanaFace
from twilio.rest import Client

from bitcoin_mining_manager.config import (
    GRAFANA_API_KEY, GRAFANA_HOST,
    TWILIO_SID, TWILIO_TOKEN, TWILIO_FROM, TWILIO_TO,
)

logger = logging.getLogger(__name__)

twilio_client = None


def init_alerts():
    """Initialize Twilio client if configured."""
    global twilio_client
    if TWILIO_SID and TWILIO_TOKEN:
        twilio_client = Client(TWILIO_SID, TWILIO_TOKEN)
        logger.info("Twilio client configured")


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
