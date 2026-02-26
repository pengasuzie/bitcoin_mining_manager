import logging

from flask import Flask, jsonify

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
