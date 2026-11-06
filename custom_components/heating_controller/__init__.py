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
    CONF_VALVE_OPENING_DEGREE,
    DEFAULT_MQTT_TOPIC_BASE,
    DEFAULT_VALVE_OPENING_DEGREE,
    DOMAIN,
    HARD_MODES,
)
from .validators import ConfigValidationError, validate_pseudo_modes

_LOGGER = logging.getLogger(__name__)
_LOGGER.warning(f"Heating Controller module loaded. DOMAIN = {DOMAIN}")


def _validate_day_type_schedule(schedule: str) -> str:
    """Validate day type schedule format.

    Each schedule must have exactly 6 time/temperature components.
    Format: "HH:MM/TT HH:MM/TT HH:MM/TT HH:MM/TT HH:MM/TT HH:MM/TT"
    Must start with "00:00/".
    """
    parts = schedule.split()

    if len(parts) != 6:
        raise vol.Invalid(
            f"Schedule must have exactly 6 components, got {len(parts)}: {schedule}"
        )

    if not parts[0].startswith("00:00/"):
        raise vol.Invalid(f"Schedule must start with '00:00/', got: {parts[0]}")

    # Validate format of each component
    for i, part in enumerate(parts):
        if "/" not in part:
            raise vol.Invalid(f"Component {i + 1} missing temperature: {part}")
        time_part, temp_part = part.split("/", 1)
        try:
            float(temp_part)
        except ValueError:
            raise vol.Invalid(f"Component {i + 1} has invalid temperature: {temp_part}")

    return schedule


# Configuration schema for configuration.yaml
CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Optional(
                    CONF_MQTT_TOPIC_BASE, default=DEFAULT_MQTT_TOPIC_BASE
                ): cv.string,
                vol.Optional(
                    CONF_VALVE_OPENING_DEGREE, default=DEFAULT_VALVE_OPENING_DEGREE
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
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

_LOGGER.warning(f"CONFIG_SCHEMA created for {DOMAIN}")


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up Heating Controller from YAML configuration."""
    _LOGGER.warning(f"async_setup called. Config keys: {list(config.keys())}")

    if DOMAIN not in config:
        _LOGGER.info(
            f"Heating Controller not in config. Available domains: {list(config.keys())}"
        )
        return True

    _LOGGER.warning(f"Heating Controller configuration found!")

    hass.data.setdefault(DOMAIN, {})
    heating_config = config[DOMAIN]
    hass.data[DOMAIN]["config"] = heating_config
    # Store valve_opening_degree globally for use in MQTT handler
    hass.data[DOMAIN]["valve_opening_degree"] = heating_config.get(
        CONF_VALVE_OPENING_DEGREE, DEFAULT_VALVE_OPENING_DEGREE
    )

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
