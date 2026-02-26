import logging

from flask import Flask, jsonify

from bitcoin_mining_manager import db
from bitcoin_mining_manager.config import metrics

logger = logging.getLogger(__name__)

app = Flask(__name__)


@app.route("/dashboard")
def dashboard():
    """Serve real-time dashboard data."""
    try:
        return jsonify({
            "grid_frequency": metrics["freq"],
            "active_asics": metrics["active_asics"],
            "power_usage": metrics["power"],
            "network_status": metrics["network"],
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
