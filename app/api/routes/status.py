"""
Status API routes
Provides current state of all thermostats, sensors, and system
"""
from fastapi import APIRouter, HTTPException
from typing import Dict, Any

from app.models.state import StatusResponse, ThermostatState, SensorState, Zone
from app.dependencies import HAClient

router = APIRouter(prefix="/api/status", tags=["status"])


@router.get("", response_model=StatusResponse)
async def get_full_status(ha_client: HAClient) -> StatusResponse:
    """
    Get complete system status including all thermostats, sensors, and zones
    """
    state = ha_client.get_state()
    
    return StatusResponse(
        system_mode=state.system_mode.value,
        connection_status=state.connection_status.value,
        last_updated=state.last_updated,
        thermostats=list(state.thermostats.values()),
        temperature_sensors=list(state.temperature_sensors.values()),
        humidity_sensors=list(state.humidity_sensors.values()),
        zones=list(state.zones.values())
    )


@router.get("/thermostats")
async def get_thermostats(ha_client: HAClient) -> Dict[str, Any]:
    """Get status of all thermostats"""
    state = ha_client.get_state()
    
    return {
        "thermostats": [t.model_dump() for t in state.thermostats.values()],
        "count": len(state.thermostats)
    }


@router.get("/thermostats/{entity_id}")
async def get_thermostat(entity_id: str, ha_client: HAClient) -> ThermostatState:
    """Get status of a specific thermostat"""
    state = ha_client.get_state()
    
    if entity_id not in state.thermostats:
        raise HTTPException(status_code=404, detail=f"Thermostat {entity_id} not found")
    
    return state.thermostats[entity_id]


@router.get("/sensors/temperature")
async def get_temperature_sensors(ha_client: HAClient) -> Dict[str, Any]:
    """Get all temperature sensors"""
    
    state = ha_client.get_state()
    
    return {
        "sensors": [s.model_dump() for s in state.temperature_sensors.values()],
        "count": len(state.temperature_sensors)
    }


@router.get("/sensors/humidity")
async def get_humidity_sensors(ha_client: HAClient) -> Dict[str, Any]:
    """Get all humidity sensors"""
    
    state = ha_client.get_state()
    
    return {
        "sensors": [s.model_dump() for s in state.humidity_sensors.values()],
        "count": len(state.humidity_sensors)
    }


@router.get("/connection")
async def get_connection_status(ha_client: HAClient) -> Dict[str, str]:
    """Get Home Assistant connection status"""
    
    state = ha_client.get_state()
    
    return {
        "status": state.connection_status.value,
        "system_mode": state.system_mode.value
    }
