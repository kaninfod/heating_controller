"""
Area API routes
Manage Home Assistant areas for heating control
"""

from fastapi import APIRouter, HTTPException
from typing import List, Optional
from pydantic import BaseModel

from app.models.state import HAArea
from app.dependencies import HAClient, AreaManagerDep

router = APIRouter(prefix="/api/areas", tags=["areas"])


class AreaUpdate(BaseModel):
    """Request model for updating an area"""

    active_schedule: Optional[str] = None
    enabled: Optional[bool] = None


@router.get("", response_model=List[HAArea])
async def get_areas(area_manager: AreaManagerDep):
    """Get all discovered areas with thermostats"""
    return area_manager.get_all_areas()


@router.get("/{area_id}")
async def get_area(area_id: str, area_manager: AreaManagerDep, ha_client: HAClient):
    """Get a specific area with current device data"""

    area = area_manager.get_area(area_id)
    if not area:
        raise HTTPException(status_code=404, detail=f"Area '{area_id}' not found")

    # Get current state from HA client
    system_state = ha_client.get_state()

    # Get detailed status with current device values
    status = area_manager.get_area_status(
        area_id,
        system_state.thermostats,
        system_state.temperature_sensors,
        system_state.humidity_sensors,
    )

    if not status:
        raise HTTPException(status_code=404, detail=f"Area '{area_id}' not found")

    return status


@router.put("/{area_id}")
async def update_area(area_id: str, update: AreaUpdate, area_manager: AreaManagerDep):
    """Update area settings (schedule, enabled status)"""

    area = area_manager.get_area(area_id)
    if not area:
        raise HTTPException(status_code=404, detail=f"Area '{area_id}' not found")

    # Update schedule if provided
    if update.active_schedule is not None:
        if not area_manager.assign_schedule_to_area(area_id, update.active_schedule):
            raise HTTPException(
                status_code=400, detail="Failed to assign schedule to area"
            )

    # Update enabled status if provided
    if update.enabled is not None:
        if not area_manager.set_area_enabled(area_id, update.enabled):
            raise HTTPException(
                status_code=400, detail="Failed to update area enabled status"
            )

    return {"message": f"Area '{area_id}' updated successfully"}
