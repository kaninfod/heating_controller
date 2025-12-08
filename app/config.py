"""
Configuration loader for the heating control system.
Loads settings from .env, zones.json, and schedule files.
"""
import os
import json
from pathlib import Path
from typing import Dict, List, Any
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from .env file"""
    
    # Home Assistant Connection
    ha_websocket_url: str = Field(alias="HA_WEBSOCKET_URL")
    ha_access_token: str = Field(alias="HA_ACCESS_TOKEN")
    
    # Entity IDs
    thermostat_entities: str = Field(alias="THERMOSTAT_ENTITIES")
    temperature_sensor_entities: str = Field(alias="TEMPERATURE_SENSOR_ENTITIES")
    humidity_sensor_entities: str = Field(alias="HUMIDITY_SENSOR_ENTITIES")
    mode_entity: str = Field(default="input_select.heating_mode", alias="MODE_ENTITY")
    
    # App Settings
    state_file_path: str = Field(default="data/state.json", alias="STATE_FILE_PATH")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    
    # Syslog Settings
    syslog_host: str = Field(default="192.168.68.102", alias="SYSLOG_HOST")
    syslog_port: int = Field(default=514, alias="SYSLOG_PORT")
    
    class Config:
        env_file = ".env"
        case_sensitive = False
        populate_by_name = True
    
    @property
    def thermostat_list(self) -> List[str]:
        """Parse comma-separated thermostat entities into list"""
        return [e.strip() for e in self.thermostat_entities.split(",") if e.strip()]
    
    @property
    def temperature_sensor_list(self) -> List[str]:
        """Parse comma-separated temperature sensor entities into list"""
        return [e.strip() for e in self.temperature_sensor_entities.split(",") if e.strip()]
    
    @property
    def humidity_sensor_list(self) -> List[str]:
        """Parse comma-separated humidity sensor entities into list"""
        return [e.strip() for e in self.humidity_sensor_entities.split(",") if e.strip()]
    
    @property
    def all_monitored_entities(self) -> List[str]:
        """Get all entities that should be monitored"""
        entities = self.thermostat_list + self.temperature_sensor_list + self.humidity_sensor_list
        # Add mode entity for persistence
        if self.mode_entity:
            entities.append(self.mode_entity)
        return entities


class ConfigLoader:
    """Loads and manages all configuration files"""
    
    def __init__(self, config_dir: str = "config"):
        self.config_dir = Path(config_dir)
        self.schedules_dir = self.config_dir / "schedules"
        self.zones_file = self.config_dir / "zones.json"
        
    def load_zones(self) -> Dict[str, Any]:
        """Load zones configuration from zones.json"""
        if not self.zones_file.exists():
            return {}
        
        with open(self.zones_file, "r") as f:
            return json.load(f)
    
    def save_zones(self, zones_data: Dict[str, Any]) -> None:
        """Save zones configuration to zones.json"""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        with open(self.zones_file, "w") as f:
            json.dump(zones_data, f, indent=2)
    
    def load_thermostat_mapping(self) -> Dict[str, Dict[str, str]]:
        """Load thermostat to Zigbee2MQTT device name mapping"""
        mapping_file = self.config_dir / "thermostat_mapping.json"
        
        if not mapping_file.exists():
            # Return empty dict if no mapping file
            return {}
        
        try:
            with open(mapping_file, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading thermostat mapping: {e}")
            return {}
    
    def load_schedules(self) -> Dict[str, Dict[str, Any]]:
        """Load all schedules from config/schedules/ directory"""
        schedules = {}
        
        if not self.schedules_dir.exists():
            return schedules
        
        for schedule_file in self.schedules_dir.glob("*.json"):
            try:
                with open(schedule_file, "r") as f:
                    schedule_data = json.load(f)
                    schedule_id = schedule_data.get("id", schedule_file.stem)
                    schedules[schedule_id] = schedule_data
            except Exception as e:
                print(f"Error loading schedule {schedule_file}: {e}")
        
        return schedules
    
    def load_schedule(self, schedule_id: str) -> Dict[str, Any] | None:
        """Load a specific schedule by ID"""
        schedule_file = self.schedules_dir / f"{schedule_id}.json"
        
        if not schedule_file.exists():
            return None
        
        with open(schedule_file, "r") as f:
            return json.load(f)
    
    def save_schedule(self, schedule_id: str, schedule_data: Dict[str, Any]) -> None:
        """Save a schedule to file"""
        self.schedules_dir.mkdir(parents=True, exist_ok=True)
        schedule_file = self.schedules_dir / f"{schedule_id}.json"
        
        with open(schedule_file, "w") as f:
            json.dump(schedule_data, f, indent=2)
    
    def delete_schedule(self, schedule_id: str) -> bool:
        """Delete a schedule file"""
        schedule_file = self.schedules_dir / f"{schedule_id}.json"
        
        if schedule_file.exists():
            schedule_file.unlink()
            return True
        return False


# Global instances
settings = Settings()
config_loader = ConfigLoader()
