import asyncio
import logging
from datetime import datetime

import aiohttp

from bitcoin_mining_manager import db
from bitcoin_mining_manager.config import (
    ASIC_API_URL, ASIC_POWER, ALERT_THRESHOLD, ASIC_API_TIMEOUT, ASIC_API_RETRIES,
    asic_count_gauge, metrics,
)

logger = logging.getLogger(__name__)


async def _asic_request(session, url):
    """Send a request to an ASIC with timeout and retries."""
    for attempt in range(1, ASIC_API_RETRIES + 1):
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=ASIC_API_TIMEOUT)) as resp:
                if resp.status == 200:
                    return True
                logger.warning(f"ASIC API returned {resp.status} for {url}")
                return False
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            if attempt < ASIC_API_RETRIES:
                logger.warning(f"ASIC API attempt {attempt}/{ASIC_API_RETRIES} failed for {url}: {e}")
                await asyncio.sleep(1)
            else:
                logger.error(f"ASIC API failed after {ASIC_API_RETRIES} attempts for {url}: {e}")
                return False


async def control_asics(freq_value, power_available, session):
    """Adjust ASIC on/off based on grid frequency and power availability."""
    try:
        with db.db_lock:
            db.cursor.execute("SELECT id, cycles FROM asics ORDER BY cycles ASC, last_off ASC")
            asics = db.cursor.fetchall()

        max_asics = min(len(asics), int(power_available / ASIC_POWER))
        if freq_value <= ALERT_THRESHOLD:
            max_asics = 0

        active_count = 0
        for i, (asic_id, cycles) in enumerate(asics):
            cache_key = f"asic:{asic_id}:status"
            should_be_active = i < max_asics

            if should_be_active:
                if db.redis_client.get(cache_key) != "on":
                    if await _asic_request(session, f"{ASIC_API_URL}/start?asic={asic_id}"):
                        db.redis_client.setex(cache_key, 60, "on")
                        logger.info(f"Started ASIC {asic_id}")
                active_count += 1
            else:
                if db.redis_client.get(cache_key) != "off":
                    if await _asic_request(session, f"{ASIC_API_URL}/stop?asic={asic_id}"):
                        db.redis_client.setex(cache_key, 60, "off")
                        with db.db_lock:
                            db.cursor.execute(
                                "UPDATE asics SET cycles = cycles + 1, last_off = ? WHERE id = ?",
                                (datetime.now().isoformat(), asic_id),
                            )
                        logger.info(f"Stopped ASIC {asic_id}")
        with db.db_lock:
            db.conn.commit()
        asic_count_gauge.set(active_count)
        metrics["active_asics"] = active_count
    except Exception as e:
        logger.error(f"Error controlling ASICs: {e}")
