"""
Broker Reconciliation for position consistency
"""

import threading
import time
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from logzero import logger

from .state_store import get_state_store
from .event_bus import get_event_bus
from .broker_connector import BrokerInterface


class BrokerReconciliation:
    """
    Periodic broker position reconciliation to ensure state consistency.
    """
    
    def __init__(
        self,
        broker: BrokerInterface,
        interval_seconds: int = 60,
        state_store=None,
        event_bus=None,
    ):
        """
        Initialize broker reconciliation.
        
        Args:
            broker: Broker interface instance
            interval_seconds: Reconciliation interval
            state_store: StateStore instance (optional)
            event_bus: EventBus instance (optional)
        """
        self.broker = broker
        self.interval = interval_seconds
        self.state_store = state_store or get_state_store()
        self.event_bus = event_bus or get_event_bus()
        
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._last_reconciliation: Optional[datetime] = None
    
    def start(self) -> bool:
        """Start reconciliation thread."""
        if self._running:
            return False
        
        try:
            self._running = True
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._reconciliation_loop, daemon=True)
            self._thread.start()
            logger.info(f"Broker reconciliation started (interval: {self.interval}s)")
            return True
        except Exception as e:
            logger.exception(f"Error starting broker reconciliation: {e}")
            self._running = False
            return False
    
    def stop(self) -> bool:
        """Stop reconciliation thread."""
        if not self._running:
            return False
        
        try:
            self._running = False
            self._stop_event.set()
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=5.0)
            logger.info("Broker reconciliation stopped")
            return True
        except Exception as e:
            logger.exception(f"Error stopping broker reconciliation: {e}")
            return False
    
    def _reconciliation_loop(self):
        """Main reconciliation loop."""
        while self._running and not self._stop_event.is_set():
            try:
                self.reconcile_positions()
            except Exception as e:
                logger.exception(f"Reconciliation error: {e}")
            
            self._stop_event.wait(self.interval)
    
    def reconcile_positions(self) -> Dict[str, Any]:
        """
        Reconcile broker positions with local state.
        
        Returns:
            Reconciliation report
        """
        try:
            # Get broker positions
            broker_positions = self.broker.get_positions() or []
            
            # Get local positions from state store
            local_positions = self.state_store.get_state('trading.positions') or {}
            
            # Build broker position map
            broker_map = {}
            for pos in broker_positions:
                tradingsymbol = pos.get('tradingsymbol') or pos.get('symbol', '')
                if tradingsymbol:
                    broker_map[tradingsymbol] = {
                        'quantity': pos.get('netqty') or pos.get('netqtyday') or 0,
                        'avg_price': pos.get('avgprice') or 0.0,
                        'ltp': pos.get('ltp') or 0.0,
                    }
            
            # Compare and detect mismatches
            mismatches = []
            for order_id, local_pos in local_positions.items():
                if not isinstance(local_pos, dict):
                    continue
                
                tradingsymbol = local_pos.get('tradingsymbol', '')
                local_qty = local_pos.get('quantity_lots', 0) * local_pos.get('lot_size', 75)
                
                broker_pos = broker_map.get(tradingsymbol, {})
                broker_qty = broker_pos.get('quantity', 0)
                
                if abs(local_qty - broker_qty) > 0:
                    mismatches.append({
                        'order_id': order_id,
                        'tradingsymbol': tradingsymbol,
                        'local_qty': local_qty,
                        'broker_qty': broker_qty,
                        'difference': broker_qty - local_qty,
                    })
            
            # Update state store with broker positions
            self.state_store.update_state(
                'trading.broker_positions',
                broker_map,
                metadata={'last_reconciliation': datetime.utcnow().isoformat()}
            )
            
            # Emit reconciliation event
            if mismatches:
                self.event_bus.publish('position_mismatch_detected', {
                    'mismatches': mismatches,
                    'timestamp': datetime.utcnow().isoformat(),
                })
                logger.warning(f"Position mismatches detected: {len(mismatches)}")
            else:
                self.event_bus.publish('position_reconciliation_success', {
                    'broker_positions': len(broker_map),
                    'local_positions': len(local_positions),
                    'timestamp': datetime.utcnow().isoformat(),
                })
            
            self._last_reconciliation = datetime.utcnow()
            
            return {
                'mismatches': len(mismatches),
                'broker_positions': len(broker_map),
                'local_positions': len(local_positions),
                'timestamp': self._last_reconciliation.isoformat(),
            }
            
        except Exception as e:
            logger.exception(f"Reconciliation failed: {e}")
            self.event_bus.publish('position_reconciliation_error', {
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat(),
            })
            return {'error': str(e)}

