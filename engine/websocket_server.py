"""
WebSocket server for real-time push updates to Streamlit dashboard.
Uses FastAPI for async WebSocket support.
"""

import asyncio
import json
import os
import threading
from typing import Set, Dict, Any, Optional
from datetime import datetime
from logzero import logger
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import queue

from .event_bus import get_event_bus
from .state_store import get_state_store


class WebSocketManager:
    """
    Manages WebSocket connections and broadcasts events to clients.
    """
    
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self.connection_metadata: Dict[WebSocket, Dict[str, Any]] = {}
        self.lock = threading.Lock()
        self.event_bus = get_event_bus()
        self.state_store = get_state_store()
        self._subscribed = False
        self._event_queue = queue.Queue()
        self._state_queue = queue.Queue()
        self._broadcast_task: Optional[asyncio.Task] = None
        
    async def connect(self, websocket: WebSocket, client_id: Optional[str] = None):
        """
        Accept a new WebSocket connection.
        
        Args:
            websocket: WebSocket connection
            client_id: Optional client identifier
        """
        await websocket.accept()
        
        with self.lock:
            self.active_connections.add(websocket)
            self.connection_metadata[websocket] = {
                'client_id': client_id or f"client_{len(self.active_connections)}",
                'connected_at': datetime.utcnow().isoformat(),
                'last_ping': datetime.utcnow(),
            }
        
        logger.info(f"WebSocket client connected: {self.connection_metadata[websocket]['client_id']}")
        
        # Send initial state snapshot
        await self.send_state_snapshot(websocket)
        
        # Subscribe to events if not already subscribed
        if not self._subscribed:
            self._subscribe_to_events()
            self._subscribed = True
            # Start broadcast task (only once, not per connection)
            try:
                loop = asyncio.get_event_loop()
                if self._broadcast_task is None or self._broadcast_task.done():
                    self._broadcast_task = loop.create_task(self._broadcast_loop())
            except RuntimeError:
                # No event loop in this thread, will be created when first connection is made
                pass
    
    def disconnect(self, websocket: WebSocket):
        """
        Remove a WebSocket connection.
        
        Args:
            websocket: WebSocket connection to remove
        """
        with self.lock:
            if websocket in self.active_connections:
                client_id = self.connection_metadata.get(websocket, {}).get('client_id', 'unknown')
                self.active_connections.remove(websocket)
                if websocket in self.connection_metadata:
                    del self.connection_metadata[websocket]
                logger.info(f"WebSocket client disconnected: {client_id}")
    
    async def send_state_snapshot(self, websocket: WebSocket):
        """
        Send current state snapshot to a client.
        
        Args:
            websocket: WebSocket connection
        """
        try:
            snapshot = self.state_store.get_snapshot()
            message = {
                'type': 'state_snapshot',
                'data': snapshot,
                'timestamp': datetime.utcnow().isoformat(),
            }
            await websocket.send_text(json.dumps(message, default=str))
        except Exception as e:
            logger.exception(f"Failed to send state snapshot: {e}")
    
    async def broadcast_event(self, event_type: str, data: Dict[str, Any]):
        """
        Broadcast an event to all connected clients.
        
        Args:
            event_type: Type of event
            data: Event data
        """
        if not self.active_connections:
            return
        
        message = {
            'type': 'event',
            'event_type': event_type,
            'data': data,
            'timestamp': datetime.utcnow().isoformat(),
        }
        
        message_json = json.dumps(message, default=str)
        disconnected = []
        
        with self.lock:
            connections = list(self.active_connections)
        
        for connection in connections:
            try:
                await connection.send_text(message_json)
            except Exception as e:
                logger.warning(f"Failed to send event to client: {e}")
                disconnected.append(connection)
        
        # Clean up disconnected clients
        for conn in disconnected:
            self.disconnect(conn)
    
    async def broadcast_state_update(self, path: str, new_value: Any, old_value: Any):
        """
        Broadcast a state update to all connected clients.
        
        Args:
            path: State path that changed
            new_value: New state value
            old_value: Old state value
        """
        if not self.active_connections:
            return
        
        message = {
            'type': 'state_update',
            'path': path,
            'new_value': new_value,
            'old_value': old_value,
            'timestamp': datetime.utcnow().isoformat(),
        }
        
        message_json = json.dumps(message, default=str)
        disconnected = []
        
        with self.lock:
            connections = list(self.active_connections)
        
        for connection in connections:
            try:
                await connection.send_text(message_json)
            except Exception as e:
                logger.warning(f"Failed to send state update to client: {e}")
                disconnected.append(connection)
        
        # Clean up disconnected clients
        for conn in disconnected:
            self.disconnect(conn)
    
    def _subscribe_to_events(self):
        """
        Subscribe to Event Bus events and forward to WebSocket clients.
        """
        def on_event(event: Dict[str, Any]):
            """Queue event for broadcast."""
            event_type = event.get('type')
            data = event.get('data', {})
            self._event_queue.put(('event', event_type, data))
        
        def on_state_change(path: str, new_value: Any, old_value: Any):
            """Queue state change for broadcast."""
            self._state_queue.put(('state_update', path, new_value, old_value))
        
        # Subscribe to all events
        self.event_bus.subscribe('*', on_event)
        
        # Subscribe to all state changes
        self.state_store.subscribe('*', on_state_change)
        
        logger.info("WebSocket manager subscribed to Event Bus and State Store")
    
    async def _broadcast_loop(self):
        """Background task to process queued events and state updates."""
        while True:
            try:
                # Process event queue
                processed = False
                try:
                    while True:  # Process all queued events
                        msg_type, *args = self._event_queue.get_nowait()
                        if msg_type == 'event':
                            event_type, data = args
                            await self.broadcast_event(event_type, data)
                            processed = True
                except queue.Empty:
                    pass
                
                # Process state queue
                try:
                    while True:  # Process all queued state updates
                        msg_type, *args = self._state_queue.get_nowait()
                        if msg_type == 'state_update':
                            path, new_value, old_value = args
                            await self.broadcast_state_update(path, new_value, old_value)
                            processed = True
                except queue.Empty:
                    pass
                
                # Small delay to prevent busy waiting (longer if nothing processed)
                await asyncio.sleep(0.1 if not processed else 0.01)
                
            except Exception as e:
                logger.exception(f"Error in broadcast loop: {e}")
                await asyncio.sleep(0.1)
    
    async def handle_client_message(self, websocket: WebSocket, message: str):
        """
        Handle incoming message from client.
        
        Args:
            websocket: WebSocket connection
            message: Message from client
        """
        try:
            data = json.loads(message)
            msg_type = data.get('type')
            
            if msg_type == 'ping':
                # Respond to ping
                await websocket.send_text(json.dumps({
                    'type': 'pong',
                    'timestamp': datetime.utcnow().isoformat(),
                }))
            elif msg_type == 'request_state':
                # Send state snapshot
                await self.send_state_snapshot(websocket)
            elif msg_type == 'subscribe':
                # Client wants to subscribe to specific events/paths
                events = data.get('events', [])
                paths = data.get('paths', [])
                # Store subscription preferences (can be enhanced)
                with self.lock:
                    if websocket in self.connection_metadata:
                        self.connection_metadata[websocket]['subscriptions'] = {
                            'events': events,
                            'paths': paths,
                        }
            else:
                logger.debug(f"Unknown message type from client: {msg_type}")
                
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON from client: {message}")
        except Exception as e:
            logger.exception(f"Error handling client message: {e}")
    
    def get_connection_count(self) -> int:
        """Get number of active connections."""
        with self.lock:
            return len(self.active_connections)


# Global WebSocket manager instance
_websocket_manager: Optional[WebSocketManager] = None
_websocket_server_thread: Optional[threading.Thread] = None
_websocket_app: Optional[FastAPI] = None


def get_websocket_manager() -> WebSocketManager:
    """Get or create WebSocket manager instance."""
    global _websocket_manager
    if _websocket_manager is None:
        _websocket_manager = WebSocketManager()
    return _websocket_manager


def create_websocket_app() -> FastAPI:
    """Create FastAPI app with WebSocket endpoint."""
    app = FastAPI(title="Trading System WebSocket Server")
    
    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # In production, restrict to specific origins
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    manager = get_websocket_manager()
    
    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        """WebSocket endpoint for real-time updates."""
        client_id = websocket.headers.get("x-client-id")
        await manager.connect(websocket, client_id)
        
        # Ensure broadcast task is running (in case it wasn't started earlier)
        if manager._broadcast_task is None or manager._broadcast_task.done():
            try:
                loop = asyncio.get_event_loop()
                manager._broadcast_task = loop.create_task(manager._broadcast_loop())
            except Exception as e:
                logger.warning(f"Failed to start broadcast task: {e}")
        
        try:
            while True:
                # Receive messages from client
                message = await websocket.receive_text()
                await manager.handle_client_message(websocket, message)
        except WebSocketDisconnect:
            manager.disconnect(websocket)
        except Exception as e:
            logger.exception(f"WebSocket error: {e}")
            manager.disconnect(websocket)
    
    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {
            "status": "healthy",
            "connections": manager.get_connection_count(),
            "timestamp": datetime.utcnow().isoformat(),
        }
    
    return app


def _is_production() -> bool:
    """Detect if running in production (Railway, Render, etc.)"""
    return (
        os.getenv("RAILWAY_ENVIRONMENT") is not None or
        os.getenv("RENDER") is not None or
        os.getenv("PORT") is not None or
        os.getenv("DYNO") is not None  # Heroku
    )


def _get_websocket_host() -> str:
    """Get WebSocket server host based on environment."""
    if _is_production():
        # In production, bind to 0.0.0.0 to accept external connections
        return "0.0.0.0"
    return os.getenv("WEBSOCKET_HOST", "127.0.0.1")


def _get_websocket_port() -> int:
    """Get WebSocket server port based on environment."""
    if _is_production():
        # In production, Railway/Render only expose one port per service
        # For now, we'll use a separate internal port
        # NOTE: This requires Railway to expose a second port or use same port
        # For Railway, consider using the same port as Streamlit or disable WebSocket server
        port_env = os.getenv("WEBSOCKET_PORT")
        if port_env:
            try:
                port = int(port_env)
                if not (0 <= port <= 65535):
                    logger.warning(f"WEBSOCKET_PORT out of range: {port}, using default")
                    port_env = None
                else:
                    return port
            except (ValueError, TypeError):
                logger.warning(f"Invalid WEBSOCKET_PORT: {port_env}, using default")
                port_env = None
        
        # Try to use PORT environment variable (Railway provides this)
        main_port_env = os.getenv("PORT")
        if main_port_env:
            try:
                main_port = int(main_port_env)
                if 0 <= main_port <= 65535:
                    # Use PORT + 1 (may not work - Railway limitation)
                    candidate_port = main_port + 1
                    if 0 <= candidate_port <= 65535:
                        return candidate_port
            except (ValueError, TypeError):
                pass
        
        # Default fallback
        logger.warning("Could not determine port from environment, using default 8765")
        return 8765
    
    # Local development
    port_env = os.getenv("WEBSOCKET_PORT", "8765")
    try:
        port = int(port_env)
        if not (0 <= port <= 65535):
            logger.warning(f"WEBSOCKET_PORT out of range: {port}, using 8765")
            return 8765
        return port
    except (ValueError, TypeError):
        logger.warning(f"Invalid WEBSOCKET_PORT: {port_env}, using 8765")
        return 8765


def start_websocket_server(host: str = None, port: int = None):
    """
    Start WebSocket server in a separate thread.
    
    Args:
        host: Server host (defaults to environment-aware value)
        port: Server port (defaults to environment-aware value)
    """
    global _websocket_server_thread, _websocket_app
    
    # Use environment-aware defaults if not provided
    if host is None:
        host = _get_websocket_host()
    if port is None:
        port = _get_websocket_port()
    
    # Validate port is within valid range
    if not isinstance(port, int) or not (0 <= port <= 65535):
        raise ValueError(f"Port must be an integer between 0 and 65535, got: {port}")
    
    # Validate host
    if not isinstance(host, str) or not host:
        raise ValueError(f"Host must be a non-empty string, got: {host}")
    
    # Check if we should disable WebSocket in production due to port limitations
    if _is_production() and not os.getenv("WEBSOCKET_PORT"):
        logger.warning(
            "WebSocket server requires a separate port. "
            "On Railway, you may need to: "
            "1) Set WEBSOCKET_PORT environment variable, or "
            "2) Deploy WebSocket as a separate service, or "
            "3) Disable WebSocket in production (set websocket.enabled=false in config)"
        )
    
    if _websocket_server_thread and _websocket_server_thread.is_alive():
        logger.warning("WebSocket server is already running")
        return
    
    _websocket_app = create_websocket_app()
    
    def run_server():
        """Run uvicorn server."""
        try:
            config = uvicorn.Config(
                _websocket_app,
                host=host,
                port=port,
                log_level="info",
                access_log=False,
            )
            server = uvicorn.Server(config)
            asyncio.run(server.serve())
        except Exception as e:
            logger.exception(f"WebSocket server error: {e}")
    
    _websocket_server_thread = threading.Thread(
        target=run_server,
        name="WebSocketServer",
        daemon=True,
    )
    _websocket_server_thread.start()
    
    # Give server time to start
    import time
    time.sleep(0.5)
    
    protocol = "wss" if _is_production() else "ws"
    logger.info(f"WebSocket server started on {protocol}://{host}:{port}/ws")


def stop_websocket_server():
    """Stop WebSocket server."""
    global _websocket_server_thread, _websocket_app
    
    if _websocket_server_thread and _websocket_server_thread.is_alive():
        # Note: uvicorn doesn't have a clean shutdown in thread
        # In production, use proper signal handling
        logger.info("WebSocket server shutdown requested")
        _websocket_server_thread = None
        _websocket_app = None

