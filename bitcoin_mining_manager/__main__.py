import asyncio
import logging
from threading import Thread

import aiohttp
from prometheus_client import start_http_server

from bitcoin_mining_manager import db, sensors, networking
from bitcoin_mining_manager.config import (
    API_HOST, API_PORT, ALERT_THRESHOLD, POLL_INTERVAL,
    grid_freq_gauge, power_usage_gauge, metrics,
    validate_config,
)
from bitcoin_mining_manager.db import init_db
from bitcoin_mining_manager.sensors import init_sensors, read_grid_frequency, read_power_sensors
from bitcoin_mining_manager.asic_control import control_asics
from bitcoin_mining_manager.networking import bond_internet, run_dummy_pool
from bitcoin_mining_manager.api import app
from bitcoin_mining_manager.alerts import init_alerts, send_alert

logger = logging.getLogger(__name__)


async def main_loop():
    """Main loop for monitoring and control."""
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                # Monitor energy demand
                freq = await read_grid_frequency()
                grid_freq_gauge.set(freq)
                metrics["freq"] = freq

                # Monitor power supply
                power = read_power_sensors()
                power_usage_gauge.set(power)
                metrics["power"] = power

                # Control ASICs
                await control_asics(freq, power, session)

                # Check connectivity and manage fallback pool
                run_dummy_pool()

                # Alerts
                if freq < ALERT_THRESHOLD:
                    send_alert(f"Grid frequency dropped to {freq} Hz")
                if power > 560:  # 160 ASICs * 3.5 kW
                    send_alert("Power usage exceeded safe threshold")

            except Exception as e:
                logger.error(f"Main loop error: {e}")

            await asyncio.sleep(POLL_INTERVAL)


def main():
    validate_config()
    init_db()
    init_sensors()
    init_alerts()

    # Start Prometheus metrics server
    start_http_server(8000)
    logger.info("Prometheus metrics server started on port 8000")

    # Start Flask API in a separate thread
    flask_thread = Thread(target=lambda: app.run(host=API_HOST, port=API_PORT, threaded=True))
    flask_thread.daemon = True
    flask_thread.start()
    logger.info(f"Flask API started on {API_HOST}:{API_PORT}")

    # Configure internet bonding once at startup
    bond_internet()

    # Start MQTT client loop in a separate thread
    mqtt_thread = Thread(target=sensors.mqtt_client.loop_forever)
    mqtt_thread.daemon = True
    mqtt_thread.start()
    logger.info("MQTT client loop started")

    # Run main async loop
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        if networking._dummy_pool_proc and networking._dummy_pool_proc.poll() is None:
            networking._dummy_pool_proc.terminate()
        sensors.modbus_client.close()
        db.conn.close()
        sensors.mqtt_client.disconnect()
    except Exception as e:
        logger.critical(f"Fatal error: {e}")
        raise


main()
