# Bitcoin Mining Manager

Automated Bitcoin mining controller for behind-the-meter operations. Adjusts ASIC miner activity based on grid frequency and available power in real time.

Designed for a shipping container deployment with 160 ASICs, running on a Beelink SER5 Pro mini PC with Ubuntu Server 24.04 LTS.

## Key Features

- **Grid frequency monitoring** via SEL-735 Power Quality Meter (Modbus TCP) — detects demand fluctuations (e.g. <49.5 Hz) and shuts down ASICs to reduce load
- **Power supply tracking** via current/voltage sensors (MQTT) — calculates available kW to prevent overloading
- **Cycle-fair ASIC scheduling** — prioritises units with fewest on/off cycles for even wear distribution across 160 miners
- **Local fallback mining** — automatically starts a Stratum server during internet outages to maintain load stability
- **Internet bonding** — bonds two connections (4G LTE + Starlink) via OpenMPTCProuter for <1% share loss
- **Real-time dashboards** — Prometheus metrics + Grafana visualisation + Flask REST API
- **SMS/Grafana alerts** — Twilio SMS and Grafana notifications for critical events

## Project Structure

```
bitcoin_mining_manager/
├── __init__.py
├── __main__.py          # Entry point (python -m bitcoin_mining_manager)
├── config.py            # Config loading, validation, Prometheus gauges
├── db.py                # SQLite + Redis initialisation
├── sensors.py           # Grid frequency (Modbus) + power sensors (MQTT)
├── asic_control.py      # ASIC start/stop logic with cycle-fair scheduling
├── networking.py        # Internet bonding + dummy Stratum pool fallback
├── api.py               # Flask dashboard endpoint
└── alerts.py            # Twilio SMS + Grafana alerting
tests/
├── test_asic_control.py # Core scheduling algorithm tests
├── test_config.py       # Config validation tests
├── test_alerts.py       # Alert routing tests
└── test_api.py          # Dashboard endpoint tests
```

## Prerequisites

- **OS**: Ubuntu Server 24.04 LTS
- **Hardware**: Beelink SER5 Pro (or similar) with cooling and enclosure
- **Sensors**: SEL-735 and power sensors installed and networked
- **Services**: Redis, Mosquitto (MQTT broker), Prometheus, Grafana
- **Networking**: 4G LTE dongle, Starlink, and USB Ethernet adapter
- **Optional**: Twilio account (SMS alerts), Grafana API key (alert integration)

## Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/pengasuzie/bitcoin_mining_manager.git
   cd bitcoin_mining_manager
   ```

2. **Install system dependencies**:
   ```bash
   sudo apt update
   sudo apt install -y python3 python3-pip python3-venv redis-server mosquitto
   ```

3. **Create a virtual environment and install Python dependencies**:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

4. **Configure environment variables**:
   ```bash
   cp .env.example .env
   # Edit .env with your actual values (sensor IPs, API keys, etc.)
   ```

5. **Start supporting services**:
   ```bash
   sudo systemctl enable --now redis-server mosquitto
   ```

6. **Run**:
   ```bash
   python -m bitcoin_mining_manager
   ```

   Or set up as a systemd service for 24/7 operation:
   ```ini
   # /etc/systemd/system/mining-manager.service
   [Unit]
   Description=Bitcoin Mining Manager
   After=network.target redis-server.service mosquitto.service

   [Service]
   ExecStart=/path/to/bitcoin_mining_manager/.venv/bin/python -m bitcoin_mining_manager
   WorkingDirectory=/path/to/bitcoin_mining_manager
   Restart=always
   User=ubuntu
   Environment=PYTHONUNBUFFERED=1

   [Install]
   WantedBy=multi-user.target
   ```
   ```bash
   sudo systemctl enable --now mining-manager
   ```

## Configuration

All configuration is via environment variables (`.env` file). See [.env.example](.env.example) for the full list with descriptions.

Key settings:
| Variable | Default | Description |
|---|---|---|
| `GRID_SENSOR_IP` | `192.168.1.100` | SEL-735 Modbus TCP address |
| `ASIC_API_URL` | `http://192.168.1.200:4028` | CGMiner API base URL |
| `ALERT_THRESHOLD` | `49.5` | Grid frequency (Hz) below which ASICs shut down |
| `ASIC_POWER` | `3.5` | Power draw per ASIC (kW) |
| `POLL_INTERVAL` | `10` | Main loop interval (seconds) |
| `MOCK_MODE` | `false` | Simulated sensors for testing without hardware |
| `API_HOST` | `127.0.0.1` | Flask dashboard bind address |

## Testing

```bash
source .venv/bin/activate
python -m pytest tests/ -v
```

Use `MOCK_MODE=true` in `.env` to run the application without physical hardware.

## Hardware

- **Beelink SER5 Pro**: AMD Ryzen 5 5600U, 16–32 GB DDR4, 500 GB NVMe SSD, ~15W idle
- **Enclosure**: IP54 dust-resistant with external 120mm fan for >40C conditions
- **UPS**: APC Back-UPS 600VA
- **Network**: NETGEAR GS308 managed switch, USB Ethernet adapter for bonding
- **Sensors**: SEL-735 Power Quality Meter (Modbus TCP), current/voltage transformers (MQTT)

## Development

```bash
# Run with mock sensors (no hardware needed)
MOCK_MODE=true python -m bitcoin_mining_manager
```

### Development tasks

- **Sensor integration**: implement MQTT parsing for your specific current/voltage sensors, test SEL-735 connectivity
- **ASIC integration**: configure CGMiner API endpoints, populate SQLite with ASIC IDs
- **Performance**: monitor CPU usage (<80% under full load), tune `POLL_INTERVAL`
- **Reliability**: stress test for grid drops, power outages, internet failures
- **Dashboards**: create Grafana dashboards, configure Prometheus alerts, test Twilio SMS

## Troubleshooting

- **Sensor errors**: check Modbus TCP (`GRID_SENSOR_IP`) or MQTT (`MQTT_BROKER`) connectivity
- **ASIC API failures**: verify `ASIC_API_URL` and network switch configuration
- **High CPU usage**: increase `POLL_INTERVAL` or check async call patterns
- **Logs**: review `mining_manager.log` for detailed errors
- **Thermal issues**: monitor CPU temperature with `sensors` command

## License

[MIT](LICENSE)
