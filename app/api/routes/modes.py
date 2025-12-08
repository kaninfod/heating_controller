"""
Modes API routes
Manage system-wide heating modes
"""
from fastapi import APIRouter, HTTPException
from typing import Optional
from pydantic import BaseModel
from datetime import datetime

from app.models.state import SystemMode
from app.dependencies import ModeManagerDep

router = APIRouter(prefix="/api/modes", tags=["modes"])


class SetModeRequest(BaseModel):
    """Request model for setting system mode"""
    mode: str
    active_zones: Optional[list[str]] = None  # For stay_home mode
    restore_time: Optional[datetime] = None  # For timer mode


@router.get("")
async def get_available_modes():
    """Get list of available system modes"""
    return {
        "modes": [
            {
                "id": "default",
                "name": "Default",
                "description": "Normal work week - zones follow default schedule"
            },
            {
                "id": "stay_home",
                "name": "Stay Home",
                "description": "Dynamic schedule - swaps current day to weekend pattern, supports active zones"
            },
            {
                "id": "holiday",
                "name": "Holiday/Away",
                "description": "Energy saving - all zones use eco schedule"
            },
            {
                "id": "timer",
                "name": "Timer",
                "description": "Turn off now, automatically restore to default at specified time"
            },
            {
                "id": "manual",
                "name": "Manual",
                "description": "No supervision - thermostats operate independently"
            },
            {
                "id": "off",
                "name": "Off",
                "description": "All thermostats turned off"
            }
        ]
    }


@router.get("/current")
async def get_current_mode(mode_manager: ModeManagerDep):
    """Get current system mode with details"""
    
    return mode_manager.get_mode_info()


@router.post("/set")
async def set_mode(request: SetModeRequest):
    """
    Set system mode
    
    - **default**: Normal work week schedule
    - **stay_home**: Swap current day to weekend pattern, optional active_zones
    - **holiday**: Apply eco schedule to all zones
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
            detail=f"Invalid mode: {request.mode}. Must be one of: default, stay_home, holiday, timer, manual, off"
        )
    
    # Validate timer mode requirements
    if mode == SystemMode.TIMER and not request.restore_time:
        raise HTTPException(
            status_code=400,
            detail="Timer mode requires restore_time"
        )
    
    # Apply the mode
    try:
        kwargs = {}
        if mode == SystemMode.STAY_HOME:
            kwargs['active_zones'] = request.active_zones
        if mode == SystemMode.TIMER:
            kwargs['restore_time'] = request.restore_time
        
        success = await mode_manager.set_mode(mode, **kwargs)
        
        if success:
            return {
                "success": True,
                "mode": mode.value,
                "message": f"System mode set to {mode.value}",
                "details": mode_manager.get_mode_info()
            }
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to apply mode {mode.value}"
            )
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error setting mode: {str(e)}"
        )


@router.post("/default")
async def set_default_mode(mode_manager: ModeManagerDep):
    """Set system to default mode - normal work week schedule"""
    
    success = await mode_manager.set_mode(SystemMode.DEFAULT)
    
    if success:
        return {
            "success": True,
            "mode": "default",
            "message": "System set to default mode - normal work week schedule"
        }
    else:
        raise HTTPException(status_code=500, detail="Failed to set default mode")


@router.post("/stay-home")
async def set_stay_home_mode(active_zones: Optional[list[str]] = None):
    """Set system to stay-home mode - swap current day to weekend pattern
    
    Args:
        active_zones: Optional list of zone IDs to heat. If None, all zones are active.
    """
    
    success = await mode_manager.set_mode(SystemMode.STAY_HOME, active_zones=active_zones)
    
    if success:
        return {
            "success": True,
            "mode": "stay_home",
            "active_zones": active_zones or "all",
            "message": "System set to stay-home mode - current day swapped to weekend pattern"
        }
    else:
        raise HTTPException(status_code=500, detail="Failed to set stay-home mode")


@router.post("/holiday")
async def set_holiday_mode(mode_manager: ModeManagerDep):
    """Set system to holiday mode - apply eco schedule to all zones"""
    
    success = await mode_manager.set_mode(SystemMode.HOLIDAY)
    
    if success:
        return {
            "success": True,
            "mode": "holiday",
            "message": "System set to holiday mode - eco schedule applied to all zones"
        }
    else:
        raise HTTPException(status_code=500, detail="Failed to set holiday mode")


@router.post("/timer")
async def set_timer_mode(hours: Optional[float] = None, restore_time: Optional[datetime] = None):
    """
    Set system to timer mode - turn off now, restore later
    
    Provide either:
    - **hours**: Number of hours from now to restore
    - **restore_time**: Specific datetime to restore
    """
    
    if not hours and not restore_time:
        raise HTTPException(
            status_code=400,
            detail="Must provide either 'hours' or 'restore_time'"
        )
    
    if hours and restore_time:
        raise HTTPException(
            status_code=400,
            detail="Cannot provide both 'hours' and 'restore_time'"
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
            "message": f"System set to timer mode - will restore at {restore_time.strftime('%Y-%m-%d %H:%M')}"
        }
    else:
        raise HTTPException(status_code=500, detail="Failed to set timer mode")


@router.post("/timer/cancel")
async def cancel_timer(mode_manager: ModeManagerDep):
    """Cancel timer mode and restore to default immediately"""
    
    success = await mode_manager.cancel_timer()
    
    if success:
        return {
            "success": True,
            "message": "Timer cancelled, restored to default mode"
        }
    else:
        raise HTTPException(status_code=400, detail="Not in timer mode or failed to cancel")


@router.post("/manual")
async def set_manual_mode(mode_manager: ModeManagerDep):
    """Set system to manual mode - no supervision"""
    
    success = await mode_manager.set_mode(SystemMode.MANUAL)
    
    if success:
        return {
            "success": True,
            "mode": "manual",
            "message": "System set to manual mode - thermostats operate independently"
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
            "message": "System set to off mode - all thermostats turned off"
        }
    else:
        raise HTTPException(status_code=500, detail="Failed to set off mode")


@router.get("/status")
async def get_system_status():
    """Get complete system status including all zones"""
    
    return await mode_manager.get_all_zones_status()
