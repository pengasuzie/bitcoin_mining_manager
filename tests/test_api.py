import threading
from unittest.mock import MagicMock, patch

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


def test_health_all_ok():
    """Health endpoint should return 200 when all services are up."""
    mock_redis = MagicMock()
    mock_cursor = MagicMock()
    mock_conn = MagicMock()

    with patch("bitcoin_mining_manager.api.db") as mock_db:
        mock_db.redis_client = mock_redis
        mock_db.cursor = mock_cursor
        mock_db.conn = mock_conn
        mock_db.db_lock = threading.Lock()

        from bitcoin_mining_manager.api import app
        client = app.test_client()
        resp = client.get("/health")

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "healthy"
        assert data["checks"]["redis"] == "ok"
        assert data["checks"]["sqlite"] == "ok"


def test_health_redis_down():
    """Health endpoint should return 503 when Redis is down."""
    mock_redis = MagicMock()
    mock_redis.ping.side_effect = ConnectionError("refused")
    mock_cursor = MagicMock()
    mock_conn = MagicMock()

    with patch("bitcoin_mining_manager.api.db") as mock_db:
        mock_db.redis_client = mock_redis
        mock_db.cursor = mock_cursor
        mock_db.conn = mock_conn
        mock_db.db_lock = threading.Lock()

        from bitcoin_mining_manager.api import app
        client = app.test_client()
        resp = client.get("/health")

        assert resp.status_code == 503
        data = resp.get_json()
        assert data["status"] == "degraded"
        assert data["checks"]["redis"] == "error"
        assert data["checks"]["sqlite"] == "ok"


def test_health_not_initialized():
    """Health endpoint should report 'not initialized' before init_db runs."""
    with patch("bitcoin_mining_manager.api.db") as mock_db:
        mock_db.redis_client = None
        mock_db.conn = None
        mock_db.db_lock = threading.Lock()

        from bitcoin_mining_manager.api import app
        client = app.test_client()
        resp = client.get("/health")

        assert resp.status_code == 503
        data = resp.get_json()
        assert data["status"] == "degraded"
        assert data["checks"]["redis"] == "not initialized"
        assert data["checks"]["sqlite"] == "not initialized"
