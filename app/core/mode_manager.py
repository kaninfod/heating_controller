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
    - Default: Normal operation, zones follow their assigned schedules
    - Stay Home: Swap current day to weekend pattern, support active zones
    - Holiday: Apply eco schedule to all zones
    - Timer: Turn off now, restore to default at specified time
    - Manual: No supervision, thermostats operate independently
    - Off: All thermostats turned off
    """
    
    def __init__(self, ha_client, zone_manager, schedule_manager, mode_entity_id: str = "input_select.heating_mode"):
        self.ha_client = ha_client
        self.zone_manager = zone_manager
        self.schedule_manager = schedule_manager
        self.mode_entity_id = mode_entity_id
        
        self.current_mode = SystemMode.MANUAL
        self.previous_mode = SystemMode.MANUAL
        self.timer_task: Optional[asyncio.Task] = None
        self.timer_restore_time: Optional[datetime] = None
        
        # Register callback for mode entity changes from HA
        self.ha_client.register_callback(self._on_ha_state_change)
        
        logger.info(f"Mode Manager initialized with persistence to {mode_entity_id}")
    
    async def _sync_mode_to_ha(self, mode: SystemMode) -> bool:
        """Sync current mode to Home Assistant input_select entity"""
        try:
            success = await self.ha_client.set_input_select_option(
                self.mode_entity_id,
                mode.value
            )
            if success:
                logger.info(f"Synced mode to HA: {mode.value}", extra={"mode": mode.value, "entity_id": self.mode_entity_id})
            else:
                logger.error(f"Failed to sync mode to HA: {mode.value}", extra={"mode": mode.value, "entity_id": self.mode_entity_id})
            return success
        except Exception as e:
            logger.error(f"Error syncing mode to HA: {e}", extra={"mode": mode.value, "error": str(e)})
            return False
    
    async def _on_ha_state_change(self, entity_id: str, new_state: dict):
        """Callback for HA state changes - detect mode changes from HA UI"""
        if entity_id == self.mode_entity_id:
            new_mode_value = new_state.get("state")
            if new_mode_value:
                try:
                    new_mode = SystemMode(new_mode_value)
                    if new_mode != self.current_mode:
                        logger.info(f"Mode changed in HA UI from {self.current_mode.value} to {new_mode_value}", 
                                  extra={"old_mode": self.current_mode.value, "new_mode": new_mode_value})
                        # Apply the mode change (but don't sync back to HA to avoid loop)
                        await self._apply_mode_without_sync(new_mode)
                except ValueError:
                    logger.warning(f"Invalid mode value from HA: {new_mode_value}", extra={"mode_value": new_mode_value})
    
    async def restore_mode_from_ha(self) -> bool:
        """Restore mode from Home Assistant on startup"""
        try:
            # Get current state from HA
            input_selects = self.ha_client.system_state.input_selects
            logger.debug(f"Input selects in state: {list(input_selects.keys())}", extra={"entity_id": self.mode_entity_id})
            
            if self.mode_entity_id in input_selects:
                mode_sensor = input_selects[self.mode_entity_id]
                mode_value = mode_sensor.state
                
                logger.info(f"Found mode entity in HA with value: {mode_value}", extra={"mode": mode_value, "entity_id": self.mode_entity_id})
                
                if mode_value and mode_value != "unavailable":
                    try:
                        restored_mode = SystemMode(mode_value)
                        
                        # Check if mode is already set (avoid re-applying on restart)
                        if restored_mode == self.current_mode:
                            logger.info(f"Mode already set to {mode_value}, skipping re-apply", extra={"mode": mode_value})
                            return True
                        
                        logger.info(f"Restoring mode from HA: {mode_value}", extra={"mode": mode_value})
                        # Apply mode without syncing back to HA
                        await self._apply_mode_without_sync(restored_mode)
                        return True
                    except ValueError:
                        logger.warning(f"Invalid mode value in HA: {mode_value}", extra={"mode_value": mode_value})
            else:
                logger.info(f"Mode entity {self.mode_entity_id} not found in state, defaulting to {self.current_mode.value}")
                # Sync current default mode to HA
                await self._sync_mode_to_ha(self.current_mode)
        except Exception as e:
            logger.error(f"Error restoring mode from HA: {e}", extra={"error": str(e)}, exc_info=True)
        
        return False
    
    def get_current_mode(self) -> SystemMode:
        """Get the current system mode"""
        return self.current_mode
    
    async def set_mode(self, mode: SystemMode, **kwargs) -> bool:
        """
        Set system mode and apply changes to all thermostats
        
        kwargs can include:
        - restore_time (datetime): For timer mode
        - active_zones (list): For stay_home mode
        """
        logger.info(f"Switching from {self.current_mode} to {mode}")
        
        self.previous_mode = self.current_mode
        self.current_mode = mode
        
        # Update system state
        self.ha_client.system_state.system_mode = mode
        
        # Apply mode-specific logic
        if mode == SystemMode.DEFAULT:
            success = await self._apply_default_mode()
        elif mode == SystemMode.STAY_HOME:
            active_zones = kwargs.get('active_zones')
            success = await self._apply_stay_home_mode(active_zones)
        elif mode == SystemMode.HOLIDAY:
            success = await self._apply_holiday_mode()
        elif mode == SystemMode.TIMER:
            restore_time = kwargs.get('restore_time')
            if not restore_time:
                logger.error("Timer mode requires restore_time")
                return False
            success = await self._apply_timer_mode(restore_time)
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
        Default mode: Apply 'default' schedule to all zones
        """
        logger.info("Applying default mode - normal work week schedule")
        
        # Check if default schedule exists
        if not self.schedule_manager.get_schedule('default'):
            logger.error("default schedule not found")
            return False
        
        results = []
        for zone in self.zone_manager.get_all_zones():
            if not zone.enabled:
                continue
            
            # Apply default schedule to all thermostats in zone
            zone_results = await self.schedule_manager.apply_schedule_to_zone(
                self.ha_client,
                self.zone_manager,
                zone.id,
                'default'
            )
            
            results.extend(zone_results.values())
        
        return all(results) if results else True
    
    async def _apply_stay_home_mode(self, active_zones: Optional[list] = None) -> bool:
        """
        Stay home mode: Swap current day to weekend pattern
        - active_zones: zones to heat (swap to weekend), others stay on default
        - if None, all zones get swapped schedule
        """
        weekday_names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        current_day = weekday_names[datetime.now().weekday()]
        
        logger.info(f"Applying stay-home mode - {current_day} as weekend")
        if active_zones:
            logger.info(f"Active zones: {active_zones}")
        
        # Get default schedule for base composition
        default_schedule = self.schedule_manager.get_schedule('default')
        if not default_schedule:
            logger.error("default schedule not found")
            return False
        
        # Generate stay-home week schedule (current day swapped to weekend)
        base_week = default_schedule.week.model_dump()
        stay_home_week = self.schedule_manager.generator.generate_stay_home_schedule(
            base_week,
            swap_day=current_day
        )
        
        # Generate default week schedule for inactive zones
        default_week = self.schedule_manager.generator.generate_week_schedule(base_week)
        
        results = []
        for zone in self.zone_manager.get_all_zones():
            if not zone.enabled:
                continue
            
            # Determine which schedule to use
            if active_zones is None or zone.id in active_zones:
                # Active zone: use stay-home (swapped) schedule
                schedule_data = stay_home_week
                logger.info(f"Applying stay-home schedule to {zone.id} (active)")
            else:
                # Inactive zone: use default schedule
                schedule_data = default_week
                logger.info(f"Applying default schedule to {zone.id} (inactive)")
            
            # Apply to each thermostat in zone
            for thermostat_id in zone.thermostats:
                # Set to auto mode first
                await self.ha_client.set_thermostat_mode(thermostat_id, "auto")
                
                # Then apply the schedule
                success = await self.ha_client.call_service(
                    domain="climate",
                    service="set_weekly_schedule",
                    entity_id=thermostat_id,
                    service_data={"weekly_schedule": schedule_data}
                )
                results.append(success)
        
        return all(results) if results else True
    
    async def _apply_holiday_mode(self) -> bool:
        """
        Holiday mode: Apply eco schedule to all zones
        """
        logger.info("Applying holiday mode - eco schedule for all zones")
        
        # Check if eco schedule exists
        if not self.schedule_manager.get_schedule('eco'):
            logger.error("eco schedule not found")
            return False
        
        results = []
        for zone in self.zone_manager.get_all_zones():
            if not zone.enabled:
                continue
            
            # Apply eco schedule to all thermostats in zone
            zone_results = await self.schedule_manager.apply_schedule_to_zone(
                self.ha_client,
                self.zone_manager,
                zone.id,
                'eco'
            )
            
            results.extend(zone_results.values())
        
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
        for zone in self.zone_manager.get_all_zones():
            all_thermostats.update(zone.thermostats)
        
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
        Manual mode: No supervision, thermostats operate independently
        Just log the change, don't modify thermostat states
        """
        logger.info("Applying manual mode - no supervision")
        return True
    
    async def _apply_off_mode(self) -> bool:
        """
        Off mode: Turn off all thermostats
        """
        logger.info("Applying off mode - turning off all thermostats")
        
        results = []
        all_thermostats = set()
        for zone in self.zone_manager.get_all_zones():
            all_thermostats.update(zone.thermostats)
        
        for thermostat_id in all_thermostats:
            success = await self.ha_client.set_thermostat_mode(thermostat_id, "off")
            results.append(success)
            
            if success:
                logger.info(f"Turned off {thermostat_id}")
            else:
                logger.error(f"Failed to turn off {thermostat_id}")
        
        return all(results) if results else True
    
    def _schedule_timer_restore(self, restore_time: datetime):
        """Schedule automatic restoration to default mode"""
        # Cancel existing timer if any
        if self.timer_task:
            self.timer_task.cancel()
        
        async def restore_after_delay():
            now = datetime.now()
            delay = (restore_time - now).total_seconds()
            
            if delay > 0:
                logger.info(f"Timer set - will restore to default in {delay/3600:.1f} hours")
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
    
    async def get_all_zones_status(self) -> dict:
        """Get status of all zones with their thermostats"""
        zones_status = []
        
        state = self.ha_client.get_state()
        
        for zone in self.zone_manager.get_all_zones():
            zone_status = self.zone_manager.get_zone_status(
                zone.id,
                state.thermostats,
                state.temperature_sensors,
                state.humidity_sensors
            )
            zones_status.append(zone_status)
        
        return {
            "mode": self.get_mode_info(),
            "zones": zones_status,
            "total_zones": len(zones_status),
            "connection_status": state.connection_status.value
        }
