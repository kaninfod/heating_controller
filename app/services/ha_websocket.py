"""
Home Assistant WebSocket Client
Maintains persistent connection and tracks entity states in real-time
"""
import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, Callable, Optional, Any, List
import websockets
from websockets.exceptions import ConnectionClosed

from app.models.state import (
    ThermostatState, 
    SensorState, 
    ConnectionStatus,
    SystemState
)

logger = logging.getLogger(__name__)


class HomeAssistantWebSocket:
    """
    WebSocket client for Home Assistant
    - Maintains persistent connection
    - Subscribes to entity state changes
    - Provides methods to control thermostats
    - Caches current state of all monitored entities
    """
    
    def __init__(
        self, 
        url: str, 
        access_token: str,
        monitored_entities: List[str]
    ):
        self.url = url
        self.access_token = access_token
        self.monitored_entities = set(monitored_entities)
        
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.message_id = 1
        self.connection_status = ConnectionStatus.DISCONNECTED
        
        # State cache
        self.system_state = SystemState()
        
        # Callbacks for state changes
        self.state_change_callbacks: List[Callable] = []
        
        # Background tasks
        self.listen_task: Optional[asyncio.Task] = None
        self.reconnect_task: Optional[asyncio.Task] = None
        
    async def connect(self) -> bool:
        """Establish WebSocket connection and authenticate"""
        try:
            logger.info(f"Connecting to Home Assistant at {self.url}")
            self.connection_status = ConnectionStatus.CONNECTING
            self.system_state.connection_status = ConnectionStatus.CONNECTING
            
            self.websocket = await websockets.connect(self.url)
            
            # Wait for auth_required message
            auth_msg = await self.websocket.recv()
            auth_data = json.loads(auth_msg)
            
            if auth_data.get("type") != "auth_required":
                logger.error(f"Expected auth_required, got: {auth_data}")
                return False
            
            # Send authentication
            await self.websocket.send(json.dumps({
                "type": "auth",
                "access_token": self.access_token
            }))
            
            # Wait for auth response
            auth_response = await self.websocket.recv()
            auth_result = json.loads(auth_response)
            
            if auth_result.get("type") == "auth_ok":
                logger.info("Authentication successful")
                self.connection_status = ConnectionStatus.CONNECTED
                self.system_state.connection_status = ConnectionStatus.CONNECTED
                
                # Fetch initial states
                await self._fetch_initial_states()
                
                # Subscribe to state changes
                await self._subscribe_to_state_changes()
                
                # Start listening for messages
                self.listen_task = asyncio.create_task(self._listen_loop())
                
                return True
            else:
                logger.error(f"Authentication failed: {auth_result}")
                self.connection_status = ConnectionStatus.ERROR
                self.system_state.connection_status = ConnectionStatus.ERROR
                return False
                
        except Exception as e:
            logger.error(f"Connection error: {e}")
            self.connection_status = ConnectionStatus.ERROR
            self.system_state.connection_status = ConnectionStatus.ERROR
            return False
    
    async def disconnect(self):
        """Close WebSocket connection"""
        if self.listen_task:
            self.listen_task.cancel()
            
        if self.websocket:
            await self.websocket.close()
            
        self.connection_status = ConnectionStatus.DISCONNECTED
        self.system_state.connection_status = ConnectionStatus.DISCONNECTED
        logger.info("Disconnected from Home Assistant")
    
    async def _fetch_initial_states(self):
        """Fetch current state of all monitored entities"""
        msg_id = self._get_message_id()
        
        await self.websocket.send(json.dumps({
            "id": msg_id,
            "type": "get_states"
        }))
        
        # Wait for response
        response = await self.websocket.recv()
        data = json.loads(response)
        
        if data.get("id") == msg_id and data.get("success"):
            states = data.get("result", [])
            
            updated_count = 0
            for state in states:
                entity_id = state.get("entity_id")
                
                if entity_id in self.monitored_entities:
                    self._update_entity_state(state)
                    updated_count += 1
                    if entity_id.startswith("input_select."):
                        logger.info(f"Loaded input_select entity: {entity_id} = {state.get('state')}")
            
            logger.info(f"Fetched initial states for {updated_count}/{len(self.monitored_entities)} entities")
            logger.debug(f"Input selects after fetch: {list(self.system_state.input_selects.keys())}")
    
    async def _subscribe_to_state_changes(self):
        """Subscribe to state_changed events"""
        msg_id = self._get_message_id()
        
        await self.websocket.send(json.dumps({
            "id": msg_id,
            "type": "subscribe_events",
            "event_type": "state_changed"
        }))
        
        logger.info("Subscribed to state_changed events")
    
    async def _listen_loop(self):
        """Listen for incoming WebSocket messages"""
        try:
            async for message in self.websocket:
                try:
                    data = json.loads(message)
                    await self._handle_message(data)
                except json.JSONDecodeError as e:
                    logger.error(f"JSON decode error: {e}")
                except Exception as e:
                    logger.error(f"Error handling message: {e}")
                    
        except ConnectionClosed:
            logger.warning("WebSocket connection closed")
            self.connection_status = ConnectionStatus.DISCONNECTED
            self.system_state.connection_status = ConnectionStatus.DISCONNECTED
            # Attempt reconnection
            asyncio.create_task(self._reconnect())
        except Exception as e:
            logger.error(f"Listen loop error: {e}")
    
    async def _reconnect(self):
        """Attempt to reconnect with exponential backoff"""
        backoff = 1
        max_backoff = 60
        
        while self.connection_status != ConnectionStatus.CONNECTED:
            logger.info(f"Attempting reconnection in {backoff} seconds...")
            await asyncio.sleep(backoff)
            
            success = await self.connect()
            if success:
                logger.info("Reconnection successful")
                return
            
            backoff = min(backoff * 2, max_backoff)
    
    async def _handle_message(self, data: Dict[str, Any]):
        """Handle incoming WebSocket messages"""
        msg_type = data.get("type")
        
        if msg_type == "event":
            event = data.get("event", {})
            event_type = event.get("event_type")
            
            if event_type == "state_changed":
                event_data = event.get("data", {})
                entity_id = event_data.get("entity_id")
                new_state = event_data.get("new_state")
                
                if entity_id in self.monitored_entities and new_state:
                    self._update_entity_state(new_state)
                    
                    # Notify callbacks
                    for callback in self.state_change_callbacks:
                        try:
                            await callback(entity_id, new_state)
                        except Exception as e:
                            logger.error(f"Callback error: {e}")
    
    def _update_entity_state(self, state: Dict[str, Any]):
        """Update the cached state of an entity"""
        entity_id = state.get("entity_id")
        state_value = state.get("state")
        attributes = state.get("attributes", {})
        last_updated = state.get("last_updated")
        
        # Parse timestamp
        try:
            timestamp = datetime.fromisoformat(last_updated.replace("Z", "+00:00")) if last_updated else datetime.now()
        except:
            timestamp = datetime.now()
        
        # Determine entity type and update appropriate cache
        if entity_id.startswith("climate."):
            # Thermostat
            thermostat = ThermostatState(
                entity_id=entity_id,
                friendly_name=attributes.get("friendly_name"),
                current_temperature=attributes.get("current_temperature"),
                target_temperature=attributes.get("temperature"),
                mode=state_value,
                preset_mode=attributes.get("preset_mode"),
                battery=attributes.get("battery"),
                available=state_value != "unavailable",
                last_updated=timestamp,
                attributes=attributes
            )
            self.system_state.thermostats[entity_id] = thermostat
            
        elif entity_id.startswith("sensor.") and "temp" in entity_id.lower():
            # Temperature sensor
            try:
                sensor_value = float(state_value) if state_value != "unavailable" else None
            except (ValueError, TypeError):
                sensor_value = None
                
            sensor = SensorState(
                entity_id=entity_id,
                friendly_name=attributes.get("friendly_name"),
                state=sensor_value,
                unit=attributes.get("unit_of_measurement", "°C"),
                available=state_value != "unavailable",
                last_updated=timestamp,
                attributes=attributes
            )
            self.system_state.temperature_sensors[entity_id] = sensor
            
        elif entity_id.startswith("sensor.") and "humid" in entity_id.lower():
            # Humidity sensor
            try:
                sensor_value = float(state_value) if state_value != "unavailable" else None
            except (ValueError, TypeError):
                sensor_value = None
                
            sensor = SensorState(
                entity_id=entity_id,
                friendly_name=attributes.get("friendly_name"),
                state=sensor_value,
                unit=attributes.get("unit_of_measurement", "%"),
                available=state_value != "unavailable",
                last_updated=timestamp,
                attributes=attributes
            )
            self.system_state.humidity_sensors[entity_id] = sensor
            
        elif entity_id.startswith("input_select."):
            # Input select - for mode persistence and other select entities
            from app.models.state import InputSelectState
            
            input_select = InputSelectState(
                entity_id=entity_id,
                friendly_name=attributes.get("friendly_name"),
                state=state_value if state_value != "unavailable" else None,
                options=attributes.get("options", []),
                available=state_value != "unavailable",
                last_updated=timestamp,
                attributes=attributes
            )
            # Store in input_selects dict
            self.system_state.input_selects[entity_id] = input_select
        
        self.system_state.last_updated = datetime.now()
    
    def get_state(self) -> SystemState:
        """Get current cached system state"""
        return self.system_state
    
    def register_callback(self, callback: Callable):
        """Register a callback for state changes"""
        self.state_change_callbacks.append(callback)
    
    async def call_service(
        self, 
        domain: str, 
        service: str, 
        entity_id: Optional[str] = None,
        service_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Call a Home Assistant service
        
        Example: Set thermostat temperature
        await client.call_service("climate", "set_temperature", "climate.bedroom", {"temperature": 21})
        """
        msg_id = self._get_message_id()
        
        # Merge entity_id into service_data only if provided (some services like mqtt.publish don't use entity_id)
        combined_data = {}
        if entity_id:
            combined_data["entity_id"] = entity_id
        if service_data:
            combined_data.update(service_data)
        
        payload = {
            "id": msg_id,
            "type": "call_service",
            "domain": domain,
            "service": service,
            "service_data": combined_data
        }
        
        try:
            payload_str = json.dumps(payload)
            logger.debug(f"Sending WebSocket payload: {payload_str}")
            await self.websocket.send(payload_str)
            if entity_id:
                logger.info(f"Called {domain}.{service} on {entity_id}")
            else:
                logger.info(f"Called {domain}.{service}")
            return True
        except Exception as e:
            logger.error(f"Error calling service: {e}")
            return False
    
    async def set_thermostat_temperature(self, entity_id: str, temperature: float) -> bool:
        """Set thermostat target temperature"""
        return await self.call_service(
            "climate", 
            "set_temperature", 
            entity_id,
            {"temperature": temperature}
        )
    
    async def set_thermostat_mode(self, entity_id: str, hvac_mode: str) -> bool:
        """Set thermostat HVAC mode (off, heat, auto)"""
        return await self.call_service(
            "climate",
            "set_hvac_mode",
            entity_id,
            {"hvac_mode": hvac_mode}
        )
    
    async def set_thermostat_preset(self, entity_id: str, preset_mode: str) -> bool:
        """Set thermostat preset mode"""
        return await self.call_service(
            "climate",
            "set_preset_mode",
            entity_id,
            {"preset_mode": preset_mode}
        )
    
    async def set_input_select_option(self, entity_id: str, option: str) -> bool:
        """Set input_select option (used for mode persistence)"""
        return await self.call_service(
            "input_select",
            "select_option",
            entity_id,
            {"option": option}
        )
    
    def get_input_select_state(self, entity_id: str) -> Optional[str]:
        """Get current state of an input_select entity"""
        # Check if we're tracking this entity in any of our state collections
        # For input_select, the state is stored directly in system_state
        # We need to look it up from the raw entity states if available
        # For now, we'll need to fetch it or cache it separately
        
        # Look through all cached entities for this one
        for state_dict in [self.system_state.thermostats, 
                          self.system_state.temperature_sensors,
                          self.system_state.humidity_sensors]:
            if entity_id in state_dict:
                return getattr(state_dict[entity_id], 'state', None)
        
        return None
    
    def _get_message_id(self) -> int:
        """Get next message ID for WebSocket communication"""
        msg_id = self.message_id
        self.message_id += 1
        return msg_id
