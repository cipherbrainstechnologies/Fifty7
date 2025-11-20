"""
Live Strategy Runner for real-time market monitoring and trade execution
"""

import threading
import time
from typing import Dict, Optional, List
from datetime import datetime, timedelta, time as dt_time, timezone as dt_timezone
from pytz import timezone
from logzero import logger
import pandas as pd

from engine.market_data import MarketDataProvider
from engine.signal_handler import SignalHandler, _set_session_state
from engine.db import get_session, init_database
from engine.models import MissedTrade
from engine.tenant_context import resolve_tenant
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
        self.org_id, self.user_id = resolve_tenant(config)
        self.strategy_id = config.get('strategy', {}).get('type', 'inside_bar')
        self.broker_name = config.get('broker', {}).get('type', 'angel')
        broker_cfg = config.get('broker', {})
        self.enable_bracket_orders = broker_cfg.get('enable_bracket_orders', False)
        self.bracket_variety = broker_cfg.get('bracket_variety', 'ROBO')
        self.bracket_product_type = broker_cfg.get('bracket_product_type', 'INTRADAY')
        self.fallback_variety = broker_cfg.get('order_variety', 'NORMAL')
        self.fallback_product_type = broker_cfg.get('product_type', 'INTRADAY')
        
        # Running state
        self._running = False
        self._thread = None
        self._stop_event = threading.Event()
        
        # Configuration from config file
        market_data_config = config.get('market_data', {})
        # --- [Enhancement: Live Inside Bar Lag Fix - 2025-11-06] ---
        # Reduced polling interval from 900s (15 min) to 10s for real-time signal detection
        self.polling_interval = market_data_config.get('polling_interval_seconds', 10)  # 10 seconds default
        self.max_retries = market_data_config.get('max_retries', 3)
        self.retry_delay = market_data_config.get('retry_delay_seconds', 5)
        
        # Strategy config
        strategy_config = config.get('strategy', {})
        self.lot_size = config.get('lot_size', 75)  # NIFTY lot size (1 lot = 75 units)
        
        # Order quantity in LOTS (standardized - not units)
        # broker.default_qty was confusing (could be lots or units), now always LOTS
        default_lots = config.get('broker', {}).get('default_lots', 2)  # Default: 2 lots
        self.order_lots = default_lots  # Always in LOTS
        
        self.sl_points = strategy_config.get('sl', 30)
        self.rr_ratio = strategy_config.get('rr', 1.8)
        
        # Position management config (for trailing SL and profit booking)
        pm_config = config.get('position_management', {})
        self.trail_points = pm_config.get('trail_points', 10)  # Trailing step in points
        
        # Statistics
        self.last_fetch_time = None
        self.last_signal_time = None
        self.cycle_count = 0
        self.error_count = 0
        self.active_monitors = []
        
        # Execution safety flag - must be explicitly armed for real trades
        self.execution_armed = False
        
        # FIX for Issue #4: Duplicate signal prevention
        self.recent_signals = {}  # signal_id -> timestamp
        self.signal_cooldown_seconds = config.get('strategy', {}).get('signal_cooldown_seconds', 3600)  # 1 hour default
        
        # FIX for Issue #8: Daily loss limit
        self.daily_loss_limit_pct = config.get('risk_management', {}).get('daily_loss_limit_pct', 5.0)  # 5% default
        self.daily_pnl = 0.0  # Track daily P&L
        self.daily_pnl_date = datetime.now().date()  # Track which day we're on
        self._orders_to_signals: Dict[str, Dict] = {}
        
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
    
    def update_strategy_config(
        self,
        sl_points: Optional[int] = None,
        order_lots: Optional[int] = None,
        trail_points: Optional[int] = None,
        atm_offset: Optional[int] = None,
        daily_loss_limit_pct: Optional[float] = None,
        lot_size: Optional[int] = None,
    ):
        """
        Update strategy configuration at runtime (from front-end).
        
        Args:
            sl_points: New stop loss in points (optional)
            order_lots: New order quantity in LOTS (optional)
            trail_points: New trailing SL step in points (optional)
            atm_offset: Offset from ATM strike in points (optional)
            daily_loss_limit_pct: Daily loss circuit breaker percentage (optional)
        """
        if sl_points is not None:
            if sl_points > 0:
                self.sl_points = sl_points
                self.config.setdefault('strategy', {})['sl'] = sl_points
                if self.signal_handler is not None:
                    self.signal_handler.config.setdefault('strategy', {})['sl'] = sl_points
                logger.info(f"Stop Loss updated to {sl_points} points")
            else:
                logger.warning(f"Invalid stop loss: {sl_points} (must be > 0)")
        
        if order_lots is not None:
            if order_lots > 0:
                self.order_lots = order_lots
                logger.info(f"Order quantity updated to {order_lots} lot(s) ({order_lots * self.lot_size} units)")
            else:
                logger.warning(f"Invalid order lots: {order_lots} (must be > 0)")
        
        if trail_points is not None:
            if trail_points > 0:
                self.trail_points = trail_points
                # Also update config for PositionMonitor
                if 'position_management' not in self.config:
                    self.config['position_management'] = {}
                self.config['position_management']['trail_points'] = trail_points
                logger.info(f"Trailing SL step updated to {trail_points} points")
            else:
                logger.warning(f"Invalid trail points: {trail_points} (must be > 0)")
        
        if atm_offset is not None:
            self.config.setdefault('strategy', {})['atm_offset'] = int(atm_offset)
            if hasattr(self, 'signal_handler') and self.signal_handler is not None:
                self.signal_handler.config.setdefault('strategy', {})['atm_offset'] = int(atm_offset)
            logger.info(f"Strike offset updated to {int(atm_offset)} points")
        
        if daily_loss_limit_pct is not None:
            if daily_loss_limit_pct > 0:
                self.daily_loss_limit_pct = float(daily_loss_limit_pct)
                self.config.setdefault('risk_management', {})['daily_loss_limit_pct'] = float(daily_loss_limit_pct)
                logger.info(f"Daily loss limit updated to {float(daily_loss_limit_pct)}%")
            else:
                logger.warning(f"Invalid daily loss limit: {daily_loss_limit_pct} (must be > 0)")

        if lot_size is not None:
            if lot_size > 0:
                self.lot_size = lot_size
                self.config['lot_size'] = lot_size
                logger.info(f"Lot size updated to {lot_size} contracts")
            else:
                logger.warning(f"Invalid lot size: {lot_size} (must be > 0)")
    
    def _display_strategy_summary(self, signal: Dict, entry_price: float, strike: int, direction: str):
        """
        Display strategy summary before trade execution.
        
        Args:
            signal: Signal dictionary
            entry_price: Actual option premium
            strike: Strike price
            direction: 'CE' or 'PE'
        """
        # Calculate values
        total_units = self.order_lots * self.lot_size
        order_value = entry_price * total_units
        sl_price = entry_price - self.sl_points
        tp_partial = entry_price + signal.get('tp', entry_price + (self.sl_points * self.rr_ratio)) - entry_price
        tp_full = tp_partial * (signal.get('tp', entry_price + (self.sl_points * self.rr_ratio)) - entry_price) / tp_partial if tp_partial > 0 else entry_price + (self.sl_points * self.rr_ratio)
        
        # Get position management targets
        pm_cfg = self.config.get('position_management', {})
        book1_points = pm_cfg.get('book1_points', 40)
        book2_points = pm_cfg.get('book2_points', 54)
        book1_ratio = pm_cfg.get('book1_ratio', 0.5)
        
        logger.info("=" * 80)
        logger.info("📊 STRATEGY SUMMARY - BEFORE EXECUTION")
        logger.info("=" * 80)
        logger.info(f"📈 Direction: {direction} ({'Call Option' if direction == 'CE' else 'Put Option'})")
        logger.info(f"🎯 Strike: {strike}")
        logger.info(f"💰 Entry Price: ₹{entry_price:.2f} per unit")
        logger.info(f"📦 Quantity: {self.order_lots} lot(s) = {total_units} units")
        logger.info(f"💵 Order Value: ₹{order_value:,.2f} (Premium × Units)")
        logger.info("")
        logger.info("🛡️ Risk Management:")
        logger.info(f"  - Stop Loss: {self.sl_points} points → ₹{sl_price:.2f} per unit")
        logger.info(f"  - Max Loss: ₹{(entry_price - sl_price) * total_units:,.2f} ({((entry_price - sl_price) / entry_price * 100):.1f}%)")
        logger.info("")
        logger.info("🎯 Profit Targets:")
        logger.info(f"  - Level 1 (Partial {book1_ratio*100:.0f}%): +{book1_points} points → ₹{entry_price + book1_points:.2f}")
        logger.info(f"  - Level 2 (Remaining): +{book2_points} points → ₹{entry_price + book2_points:.2f}")
        logger.info(f"  - Max Profit: ₹{(book2_points) * total_units:,.2f} ({((book2_points) / entry_price * 100):.1f}%)")
        logger.info("")
        logger.info(f"📊 Risk-Reward Ratio: 1:{self.rr_ratio:.1f}")
        logger.info(f"📝 Signal Reason: {signal.get('reason', 'Inside Bar 1H breakout')}")
        logger.info("=" * 80)
    
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
            
            # --- [Enhancement: Live Inside Bar Lag Fix - 2025-11-06] ---
            # Pass include_latest=True to get current incomplete candle for real-time detection
            # Get aggregated dataframes (prefer direct interval fetching with fallback to resampling)
            market_data_cfg = self.config.get('market_data', {})
            window_hours_1h = market_data_cfg.get('data_window_hours_1h', 48)
            min_1h_candles = market_data_cfg.get('min_1h_candles', self.config.get('strategy', {}).get('min_1h_candles', 20))
            data_1h = self.market_data.get_1h_data(
                window_hours=window_hours_1h,
                use_direct_interval=True,  # Try ONE_HOUR interval first
                include_latest=True  # Include incomplete latest candle for live mode
            )
            data_15m = self.market_data.get_15m_data(
                window_hours=market_data_cfg.get('data_window_hours_15m', 12),
                use_direct_interval=True,  # Try FIFTEEN_MINUTE interval first
                include_latest=True  # Include incomplete latest candle for live mode
            )
            
            # --- [Enhancement: Fix 1H Inside Bar Live Lag + NSE Candle Alignment - 2025-11-06] ---
            # Confirm a 1H candle close has occurred before running detection
            # This ensures we only detect breakouts at actual candle close times (NSE-aligned)
            try:
                last_closed_hour_end = self.market_data.get_last_closed_hour_end()
                logger.debug(f"Last closed 1H candle end time (NSE-aligned): {last_closed_hour_end}")
                
                # Check if we have a candle at or before this close time in data_1h
                if not data_1h.empty:
                    latest_candle_time = data_1h['Date'].iloc[-1]
                    # Make timezone-aware for comparison if needed
                    if hasattr(latest_candle_time, 'tz_localize') and latest_candle_time.tzinfo is None:
                        import pytz
                        ist = pytz.timezone('Asia/Kolkata')
                        latest_candle_time = latest_candle_time.tz_localize(ist)
                    
                    # Only proceed if latest candle is at or before last closed hour
                    if latest_candle_time <= last_closed_hour_end:
                        logger.info(f"✅ Candle close confirmed: Latest candle {latest_candle_time} <= Last closed {last_closed_hour_end}")
                    else:
                        logger.debug(f"⏳ Waiting for candle close: Latest candle {latest_candle_time} > Last closed {last_closed_hour_end}")
                        # Don't skip - still process with available data
            except Exception as e:
                logger.warning(f"Failed to confirm candle close: {e}")
                # Continue with existing logic
            
            # Merge live candle snapshot before inside bar detection to ensure no delay
            # Fetch current OHLC snapshot and update the latest candle in data_1h
            try:
                ohlc_snapshot = self.market_data.fetch_ohlc(mode="OHLC")
                if ohlc_snapshot and not data_1h.empty:
                    current_time = datetime.now()
                    # Round down to nearest hour for 1H timeframe
                    rounded_1h = current_time.replace(minute=0, second=0, microsecond=0)
                    
                    # Check if latest candle in data_1h matches current hour
                    latest_candle_time = data_1h['Date'].iloc[-1]
                    if hasattr(latest_candle_time, 'replace'):
                        # If latest candle is for current hour, update it with live snapshot
                        if latest_candle_time.replace(minute=0, second=0, microsecond=0) == rounded_1h:
                            # Update latest candle with live OHLC data
                            data_1h.loc[data_1h.index[-1], 'High'] = max(
                                data_1h.loc[data_1h.index[-1], 'High'],
                                ohlc_snapshot.get('high', data_1h.loc[data_1h.index[-1], 'High'])
                            )
                            data_1h.loc[data_1h.index[-1], 'Low'] = min(
                                data_1h.loc[data_1h.index[-1], 'Low'],
                                ohlc_snapshot.get('low', data_1h.loc[data_1h.index[-1], 'Low'])
                            )
                            data_1h.loc[data_1h.index[-1], 'Close'] = ohlc_snapshot.get('ltp', ohlc_snapshot.get('close', data_1h.loc[data_1h.index[-1], 'Close']))
                            if 'Volume' in data_1h.columns:
                                data_1h.loc[data_1h.index[-1], 'Volume'] = ohlc_snapshot.get('tradeVolume', data_1h.loc[data_1h.index[-1], 'Volume'])
                            logger.debug(f"Merged live OHLC snapshot into latest 1H candle: H={data_1h.loc[data_1h.index[-1], 'High']:.2f}, L={data_1h.loc[data_1h.index[-1], 'Low']:.2f}, C={data_1h.loc[data_1h.index[-1], 'Close']:.2f}")
                        else:
                            # New candle period started, create new row
                            new_row = pd.DataFrame([{
                                'Date': rounded_1h,
                                'Open': ohlc_snapshot.get('open', ohlc_snapshot.get('ltp', 0)),
                                'High': ohlc_snapshot.get('high', ohlc_snapshot.get('ltp', 0)),
                                'Low': ohlc_snapshot.get('low', ohlc_snapshot.get('ltp', 0)),
                                'Close': ohlc_snapshot.get('ltp', ohlc_snapshot.get('close', 0)),
                                'Volume': ohlc_snapshot.get('tradeVolume', 0)
                            }])
                            data_1h = pd.concat([data_1h, new_row], ignore_index=True)
                            data_1h = data_1h.sort_values('Date').reset_index(drop=True)
                            logger.debug(f"Added new 1H candle from live snapshot: {rounded_1h}")
            except Exception as e:
                logger.warning(f"Failed to merge live candle snapshot: {e}")
                # Continue with existing data if merge fails
            
            # Check if we have sufficient data - ONLY 1H data required now (1H breakouts only)
            if data_1h.empty:
                logger.warning("Insufficient market data - empty 1H dataframe. Skipping cycle. Check API connectivity or wait for market data.")
                return
            
            # Log candle counts for diagnostics
            logger.info(f"1H candles available: {len(data_1h)}, 15m candles available: {len(data_15m) if data_15m is not None and not data_15m.empty else 0} (NOT USED - only 1H breakouts)")
            
            if len(data_1h) < min_1h_candles:  # Need sufficient 1H candles for detection + breakout
                extended_window = max(window_hours_1h * 2, min_1h_candles * 3)
                if extended_window > window_hours_1h:
                    logger.warning(
                        "Insufficient 1h data (%s candles, need at least %s). "
                        "Attempting backfill with an extended %s-hour window.",
                        len(data_1h),
                        min_1h_candles,
                        extended_window,
                    )
                    data_1h = self.market_data.get_1h_data(
                        window_hours=extended_window,
                        use_direct_interval=True,
                        include_latest=True,
                    )
                    if len(data_1h) >= min_1h_candles:
                        # Persist new window size for subsequent cycles
                        self.config.setdefault('market_data', {})['data_window_hours_1h'] = extended_window
                        window_hours_1h = extended_window
                    else:
                        logger.warning(
                            "Still insufficient 1h data after extended backfill (%s candles). "
                            "Skipping cycle and waiting for more market data.",
                            len(data_1h),
                        )
                        return
                else:
                    logger.warning(
                        "Insufficient 1h data (%s candles). Need at least %s for inside bar detection. "
                        "Skipping cycle. Data may be too recent or aggregation failed.",
                        len(data_1h),
                        min_1h_candles,
                    )
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
            # Check if execution is armed (from UI or programmatically)
            # This is a CRITICAL safety check
            execution_armed = getattr(self, 'execution_armed', False)
            if not execution_armed:
                logger.error(
                    f"\n{'🛑'*40}\n"
                    f"🚫 TRADE BLOCKED: EXECUTION NOT ARMED\n"
                    f"   Signal: {signal.get('direction')} {signal.get('strike')}\n"
                    f"   ➡️ To enable: Click 'Arm Execution' button in dashboard\n"
                    f"   This is a SAFETY mechanism to prevent accidental live trades\n"
                    f"{'🛑'*40}"
                )
                return
            
            logger.info(f"✅ Execution is ARMED - proceeding with trade for signal: {signal}")
            
            # Extract signal parameters
            direction = signal.get('direction')
            strike = signal.get('strike')
            entry_estimate = signal.get('entry')  # This is placeholder from strategy_engine
            
            if not all([direction, strike]):
                logger.error(f"Invalid signal parameters: {signal}")
                return

            symbol = signal.get('symbol') or self.config.get('market_data', {}).get('nifty_symbol', 'NIFTY')
            
            # FIX for Issue #6: Get and validate expiry
            expiry = self._get_nearest_expiry()
            if not self._is_safe_to_trade_expiry(expiry):
                logger.warning("Expiry validation failed - skipping trade")
                self._record_execution_skip(signal, entry_estimate, "Expiry validation failed")
                return
            
            # FIX for Issue #2: Fetch actual option price from broker
            expiry_date_str = None
            if expiry:
                # Format expiry date for broker API (DDMMMYY)
                expiry_date_str = expiry.strftime('%d%b%y').upper()
            
            entry_price = self.broker.get_option_price(
                symbol=symbol,
                strike=strike,
                direction=direction,
                expiry_date=expiry_date_str
            )
            
            if entry_price is None:
                logger.error(f"Failed to fetch option price for {direction} {strike} - skipping trade")
                return
            
            logger.info(f"Option price fetched: ₹{entry_price:.2f} (estimate was ₹{entry_estimate:.2f})")
            signal['entry'] = entry_price
            # Recompute SL/TP based on actual entry for downstream consumers
            signal['sl'] = entry_price - self.sl_points
            signal['tp'] = entry_price + (self.sl_points * self.rr_ratio)

            stoploss_points = max(entry_price - signal['sl'], 0)
            squareoff_points = max(signal['tp'] - entry_price, 0)
            trailing_points = self.trail_points if self.enable_bracket_orders else None

            order_kwargs = {}
            if self.enable_bracket_orders:
                order_kwargs.update({
                    "squareoff_points": squareoff_points,
                    "stoploss_points": stoploss_points or self.sl_points,
                    "trailing_points": trailing_points,
                    "variety": self.bracket_variety,
                    "product_type": self.bracket_product_type,
                })
            else:
                order_kwargs.update({
                    "variety": self.fallback_variety,
                    "product_type": self.fallback_product_type,
                })
            
            # Display strategy summary before execution
            self._display_strategy_summary(signal, entry_price, strike, direction)
            
            # FIX for Issue #5: Check capital before placing order
            # Calculate order value: entry_price × lots × lot_size (units per lot)
            order_value = entry_price * self.order_lots * self.lot_size
            if not self._check_capital_sufficient(order_value):
                logger.error(f"Insufficient capital for trade - skipping")
                return
            
            # FIX for Issue #3: Double-check market hours before order placement
            if not self._is_market_open():
                logger.warning("Market closed - skipping order placement")
                return
            
            # Place order via broker (transaction_type defaults to "BUY")
            # Pass quantity in LOTS (broker will multiply by lot_size internally if needed)
            order_result = self.broker.place_order(
                symbol=symbol,
                strike=strike,
                direction=direction,
                quantity=self.order_lots,  # In LOTS (1 lot = 75 units)
                order_type="MARKET",
                transaction_type="BUY",  # Explicitly set BUY for opening positions
                **order_kwargs,
            )
            
            # FIX for Issue #9: Validate order execution
            if not order_result.get('status'):
                error_msg = order_result.get('message', 'Unknown error')
                logger.error(f"Order placement failed: {error_msg}")
                
                # Log failed trade attempt
                self.trade_logger.log_trade({
                    'timestamp': datetime.now().isoformat(),
                    'symbol': symbol,
                    'strike': strike,
                    'direction': direction,
                    'order_id': '',
                    'entry': entry_price,
                    'sl': signal.get('sl'),
                    'tp': signal.get('tp'),
                    'status': 'failed',
                    'pre_reason': f"Order failed: {error_msg}",
                    'quantity': self.order_lots,
                    'org_id': self.org_id,
                    'user_id': self.user_id,
                    'broker': self.broker_name,
                    'strategy_id': self.strategy_id,
                    'side': 'BUY',
                })
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
            signal['executed_qty_lots'] = self.order_lots
            signal['lot_size'] = self.lot_size
            self.signal_handler.mark_signal_executed(signal, order_id)
            self._orders_to_signals[order_id] = signal
            
            # Get tradingsymbol from order result for PositionMonitor
            tradingsymbol = order_result.get('order_data', {}).get('tradingsymbol')
            if not tradingsymbol:
                # Fallback: generate from parameters
                if expiry_date_str:
                    tradingsymbol = f"{symbol}{expiry_date_str}{strike}{direction}"
            
            # Log trade with actual entry price
            self.trade_logger.log_trade({
                'timestamp': datetime.now().isoformat(),
                'symbol': symbol,
                'strike': strike,
                'direction': direction,
                'order_id': order_id,
                'entry': entry_price,  # Actual entry price
                'sl': signal.get('sl'),
                'tp': signal.get('tp'),
                'status': 'open',
                'pre_reason': signal.get('reason', 'Inside Bar breakout'),
                'quantity': self.order_lots,
                'org_id': self.org_id,
                'user_id': self.user_id,
                'broker': self.broker_name,
                'strategy_id': self.strategy_id,
                'side': 'BUY',
            })
            
            logger.info(
                f"Trade logged: Order {order_id}, {direction} {strike} @ ₹{entry_price:.2f}, "
                f"{self.order_lots} lot(s) ({self.order_lots * self.lot_size} units)"
            )
            _set_session_state('pending_trade_signal', None)

            # Start PositionMonitor for this position
            try:
                symboltoken = order_result.get('symboltoken')
                exchange = order_result.get('exchange', 'NFO')
                pm_cfg = self.config.get('position_management', {})
                # Use self.trail_points if available (from UI update), otherwise use config
                trail_pts = self.trail_points if hasattr(self, 'trail_points') else pm_cfg.get('trail_points', 10)
                rules = PositionRules(
                    sl_points=int(pm_cfg.get('sl_points', self.sl_points)),  # Use self.sl_points if updated from UI
                    trail_points=int(trail_pts),  # Use configured trail_points
                    book1_points=int(pm_cfg.get('book1_points', 40)),
                    book2_points=int(pm_cfg.get('book2_points', 54)),
                    book1_ratio=float(pm_cfg.get('book1_ratio', 0.5)),
                )
                # FIX for Issue #10: Pass symbol info to PositionMonitor
                # PositionMonitor expects quantity in LOTS (it will handle lot conversions internally)
                monitor = PositionMonitor(
                    broker=self.broker,
                    symbol_token=symboltoken,
                    exchange=exchange,
                    entry_price=entry_price,  # Use actual fetched price
                    total_qty=self.order_lots,  # Quantity in LOTS (1 lot = 75 units)
                    rules=rules,
                    order_id=order_id,
                    symbol=symbol,  # FIX: Add symbol info
                    strike=strike,  # FIX: Add strike info
                    direction=direction,  # FIX: Add direction info
                    tradingsymbol=tradingsymbol,  # FIX: Add tradingsymbol for order placement
                    lot_size=self.lot_size,
                    pnl_callback=self._handle_position_update,
                    broker_managed=self.enable_bracket_orders,
                    bracket_stop_points=stoploss_points if self.enable_bracket_orders else None,
                    bracket_target_points=squareoff_points if self.enable_bracket_orders else None,
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
    
    def _coerce_datetime(self, value):
        if value is None:
            return None
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=dt_timezone.utc)
            return value.astimezone(dt_timezone.utc)
        try:
            ts = pd.to_datetime(value)
            if isinstance(ts, pd.Timestamp):
                if ts.tzinfo is None:
                    ts = ts.tz_localize("UTC")
                else:
                    ts = ts.tz_convert("UTC")
                return ts.to_pydatetime()
        except Exception:
            return None
        return None

    def _record_execution_skip(self, signal: Dict, entry_price: Optional[float], reason: str) -> None:
        if MissedTrade is None or get_session is None:
            return
        try:
            init_database(create_all=True)
        except Exception:
            pass
        sess_gen = get_session()
        db = next(sess_gen)
        try:
            row = MissedTrade(
                org_id=str(self.org_id),
                user_id=str(self.user_id),
                direction=str(signal.get('direction', '')).upper(),
                strike=signal.get('strike'),
                entry_price=entry_price,
                sl_price=signal.get('sl'),
                tp_price=signal.get('tp'),
                range_high=signal.get('range_high'),
                range_low=signal.get('range_low'),
                inside_bar_time=self._coerce_datetime(signal.get('inside_bar_time')),
                signal_time=self._coerce_datetime(signal.get('signal_time')),
                breakout_close=entry_price,
                reason=reason,
            )
            db.add(row)
            db.commit()
        except Exception:
            db.rollback()
        finally:
            try:
                next(sess_gen)
            except StopIteration:
                pass

    def _handle_position_update(self, update: Dict):
        """
        Receive position updates from PositionMonitor and update P&L / trade state.
        """
        if not isinstance(update, dict):
            return

        logger.info(f"Position update received: {update}")

        pnl_value = update.get('pnl')
        if pnl_value is not None:
            self._update_daily_pnl(pnl_value)

        order_id = update.get('order_id')
        if not order_id:
            return

        remaining_lots = update.get('remaining_qty_lots')
        exit_price = update.get('exit_price')
        total_pnl = update.get('total_pnl')
        reason = update.get('reason') or update.get('event') or 'exit'

        if remaining_lots == 0:
            # Update trade journal with exit info
            tracked_signal = self._orders_to_signals.get(order_id)
            executed_lots = self.order_lots
            lot_size = self.lot_size
            if tracked_signal:
                executed_lots = tracked_signal.get('executed_qty_lots', executed_lots)
                lot_size = tracked_signal.get('lot_size', lot_size)

            if exit_price is not None and total_pnl is not None:
                try:
                    metadata = {
                        'org_id': self.org_id,
                        'user_id': self.user_id,
                        'strategy_id': self.strategy_id,
                        'broker': self.broker_name,
                        'lot_size': lot_size,
                        'quantity': executed_lots,
                        'exit_timestamp': update.get('timestamp'),
                    }
                    self.trade_logger.update_trade_exit(
                        order_id,
                        exit_price,
                        total_pnl,
                        reason,
                        metadata=metadata,
                    )
                except Exception as log_error:
                    logger.exception(f"Failed to update trade log for order {order_id}: {log_error}")

            # Mark signal closed if we tracked one for this order
            signal = self._orders_to_signals.pop(order_id, tracked_signal)
            if signal and exit_price is not None and total_pnl is not None:
                try:
                    self.signal_handler.mark_signal_closed(signal, exit_price, total_pnl)
                except Exception as signal_error:
                    logger.exception(f"Failed to mark signal closed for order {order_id}: {signal_error}")

            # Stop and remove the monitor associated with this order
            monitor = next((m for m in self.active_monitors if getattr(m, 'order_id', None) == order_id), None)
            if monitor:
                try:
                    monitor.stop()
                except Exception as stop_error:
                    logger.exception(f"Error stopping monitor for order {order_id}: {stop_error}")
                finally:
                    self.active_monitors = [
                        m for m in self.active_monitors if getattr(m, 'order_id', None) != order_id
                    ]

            # Re-evaluate daily loss limit post exit
            if not self._check_daily_loss_limit():
                logger.error("Daily loss limit breached after position update")
    
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

