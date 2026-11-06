"""Heating Controller integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.discovery import async_load_platform

from .const import (
    CONF_AREAS,
    CONF_DAY_TYPES,
    CONF_HEATING_MODES,
    CONF_MQTT_TOPIC_BASE,
    CONF_SCHEDULES,
    CONF_SMART_TEMPERATURE_CONTROL,
    CONF_TEMPERATURE_ACCURACY,
    CONF_VALVE_CLOSING_DEGREE,
    CONF_VALVE_OPENING_DEGREE,
    DEFAULT_MQTT_TOPIC_BASE,
    DOMAIN,
    HARD_MODES,
)
from .validation import WEEKDAYS, validate_day_type_schedule
from .validators import ConfigValidationError, validate_pseudo_modes

_LOGGER = logging.getLogger(__name__)
_LOGGER.debug("Heating Controller module loaded. DOMAIN = %s", DOMAIN)


def _validate_day_type_schedule(schedule: str) -> str:
    """Validate and normalise a day-type schedule."""
    try:
        return validate_day_type_schedule(schedule)
    except ValueError as err:
        raise vol.Invalid(str(err)) from err


_KNOWN_TOP_LEVEL_KEYS = {
    CONF_MQTT_TOPIC_BASE,
    CONF_VALVE_OPENING_DEGREE,
    CONF_VALVE_CLOSING_DEGREE,
    CONF_TEMPERATURE_ACCURACY,
    CONF_SMART_TEMPERATURE_CONTROL,
    CONF_AREAS,
    CONF_DAY_TYPES,
    CONF_SCHEDULES,
    CONF_HEATING_MODES,
}


def _duplicates(values: list[str]) -> list[str]:
    """Return duplicate values in input order."""
    seen: set[str] = set()
    duplicates: set[str] = set()

    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)

    return sorted(duplicates)


def _log_config_warnings(heating_config: dict[str, Any]) -> None:
    """Log non-fatal configuration problems (warn-only policy)."""
    for key in heating_config:
        if key not in _KNOWN_TOP_LEVEL_KEYS:
            _LOGGER.warning(
                "Unknown configuration key '%s' will be ignored", key
            )

    areas = heating_config.get(CONF_AREAS, [])
    area_ids = [area.get("id") for area in areas if area.get("id")]
    for area_id in _duplicates(area_ids):
        _LOGGER.warning("Duplicate area id '%s' in areas", area_id)

    modes = heating_config.get(CONF_HEATING_MODES, [])
    if not modes:
        _LOGGER.warning(
            "No heating_modes configured; select.heating_mode will have no options"
        )

    mode_names = [mode.get("name") for mode in modes if mode.get("name")]
    for mode_name in _duplicates(mode_names):
        _LOGGER.warning("Duplicate heating mode name '%s'", mode_name)

    for mode in modes:
        for config in mode.get("configurations", []) or []:
            for area_id in _duplicates(config.get("area_ids") or []):
                _LOGGER.warning(
                    "Heating mode '%s' has duplicate area id '%s'",
                    mode.get("name"),
                    area_id,
                )

    day_types = heating_config.get(CONF_DAY_TYPES, {})
    schedules = heating_config.get(CONF_SCHEDULES, {})

    if "default" not in schedules:
        _LOGGER.warning(
            "Missing 'default' schedule; parent_mode 'default' and 'stay_home' "
            "will fail when selected"
        )
    if "eco" not in schedules:
        _LOGGER.warning(
            "Missing 'eco' schedule; parent_mode 'eco' will fail when selected"
        )
    if "weekend" not in day_types:
        _LOGGER.warning(
            "Missing 'weekend' day type; parent_mode 'stay_home' will fail when selected"
        )

    known_days = set(WEEKDAYS)

    for schedule_name, week in schedules.items():
        days = {str(day).lower() for day in week}

        for day in WEEKDAYS:
            if day not in days:
                _LOGGER.warning(
                    "Schedule '%s' is missing day '%s'", schedule_name, day
                )

        for day in sorted(days - known_days):
            _LOGGER.warning(
                "Schedule '%s' has unknown day '%s'", schedule_name, day
            )

        for day, day_type in week.items():
            if day_type not in day_types:
                _LOGGER.warning(
                    "Schedule '%s' day '%s' references unknown day type '%s'",
                    schedule_name,
                    day,
                    day_type,
                )


# Configuration schema for configuration.yaml
CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Optional(
                    CONF_MQTT_TOPIC_BASE, default=DEFAULT_MQTT_TOPIC_BASE
                ): cv.string,
                vol.Optional(CONF_VALVE_OPENING_DEGREE): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=100)
                ),
                vol.Optional(CONF_VALVE_CLOSING_DEGREE): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=100)
                ),
                vol.Optional(CONF_TEMPERATURE_ACCURACY): vol.All(
                    vol.Coerce(float), vol.Range(min=-1.0, max=-0.2)
                ),
                vol.Optional(CONF_SMART_TEMPERATURE_CONTROL): cv.boolean,
                vol.Required(CONF_AREAS): [
                    {
                        vol.Required("name"): cv.string,
                        vol.Required("id"): cv.string,
                        vol.Required("thermostats"): [
                            {
                                vol.Required("climate_entity"): cv.entity_id,
                                vol.Required("mqtt_name"): cv.string,
                            }
                        ],
                    }
                ],
                vol.Required(CONF_DAY_TYPES): {cv.string: _validate_day_type_schedule},
                vol.Required(CONF_SCHEDULES): {
                    cv.string: {cv.string: cv.string}  # mode -> {day: day_type}
                },
                vol.Optional(CONF_HEATING_MODES, default=[]): [
                    vol.Any(
                        # Old format: single parent_mode + area_ids
                        {
                            vol.Required("name"): cv.string,
                            vol.Required("parent_mode"): vol.In(HARD_MODES),
                            vol.Optional("area_ids", default=[]): [cv.string],
                        },
                        # New format: multiple configurations
                        {
                            vol.Required("name"): cv.string,
                            vol.Required("configurations"): [
                                {
                                    vol.Required("parent_mode"): vol.In(HARD_MODES),
                                    vol.Optional("area_ids", default=[]): [cv.string],
                                }
                            ],
                        },
                    )
                ],
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)

_LOGGER.debug("CONFIG_SCHEMA created for %s", DOMAIN)


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up Heating Controller from YAML configuration."""
    _LOGGER.debug("async_setup called. Config keys: %s", list(config.keys()))

    if DOMAIN not in config:
        _LOGGER.debug(
            "Heating Controller not in config. Available domains: %s",
            list(config.keys()),
        )
        return True

    _LOGGER.info("Heating Controller configuration found")

    hass.data.setdefault(DOMAIN, {})
    heating_config = config[DOMAIN]
    hass.data[DOMAIN]["config"] = heating_config

    _log_config_warnings(heating_config)

    # Validate heating modes configuration
    try:
        validate_pseudo_modes(
            heating_config.get(CONF_HEATING_MODES, []),
            heating_config.get(CONF_AREAS, []),
        )
    except ConfigValidationError as e:
        _LOGGER.error(f"Configuration validation error: {e}")
        return False

    _LOGGER.info("Heating modes configuration validated successfully")

    # Load the select platform
    hass.async_create_task(async_load_platform(hass, "select", DOMAIN, {}, config))

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Heating Controller from config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["entry"] = entry

    _LOGGER.debug("Heating Controller setup from config entry")

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Heating Controller unloaded")
    return True
