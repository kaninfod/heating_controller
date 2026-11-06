"""Tests for the pure validation and resolution helpers."""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

_VALIDATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "heating_controller"
    / "validation.py"
)
_spec = importlib.util.spec_from_file_location(
    "heating_controller_validation", _VALIDATION_PATH
)
_validation = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _validation
_spec.loader.exec_module(_validation)

validate_day_type_schedule = _validation.validate_day_type_schedule
resolve_effective_area_ids = _validation.resolve_effective_area_ids
weekday_name = _validation.weekday_name


class TestDayTypeSchedule:
    """Day-type format rules."""

    def test_accepts_six_transitions(self) -> None:
        schedule = "00:00/18.5 06:30/20 09:00/18.5 17:00/20 22:00/20 23:00/18"
        assert validate_day_type_schedule(schedule) == schedule

    def test_accepts_three_transitions(self) -> None:
        schedule = "00:00/16 07:00/18 22:00/16"
        assert validate_day_type_schedule(schedule) == schedule

    def test_accepts_one_transition(self) -> None:
        schedule = "00:00/18"
        assert validate_day_type_schedule(schedule) == schedule

    def test_rejects_empty(self) -> None:
        with pytest.raises(ValueError, match="between 1 and 6"):
            validate_day_type_schedule("")

    def test_rejects_seven_transitions(self) -> None:
        schedule = "00:00/18 " + " ".join(
            f"{hour:02d}:00/18" for hour in range(1, 7)
        )
        with pytest.raises(ValueError, match="between 1 and 6"):
            validate_day_type_schedule(schedule)

    def test_requires_midnight_first(self) -> None:
        with pytest.raises(ValueError, match="start with '00:00/'"):
            validate_day_type_schedule("06:00/20 00:00/18")

    def test_accepts_half_degree(self) -> None:
        assert validate_day_type_schedule("00:00/18.5") == "00:00/18.5"

    def test_normalises_whole_degree(self) -> None:
        assert (
            validate_day_type_schedule("00:00/18.0 06:30/20.0")
            == "00:00/18 06:30/20"
        )

    def test_rejects_quarter_degree(self) -> None:
        with pytest.raises(ValueError, match="0.5"):
            validate_day_type_schedule("00:00/18.25")

    @pytest.mark.parametrize("temperature", ["3.5", "35.5"])
    def test_rejects_out_of_range(self, temperature: str) -> None:
        with pytest.raises(ValueError, match="outside"):
            validate_day_type_schedule(f"00:00/{temperature}")

    @pytest.mark.parametrize("time_value", ["24:00", "00:60", "6:00"])
    def test_rejects_bad_time(self, time_value: str) -> None:
        with pytest.raises(ValueError, match="invalid time"):
            validate_day_type_schedule(f"00:00/18 {time_value}/20")

    def test_rejects_non_ascending_times(self) -> None:
        with pytest.raises(ValueError, match="later than"):
            validate_day_type_schedule("00:00/18 06:00/20 05:00/18")


class TestAreaResolution:
    """Catch-all and explicit area resolution."""

    def test_explicit_areas(self) -> None:
        configs = [SimpleNamespace(area_ids=["bedroom"])]
        assert resolve_effective_area_ids(configs, ["bedroom", "kitchen"]) == [
            ["bedroom"]
        ]

    def test_empty_means_all_when_nothing_mentioned(self) -> None:
        configs = [SimpleNamespace(area_ids=[])]
        assert resolve_effective_area_ids(configs, ["bedroom", "kitchen"]) == [None]

    def test_empty_is_catch_all_for_unmentioned(self) -> None:
        configs = [
            SimpleNamespace(area_ids=["bedroom"]),
            SimpleNamespace(area_ids=[]),
        ]
        assert resolve_effective_area_ids(configs, ["bedroom", "kitchen"]) == [
            ["bedroom"],
            ["kitchen"],
        ]

    def test_empty_catch_all_remainder_is_empty(self) -> None:
        configs = [
            SimpleNamespace(area_ids=["bedroom", "kitchen"]),
            SimpleNamespace(area_ids=[]),
        ]
        assert resolve_effective_area_ids(configs, ["bedroom", "kitchen"]) == [
            ["bedroom", "kitchen"],
            [],
        ]


def test_weekday_name_uses_english_names() -> None:
    assert weekday_name(datetime(2026, 11, 6)) == "friday"
    assert weekday_name(datetime(2026, 11, 7)) == "saturday"
    assert weekday_name(datetime(2026, 11, 8)) == "sunday"
