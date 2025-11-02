"""
Position monitoring and risk management (SL/TP, trailing, profit booking)
"""

import threading
import time
from dataclasses import dataclass
from typing import Dict, Optional
from datetime import datetime
from logzero import logger


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
    ):
        self.broker = broker
        self.symbol_token = symbol_token
        self.exchange = exchange
        self.entry_price = float(entry_price)
        self.total_qty = int(total_qty)
        self.remaining_qty = int(total_qty)
        self.rules = rules
        self.order_id = order_id
        
        # Store symbol info for order placement (FIX for issue #10)
        self.symbol = symbol  # e.g., 'NIFTY'
        self.strike = strike  # e.g., 19000
        self.direction = direction  # e.g., 'CE' or 'PE'
        self.tradingsymbol = tradingsymbol  # e.g., 'NIFTY29OCT2419000CE'

        # Derived levels
        self.stop_loss = self.entry_price - self.rules.sl_points
        self.trail_anchor = self.entry_price
        self.book1_done = False
        self.book2_done = False

        # Threading
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # Stats
        self.last_quote_time: Optional[datetime] = None
        self.last_ltp: Optional[float] = None
        self.closed = False

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

        # Update trailing SL if price advances beyond anchor by trail_points
        if ltp - self.trail_anchor >= self.rules.trail_points:
            increments = int((ltp - self.trail_anchor) // self.rules.trail_points)
            if increments > 0:
                self.trail_anchor += increments * self.rules.trail_points
                new_sl = self.trail_anchor - self.rules.sl_points
                if new_sl > self.stop_loss:
                    logger.info(f"Trailing SL raised from {self.stop_loss} to {new_sl}")
                    self.stop_loss = new_sl

        # Profit booking levels (point-based off entry)
        # Note: total_qty and remaining_qty are in lots (units), not individual shares
        if not self.book1_done and (ltp >= self.entry_price + self.rules.book1_points):
            qty_to_close = int(round(self.remaining_qty * self.rules.book1_ratio))
            if qty_to_close > 0:
                self._book_profit(qty_to_close, level="L1")
                self.book1_done = True

        # Full target
        if not self.book2_done and (ltp >= self.entry_price + self.rules.book2_points):
            qty_to_close = self.remaining_qty
            if qty_to_close > 0:
                self._book_profit(qty_to_close, level="L2")
                self.book2_done = True

        # Stop loss
        if ltp <= self.stop_loss:
            qty_to_close = self.remaining_qty
            if qty_to_close > 0:
                self._exit_sl(qty_to_close)

    def _book_profit(self, qty: int, level: str):
        """
        Book profit by placing SELL order to close position.
        FIXED: Now actually places orders via broker (Issue #1).
        """
        if qty <= 0 or self.remaining_qty <= 0 or self.closed:
            return
        qty = min(qty, self.remaining_qty)
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
                    if hasattr(self.broker, '_place_order_sell'):
                        order_result = self.broker._place_order_sell(
                            symbol=self.symbol,
                            strike=self.strike,
                            direction=self.direction,
                            quantity=qty,
                            order_type="MARKET",
                            symboltoken=symboltoken,
                            tradingsymbol=self.tradingsymbol
                        )
                    else:
                        # Fallback: Use broker's place_order with modified params
                        # For Angel One, we'll need to place a SELL order manually
                        logger.warning("Broker doesn't support direct SELL - using symbol token approach")
                        
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
                        logger.error("Cannot place SELL order: broker API not available")
                        return
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

    def _exit_sl(self, qty: int):
        """
        Exit stop loss by placing SELL order to close position.
        FIXED: Now actually places orders via broker (Issue #1).
        """
        if qty <= 0 or self.remaining_qty <= 0 or self.closed:
            return
        qty = min(qty, self.remaining_qty)
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


