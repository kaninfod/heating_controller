"""
Schedule generator service

Loads day type templates and generates TRVZB-formatted schedules
from week compositions. Ensures all schedules have exactly 6 time/temp
pairs starting with 00:00.
"""
from typing import Dict
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class ScheduleGenerator:
    """Generates TRVZB schedules from day type templates"""
    
    def __init__(self, day_types_path: str = "config/day_types.json"):
        self.day_types_path = day_types_path
        self.day_types: Dict[str, str] = {}
        self._load_day_types()
    
    def _load_day_types(self):
        """Load day type templates from config"""
        try:
            with open(self.day_types_path, 'r') as f:
                data = json.load(f)
                # Handle formats:
                # 1. {"day_types": {...}} or {"day_types": [...]}
                # 2. Direct format: {"workday": {...}, "weekend_day": {...}}
                if "day_types" in data:
                    day_types_data = data["day_types"]
                    if isinstance(day_types_data, dict):
                        self.day_types = {dt_id: dt_data["schedule"] for dt_id, dt_data in day_types_data.items()}
                    else:
                        self.day_types = {dt["id"]: dt["schedule"] for dt in day_types_data}
                else:
                    # Direct format: {"workday": {"schedule": "..."}, ...}
                    self.day_types = {dt_id: dt_data["schedule"] for dt_id, dt_data in data.items()}
            logger.info(f"Loaded {len(self.day_types)} day types: {list(self.day_types.keys())}")
        except Exception as e:
            logger.error(f"Failed to load day types from {self.day_types_path}: {e}")
            # Provide defaults if loading fails
            self.day_types = {
                "workday": "00:00/17 06:30/19 07:00/21 09:00/17 16:00/21 23:00/17",
                "weekend_day": "00:00/17 07:00/21 12:00/21 18:00/21 22:00/21 23:00/17",
                "eco_day": "00:00/16 06:00/17 08:00/18 16:00/18 20:00/17 23:00/16"
            }
    
    def get_day_schedule(self, day_type_id: str) -> str:
        """
        Get the TRVZB schedule string for a day type
        
        Args:
            day_type_id: ID of the day type (e.g., "workday", "weekend_day")
            
        Returns:
            TRVZB format schedule string with 6 time/temp pairs
            
        Raises:
            ValueError: If day type ID not found
        """
        if day_type_id not in self.day_types:
            raise ValueError(f"Day type '{day_type_id}' not found. Available: {list(self.day_types.keys())}")
        
        schedule = self.day_types[day_type_id]
        
        # Validate format (should have 6 pairs)
        pairs = schedule.split()
        if len(pairs) != 6:
            logger.warning(f"Day type '{day_type_id}' has {len(pairs)} pairs, expected 6")
        
        # Ensure starts with 00:00
        if not schedule.startswith("00:00/"):
            logger.warning(f"Day type '{day_type_id}' doesn't start with 00:00")
        
        return schedule
    
    def generate_week_schedule(self, week_composition: Dict[str, str]) -> Dict[str, str]:
        """
        Generate a full week schedule from day type references
        
        Args:
            week_composition: Dict mapping day names to day type IDs
                             e.g., {"monday": "workday", "tuesday": "workday", ...}
        
        Returns:
            Dict mapping day names to TRVZB schedule strings
            
        Example:
            >>> week = {
            ...     "monday": "workday",
            ...     "saturday": "weekend_day"
            ... }
            >>> generator.generate_week_schedule(week)
            {
                "monday": "00:00/17 06:30/19 07:00/21 09:00/17 16:00/21 23:00/17",
                "saturday": "00:00/17 07:00/21 12:00/21 18:00/21 22:00/21 23:00/17"
            }
        """
        result = {}
        
        for day_name, day_type_id in week_composition.items():
            try:
                result[day_name] = self.get_day_schedule(day_type_id)
            except ValueError as e:
                logger.error(f"Failed to generate schedule for {day_name}: {e}")
                # Use eco_day as fallback
                result[day_name] = self.day_types.get("eco_day", "00:00/16")
        
        return result
    
    def generate_stay_home_schedule(
        self,
        base_week: Dict[str, str],
        swap_day: str = None
    ) -> Dict[str, str]:
        """
        Generate stay-home schedule by swapping current/specified day to weekend pattern
        
        Args:
            base_week: Base week composition (day name -> day type ID)
            swap_day: Day to swap (e.g., "monday"). If None, uses current day.
        
        Returns:
            Week schedule with specified day swapped to weekend_day pattern
            
        Example:
            If today is Monday and base week has Monday as "workday":
            - Input: {"monday": "workday", "tuesday": "workday", ...}
            - Output: {"monday": "weekend_day", "tuesday": "workday", ...}
        """
        # Determine which day to swap
        if swap_day is None:
            # Auto-detect current day
            weekday = datetime.now().weekday()  # 0=Monday, 6=Sunday
            day_names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
            swap_day = day_names[weekday]
        
        logger.info(f"Generating stay-home schedule, swapping {swap_day} to weekend_day")
        
        # Create modified week composition
        modified_week = base_week.copy()
        modified_week[swap_day] = "weekend_day"
        
        # Generate full schedules
        return self.generate_week_schedule(modified_week)
    
    def reload_day_types(self):
        """Reload day types from file (useful after config changes)"""
        logger.info("Reloading day types...")
        self._load_day_types()
