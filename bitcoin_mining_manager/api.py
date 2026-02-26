import logging
import os

from flask import Flask, jsonify, send_file

from bitcoin_mining_manager import db
from bitcoin_mining_manager.config import (
    metrics, MAX_POWER, ALERT_THRESHOLD, ASIC_POWER, POLL_INTERVAL,
)

logger = logging.getLogger(__name__)

app = Flask(__name__)


@app.route("/")
def index():
    """Serve the HTML dashboard."""
    html_path = os.path.join(os.path.dirname(__file__), "dashboard.html")
    return send_file(html_path, mimetype="text/html")


@app.route("/asics")
def asics():
    """Return per-ASIC status, cycle count, and last-off time."""
    try:
        with db.db_lock:
            db.cursor.execute(
                "SELECT id, cycles, last_off FROM asics ORDER BY id"
            )
            rows = db.cursor.fetchall()

        result = []
        for asic_id, cycles, last_off in rows:
            status = "unknown"
            try:
                if db.redis_client:
                    cached = db.redis_client.get(f"asic:{asic_id}:status")
                    if cached:
                        status = cached
            except Exception:
                pass
            result.append({
                "id": asic_id,
                "status": status,
                "cycles": cycles,
                "last_off": last_off,
            })

        return jsonify(result)
    except Exception as e:
        logger.error(f"Error serving ASIC data: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/dashboard")
def dashboard():
    """Serve real-time dashboard data."""
    try:
        return jsonify({
            "grid_frequency": metrics["freq"],
            "active_asics": metrics["active_asics"],
            "power_usage": metrics["power"],
            "network_status": metrics["network"],
            "max_power": MAX_POWER,
            "alert_threshold": ALERT_THRESHOLD,
            "asic_power": ASIC_POWER,
            "poll_interval": POLL_INTERVAL,
        })
    except Exception as e:
        logger.error(f"Error serving dashboard: {e}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/health")
def health():
    """Service health check for monitoring."""
    checks = {}

    try:
        if db.redis_client:
            db.redis_client.ping()
            checks["redis"] = "ok"
        else:
            checks["redis"] = "not initialized"
    except Exception:
        checks["redis"] = "error"

    try:
        if db.conn:
            with db.db_lock:
                db.cursor.execute("SELECT 1")
            checks["sqlite"] = "ok"
        else:
            checks["sqlite"] = "not initialized"
    except Exception:
        checks["sqlite"] = "error"

    status = "healthy" if all(v == "ok" for v in checks.values()) else "degraded"
    code = 200 if status == "healthy" else 503
    return jsonify({"status": status, "checks": checks}), code
