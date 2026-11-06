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


def build_temporary_mode_payload(
    mode: str, duration: int, target_temperature: float | None = None
) -> dict[str, Any]:
    """Build a TRV temporary-mode payload (boost or timer)."""
    payload: dict[str, Any] = {
        "temporary_mode_select": mode,
        "temporary_mode_duration": int(duration),
    }

    if target_temperature is not None:
        payload["timer_mode_target_temp"] = float(target_temperature)

    return payload


def build_device_settings_map(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Merge global, area, and thermostat device settings.

    Only independent settings belong here (open window, frost protection,
    child lock). Smart-gated valve/accuracy settings are handled separately.
    """
    global_settings = dict(config.get("device_settings") or {})
    settings_by_mqtt: dict[str, dict[str, Any]] = {}
    allowed = {"open_window", "frost_protection_temperature", "child_lock"}

    for area in config.get("areas", []):
        area_settings = {
            **global_settings,
            **(area.get("device_settings") or {}),
        }

        for thermostat in area.get("thermostats", []):
            merged = {
                **area_settings,
                **(thermostat.get("device_settings") or {}),
            }
            settings_by_mqtt[thermostat["mqtt_name"]] = {
                key: value
                for key, value in merged.items()
                if key in allowed and value is not None
            }

    return settings_by_mqtt


def clamp_external_temperature(value: float) -> float:
    """Clamp an external temperature to the TRV-supported range."""
    return round(max(0.0, min(99.9, float(value))), 1)
