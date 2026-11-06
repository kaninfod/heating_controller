"""Select entities for Heating Controller."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later, async_track_state_change_event
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    CONF_SMART_TEMPERATURE_CONTROL,
    CONF_TEMPERATURE_ACCURACY,
    CONF_VALVE_CLOSING_DEGREE,
    CONF_VALVE_OPENING_DEGREE,
    DOMAIN,
)
from .models import ModeConfiguration, PseudoMode
from .mqtt_handler import ThermostatController
from .payloads import build_device_settings
from .schedule_manager import ScheduleManager
from .validation import resolve_effective_area_ids

_LOGGER = logging.getLogger(__name__)

_UNAVAILABLE_STATES = {"unavailable", "unknown"}
_REAPPLY_DELAY_SECONDS = 5


def _build_pseudo_modes(configs: list[dict[str, Any]]) -> dict[str, PseudoMode]:
    """Build PseudoMode objects from the YAML configuration."""
    pseudo_modes: dict[str, PseudoMode] = {}

    for config in configs:
        name = config["name"]

        if "configurations" in config:
            configurations = [
                ModeConfiguration(
                    parent_mode=item["parent_mode"],
                    area_ids=item.get("area_ids", []),
                )
                for item in config["configurations"]
            ]
        else:
            configurations = [
                ModeConfiguration(
                    parent_mode=config["parent_mode"],
                    area_ids=config.get("area_ids", []),
                )
            ]

        pseudo_modes[name] = PseudoMode(name=name, configurations=configurations)

    return pseudo_modes


async def async_setup_platform(
    hass: HomeAssistant,
    config: dict[str, Any],
    async_add_entities: AddEntitiesCallback,
    discovery_info: dict[str, Any] | None = None,
) -> None:
    """Set up Heating Controller select entities from YAML."""
    heating_config = hass.data.get(DOMAIN, {}).get("config")
    if not heating_config:
        _LOGGER.warning("Heating Controller config not found in hass.data")
        return

    _LOGGER.debug("Creating heating mode select entities")
    main_entity = HeatingModeSelect(hass, heating_config)
    previous_entity = PreviousHeatingModeSelect(hass, heating_config)

    hass.data[DOMAIN]["previous_mode_entity"] = previous_entity

    async_add_entities([main_entity, previous_entity], update_before_add=False)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Heating Controller select entity from a config entry."""
    config = hass.data.get(DOMAIN, {}).get("config")
    if not config:
        _LOGGER.warning("Heating Controller config not found in hass.data")
        return

    async_add_entities([HeatingModeSelect(hass, config)], update_before_add=False)


class HeatingModeSelect(SelectEntity, RestoreEntity):
    """Select entity for heating mode control."""

    _attr_icon = "mdi:fire"
    _attr_has_entity_name = True

    def __init__(self, hass: HomeAssistant, config: dict[str, Any]) -> None:
        """Initialize the select entity."""
        self.hass = hass
        self._config = config

        self._mqtt_topic_base = config.get("mqtt_topic_base", "zigbee2mqtt")
        self._areas: list[dict[str, Any]] = config.get("areas", [])
        self._day_types: dict[str, str] = config.get("day_types", {})
        self._schedules: dict[str, dict[str, str]] = config.get("schedules", {})

        self._schedule_manager = ScheduleManager(
            self._areas, self._day_types, self._schedules
        )
        self._thermostat_controller = ThermostatController(
            hass, self._mqtt_topic_base
        )

        self._pseudo_modes = _build_pseudo_modes(config.get("heating_modes", []))
        self._first_pseudo_mode = next(iter(self._pseudo_modes), None)
        self._options = list(self._pseudo_modes)

        self._mqtt_to_climate = {
            thermostat["mqtt_name"]: thermostat["climate_entity"]
            for area in self._areas
            for thermostat in area.get("thermostats", [])
        }

        self._device_settings = self._build_device_settings()

        self._attr_unique_id = "heating_mode"
        self._attr_name = "Heating mode"
        self._attr_current_option: str | None = None
        self._attr_options = self._options

        self._apply_lock = asyncio.Lock()
        self._startup_done = False
        self._availability_cancel: Any = None

    @property
    def options(self) -> list[str]:
        """Return the available heating modes."""
        return self._options

    def _build_device_settings(self) -> dict[str, Any]:
        """Build the optional device configuration payload."""
        settings, ignored = build_device_settings(
            smart_temperature_control=self._config.get(
                CONF_SMART_TEMPERATURE_CONTROL
            ),
            valve_opening_degree=self._config.get(CONF_VALVE_OPENING_DEGREE),
            valve_closing_degree=self._config.get(CONF_VALVE_CLOSING_DEGREE),
            temperature_accuracy=self._config.get(CONF_TEMPERATURE_ACCURACY),
        )

        if ignored:
            _LOGGER.warning(
                "Ignoring %s because smart_temperature_control is not false",
                ", ".join(ignored),
            )

        return settings

    async def async_added_to_hass(self) -> None:
        """Restore state and arrange startup/availability reapply."""
        await super().async_added_to_hass()

        last_state = await self.async_get_last_state()

        if last_state and last_state.state in self._options:
            self._attr_current_option = last_state.state
            _LOGGER.info(
                "Restored heating mode '%s' after restart", last_state.state
            )
        else:
            self._attr_current_option = self._first_pseudo_mode
            if last_state and last_state.state:
                _LOGGER.warning(
                    "Previous heating mode '%s' no longer exists; using '%s'",
                    last_state.state,
                    self._attr_current_option,
                )
            else:
                _LOGGER.debug(
                    "No previous state; using '%s'", self._attr_current_option
                )

        self.async_write_ha_state()

        climate_entities = list(self._mqtt_to_climate.values())
        if climate_entities:
            self.async_on_remove(
                async_track_state_change_event(
                    self.hass, climate_entities, self._handle_availability_change
                )
            )

        if self.hass.is_running:
            self.hass.async_create_task(self._async_startup_reapply())
        else:
            self.async_on_remove(
                self.hass.bus.async_listen_once(
                    EVENT_HOMEASSISTANT_STARTED, self._handle_hass_started
                )
            )

        self.async_on_remove(self._cancel_availability_reapply)

    async def _handle_hass_started(self, _event: Any) -> None:
        """Handle Home Assistant finishing startup."""
        await self._async_startup_reapply()

    async def _async_startup_reapply(self) -> None:
        """Publish the restored mode once after startup."""
        if self._startup_done:
            return

        self._startup_done = True

        if self._attr_current_option:
            await self._async_reapply()

    async def _async_reapply(self, _now: Any = None) -> None:
        """Reapply the current mode, e.g. after a TRV reconnects."""
        if self._attr_current_option:
            await self._apply_mode(
                self._attr_current_option, update_previous=False
            )

    def _handle_availability_change(self, event: Any) -> None:
        """Reapply after an unavailable thermostat becomes available."""
        if not self._startup_done:
            return

        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")

        if new_state is None or new_state.state in _UNAVAILABLE_STATES:
            return

        if old_state is None:
            return

        if old_state.state not in _UNAVAILABLE_STATES:
            return

        self._cancel_availability_reapply()
        self._availability_cancel = async_call_later(
            self.hass, _REAPPLY_DELAY_SECONDS, self._async_reapply
        )

    def _cancel_availability_reapply(self) -> None:
        """Cancel a pending availability-triggered reapply."""
        if self._availability_cancel:
            self._availability_cancel()
            self._availability_cancel = None

    async def async_select_option(self, option: str) -> None:
        """Handle a user selection."""
        _LOGGER.info("Heating mode changed to '%s'", option)
        await self._apply_mode(option, update_previous=True)

    async def _apply_mode(self, option: str, update_previous: bool) -> bool:
        """Resolve and publish one heating mode."""
        async with self._apply_lock:
            pseudo_mode = self._pseudo_modes.get(option)
            if not pseudo_mode:
                _LOGGER.error("Unknown heating mode '%s'", option)
                return False

            old_option = self._attr_current_option
            all_area_ids = [area["id"] for area in self._areas]
            effective_areas = resolve_effective_area_ids(
                pseudo_mode.configurations, all_area_ids
            )

            jobs: list[tuple[list[str], str, Any, str]] = []

            for index, (configuration, area_ids) in enumerate(
                zip(pseudo_mode.configurations, effective_areas)
            ):
                if area_ids is not None and not area_ids:
                    _LOGGER.debug(
                        "Mode '%s' configuration %d: catch-all has no remaining "
                        "areas; skipping",
                        option,
                        index,
                    )
                    continue

                parent_mode = configuration.parent_mode

                if parent_mode == "stay_home":
                    schedule_mode = "default"
                    override_day_type = "weekend"
                else:
                    schedule_mode = parent_mode
                    override_day_type = None

                if parent_mode in ("manual", "heating_off", "ventilation"):
                    weekly_schedule = None
                else:
                    try:
                        weekly_schedule = self._schedule_manager.get_weekly_schedule(
                            schedule_mode,
                            override_today_with=override_day_type,
                        )
                    except ValueError as err:
                        _LOGGER.error(
                            "Failed to build the schedule for mode '%s': %s",
                            option,
                            err,
                        )
                        return False

                mqtt_names = self._schedule_manager.get_active_mqtt_devices(
                    area_ids
                )
                mqtt_names = self._filter_available(mqtt_names)

                if not mqtt_names:
                    _LOGGER.warning(
                        "Mode '%s' configuration %d: no available thermostats; "
                        "skipping",
                        option,
                        index,
                    )
                    continue

                jobs.append(
                    (
                        mqtt_names,
                        self._get_hvac_mode(parent_mode),
                        weekly_schedule,
                        parent_mode,
                    )
                )

            if not jobs:
                _LOGGER.warning(
                    "Mode '%s' has no available thermostats; recording the mode "
                    "without publishing",
                    option,
                )

            results: list[bool] = []

            for mqtt_names, hvac_mode, weekly_schedule, parent_mode in jobs:
                results.append(
                    await self._thermostat_controller.set_mode_and_schedule(
                        mqtt_names,
                        hvac_mode,
                        weekly_schedule,
                        mode=parent_mode,
                        device_settings=self._device_settings,
                    )
                )

            if results and not all(results):
                _LOGGER.error("Failed to apply mode '%s'", option)
                return False

            self._attr_current_option = option
            self.async_write_ha_state()

            if update_previous:
                previous = old_option or option
                self.hass.data.setdefault(DOMAIN, {})["previous_mode"] = previous
                previous_entity = self.hass.data[DOMAIN].get(
                    "previous_mode_entity"
                )
                if previous_entity:
                    previous_entity._attr_current_option = previous
                    previous_entity.async_write_ha_state()

            return True

    def _filter_available(self, mqtt_names: list[str]) -> list[str]:
        """Drop thermostats whose climate entity is unavailable."""
        available: list[str] = []

        for mqtt_name in mqtt_names:
            entity_id = self._mqtt_to_climate.get(mqtt_name)

            if entity_id:
                state = self.hass.states.get(entity_id)
                if state is None or state.state in _UNAVAILABLE_STATES:
                    _LOGGER.debug(
                        "Skipping offline thermostat '%s' (%s)",
                        mqtt_name,
                        entity_id,
                    )
                    continue

            available.append(mqtt_name)

        return available

    def _get_hvac_mode(self, mode: str) -> str:
        """Convert a heating mode to an HVAC mode."""
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

        self._pseudo_modes = _build_pseudo_modes(config.get("heating_modes", []))
        self._first_pseudo_mode = next(iter(self._pseudo_modes), None)
        self._options = list(self._pseudo_modes)

        self._attr_unique_id = "previous_heating_mode"
        self._attr_name = "Previous heating mode"
        self._attr_current_option: str | None = None
        self._attr_options = self._options

    @property
    def options(self) -> list[str]:
        """Return the available heating modes."""
        return self._options

    async def async_added_to_hass(self) -> None:
        """Restore the previous mode after a restart."""
        await super().async_added_to_hass()

        last_state = await self.async_get_last_state()

        if last_state and last_state.state in self._options:
            self._attr_current_option = last_state.state
        else:
            self._attr_current_option = self._first_pseudo_mode
            if last_state and last_state.state:
                _LOGGER.warning(
                    "Previous heating mode '%s' no longer exists; using '%s'",
                    last_state.state,
                    self._attr_current_option,
                )

        self.async_write_ha_state()

    async def async_select_option(self, option: str) -> None:
        """Handle a manual update of the previous-mode helper."""
        self._attr_current_option = option
        self.async_write_ha_state()
