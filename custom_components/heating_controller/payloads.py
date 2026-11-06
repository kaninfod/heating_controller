"""Pure MQTT payload construction helpers."""

from __future__ import annotations

from typing import Any

_SCHEDULE_SKIP_MODES = {"ventilation", "manual", "heating_off"}


def build_mqtt_payload(
    hvac_mode: str,
    weekly_schedule: Any | None,
    mode: str = "",
    device_settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the MQTT payload for one or more thermostats."""
    payload: dict[str, Any] = {"system_mode": hvac_mode}

    if device_settings:
        payload.update(device_settings)

    if weekly_schedule is not None and mode not in _SCHEDULE_SKIP_MODES:
        payload.update(weekly_schedule.to_dict())

    return payload


def build_device_settings(
    *,
    smart_temperature_control: bool | None,
    valve_opening_degree: int | None,
    valve_closing_degree: int | None,
    temperature_accuracy: float | None,
) -> tuple[dict[str, Any], list[str]]:
    """Build optional device settings and return ignored keys.

    Valve opening/closing and temperature accuracy are only usable when smart
    temperature control is explicitly disabled. When smart control is on or
    unknown, those keys are returned as ignored so the caller can warn.
    """
    settings: dict[str, Any] = {}

    if smart_temperature_control is not None:
        settings["smart_temperature_control"] = smart_temperature_control

    configured = {
        "valve_opening_degree": valve_opening_degree,
        "valve_closing_degree": valve_closing_degree,
        "temperature_accuracy": temperature_accuracy,
    }

    if smart_temperature_control is False:
        for key, value in configured.items():
            if value is not None:
                settings[key] = value
        return settings, []

    ignored = [key for key, value in configured.items() if value is not None]
    return settings, ignored
