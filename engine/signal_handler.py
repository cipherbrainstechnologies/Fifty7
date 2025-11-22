"""
Signal Handler for processing and validating trading signals
"""

import pandas as pd
from typing import Optional, Dict, List
from datetime import datetime, timezone
from engine.inside_bar_breakout_strategy import (
    detect_inside_bar,
    confirm_breakout_on_hour_close,
    calculate_strike_price,
    calculate_sl_tp_levels,
    get_active_signal
)
from engine.tenant_context import resolve_tenant
from engine.state_store import get_state_store
from engine.event_bus import get_event_bus
from logzero import logger

try:
    from engine.db import get_session, init_database
    from engine.models import MissedTrade
    MISSED_DB_AVAILABLE = True
except Exception:
    get_session = None
    init_database = None
    MissedTrade = None
    MISSED_DB_AVAILABLE = False


def _set_session_state(key: str, value):
    try:
        import streamlit as st  # type: ignore
    except Exception:
        return
    st.session_state[key] = value


def _format_ts(value):
    if value is None:
        return None
    try:
        return value.strftime("%Y-%m-%d %H:%M:%S IST")
    except Exception:
        return str(value)


class SignalHandler:
    """
    Handles signal processing, validation, and trade signal generation.
    """
    
    def __init__(self, config: Dict):
        """
        Initialize SignalHandler with configuration.
        
        Args:
            config: Configuration dictionary with strategy parameters
        """
        self.config = config
        self.active_signals = []
        self.signal_history = []
        self._active_signal_state = None  # Track active signal for new strategy
        self.org_id, self.user_id = resolve_tenant(config)
        
        # State Store integration
        self.state_store = get_state_store()
        self.event_bus = get_event_bus()
        
        # Restore signal state if available
        self._restore_signal_state()
    
    def _restore_signal_state(self):
        """Restore signal state from StateStore."""
        try:
            restored_signal = self.state_store.get_state('trading.active_signal')
            if restored_signal:
                self._active_signal_state = restored_signal
                logger.info("Restored active signal state from StateStore")
        except Exception as e:
            logger.warning(f"Failed to restore signal state: {e}")
    
    def validate_signal(self, signal: Dict) -> bool:
        """
        Validate generated signal against filters and rules.
        
        Args:
            signal: Signal dictionary from strategy_engine
        
        Returns:
            True if signal is valid, False otherwise
        """
        if signal is None:
            return False
        
        filters = self.config.get('strategy', {}).get('filters', {})
        
        # Check volume spike filter
        if filters.get('volume_spike', False):
            # Volume validation should be done in strategy_engine
            # Additional validation can be added here
            pass
        
        # Check open range avoidance filter
        if filters.get('avoid_open_range', False):
            current_hour = datetime.now().hour
            current_minute = datetime.now().minute
            # Avoid trading in first 30 minutes (9:00-9:30 IST)
            if current_hour == 9 and current_minute < 30:
                return False
        
        # Validate signal structure
        required_fields = ['direction', 'strike', 'entry', 'sl', 'tp']
        for field in required_fields:
            if field not in signal:
                return False
        
        # Validate direction
        if signal['direction'] not in ['CE', 'PE']:
            return False
        
        # Validate price levels
        if signal['sl'] >= signal['entry'] or signal['tp'] <= signal['entry']:
            return False
        
        return True
    
    def process_signal(
        self,
        data_1h: pd.DataFrame,
        data_15m: Optional[pd.DataFrame] = None  # Optional - kept for backward compatibility but not used
    ) -> Optional[Dict]:
        """
        Process market data and generate validated signal using refactored Inside Bar strategy.
        
        IMPORTANT: Now uses the production-grade inside_bar_breakout_strategy module
        which has improved signal management and breakout detection.
        
        Args:
            data_1h: 1-hour OHLCV data (REQUIRED - used for both inside bar and breakout)
            data_15m: 15-minute OHLCV data (OPTIONAL - kept for backward compatibility, NOT USED)
        
        Returns:
            Validated signal dictionary or None
        """
        # Get strategy configuration
        sl_points = self.config.get('strategy', {}).get('sl', 30)
        rr_ratio = self.config.get('strategy', {}).get('rr', 1.8)
        atm_offset = self.config.get('strategy', {}).get('atm_offset', 0)
        symbol_name = self.config.get('market_data', {}).get('nifty_symbol', 'NIFTY')
        
        # Validate data sufficiency
        if data_1h.empty or len(data_1h) < 20:
            return None
        
        # Get or update active signal using new strategy
        active_signal = get_active_signal(
            candles=data_1h,
            previous_signal=self._active_signal_state,
            mark_signal_invalid=False,
            exclude_before_time=None
        )
        
        if active_signal is None:
            # No active signal
            self._active_signal_state = None
            _set_session_state('last_breakout_direction', None)
            return None
        
        # Update internal signal state
        self._active_signal_state = active_signal
        
        # Update state store
        self.state_store.update_state(
            'trading.active_signal',
            active_signal,
            metadata={'source': 'signal_handler', 'timestamp': datetime.now(timezone.utc).isoformat()}
        )
        
        # Check for breakout using the new strategy
        breakout_direction, latest_closed_candle, is_missed_trade = confirm_breakout_on_hour_close(
            candles=data_1h,
            signal=active_signal,
            current_time=None,  # Will use current time
            check_missed_trade=True
        )
        
        if breakout_direction is None:
            # No breakout yet - signal is still active but not triggered
            return None

        current_price = data_1h['Close'].iloc[-1]
        entry_price_est = (
            latest_closed_candle['Close']
            if latest_closed_candle is not None
            else current_price
        )

        # Handle missed trade - invalidate signal and wait for new one
        if is_missed_trade:
            logger.warning("Missed trade detected - invalidating signal")
            self._active_signal_state = None
            _set_session_state('last_breakout_direction', None)
            latest_close = latest_closed_candle['Close'] if latest_closed_candle is not None else current_price
            missed_strike = calculate_strike_price(latest_close, breakout_direction, atm_offset)
            missed_stop_loss, missed_take_profit = calculate_sl_tp_levels(
                latest_close,
                sl_points,
                rr_ratio
            )
            self._record_missed_trade(
                direction=breakout_direction,
                strike=missed_strike,
                entry=latest_close,
                sl=missed_stop_loss,
                tp=missed_take_profit,
                range_high=active_signal['range_high'],
                range_low=active_signal['range_low'],
                inside_bar_time=active_signal['inside_bar_time'],
                signal_time=active_signal['signal_time'],
                reason="Breakout window expired"
            )
            _set_session_state(
                'last_missed_trade',
                {
                    'direction': breakout_direction,
                    'range_high': active_signal['range_high'],
                    'range_low': active_signal['range_low'],
                    'inside_bar_time': _format_ts(active_signal['inside_bar_time']),
                    'signal_time': _format_ts(active_signal['signal_time']),
                    'timestamp': datetime.now().isoformat(),
                    'strike': missed_strike,
                    'close_price': latest_close,
                }
            )
            _set_session_state('pending_trade_signal', None)
            return None
        
        # Breakout confirmed - generate trade signal
        strike = calculate_strike_price(current_price, breakout_direction, atm_offset)
        
        # Use actual close price from breakout candle as entry estimate
        entry_price = entry_price_est
        
        # Calculate SL and TP
        stop_loss, take_profit = calculate_sl_tp_levels(
            entry_price,
            sl_points,
            rr_ratio
        )
        
        signal = {
            'direction': breakout_direction,
            'strike': strike,
            'entry': entry_price,
            'sl': stop_loss,
            'tp': take_profit,
            'range_high': active_signal['range_high'],
            'range_low': active_signal['range_low'],
            'reason': f"Inside Bar 1H breakout on {breakout_direction} side",
            'inside_bar_time': active_signal['inside_bar_time'],
            'signal_time': active_signal['signal_time'],
            'symbol': symbol_name,
        }
        
        # Validate signal
        if not self.validate_signal(signal):
            return None
        
        # Add timestamp and status
        signal['timestamp'] = datetime.now().isoformat()
        signal['status'] = 'pending'
        
        # Store in history
        self.signal_history.append(signal)
        
        # Invalidate signal after breakout attempt (signal consumed)
        self._active_signal_state = None
        
        # Update state store - clear active signal
        self.state_store.update_state(
            'trading.active_signal',
            None,
            metadata={'source': 'signal_handler', 'action': 'signal_consumed'}
        )
        
        # Update state store - add to signal history
        signal_history = self.state_store.get_state('trading.signal_history') or []
        signal_history.append(signal)
        # Keep only recent signals (last 100)
        if len(signal_history) > 100:
            signal_history = signal_history[-100:]
        self.state_store.update_state(
            'trading.signal_history',
            signal_history,
            metadata={'source': 'signal_handler', 'action': 'signal_generated'}
        )
        
        _set_session_state('last_breakout_direction', breakout_direction)
        _set_session_state('last_missed_trade', None)
        ui_signal = signal.copy()
        ui_signal['inside_bar_time'] = _format_ts(active_signal['inside_bar_time'])
        ui_signal['signal_time'] = _format_ts(active_signal['signal_time'])
        _set_session_state('pending_trade_signal', ui_signal)
        
        return signal

    def _coerce_datetime(self, value) -> Optional[datetime]:
        if value is None:
            return None
        try:
            ts = pd.to_datetime(value)
            if isinstance(ts, pd.Timestamp):
                if ts.tzinfo is None:
                    ts = ts.tz_localize("UTC")
                else:
                    ts = ts.tz_convert("UTC")
                return ts.to_pydatetime()
            if isinstance(value, datetime):
                if value.tzinfo is None:
                    return value.replace(tzinfo=timezone.utc)
                return value.astimezone(timezone.utc)
        except Exception:
            return None
        return None

    def _record_missed_trade(self, **kwargs) -> None:
        if not MISSED_DB_AVAILABLE or MissedTrade is None or get_session is None:
            return
        try:
            init_database(create_all=True)
        except Exception:
            pass

        entry = kwargs.get('entry')
        sl_price = kwargs.get('sl')
        tp_price = kwargs.get('tp')

        inside_bar_time = self._coerce_datetime(kwargs.get('inside_bar_time'))
        signal_time = self._coerce_datetime(kwargs.get('signal_time'))

        sess_gen = get_session()
        db = next(sess_gen)
        try:
            row = MissedTrade(
                org_id=str(self.org_id),
                user_id=str(self.user_id),
                direction=str(kwargs.get('direction', '')).upper(),
                strike=kwargs.get('strike'),
                entry_price=entry,
                sl_price=sl_price,
                tp_price=tp_price,
                range_high=kwargs.get('range_high'),
                range_low=kwargs.get('range_low'),
                inside_bar_time=inside_bar_time,
                signal_time=signal_time,
                breakout_close=entry,
                reason=kwargs.get('reason'),
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
    
    def get_active_signals(self) -> List[Dict]:
        """
        Get list of active trading signals.
        
        Returns:
            List of active signal dictionaries
        """
        return [s for s in self.active_signals if s.get('status') == 'active']
    
    def mark_signal_executed(self, signal: Dict, order_id: str):
        """
        Mark signal as executed with order ID.
        
        Args:
            signal: Signal dictionary
            order_id: Broker order ID
        """
        signal['status'] = 'executed'
        signal['order_id'] = order_id
        signal['executed_at'] = datetime.now(timezone.utc).isoformat()
        
        if signal not in self.active_signals:
            self.active_signals.append(signal)
    
    def mark_signal_closed(self, signal: Dict, exit_price: float, pnl: float):
        """
        Mark signal as closed with exit details.
        
        Args:
            signal: Signal dictionary
            exit_price: Exit price
            pnl: Profit/Loss amount
        """
        signal['status'] = 'closed'
        signal['exit_price'] = exit_price
        signal['pnl'] = pnl
        signal['closed_at'] = datetime.now(timezone.utc).isoformat()
        
        # Update state store
        order_id = signal.get('order_id')
        if order_id:
            self.state_store.update_state(
                f'trading.signals.{order_id}',
                signal,
                metadata={'source': 'signal_handler', 'action': 'signal_closed'}
            )
        signal['pnl'] = pnl
        signal['closed_at'] = datetime.now(timezone.utc).isoformat()
        
        # Update state store
        order_id = signal.get('order_id')
        if order_id:
            self.state_store.update_state(
                f'trading.signals.{order_id}',
                signal,
                metadata={'source': 'signal_handler', 'action': 'signal_closed'}
            )
        signal['pnl'] = pnl
        signal['closed_at'] = datetime.now().isoformat()
        
        # Remove from active signals
        if signal in self.active_signals:
            self.active_signals.remove(signal)

