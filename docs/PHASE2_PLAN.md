# Phase 2: Area-Based Control Integration

## Overview
Migrate from zone-based control to **area-based control** while maintaining backward compatibility. Areas are dynamically discovered from Home Assistant, replacing the static zones.json configuration.

## Current State
- ✅ **Phase 1 Complete**: Areas discovered with thermostats and sensors
- ✅ **API Ready**: `/api/areas` returns all areas with devices
- ❌ **Control Not Integrated**: ModeManager, ScheduleManager still use zones
- ❌ **State Not Persisted**: Area active_schedule and enabled status lost on restart

## Phase 2 Objectives

### 1. Update Schedule Manager for Areas
**Goal**: Apply schedules to thermostats in a specific area

**Changes**:
- Add `apply_schedule_to_area()` method that:
  - Takes `area_id` instead of `zone_id`
  - Gets thermostats from `area_manager.get_area(area_id).thermostats`
  - Applies schedule to each thermostat
  - Updates `area.active_schedule`

**Location**: `app/core/schedule_manager.py`

---

### 2. Update Mode Manager for Areas
**Goal**: Apply system modes to all areas instead of zones

**Changes**:
- Update constructor to accept `area_manager` parameter
- Modify `_apply_default_mode()`:
  - Iterate over `area_manager.get_all_areas()` instead of `zone_manager.get_all_zones()`
  - Call new `apply_schedule_to_area()` method
- Modify `_apply_stay_home_mode()`:
  - Accept `active_areas` instead of `active_zones`
  - Same logic, different container
- Modify `_apply_holiday_mode()`:
  - Apply eco schedule to all areas
- Modify `_apply_off_mode()`:
  - Turn off all thermostats in all areas
- Modify `_apply_timer_mode()`:
  - Turn off all thermostats in all areas

**Location**: `app/core/mode_manager.py`

---

### 3. Persist Area Settings
**Goal**: Save `active_schedule` and `enabled` status per area

**Changes**:
- Areas need persistent state storage (currently lost on restart)
- Options:
  - **A) Input Selects** (Recommended): One input_select per area to store schedule
  - **B) Config File**: Save to persistent areas config file
  - **C) HA Helper**: Use HA helper entities for state

**Recommendation**: Use **Option A** (Input Selects)
- Integrates with HA seamlessly
- Visible in HA UI
- Survives restarts
- Already have pattern: `MODE_ENTITY=input_select.heating_mode`

**Implementation**:
- Create input_select entities in HA for each area (or auto-detect if they exist)
- Store active schedule per area
- Load on startup from HA state
- Update when schedule changes

---

### 4. New API Endpoints for Area Control
**Goal**: Provide area-specific control endpoints

**Endpoints**:
```
PUT /api/areas/{area_id}/schedule
  - Set active schedule for area
  - Body: {"schedule_id": "default"}
  
PUT /api/areas/{area_id}/enabled
  - Enable/disable area heating
  - Body: {"enabled": true}

GET /api/areas/{area_id}/status
  - Get current status (already exists from Phase 1)
```

**Location**: `app/api/routes/areas.py` (extend existing)

---

### 5. Update Mode API Endpoints
**Goal**: Modes work with areas instead of zones

**Endpoints Updated**:
```
POST /api/modes/stay-home
  - Parameter: active_areas (instead of active_zones)
  - Example: active_areas=["kitchen", "bedroom"]

GET /api/modes/status
  - Return areas instead of zones
  - Same structure, different container
```

**Location**: `app/api/routes/modes.py`

---

### 6. Update Startup Flow
**Goal**: Initialize area control system properly

**Changes in `app/main.py`**:
- Already initializes AreaManager ✓
- Pass `area_manager` to ModeManager constructor
- Initialize area state from HA
- Restore mode from HA (existing, works as-is)

---

## Implementation Sequence

### Step 1: Add Area Methods to ScheduleManager
1. Create `apply_schedule_to_area(area_manager, area_id, schedule_id)` method
2. Internally calls existing `apply_schedule_to_thermostat()` for each thermostat
3. Update `area.active_schedule` after success

### Step 2: Update ModeManager Constructor & Init
1. Accept `area_manager` parameter
2. Store as instance variable
3. Update logging

### Step 3: Update Mode Application Methods
1. `_apply_default_mode()` - iterate areas instead of zones
2. `_apply_stay_home_mode()` - iterate areas, accept active_areas parameter
3. `_apply_holiday_mode()` - iterate areas
4. `_apply_timer_mode()` - no changes needed (applies to all)
5. `_apply_off_mode()` - no changes needed (applies to all)

### Step 4: Add Area State Persistence
1. Create helper method to load area state from HA
2. Create helper method to persist area state to HA
3. Call on startup and after schedule/enabled changes

### Step 5: Extend Area API Routes
1. Add PUT endpoints for schedule assignment
2. Add PUT endpoints for enable/disable
3. Implement schedule persistence via updates

### Step 6: Update Mode API Endpoints
1. Update `/api/modes/stay-home` to accept `active_areas` parameter
2. Update status endpoint to return areas instead of zones

### Step 7: Testing & Validation
1. Test each mode with areas
2. Test schedule persistence
3. Test area enable/disable
4. Test HA integration

---

## Backward Compatibility

**Phase 2 Can Coexist With Zones**:
- Keep ZoneManager for now (don't remove)
- Modes can support both zones and areas
- Gradually deprecate zones in Phase 3

**No Breaking Changes**:
- Existing zone endpoints still work
- Mode API can accept both active_zones and active_areas
- Zones slowly phased out

---

## Estimated Effort

- **Step 1-3**: ~2 hours (core mode logic changes)
- **Step 4**: ~1 hour (state persistence)
- **Step 5-6**: ~1.5 hours (API endpoints)
- **Step 7**: ~1 hour (testing)

**Total**: ~5.5 hours

---

## Files to Modify

1. **`app/core/schedule_manager.py`**
   - Add `apply_schedule_to_area()` method
   - Keep existing zone methods for backward compatibility

2. **`app/core/mode_manager.py`**
   - Add `area_manager` parameter to constructor
   - Update all mode application methods
   - Add area state persistence methods

3. **`app/api/routes/areas.py`**
   - Extend with PUT endpoints for schedule/enabled
   - Add persistence implementation

4. **`app/api/routes/modes.py`**
   - Update stay-home endpoint to accept active_areas
   - Update status endpoint to return areas

5. **`app/main.py`**
   - Pass area_manager to ModeManager
   - Initialize area state from HA

6. **`app/dependencies.py`**
   - No changes (already has all managers)

---

## Success Criteria

- ✅ All modes work with areas
- ✅ Schedules persist per area
- ✅ Area enabled/disabled status persists
- ✅ API endpoints fully functional
- ✅ HA integration seamless
- ✅ Backward compatible with zones (for now)
- ✅ All modes tested (default, stay-home, holiday, timer, off, manual)

---

## Next Steps After Phase 2

**Phase 3**: Deprecation & Cleanup
- Remove zone-based endpoints
- Remove zones.json dependency
- Remove ZoneManager
- Clean up old zone-related code

---

## Questions for Discussion

1. **Input Select per Area**: Should we auto-create input_select entities for each area, or expect them to exist?
   - Proposed: Auto-create in HA via service call on startup

2. **Active Areas Parameter**: Stay-home mode - should it support individual area enable/disable, or just active areas list?
   - Proposed: Just active areas list (simpler, same as current active_zones)

3. **Area Enable/Disable**: Should disabling an area turn it off immediately, or just skip it in next mode application?
   - Proposed: Just skip it in mode application (lazy disable)
