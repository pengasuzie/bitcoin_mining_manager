from unittest.mock import patch

import pytest


def test_dashboard_returns_metrics():
    """Dashboard endpoint should return current metric values."""
    test_metrics = {
        "freq": 50.1,
        "active_asics": 42,
        "power": 147.0,
        "network": 1,
    }
    with patch("bitcoin_mining_manager.api.metrics", test_metrics):
        from bitcoin_mining_manager.api import app
        client = app.test_client()
        resp = client.get("/dashboard")

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["grid_frequency"] == 50.1
        assert data["active_asics"] == 42
        assert data["power_usage"] == 147.0
        assert data["network_status"] == 1


def test_dashboard_zero_state():
    """Dashboard should handle initial zero state."""
    test_metrics = {
        "freq": 0.0,
        "active_asics": 0,
        "power": 0.0,
        "network": 0,
    }
    with patch("bitcoin_mining_manager.api.metrics", test_metrics):
        from bitcoin_mining_manager.api import app
        client = app.test_client()
        resp = client.get("/dashboard")

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["grid_frequency"] == 0.0
        assert data["active_asics"] == 0
