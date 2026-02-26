from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def clear_cooldown():
    """Reset alert cooldown state between tests."""
    from bitcoin_mining_manager import alerts
    alerts._last_alert_times.clear()
    alerts._active_alerts.clear()


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


def test_cooldown_suppresses_duplicate():
    """Same alert_type within cooldown window should not send twice."""
    with patch("bitcoin_mining_manager.alerts.GRAFANA_API_KEY", ""), \
         patch("bitcoin_mining_manager.alerts.ALERT_COOLDOWN", 300):
        from bitcoin_mining_manager import alerts
        alerts.twilio_client = MagicMock()

        alerts.send_alert("freq low 49.2 Hz", alert_type="freq_low")
        alerts.send_alert("freq low 49.1 Hz", alert_type="freq_low")

        # Only one call despite two send_alert invocations
        assert alerts.twilio_client.messages.create.call_count == 1


def test_cooldown_allows_different_types():
    """Different alert types should fire independently."""
    with patch("bitcoin_mining_manager.alerts.GRAFANA_API_KEY", ""), \
         patch("bitcoin_mining_manager.alerts.ALERT_COOLDOWN", 300):
        from bitcoin_mining_manager import alerts
        alerts.twilio_client = MagicMock()

        alerts.send_alert("freq low", alert_type="freq_low")
        alerts.send_alert("power high", alert_type="power_high")

        assert alerts.twilio_client.messages.create.call_count == 2


def test_cooldown_expires(monkeypatch):
    """After cooldown expires, the same alert type should fire again."""
    import time
    current = [1000.0]
    monkeypatch.setattr(time, "time", lambda: current[0])

    with patch("bitcoin_mining_manager.alerts.GRAFANA_API_KEY", ""), \
         patch("bitcoin_mining_manager.alerts.ALERT_COOLDOWN", 300):
        from bitcoin_mining_manager import alerts
        alerts.twilio_client = MagicMock()

        alerts.send_alert("freq low", alert_type="freq_low")
        current[0] = 1301.0  # 301 seconds later
        alerts.send_alert("freq low again", alert_type="freq_low")

        assert alerts.twilio_client.messages.create.call_count == 2


def test_clear_alert_sends_recovery():
    """clear_alert should send a recovery message for an active alert."""
    with patch("bitcoin_mining_manager.alerts.GRAFANA_API_KEY", ""), \
         patch("bitcoin_mining_manager.alerts.ALERT_COOLDOWN", 300):
        from bitcoin_mining_manager import alerts
        alerts.twilio_client = MagicMock()

        alerts.send_alert("freq low", alert_type="freq_low")
        alerts.clear_alert("freq_low", "Frequency recovered to 50.1 Hz")

        assert alerts.twilio_client.messages.create.call_count == 2
        second_call = alerts.twilio_client.messages.create.call_args_list[1]
        assert "recovered" in second_call.kwargs["body"].lower()


def test_clear_alert_noop_when_not_active():
    """clear_alert should do nothing if the alert was never fired."""
    with patch("bitcoin_mining_manager.alerts.GRAFANA_API_KEY", ""):
        from bitcoin_mining_manager import alerts
        alerts.twilio_client = MagicMock()

        alerts.clear_alert("freq_low", "recovered")

        alerts.twilio_client.messages.create.assert_not_called()


def test_clear_alert_resets_cooldown():
    """After clear_alert, the same alert_type should fire immediately again."""
    with patch("bitcoin_mining_manager.alerts.GRAFANA_API_KEY", ""), \
         patch("bitcoin_mining_manager.alerts.ALERT_COOLDOWN", 300):
        from bitcoin_mining_manager import alerts
        alerts.twilio_client = MagicMock()

        alerts.send_alert("freq low", alert_type="freq_low")
        alerts.clear_alert("freq_low")
        alerts.send_alert("freq low again", alert_type="freq_low")

        # 3 calls: alert, clear, re-alert
        assert alerts.twilio_client.messages.create.call_count == 3
