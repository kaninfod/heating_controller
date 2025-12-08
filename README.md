# Heating Control System

Central heating control system for Raspberry Pi to supervise 6 TRVZB thermostats via Home Assistant.

## Features

- **Real-time monitoring** of thermostats, temperature sensors, and humidity sensors via Home Assistant WebSocket
- **Zone management** - Group thermostats into logical zones
- **Schedule management** - Define and apply heating schedules to zones
- **System modes** - Holiday, stay-home, timer, and other supervisory modes (coming soon)
- **REST API** - Control and monitor your heating system

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

Copy `.env.example` to `.env` and update with your Home Assistant details:

```bash
cp .env.example .env
```

Edit `.env`:
- Set `HA_WEBSOCKET_URL` to your Home Assistant WebSocket URL
- Set `HA_ACCESS_TOKEN` to your long-lived access token
- Update entity IDs for your thermostats and sensors

### 3. Configure Zones

Edit `config/zones.json` to define your heating zones and assign thermostats/sensors to each zone.

### 4. Create Schedules

Add schedule files to `config/schedules/`. Each schedule is a JSON file with the TRVZB weekly schedule format.

Example schedules are provided:
- `weekday_work.json` - Workday schedule
- `weekend.json` - Weekend schedule
- `holiday.json` - Away/holiday minimal heating
- `stay_home.json` - All-day comfort heating

### 5. Run the Application

```bash
python -m app.main
```

Or with uvicorn:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 6. Access the API

- **API Documentation**: http://localhost:8000/docs
- **Status Endpoint**: http://localhost:8000/api/status

## API Endpoints

### Status
- `GET /api/status` - Full system status (all thermostats, sensors, zones)
- `GET /api/status/thermostats` - All thermostats
- `GET /api/status/thermostats/{entity_id}` - Specific thermostat
- `GET /api/status/sensors/temperature` - All temperature sensors
- `GET /api/status/sensors/humidity` - All humidity sensors
- `GET /api/status/connection` - Home Assistant connection status

### Health
- `GET /health` - Application health check

## Project Structure

```
/workspace/
├── app/
│   ├── main.py                 # FastAPI application
│   ├── config.py               # Configuration loader
│   ├── models/
│   │   └── state.py           # Data models
│   ├── services/
│   │   └── ha_websocket.py    # Home Assistant WebSocket client
│   ├── core/                  # Business logic (future)
│   └── api/
│       └── routes/
│           └── status.py      # Status API routes
├── config/
│   ├── zones.json            # Zone definitions
│   └── schedules/            # Schedule files
├── data/
│   └── state.json           # Runtime state (auto-generated)
├── logs/
│   └── app.log             # Application logs
├── .env                     # Configuration (create from .env.example)
└── requirements.txt         # Python dependencies
```

## TRVZB Schedule Format

Schedules use the TRVZB format: `"HH:MM/TEMP HH:MM/TEMP ..."`

Example:
```json
"monday": "00:00/17 06:30/19 07:00/20 09:30/17 16:00/21 23:00/17"
```

This means:
- 00:00 - Set to 17°C
- 06:30 - Set to 19°C
- 07:00 - Set to 20°C
- 09:30 - Set to 17°C
- 16:00 - Set to 21°C
- 23:00 - Set to 17°C

## Development Status

### Phase 1 (Current) ✓
- [x] Home Assistant WebSocket connection
- [x] Real-time entity monitoring
- [x] Status API endpoints
- [x] Configuration management

### Phase 2 (Planned)
- [ ] Zone orchestration
- [ ] Schedule distribution to thermostats
- [ ] Schedule management API

### Phase 3 (Planned)
- [ ] System modes (holiday, stay-home, timer)
- [ ] Mode management API

### Phase 4 (Planned)
- [ ] Bathroom fan control
- [ ] Advanced automation rules

## License

MIT
# heating_controller
