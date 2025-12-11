"""
Modes API routes
Manage system-wide heating modes
"""

from fastapi import APIRouter, HTTPException, Body
from typing import Optional
from pydantic import BaseModel, Field
from datetime import datetime

from app.models.state import SystemMode
from app.dependencies import ModeManagerDep, AreaManagerDep

router = APIRouter(prefix="/api/modes", tags=["modes"])


class SetModeRequest(BaseModel):
    """Request model for setting system mode"""

    mode: str
    active_areas: Optional[list[str]] = None  # For stay_home mode
    ventilation_time: Optional[int] = Field(
        None, ge=1, le=60
    )  # 1-60 minutes, default 5


@router.get("")
async def get_available_modes():
    """Get list of available system modes"""
    return {
        "modes": [
            {
                "id": "default",
                "name": "Default",
                "description": "Normal work week - all areas follow default schedule",
            },
            {
                "id": "stay_home",
                "name": "Stay Home",
                "description": "Dynamic schedule - swaps current day to weekend pattern, supports active areas",
            },
            {
                "id": "holiday",
                "name": "Holiday/Away",
                "description": "Energy saving - all areas use eco schedule",
            },
            {
                "id": "ventilation",
                "name": "Ventilation",
                "description": "Turn off thermostats for house ventilation, automatically restore to previous mode",
            },
            {
                "id": "manual",
                "name": "Manual",
                "description": "No supervision - thermostats operate independently",
            },
            {"id": "off", "name": "Off", "description": "All thermostats turned off"},
        ]
    }


@router.get("/current")
async def get_current_mode(mode_manager: ModeManagerDep):
    """Get current system mode with details"""

    return mode_manager.get_mode_info()


@router.post("/set")
async def set_mode(request: SetModeRequest, mode_manager: ModeManagerDep):
    """
    Set system mode

    - **default**: Normal work week schedule
    - **stay_home**: Swap current day to weekend pattern, optional active_areas
    - **holiday**: Apply eco schedule to all areas
    - **ventilation**: Turn off thermostats for house ventilation, restore after ventilation_time (1-60 min, default 5)
    - **manual**: No supervision
    - **off**: All thermostats turned off
    """

    # Pydantic validates mode is valid SystemMode
    mode = SystemMode(request.mode)

    kwargs = {}
    if mode == SystemMode.STAY_HOME:
        kwargs["active_areas"] = request.active_areas
    if mode == SystemMode.VENTILATION:
        # Use provided ventilation_time or default to 5
        ventilation_time = request.ventilation_time or 5
        kwargs["ventilation_time"] = ventilation_time

    success = await mode_manager.set_mode(mode, **kwargs)

    if not success:
        raise HTTPException(status_code=500, detail=f"Failed to set {mode.value}")

    return {
        "success": True,
        "mode": mode.value,
        "message": f"System mode set to {mode.value}",
        "details": mode_manager.get_mode_info(),
    }


@router.get("/status")
async def get_system_status(mode_manager: ModeManagerDep, area_manager: AreaManagerDep):
    """Get complete system status including all areas"""

    areas_data = []
    for area in area_manager.get_all_areas():
        areas_data.append(
            {
                "area_id": area.area_id,
                "name": area.name,
                "enabled": area.enabled,
                "active_schedule": area.active_schedule,
                "thermostat_count": len(area.thermostats),
                "temperature_sensors": len(area.temperature_sensors),
                "humidity_sensors": len(area.humidity_sensors),
            }
        )

    return {
        "mode": mode_manager.get_mode_info(),
        "areas": areas_data,
        "total_areas": len(areas_data),
    }
