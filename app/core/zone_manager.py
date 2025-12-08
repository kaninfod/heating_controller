"""
Zone Manager Service
Manages heating zones and their thermostats
"""
import logging
from typing import Dict, List, Optional

from app.models.state import Zone, ThermostatState, SensorState
from app.config import config_loader

logger = logging.getLogger(__name__)


class ZoneManager:
    """
    Manages heating zones
    - Load zones from config/zones.json
    - Group thermostats by zone
    - Get aggregated zone status
    """
    
    def __init__(self):
        self.zones: Dict[str, Zone] = {}
        self.load_zones()
    
    def load_zones(self):
        """Load all zones from config/zones.json"""
        zones_data = config_loader.load_zones()
        
        # Handle both formats: dict or list
        if isinstance(zones_data, dict):
            # Dict format: {zone_id: {zone_data}}
            for zone_id, zone_data in zones_data.items():
                try:
                    zone = Zone(**zone_data)
                    self.zones[zone.id] = zone
                except Exception as e:
                    logger.error(f"Error loading zone {zone_id}: {e}")
        elif isinstance(zones_data, list):
            # List format: [{zone_data}, ...]
            for zone_data in zones_data:
                try:
                    zone = Zone(**zone_data)
                    self.zones[zone.id] = zone
                except Exception as e:
                    logger.error(f"Error loading zone {zone_data.get('id', 'unknown')}: {e}")
        
        logger.info(f"Loaded {len(self.zones)} zones")
    
    def get_all_zones(self) -> List[Zone]:
        """Get all zones"""
        return list(self.zones.values())
    
    def get_zone(self, zone_id: str) -> Optional[Zone]:
        """Get a specific zone by ID"""
        return self.zones.get(zone_id)
    
    def get_zone_thermostats(self, zone_id: str) -> List[str]:
        """Get list of thermostat entity IDs for a zone"""
        zone = self.zones.get(zone_id)
        return zone.thermostats if zone else []
    
    def create_zone(self, zone: Zone) -> Zone:
        """Create a new zone"""
        if zone.id in self.zones:
            raise ValueError(f"Zone {zone.id} already exists")
        
        self.zones[zone.id] = zone
        self._save_zones()
        logger.info(f"Created zone: {zone.id}")
        return zone
    
    def update_zone(self, zone_id: str, zone_data: dict) -> Zone:
        """Update an existing zone"""
        if zone_id not in self.zones:
            raise ValueError(f"Zone {zone_id} not found")
        
        # Update zone
        zone = Zone(**{**self.zones[zone_id].model_dump(), **zone_data})
        self.zones[zone_id] = zone
        
        self._save_zones()
        logger.info(f"Updated zone: {zone_id}")
        return zone
    
    def delete_zone(self, zone_id: str) -> bool:
        """Delete a zone"""
        if zone_id not in self.zones:
            return False
        
        del self.zones[zone_id]
        self._save_zones()
        logger.info(f"Deleted zone: {zone_id}")
        return True
    
    def assign_schedule_to_zone(self, zone_id: str, schedule_id: str) -> bool:
        """Assign a schedule to a zone"""
        if zone_id not in self.zones:
            logger.error(f"Zone {zone_id} not found")
            return False
        
        self.zones[zone_id].active_schedule = schedule_id
        self._save_zones()
        logger.info(f"Assigned schedule {schedule_id} to zone {zone_id}")
        return True
    
    def get_zone_status(
        self,
        zone_id: str,
        thermostats: Dict[str, ThermostatState],
        temp_sensors: Dict[str, SensorState],
        humidity_sensors: Dict[str, SensorState]
    ) -> dict:
        """
        Get detailed status for a zone including aggregated sensor data
        """
        zone = self.zones.get(zone_id)
        if not zone:
            return None
        
        # Get thermostat data
        zone_thermostats = []
        for t_id in zone.thermostats:
            if t_id in thermostats:
                zone_thermostats.append(thermostats[t_id].model_dump())
        
        # Get temperature sensor data
        zone_temp_sensors = []
        temps = []
        for s_id in zone.temperature_sensors:
            if s_id in temp_sensors:
                sensor = temp_sensors[s_id]
                zone_temp_sensors.append(sensor.model_dump())
                if sensor.state is not None:
                    temps.append(sensor.state)
        
        # Get humidity sensor data
        zone_humidity_sensors = []
        humidities = []
        for s_id in zone.humidity_sensors:
            if s_id in humidity_sensors:
                sensor = humidity_sensors[s_id]
                zone_humidity_sensors.append(sensor.model_dump())
                if sensor.state is not None:
                    humidities.append(sensor.state)
        
        # Calculate averages
        avg_temp = sum(temps) / len(temps) if temps else None
        avg_humidity = sum(humidities) / len(humidities) if humidities else None
        
        return {
            "zone": zone.model_dump(),
            "thermostats": zone_thermostats,
            "temperature_sensors": zone_temp_sensors,
            "humidity_sensors": zone_humidity_sensors,
            "average_temperature": round(avg_temp, 1) if avg_temp else None,
            "average_humidity": round(avg_humidity, 1) if avg_humidity else None
        }
    
    def _save_zones(self):
        """Save zones to config file"""
        zones_data = [zone.model_dump() for zone in self.zones.values()]
        config_loader.save_zones(zones_data)
