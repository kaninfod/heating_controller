"""
Schedule Manager Service
Manages heating schedules and applies them to thermostats
"""

import asyncio
import logging
import re
from typing import Dict, List, Optional

from app.models.state import Schedule
from app.config import config_loader
from app.services.schedule_generator import ScheduleGenerator

logger = logging.getLogger(__name__)


class ScheduleManager:
    """
    Manages heating schedules
    - Load schedules from config/schedules/
    - Apply schedules to thermostats via Home Assistant
    - CRUD operations on schedules
    - Error recovery with retry logic
    """

    def __init__(self):
        self.schedules: Dict[str, Schedule] = {}
        self.generator = ScheduleGenerator()
        self.thermostat_mapping: Dict[str, Dict[str, str]] = {}
        self.load_schedules()
        self.load_thermostat_mapping()

    def load_thermostat_mapping(self):
        """Load thermostat to Z2M device name mapping from config"""
        self.thermostat_mapping = config_loader.load_thermostat_mapping()
        logger.info(f"Loaded {len(self.thermostat_mapping)} thermostat mappings")

    def load_schedules(self):
        """Load all schedules from config/schedules/ directory"""
        schedules_data = config_loader.load_schedules()

        for schedule_id, schedule_data in schedules_data.items():
            try:
                schedule = Schedule(**schedule_data)
                self.schedules[schedule.id] = schedule
            except Exception as e:
                logger.error(f"Error loading schedule {schedule_id}: {e}")

        logger.info(f"Loaded {len(self.schedules)} schedules")

    def get_all_schedules(self) -> List[Schedule]:
        """Get all schedules"""
        return list(self.schedules.values())

    def get_schedule(self, schedule_id: str) -> Optional[Schedule]:
        """Get a specific schedule by ID"""
        return self.schedules.get(schedule_id)

    def create_schedule(self, schedule: Schedule) -> Schedule:
        """Create a new schedule"""
        if schedule.id in self.schedules:
            raise ValueError(f"Schedule {schedule.id} already exists")

        self.schedules[schedule.id] = schedule
        config_loader.save_schedule(schedule.id, schedule.model_dump())
        logger.info(f"Created schedule: {schedule.id}")
        return schedule

    def update_schedule(self, schedule_id: str, schedule_data: dict) -> Schedule:
        """Update an existing schedule"""
        if schedule_id not in self.schedules:
            raise ValueError(f"Schedule {schedule_id} not found")

        # Update schedule
        schedule = Schedule(
            **{**self.schedules[schedule_id].model_dump(), **schedule_data}
        )
        self.schedules[schedule_id] = schedule

        config_loader.save_schedule(schedule_id, schedule.model_dump())
        logger.info(f"Updated schedule: {schedule_id}")
        return schedule

    def delete_schedule(self, schedule_id: str) -> bool:
        """Delete a schedule"""
        if schedule_id not in self.schedules:
            return False

        del self.schedules[schedule_id]
        config_loader.delete_schedule(schedule_id)
        logger.info(f"Deleted schedule: {schedule_id}")
        return True

    async def apply_schedule_to_thermostat(
        self, ha_client, thermostat_id: str, schedule_id: str
    ) -> bool:
        """
        Apply a schedule to a specific thermostat

        This sends the weekly_schedule data to the thermostat via Home Assistant
        """
        schedule = self.schedules.get(schedule_id)
        if not schedule:
            logger.error(f"Schedule {schedule_id} not found")
            return False

        if not schedule.enabled:
            logger.warning(f"Schedule {schedule_id} is disabled")
            return False

        # Generate TRVZB schedules from week composition
        week_composition = schedule.week.model_dump()
        schedule_data = self.generator.generate_week_schedule(week_composition)

        try:
            # First, set the thermostat to 'auto' mode so it follows the schedule
            mode_success = await ha_client.set_thermostat_mode(thermostat_id, "auto")
            if not mode_success:
                logger.warning(
                    f"Failed to set {thermostat_id} to auto mode, continuing anyway..."
                )

            # Give the thermostat time to process the mode change
            # WebSocket calls are fire-and-forget, so we wait for state update
            await asyncio.sleep(0.5)

            # Get Z2M device name from mapping
            thermostat_config = self.thermostat_mapping.get(thermostat_id)
            if not thermostat_config:
                logger.error(f"No mapping found for thermostat: {thermostat_id}")
                return False

            z2m_device_name = thermostat_config.get("z2m_name")
            if not z2m_device_name:
                logger.error(f"No Z2M name configured for: {thermostat_id}")
                return False

            # Validate device name (prevent injection)
            if not re.match(r"^[a-z0-9\s\(\)]+$", z2m_device_name):
                logger.error(f"Invalid Z2M device name: {z2m_device_name}")
                return False

            # For Zigbee2MQTT thermostats, publish schedule via MQTT
            mqtt_topic = f"zigbee2mqtt/{z2m_device_name}/set"

            import json

            mqtt_payload_json = json.dumps({"weekly_schedule": schedule_data})

            # Retry logic with exponential backoff
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    # mqtt.publish doesn't use entity_id, only topic and payload
                    success = await ha_client.call_service(
                        domain="mqtt",
                        service="publish",
                        service_data={
                            "topic": mqtt_topic,
                            "payload": mqtt_payload_json,
                        },
                    )

                    if success:
                        logger.info(
                            f"Applied schedule {schedule_id} to {thermostat_id}",
                            extra={
                                "schedule_id": schedule_id,
                                "thermostat_id": thermostat_id,
                                "z2m_device": z2m_device_name,
                                "mode": "auto",
                                "attempt": attempt + 1,
                            },
                        )
                        return True

                    # If not successful and retries remain, wait before retry
                    if attempt < max_retries - 1:
                        wait_time = 2**attempt  # Exponential backoff: 1s, 2s, 4s
                        logger.warning(
                            f"Retry {attempt + 1}/{max_retries} for {thermostat_id} in {wait_time}s"
                        )
                        await asyncio.sleep(wait_time)

                except Exception as e:
                    logger.error(
                        f"Attempt {attempt + 1}/{max_retries} failed for {thermostat_id}: {e}",
                        extra={"thermostat_id": thermostat_id, "error": str(e)},
                    )
                    if attempt < max_retries - 1:
                        await asyncio.sleep(2**attempt)
                    else:
                        raise

            logger.error(
                f"Failed to apply schedule {schedule_id} to {thermostat_id} after {max_retries} attempts"
            )
            return False

        except Exception as e:
            logger.error(f"Error applying schedule to {thermostat_id}: {e}")
            return False

    async def apply_schedule_to_area(
        self, ha_client, area_manager, area_id: str, schedule_id: str
    ) -> Dict[str, bool]:
        """
        Apply a schedule to all thermostats in an area

        Args:
            ha_client: HomeAssistantWebSocket client
            area_manager: AreaManager instance
            area_id: Area ID to apply schedule to
            schedule_id: Schedule ID to apply

        Returns:
            Dict of {thermostat_id: success}
        """
        results = {}

        # Get area
        area = area_manager.get_area(area_id)
        if not area:
            logger.error(f"Area {area_id} not found")
            return results

        # Get thermostats in the area
        thermostat_ids = area.thermostats

        if not thermostat_ids:
            logger.warning(f"No thermostats in area {area_id}")
            return results

        # Apply schedule to each thermostat
        for thermostat_id in thermostat_ids:
            success = await self.apply_schedule_to_thermostat(
                ha_client, thermostat_id, schedule_id
            )
            results[thermostat_id] = success

        # Update area's active schedule
        if all(results.values()):
            area_manager.assign_schedule_to_area(area_id, schedule_id)
            logger.info(
                f"Applied schedule {schedule_id} to all thermostats in area {area_id}"
            )
        else:
            logger.warning(
                f"Some thermostats failed when applying schedule to area {area_id}"
            )

        return results

    def validate_schedule_format(self, schedule_data: dict) -> bool:
        """
        Validate that a schedule has the correct format (week composition)
        """
        try:
            week = schedule_data.get("week", {})
            days = [
                "monday",
                "tuesday",
                "wednesday",
                "thursday",
                "friday",
                "saturday",
                "sunday",
            ]

            # Check all days are present
            for day in days:
                if day not in week:
                    logger.error(f"Missing day: {day}")
                    return False

                # Check day type exists
                day_type_id = week[day]
                if not isinstance(day_type_id, str):
                    logger.error(f"Invalid day type for {day}: {day_type_id}")
                    return False

                # Verify day type exists in generator
                try:
                    self.generator.get_day_schedule(day_type_id)
                except ValueError as e:
                    logger.error(f"Invalid day type reference: {e}")
                    return False

            return True

        except Exception as e:
            logger.error(f"Schedule validation error: {e}")
            return False
