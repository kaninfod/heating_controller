# Migration Analysis: Zones → HA Areas

## Current Architecture

### Current Zone System
- **Source**: `config/zones.json` - manually maintained JSON file
- **Structure**: List of zone objects containing:
  - `id`: Unique identifier
  - `name`: Display name
  - `thermostats`: List of climate entity IDs
  - `temperature_sensors`: List of sensor entity IDs
  - `humidity_sensors`: List of sensor entity IDs
  - `active_schedule`: Currently assigned schedule
  - `enabled`: Boolean flag

### Current Implementation
- **ZoneManager** (`app/core/zone_manager.py`): Loads zones from JSON, provides CRUD operations
- **API Routes** (`app/api/routes/zones.py`): Exposes zones via REST endpoints
- **HA WebSocket** (`app/services/ha_websocket.py`): Maintains entity state cache but doesn't fetch area data
- **Models** (`app/models/state.py`): Defines `Zone` model

### Current Data Flow
1. Zones loaded from `config/zones.json`
2. ZoneManager tracks thermostats and sensors per zone
3. API exposes zone data and status
4. Modes controller uses zones to apply heating rules

---

## Proposed HA Areas System

### Key Concepts
- **7 HA Areas total** with the following configuration:
  - 5 areas with 1 thermostat each
  - 1 area with 2 thermostats
  - 2 areas with no thermostats (excluded from control)
  - Some thermostats have associated temperature/humidity sensors

### Advantages
1. **Single source of truth**: HA areas are already defined in HA
2. **Less maintenance**: No manual JSON updates when areas change in HA
3. **Automatic discovery**: Can fetch all areas and filter by thermostat presence
4. **Dynamic**: Easy to add new areas in HA without code/config changes

### Implementation Strategy

#### Phase 1: Add HA Area Discovery (Non-Breaking)
Create new `AreaManager` parallel to `ZoneManager`:

1. **Fetch HA Areas**
   - Add method to `HomeAssistantWebSocket` to call HA API
   - Use WebSocket RPC: `config/area_registry/list` message
   - Returns all area definitions with area_id, name, icon

2. **Map Devices to Areas**
   - Use HA's device registry: `config/device_registry/list`
   - Use HA's entity registry: `config/entity_registry/list`
   - Map thermostats → areas, temp sensors → areas, humidity sensors → areas

3. **Build HAArea Objects**
   - Create new `HAArea` model (similar to `Zone` but with HA metadata)
   - Filter areas: only include those with thermostats
   - Aggregate sensors per area

4. **Create AreaManager Service**
   - Load all areas on startup
   - Provide same interface as ZoneManager: `get_all_areas()`, `get_area()`, `get_area_status()`
   - Cache area→entity mappings

5. **Add API Endpoints** (`/api/areas/`)
   - `GET /api/areas` - list all active areas with thermostats
   - `GET /api/areas/{area_id}` - get specific area with current device data
   - Same status format as zones (thermostats, sensors, averages)

#### Phase 2: Integrate into Modes Control
- Update ModeManager to work with areas instead of zones
- Apply heating profiles per area
- Maintain backward compatibility with existing schedules

#### Phase 3: Phase Out Zones
- Deprecate zone endpoints
- Migrate persisted state from zones to areas
- Remove zones.json dependency

---

## Technical Implementation Details

### New Model: HAArea
```python
class HAArea(BaseModel):
    """Represents a HA area with its connected devices"""
    area_id: str           # HA's area ID
    name: str              # Display name
    icon: Optional[str]    # Icon identifier
    thermostats: List[str] # Climate entity IDs in this area
    temperature_sensors: List[str]  # Temp sensor entities
    humidity_sensors: List[str]     # Humidity sensor entities
    active_schedule: Optional[str]  # Current schedule (new field)
    enabled: bool = True            # Control flag
```

### New Service: AreaManager
Location: `app/core/area_manager.py`

**Key Methods**:
```python
async def discover_areas() -> Dict[str, HAArea]
    # Fetch HA areas and build HAArea objects

async def get_all_areas() -> List[HAArea]

async def get_area(area_id: str) -> Optional[HAArea]

async def get_area_status(area_id: str, ha_client) -> dict
    # Returns thermostats, sensors, averages (same as zone status)

async def assign_schedule_to_area(area_id: str, schedule_id: str) -> bool

async def get_all_thermostat_areas() -> Dict[str, HAArea]
    # Returns only areas with thermostats
```

### HA WebSocket Extensions
Add methods to `HomeAssistantWebSocket`:
```python
async def fetch_areas() -> List[Dict]
    # Calls HA's area registry

async def fetch_devices() -> List[Dict]
    # Calls HA's device registry

async def fetch_entities() -> List[Dict]
    # Calls HA's entity registry

async def get_area_entities(area_id: str) -> List[Dict]
    # Gets all entities in a specific area
```

### Data Flow (New)
```
HA Setup
  ├── Areas defined in HA
  ├── Devices assigned to areas
  ├── Entities (climate, sensors) assigned to devices
  │
  └─→ AreaManager discovers on startup
        ├── Fetch areas via HA API
        ├── Fetch devices & entities via HA API
        ├── Map thermostats/sensors to areas
        ├── Filter areas (only keep those with thermostats)
        └── Build HAArea objects
              │
              └─→ API endpoints serve areas
                    ├── GET /api/areas
                    └── GET /api/areas/{id}
                          │
                          └─→ ModeManager (Phase 2)
                                Apply heating rules per area
```

---

## Challenge Areas & Solutions

### Challenge 1: Finding Entities in an Area
**Problem**: HA's area registry doesn't directly list entities. Need to traverse registries.

**Solution**:
1. Fetch entity registry → get all entities with their device_id
2. Fetch device registry → get all devices with their area_id
3. Cross-reference: entity → device → area

**Code Approach**:
```python
# entities have: entity_id, device_id
# devices have: device_id, area_id
# Build: area_id → [entity_ids]

entities = await ha_client.fetch_entities()  # {device_id, entity_id}
devices = await ha_client.fetch_devices()    # {device_id, area_id}

area_entities = defaultdict(list)
for entity in entities:
    if entity['device_id']:
        device = next((d for d in devices if d['id'] == entity['device_id']), None)
        if device and device['area_id']:
            area_entities[device['area_id']].append(entity['entity_id'])
```

### Challenge 2: Entity Type Detection
**Problem**: Need to distinguish thermostats from sensors automatically.

**Solution**:
- Climate entities are thermostats: `entity_id.startswith('climate.')`
- Sensors with 'temp' in name/entity_id are temperature sensors
- Sensors with 'humid' in name/entity_id are humidity sensors
- Match by friendly_name or use entity metadata

### Challenge 3: Persistence Across HA Changes
**Problem**: If someone moves a device to a new area in HA, we need to adapt.

**Solution**:
- On startup, always refresh area→entity mappings
- Cache with TTL (refresh every 5-10 minutes)
- Watch for config changes in HA (use `config_entries` events)

### Challenge 4: Backward Compatibility
**Problem**: Existing schedules and data reference zone IDs.

**Solution**:
- Keep zones in parallel during Phase 1 & 2
- Optionally add a mapping: `zone_id → area_id`
- Gradual migration: new deployments use areas, existing keep zones
- Provide migration utility for existing schedules

---

## API Changes

### New Endpoints (Phase 1)
```
GET  /api/areas              # List all areas with thermostats
GET  /api/areas/{area_id}    # Get specific area with status
PUT  /api/areas/{area_id}    # Update area settings (schedule, enabled)
```

### Response Format (Same as Zones)
```json
{
  "area_id": "bedroom",
  "name": "Bedroom",
  "icon": "bedroom",
  "thermostats": [
    {
      "entity_id": "climate.bedroom",
      "friendly_name": "Bedroom Thermostat",
      "current_temperature": 21.5,
      "target_temperature": 20.0,
      "mode": "heat",
      "available": true,
      "last_updated": "2025-12-11T10:30:00Z"
    }
  ],
  "temperature_sensors": [...],
  "humidity_sensors": [...],
  "average_temperature": 21.5,
  "average_humidity": 45.0,
  "active_schedule": "default",
  "enabled": true
}
```

---

## Dependencies & Requirements

### WebSocket Messages Needed
All can be done via WebSocket RPC (no HTTP calls needed):

1. **Get Areas**
   ```json
   {"id": 1, "type": "call_service", "domain": "config", "service": "area_registry_list"}
   ```
   Alternative: Custom WebSocket call `config/area_registry/list`

2. **Get Devices**
   ```json
   {"id": 2, "type": "call_service", "domain": "config", "service": "device_registry_list"}
   ```

3. **Get Entities**
   ```json
   {"id": 3, "type": "call_service", "domain": "config", "service": "entity_registry_list"}
   ```

### HA Requirements
- Home Assistant API access (WebSocket + HTTP REST if needed)
- Proper permissions in HA token
- Access to registries (usually built-in)

---

## Migration Phases Summary

| Phase | Duration | What | Breaking |
|-------|----------|------|----------|
| **1** | Week 1 | Implement AreaManager, fetch areas, API endpoints | No |
| **2** | Week 2-3 | Integrate areas into modes/schedules control | No |
| **3** | Week 4+ | Deprecate zones, phase out zones.json | Yes, but optional |

---

## Next Steps

1. **Implement AreaManager** (`app/core/area_manager.py`)
   - Fetch areas from HA
   - Map entities to areas
   - Build HAArea objects

2. **Extend HomeAssistantWebSocket**
   - Add registry fetching methods
   - Handle registry queries

3. **Create HAArea Model** in `app/models/state.py`

4. **Add Area API Routes** (`app/api/routes/areas.py`)

5. **Test with Your Setup**
   - Verify area discovery works
   - Confirm thermostat/sensor mapping
   - Validate API responses

---

## Questions to Clarify

1. Should we keep zones.json as fallback if HA areas fetch fails?
2. Should area IDs be HA's IDs or human-friendly names?
3. Do you want automatic discovery on every startup, or cache with periodic refresh?
4. Should schedules be per-area or continue to be global?
5. Do you need migration script for existing zone-based configurations?
