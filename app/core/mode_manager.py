"""
Mode Manager Service
Manages high-level system operating modes and orchestrates changes across all zones
"""

import logging
import asyncio
from typing import Dict, Optional
from datetime import datetime, timedelta

from app.models.state import SystemMode

logger = logging.getLogger(__name__)


class ModeManager:
    """
    Manages system-wide heating modes
    - Default: Normal operation, areas follow their assigned schedules
    - Stay Home: Swap current day to weekend pattern, support active areas
    - Holiday: Apply eco schedule to all areas
    - Timer: Turn off now, restore to default at specified time
    - Manual: No supervision, thermostats operate independently
    - Off: All thermostats turned off
    """

    def __init__(
        self,
        ha_client,
        schedule_manager,
        area_manager,
        thermostat_mapping: Dict = None,
        mode_entity_id: str = "input_select.heating_mode",
    ):
        self.ha_client = ha_client
        self.area_manager = area_manager
        self.schedule_manager = schedule_manager
        self.thermostat_mapping = thermostat_mapping or {}
        self.mode_entity_id = mode_entity_id

        self.current_mode = SystemMode.MANUAL
        self.previous_mode = SystemMode.MANUAL
        self.timer_task: Optional[asyncio.Task] = None
        self.timer_restore_time: Optional[datetime] = None
        self.saved_mode: Optional[SystemMode] = (
            None  # For ventilation mode to restore previous mode
        )

        # Unidirectional sync: only sync controller state to HA on startup
        logger.info(
            f"Mode Manager initialized with unidirectional persistence to {mode_entity_id}"
        )

    async def _sync_mode_to_ha(self, mode: SystemMode) -> bool:
        """Sync current mode to Home Assistant input_select entity"""
        try:
            success = await self.ha_client.set_input_select_option(
                self.mode_entity_id, mode.value
            )
            if success:
                logger.info(
                    f"Synced mode to HA: {mode.value}",
                    extra={"mode": mode.value, "entity_id": self.mode_entity_id},
                )
            else:
                logger.error(
                    f"Failed to sync mode to HA: {mode.value}",
                    extra={"mode": mode.value, "entity_id": self.mode_entity_id},
                )
            return success
        except Exception as e:
            logger.error(
                f"Error syncing mode to HA: {e}",
                extra={"mode": mode.value, "error": str(e)},
            )
            return False

    # Bidirectional sync removed: input_select changes in HA will NOT change controller mode

    async def restore_mode_from_ha(self) -> bool:
        """Restore mode from Home Assistant on startup"""
        try:
            # Get current state from HA
            input_selects = self.ha_client.system_state.input_selects
            logger.debug(
                f"Input selects in state: {list(input_selects.keys())}",
                extra={"entity_id": self.mode_entity_id},
            )

            if self.mode_entity_id in input_selects:
                mode_sensor = input_selects[self.mode_entity_id]
                mode_value = mode_sensor.state

                logger.info(
                    f"Found mode entity in HA with value: {mode_value}",
                    extra={"mode": mode_value, "entity_id": self.mode_entity_id},
                )

                if mode_value and mode_value != "unavailable":
                    try:
                        restored_mode = SystemMode(mode_value)

                        # Check if mode is already set (avoid re-applying on restart)
                        if restored_mode == self.current_mode:
                            logger.info(
                                f"Mode already set to {mode_value}, skipping re-apply",
                                extra={"mode": mode_value},
                            )
                            return True

                        logger.info(
                            f"Restoring mode from HA: {mode_value}",
                            extra={"mode": mode_value},
                        )
                        # Apply mode without syncing back to HA
                        await self._apply_mode_without_sync(restored_mode)
                        return True
                    except ValueError:
                        logger.warning(
                            f"Invalid mode value in HA: {mode_value}",
                            extra={"mode_value": mode_value},
                        )
            else:
                logger.info(
                    f"Mode entity {self.mode_entity_id} not found in state, defaulting to {self.current_mode.value}"
                )
                # Sync current default mode to HA
                await self._sync_mode_to_ha(self.current_mode)
        except Exception as e:
            logger.error(
                f"Error restoring mode from HA: {e}",
                extra={"error": str(e)},
                exc_info=True,
            )

        return False

    def get_current_mode(self) -> SystemMode:
        """Get the current system mode"""
        return self.current_mode

    async def set_mode(self, mode: SystemMode, force: bool = False, **kwargs) -> bool:
        """
        Set system mode and apply changes to all thermostats

        kwargs can include:
        - restore_time (datetime): For timer mode
        - active_areas (list): For stay_home mode
        """
        if not force and mode == self.current_mode:
            logger.info(f"Mode {mode} is already set. Skipping (force={force}).")
            return False

        logger.info(f"Switching from {self.current_mode} to {mode}")

        self.previous_mode = self.current_mode
        self.current_mode = mode

        # Update system state
        self.ha_client.system_state.system_mode = mode

        # Apply mode-specific logic
        if mode == SystemMode.DEFAULT:
            success = await self._apply_default_mode()
        elif mode == SystemMode.STAY_HOME:
            active_areas = kwargs.get("active_areas")
            success = await self._apply_stay_home_mode(active_areas=active_areas)
        elif mode == SystemMode.HOLIDAY:
            success = await self._apply_holiday_mode()
        elif mode == SystemMode.TIMER:
            restore_time = kwargs.get("restore_time")
            if not restore_time:
                logger.error("Timer mode requires restore_time")
                return False
            success = await self._apply_timer_mode(restore_time)
        elif mode == SystemMode.VENTILATION:
            ventilation_time = kwargs.get("ventilation_time", 5)
            success = await self._apply_ventilation_mode(ventilation_time)
        elif mode == SystemMode.MANUAL:
            success = await self._apply_manual_mode()
        elif mode == SystemMode.OFF:
            success = await self._apply_off_mode()
        else:
            logger.error(f"Unknown mode: {mode}")
            return False

        if success:
            logger.info(f"Successfully switched to {mode}")
            # Sync mode to Home Assistant
            await self._sync_mode_to_ha(mode)
        else:
            logger.error(f"Failed to switch to {mode}")
            self.current_mode = self.previous_mode  # Rollback

        return success

    async def _apply_mode_without_sync(self, mode: SystemMode, **kwargs) -> bool:
        """Apply mode change without syncing to HA (used when change originates from HA)"""
        logger.info(f"Applying mode from HA: {mode}")

        self.previous_mode = self.current_mode
        self.current_mode = mode
        self.ha_client.system_state.system_mode = mode

        # Apply mode-specific logic
        if mode == SystemMode.DEFAULT:
            return await self._apply_default_mode()
        elif mode == SystemMode.STAY_HOME:
            # For stay_home from HA, apply to all zones by default
            return await self._apply_stay_home_mode(None)
        elif mode == SystemMode.HOLIDAY:
            return await self._apply_holiday_mode()
        elif mode == SystemMode.VENTILATION:
            # Ventilation from HA UI uses default 5 minutes
            return await self._apply_ventilation_mode(5)
        elif mode == SystemMode.MANUAL:
            return await self._apply_manual_mode()
        elif mode == SystemMode.OFF:
            return await self._apply_off_mode()
        elif mode == SystemMode.TIMER:
            # Timer from HA UI won't have restore_time, just turn off
            logger.warning("Timer mode from HA without restore_time, just turning off")
            return await self._apply_off_mode()
        else:
            logger.error(f"Unknown mode: {mode}")
            return False

    async def _apply_default_mode(self) -> bool:
        """
        Default mode: Apply 'default' schedule to all areas
        """
        logger.info("Applying default mode - normal work week schedule")

        # Check if default schedule exists
        if not self.schedule_manager.get_schedule("default"):
            logger.error("default schedule not found")
            return False

        results = []
        for area in self.area_manager.get_all_areas():
            if not area.enabled:
                continue

            # Apply default schedule to all thermostats in area
            area_results = await self.schedule_manager.apply_schedule_to_area(
                self.ha_client, self.area_manager, area.area_id, "default"
            )

            results.extend(area_results.values())

        return all(results) if results else True

    async def _apply_ventilation_mode(self, ventilation_time: int = 5) -> bool:
        """
        Ventilation mode: Turn off all thermostats for ventilation period, then restore previous mode

        Args:
            ventilation_time: Duration in minutes (default 5 minutes)
        """
        logger.info(
            f"Applying ventilation mode - thermostats off for {ventilation_time} minutes"
        )

        # Save current mode to restore after ventilation
        self.saved_mode = self.previous_mode

        # Turn off all thermostats
        results = []
        all_thermostats = set()
        for area in self.area_manager.get_all_areas():
            all_thermostats.update(area.thermostats)

        for thermostat_id in all_thermostats:
            success = await self.ha_client.set_thermostat_mode(thermostat_id, "off")
            results.append(success)

            if success:
                logger.info(f"Turned off {thermostat_id} for ventilation")

        # Schedule restoration to previous mode
        if all(results):
            restore_time = datetime.now() + timedelta(minutes=ventilation_time)
            self._schedule_ventilation_restore(restore_time, self.saved_mode)

        return all(results) if results else True

    def _schedule_ventilation_restore(
        self, restore_time: datetime, restore_mode: SystemMode
    ):
        """Schedule restoration of previous mode after ventilation"""
        # Cancel existing timer if any
        if self.timer_task:
            self.timer_task.cancel()

        async def restore_after_ventilation():
            now = datetime.now()
            delay = (restore_time - now).total_seconds()

            if delay > 0:
                logger.info(
                    f"Ventilation scheduled - will restore to {restore_mode.value} in {delay/60:.1f} minutes"
                )
                await asyncio.sleep(delay)

                logger.info(
                    f"Ventilation complete - restoring to {restore_mode.value} mode"
                )
                # Set all thermostats to auto mode first
                all_thermostats = set()
                for area in self.area_manager.get_all_areas():
                    all_thermostats.update(area.thermostats)

                for thermostat_id in all_thermostats:
                    await self.ha_client.set_thermostat_mode(thermostat_id, "auto")

                # Restore previous mode
                await self.set_mode(restore_mode)
            else:
                logger.warning("Ventilation restore time is in the past")

        self.timer_task = asyncio.create_task(restore_after_ventilation())

    async def _apply_stay_home_mode(self, active_areas: Optional[list] = None) -> bool:
        """
        Stay home mode: Swap current day to weekend pattern
        - active_areas: areas to heat (swap to weekend), others stay on default
        - if None, all areas get swapped schedule
        """
        import json
        import re

        weekday_names = [
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        ]
        current_day = weekday_names[datetime.now().weekday()]

        logger.info(f"Applying stay-home mode - {current_day} as weekend")

        if active_areas:
            logger.info(f"Active areas: {active_areas}")

        # Get default schedule for base composition
        default_schedule = self.schedule_manager.get_schedule("default")
        if not default_schedule:
            logger.error("default schedule not found")
            return False

        # Generate stay-home week schedule (current day swapped to weekend)
        base_week = default_schedule.week.model_dump()
        logger.debug(f"Base week: {base_week}")

        stay_home_week = self.schedule_manager.generator.generate_stay_home_schedule(
            base_week, swap_day=current_day
        )
        logger.debug(f"Stay-home week: {stay_home_week}")
        logger.info(
            f"Thursday schedule in stay_home_week: {stay_home_week.get('thursday', 'NOT FOUND')}"
        )

        # Generate default week schedule for inactive areas
        default_week = self.schedule_manager.generator.generate_week_schedule(base_week)

        results = []

        for area in self.area_manager.get_all_areas():
            if not area.enabled:
                continue

            # Determine which schedule to use
            if active_areas is None or area.area_id in active_areas:
                # Active area: use stay-home (swapped) schedule
                schedule_data = stay_home_week
                logger.info(f"Applying stay-home schedule to {area.name} (active)")
            else:
                # Inactive area: use default schedule
                schedule_data = default_week
                logger.info(f"Applying default schedule to {area.name} (inactive)")

            # Apply to each thermostat in area
            for thermostat_id in area.thermostats:
                # Set to auto mode first
                await self.ha_client.set_thermostat_mode(thermostat_id, "auto")

                # Log what we're about to send
                logger.debug(
                    f"Applying schedule to {thermostat_id}: thursday={schedule_data.get('thursday', 'NOT FOUND')}"
                )

                # Get thermostat mapping to Z2M device name
                thermostat_config = self.thermostat_mapping.get(thermostat_id)
                if not thermostat_config:
                    logger.warning(
                        f"No mapping found for thermostat {thermostat_id}, skipping"
                    )
                    results.append(False)
                    continue

                z2m_device_name = thermostat_config.get("z2m_name")
                if not z2m_device_name:
                    logger.warning(
                        f"No Z2M name configured for {thermostat_id}, skipping"
                    )
                    results.append(False)
                    continue

                # Validate device name (prevent injection)
                if not re.match(r"^[a-z0-9\s\(\)]+$", z2m_device_name):
                    logger.error(f"Invalid Z2M device name: {z2m_device_name}")
                    results.append(False)
                    continue

                # Publish schedule via MQTT to Zigbee2MQTT
                mqtt_topic = f"zigbee2mqtt/{z2m_device_name}/set"
                mqtt_payload = json.dumps({"weekly_schedule": schedule_data})

                logger.debug(f"Publishing to {mqtt_topic}: {mqtt_payload[:100]}...")

                success = await self.ha_client.call_service(
                    domain="mqtt",
                    service="publish",
                    service_data={
                        "topic": mqtt_topic,
                        "payload": mqtt_payload,
                    },
                )

                if success:
                    logger.info(
                        f"Published stay-home schedule to {thermostat_id} via MQTT",
                        extra={
                            "thermostat_id": thermostat_id,
                            "z2m_device": z2m_device_name,
                        },
                    )
                else:
                    logger.error(f"Failed to publish schedule to {thermostat_id}")

                results.append(success)

        # Schedule auto-restore to default mode at midnight (since stay-home only applies to current day)
        midnight = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        midnight = midnight + timedelta(days=1)  # Next midnight
        self._schedule_stay_home_restore(midnight)

        return all(results) if results else True

    async def _apply_holiday_mode(self) -> bool:
        """
        Holiday mode: Apply eco schedule to all areas
        """
        logger.info("Applying holiday mode - eco schedule for all areas")

        # Check if eco schedule exists
        if not self.schedule_manager.get_schedule("eco"):
            logger.error("eco schedule not found")
            return False

        results = []
        for area in self.area_manager.get_all_areas():
            if not area.enabled:
                continue

            # Apply eco schedule to all thermostats in area
            area_results = await self.schedule_manager.apply_schedule_to_area(
                self.ha_client, self.area_manager, area.area_id, "eco"
            )

            results.extend(area_results.values())

        return all(results) if results else True

    async def _apply_timer_mode(self, restore_time: datetime) -> bool:
        """
        Timer mode: Turn off all thermostats now, restore to default at specified time
        """
        logger.info(f"Applying timer mode - off until {restore_time}")

        self.timer_restore_time = restore_time

        # Turn off all thermostats
        results = []
        all_thermostats = set()
        for area in self.area_manager.get_all_areas():
            all_thermostats.update(area.thermostats)

        for thermostat_id in all_thermostats:
            success = await self.ha_client.set_thermostat_mode(thermostat_id, "off")
            results.append(success)

            if success:
                logger.info(f"Turned off {thermostat_id}")

        # Schedule restoration
        if all(results):
            self._schedule_timer_restore(restore_time)

        return all(results) if results else True

    async def _apply_manual_mode(self) -> bool:
        """
        Manual mode: Thermostats operate in heat mode independently
        Sets all thermostats to 'heat' so they don't follow any schedule
        """
        logger.info("Applying manual mode - setting all thermostats to heat mode")

        results = []
        all_thermostats = set()
        for area in self.area_manager.get_all_areas():
            all_thermostats.update(area.thermostats)

        for thermostat_id in all_thermostats:
            success = await self.ha_client.set_thermostat_mode(thermostat_id, "heat")
            results.append(success)

            if success:
                logger.info(f"Set {thermostat_id} to heat mode (manual)")
            else:
                logger.error(f"Failed to set {thermostat_id} to heat mode")

        return all(results) if results else True

    async def _apply_off_mode(self) -> bool:
        """
        Off mode: Turn off all thermostats
        """
        logger.info("Applying off mode - turning off all thermostats")

        results = []
        all_thermostats = set()
        for area in self.area_manager.get_all_areas():
            all_thermostats.update(area.thermostats)

        for thermostat_id in all_thermostats:
            success = await self.ha_client.set_thermostat_mode(thermostat_id, "off")
            results.append(success)

            if success:
                logger.info(f"Turned off {thermostat_id}")
            else:
                logger.error(f"Failed to turn off {thermostat_id}")

        return all(results) if results else True

    def _schedule_stay_home_restore(self, restore_time: datetime):
        """Schedule restoration to default mode at midnight (since stay-home only applies to current day)"""
        # Don't overwrite ventilation task, only schedule if no other task is running
        if self.timer_task and self.current_mode == SystemMode.VENTILATION:
            return

        async def restore_at_midnight():
            now = datetime.now()
            delay = (restore_time - now).total_seconds()

            if delay > 0:
                hours_until_midnight = delay / 3600
                logger.info(
                    f"Stay-home scheduled - will restore to default at midnight in {hours_until_midnight:.1f} hours"
                )
                await asyncio.sleep(delay)

                if self.current_mode == SystemMode.STAY_HOME:
                    logger.info(
                        "Midnight reached - restoring from stay-home to default mode"
                    )
                    await self.set_mode(SystemMode.DEFAULT)
            else:
                logger.warning("Midnight restore time is in the past")

        self.timer_task = asyncio.create_task(restore_at_midnight())

    def _schedule_timer_restore(self, restore_time: datetime):
        """Schedule automatic restoration to default mode"""
        # Cancel existing timer if any
        if self.timer_task:
            self.timer_task.cancel()

        async def restore_after_delay():
            now = datetime.now()
            delay = (restore_time - now).total_seconds()

            if delay > 0:
                logger.info(
                    f"Timer set - will restore to default in {delay/3600:.1f} hours"
                )
                await asyncio.sleep(delay)

                logger.info("Timer expired - restoring to default mode")
                await self.set_mode(SystemMode.DEFAULT)
            else:
                logger.warning("Timer restore time is in the past")

        self.timer_task = asyncio.create_task(restore_after_delay())

    async def cancel_timer(self) -> bool:
        """Cancel timer mode and restore to default"""
        if self.current_mode != SystemMode.TIMER:
            logger.warning("Not in timer mode")
            return False

        if self.timer_task:
            self.timer_task.cancel()
            self.timer_task = None

        self.timer_restore_time = None

        # Restore to default mode
        return await self.set_mode(SystemMode.DEFAULT)

    def get_mode_info(self) -> dict:
        """Get detailed information about current mode"""
        info = {
            "current_mode": self.current_mode.value,
            "previous_mode": self.previous_mode.value,
        }

        if self.current_mode == SystemMode.TIMER and self.timer_restore_time:
            info["timer_restore_time"] = self.timer_restore_time.isoformat()
            remaining = (self.timer_restore_time - datetime.now()).total_seconds()
            info["timer_remaining_seconds"] = max(0, int(remaining))

        return info
