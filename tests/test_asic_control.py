import asyncio
import sqlite3
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest


@pytest.fixture
def setup_db():
    """Create an in-memory SQLite database with test ASICs."""
    conn = sqlite3.connect(":memory:")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE asics (
            id TEXT PRIMARY KEY,
            cycles INTEGER DEFAULT 0,
            last_off TIMESTAMP
        )
    """)
    # Insert 5 test ASICs with varying cycle counts
    for i in range(5):
        cursor.execute("INSERT INTO asics (id, cycles) VALUES (?, ?)", (f"asic-{i}", i))
    conn.commit()
    return conn, cursor


@pytest.fixture
def mock_redis():
    """Mock Redis client that tracks ASIC status in a dict."""
    store = {}
    client = MagicMock()
    client.get = MagicMock(side_effect=lambda key: store.get(key))
    client.setex = MagicMock(side_effect=lambda key, ttl, val: store.__setitem__(key, val))
    return client, store


@pytest.fixture
def mock_session():
    """Mock aiohttp session where all ASIC API calls succeed."""
    response = AsyncMock()
    response.status = 200
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=response)
    ctx.__aexit__ = AsyncMock(return_value=False)
    session = MagicMock()
    session.get = MagicMock(return_value=ctx)
    return session


def run_control(setup_db, mock_redis, mock_session, freq, power):
    """Helper to run control_asics with patched dependencies."""
    conn, cursor = setup_db
    redis_client, _ = mock_redis

    with patch("bitcoin_mining_manager.asic_control.db") as mock_db, \
         patch("bitcoin_mining_manager.asic_control.ASIC_POWER", 3.5), \
         patch("bitcoin_mining_manager.asic_control.ALERT_THRESHOLD", 49.5), \
         patch("bitcoin_mining_manager.asic_control.ASIC_API_URL", "http://test:4028"), \
         patch("bitcoin_mining_manager.asic_control.ASIC_API_TIMEOUT", 10), \
         patch("bitcoin_mining_manager.asic_control.ASIC_API_RETRIES", 2), \
         patch("bitcoin_mining_manager.asic_control.asic_count_gauge") as mock_gauge, \
         patch("bitcoin_mining_manager.asic_control.metrics", {"active_asics": 0}):
        mock_db.cursor = cursor
        mock_db.conn = conn
        mock_db.redis_client = redis_client

        from bitcoin_mining_manager.asic_control import control_asics, metrics
        asyncio.run(control_asics(freq, power, mock_session))
        return metrics["active_asics"]


class TestControlAsics:
    def test_all_asics_on_when_power_sufficient(self, setup_db, mock_redis, mock_session):
        """With enough power and good frequency, all ASICs should be active."""
        count = run_control(setup_db, mock_redis, mock_session, freq=50.0, power=17.5)
        assert count == 5  # 17.5 kW / 3.5 kW = 5 ASICs

    def test_partial_asics_when_power_limited(self, setup_db, mock_redis, mock_session):
        """With limited power, only affordable ASICs should be active."""
        count = run_control(setup_db, mock_redis, mock_session, freq=50.0, power=10.5)
        assert count == 3  # 10.5 kW / 3.5 kW = 3 ASICs

    def test_no_asics_when_freq_below_threshold(self, setup_db, mock_redis, mock_session):
        """When grid frequency drops below threshold, all ASICs should be off."""
        count = run_control(setup_db, mock_redis, mock_session, freq=49.0, power=17.5)
        assert count == 0

    def test_no_asics_when_freq_equals_threshold(self, setup_db, mock_redis, mock_session):
        """Frequency exactly at threshold should shut down all ASICs."""
        count = run_control(setup_db, mock_redis, mock_session, freq=49.5, power=17.5)
        assert count == 0

    def test_no_asics_when_no_power(self, setup_db, mock_redis, mock_session):
        """Zero power should mean zero ASICs."""
        count = run_control(setup_db, mock_redis, mock_session, freq=50.0, power=0)
        assert count == 0

    def test_already_on_asics_counted(self, setup_db, mock_redis, mock_session):
        """ASICs already cached as 'on' should still be counted as active."""
        _, store = mock_redis
        # Pre-populate 2 ASICs as already on
        store["asic:asic-0:status"] = "on"
        store["asic:asic-1:status"] = "on"
        count = run_control(setup_db, mock_redis, mock_session, freq=50.0, power=10.5)
        assert count == 3  # 3 slots available, 2 already on + 1 newly started

    def test_stops_excess_asics(self, setup_db, mock_redis, mock_session):
        """ASICs beyond the max should be stopped."""
        _, store = mock_redis
        # All 5 ASICs currently on
        for i in range(5):
            store[f"asic:asic-{i}:status"] = "on"
        count = run_control(setup_db, mock_redis, mock_session, freq=50.0, power=7.0)
        # Only 2 slots (7.0 / 3.5), so 3 should be stopped
        assert count == 2
        # Verify the excess ones were set to "off"
        assert store["asic:asic-2:status"] == "off"
        assert store["asic:asic-3:status"] == "off"
        assert store["asic:asic-4:status"] == "off"

    def test_cycle_fairness_ordering(self, setup_db, mock_redis, mock_session):
        """ASICs with fewest cycles should get priority (be turned on first)."""
        conn, cursor = setup_db
        _, store = mock_redis

        # Verify ASICs are ordered by cycles ASC
        cursor.execute("SELECT id, cycles FROM asics ORDER BY cycles ASC")
        asics = cursor.fetchall()
        assert asics[0] == ("asic-0", 0)  # Fewest cycles
        assert asics[4] == ("asic-4", 4)  # Most cycles

        # With only 2 slots, the first 2 (fewest cycles) should be on
        count = run_control(setup_db, mock_redis, mock_session, freq=50.0, power=7.0)
        assert count == 2
        assert store.get("asic:asic-0:status") == "on"
        assert store.get("asic:asic-1:status") == "on"


class TestAsicRequest:
    def test_retries_on_timeout(self):
        """_asic_request should retry on timeout, then succeed."""
        response = AsyncMock()
        response.status = 200

        call_count = [0]

        def make_ctx(url, **kwargs):
            call_count[0] += 1
            ctx = AsyncMock()
            if call_count[0] == 1:
                ctx.__aenter__ = AsyncMock(side_effect=asyncio.TimeoutError())
            else:
                ctx.__aenter__ = AsyncMock(return_value=response)
            ctx.__aexit__ = AsyncMock(return_value=False)
            return ctx

        session = MagicMock()
        session.get = MagicMock(side_effect=make_ctx)

        with patch("bitcoin_mining_manager.asic_control.ASIC_API_TIMEOUT", 1), \
             patch("bitcoin_mining_manager.asic_control.ASIC_API_RETRIES", 3):
            from bitcoin_mining_manager.asic_control import _asic_request
            result = asyncio.run(_asic_request(session, "http://test/start?asic=x"))
            assert result is True
            assert call_count[0] == 2

    def test_fails_after_max_retries(self):
        """_asic_request should return False after exhausting retries."""
        def make_ctx(url, **kwargs):
            ctx = AsyncMock()
            ctx.__aenter__ = AsyncMock(side_effect=asyncio.TimeoutError())
            ctx.__aexit__ = AsyncMock(return_value=False)
            return ctx

        session = MagicMock()
        session.get = MagicMock(side_effect=make_ctx)

        with patch("bitcoin_mining_manager.asic_control.ASIC_API_TIMEOUT", 1), \
             patch("bitcoin_mining_manager.asic_control.ASIC_API_RETRIES", 2):
            from bitcoin_mining_manager.asic_control import _asic_request
            result = asyncio.run(_asic_request(session, "http://test/start?asic=x"))
            assert result is False
            assert session.get.call_count == 2
