# Quick Reference: Phase 1 HA Areas Integration

## 🎯 What You Get

Phase 1 adds automatic Home Assistant area discovery to your heating control system:

```
HA Areas (7) → Fetch → Filter → Discover → API
               Entities   (>2 thermo)   Routes
```

## 📍 Your Setup After Phase 1

```
Discovered Areas:
  ✓ Bedroom        [1 thermostat, temp sensor, humidity sensor]
  ✓ Kitchen        [1 thermostat, temp sensor, humidity sensor]
  ✓ Dining Room    [2 thermostats, temp sensor]
  ✓ Living Room    [1 thermostat]
  ✓ Office         [1 thermostat, temp sensor]
  
Skipped (no thermostats):
  ✗ Hallway
  ✗ Bathroom
```

## 🔧 Key Components

| Component | File | Purpose |
|-----------|------|---------|
| **HAArea** | `app/models/state.py` | Data model for areas |
| **AreaManager** | `app/core/area_manager.py` | Discovery & management |
| **Area Routes** | `app/api/routes/areas.py` | REST API endpoints |
| **HA Registry Fetching** | `app/services/ha_websocket.py` | Fetch areas/entities |

## 🔍 Entity Detection Logic

```python
# Uses DOMAIN + DEVICE_CLASS (not naming!)

if domain == 'climate':
    → Thermostat ✓

if domain == 'sensor' AND device_class == 'temperature':
    → Temperature Sensor ✓

if domain == 'sensor' AND device_class == 'humidity':
    → Humidity Sensor ✓

if domain == 'sensor' AND device_class == 'carbon_dioxide':
    → Filtered Out ✗
```

## 📡 API Endpoints

### List All Areas
```bash
GET /api/areas

Response: List[HAArea]
```

### Get Area with Current Data
```bash
GET /api/areas/{area_id}

Response: {
  "area": HAArea,
  "thermostats": List[ThermostatState],
  "temperature_sensors": List[SensorState],
  "humidity_sensors": List[SensorState],
  "average_temperature": float,
  "average_humidity": float
}
```

### Update Area
```bash
PUT /api/areas/{area_id}

Body: {
  "active_schedule": "default",  // optional
  "enabled": true                 // optional
}
```

## 🚀 Startup Process

```
1. FastAPI starts
   ↓
2. AreaManager created
   ↓
3. Connect to Home Assistant WebSocket
   ↓
4. Fetch areas, entities, devices from HA registries
   ↓
5. Group entities by area and type (domain + device_class)
   ↓
6. Build HAArea objects (only areas with thermostats)
   ↓
7. APIs available at /api/areas/*
   ↓
8. Check logs for: "Successfully discovered N areas..."
```

## ✅ Verification

After starting the app, check:

```bash
# In logs:
"Discovered area 'Bedroom': 1 thermostat(s), 1 temp sensor(s), 1 humidity sensor(s)"
"Successfully discovered 5 areas with heating devices"

# Via API:
curl http://localhost:8321/api/areas | jq '.[] | .area_id'
# Output: bedroom, kitchen, dining_room, living_room, office
```

## 🔗 What's Connected

```
HomeAssistantWebSocket
    ├─ fetch_areas()      → Area registry
    ├─ fetch_entities()   → Entity registry (with domain + device_class)
    └─ fetch_devices()    → Device registry
    
    ↓
    
AreaManager.discover_areas()
    ├─ _group_entities_by_area_and_type()
    │   └─ Uses domain + device_class for classification
    ├─ Filter areas with thermostats
    └─ Build HAArea objects
    
    ↓
    
SystemState
    └─ Cached thermostat and sensor states
    
    ↓
    
API Routes
    ├─ GET  /api/areas
    ├─ GET  /api/areas/{id}
    └─ PUT  /api/areas/{id}
```

## 📊 Data Flow

```
Home Assistant Setup
    │
    ├─ 7 areas (Bedroom, Kitchen, Dining, Living, Office, Hallway, Bathroom)
    ├─ Climate entities (thermostats)
    ├─ Sensor entities with device_class (temperature, humidity, CO2, etc)
    └─ Device assignments to areas
    │
    ↓ WebSocket: config/area_registry/list
    ↓ WebSocket: config/entity_registry/list
    ↓ WebSocket: config/device_registry/list
    │
AreaManager
    │
    ├─ Parse: area_id → area_name, icon
    ├─ Parse: entity + device_class → entity_type
    ├─ Group: (area_id, entity_type) → [entity_ids]
    ├─ Filter: keep only areas with thermostats
    └─ Build: HAArea objects
    │
    ↓
APIResponses
    │
    ├─ GET /api/areas
    │   └─ [HAArea, HAArea, ...]
    │
    └─ GET /api/areas/{id}
        └─ {
            "area": HAArea,
            "thermostats": [ThermostatState, ...],
            "temperature_sensors": [SensorState, ...],
            "humidity_sensors": [SensorState, ...],
            "average_temperature": 21.5,
            "average_humidity": 45.0
          }
```

## 🔄 Non-Breaking Design

✅ Zones still work normally
✅ API endpoints for zones unchanged
✅ No changes to modes or schedules (yet)
✅ Areas and zones coexist
✅ Can test areas independently

## 🆘 Troubleshooting

| Issue | Check |
|-------|-------|
| No areas discovered | HA connection status, entity assignments |
| Missing thermostats | Check `domain == 'climate'` |
| Missing temp sensors | Check `device_class == 'temperature'` |
| Missing humidity | Check `device_class == 'humidity'` |
| Wrong count | Check area assignments in HA device registry |
| Disabled entities | Entities with `disabled_by` are filtered |

## 📚 Documentation Files

- **PHASE1_IMPLEMENTATION.md** - Full technical details
- **PHASE1_CHECKLIST.md** - Verification & API usage
- **MIGRATION_ANALYSIS.md** - Complete migration strategy

## 🎯 Next: Phase 2

Phase 2 will integrate areas into:
- ModeManager (apply heating profiles per area)
- ScheduleManager (execute per-area)
- State persistence (save settings)

---

**Status**: Phase 1 ✅ Complete and Ready to Test
