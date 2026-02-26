# Bitcoin Mining Manager

Automated Bitcoin mining controller for behind-the-meter operations. Adjusts ASIC miner activity based on grid frequency and available power in real time.

Designed for a shipping container deployment with 160 ASICs, running on a Beelink SER5 Pro mini PC with Ubuntu Server 24.04 LTS.

## Key Features

- **Grid frequency monitoring** via SEL-735 Power Quality Meter (Modbus TCP) — detects demand fluctuations (e.g. <49.5 Hz) and shuts down ASICs to reduce load
- **Power supply tracking** via current/voltage sensors (MQTT) — calculates available kW to prevent overloading
- **Cycle-fair ASIC scheduling** — prioritises units with fewest on/off cycles for even wear distribution across 160 miners
- **Local fallback mining** — automatically starts a Stratum server during internet outages to maintain load stability
- **Internet bonding** — bonds two connections (4G LTE + Starlink) via OpenMPTCProuter for <1% share loss
- **Real-time dashboards** — built-in HTML dashboard at `/`, Prometheus metrics + Grafana visualisation, Flask REST API
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
├── api.py               # Flask REST API + dashboard serving
├── dashboard.html       # Self-contained HTML dashboard (served at /)
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

## Dashboard

The built-in HTML dashboard is served at `http://{API_HOST}:{API_PORT}/` (default `http://127.0.0.1:5000/`). It shows:

- **KPIs**: grid frequency, active ASICs, power usage, network status, system health
- **ASIC table**: sortable, filterable list of all 160 ASICs with status, cycle count, and last offline time
- **Auto-refresh**: polls the API every 10 seconds

No extra dependencies — it's a single self-contained HTML file with inline CSS/JS.

### API endpoints

| Endpoint | Description |
|---|---|
| `GET /` | HTML dashboard |
| `GET /dashboard` | JSON: grid frequency, active ASICs, power, network status |
| `GET /asics` | JSON: per-ASIC status, cycle count, last offline time |
| `GET /health` | JSON: service health (Redis, SQLite) |

## Mock Mode (development without hardware)

Set `MOCK_MODE=true` to run the full application without physical sensors, ASICs, or networking hardware. In mock mode:

- **Grid frequency** returns a fixed 50.0 Hz
- **Power sensors** return 560.0 kW (full capacity)
- **MQTT and internet bonding** are skipped entirely
- **Redis** is optional — the app starts without it (ASIC statuses show as "unknown")
- **ASIC API calls** will fail silently (no real hardware), but the control loop continues

### Quick start (mock mode)

```bash
# 1. Start Redis (optional, but needed for ASIC status badges)
docker compose up -d redis

# 2. Register 160 ASICs in the database
MOCK_MODE=true python -m bitcoin_mining_manager register --count 160

# 3. Start the application
MOCK_MODE=true python -m bitcoin_mining_manager

# 4. Open the dashboard
open http://127.0.0.1:5000/
```

### Seed realistic demo data

To populate the dashboard with realistic-looking ASIC statuses and cycle counts:

```bash
python3 -c "
import redis, random, sqlite3
from datetime import datetime, timedelta

r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
conn = sqlite3.connect('asic_cycles.db')
c = conn.cursor()

for i in range(160):
    aid = f'asic-{i:03d}'
    roll = random.random()
    if roll < 0.75: r.setex(f'asic:{aid}:status', 300, 'on')
    elif roll < 0.95: r.setex(f'asic:{aid}:status', 300, 'off')
    cycles = random.randint(0, 85)
    last_off = (datetime.now() - timedelta(hours=random.randint(1, 720))).isoformat() if cycles else None
    c.execute('UPDATE asics SET cycles=?, last_off=? WHERE id=?', (cycles, last_off, aid))

conn.commit()
conn.close()
print('Seeded 160 ASICs with mock data')
"
```

### Switching to production

To run with real hardware, remove `MOCK_MODE` (or set it to `false`) and ensure all services are configured:

1. Set real sensor IPs in `.env` (`GRID_SENSOR_IP`, `ASIC_API_URL`, `MQTT_BROKER`)
2. Start Redis and Mosquitto: `sudo systemctl enable --now redis-server mosquitto`
3. Run: `python -m bitcoin_mining_manager`

## Development

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
