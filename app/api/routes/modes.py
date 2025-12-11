"""
Modes API routes
Manage system-wide heating modes
"""

from fastapi import APIRouter, HTTPException, Body
from typing import Optional
from pydantic import BaseModel
from datetime import datetime

from app.models.state import SystemMode
from app.dependencies import ModeManagerDep, AreaManagerDep

router = APIRouter(prefix="/api/modes", tags=["modes"])


class SetModeRequest(BaseModel):
    """Request model for setting system mode"""

    mode: str
    active_areas: Optional[list[str]] = None  # For stay_home mode
    restore_time: Optional[datetime] = None  # For timer mode


class StayHomeRequest(BaseModel):
    """Request model for stay-home mode"""

    active_areas: Optional[list[str]] = (
        None  # Areas to heat (swap to weekend), others stay on default
    )


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
                "id": "timer",
                "name": "Timer",
                "description": "Turn off now, automatically restore to default at specified time",
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
    - **timer**: Turn off all thermostats, restore to default at restore_time
    - **manual**: No supervision
    - **off**: All thermostats turned off
    """

    # Validate mode
    try:
        mode = SystemMode(request.mode)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mode: {request.mode}. Must be one of: default, stay_home, holiday, timer, manual, off",
        )

    # Validate timer mode requirements
    if mode == SystemMode.TIMER and not request.restore_time:
        raise HTTPException(status_code=400, detail="Timer mode requires restore_time")

    # Apply the mode
    try:
        kwargs = {}
        if mode == SystemMode.STAY_HOME:
            kwargs["active_areas"] = request.active_areas
        if mode == SystemMode.TIMER:
            kwargs["restore_time"] = request.restore_time

        success = await mode_manager.set_mode(mode, **kwargs)

        if success:
            return {
                "success": True,
                "mode": mode.value,
                "message": f"System mode set to {mode.value}",
                "details": mode_manager.get_mode_info(),
            }
        else:
            raise HTTPException(
                status_code=500, detail=f"Failed to apply mode {mode.value}"
            )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error setting mode: {str(e)}")


@router.post("/default")
async def set_default_mode(mode_manager: ModeManagerDep):
    """Set system to default mode - normal work week schedule"""

    success = await mode_manager.set_mode(SystemMode.DEFAULT)

    if success:
        return {
            "success": True,
            "mode": "default",
            "message": "System set to default mode - normal work week schedule",
        }
    else:
        raise HTTPException(status_code=500, detail="Failed to set default mode")


@router.post("/stay-home")
async def set_stay_home_mode(
    request: Optional[StayHomeRequest] = Body(None),
    mode_manager: ModeManagerDep = None,
):
    """Set system to stay-home mode - swap current day to weekend pattern

    Args:
        request: Optional request body with:
            - active_areas: Optional list of area IDs to heat. If None, all areas are active.
    
    Examples:
        - Empty body `{}`: Apply stay-home to all areas
        - `{"active_areas": ["kitchen", "bedroom"]}`: Apply only to specific areas
    """

    # Extract active areas from request, default to None (apply to all areas)
    active_areas = None

    if request:
        active_areas = request.active_areas

    success = await mode_manager.set_mode(
        SystemMode.STAY_HOME, active_areas=active_areas
    )

    if success:
        return {
            "success": True,
            "mode": "stay_home",
            "active_areas": active_areas or "all",
            "message": "System set to stay-home mode - current day swapped to weekend pattern",
        }
    else:
        raise HTTPException(status_code=500, detail="Failed to set stay-home mode")


@router.post("/holiday")
async def set_holiday_mode(mode_manager: ModeManagerDep):
    """Set system to holiday mode - apply eco schedule to all areas"""

    success = await mode_manager.set_mode(SystemMode.HOLIDAY)

    if success:
        return {
            "success": True,
            "mode": "holiday",
            "message": "System set to holiday mode - eco schedule applied to all areas",
        }
    else:
        raise HTTPException(status_code=500, detail="Failed to set holiday mode")


@router.post("/timer")
async def set_timer_mode(
    hours: Optional[float] = None, restore_time: Optional[datetime] = None
):
    """
    Set system to timer mode - turn off now, restore later

    Provide either:
    - **hours**: Number of hours from now to restore
    - **restore_time**: Specific datetime to restore
    """

    if not hours and not restore_time:
        raise HTTPException(
            status_code=400, detail="Must provide either 'hours' or 'restore_time'"
        )

    if hours and restore_time:
        raise HTTPException(
            status_code=400, detail="Cannot provide both 'hours' and 'restore_time'"
        )

    # Calculate restore time
    if hours:
        from datetime import timedelta

        restore_time = datetime.now() + timedelta(hours=hours)

    success = await mode_manager.set_mode(SystemMode.TIMER, restore_time=restore_time)

    if success:
        return {
            "success": True,
            "mode": "timer",
            "restore_time": restore_time.isoformat(),
            "message": f"System set to timer mode - will restore at {restore_time.strftime('%Y-%m-%d %H:%M')}",
        }
    else:
        raise HTTPException(status_code=500, detail="Failed to set timer mode")


@router.post("/timer/cancel")
async def cancel_timer(mode_manager: ModeManagerDep):
    """Cancel timer mode and restore to default immediately"""

    success = await mode_manager.cancel_timer()

    if success:
        return {"success": True, "message": "Timer cancelled, restored to default mode"}
    else:
        raise HTTPException(
            status_code=400, detail="Not in timer mode or failed to cancel"
        )


@router.post("/manual")
async def set_manual_mode(mode_manager: ModeManagerDep):
    """Set system to manual mode - no supervision"""

    success = await mode_manager.set_mode(SystemMode.MANUAL)

    if success:
        return {
            "success": True,
            "mode": "manual",
            "message": "System set to manual mode - thermostats operate independently",
        }
    else:
        raise HTTPException(status_code=500, detail="Failed to set manual mode")


@router.post("/off")
async def set_off_mode(mode_manager: ModeManagerDep):
    """Set system to off mode - turn off all thermostats"""

    success = await mode_manager.set_mode(SystemMode.OFF)

    if success:
        return {
            "success": True,
            "mode": "off",
            "message": "System set to off mode - all thermostats turned off",
        }
    else:
        raise HTTPException(status_code=500, detail="Failed to set off mode")


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
