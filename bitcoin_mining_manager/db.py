import logging
import sqlite3
import threading

import redis

from bitcoin_mining_manager.config import REDIS_HOST, REDIS_PORT

logger = logging.getLogger(__name__)

conn = None
cursor = None
redis_client = None
db_lock = threading.Lock()


def init_db():
    """Initialize SQLite and Redis connections."""
    global conn, cursor, redis_client

    conn = sqlite3.connect("asic_cycles.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS asics (
            id TEXT PRIMARY KEY,
            cycles INTEGER DEFAULT 0,
            last_off TIMESTAMP
        )
    """)
    conn.commit()
    logger.info("SQLite connected")

    try:
        redis_client = redis.Redis(
            host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True
        )
        redis_client.ping()
        logger.info("Redis connected")
    except redis.exceptions.ConnectionError:
        redis_client = None
        logger.warning("Redis unavailable — running without cache")


def register_asics(count, prefix="asic"):
    """Register ASICs in the database. Skips IDs that already exist."""
    added = 0
    for i in range(count):
        asic_id = f"{prefix}-{i:03d}"
        cursor.execute("INSERT OR IGNORE INTO asics (id) VALUES (?)", (asic_id,))
        added += cursor.rowcount
    conn.commit()
    logger.info(f"Registered {added} new ASICs ({count - added} already existed)")
    return added


def list_asics():
    """Return all registered ASICs sorted by ID."""
    cursor.execute("SELECT id, cycles, last_off FROM asics ORDER BY id")
    return cursor.fetchall()
