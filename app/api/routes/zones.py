"""
Zone API routes
Manage heating zones
"""
from fastapi import APIRouter, HTTPException
from typing import List
from pydantic import BaseModel

from app.models.state import Zone
from app.dependencies import HAClient, ZoneManagerDep

router = APIRouter(prefix="/api/zones", tags=["zones"])


class ZoneCreate(BaseModel):
    """Request model for creating a zone"""
    id: str
    name: str
    thermostats: List[str] = []
    temperature_sensors: List[str] = []
    humidity_sensors: List[str] = []
    active_schedule: str | None = None
    enabled: bool = True


class ZoneUpdate(BaseModel):
    """Request model for updating a zone"""
    name: str | None = None
    thermostats: List[str] | None = None
    temperature_sensors: List[str] | None = None
    humidity_sensors: List[str] | None = None
    active_schedule: str | None = None
    enabled: bool | None = None


@router.get("", response_model=List[Zone])
async def get_zones(zone_manager: ZoneManagerDep):
    """Get all zones"""
    return zone_manager.get_all_zones()


@router.get("/{zone_id}")
async def get_zone(zone_id: str, zone_manager: ZoneManagerDep, ha_client: HAClient):
    """Get a specific zone with current device data"""
    
    zone = zone_manager.get_zone(zone_id)
    if not zone:
        raise HTTPException(status_code=404, detail=f"Zone {zone_id} not found")
    
    # Get current state
    state = ha_client.get_state()
    
    # Get detailed zone status with sensor data
    zone_status = zone_manager.get_zone_status(
        zone_id,
        state.thermostats,
        state.temperature_sensors,
        state.humidity_sensors
    )
    
    return zone_status


@router.post("", response_model=Zone, status_code=201)
async def create_zone(zone_data: ZoneCreate, zone_manager: ZoneManagerDep):
    """Create a new zone"""
    
    try:
        zone = Zone(**zone_data.model_dump())
        created_zone = zone_manager.create_zone(zone)
        return created_zone
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating zone: {str(e)}")


@router.put("/{zone_id}", response_model=Zone)
async def update_zone(zone_id: str, zone_data: ZoneUpdate, zone_manager: ZoneManagerDep):
    """Update an existing zone"""
    
    try:
        # Only include non-None fields
        update_dict = {k: v for k, v in zone_data.model_dump().items() if v is not None}
        
        if not update_dict:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        updated_zone = zone_manager.update_zone(zone_id, update_dict)
        return updated_zone
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating zone: {str(e)}")


@router.delete("/{zone_id}")
async def delete_zone(zone_id: str, zone_manager: ZoneManagerDep):
    """Delete a zone"""
    
    success = zone_manager.delete_zone(zone_id)
    
    if success:
        return {"success": True, "message": f"Zone {zone_id} deleted"}
    else:
        raise HTTPException(status_code=404, detail=f"Zone {zone_id} not found")


@router.post("/{zone_id}/schedule")
async def assign_schedule_to_zone(zone_id: str, schedule_id: str, zone_manager: ZoneManagerDep):
    """Assign a schedule to a zone (does not apply it to thermostats)"""
    
    success = zone_manager.assign_schedule_to_zone(zone_id, schedule_id)
    
    if success:
        return {
            "success": True,
            "zone_id": zone_id,
            "schedule_id": schedule_id,
            "message": f"Assigned schedule {schedule_id} to zone {zone_id}"
        }
    else:
        raise HTTPException(status_code=404, detail=f"Zone {zone_id} not found")
