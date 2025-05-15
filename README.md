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
