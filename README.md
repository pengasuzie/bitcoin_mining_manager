# Bitcoin Mining Manager

## Overview
The **Bitcoin Mining Manager** is a Python-based software system designed to manage a Bitcoin mining data center housed in a shipping container in remote Africa. Running on a **Beelink SER5 Pro** mini PC, it controls 160 ASICs, monitors energy supply and demand, manages internet connectivity, and provides real-time dashboards and alerts. The system optimizes mining operations in a harsh environment (high temperatures, dust, humidity) by dynamically adjusting ASIC activity based on energy availability.

This repository contains the core software (`bitcoin_mining_manager.py`) and supporting files for developers to deploy, customize, and optimize the system during a 3–6-month pilot period. The project is built for **Ubuntu Server 24.04 LTS** and integrates with industrial sensors, networking tools, and monitoring platforms.

## Key Features
- **Energy Demand Monitoring**:
  - Monitors grid frequency using a SEL-735 Power Quality Meter via Modbus TCP.
  - Detects demand fluctuations (e.g., <49.5 Hz) to adjust ASIC operations.
- **Energy Supply Optimization**:
  - Tracks power supply via current/voltage sensors (e.g., INA219) using MQTT.
  - Calculates available power (kW) to prevent overloading.
- **ASIC Control**:
  - Manages 160 ASICs with an algorithm that prioritizes units with fewer cycles and older last-off times.
  - Uses asynchronous API calls (`aiohttp`) to CGMiner or equivalent for efficient on/off control (~16–32 requests/second).
  - Tracks cycles in SQLite and caches status in Redis.
- **Local Dummy Mining Pool**:
  - Runs a Stratum server (`stratum-mining`) during internet outages to maintain load stability.
  - Automatically switches ASICs to localhost:3333 when connectivity drops.
- **Internet Connectivity**:
  - Bonds two connections (e.g., 4G LTE, Starlink) using OpenMPTCProuter for <1% share loss.
  - Supports Gigabit Ethernet and USB Ethernet adapters, with Wi-Fi 6 as backup.
- **Real-Time Dashboards and Alerts**:
  - Visualizes grid frequency, ASIC status, power usage, and network status in Grafana (localhost:3000).
  - Collects metrics with Prometheus (localhost:9090) and serves data via a Flask API (localhost:5000).
  - Sends alerts via Prometheus Alertmanager and Twilio SMS for critical events (e.g., low grid frequency, high power usage).
- **Reliability**:
  - Comprehensive logging (`mining_manager.log`) for debugging.
  - Runs as a systemd service for 24/7 operation.
  - Error handling for sensor failures, API timeouts, and network issues.
- **Scalability**:
  - Designed for 160 ASICs, with potential to scale to 200+ using Redis caching and async I/O.
  - Optimized for Beelink SER5 Pro’s 6-core AMD Ryzen 5 5600U and 16–32 GB RAM.

## Hardware Requirements
- **Beelink SER5 Pro**:
  - CPU: AMD Ryzen 5 5600U (6-core, 12-thread, up to 4.2 GHz).
  - RAM: 16–32 GB DDR4.
  - Storage: 500 GB NVMe SSD.
  - Ports: 4x USB 3.2, 1x USB-C, Gigabit Ethernet, Wi-Fi 6.
  - Power: 12V DC, ~15W idle.
- **Environmental Setup**:
  - IP54 dust-resistant enclosure.
  - External 120mm fan for cooling in >40°C conditions.
  - APC Back-UPS 600VA UPS for power stability.
  - Shipping container with evaporative cooling (e.g., EZ Smartbox water wall).
- **Networking**:
  - NETGEAR GS308 managed switch for ASIC connectivity.
  - USB Ethernet adapter for internet bonding (4G LTE + Starlink).
- **Sensors**:
  - SEL-735 Power Quality Meter (Ethernet, Modbus TCP) for grid frequency.
  - Current/voltage transformers (USB/Ethernet, MQTT) for power monitoring.

## Project Structure
bitcoin-mining-manager/
├── bitcoin_mining_manager.py  # Main Python script
├── requirements.txt           # Python dependencies
├── README.md                 # Project documentation
├── .gitignore                # Git ignore file
├── .env.example              # Template for environment variables
└── mining_manager.log        # Log file (generated on run)

text


## Prerequisites
- **Operating System**: Ubuntu Server 24.04 LTS.
- **Hardware**: Beelink SER5 Pro configured with cooling and enclosure.
- **Sensors**: SEL-735 and power sensors installed and networked.
- **Networking**: 4G LTE dongle, Starlink, and USB Ethernet adapter.
- **Accounts**:
  - Twilio account for SMS alerts.
  - Grafana API key for alert integration.

## Installation
1. **Clone the Repository**:
   ```bash
   git clone https://github.com/your-username/bitcoin-mining-manager.git
   cd bitcoin-mining-manager
Install System Dependencies:
bash

sudo apt update
sudo apt install -y python3.11 python3-pip redis-server mosquitto grafana
Install Python Dependencies:
bash

pip3 install -r requirements.txt
requirements.txt:
text

aiohttp>=3.8.5
paho-mqtt>=1.6.1
pymodbus>=3.6.4
redis>=5.0.1
flask>=2.2.2
grafana-api>=1.0.3
prometheus-client>=0.17.0
python-dotenv>=1.0.0
twilio>=8.10.0
Configure Environment Variables:
Copy .env.example to .env:
bash

cp .env.example .env
Edit .env with your settings:
text

GRID_SENSOR_IP=192.168.1.100
ASIC_API_URL=http://192.168.1.200:4028
MQTT_BROKER=localhost
GRAFANA_HOST=localhost:3000
GRAFANA_API_KEY=your_grafana_api_key
TWILIO_SID=your_twilio_sid
TWILIO_TOKEN=your_twilio_token
TWILIO_FROM=+1234567890
TWILIO_TO=+0987654321
ALERT_THRESHOLD=49.5
POLL_INTERVAL=10
ASIC_POWER=3.5
Set Up Services:
Grafana:
bash

sudo systemctl enable grafana-server
sudo systemctl start grafana-server
Access at http://localhost:3000 and configure dashboards.
Prometheus:
bash

wget https://github.com/prometheus/prometheus/releases/download/v2.45.0/prometheus-2.45.0.linux-amd64.tar.gz
tar xvfz prometheus-*.tar.gz
sudo mv prometheus-*/prometheus /usr/local/bin/
sudo nano /etc/systemd/system/prometheus.service
Add:
text

[Unit]
Description=Prometheus
After=network.target
[Service]
ExecStart=/usr/local/bin/prometheus --config.file=/etc/prometheus/prometheus.yml
Restart=always
[Install]
WantedBy=multi-user.target
Configure /etc/prometheus/prometheus.yml to scrape localhost:8000.
bash

sudo systemctl enable prometheus
sudo systemctl start prometheus
Mosquitto:
bash

sudo systemctl enable mosquitto
sudo systemctl start mosquitto
OpenMPTCProuter:
bash

sudo apt install openmptcprouter
sudo omr-admin bond eth0 usb0
Run the Script:
Test manually:
bash

python3 bitcoin_mining_manager.py
Set up as a systemd service:
bash

sudo nano /etc/systemd/system/mining-manager.service
Add:
text

[Unit]
Description=Bitcoin Mining Manager
After=network.target redis-server.service mosquitto.service
[Service]
ExecStart=/usr/bin/python3 /path/to/bitcoin-mining-manager/bitcoin_mining_manager.py
WorkingDirectory=/path/to/bitcoin-mining-manager
Restart=always
User=ubuntu
Environment=PYTHONUNBUFFERED=1
[Install]
WantedBy=multi-user.target
bash

sudo systemctl enable mining-manager
sudo systemctl start mining-manager


## Development Tasks
- **Developers are expected to**:

-- **Sensor Integration**:
Implement MQTT parsing in read_power_sensors() for specific current/voltage sensors.
Test SEL-735 connectivity and calibrate frequency readings.

-- **ASIC Integration**:
Configure CGMiner API endpoints for 160 ASICs.
Populate SQLite database with ASIC IDs.
Optimize async API calls for <2-second latency.

-- **Performance Optimization**:
Monitor CPU usage (<80% under full load) using htop.
Adjust POLL_INTERVAL or add Redis caching strategies for scalability.
Minimize share loss (<1%) via robust bonding.

-- **Reliability**:
Stress test for grid frequency drops, power outages, and internet failures.
Ensure thermal stability with cooling (check sensors command).
Enhance error handling for edge cases.

-- **Dashboards/Alerts**:
Create Grafana dashboards for grid frequency, ASIC status, power, and network.
Configure Prometheus alerts for critical thresholds.
Test Twilio SMS delivery.

-- **Pilot Period (3–6 Months)**:
Month 1–2: Setup hardware, sensors, and initial ASIC testing (10–20 units).
Month 3–4: Scale to 160 ASICs, bond internet, deploy dashboards.
Month 5–6: Optimize performance, stress test, and document.

## Contributing
Code Style: Follow PEP 8 for Python. Use type hints where applicable.
Commits: Use clear messages (e.g., "Add Redis caching for ASIC status").
Branches: Create feature branches (e.g., feat/mqtt-sensor) and submit pull requests to main.
Issues: Report bugs or enhancements via GitHub Issues.

## Testing:
Test locally with mock sensors and a small ASIC setup.
Use unittest for critical functions (e.g., control_asics).
Simulate outages to verify dummy pool.

## Troubleshooting
Sensor Errors: Check Modbus TCP (GRID_SENSOR_IP) or MQTT (MQTT_BROKER) connectivity.
ASIC API Failures: Verify ASIC_API_URL and network switch configuration.
High CPU Usage: Increase POLL_INTERVAL or optimize async calls.
Logs: Review mining_manager.log for detailed errors.
Thermal Issues: Monitor CPU temperature:
