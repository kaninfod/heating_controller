# Heating Controller API

A REST API for managing multi-zone heating systems with Home Assistant integration. Control your Zigbee thermostats, define heating schedules, and manage different heating modes—all through a simple API or Home Assistant automations.

## Features

- 🏠 **Multi-zone control** - Manage heating independently for each room/area
- 📅 **Smart scheduling** - Define custom schedules with workday/weekend/holiday variations
- 🎛️ **Mode switching** - Quick preset modes: default, stay_home, eco, timer, manual, off, ventilation
- 🏡 **Home Assistant integration** - Automatic area discovery, real-time synchronization, MQTT-based control
- 🌡️ **TRV support** - Direct control of Zigbee2MQTT radiator thermostats
- 📊 **REST API** - Full OpenAPI documentation at `/docs`

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Home Assistant instance with WebSocket access
- Zigbee2MQTT (to control TRV devices)
- Climate entities configured in Home Assistant

### 1. Deploy

```bash
git clone https://github.com/kaninfod/heating_controller.git
cd heating_controller

# Create configuration
cp .env.example .env

# Edit .env with your values
nano .env

# Start
docker-compose up -d
```

The API will be available at `http://localhost:8000`.

### 2. Configure Home Assistant

Create an `input_select` entity for heating modes:

```yaml
input_select:
  heating_mode:
    name: Heating Mode
    options:
      - default
      - stay_home
      - eco
      - timer
      - manual
      - off
      - ventilation
    initial: default
```

### 3. Map Your Thermostats

Edit `config/thermostat_mapping.json` to match your setup:

```json
{
  "climate.bedroom_thermostat": "bedroom thermostat",
  "climate.kitchen_thermostat": "kitchen thermostat",
  "climate.living_room_thermostat": "living room thermostat"
}
```

The controller automatically discovers areas from Home Assistant.

## API Overview

### Get System Status

```bash
curl http://localhost:8000/api/status
```

### Change Heating Mode

```bash
curl -X POST http://localhost:8000/api/modes/default
```

Available modes:
- `default` - Normal schedule
- `stay_home` - Generate optimized schedule for staying home
- `eco` - Energy-saving mode
- `timer` - Temporary timer mode
- `manual` - Manual control without schedule
- `off` - Turn off heating
- `ventilation` - Ventilation only

### List Areas

```bash
curl http://localhost:8000/api/areas
```

### Get Available Schedules

```bash
curl http://localhost:8000/api/schedules
```

### View Schedule Details

```bash
curl http://localhost:8000/api/schedules/default
```

### Set Temperature Override

```bash
curl -X POST http://localhost:8000/api/areas/bedroom/temperature \
  -H "Content-Type: application/json" \
  -d '{"temperature": 22}'
```

### Interactive API Documentation

Open [http://localhost:8000/docs](http://localhost:8000/docs) in your browser to explore all endpoints with a UI.

## Configuration

### Environment Variables (`.env`)

```env
# Home Assistant WebSocket connection
HA_WEBSOCKET_URL=wss://your-ha-instance/api/websocket
HA_ACCESS_TOKEN=eyJ0eXA...  # Long-lived access token from HA profile

# Heating mode input_select entity
MODE_ENTITY=input_select.heating_mode

# Areas to exclude from control (comma-separated)
# Leave empty to control all discovered areas
BLACKLISTED_AREAS=

# Logging
LOG_LEVEL=DEBUG
SYSLOG_HOST=192.168.1.100
SYSLOG_PORT=514
```

### Thermostat Mapping

**File:** `config/thermostat_mapping.json`

Maps Home Assistant climate entities to Zigbee2MQTT device names:

```json
{
  "climate.bedroom_thermostat": "bedroom thermostat",
  "climate.kitchen_thermostat": "kitchen thermostat"
}
```

### Schedule Templates

**File:** `config/day_types.json`

Defines temperature curves for different day types:

```json
{
  "workday": "09:00/21 12:00/18 17:00/21 22:00/17 23:00/16",
  "weekend": "09:00/20 12:00/18 17:00/20 22:00/17 23:00/16"
}
```

Format: `HH:MM/TEMPERATURE` separated by spaces

### Predefined Schedules

**Directory:** `config/schedules/`

Contains JSON files defining weekly schedules:

```json
{
  "monday": "workday",
  "tuesday": "workday",
  "wednesday": "workday",
  "thursday": "workday",
  "friday": "workday",
  "saturday": "weekend",
  "sunday": "weekend"
}
```

## Home Assistant Integration

### Automatic Area Discovery

The controller automatically discovers areas from Home Assistant. Each area with climate entities is available for control.

### Mode Synchronization

When you change the heating mode via the API, it updates the `input_select.heating_mode` entity in Home Assistant.

### MQTT Integration

Schedules are published to Zigbee2MQTT via MQTT topics:

```
zigbee2mqtt/{device_name}/set
```

The controller handles publishing schedule updates automatically when switching modes.

### Example Automation

Automatically switch to eco mode when no one is home:

```yaml
automation:
  - alias: "Heating: Away Mode"
    trigger:
      - platform: state
        entity_id: group.all_people
        to: "not_home"
    action:
      - service: input_select.select_option
        target:
          entity_id: input_select.heating_mode
        data:
          option: "eco"
```

## Troubleshooting

### "No areas discovered"

1. Verify Home Assistant connection:
   - Check `.env` has correct `HA_WEBSOCKET_URL` and `HA_ACCESS_TOKEN`
   - Ensure access token is a long-lived token from HA profile
   - Verify network connectivity to Home Assistant

2. Check area configuration:
   - Navigate to Settings → Areas in Home Assistant
   - Create areas and assign devices to them
   - At least one area must have a climate entity

3. View logs:
   ```bash
   docker-compose logs app | grep -i area
   ```

### "Thermostats not updating"

1. Verify thermostat mapping:
   ```bash
   cat config/thermostat_mapping.json
   ```
   - Climate entity IDs must match Home Assistant exactly
   - Z2M device names must match Zigbee2MQTT device names

2. Check MQTT connectivity:
   ```bash
   docker-compose logs app | grep -i mqtt
   ```
   - Zigbee2MQTT must be running and accessible

3. Verify Zigbee pairing:
   - Device must be paired in Zigbee2MQTT
   - Device name must be exactly as specified in mapping

### "Wrong schedule after restart"

The controller caches schedules in memory. This is normal. To reset:

```bash
docker-compose restart app
```

### "API endpoint returns 503"

1. Check logs:
   ```bash
   docker-compose logs app
   ```

2. Verify Home Assistant is reachable:
   ```bash
   curl $HA_WEBSOCKET_URL
   ```

3. Restart the service:
   ```bash
   docker-compose restart app
   ```

## Advanced Configuration

### Blacklisting Areas

To prevent specific areas from being controlled:

```env
BLACKLISTED_AREAS=garage,storage,office
```

The controller will skip these areas during discovery.

### Logging Configuration

Set log level in `.env`:

```env
LOG_LEVEL=DEBUG   # Verbose logging
LOG_LEVEL=INFO    # Standard logging
LOG_LEVEL=WARNING # Errors only
```

Send logs to syslog server:

```env
SYSLOG_HOST=192.168.1.100
SYSLOG_PORT=514
```

View logs locally:

```bash
docker-compose logs -f app
```

## License

[Add license information]

## Contributing

Contributions are welcome. Please open an issue or pull request on GitHub.

## Support

For issues or questions, please open an issue on the GitHub repository.

