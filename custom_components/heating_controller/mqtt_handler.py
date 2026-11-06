"""Thermostat controller for MQTT communication."""

from __future__ import annotations

import json
import logging
from typing import Any

from homeassistant.core import HomeAssistant

from .models import WeeklySchedule
from .payloads import build_mqtt_payload

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
        device_settings: dict[str, Any] | None = None,
    ) -> bool:
        """Set HVAC mode, optional device settings, and schedule.

        Args:
            thermostat_mqtt_names: List of MQTT device names to update
            hvac_mode: HVAC mode (e.g., "heat", "off")
            weekly_schedule: WeeklySchedule object, or None if no schedule is needed
            mode: The parent heating mode (used to decide whether to include a schedule)
            device_settings: Optional device configuration keys (valve/accuracy/smart)

        Returns:
            True if every publish succeeded, False otherwise.
        """
        if not thermostat_mqtt_names:
            _LOGGER.debug("No thermostats to update")
            return True

        _LOGGER.debug(
            "Sending mode=%s to %d thermostat(s)",
            hvac_mode,
            len(thermostat_mqtt_names),
        )

        payload = build_mqtt_payload(
            hvac_mode,
            weekly_schedule,
            mode=mode,
            device_settings=device_settings,
        )

        if weekly_schedule is not None and mode not in {
            "ventilation",
            "manual",
            "heating_off",
        }:
            _LOGGER.debug("Mode '%s': including weekly schedule", mode)
        else:
            _LOGGER.debug("Mode '%s': skipping weekly schedule", mode)

        payload_json = json.dumps(payload)

        results: list[bool] = []

        for mqtt_device_name in thermostat_mqtt_names:
            topic = f"{self.mqtt_topic_base}/{mqtt_device_name}/set"
            _LOGGER.info("Publishing to %s: %s", mqtt_device_name, payload_json)
            results.append(await self._publish(topic, payload, mqtt_device_name))

        return all(results)

    async def _publish(
        self, topic: str, payload: dict[str, Any], device_name: str = ""
    ) -> bool:
        """Publish payload to an MQTT topic via Home Assistant's MQTT service."""
        try:
            await self.hass.services.async_call(
                "mqtt",
                "publish",
                {
                    "topic": topic,
                    "payload": json.dumps(payload),
                },
            )
        except Exception as err:  # noqa: BLE001 - surfaced in the log
            if "Action mqtt.publish not found" in str(err):
                _LOGGER.error(
                    "MQTT service not available for %s. Ensure the MQTT "
                    "integration is installed and loaded: %s",
                    device_name or topic,
                    err,
                )
            else:
                _LOGGER.error("Failed to publish to %s: %s", device_name or topic, err)
            return False

        _LOGGER.debug("Successfully published to %s", device_name or topic)
        return True
