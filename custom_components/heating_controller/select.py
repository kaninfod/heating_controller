"""Select entity for Heating Controller."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN, HARD_MODES
from .models import ModeConfiguration, PseudoMode
from .mqtt_handler import ThermostatController
from .schedule_manager import ScheduleManager

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(
    hass: HomeAssistant,
    config: dict[str, Any],
    async_add_entities: AddEntitiesCallback,
    discovery_info: dict[str, Any] | None = None,
) -> None:
    """Set up Heating Controller select entities from YAML."""
    if DOMAIN not in hass.data:
        _LOGGER.warning("Heating Controller config not found in hass.data")
        return

    heating_config = hass.data[DOMAIN].get("config")
    if not heating_config:
        _LOGGER.warning("Heating Controller config not found in hass.data")
        return

    _LOGGER.info("Creating heating mode select entities")
    main_entity = HeatingModeSelect(hass, heating_config)
    previous_entity = PreviousHeatingModeSelect(hass, heating_config)

    # Store reference to previous entity so main can update it
    hass.data[DOMAIN]["previous_mode_entity"] = previous_entity

    async_add_entities([main_entity, previous_entity], update_before_add=False)
    _LOGGER.info("Heating mode select entities created successfully")


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Heating Controller select entity."""
    if DOMAIN not in hass.data:
        _LOGGER.warning("Heating Controller config not found")
        return

    config = hass.data[DOMAIN].get("config")
    if not config:
        _LOGGER.warning("Heating Controller config not found in hass.data")
        return

    entity = HeatingModeSelect(hass, config)
    async_add_entities([entity], update_before_add=False)


class HeatingModeSelect(SelectEntity, RestoreEntity):
    """Select entity for heating mode control."""

    _attr_icon = "mdi:fire"
    _attr_has_entity_name = True

    def __init__(self, hass: HomeAssistant, config: dict[str, Any]) -> None:
        """Initialize the select entity."""
        self.hass = hass
        self._config = config

        # Extract config
        self._ventilation_time = config.get("ventilation_time_minutes", 10)
        self._mqtt_topic_base = config.get("mqtt_topic_base", "zigbee2mqtt")
        self._areas: list[dict[str, str]] = config.get("areas", [])
        self._day_types: dict[str, str] = config.get("day_types", {})
        self._schedules: dict[str, dict[str, str]] = config.get("schedules", {})
        self._pseudo_modes_config: list[dict[str, Any]] = config.get(
            "heating_modes", []
        )

        # Initialize managers
        self._schedule_manager = ScheduleManager(
            self._areas, self._day_types, self._schedules
        )
        self._thermostat_controller = ThermostatController(
            hass,
            self._mqtt_topic_base,
        )

        # Build pseudo modes from config
        self._pseudo_modes: dict[str, PseudoMode] = {}
        for pm_config in self._pseudo_modes_config:
            pm_name = pm_config["name"]

            # Support both old format (parent_mode + area_ids) and new (configurations)
            if "configurations" in pm_config:
                # New format: multiple configurations
                configurations = []
                for config_item in pm_config["configurations"]:
                    configurations.append(
                        ModeConfiguration(
                            parent_mode=config_item["parent_mode"],
                            area_ids=config_item.get("area_ids", []),
                        )
                    )
            else:
                # Old format: single parent_mode + area_ids
                configurations = [
                    ModeConfiguration(
                        parent_mode=pm_config["parent_mode"],
                        area_ids=pm_config.get("area_ids", []),
                    )
                ]

            self._pseudo_modes[pm_name] = PseudoMode(
                name=pm_name,
                configurations=configurations,
            )

        # Set current mode to first pseudo mode by default
        self._current_pseudo_mode: str | None = None
        self._first_pseudo_mode = next(iter(self._pseudo_modes.keys()), None)

        # Build options list (only pseudo modes - no HARD_MODES)
        self._options = list(self._pseudo_modes.keys())

        self._attr_unique_id = "heating_mode"
        self._attr_name = "Heating mode"
        # Don't set current_option here - let async_added_to_hass() restore it
        self._attr_current_option: str | None = None

    @property
    def options(self) -> list[str]:
        """Return list of available options."""
        return self._options

    async def async_added_to_hass(self) -> None:
        """Called when the entity is added to Home Assistant.

        Attempts to restore the previous state. If the previous state is no longer
        available (user removed it from config), falls back to the first option.
        """
        await super().async_added_to_hass()

        # Try to restore the last known state
        last_state = await self.async_get_last_state()
        if last_state and last_state.state:
            # Check if the restored state still exists in current options
            if last_state.state in self._options:
                self._attr_current_option = last_state.state
                _LOGGER.info(
                    f"Restored heating mode to '{last_state.state}' after restart"
                )
            else:
                # Previous mode was removed from config, use first option
                self._attr_current_option = self._first_pseudo_mode or "default"
                _LOGGER.warning(
                    f"Previous heating mode '{last_state.state}' no longer exists in config. "
                    f"Falling back to '{self._attr_current_option}'"
                )
        else:
            # No previous state to restore, use first option
            self._attr_current_option = self._first_pseudo_mode or "default"
            _LOGGER.debug(
                f"No previous state found. Using default mode '{self._attr_current_option}'"
            )

        self.async_write_ha_state()

    async def async_select_option(self, option: str) -> None:
        """Handle option selection for pseudo mode.

        Processes the pseudo mode's configurations and sends appropriate
        MQTT commands to each group of areas.
        """
        _LOGGER.info(f"Heating mode changed to: {option}")

        # Save previous mode
        if self.hass.data[DOMAIN].get("previous_mode") is None:
            self.hass.data[DOMAIN]["previous_mode"] = self._attr_current_option
        else:
            self.hass.data[DOMAIN]["previous_mode"] = self._attr_current_option

        # Get the pseudo mode
        pseudo_mode = self._pseudo_modes.get(option)
        if not pseudo_mode:
            _LOGGER.error(f"Unknown pseudo mode: {option}")
            return

        self._current_pseudo_mode = option

        _LOGGER.debug(
            f"Applying pseudo mode '{option}' with {len(pseudo_mode.configurations)} configuration(s)"
        )

        # Collect all explicitly mentioned area_ids to detect catch-all
        mentioned_area_ids = set()
        for config in pseudo_mode.configurations:
            if config.area_ids:  # Non-empty area_ids
                mentioned_area_ids.update(config.area_ids)

        # Process each configuration in the pseudo mode
        for i, config in enumerate(pseudo_mode.configurations):
            parent_mode = config.parent_mode
            area_ids = config.area_ids

            # If area_ids is empty and there are mentioned areas, this is a catch-all
            if not area_ids and mentioned_area_ids:
                # Get all area IDs and subtract mentioned ones
                all_area_ids = {area["id"] for area in self._areas}
                catch_all_area_ids = list(all_area_ids - mentioned_area_ids)
                _LOGGER.debug(
                    f"Config {i}: parent_mode='{parent_mode}', catch-all for unmentioned areas: {catch_all_area_ids}"
                )
                effective_area_ids = catch_all_area_ids
            elif not area_ids:
                # Empty with no mentioned areas = truly all areas
                _LOGGER.debug(
                    f"Config {i}: parent_mode='{parent_mode}', area_ids=all (all areas)"
                )
                effective_area_ids = None  # None means all areas
            else:
                # Explicit area list
                _LOGGER.debug(
                    f"Config {i}: parent_mode='{parent_mode}', area_ids={area_ids}"
                )
                effective_area_ids = area_ids

            # Determine mode and override
            if parent_mode == "stay_home":
                mode = "default"
                override_day_type = "weekend"
            else:
                mode = parent_mode
                override_day_type = None

            # Get schedule (only for modes that require it)
            # Hard modes that don't need schedules: manual, heating_off, ventilation
            modes_without_schedule = {"manual", "heating_off", "ventilation"}

            if parent_mode in modes_without_schedule:
                weekly_schedule = None
                _LOGGER.debug(
                    f"Config {i}: Hard mode '{parent_mode}' does not require a schedule"
                )
            else:
                try:
                    weekly_schedule = self._schedule_manager.get_weekly_schedule(
                        mode, override_today_with=override_day_type
                    )
                    _LOGGER.info(
                        f"Generated schedule for config {i} mode '{mode}': {weekly_schedule.to_dict()}"
                    )
                except ValueError as e:
                    _LOGGER.error(f"Failed to get schedule for config {i}: {e}")
                    return

            # Get active thermostat MQTT devices for this configuration
            thermostat_ids = self._schedule_manager.get_active_mqtt_devices(
                effective_area_ids
            )

            # Determine HVAC mode
            hvac_mode = self._get_hvac_mode(parent_mode)

            # Publish to thermostats for this configuration
            # Pass None for schedule if mode doesn't need it
            # Get global valve_opening_degree from hass.data
            valve_opening_degree = self.hass.data[DOMAIN].get(
                "valve_opening_degree", 50
            )
            await self._thermostat_controller.set_mode_and_schedule(
                thermostat_ids,
                hvac_mode,
                weekly_schedule,
                mode=parent_mode,
                valve_opening_degree=valve_opening_degree,
            )

        # Update internal state
        self._attr_current_option = option
        self.async_write_ha_state()

        # Update previous mode entity
        previous_entity = self.hass.data[DOMAIN].get("previous_mode_entity")
        if previous_entity:
            previous_entity._attr_current_option = self.hass.data[DOMAIN].get(
                "previous_mode", option
            )
            previous_entity.async_write_ha_state()

    def _get_hvac_mode(self, mode: str) -> str:
        """Convert heating mode to HVAC mode."""
        hvac_map = {
            "default": "auto",
            "stay_home": "auto",
            "eco": "auto",
            "manual": "heat",
            "heating_off": "off",
            "ventilation": "off",
        }
        return hvac_map.get(mode, "auto")


class PreviousHeatingModeSelect(SelectEntity, RestoreEntity):
    """Select entity that tracks the previous heating mode."""

    _attr_icon = "mdi:history"
    _attr_has_entity_name = True

    def __init__(self, hass: HomeAssistant, config: dict[str, Any]) -> None:
        """Initialize the previous mode select entity."""
        self.hass = hass
        self._config = config

        # Get the same options as HeatingModeSelect (heating modes only)
        self._pseudo_modes_config: list[dict[str, Any]] = config.get(
            "heating_modes", []
        )
        self._pseudo_modes: dict[str, PseudoMode] = {}
        for pm_config in self._pseudo_modes_config:
            pm_name = pm_config["name"]

            # Support both old format (parent_mode + area_ids) and new (configurations)
            if "configurations" in pm_config:
                # New format: multiple configurations
                configurations = []
                for config_item in pm_config["configurations"]:
                    configurations.append(
                        ModeConfiguration(
                            parent_mode=config_item["parent_mode"],
                            area_ids=config_item.get("area_ids", []),
                        )
                    )
            else:
                # Old format: single parent_mode + area_ids
                configurations = [
                    ModeConfiguration(
                        parent_mode=pm_config["parent_mode"],
                        area_ids=pm_config.get("area_ids", []),
                    )
                ]

            self._pseudo_modes[pm_name] = PseudoMode(
                name=pm_name,
                configurations=configurations,
            )

        first_pseudo_mode = next(iter(self._pseudo_modes.keys()), None)
        self._first_pseudo_mode = first_pseudo_mode
        self._options = list(self._pseudo_modes.keys())

        self._attr_unique_id = "previous_heating_mode"
        self._attr_name = "Previous heating mode"
        # Don't set current_option here - let async_added_to_hass() restore it
        self._attr_current_option: str | None = None

    @property
    def options(self) -> list[str]:
        """Return list of available options."""
        return self._options

    async def async_added_to_hass(self) -> None:
        """Called when the entity is added to Home Assistant.

        Attempts to restore the previous state. If the previous state is no longer
        available (user removed it from config), falls back to the first option.
        """
        await super().async_added_to_hass()

        # Try to restore the last known state
        last_state = await self.async_get_last_state()
        if last_state and last_state.state:
            # Check if the restored state still exists in current options
            if last_state.state in self._options:
                self._attr_current_option = last_state.state
                _LOGGER.info(
                    f"Restored previous heating mode to '{last_state.state}' after restart"
                )
            else:
                # Previous mode was removed from config, use first option
                self._attr_current_option = self._first_pseudo_mode or "default"
                _LOGGER.warning(
                    f"Previous heating mode '{last_state.state}' no longer exists in config. "
                    f"Falling back to '{self._attr_current_option}'"
                )
        else:
            # No previous state to restore, use first option
            self._attr_current_option = self._first_pseudo_mode or "default"
            _LOGGER.debug(
                f"No previous state found for previous mode. Using '{self._attr_current_option}'"
            )

        self.async_write_ha_state()

    async def async_select_option(self, option: str) -> None:
        """Handle option selection (not typically called, but required by interface)."""
        _LOGGER.debug(f"Previous mode updated to: {option}")
        self._attr_current_option = option
        self.async_write_ha_state()
