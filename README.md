
docker run -d -p 8321:8321 \
# Heating Controller API — User Guide

Easily automate and control your Zigbee TRVZB thermostats and heating zones via a simple REST API. This system integrates with Home Assistant (HA) for real-time monitoring and advanced scheduling, but you interact with it using a modern, documented API.

---

## What Can You Do With This API?

- Set your home's heating mode (e.g. eco, stay-home, off, timer, ventilation)
- Get the current system mode and status of all zones/thermostats
- Change which rooms are heated and when, using flexible schedules
- Integrate with your own apps, automations, or dashboards

---

## Quick Start for API Users

### 1. Deploy the Controller

**Recommended:** Use Docker Compose (see below). The API will be available on port 8321 by default.

### 2. Connect to the API

- OpenAPI docs: [http://localhost:8321/docs](http://localhost:8321/docs)
- All endpoints are unauthenticated by default (unless you add a proxy or auth layer)

### 3. Set Up Your Heating Zones and Schedules

Edit the config files (see below) to match your home. Restart the container after changes.

---

## Example API Usage

### Get Current System Mode

```bash
curl http://localhost:8321/api/modes/current
```

### Set System Mode (e.g. Eco Mode for When Away)

```bash
curl -X POST http://localhost:8321/api/modes/set \
  -H "Content-Type: application/json" \
  -d '{"mode": "eco"}'
```

### Set Stay Home Mode for Specific Areas

```bash
curl -X POST http://localhost:8321/api/modes/set \
  -H "Content-Type: application/json" \
  -d '{"mode": "stay_home", "active_areas": ["bedroom", "kitchen"]}'
```

### List Available Modes

```bash
curl http://localhost:8321/api/modes
```

### Get Full System Status

```bash
curl http://localhost:8321/api/modes/status
```

---

## How to Configure Your System

### 1. Home Assistant Connection

Create a `.env` file (see `.env.example`) and set:
- `HA_WEBSOCKET_URL` (e.g. `ws://homeassistant.local:8123/api/websocket`)
- `HA_ACCESS_TOKEN` (long-lived token from HA profile)

### 2. Define Your Zones

Edit `config/zones.json` to list each room/zone, thermostats, and sensors. Example:
```json
[
  {
    "id": "bedroom",
    "name": "Bedroom",
    "thermostats": ["climate.bedroom_thermostat"],
    "temperature_sensors": ["sensor.bedroom_temp"],
    "humidity_sensors": ["sensor.bedroom_humidity"],
    "active_schedule": "default",
    "enabled": true
  }
]
```

### 3. Set Up Schedules

Each file in `config/schedules/` defines a schedule. Use the `week` key (not `weekly_schedule`). Example:
```json
{
  "id": "default",
  "name": "Default",
  "description": "Standard work week schedule",
  "week": {
    "monday": "workday",
    "tuesday": "workday",
    "wednesday": "workday",
    "thursday": "workday",
    "friday": "workday",
    "saturday": "weekend_day",
    "sunday": "weekend_day"
  }
}
```
Day types (see `config/day_types.json`) define the actual time/temperature strings for each day type.

### 4. Map Thermostats

Edit `config/thermostat_mapping.json` to map logical thermostat IDs to Zigbee2MQTT device names.

---

## Home Assistant Integration (What to Expect)

- The controller updates HA’s input_select to reflect the current mode, but changes in HA do NOT change the controller’s mode.
- All thermostats, sensors, and input_selects must exist in HA and be mapped in your config files.
- Schedules are pushed to TRVs via Zigbee2MQTT.

---

## Deployment (for API Users)

### Docker Compose (Recommended)

1. Edit `docker-compose.yml` to mount your config and data directories.
2. Start the service:
   ```bash
   docker-compose up -d
   ```
3. The API will be available on port 8321.

### Manual Docker

```bash
docker build -t heating_controller .

  -v $(pwd)/config:/app/config \
  -v $(pwd)/data:/app/data \
  heating_controller
```

---

## Troubleshooting for API Users

- **Schedule validation errors:** Make sure all schedule files use the `week` key, not `weekly_schedule`.
- **HA connection issues:** Double-check `.env` and your HA token permissions.
- **Mode not changing in HA:** Only controller-originated changes sync to HA.
- **API not responding:** Check container logs and ensure port 8321 is open.

---

## License

MIT

