"""Thermostat controller for MQTT communication."""

from __future__ import annotations

import json
import logging
from typing import Any

from homeassistant.core import HomeAssistant

from .models import WeeklySchedule

_LOGGER = logging.getLogger(__name__)


class ThermostatController:
    """Central place for all thermostat communication via MQTT."""

    def __init__(self, hass: HomeAssistant, mqtt_topic_base: str) -> None:
        """Initialize thermostat controller.

        Args:
            hass: Home Assistant instance
            mqtt_topic_base: Base MQTT topic (e.g., "zigbee2mqtt")
        """
        self.hass = hass
        self.mqtt_topic_base = mqtt_topic_base

    async def set_mode_and_schedule(
        self,
        thermostat_mqtt_names: list[str],
        hvac_mode: str,
        weekly_schedule: WeeklySchedule | None,
        mode: str = "",
        valve_opening_degree: int = 50,
    ) -> None:
        """Set HVAC mode and schedule for thermostats.

        Args:
            thermostat_mqtt_names: List of MQTT device names to update
            hvac_mode: HVAC mode (e.g., "heat", "off")
            weekly_schedule: WeeklySchedule object with the schedule, or None if no schedule needed
            mode: The heating mode (used to determine if schedule should be included)

        Note:
            The weekly schedule is sent in flattened format with individual MQTT keys per day
            (e.g., "weekly_schedule_monday", "weekly_schedule_tuesday", etc.).
            This format is required by thermostat firmware versions that support per-day
            schedule configuration.
        """
        if not thermostat_mqtt_names:
            _LOGGER.info("No thermostats to update")
            return

        _LOGGER.info(
            f"Sending mode={hvac_mode} to {len(thermostat_mqtt_names)} thermostat(s)"
        )

        payload = {
            "system_mode": hvac_mode,
            # "valve_opening_degree": valve_opening_degree,
        }

        # Only include schedule if provided and not a mode that skips it
        if weekly_schedule and mode not in ("ventilation", "manual", "heating_off"):
            payload.update(weekly_schedule.to_dict())
            _LOGGER.debug(f"Mode '{mode}': including weekly schedule")
        else:
            _LOGGER.info(f"Mode '{mode}': skipping weekly schedule")

        payload_json = json.dumps(payload)

        for mqtt_device_name in thermostat_mqtt_names:
            topic = f"{self.mqtt_topic_base}/{mqtt_device_name}/set"
            _LOGGER.info(f"Publishing to {mqtt_device_name}: {payload_json}")

            # Publish via Home Assistant MQTT service
            await self._publish(topic, payload, mqtt_device_name)

    async def _publish(
        self, topic: str, payload: dict[str, Any], device_name: str = ""
    ) -> None:
        """Publish payload to MQTT topic via Home Assistant MQTT service.

        Args:
            topic: MQTT topic
            payload: Dictionary to publish as JSON
            device_name: Device name for logging
        """
        try:
            payload_json = json.dumps(payload)

            await self.hass.services.async_call(
                "mqtt",
                "publish",
                {
                    "topic": topic,
                    "payload": payload_json,
                },
            )
            _LOGGER.debug(f"Successfully published to {device_name or topic}")
        except Exception as e:
            error_msg = str(e)
            if "Action mqtt.publish not found" in error_msg:
                _LOGGER.error(
                    f"MQTT service not available for {device_name or topic}. "
                    f"Ensure the MQTT integration is installed and loaded. "
                    f"Error: {e}"
                )
            else:
                _LOGGER.error(f"Failed to publish to {device_name or topic}: {e}")
