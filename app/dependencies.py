"""
Dependency injection for FastAPI
Centralizes service instances and provides type-safe dependencies
"""

from typing import Annotated
from fastapi import Depends, HTTPException

from app.services.ha_websocket import HomeAssistantWebSocket
from app.core.area_manager import AreaManager
from app.core.schedule_manager import ScheduleManager
from app.core.mode_manager import ModeManager


class ServiceContainer:
    """Container for all service instances"""

    def __init__(self):
        self.ha_client: HomeAssistantWebSocket | None = None
        self.area_manager: AreaManager | None = None
        self.schedule_manager: ScheduleManager | None = None
        self.mode_manager: ModeManager | None = None

    def initialize(
        self,
        ha_client: HomeAssistantWebSocket,
        area_manager: AreaManager,
        schedule_manager: ScheduleManager,
        mode_manager: ModeManager,
    ):
        """Initialize all services"""
        self.ha_client = ha_client
        self.area_manager = area_manager
        self.schedule_manager = schedule_manager
        self.mode_manager = mode_manager


# Global service container
services = ServiceContainer()


def get_ha_client() -> HomeAssistantWebSocket:
    """Dependency for HomeAssistant WebSocket client"""
    if not services.ha_client:
        raise HTTPException(
            status_code=503, detail="Home Assistant client not initialized"
        )
    return services.ha_client


def get_area_manager() -> AreaManager:
    """Dependency for Area Manager"""
    if not services.area_manager:
        raise HTTPException(status_code=503, detail="Area manager not initialized")
    return services.area_manager


def get_schedule_manager() -> ScheduleManager:
    """Dependency for Schedule Manager"""
    if not services.schedule_manager:
        raise HTTPException(status_code=503, detail="Schedule manager not initialized")
    return services.schedule_manager


def get_mode_manager() -> ModeManager:
    """Dependency for Mode Manager"""
    if not services.mode_manager:
        raise HTTPException(status_code=503, detail="Mode manager not initialized")
    return services.mode_manager


# Type aliases for cleaner annotations
HAClient = Annotated[HomeAssistantWebSocket, Depends(get_ha_client)]
AreaManagerDep = Annotated[AreaManager, Depends(get_area_manager)]
ScheduleManagerDep = Annotated[ScheduleManager, Depends(get_schedule_manager)]
ModeManagerDep = Annotated[ModeManager, Depends(get_mode_manager)]
