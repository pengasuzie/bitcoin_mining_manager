from unittest.mock import MagicMock, patch

import pytest


def test_send_alert_twilio_only():
    """Alert should send via Twilio when configured, skip Grafana when not."""
    with patch("bitcoin_mining_manager.alerts.GRAFANA_API_KEY", ""), \
         patch("bitcoin_mining_manager.alerts.TWILIO_FROM", "+1111"), \
         patch("bitcoin_mining_manager.alerts.TWILIO_TO", "+2222"):
        from bitcoin_mining_manager import alerts
        alerts.twilio_client = MagicMock()

        alerts.send_alert("test message")

        alerts.twilio_client.messages.create.assert_called_once_with(
            body="test message", from_="+1111", to="+2222"
        )


def test_send_alert_no_services():
    """Alert should not crash when neither Twilio nor Grafana is configured."""
    with patch("bitcoin_mining_manager.alerts.GRAFANA_API_KEY", ""):
        from bitcoin_mining_manager import alerts
        alerts.twilio_client = None

        alerts.send_alert("test message")  # Should not raise


def test_send_alert_grafana_only():
    """Alert should send via Grafana when configured, skip Twilio when not."""
    mock_grafana = MagicMock()
    with patch("bitcoin_mining_manager.alerts.GRAFANA_API_KEY", "real_key"), \
         patch("bitcoin_mining_manager.alerts.GRAFANA_HOST", "localhost:3000"), \
         patch("bitcoin_mining_manager.alerts.GrafanaFace", return_value=mock_grafana):
        from bitcoin_mining_manager import alerts
        alerts.twilio_client = None

        alerts.send_alert("test message")

        mock_grafana.alerts.create_alert.assert_called_once_with({"message": "test message"})
