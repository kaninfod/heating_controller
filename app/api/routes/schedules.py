"""
Schedule API routes
Manage heating schedules and apply them to thermostats/areas
"""

from fastapi import APIRouter, HTTPException
from typing import List, Dict
from pydantic import BaseModel

from app.models.state import Schedule, WeekComposition
from app.dependencies import HAClient, ScheduleManagerDep

router = APIRouter(prefix="/api/schedules", tags=["schedules"])


class ScheduleCreate(BaseModel):
    """Request model for creating a schedule"""

    id: str
    name: str
    description: str = ""
    enabled: bool = True
    week: WeekComposition


class ScheduleUpdate(BaseModel):
    """Request model for updating a schedule"""

    name: str | None = None
    description: str | None = None
    enabled: bool | None = None
    week: WeekComposition | None = None


class ApplyScheduleRequest(BaseModel):
    """Request model for applying a schedule"""

    thermostat_id: str


class ScheduleExpanded(Schedule):
    """Extended schedule model with expanded time/temperature data"""

    expanded_schedule: Dict[str, str]  # e.g., {"monday": "00:00/16 06:30/20 ...", ...}


@router.get("", response_model=List[ScheduleExpanded])
async def get_schedules(schedule_manager: ScheduleManagerDep):
    """Get all schedules with expanded time/temperature data"""

    schedules = schedule_manager.get_all_schedules()

    # Expand each schedule with actual time/temp data
    expanded_schedules = []
    for schedule in schedules:
        week_composition = schedule.week.model_dump()
        expanded_schedule = schedule_manager.generator.generate_week_schedule(
            week_composition
        )

        expanded_schedules.append(
            ScheduleExpanded(
                **schedule.model_dump(), expanded_schedule=expanded_schedule
            )
        )

    return expanded_schedules


@router.get("/{schedule_id}", response_model=ScheduleExpanded)
async def get_schedule(schedule_id: str, schedule_manager: ScheduleManagerDep):
    """Get a specific schedule with expanded time/temperature data"""

    schedule = schedule_manager.get_schedule(schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail=f"Schedule {schedule_id} not found")

    # Expand schedule with actual time/temp data
    week_composition = schedule.week.model_dump()
    expanded_schedule = schedule_manager.generator.generate_week_schedule(
        week_composition
    )

    return ScheduleExpanded(
        **schedule.model_dump(), expanded_schedule=expanded_schedule
    )


@router.post("", response_model=Schedule, status_code=201)
async def create_schedule(
    schedule_data: ScheduleCreate, schedule_manager: ScheduleManagerDep
):
    """Create a new schedule"""

    try:
        # Validate schedule format
        if not schedule_manager.validate_schedule_format(schedule_data.model_dump()):
            raise HTTPException(status_code=400, detail="Invalid schedule format")

        schedule = Schedule(**schedule_data.model_dump())
        created_schedule = schedule_manager.create_schedule(schedule)
        return created_schedule
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error creating schedule: {str(e)}"
        )


@router.put("/{schedule_id}", response_model=Schedule)
async def update_schedule(
    schedule_id: str,
    schedule_data: ScheduleUpdate,
    schedule_manager: ScheduleManagerDep,
):
    """Update an existing schedule"""

    try:
        # Only include non-None fields
        update_dict = {
            k: v for k, v in schedule_data.model_dump().items() if v is not None
        }

        if not update_dict:
            raise HTTPException(status_code=400, detail="No fields to update")

        # Validate if week is being updated
        if "week" in update_dict:
            test_schedule = {
                **schedule_manager.get_schedule(schedule_id).model_dump(),
                **update_dict,
            }
            if not schedule_manager.validate_schedule_format(test_schedule):
                raise HTTPException(status_code=400, detail="Invalid schedule format")

        updated_schedule = schedule_manager.update_schedule(schedule_id, update_dict)
        return updated_schedule
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error updating schedule: {str(e)}"
        )


@router.delete("/{schedule_id}")
async def delete_schedule(schedule_id: str, schedule_manager: ScheduleManagerDep):
    """Delete a schedule"""

    success = schedule_manager.delete_schedule(schedule_id)

    if success:
        return {"success": True, "message": f"Schedule {schedule_id} deleted"}
    else:
        raise HTTPException(status_code=404, detail=f"Schedule {schedule_id} not found")


@router.post("/{schedule_id}/apply")
async def apply_schedule(
    schedule_id: str,
    request: ApplyScheduleRequest,
    schedule_manager: ScheduleManagerDep,
    ha_client: HAClient,
):
    """
    Apply a schedule to a thermostat

    Note: Schedules are typically applied to areas through modes.
    This endpoint is for direct thermostat-level control.
    """

    try:
        # Apply to single thermostat
        success = await schedule_manager.apply_schedule_to_thermostat(
            ha_client, request.thermostat_id, schedule_id
        )

        if success:
            return {
                "success": True,
                "schedule_id": schedule_id,
                "thermostat_id": request.thermostat_id,
                "message": f"Applied schedule {schedule_id} to {request.thermostat_id}",
            }
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to apply schedule to {request.thermostat_id}",
            )

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error applying schedule: {str(e)}"
        )


@router.get("/{schedule_id}/validate")
async def validate_schedule(schedule_id: str, schedule_manager: ScheduleManagerDep):
    """Validate a schedule format"""

    schedule = schedule_manager.get_schedule(schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail=f"Schedule {schedule_id} not found")

    is_valid = schedule_manager.validate_schedule_format(schedule.model_dump())

    return {"schedule_id": schedule_id, "valid": is_valid}
