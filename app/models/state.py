"""
Data models for the heating control system
"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from enum import Enum


class ThermostatMode(str, Enum):
    """Thermostat operating modes for TRVZB"""

    OFF = "off"
    HEAT = "heat"
    AUTO = "auto"


class ThermostatState(BaseModel):
    """Represents the current state of a thermostat"""

    entity_id: str
    friendly_name: Optional[str] = None
    current_temperature: Optional[float] = None
    target_temperature: Optional[float] = None
    mode: Optional[str] = None  # off, heat, auto
    preset_mode: Optional[str] = None
    battery: Optional[int] = None
    available: bool = True
    last_updated: Optional[datetime] = None
    attributes: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat() if v else None}


class SensorState(BaseModel):
    """Represents the current state of a temperature or humidity sensor"""

    entity_id: str
    friendly_name: Optional[str] = None
    state: Optional[float] = None  # The sensor value (temperature or humidity)
    unit: Optional[str] = None  # °C, °F, %
    available: bool = True
    last_updated: Optional[datetime] = None
    attributes: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat() if v else None}


class InputSelectState(BaseModel):
    """Represents the current state of an input_select entity"""

    entity_id: str
    friendly_name: Optional[str] = None
    state: Optional[str] = None  # Current selected option
    options: List[str] = Field(default_factory=list)  # Available options
    available: bool = True
    last_updated: Optional[datetime] = None
    attributes: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat() if v else None}


class Zone(BaseModel):
    """Represents a heating zone"""

    id: str
    name: str
    thermostats: List[str] = Field(default_factory=list)
    temperature_sensors: List[str] = Field(default_factory=list)
    humidity_sensors: List[str] = Field(default_factory=list)
    active_schedule: Optional[str] = None
    enabled: bool = True


class HAArea(BaseModel):
    """Represents a Home Assistant area with connected heating devices"""

    area_id: str  # Home Assistant's area ID
    name: str  # Display name from HA
    icon: Optional[str] = None  # Icon identifier (e.g., "mdi:bedroom")
    thermostats: List[str] = Field(default_factory=list)  # Climate entity IDs
    temperature_sensors: List[str] = Field(
        default_factory=list
    )  # Temperature sensor entity IDs
    humidity_sensors: List[str] = Field(
        default_factory=list
    )  # Humidity sensor entity IDs
    active_schedule: Optional[str] = None  # Currently assigned schedule
    enabled: bool = True  # Whether this area is active for control


class DayType(BaseModel):
    """Reusable day schedule template"""

    id: str
    schedule: (
        str  # TRVZB format: "HH:MM/TEMP HH:MM/TEMP ..." (6 pairs starting with 00:00)
    )
    description: Optional[str] = None


class WeekComposition(BaseModel):
    """Week schedule composed from day type references"""

    monday: str  # Reference to day type ID
    tuesday: str
    wednesday: str
    thursday: str
    friday: str
    saturday: str
    sunday: str


class Schedule(BaseModel):
    """Heating schedule definition composed from day types"""

    id: str
    name: str
    description: Optional[str] = None
    enabled: bool = True
    week: WeekComposition  # References day types instead of full schedules
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat() if v else None}


class SystemMode(str, Enum):
    """High-level system operating modes"""

    DEFAULT = "default"  # Normal schedule-based operation (renamed from AUTO)
    STAY_HOME = (
        "stay_home"  # Dynamic: swap current day to weekend, support active zones
    )
    HOLIDAY = "holiday"  # Apply eco schedule to all zones
    TIMER = "timer"  # Temporary override with auto-restore
    MANUAL = "manual"  # No automatic control
    OFF = "off"  # All thermostats turned off
    VENTILATION = (
        "ventilation"  # Temporary ventilation mode - off for X minutes then restore
    )


class ConnectionStatus(str, Enum):
    """Home Assistant connection status"""

    CONNECTED = "connected"
    CONNECTING = "connecting"
    DISCONNECTED = "disconnected"
    ERROR = "error"


class SystemState(BaseModel):
    """Overall system state"""

    system_mode: SystemMode = SystemMode.MANUAL
    connection_status: ConnectionStatus = ConnectionStatus.DISCONNECTED
    last_updated: datetime = Field(default_factory=datetime.now)
    thermostats: Dict[str, ThermostatState] = Field(default_factory=dict)
    temperature_sensors: Dict[str, SensorState] = Field(default_factory=dict)
    humidity_sensors: Dict[str, SensorState] = Field(default_factory=dict)
    input_selects: Dict[str, InputSelectState] = Field(default_factory=dict)

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat() if v else None}


class StatusResponse(BaseModel):
    """API response for /api/status endpoint"""

    system_mode: str
    connection_status: str
    last_updated: datetime
    thermostats: List[ThermostatState]
    temperature_sensors: List[SensorState]
    humidity_sensors: List[SensorState]
    zones: List[Zone]

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat() if v else None}
