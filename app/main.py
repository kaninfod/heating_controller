"""
Main FastAPI application
Initializes the heating control system and exposes REST API
"""
import logging
import logging.handlers
import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings, config_loader
from app.services.ha_websocket import HomeAssistantWebSocket
from app.core.zone_manager import ZoneManager
from app.core.schedule_manager import ScheduleManager
from app.core.mode_manager import ModeManager
from app.api.routes import status, zones, schedules, modes
from app.middleware import RequestContextMiddleware
from app.dependencies import services

# Configure logging with syslog
def setup_logging():
    """Configure logging with file, console, and syslog handlers"""
    handlers = []
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))
    handlers.append(console_handler)
    
    # File handler
    os.makedirs('logs', exist_ok=True)
    file_handler = logging.FileHandler('logs/app.log')
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))
    handlers.append(file_handler)
    
    # Syslog handler (works in Docker)
    try:
        syslog_handler = logging.handlers.SysLogHandler(
            address=(settings.syslog_host, settings.syslog_port)
        )
        syslog_handler.setFormatter(logging.Formatter(
            'heating-control[%(process)d]: %(name)s - %(levelname)s - %(message)s'
        ))
        handlers.append(syslog_handler)
    except Exception as e:
        print(f"Warning: Could not configure syslog: {e}")
    
    logging.basicConfig(
        level=getattr(logging, settings.log_level),
        handlers=handlers,
        force=True
    )
    
    # Silence watchfiles logger
    logging.getLogger("watchfiles.main").setLevel(logging.WARNING)

setup_logging()
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for FastAPI
    Handles startup and shutdown events with proper error handling
    """
    # Startup
    logger.info("Starting Heating Control System", extra={
        "ha_url": settings.ha_websocket_url,
        "monitored_entities": len(settings.all_monitored_entities),
        "syslog_enabled": f"{settings.syslog_host}:{settings.syslog_port}"
    })
    
    try:
        # Initialize managers
        zone_manager = ZoneManager()
        schedule_manager = ScheduleManager()
        
        # Initialize Home Assistant WebSocket client
        ha_client = HomeAssistantWebSocket(
            url=settings.ha_websocket_url,
            access_token=settings.ha_access_token,
            monitored_entities=settings.all_monitored_entities
        )
        
        # Initialize mode manager with mode entity for persistence
        mode_manager = ModeManager(ha_client, zone_manager, schedule_manager, settings.mode_entity)
        
        # Initialize service container
        services.initialize(ha_client, zone_manager, schedule_manager, mode_manager)
        
        logger.info(f"Loaded {len(zone_manager.zones)} zones, {len(schedule_manager.schedules)} schedules")
        
        # Connect to Home Assistant with timeout
        try:
            await asyncio.wait_for(ha_client.connect(), timeout=10.0)
            logger.info("✓ Connected to Home Assistant")
            
            # Restore mode from HA after connection established
            await mode_manager.restore_mode_from_ha()
            logger.info(f"✓ Mode restored: {mode_manager.get_current_mode().value}")
            
        except asyncio.TimeoutError:
            logger.warning("⚠ Home Assistant connection timeout, will retry in background")
        except Exception as e:
            logger.error(f"⚠ Failed to connect to Home Assistant: {e}", exc_info=True)
        
        yield
        
    except Exception as e:
        logger.error(f"Failed to initialize system: {e}", exc_info=True)
        raise
    
    finally:
        # Shutdown
        logger.info("Shutting down Heating Control System")
        if services.ha_client:
            try:
                await services.ha_client.disconnect()
                logger.info("✓ Disconnected from Home Assistant")
            except Exception as e:
                logger.error(f"Error disconnecting: {e}")


# Create FastAPI app
app = FastAPI(
    title="Heating Control System",
    description="Central heating control system with zone management and scheduling",
    version="2.0.0",
    lifespan=lifespan
)

# Add request context middleware
app.add_middleware(RequestContextMiddleware)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(status.router)
app.include_router(zones.router)
app.include_router(schedules.router)
app.include_router(modes.router)


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "name": "Heating Control System",
        "version": "2.0.0",
        "status": "running",
        "endpoints": {
            "status": "/api/status",
            "zones": "/api/zones",
            "schedules": "/api/schedules",
            "modes": "/api/modes",
            "docs": "/docs"
        }
    }


@app.get("/health")
async def health():
    """Health check endpoint"""
    ha_status = "not_initialized"
    mode_status = "not_initialized"
    
    try:
        if services.ha_client:
            ha_status = services.ha_client.connection_status.value
        if services.mode_manager:
            mode_status = services.mode_manager.current_mode.value
    except Exception:
        pass
    
    return {
        "status": "healthy",
        "ha_connection": ha_status,
        "current_mode": mode_status,
        "version": "2.0.0"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,  # Disabled to avoid log file watching loop
        log_level=settings.log_level.lower()
    )
