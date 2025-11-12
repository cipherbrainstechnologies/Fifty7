"""
Signal Handler for processing and validating trading signals
"""

import pandas as pd
from typing import Optional, Dict, List
from datetime import datetime
from engine.inside_bar_breakout_strategy import (
    detect_inside_bar,
    confirm_breakout_on_hour_close,
    calculate_strike_price,
    calculate_sl_tp_levels,
    get_active_signal
)
from logzero import logger


def _set_session_state(key: str, value):
    try:
        import streamlit as st  # type: ignore
    except Exception:
        return
    st.session_state[key] = value


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
        
        # Handle missed trade - invalidate signal and wait for new one
        if is_missed_trade:
            logger.warning("Missed trade detected - invalidating signal")
            self._active_signal_state = None
            _set_session_state('last_breakout_direction', None)
            _set_session_state(
                'last_missed_trade',
                {
                    'direction': breakout_direction,
                    'range_high': active_signal['range_high'],
                    'range_low': active_signal['range_low'],
                    'inside_bar_time': active_signal['inside_bar_time'],
                    'signal_time': active_signal['signal_time'],
                    'timestamp': datetime.now().isoformat(),
                }
            )
            return None
        
        # Breakout confirmed - generate trade signal
        current_price = data_1h['Close'].iloc[-1]
        strike = calculate_strike_price(current_price, breakout_direction, atm_offset)
        
        # Use actual close price from breakout candle as entry estimate
        entry_price = latest_closed_candle['Close'] if latest_closed_candle else current_price
        
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
            'signal_time': active_signal['signal_time']
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
            _set_session_state('last_breakout_direction', breakout_direction)
        _set_session_state('last_missed_trade', None)
        
        return signal
    
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
        signal['executed_at'] = datetime.now().isoformat()
        
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
        signal['closed_at'] = datetime.now().isoformat()
        
        # Remove from active signals
        if signal in self.active_signals:
            self.active_signals.remove(signal)

