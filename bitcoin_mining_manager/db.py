import logging
import sqlite3

import redis

from bitcoin_mining_manager.config import REDIS_HOST, REDIS_PORT

logger = logging.getLogger(__name__)

conn = None
cursor = None
redis_client = None


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

    redis_client = redis.Redis(
        host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True
    )
    redis_client.ping()
    logger.info("Redis connected")
