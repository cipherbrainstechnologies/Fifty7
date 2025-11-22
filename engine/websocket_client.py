"""
WebSocket client for Streamlit dashboard to receive real-time push updates.
"""

import asyncio
import json
import threading
import time
from typing import Optional, Callable, Dict, Any
from datetime import datetime
from logzero import logger
import websockets
from websockets.exceptions import ConnectionClosed, InvalidURI


class WebSocketClient:
    """
    WebSocket client for receiving real-time updates from server.
    Thread-safe and designed for Streamlit integration.
    """
    
    def __init__(
        self,
        uri: str = "ws://127.0.0.1:8765/ws",
        reconnect_interval: int = 5,
        ping_interval: int = 30,
    ):
        """
        Initialize WebSocket client.
        
        Args:
            uri: WebSocket server URI
            reconnect_interval: Seconds to wait before reconnecting
            ping_interval: Seconds between ping messages
        """
        self.uri = uri
        self.reconnect_interval = reconnect_interval
        self.ping_interval = ping_interval
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.connected = False
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._message_queue: list = []
        self._lock = threading.Lock()
        self._callbacks: Dict[str, list] = {}
        self._last_ping = time.time()
        
    def start(self) -> bool:
        """
        Start WebSocket client in background thread.
        
        Returns:
            True if started successfully
        """
        if self._running:
            logger.warning("WebSocket client is already running")
            return False
        
        try:
            self._running = True
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()
            logger.info(f"WebSocket client started (URI: {self.uri})")
            return True
        except Exception as e:
            logger.exception(f"Error starting WebSocket client: {e}")
            self._running = False
            return False
    
    def stop(self) -> bool:
        """
        Stop WebSocket client.
        
        Returns:
            True if stopped successfully
        """
        if not self._running:
            return False
        
        try:
            self._running = False
            self._stop_event.set()
            
            if self.websocket:
                asyncio.run(self.websocket.close())
            
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=5.0)
            
            self.connected = False
            logger.info("WebSocket client stopped")
            return True
        except Exception as e:
            logger.exception(f"Error stopping WebSocket client: {e}")
            return False
    
    def _run_loop(self):
        """Main connection loop with auto-reconnect."""
        while self._running and not self._stop_event.is_set():
            try:
                # Connect to server
                asyncio.run(self._connect_and_listen())
            except Exception as e:
                logger.exception(f"WebSocket connection error: {e}")
            
            if not self._running:
                break
            
            # Wait before reconnecting
            logger.info(f"Reconnecting in {self.reconnect_interval} seconds...")
            self._stop_event.wait(self.reconnect_interval)
    
    async def _connect_and_listen(self):
        """Connect to server and listen for messages."""
        try:
            async with websockets.connect(
                self.uri,
                ping_interval=None,  # We handle ping manually
            ) as websocket:
                self.websocket = websocket
                self.connected = True
                logger.info("WebSocket connected to server")
                
                # Send initial ping
                await self._send_ping()
                self._last_ping = time.time()
                
                # Listen for messages
                while self._running and not self._stop_event.is_set():
                    try:
                        # Check if we need to send ping
                        if time.time() - self._last_ping >= self.ping_interval:
                            await self._send_ping()
                            self._last_ping = time.time()
                        
                        # Wait for message with timeout
                        try:
                            message = await asyncio.wait_for(
                                websocket.recv(),
                                timeout=1.0
                            )
                            await self._handle_message(message)
                        except asyncio.TimeoutError:
                            # Timeout is OK, continue loop
                            continue
                        
                    except ConnectionClosed:
                        logger.warning("WebSocket connection closed by server")
                        break
                    except Exception as e:
                        logger.exception(f"Error receiving message: {e}")
                        break
                
        except InvalidURI:
            logger.error(f"Invalid WebSocket URI: {self.uri}")
        except ConnectionRefusedError:
            logger.warning(f"WebSocket server not available at {self.uri}")
        except Exception as e:
            logger.exception(f"WebSocket connection error: {e}")
        finally:
            self.connected = False
            self.websocket = None
    
    async def _send_ping(self):
        """Send ping message to server."""
        if self.websocket:
            try:
                await self.websocket.send(json.dumps({
                    'type': 'ping',
                    'timestamp': datetime.utcnow().isoformat(),
                }))
            except Exception as e:
                logger.debug(f"Failed to send ping: {e}")
    
    async def _handle_message(self, message: str):
        """Handle incoming message from server."""
        try:
            data = json.loads(message)
            msg_type = data.get('type')
            
            # Add to message queue
            with self._lock:
                self._message_queue.append(data)
                # Keep queue size manageable
                if len(self._message_queue) > 1000:
                    self._message_queue.pop(0)
            
            # Call registered callbacks
            if msg_type in self._callbacks:
                for callback in self._callbacks[msg_type]:
                    try:
                        callback(data)
                    except Exception as e:
                        logger.exception(f"Error in callback: {e}")
            
            # Also call wildcard callbacks
            if '*' in self._callbacks:
                for callback in self._callbacks['*']:
                    try:
                        callback(data)
                    except Exception as e:
                        logger.exception(f"Error in wildcard callback: {e}")
                        
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON message: {message}")
        except Exception as e:
            logger.exception(f"Error handling message: {e}")
    
    def subscribe(self, message_type: str, callback: Callable[[Dict[str, Any]], None]):
        """
        Subscribe to specific message types.
        
        Args:
            message_type: Message type ('event', 'state_update', 'state_snapshot', '*')
            callback: Callback function to call when message received
        """
        with self._lock:
            if message_type not in self._callbacks:
                self._callbacks[message_type] = []
            if callback not in self._callbacks[message_type]:
                self._callbacks[message_type].append(callback)
    
    def unsubscribe(self, message_type: str, callback: Callable[[Dict[str, Any]], None]):
        """
        Unsubscribe from message types.
        
        Args:
            message_type: Message type
            callback: Callback function to remove
        """
        with self._lock:
            if message_type in self._callbacks and callback in self._callbacks[message_type]:
                self._callbacks[message_type].remove(callback)
    
    def get_messages(self, message_type: Optional[str] = None, limit: int = 100) -> list:
        """
        Get recent messages from queue.
        
        Args:
            message_type: Filter by message type (None for all)
            limit: Maximum number of messages to return
            
        Returns:
            List of messages
        """
        with self._lock:
            messages = self._message_queue.copy()
        
        if message_type:
            messages = [m for m in messages if m.get('type') == message_type]
        
        return messages[-limit:]
    
    def clear_messages(self):
        """Clear message queue."""
        with self._lock:
            self._message_queue.clear()
    
    def is_connected(self) -> bool:
        """Check if connected to server."""
        return self.connected
    
    async def request_state(self):
        """Request state snapshot from server."""
        if self.websocket:
            try:
                await self.websocket.send(json.dumps({
                    'type': 'request_state',
                    'timestamp': datetime.utcnow().isoformat(),
                }))
            except Exception as e:
                logger.debug(f"Failed to request state: {e}")


# Global client instance
_websocket_client: Optional[WebSocketClient] = None


def get_websocket_client(uri: str = "ws://127.0.0.1:8765/ws") -> WebSocketClient:
    """Get or create WebSocket client instance."""
    global _websocket_client
    if _websocket_client is None:
        _websocket_client = WebSocketClient(uri=uri)
    return _websocket_client

