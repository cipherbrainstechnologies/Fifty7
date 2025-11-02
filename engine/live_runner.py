"""
Live Strategy Runner for real-time market monitoring and trade execution
"""

import threading
import time
from typing import Dict, Optional, List
from datetime import datetime, timedelta, time as dt_time
from pytz import timezone
from logzero import logger

from engine.market_data import MarketDataProvider
from engine.signal_handler import SignalHandler
from engine.broker_connector import BrokerInterface
from engine.trade_logger import TradeLogger
from engine.position_monitor import PositionMonitor, PositionRules


class LiveStrategyRunner:
    """
    Manages live strategy execution with polling and trade execution.
    Runs in background thread to monitor market and execute trades.
    """
    
    def __init__(
        self,
        market_data_provider: MarketDataProvider,
        signal_handler: SignalHandler,
        broker: BrokerInterface,
        trade_logger: TradeLogger,
        config: Dict
    ):
        """
        Initialize LiveStrategyRunner.
        
        Args:
            market_data_provider: MarketDataProvider instance
            signal_handler: SignalHandler instance
            broker: BrokerInterface instance
            trade_logger: TradeLogger instance
            config: Configuration dictionary
        """
        self.market_data = market_data_provider
        self.signal_handler = signal_handler
        self.broker = broker
        self.trade_logger = trade_logger
        self.config = config
        
        # Running state
        self._running = False
        self._thread = None
        self._stop_event = threading.Event()
        
        # Configuration from config file
        market_data_config = config.get('market_data', {})
        self.polling_interval = market_data_config.get('polling_interval_seconds', 900)  # 15 minutes default
        self.max_retries = market_data_config.get('max_retries', 3)
        self.retry_delay = market_data_config.get('retry_delay_seconds', 5)
        
        # Strategy config
        strategy_config = config.get('strategy', {})
        self.lot_size = config.get('lot_size', 75)
        # Use broker.default_qty if provided; fallback to 2 lots
        self.order_qty = config.get('broker', {}).get('default_qty', self.lot_size * 2)
        self.sl_points = strategy_config.get('sl', 30)
        self.rr_ratio = strategy_config.get('rr', 1.8)
        
        # Statistics
        self.last_fetch_time = None
        self.last_signal_time = None
        self.cycle_count = 0
        self.error_count = 0
        self.active_monitors = []
        
        # FIX for Issue #4: Duplicate signal prevention
        self.recent_signals = {}  # signal_id -> timestamp
        self.signal_cooldown_seconds = config.get('strategy', {}).get('signal_cooldown_seconds', 3600)  # 1 hour default
        
        # FIX for Issue #8: Daily loss limit
        self.daily_loss_limit_pct = config.get('risk_management', {}).get('daily_loss_limit_pct', 5.0)  # 5% default
        self.daily_pnl = 0.0  # Track daily P&L
        self.daily_pnl_date = datetime.now().date()  # Track which day we're on
        
        # FIX for Issue #7: Position limits
        self.max_concurrent_positions = config.get('position_management', {}).get('max_concurrent_positions', 
                                                                                   config.get('sizing', {}).get('max_concurrent_positions', 2))
        
        logger.info(f"LiveStrategyRunner initialized (polling interval: {self.polling_interval}s)")
    
    def start(self) -> bool:
        """
        Start the live strategy monitoring loop.
        
        Returns:
            True if started successfully, False otherwise
        """
        if self._running:
            logger.warning("LiveStrategyRunner is already running")
            return False
        
        try:
            self._running = True
            self._stop_event.clear()
            
            # Create and start thread
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()
            
            logger.info("LiveStrategyRunner started")
            return True
            
        except Exception as e:
            logger.exception(f"Error starting LiveStrategyRunner: {e}")
            self._running = False
            return False
    
    def stop(self) -> bool:
        """
        Stop the live strategy monitoring loop.
        
        Returns:
            True if stopped successfully, False otherwise
        """
        if not self._running:
            logger.warning("LiveStrategyRunner is not running")
            return False
        
        try:
            self._running = False
            self._stop_event.set()
            
            # Wait for thread to finish (with timeout)
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=5.0)
            
            logger.info("LiveStrategyRunner stopped")
            return True
            
        except Exception as e:
            logger.exception(f"Error stopping LiveStrategyRunner: {e}")
            return False
    
    def is_running(self) -> bool:
        """Check if runner is currently running."""
        return self._running
    
    def _is_market_open(self) -> bool:
        """
        Check if market is currently open (9:15 AM - 3:30 PM IST, Monday-Friday).
        FIX for Issue #3: Market hours validation.
        
        Returns:
            True if market is open, False otherwise
        """
        try:
            ist = timezone('Asia/Kolkata')
            now = datetime.now(ist)
            
            # Check weekday (Monday=0, Friday=4, Saturday=5, Sunday=6)
            if now.weekday() >= 5:  # Saturday or Sunday
                return False
            
            # Check time (9:15 AM - 3:30 PM IST)
            market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
            market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
            
            is_open = market_open <= now <= market_close
            if not is_open:
                logger.debug(f"Market closed: Current time {now.strftime('%H:%M:%S IST')} outside trading hours (9:15-15:30)")
            
            return is_open
            
        except Exception as e:
            logger.exception(f"Error checking market hours: {e}")
            return False  # Fail safe: assume market closed if check fails
    
    def _generate_signal_id(self, signal: Dict) -> str:
        """
        Generate unique signal ID from signal parameters.
        FIX for Issue #4: Duplicate signal prevention.
        
        Args:
            signal: Signal dictionary
        
        Returns:
            Unique signal ID string
        """
        direction = signal.get('direction', '')
        strike = signal.get('strike', '')
        range_high = signal.get('range_high', '')
        range_low = signal.get('range_low', '')
        timestamp_str = signal.get('timestamp', '')[:19]  # First 19 chars (YYYY-MM-DD HH:MM:SS)
        
        # Create unique ID from signal characteristics
        signal_id = f"{direction}_{strike}_{range_high}_{range_low}_{timestamp_str}"
        return signal_id
    
    def _check_signal_duplicate(self, signal: Dict) -> bool:
        """
        Check if signal was recently executed (cooldown period).
        FIX for Issue #4: Duplicate signal prevention.
        
        Args:
            signal: Signal dictionary
        
        Returns:
            True if signal is duplicate (within cooldown), False otherwise
        """
        signal_id = self._generate_signal_id(signal)
        
        if signal_id in self.recent_signals:
            elapsed = (datetime.now() - self.recent_signals[signal_id]).total_seconds()
            if elapsed < self.signal_cooldown_seconds:
                logger.warning(f"Duplicate signal detected (cooldown active): {signal_id}, elapsed: {elapsed:.0f}s")
                return True
        
        # Not a duplicate or cooldown expired
        self.recent_signals[signal_id] = datetime.now()
        
        # Clean old signals (older than cooldown period)
        cutoff_time = datetime.now() - timedelta(seconds=self.signal_cooldown_seconds)
        self.recent_signals = {
            sid: ts for sid, ts in self.recent_signals.items()
            if ts > cutoff_time
        }
        
        return False
    
    def _check_capital_sufficient(self, order_value: float) -> bool:
        """
        Check if sufficient capital is available for order.
        FIX for Issue #5: Capital validation.
        
        Args:
            order_value: Required capital for order
        
        Returns:
            True if sufficient capital, False otherwise
        """
        try:
            available_margin = self.broker.get_available_margin()
            
            if available_margin < order_value:
                logger.error(
                    f"Insufficient capital: need ₹{order_value:,.2f}, "
                    f"have ₹{available_margin:,.2f}"
                )
                return False
            
            logger.info(
                f"Capital check passed: need ₹{order_value:,.2f}, "
                f"have ₹{available_margin:,.2f}"
            )
            return True
            
        except Exception as e:
            logger.exception(f"Error checking capital: {e}")
            return False  # Fail safe: assume insufficient if check fails
    
    def _get_nearest_expiry(self) -> Optional[datetime]:
        """
        Get nearest option expiry date.
        FIX for Issue #6: Option expiry validation.
        
        Returns:
            Nearest expiry datetime or None
        """
        try:
            expiries = self.broker.get_option_expiries("NIFTY")
            if not expiries:
                logger.warning("No expiries found for NIFTY")
                return None
            
            now = datetime.now()
            valid_expiries = [e for e in expiries if e > now]
            
            if not valid_expiries:
                logger.warning("No valid expiries found (all expired)")
                return None
            
            nearest = min(valid_expiries)
            logger.info(f"Nearest expiry: {nearest.strftime('%Y-%m-%d %H:%M:%S')}")
            return nearest
            
        except Exception as e:
            logger.exception(f"Error getting nearest expiry: {e}")
            return None
    
    def _is_safe_to_trade_expiry(self, expiry: Optional[datetime]) -> bool:
        """
        Check if it's safe to trade based on expiry date.
        FIX for Issue #6: Option expiry validation.
        
        Args:
            expiry: Expiry datetime
        
        Returns:
            True if safe to trade, False otherwise
        """
        if expiry is None:
            logger.warning("Expiry date not available - skipping trade")
            return False
        
        now = datetime.now()
        days_to_exp = (expiry - now).days
        
        # Don't trade if expires within 1 day
        if days_to_exp < 1:
            logger.warning(f"Expiry too close: {days_to_exp} days remaining - skipping trade")
            return False
        
        # On expiry day, only trade before 2 PM
        if days_to_exp == 0:
            now_time = now.time()
            cutoff_time = dt_time(14, 0)  # 2:00 PM
            if now_time > cutoff_time:
                logger.warning(f"Expiry day after 2 PM - skipping trade")
                return False
        
        return True
    
    def _check_position_limit(self) -> bool:
        """
        Check if position limit has been reached.
        FIX for Issue #7: Position limits check.
        
        Returns:
            True if within limit, False if limit reached
        """
        current_positions = len(self.active_monitors)
        
        if current_positions >= self.max_concurrent_positions:
            logger.warning(
                f"Position limit reached: {current_positions}/{self.max_concurrent_positions} "
                f"- skipping new trade"
            )
            return False
        
        logger.debug(f"Position check passed: {current_positions}/{self.max_concurrent_positions}")
        return True
    
    def _check_daily_loss_limit(self) -> bool:
        """
        Check if daily loss limit has been hit.
        FIX for Issue #8: Daily loss limit circuit breaker.
        
        Returns:
            True if within limit, False if limit hit
        """
        # Reset daily P&L if new day
        today = datetime.now().date()
        if today != self.daily_pnl_date:
            logger.info(f"New trading day - resetting daily P&L (previous: ₹{self.daily_pnl:.2f})")
            self.daily_pnl = 0.0
            self.daily_pnl_date = today
        
        # Get initial capital (from config or use default)
        initial_capital = self.config.get('initial_capital', 100000.0)
        loss_limit_amount = initial_capital * (self.daily_loss_limit_pct / 100.0)
        
        if self.daily_pnl <= -loss_limit_amount:
            logger.error(
                f"Daily loss limit hit: P&L ₹{self.daily_pnl:,.2f} "
                f"exceeds limit ₹{-loss_limit_amount:,.2f} ({self.daily_loss_limit_pct}% of capital)"
            )
            return False
        
        return True
    
    def _update_daily_pnl(self, pnl: float):
        """
        Update daily P&L tracking.
        FIX for Issue #8: Daily loss limit.
        
        Args:
            pnl: Trade P&L to add
        """
        self.daily_pnl += pnl
        logger.info(f"Daily P&L updated: ₹{self.daily_pnl:,.2f}")
    
    def _run_loop(self):
        """
        Main polling loop (runs in background thread).
        """
        logger.info("Live strategy polling loop started")
        
        while self._running and not self._stop_event.is_set():
            try:
                # Run one cycle
                self._run_cycle()
                
                # Wait for next polling interval
                self._stop_event.wait(self.polling_interval)
                
            except Exception as e:
                logger.exception(f"Error in polling loop: {e}")
                self.error_count += 1
                
                # Wait a bit before retrying
                self._stop_event.wait(self.retry_delay)
        
        logger.info("Live strategy polling loop stopped")
    
    def _run_cycle(self):
        """
        Execute one cycle of market monitoring and strategy execution.
        """
        self.cycle_count += 1
        logger.info(f"Running strategy cycle #{self.cycle_count}")
        
        # Fetch latest market data
        try:
            self.market_data.refresh_data()
            self.last_fetch_time = datetime.now()
            
            # Get aggregated dataframes (prefer direct interval fetching with fallback to resampling)
            data_1h = self.market_data.get_1h_data(
                window_hours=self.config.get('market_data', {}).get('data_window_hours_1h', 48),
                use_direct_interval=True  # Try ONE_HOUR interval first
            )
            data_15m = self.market_data.get_15m_data(
                window_hours=self.config.get('market_data', {}).get('data_window_hours_15m', 12),
                use_direct_interval=True  # Try FIFTEEN_MINUTE interval first
            )
            
            # Check if we have sufficient data - ONLY 1H data required now (1H breakouts only)
            if data_1h.empty:
                logger.warning("Insufficient market data - empty 1H dataframe. Skipping cycle. Check API connectivity or wait for market data.")
                return
            
            # Log candle counts for diagnostics
            logger.info(f"1H candles available: {len(data_1h)}, 15m candles available: {len(data_15m) if data_15m is not None and not data_15m.empty else 0} (NOT USED - only 1H breakouts)")
            
            if len(data_1h) < 20:  # Need at least 20 candles for Inside Bar detection AND breakout confirmation
                logger.warning(f"Insufficient 1h data ({len(data_1h)} candles). Need at least 20 for inside bar detection and 1H breakout. Skipping cycle. Data may be too recent or aggregation failed.")
                return
            
            # Note: 15m data is no longer required (only using 1H breakouts)
            # Still fetch it for backward compatibility but don't validate it
            
            logger.info(f"Processing strategy with {len(data_1h)} 1h candles (ONLY 1H breakouts - no 15m breakouts)")
            
            # FIX for Issue #3: Check market hours before processing
            if not self._is_market_open():
                logger.debug("Market closed - skipping signal processing")
                return
            
            # Process signal - only pass 1H data (15m is optional and not used)
            signal = self.signal_handler.process_signal(data_1h, data_15m)
            
            if signal:
                self.last_signal_time = datetime.now()
                logger.info(f"Signal detected: {signal}")
                
                # FIX for Issue #4: Check for duplicate signals
                if self._check_signal_duplicate(signal):
                    logger.warning("Duplicate signal detected - skipping execution")
                    return
                
                # FIX for Issue #8: Check daily loss limit
                if not self._check_daily_loss_limit():
                    logger.error("Daily loss limit hit - stopping trading for today")
                    # Optionally stop the runner
                    # self.stop()
                    return
                
                # FIX for Issue #7: Check position limit
                if not self._check_position_limit():
                    logger.warning("Position limit reached - skipping trade")
                    return
                
                # Execute trade
                self._execute_trade(signal)
            else:
                logger.debug("No signal detected in this cycle")
                
        except Exception as e:
            logger.exception(f"Error in cycle execution: {e}")
            self.error_count += 1
    
    def _execute_trade(self, signal: Dict):
        """
        Execute trade based on signal with all safety checks.
        FIX: Added capital validation, expiry validation, and order execution validation.
        
        Args:
            signal: Signal dictionary from signal_handler
        """
        try:
            logger.info(f"Executing trade for signal: {signal}")
            
            # Extract signal parameters
            direction = signal.get('direction')
            strike = signal.get('strike')
            entry_estimate = signal.get('entry')  # This is placeholder from strategy_engine
            
            if not all([direction, strike]):
                logger.error(f"Invalid signal parameters: {signal}")
                return
            
            # FIX for Issue #6: Get and validate expiry
            expiry = self._get_nearest_expiry()
            if not self._is_safe_to_trade_expiry(expiry):
                logger.warning(f"Expiry validation failed - skipping trade")
                return
            
            # FIX for Issue #2: Fetch actual option price from broker
            expiry_date_str = None
            if expiry:
                # Format expiry date for broker API (DDMMMYY)
                expiry_date_str = expiry.strftime('%d%b%y').upper()
            
            entry_price = self.broker.get_option_price(
                symbol="NIFTY",
                strike=strike,
                direction=direction,
                expiry_date=expiry_date_str
            )
            
            if entry_price is None:
                logger.error(f"Failed to fetch option price for {direction} {strike} - skipping trade")
                return
            
            logger.info(f"Option price fetched: ₹{entry_price:.2f} (estimate was ₹{entry_estimate:.2f})")
            
            # FIX for Issue #5: Check capital before placing order
            order_value = entry_price * self.order_qty * self.lot_size
            if not self._check_capital_sufficient(order_value):
                logger.error(f"Insufficient capital for trade - skipping")
                return
            
            # FIX for Issue #3: Double-check market hours before order placement
            if not self._is_market_open():
                logger.warning("Market closed - skipping order placement")
                return
            
            # Place order via broker (transaction_type defaults to "BUY")
            order_result = self.broker.place_order(
                symbol="NIFTY",
                strike=strike,
                direction=direction,
                quantity=self.order_qty,
                order_type="MARKET",
                transaction_type="BUY"  # Explicitly set BUY for opening positions
            )
            
            # FIX for Issue #9: Validate order execution
            if not order_result.get('status'):
                error_msg = order_result.get('message', 'Unknown error')
                logger.error(f"Order placement failed: {error_msg}")
                
                # Log failed trade attempt
                self.trade_logger.log_trade(
                    timestamp=datetime.now().isoformat(),
                    direction=direction,
                    strike=strike,
                    entry_price=entry_price,
                    quantity=self.order_qty,
                    order_id=None,
                    status="FAILED",
                    reason=f"Order failed: {error_msg}"
                )
                return
            
            order_id = order_result.get('order_id')
            logger.info(f"Order placed successfully: {order_id}")
            
            # FIX for Issue #9: Wait and verify order execution
            import time as sleep_time
            sleep_time.sleep(2)  # Wait 2 seconds for order to be processed
            
            order_status = self.broker.get_order_status(order_id)
            if order_status.get('status') not in ['COMPLETE', 'FILLED', 'OPEN']:
                logger.warning(f"Order status: {order_status.get('status')} - may not be executed yet")
                # Still proceed but log warning
            
            # Mark signal as executed
            self.signal_handler.mark_signal_executed(signal, order_id)
            
            # Get tradingsymbol from order result for PositionMonitor
            tradingsymbol = order_result.get('order_data', {}).get('tradingsymbol')
            if not tradingsymbol:
                # Fallback: generate from parameters
                if expiry_date_str:
                    tradingsymbol = f"NIFTY{expiry_date_str}{strike}{direction}"
            
            # Log trade with actual entry price
            self.trade_logger.log_trade(
                timestamp=datetime.now().isoformat(),
                direction=direction,
                strike=strike,
                entry_price=entry_price,  # Use actual fetched price
                quantity=self.order_qty,
                order_id=order_id,
                status="OPEN",
                reason=signal.get('reason', 'Inside Bar breakout')
            )
            
            logger.info(f"Trade logged: Order {order_id}, {direction} {strike} @ ₹{entry_price:.2f}")

            # Start PositionMonitor for this position
            try:
                symboltoken = order_result.get('symboltoken')
                exchange = order_result.get('exchange', 'NFO')
                pm_cfg = self.config.get('position_management', {})
                rules = PositionRules(
                    sl_points=int(pm_cfg.get('sl_points', 30)),
                    trail_points=int(pm_cfg.get('trail_points', 10)),
                    book1_points=int(pm_cfg.get('book1_points', 40)),
                    book2_points=int(pm_cfg.get('book2_points', 54)),
                    book1_ratio=float(pm_cfg.get('book1_ratio', 0.5)),
                )
                # FIX for Issue #10: Pass symbol info to PositionMonitor
                monitor = PositionMonitor(
                    broker=self.broker,
                    symbol_token=symboltoken,
                    exchange=exchange,
                    entry_price=entry_price,  # Use actual fetched price
                    total_qty=self.order_qty,  # Quantity in lots (PositionMonitor handles per lot)
                    rules=rules,
                    order_id=order_id,
                    symbol="NIFTY",  # FIX: Add symbol info
                    strike=strike,  # FIX: Add strike info
                    direction=direction,  # FIX: Add direction info
                    tradingsymbol=tradingsymbol  # FIX: Add tradingsymbol for order placement
                )
                if monitor.start():
                    self.active_monitors.append(monitor)
                    logger.info(f"Position monitor started for order {order_id}")
                else:
                    logger.error(f"Failed to start PositionMonitor for order {order_id}")
            except Exception as e:
                logger.exception(f"Failed to start PositionMonitor: {e}")
                
        except Exception as e:
            logger.exception(f"Error executing trade: {e}")
            self.error_count += 1
    
    def get_status(self) -> Dict:
        """
        Get current status of the live runner.
        
        Returns:
            Dictionary with status information
        """
        return {
            'running': self._running,
            'cycle_count': self.cycle_count,
            'error_count': self.error_count,
            'last_fetch_time': self.last_fetch_time.isoformat() if self.last_fetch_time else None,
            'last_signal_time': self.last_signal_time.isoformat() if self.last_signal_time else None,
            'polling_interval': self.polling_interval
        }

