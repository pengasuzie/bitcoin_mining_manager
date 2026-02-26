import logging
import subprocess

from bitcoin_mining_manager.config import MINING_POOL_HOST, network_status_gauge, metrics

logger = logging.getLogger(__name__)

_dummy_pool_proc = None


def bond_internet():
    """Configure internet bonding with OpenMPTCProuter."""
    try:
        subprocess.run(
            ["openmptcprouter", "bond", "eth0", "usb0"],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        logger.info("Internet bonding configured")
    except subprocess.SubprocessError as e:
        logger.error(f"Error bonding internet: {e}")


def run_dummy_pool():
    """Start local Stratum server if internet is down. Track the process to avoid duplicates."""
    global _dummy_pool_proc
    try:
        subprocess.run(["ping", "-c", "1", MINING_POOL_HOST], timeout=5, check=True)
        network_status_gauge.set(1)
        metrics["network"] = 1
        # Internet is back — stop dummy pool if running
        if _dummy_pool_proc and _dummy_pool_proc.poll() is None:
            _dummy_pool_proc.terminate()
            _dummy_pool_proc = None
            logger.info("Internet restored, stopped local Stratum server")
        return
    except subprocess.SubprocessError:
        network_status_gauge.set(0)
        metrics["network"] = 0
        # Only spawn if not already running
        if _dummy_pool_proc and _dummy_pool_proc.poll() is None:
            return
        logger.warning("Internet down, starting local Stratum server")
        _dummy_pool_proc = subprocess.Popen(
            ["stratum-mining", "--host", "localhost", "--port", "3333"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
