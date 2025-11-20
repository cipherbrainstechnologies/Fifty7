"""
Position monitoring and risk management (SL/TP, trailing, profit booking)
"""

import threading
import time
from dataclasses import dataclass
from typing import Callable, Dict, Optional
from datetime import datetime
from logzero import logger

from .symbol_utils import canonicalize_tradingsymbol


@dataclass
class PositionRules:
    sl_points: int
    trail_points: int
    book1_points: int
    book2_points: int
    book1_ratio: float  # e.g., 0.5 for 50%


class PositionMonitor:
    """
    Monitors a single option position and enforces SL/TP, trailing SL, and profit booking.
    Assumptions:
    - Point-based rules on option price
    - Uses broker.get_positions() and broker.get_market_quote/getLtpData equivalent
    """

    def __init__(
        self,
        broker,
        symbol_token: str,
        exchange: str,
        entry_price: float,
        total_qty: int,
        rules: PositionRules,
        order_id: Optional[str] = None,
        symbol: Optional[str] = None,
        strike: Optional[int] = None,
        direction: Optional[str] = None,
        tradingsymbol: Optional[str] = None,
        lot_size: int = 75,
        pnl_callback: Optional[Callable[[Dict], None]] = None,
        broker_managed: bool = False,
        bracket_stop_points: Optional[float] = None,
        bracket_target_points: Optional[float] = None,
    ):
        self.broker = broker
        self.symbol_token = symbol_token
        self.exchange = exchange
        self.entry_price = float(entry_price)
        self.total_qty = int(total_qty)
        self.remaining_qty = int(total_qty)
        self.lot_size = int(lot_size)
        self.rules = rules
        self.order_id = order_id
        
        # Store symbol info for order placement (FIX for issue #10)
        self.symbol = symbol  # e.g., 'NIFTY'
        self.strike = strike  # e.g., 19000
        self.direction = direction  # e.g., 'CE' or 'PE'
        self.tradingsymbol = canonicalize_tradingsymbol(tradingsymbol)  # e.g., 'NIFTY29OCT2419000CE'
        self.pnl_callback = pnl_callback
        self.broker_managed = broker_managed
        self.bracket_stop_points = bracket_stop_points
        self.bracket_target_points = bracket_target_points

        # Derived levels
        self.stop_loss = self.entry_price - self.rules.sl_points
        self.trail_anchor = self.entry_price
        self.book1_done = False
        self.book2_done = False

        if self.broker_managed:
            # Broker handles partial exits; disable book1
            self.book1_done = True
            if self.bracket_stop_points is not None:
                self.stop_loss = self.entry_price - float(self.bracket_stop_points)
            self.broker_target_price = (
                self.entry_price + float(self.bracket_target_points)
                if self.bracket_target_points is not None
                else self.entry_price + self.rules.book2_points
            )
        else:
            self.broker_target_price = self.entry_price + self.rules.book2_points

        # Threading
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # Stats
        self.last_quote_time: Optional[datetime] = None
        self.last_ltp: Optional[float] = None
        self.closed = False
        self.realized_pnl: float = 0.0

    def start(self):
        if self._running:
            return False
        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info(
            f"PositionMonitor started (entry={self.entry_price}, SL={self.stop_loss}, qty={self.total_qty})"
        )
        return True

    def stop(self):
        if not self._running:
            return False
        self._running = False
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        logger.info("PositionMonitor stopped")
        return True

    def _loop(self):
        # 10-second monitoring cadence (as per user confirmation)
        interval_sec = 10
        while self._running and not self._stop_event.is_set() and not self.closed:
            try:
                self._tick()
            except Exception as e:
                logger.exception(f"PositionMonitor tick error: {e}")
            self._stop_event.wait(interval_sec)

    def _tick(self):
        # Fetch LTP via market quote API (LTP mode)
        params = {
            "mode": "LTP",
            "exchangeTokens": {self.exchange: [self.symbol_token]},
        }
        quote = self.broker.get_market_quote(params)
        if not isinstance(quote, dict) or not quote.get("data"):
            logger.warning("PositionMonitor: quote fetch failed or empty")
            return

        fetched = quote.get("data", {}).get("fetched", [])
        if not fetched:
            return
        ltp = float(fetched[0].get("ltp"))
        self.last_ltp = ltp
        self.last_quote_time = datetime.now()

        # Update trailing SL if price advances beyond anchor by trail_points (only when we manage exits)
        if not self.broker_managed and (ltp - self.trail_anchor) >= self.rules.trail_points:
            increments = int((ltp - self.trail_anchor) // self.rules.trail_points)
            if increments > 0:
                self.trail_anchor += increments * self.rules.trail_points
                new_sl = self.trail_anchor - self.rules.sl_points
                if new_sl > self.stop_loss:
                    logger.info(f"Trailing SL raised from {self.stop_loss} to {new_sl}")
                    self.stop_loss = new_sl

        # Profit booking levels (point-based off entry)
        # Note: total_qty and remaining_qty are in LOTS (1 lot = 75 units)
        if (not self.book1_done) and (ltp >= self.entry_price + self.rules.book1_points) and not self.broker_managed:
            qty_to_close_lots = int(round(self.remaining_qty * self.rules.book1_ratio))
            if qty_to_close_lots > 0:
                self._book_profit(qty_to_close_lots, level="L1")
                self.book1_done = True

        # Full target
        target_price = self.broker_target_price if self.broker_managed else (self.entry_price + self.rules.book2_points)
        if not self.book2_done and (ltp >= target_price):
            qty_to_close = self.remaining_qty
            if qty_to_close > 0:
                if self.broker_managed:
                    self._finalize_broker_exit("target", qty_to_close, ltp)
                else:
                    self._book_profit(qty_to_close, level="L2")
                self.book2_done = True

        # Stop loss
        if ltp <= self.stop_loss:
            qty_to_close = self.remaining_qty
            if qty_to_close > 0:
                if self.broker_managed:
                    self._finalize_broker_exit("stop_loss", qty_to_close, ltp)
                else:
                    self._exit_sl(qty_to_close)

    def _emit_position_event(self, event: str, qty_lots: int, exit_price: float, level: Optional[str] = None):
        """
        Notify listeners about realized P&L updates for the position.
        """
        if qty_lots <= 0:
            return
        try:
            exit_price = float(exit_price)
            units_closed = int(qty_lots * self.lot_size)
            pnl_value = (exit_price - self.entry_price) * units_closed
            self.realized_pnl += pnl_value

            if event == "book_profit":
                reason = f"book_profit_{level.lower()}" if level else "book_profit"
            elif event == "stop_loss":
                reason = "stop_loss"
            else:
                reason = event

            update_payload = {
                "event": event,
                "level": level,
                "reason": reason,
                "qty_lots": qty_lots,
                "qty_units": units_closed,
                "exit_price": exit_price,
                "entry_price": self.entry_price,
                "pnl": pnl_value,
                "total_pnl": self.realized_pnl,
                "order_id": self.order_id,
                "symbol": self.symbol,
                "strike": self.strike,
                "direction": self.direction,
                "remaining_qty_lots": self.remaining_qty,
                "remaining_qty_units": self.remaining_qty * self.lot_size,
                "timestamp": datetime.now().isoformat(),
            }

            if self.pnl_callback:
                try:
                    self.pnl_callback(update_payload)
                except Exception as callback_error:
                    logger.exception(f"PositionMonitor callback error: {callback_error}")
        except Exception as e:
            logger.exception(f"Failed to emit position event '{event}': {e}")

    def _book_profit(self, qty: int, level: str):
        """
        Book profit by placing SELL order to close position.
        FIXED: Now actually places orders via broker (Issue #1).
        """
        if qty <= 0 or self.remaining_qty <= 0 or self.closed:
            return
        qty = min(qty, self.remaining_qty)
        if getattr(self, "broker_managed", False):
            self._finalize_broker_exit("target", qty, self.last_ltp or (self.entry_price + self.rules.book2_points), level=level)
            return
        try:
            logger.info(f"Profit booking {level}: closing {qty} @ market")
            
            # Place SELL order to close position (FIXED: Actually execute order)
            if self.symbol and self.strike and self.direction:
                # Reverse direction for SELL (CE becomes SELL CE, PE becomes SELL PE)
                # For options: BUY creates long position, SELL closes it
                # We need to use the same tradingsymbol but with SELL transaction
                # Note: In broker API, we may need to use "SELL" transaction type
                # Since we're closing a long position, we SELL the same option
                
                # Try using tradingsymbol if available
                if self.tradingsymbol:
                    # Get symbol token for tradingsymbol (might be same as stored token)
                    symboltoken = self.broker._get_symbol_token(self.tradingsymbol, self.exchange) or self.symbol_token
                    
                    # Place SELL order using broker's place_order with SELL transaction
                    # Note: Most broker APIs require SELL transaction type to close
                    # For now, we'll use the broker's abstract interface
                    # The broker implementation should handle SELL orders
                    
                    # Since place_order uses "BUY" by default, we need to modify or use direct API
                    # For Angel One, we can call place_order but we need SELL transaction type
                    # Let's use a workaround: call broker directly with SELL transaction
                    # Use broker's place_order with SELL transaction type
                    # FIX: Broker now supports transaction_type parameter
                    order_result = self.broker.place_order(
                        symbol=self.symbol,
                        strike=self.strike,
                        direction=self.direction,
                        quantity=qty,  # qty is in lots
                        order_type="MARKET",
                        transaction_type="SELL"  # SELL to close
                    )
                    
                    if order_result.get('status') == True:
                        order_id = order_result.get('order_id')
                        logger.info(f"Profit booking {level} order placed: {order_id}")
                    else:
                        error_msg = order_result.get('message', 'Unknown error')
                        logger.error(f"Profit booking order failed: {error_msg}")
                        return  # Don't update remaining_qty if order failed
                else:
                    logger.error(f"Cannot book profit: missing tradingsymbol for {self.symbol} {self.strike}{self.direction}")
                    return
            else:
                logger.error(f"Cannot book profit: missing symbol info (symbol={self.symbol}, strike={self.strike}, direction={self.direction})")
                return
                
        except Exception as e:
            logger.exception(f"Error booking profit {level}: {e}")
            return  # Don't update remaining_qty if order failed
        
        # Only update remaining_qty if order was successful
        self.remaining_qty -= qty
        if self.remaining_qty == 0:
            self.closed = True
            logger.info("Position fully closed (profit targets)")
        
        if level == "L2":
            fallback_points = self.rules.book2_points
        else:
            fallback_points = self.rules.book1_points
        exit_price = self.last_ltp if self.last_ltp is not None else (self.entry_price + fallback_points)
        self._emit_position_event("book_profit", qty, exit_price, level)

    def _exit_sl(self, qty: int):
        """
        Exit stop loss by placing SELL order to close position.
        FIXED: Now actually places orders via broker (Issue #1).
        """
        if qty <= 0 or self.remaining_qty <= 0 or self.closed:
            return
        qty = min(qty, self.remaining_qty)
        if getattr(self, "broker_managed", False):
            self._finalize_broker_exit("stop_loss", qty, self.last_ltp or self.stop_loss)
            return
        try:
            logger.info(f"Stop loss hit: closing {qty} @ market")
            
            # Place SELL order to close position (FIXED: Actually execute order)
            if self.symbol and self.strike and self.direction and self.tradingsymbol:
                symboltoken = self.broker._get_symbol_token(self.tradingsymbol, self.exchange) or self.symbol_token
                
                # Use broker's place_order with SELL transaction type
                # FIX: Broker now supports transaction_type parameter
                order_result = self.broker.place_order(
                    symbol=self.symbol,
                    strike=self.strike,
                    direction=self.direction,
                    quantity=qty,  # qty is in lots
                    order_type="MARKET",
                    transaction_type="SELL"  # SELL to close
                )
                
                if order_result.get('status') == True:
                    order_id = order_result.get('order_id')
                    logger.info(f"Stop loss exit order placed: {order_id}")
                else:
                    error_msg = order_result.get('message', 'Unknown error')
                    logger.error(f"Stop loss exit order failed: {error_msg}")
                    return  # Don't update remaining_qty if order failed
            else:
                logger.error(f"Cannot exit SL: missing symbol info")
                return
                
        except Exception as e:
            logger.exception(f"Error exiting stop loss: {e}")
            return  # Don't update remaining_qty if order failed
        
        # Only update remaining_qty if order was successful
        self.remaining_qty -= qty
        if self.remaining_qty == 0:
            self.closed = True
            logger.info("Position fully closed (SL)")
        
        exit_price = self.last_ltp if self.last_ltp is not None else self.stop_loss
        self._emit_position_event("stop_loss", qty, exit_price)

    def _finalize_broker_exit(self, reason: str, qty: int, exit_price: float, level: Optional[str] = None):
        """
        Mirror a broker-managed square-off (ROBO order) so the rest of the system records the exit.
        """
        qty = min(qty, self.remaining_qty)
        if qty <= 0:
            return
        self.remaining_qty -= qty
        if self.remaining_qty <= 0:
            self.remaining_qty = 0
            self.closed = True
        event = "book_profit" if reason == "target" else "stop_loss"
        self._emit_position_event(event, qty, exit_price, level=level or "BROKER")
        if self.closed:
            logger.info("Broker-managed position closed")


