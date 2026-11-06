"""Tests for heating_controller models."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_MODELS_PATH = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "heating_controller"
    / "models.py"
)
_spec = importlib.util.spec_from_file_location("heating_controller_models", _MODELS_PATH)
_models = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _models
_spec.loader.exec_module(_models)
WeeklySchedule = _models.WeeklySchedule


class TestWeeklySchedule:
    """Test cases for WeeklySchedule model."""

    def test_to_dict_flattened_format(self) -> None:
        """Test that to_dict() returns flattened format with per-day keys."""
        # Arrange: Create a weekly schedule with typical format
        schedule_data = {
            "monday": "00:00/18.5 06:30/20 09:00/18.5 17:00/20 22:00/20 23:00/18",
            "tuesday": "00:00/18.5 06:30/20 09:00/18.5 17:00/20 22:00/20 23:00/18",
            "wednesday": "00:00/18.5 06:30/20 09:00/18.5 17:00/20 22:00/20 23:00/18",
            "thursday": "00:00/18.5 06:30/20 09:00/18.5 17:00/20 22:00/20 23:00/18",
            "friday": "00:00/18.5 06:30/20 09:00/18.5 17:00/20 22:00/20 23:00/18",
            "saturday": "00:00/18.5 06:30/20 09:00/20 17:00/20 22:00/20 23:00/18",
            "sunday": "00:00/18.5 06:30/20 09:00/20 17:00/20 22:00/20 23:00/18",
        }
        weekly_schedule = WeeklySchedule(weekly_schedule=schedule_data)

        # Act: Convert to dict
        result = weekly_schedule.to_dict()

        # Assert: Check format is flattened with per-day keys
        assert "weekly_schedule_monday" in result
        assert "weekly_schedule_tuesday" in result
        assert "weekly_schedule_wednesday" in result
        assert "weekly_schedule_thursday" in result
        assert "weekly_schedule_friday" in result
        assert "weekly_schedule_saturday" in result
        assert "weekly_schedule_sunday" in result

        # Assert: Check values are correct
        assert (
            result["weekly_schedule_monday"]
            == "00:00/18.5 06:30/20 09:00/18.5 17:00/20 22:00/20 23:00/18"
        )
        assert (
            result["weekly_schedule_saturday"]
            == "00:00/18.5 06:30/20 09:00/20 17:00/20 22:00/20 23:00/18"
        )

        # Assert: Ensure old nested format is NOT present
        assert "weekly_schedule" not in result

    def test_to_dict_all_days_present(self) -> None:
        """Test that all 7 days are represented in flattened output."""
        schedule_data = {
            day: f"00:00/18 06:00/20 22:00/18"
            for day in [
                "monday",
                "tuesday",
                "wednesday",
                "thursday",
                "friday",
                "saturday",
                "sunday",
            ]
        }
        weekly_schedule = WeeklySchedule(weekly_schedule=schedule_data)

        # Act
        result = weekly_schedule.to_dict()

        # Assert: Exactly 7 keys (one per day)
        assert len(result) == 7
        expected_keys = {
            "weekly_schedule_monday",
            "weekly_schedule_tuesday",
            "weekly_schedule_wednesday",
            "weekly_schedule_thursday",
            "weekly_schedule_friday",
            "weekly_schedule_saturday",
            "weekly_schedule_sunday",
        }
        assert set(result.keys()) == expected_keys

    def test_to_dict_preserves_schedule_strings(self) -> None:
        """Test that schedule string values are preserved exactly."""
        schedule_data = {
            "monday": "00:00/17.5 06:30/21.5 09:00/18.5 17:00/21.5 22:00/21.5 23:00/17",
            "friday": "00:00/18 12:00/22 18:00/20",
        }
        weekly_schedule = WeeklySchedule(weekly_schedule=schedule_data)

        # Act
        result = weekly_schedule.to_dict()

        # Assert: Values are preserved exactly as provided
        assert (
            result["weekly_schedule_monday"]
            == "00:00/17.5 06:30/21.5 09:00/18.5 17:00/21.5 22:00/21.5 23:00/17"
        )
        assert result["weekly_schedule_friday"] == "00:00/18 12:00/22 18:00/20"

    def test_to_dict_empty_schedule(self) -> None:
        """Test that empty schedule dict returns empty result."""
        schedule_data: dict[str, str] = {}
        weekly_schedule = WeeklySchedule(weekly_schedule=schedule_data)

        # Act
        result = weekly_schedule.to_dict()

        # Assert
        assert result == {}

    def test_to_dict_single_day(self) -> None:
        """Test that single day schedules work correctly."""
        schedule_data = {
            "monday": "00:00/18.5 06:30/20",
        }
        weekly_schedule = WeeklySchedule(weekly_schedule=schedule_data)

        # Act
        result = weekly_schedule.to_dict()

        # Assert
        assert len(result) == 1
        assert "weekly_schedule_monday" in result
        assert result["weekly_schedule_monday"] == "00:00/18.5 06:30/20"

    def test_to_dict_case_sensitivity(self) -> None:
        """Test that day names maintain their case in the flattened keys."""
        schedule_data = {
            "Monday": "00:00/18.5",  # Note: capital M
            "friday": "06:30/20",  # Note: lowercase f
        }
        weekly_schedule = WeeklySchedule(weekly_schedule=schedule_data)

        # Act
        result = weekly_schedule.to_dict()

        # Assert: Keys preserve the original case (format is weekly_schedule_{original_day_name})
        assert "weekly_schedule_Monday" in result
        assert "weekly_schedule_friday" in result
        assert result["weekly_schedule_Monday"] == "00:00/18.5"
        assert result["weekly_schedule_friday"] == "06:30/20"


class TestWeeklyScheduleIntegration:
    """Integration tests for WeeklySchedule with typical thermostat usage."""

    def test_mqtt_payload_structure(self) -> None:
        """Test that the payload structure is compatible with MQTT publishing.

        This verifies that when to_dict() result is merged into an MQTT payload,
        it produces the expected flattened structure.
        """
        # Arrange: Create a realistic schedule
        schedule_data = {
            "monday": "00:00/18.5 06:30/20 09:00/18.5 17:00/20 22:00/20 23:00/18",
            "tuesday": "00:00/18.5 06:30/20 09:00/18.5 17:00/20 22:00/20 23:00/18",
            "wednesday": "00:00/18.5 06:30/20 09:00/18.5 17:00/20 22:00/20 23:00/18",
            "thursday": "00:00/18.5 06:30/20 09:00/18.5 17:00/20 22:00/20 23:00/18",
            "friday": "00:00/18.5 06:30/20 09:00/18.5 17:00/20 22:00/20 23:00/18",
            "saturday": "00:00/18.5 06:30/20 09:00/20 17:00/20 22:00/20 23:00/18",
            "sunday": "00:00/18.5 06:30/20 09:00/20 17:00/20 22:00/20 23:00/18",
        }
        weekly_schedule = WeeklySchedule(weekly_schedule=schedule_data)

        # Act: Simulate MQTT payload construction
        mqtt_payload = {
            "system_mode": "heat",
            "valve_opening_degree": 50,
        }
        mqtt_payload.update(weekly_schedule.to_dict())

        # Assert: Payload has correct structure
        assert mqtt_payload["system_mode"] == "heat"
        assert mqtt_payload["valve_opening_degree"] == 50

        # Assert: All weekly schedule keys are present at top level
        assert "weekly_schedule_monday" in mqtt_payload
        assert "weekly_schedule_sunday" in mqtt_payload

        # Assert: No nested "weekly_schedule" object
        assert "weekly_schedule" not in mqtt_payload or isinstance(
            mqtt_payload.get("weekly_schedule"), str
        )

        # Assert: Total payload keys (2 system keys + 7 schedule keys)
        assert (
            len([k for k in mqtt_payload.keys() if k.startswith("weekly_schedule_")])
            == 7
        )
