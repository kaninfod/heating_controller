"""
Area Manager Service
Manages Home Assistant areas and their associated heating devices
"""

import logging
from typing import Dict, List, Optional
from collections import defaultdict

from app.models.state import HAArea, ThermostatState, SensorState
from app.services.ha_websocket import HomeAssistantWebSocket

logger = logging.getLogger(__name__)


class AreaManager:
    """
    Manages Home Assistant areas for heating control
    - Fetches areas from Home Assistant
    - Maps thermostats and sensors to areas
    - Discovers devices by entity type (domain and device_class)
    - Provides aggregated area status
    """

    def __init__(self, ha_client: HomeAssistantWebSocket):
        self.ha_client = ha_client
        self.areas: Dict[str, HAArea] = {}
        self.discovered: bool = False

    async def discover_areas(self) -> Dict[str, HAArea]:
        """
        Discover all areas and their associated thermostats and sensors

        Returns:
            Dict mapping area_id to HAArea objects (only areas with thermostats)
        """
        try:
            # Fetch all registries
            areas_data = await self.ha_client.fetch_areas()
            entities_data = await self.ha_client.fetch_entities()
            devices_data = await self.ha_client.fetch_devices()
            sensor_states = await self.ha_client.fetch_sensor_entities()

            if not areas_data or not entities_data or not devices_data:
                logger.error(
                    "Failed to fetch areas, entities, or devices from Home Assistant"
                )
                return {}

            # Build area_id to area_data mapping
            areas_map = {area["area_id"]: area for area in areas_data}

            # Build device_id to area_id mapping
            device_to_area = {}
            for device in devices_data:
                device_id = device.get("id")
                area_id = device.get("area_id")
                if area_id and device_id:
                    device_to_area[device_id] = area_id

            logger.debug(
                f"Built device->area mapping: {len(device_to_area)} devices with areas"
            )

            # Build entity_id to device_id mapping from entity registry
            # This helps us find the device (and thus area) for sensor entities
            entity_to_device = {}
            for entity in entities_data:
                entity_id = entity.get("entity_id")
                device_id = entity.get("device_id")
                if entity_id and device_id:
                    entity_to_device[entity_id] = device_id

            logger.debug(
                f"Built entity->device mapping: {len(entity_to_device)} entities with devices"
            )

            # Group thermostats by area and type
            # Entities inherit their area from their device
            area_entities = self._group_entities_by_area_and_type(
                entities_data, device_to_area
            )

            # Add sensor entities to areas
            # Sensors come from fetch_sensor_entities() which returns state objects with device_class
            self._add_sensors_to_areas(
                area_entities, sensor_states, entity_to_device, device_to_area
            )

            # Create HAArea objects, filtering to only areas with thermostats
            self.areas = {}
            for area_id, entities_by_type in area_entities.items():
                if not entities_by_type["thermostats"]:
                    # Skip areas with no thermostats
                    logger.debug(f"Skipping area '{area_id}': no thermostats")
                    continue

                area_data = areas_map.get(area_id, {})
                ha_area = HAArea(
                    area_id=area_id,
                    name=area_data.get("name", area_id),
                    icon=area_data.get("icon"),
                    thermostats=entities_by_type["thermostats"],
                    temperature_sensors=entities_by_type["temperature_sensors"],
                    humidity_sensors=entities_by_type["humidity_sensors"],
                    active_schedule=None,
                    enabled=True,
                )
                self.areas[area_id] = ha_area
                logger.info(
                    f"Discovered area '{ha_area.name}': "
                    f"{len(ha_area.thermostats)} thermostat(s), "
                    f"{len(ha_area.temperature_sensors)} temp sensor(s), "
                    f"{len(ha_area.humidity_sensors)} humidity sensor(s)"
                )

            self.discovered = True
            logger.info(
                f"Successfully discovered {len(self.areas)} areas with heating devices"
            )
            return self.areas

        except Exception as e:
            logger.error(f"Error discovering areas: {e}")
            return {}

    def _group_entities_by_area_and_type(
        self, entities: List[Dict], device_to_area: Dict[str, str]
    ) -> Dict[str, Dict[str, List[str]]]:
        """
        Group entities by area and type (thermostat, temp sensor, humidity sensor)

        Entities inherit their area from their device via the device_id field.
        This method maps entities to areas through device cross-reference.

        Uses entity_id prefix for domain detection (not registry domain field which is often None):
        - Thermostats: entity_id starts with 'climate.'
        - Temperature sensors: entity_id starts with 'sensor.' (device_class checked separately)
        - Humidity sensors: entity_id starts with 'sensor.' (device_class checked separately)

        Args:
            entities: List of entity objects from HA entity registry
            device_to_area: Dict mapping device_id to area_id

        Returns:
            Dict mapping area_id to entity types:
            {
                "bedroom": {
                    "thermostats": ["climate.bedroom"],
                    "temperature_sensors": ["sensor.bedroom_temp"],
                    "humidity_sensors": ["sensor.bedroom_humidity"]
                },
                ...
            }
        """
        area_entities = defaultdict(
            lambda: {
                "thermostats": [],
                "temperature_sensors": [],
                "humidity_sensors": [],
            }
        )

        for entity in entities:
            # Skip disabled entities
            if entity.get("disabled_by"):
                continue

            # Get area from device (entities inherit area from their device)
            device_id = entity.get("device_id")
            if not device_id or device_id not in device_to_area:
                continue

            area_id = device_to_area[device_id]
            entity_id = entity.get("entity_id")
            if not entity_id:
                continue

            # Extract domain from entity_id prefix (registry domain field is often None)
            if entity_id.startswith("climate."):
                # Thermostat
                area_entities[area_id]["thermostats"].append(entity_id)
                logger.debug(f"Found thermostat in area '{area_id}': {entity_id}")

            elif entity_id.startswith("sensor."):
                # Sensor - device_class will be checked when adding from states
                # For now, skip - will be added via _add_sensors_to_areas()
                pass

        return dict(area_entities)

    def _add_sensors_to_areas(
        self,
        area_entities: Dict,
        sensor_states: List[Dict],
        entity_to_device: Dict[str, str],
        device_to_area: Dict[str, str],
    ) -> None:
        """
        Add sensor entities to their respective areas

        Sensor entities are mapped to areas via device cross-reference:
        entity_id -> device_id (from entity registry) -> area_id (from device registry)

        Args:
            area_entities: Dict to update with sensor entities
            sensor_states: List of sensor state objects from fetch_sensor_entities()
                          Each has entity_id, state, attributes (with device_class)
            entity_to_device: Dict mapping entity_id to device_id
            device_to_area: Dict mapping device_id to area_id
        """
        for sensor in sensor_states:
            entity_id = sensor.get("entity_id")
            attributes = sensor.get("attributes", {})
            device_class = attributes.get("device_class")

            if not entity_id:
                continue

            # Find the device for this entity
            device_id = entity_to_device.get(entity_id)
            if not device_id:
                logger.debug(f"Sensor {entity_id} has no device assignment, skipping")
                continue

            # Find the area for this device
            area_id = device_to_area.get(device_id)
            if not area_id:
                logger.debug(
                    f"Sensor {entity_id} device {device_id} has no area, skipping"
                )
                continue

            # Add to appropriate sensor list based on device_class
            if device_class == "temperature":
                if area_id not in area_entities:
                    area_entities[area_id] = {
                        "thermostats": [],
                        "temperature_sensors": [],
                        "humidity_sensors": [],
                    }
                area_entities[area_id]["temperature_sensors"].append(entity_id)
                logger.debug(
                    f"Added temperature sensor to area '{area_id}': {entity_id}"
                )

            elif device_class == "humidity":
                if area_id not in area_entities:
                    area_entities[area_id] = {
                        "thermostats": [],
                        "temperature_sensors": [],
                        "humidity_sensors": [],
                    }
                area_entities[area_id]["humidity_sensors"].append(entity_id)
                logger.debug(f"Added humidity sensor to area '{area_id}': {entity_id}")

        return dict(area_entities)

    def get_all_areas(self) -> List[HAArea]:
        """Get all discovered areas with thermostats"""
        if not self.discovered:
            logger.warning("Areas not yet discovered. Call discover_areas() first.")
        return list(self.areas.values())

    def get_area(self, area_id: str) -> Optional[HAArea]:
        """Get a specific area by ID"""
        return self.areas.get(area_id)

    def get_all_thermostat_areas(self) -> Dict[str, HAArea]:
        """Get all areas that have thermostats (all discovered areas)"""
        return dict(self.areas)

    def get_area_status(
        self,
        area_id: str,
        thermostats: Dict[str, ThermostatState],
        temp_sensors: Dict[str, SensorState],
        humidity_sensors: Dict[str, SensorState],
    ) -> Optional[dict]:
        """
        Get detailed status for an area including aggregated sensor data

        Args:
            area_id: Area ID to get status for
            thermostats: All thermostat states (key: entity_id, value: ThermostatState)
            temp_sensors: All temperature sensor states
            humidity_sensors: All humidity sensor states

        Returns:
            Dict with area info, devices, and aggregated values, or None if area not found
        """
        area = self.areas.get(area_id)
        if not area:
            logger.warning(f"Area '{area_id}' not found")
            return None

        # Get thermostat data
        area_thermostats = []
        for t_id in area.thermostats:
            if t_id in thermostats:
                area_thermostats.append(thermostats[t_id].model_dump())

        # Get temperature sensor data
        area_temp_sensors = []
        temps = []
        for s_id in area.temperature_sensors:
            if s_id in temp_sensors:
                sensor = temp_sensors[s_id]
                area_temp_sensors.append(sensor.model_dump())
                if sensor.state is not None:
                    temps.append(sensor.state)

        # Get humidity sensor data
        area_humidity_sensors = []
        humidities = []
        for s_id in area.humidity_sensors:
            if s_id in humidity_sensors:
                sensor = humidity_sensors[s_id]
                area_humidity_sensors.append(sensor.model_dump())
                if sensor.state is not None:
                    humidities.append(sensor.state)

        # Calculate averages
        avg_temp = sum(temps) / len(temps) if temps else None
        avg_humidity = sum(humidities) / len(humidities) if humidities else None

        return {
            "area": area.model_dump(),
            "thermostats": area_thermostats,
            "temperature_sensors": area_temp_sensors,
            "humidity_sensors": area_humidity_sensors,
            "average_temperature": round(avg_temp, 1) if avg_temp else None,
            "average_humidity": round(avg_humidity, 1) if avg_humidity else None,
        }

    def assign_schedule_to_area(self, area_id: str, schedule_id: str) -> bool:
        """
        Assign a schedule to an area

        Args:
            area_id: Area to assign schedule to
            schedule_id: Schedule ID to assign

        Returns:
            True if successful, False otherwise
        """
        if area_id not in self.areas:
            logger.error(f"Area '{area_id}' not found")
            return False

        self.areas[area_id].active_schedule = schedule_id
        logger.info(f"Assigned schedule '{schedule_id}' to area '{area_id}'")
        return True

    def set_area_enabled(self, area_id: str, enabled: bool) -> bool:
        """
        Enable or disable an area for heating control

        Args:
            area_id: Area to enable/disable
            enabled: True to enable, False to disable

        Returns:
            True if successful, False otherwise
        """
        if area_id not in self.areas:
            logger.error(f"Area '{area_id}' not found")
            return False

        self.areas[area_id].enabled = enabled
        status = "enabled" if enabled else "disabled"
        logger.info(f"Area '{area_id}' {status}")
        return True
