"""Models for Heating Controller."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ModeConfiguration:
    """Represents a single mode configuration within a pseudo mode."""

    parent_mode: str  # e.g., "default", "stay_home", "eco"
    area_ids: list[str]  # e.g., ["bedroom", "kitchen"]; empty means all areas


@dataclass
class PseudoMode:
    """Represents a pseudo mode (area-specific or custom variation).

    Supports two formats:
    1. Simple: Single parent_mode + area_ids
    2. Advanced: Multiple configurations with different modes per area
    """

    name: str
    configurations: list[ModeConfiguration]


@dataclass
class WeeklySchedule:
    """Represents a complete weekly schedule for a thermostat."""

    weekly_schedule: dict[str, str]  # day_name -> temperature_schedule

    def to_dict(self) -> dict[str, Any]:
        """Convert to MQTT payload format.

        Converts the weekly schedule to flattened format where each day's schedule
        is sent as a separate MQTT key. This format is required by thermostat firmware
        versions that support per-day schedule configuration.

        Returns:
            Dictionary with keys like "weekly_schedule_monday", "weekly_schedule_tuesday", etc.
            Example: {"weekly_schedule_monday": "00:00/18.5 06:30/20 ...", ...}
        """
        return {
            f"weekly_schedule_{str(day).lower()}": schedule
            for day, schedule in self.weekly_schedule.items()
        }
