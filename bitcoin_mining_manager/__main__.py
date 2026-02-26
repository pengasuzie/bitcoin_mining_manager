import argparse
import asyncio
import logging
import signal
from threading import Thread

import aiohttp
from prometheus_client import start_http_server

from bitcoin_mining_manager import db, sensors, networking
from bitcoin_mining_manager.config import (
    API_HOST, API_PORT, ALERT_THRESHOLD, POLL_INTERVAL, MAX_POWER,
    grid_freq_gauge, power_usage_gauge, metrics,
    validate_config,
)
from bitcoin_mining_manager.db import init_db, register_asics, list_asics
from bitcoin_mining_manager.sensors import init_sensors, read_grid_frequency, read_power_sensors
from bitcoin_mining_manager.asic_control import control_asics
from bitcoin_mining_manager.networking import bond_internet, run_dummy_pool
from bitcoin_mining_manager.api import app
from bitcoin_mining_manager.alerts import init_alerts, send_alert, clear_alert

logger = logging.getLogger(__name__)

_shutdown_event = asyncio.Event()


def _shutdown_handler(loop):
    """Signal handler that triggers graceful shutdown."""
    logger.info("Shutdown signal received, stopping...")
    _shutdown_event.set()


async def main_loop():
    """Main loop for monitoring and control."""
    async with aiohttp.ClientSession() as session:
        while not _shutdown_event.is_set():
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

                # Alerts (with cooldown via alert_type keys) + recovery
                if freq < ALERT_THRESHOLD:
                    send_alert(f"Grid frequency dropped to {freq} Hz", alert_type="freq_low")
                else:
                    clear_alert("freq_low", f"Grid frequency recovered to {freq} Hz")
                if power > MAX_POWER:
                    send_alert("Power usage exceeded safe threshold", alert_type="power_high")
                else:
                    clear_alert("power_high", f"Power usage back to normal ({power} kW)")

            except Exception as e:
                logger.error(f"Main loop error: {e}")

            try:
                await asyncio.wait_for(_shutdown_event.wait(), timeout=POLL_INTERVAL)
                break  # shutdown was requested
            except asyncio.TimeoutError:
                pass  # normal — poll interval elapsed


def run():
    """Start the mining manager."""
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
    if sensors.mqtt_client:
        mqtt_thread = Thread(target=sensors.mqtt_client.loop_forever)
        mqtt_thread.daemon = True
        mqtt_thread.start()
        logger.info("MQTT client loop started")

    # Run main async loop with signal-based graceful shutdown
    loop = asyncio.new_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _shutdown_handler, loop)
    try:
        loop.run_until_complete(main_loop())
    except Exception as e:
        logger.critical(f"Fatal error: {e}")
        raise
    finally:
        _cleanup()
        loop.close()


def _cleanup():
    """Release all resources on shutdown."""
    logger.info("Cleaning up resources...")
    try:
        if networking._dummy_pool_proc and networking._dummy_pool_proc.poll() is None:
            networking._dummy_pool_proc.terminate()
    except Exception:
        pass
    try:
        sensors.modbus_client.close()
    except Exception:
        pass
    try:
        sensors.mqtt_client.disconnect()
    except Exception:
        pass
    try:
        db.conn.close()
    except Exception:
        pass
    logger.info("Shutdown complete")


def main():
    parser = argparse.ArgumentParser(
        description="Bitcoin Mining Manager — ASIC control based on grid frequency and power"
    )
    sub = parser.add_subparsers(dest="command")

    reg = sub.add_parser("register", help="Register ASICs in the database")
    reg.add_argument("--count", type=int, required=True, help="Number of ASICs to register")
    reg.add_argument("--prefix", default="asic", help="ID prefix (default: asic)")

    sub.add_parser("list", help="List registered ASICs and cycle counts")

    args = parser.parse_args()

    if args.command == "register":
        init_db()
        added = register_asics(args.count, args.prefix)
        total = len(list_asics())
        print(f"Registered {added} new ASICs. Total: {total}")

    elif args.command == "list":
        init_db()
        asics = list_asics()
        if not asics:
            print("No ASICs registered. Run: python -m bitcoin_mining_manager register --count 160")
        else:
            print(f"{'ID':<15} {'Cycles':<10} {'Last Off'}")
            print("-" * 45)
            for asic_id, cycles, last_off in asics:
                print(f"{asic_id:<15} {cycles:<10} {last_off or 'never'}")
            print(f"\nTotal: {len(asics)} ASICs")

    else:
        run()


main()
