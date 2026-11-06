"""Tests for pure MQTT payload construction."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_PAYLOADS_PATH = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "heating_controller"
    / "payloads.py"
)
_spec = importlib.util.spec_from_file_location(
    "heating_controller_payloads", _PAYLOADS_PATH
)
_payloads = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _payloads
_spec.loader.exec_module(_payloads)

build_mqtt_payload = _payloads.build_mqtt_payload
build_device_settings = _payloads.build_device_settings


class _FakeSchedule:
    def __init__(self, data: dict[str, str]) -> None:
        self._data = data

    def to_dict(self) -> dict[str, str]:
        return self._data


def test_scheduled_payload_includes_week() -> None:
    payload = build_mqtt_payload(
        "auto",
        _FakeSchedule({"weekly_schedule_monday": "00:00/18"}),
        mode="default",
    )
    assert payload == {
        "system_mode": "auto",
        "weekly_schedule_monday": "00:00/18",
    }


def test_manual_skips_schedule() -> None:
    payload = build_mqtt_payload(
        "heat",
        _FakeSchedule({"weekly_schedule_monday": "00:00/18"}),
        mode="manual",
    )
    assert payload == {"system_mode": "heat"}


def test_heating_off_skips_schedule() -> None:
    payload = build_mqtt_payload(
        "off",
        _FakeSchedule({"weekly_schedule_monday": "00:00/18"}),
        mode="heating_off",
    )
    assert payload == {"system_mode": "off"}


def test_device_settings_are_merged() -> None:
    payload = build_mqtt_payload(
        "auto",
        None,
        mode="default",
        device_settings={"smart_temperature_control": True},
    )
    assert payload == {
        "system_mode": "auto",
        "smart_temperature_control": True,
    }


def test_smart_on_gates_valve_and_accuracy() -> None:
    settings, ignored = build_device_settings(
        smart_temperature_control=True,
        valve_opening_degree=15,
        valve_closing_degree=100,
        temperature_accuracy=-0.6,
    )
    assert settings == {"smart_temperature_control": True}
    assert ignored == [
        "valve_opening_degree",
        "valve_closing_degree",
        "temperature_accuracy",
    ]


def test_smart_off_allows_valve_and_accuracy() -> None:
    settings, ignored = build_device_settings(
        smart_temperature_control=False,
        valve_opening_degree=15,
        valve_closing_degree=100,
        temperature_accuracy=-0.6,
    )
    assert settings == {
        "smart_temperature_control": False,
        "valve_opening_degree": 15,
        "valve_closing_degree": 100,
        "temperature_accuracy": -0.6,
    }
    assert ignored == []


def test_smart_unknown_gates_valve_and_accuracy() -> None:
    settings, ignored = build_device_settings(
        smart_temperature_control=None,
        valve_opening_degree=15,
        valve_closing_degree=None,
        temperature_accuracy=None,
    )
    assert settings == {}
    assert ignored == ["valve_opening_degree"]
