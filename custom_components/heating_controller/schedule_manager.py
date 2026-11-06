"""Schedule manager for Heating Controller."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.util import dt as dt_util

from .models import WeeklySchedule
from .validation import weekday_name

_LOGGER = logging.getLogger(__name__)


class ScheduleManager:
    """Manages schedule calculations and transformations."""

    def __init__(
        self,
        areas: list[dict[str, Any]],
        day_types: dict[str, str],
        schedules: dict[str, dict[str, str]],
    ) -> None:
        """Initialize schedule manager.

        Args:
            areas: List of area config dicts, each with thermostats list
            day_types: Dict mapping day_type_name -> temperature_schedule
            schedules: Dict mapping mode_name -> {day_name -> day_type_name}
        """
        self.areas = {area["id"]: area for area in areas}
        self.day_types = day_types
        self.schedules = schedules

    def get_weekly_schedule(
        self, mode: str, override_today_with: str | None = None
    ) -> WeeklySchedule:
        """Get weekly schedule for a mode.

        Args:
            mode: The heating mode (e.g., "default", "eco")
            override_today_with: Optional day_type to use for today instead of normal

        Returns:
            WeeklySchedule with the complete weekly schedule

        Raises:
            ValueError: If mode or day_type not found
        """
        if mode not in self.schedules:
            raise ValueError(f"Mode '{mode}' not found in schedules")

        schedule_template = self.schedules[mode]
        today = weekday_name(dt_util.now())

        weekly = {}

        for day_name, day_type_name in schedule_template.items():
            day_key = day_name.lower()

            # If today and override_today_with is provided, use the override
            if day_key == today and override_today_with:
                resolved_day_type = override_today_with
                _LOGGER.debug(
                    "Using override for %s: %s (instead of %s)",
                    day_name,
                    override_today_with,
                    day_type_name,
                )
            else:
                resolved_day_type = day_type_name

            if resolved_day_type not in self.day_types:
                raise ValueError(
                    f"Day type '{resolved_day_type}' not found in day_types"
                )

            weekly[day_key] = self.day_types[resolved_day_type]

        return WeeklySchedule(weekly_schedule=weekly)

    def get_active_mqtt_devices(
        self, active_area_ids: list[str] | None = None
    ) -> list[str]:
        """Get list of MQTT device names for active areas.

        Args:
            active_area_ids: Optional list of area IDs. If None, all thermostats active.

        Returns:
            List of MQTT device names to publish to (flattened from all thermostats in areas)
        """
        mqtt_devices = []

        if active_area_ids is None:
            # All areas active - flatten all thermostats
            for area in self.areas.values():
                for thermostat in area.get("thermostats", []):
                    mqtt_devices.append(thermostat["mqtt_name"])
        else:
            # Filter by area IDs - flatten thermostats from selected areas
            for area_id in active_area_ids:
                if area_id in self.areas:
                    for thermostat in self.areas[area_id].get("thermostats", []):
                        mqtt_devices.append(thermostat["mqtt_name"])

        return mqtt_devices
