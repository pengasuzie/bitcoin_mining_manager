from unittest.mock import patch

import pytest

from bitcoin_mining_manager import config


def test_validate_config_valid():
    """Valid config should not raise."""
    with patch.object(config, "ASIC_POWER", 3.5), \
         patch.object(config, "POLL_INTERVAL", 10), \
         patch.object(config, "ALERT_THRESHOLD", 49.5), \
         patch.object(config, "TWILIO_SID", ""), \
         patch.object(config, "TWILIO_TOKEN", ""), \
         patch.object(config, "GRAFANA_API_KEY", ""), \
         patch.object(config, "MOCK_MODE", False):
        config.validate_config()  # Should not raise


def test_validate_config_bad_asic_power():
    """ASIC_POWER <= 0 should fail."""
    with patch.object(config, "ASIC_POWER", 0), \
         patch.object(config, "POLL_INTERVAL", 10), \
         patch.object(config, "ALERT_THRESHOLD", 49.5):
        with pytest.raises(SystemExit):
            config.validate_config()


def test_validate_config_bad_poll_interval():
    """POLL_INTERVAL <= 0 should fail."""
    with patch.object(config, "ASIC_POWER", 3.5), \
         patch.object(config, "POLL_INTERVAL", -1), \
         patch.object(config, "ALERT_THRESHOLD", 49.5):
        with pytest.raises(SystemExit):
            config.validate_config()


def test_validate_config_bad_alert_threshold():
    """ALERT_THRESHOLD <= 0 should fail."""
    with patch.object(config, "ASIC_POWER", 3.5), \
         patch.object(config, "POLL_INTERVAL", 10), \
         patch.object(config, "ALERT_THRESHOLD", 0):
        with pytest.raises(SystemExit):
            config.validate_config()


def test_validate_config_placeholder_twilio():
    """Placeholder Twilio creds should fail."""
    with patch.object(config, "ASIC_POWER", 3.5), \
         patch.object(config, "POLL_INTERVAL", 10), \
         patch.object(config, "ALERT_THRESHOLD", 49.5), \
         patch.object(config, "TWILIO_SID", "your_twilio_sid"), \
         patch.object(config, "TWILIO_TOKEN", "your_twilio_token"), \
         patch.object(config, "GRAFANA_API_KEY", ""):
        with pytest.raises(SystemExit):
            config.validate_config()


def test_validate_config_placeholder_grafana():
    """Placeholder Grafana key should fail."""
    with patch.object(config, "ASIC_POWER", 3.5), \
         patch.object(config, "POLL_INTERVAL", 10), \
         patch.object(config, "ALERT_THRESHOLD", 49.5), \
         patch.object(config, "TWILIO_SID", ""), \
         patch.object(config, "TWILIO_TOKEN", ""), \
         patch.object(config, "GRAFANA_API_KEY", "your_grafana_api_key"):
        with pytest.raises(SystemExit):
            config.validate_config()
