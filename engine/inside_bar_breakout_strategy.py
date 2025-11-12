"""
Inside Bar Breakout Strategy - Production-Grade Implementation
Implements complete Inside Bar + Breakout strategy for NIFTY Options Trading

Strategy Rules:
1. Use 1-Hour candles (IST timezone). Market hours: 09:15 AM to 03:15 PM IST
2. Detect the most recent inside bar candle (high < previous high, low > previous low)
3. The candle just before the inside bar is the Signal Candle
4. Signal remains active until a new inside bar is detected
5. If any 1-hour candle CLOSES:
   - Above signal high → execute CE trade
   - Below signal low → execute PE trade
6. No 15-min confirmation logic is needed. Only 1-hour candle close matters.
"""

import pandas as pd
from typing import Dict, Optional, List, Tuple, Any
from datetime import datetime, timedelta
import pytz
from logzero import logger
import os
import csv

# Import broker and market data modules
from .broker_connector import AngelOneBroker, BrokerInterface
from .market_data import MarketDataProvider


# Configuration
LIVE_MODE = True  # CHANGED: Enable live trading mode (was False)
MARKET_OPEN_HOUR = 9
MARKET_OPEN_MINUTE = 15
MARKET_CLOSE_HOUR = 15
MARKET_CLOSE_MINUTE = 15
IST = pytz.timezone('Asia/Kolkata')


def ist_now() -> datetime:
    """Return current IST-aware datetime."""
    return datetime.now(IST)


def to_ist(dt: Any) -> datetime:
    """Ensure a datetime-like object is converted to IST-aware datetime."""
    if dt is None:
        raise ValueError("Datetime value cannot be None for IST conversion")
    
    if isinstance(dt, pd.Timestamp):
        ts = dt.to_pydatetime()
    elif isinstance(dt, datetime):
        ts = dt
    else:
        ts = pd.to_datetime(dt).to_pydatetime()
    
    if ts.tzinfo is None:
        return IST.localize(ts)
    return ts.astimezone(IST)


def format_ist_datetime(dt: Any) -> str:
    """Format datetime in DD-MMM-YYYY HH:MM:SS IST."""
    return to_ist(dt).strftime("%d-%b-%Y %H:%M:%S IST")


def format_ist_date(dt: Any) -> str:
    """Format datetime in DD-MMM-YYYY."""
    return to_ist(dt).strftime("%d-%b-%Y")


def log_candle(label: str, candle: Dict[str, Any]):
    """Structured logging for candle OHLC data."""
    if not candle:
        logger.debug(f"{label}: No candle data available")
        return
    candle_time = candle.get('Date')
    open_price = candle.get('Open')
    high_price = candle.get('High')
    low_price = candle.get('Low')
    close_price = candle.get('Close')
    logger.info(
        f"{label}: {format_ist_datetime(candle_time)} | "
        f"O={open_price:.2f}, H={high_price:.2f}, "
        f"L={low_price:.2f}, C={close_price:.2f}"
    )


def log_recent_hourly_candles(
    candles: pd.DataFrame, 
    count: int = 10,
    signal: Optional[Dict[str, Any]] = None
) -> str:
    """
    Log recent hourly candles in a formatted table.
    
    Args:
        candles: DataFrame with hourly candles
        count: Number of recent candles to display (default: 10)
        signal: Active signal dict with inside bar info (optional)
    
    Returns:
        Formatted table string
    """
    if candles is None or candles.empty:
        return "No candles available"
    
    # Get most recent 'count' candles
    recent = candles.tail(count).copy()
    
    # Prepare table header
    table = "\n" + "="*120 + "\n"
    table += "RECENT HOURLY CANDLES (1H TIMEFRAME - IST)\n"
    table += "="*120 + "\n"
    table += f"{'Timestamp':<22} | {'Open':>8} | {'High':>8} | {'Low':>8} | {'Close':>8} | {'Status':<15} | {'Reference Range'}\n"
    table += "-"*120 + "\n"
    
    # Determine inside bar and signal candle indices if signal exists
    inside_bar_time = None
    signal_time = None
    range_high = None
    range_low = None
    
    if signal:
        inside_bar_time = to_ist(signal.get('inside_bar_time'))
        signal_time = to_ist(signal.get('signal_time'))
        range_high = signal.get('range_high')
        range_low = signal.get('range_low')
    
    # Process each candle
    for idx, row in recent.iterrows():
        candle_time = to_ist(row['Date'])
        timestamp_str = format_ist_datetime(candle_time)
        open_val = row['Open']
        high_val = row['High']
        low_val = row['Low']
        close_val = row['Close']
        
        # Determine status
        status = "Normal"
        reference_range = "-"
        
        if signal:
            if candle_time == inside_bar_time:
                status = "\ud83d\udfe2 Inside Bar"
                reference_range = f"Range: {range_low:.2f}-{range_high:.2f}"
            elif candle_time == signal_time:
                status = "\ud83d\udd35 Signal Candle"
                reference_range = f"Range: {range_low:.2f}-{range_high:.2f}"
            elif candle_time > inside_bar_time:
                # Check if breakout
                if close_val > range_high:
                    status = "\ud83d\udfe2 Breakout CE"
                    reference_range = f"Close > {range_high:.2f}"
                elif close_val < range_low:
                    status = "\ud83d\udd34 Breakout PE"
                    reference_range = f"Close < {range_low:.2f}"
                else:
                    status = "\u23f3 Inside Range"
                    reference_range = f"{range_low:.2f}-{range_high:.2f}"
        
        table += f"{timestamp_str:<22} | {open_val:>8.2f} | {high_val:>8.2f} | {low_val:>8.2f} | {close_val:>8.2f} | {status:<15} | {reference_range}\n"
    
    table += "="*120 + "\n"
    
    return table


def _find_latest_inside_structure(candles: pd.DataFrame) -> Optional[Dict[str, Any]]:
    """
    Identify the most recent Inside Bar compression structure, preserving the
    original mother candle until a new mother is formed.

    Returns a dictionary containing the mother index and a list of inside bar
    indices representing the active compression sequence.
    """
    if candles is None or len(candles) < 2:
        return None

    mother_idx: Optional[int] = None
    inside_indices: List[int] = []
    latest_structure: Optional[Dict[str, Any]] = None

    for idx in range(1, len(candles)):
        current = candles.iloc[idx]
        previous = candles.iloc[idx - 1]

        if mother_idx is not None:
            mother = candles.iloc[mother_idx]
            if (current['High'] <= mother['High']) and (current['Low'] >= mother['Low']):
                inside_indices.append(idx)
                latest_structure = {
                    'mother_idx': mother_idx,
                    'inside_indices': inside_indices.copy()
                }
                continue
            else:
                mother_idx = None
                inside_indices = []

        if (previous['High'] > current['High']) and (previous['Low'] < current['Low']):
            mother_idx = idx - 1
            inside_indices = [idx]
            latest_structure = {
                'mother_idx': mother_idx,
                'inside_indices': inside_indices.copy()
            }
        else:
            mother_idx = None
            inside_indices = []

    return latest_structure


def _ensure_datetime_column(candles: pd.DataFrame) -> pd.DataFrame:
    """Ensure candles DataFrame has a Date column with datetime objects."""
    if candles is None or candles.empty:
        return pd.DataFrame(columns=['Date', 'Open', 'High', 'Low', 'Close', 'Volume'])
    
    working = candles.copy()
    if 'Date' not in working.columns:
        if isinstance(working.index, pd.DatetimeIndex):
            working = working.reset_index().rename(columns={'index': 'Date'})
        else:
            raise ValueError("Candles DataFrame must include a 'Date' column or DateTimeIndex")
    
    working['Date'] = pd.to_datetime(working['Date'])
    return working


def _candle_end_time(candle_time: Any) -> datetime:
    """Return the end time (close) of a 1-hour candle."""
    return to_ist(candle_time) + timedelta(hours=1)


def get_hourly_candles(
    market_data: Optional[MarketDataProvider] = None,
    window_hours: int = 48,
    data: Optional[pd.DataFrame] = None,
    current_time: Optional[datetime] = None
) -> pd.DataFrame:
    """
    Fetch closed hourly candles aligned to IST market hours.
    Excludes incomplete candles but retains the just-closed candle.
    """
    source = "provided_data" if data is not None else "market_data"
    
    if data is not None:
        candles = _ensure_datetime_column(data)
    else:
        if market_data is None:
            raise ValueError("market_data provider is required when data is not supplied")
        raw_candles = market_data.get_1h_data(
            window_hours=window_hours,
            use_direct_interval=True,
            include_latest=True
        )
        candles = _ensure_datetime_column(raw_candles) if raw_candles is not None else pd.DataFrame()
    
    if candles.empty:
        logger.warning("No hourly candles available after initial fetch")
        return candles
    
    candles = candles.drop_duplicates(subset=['Date']).sort_values('Date').reset_index(drop=True)
    
    # Normalize to IST-aware timestamps
    try:
        candles['Date'] = pd.to_datetime(candles['Date'], utc=False)
        if getattr(candles['Date'].dt, "tz", None) is None:
            candles['Date'] = candles['Date'].dt.tz_localize(IST)
        else:
            candles['Date'] = candles['Date'].dt.tz_convert(IST)
    except Exception as tz_error:
        logger.warning(f"Failed to normalize candle timestamps to IST: {tz_error}")
        candles['Date'] = candles['Date'].apply(to_ist)
    
    # Determine reference time for completeness checks
    if current_time is not None:
        reference_time = to_ist(current_time)
    elif market_data is not None:
        try:
            reference_time = market_data.get_last_closed_hour_end()
        except Exception as err:
            logger.warning(f"Unable to fetch last closed hour end from market data: {err}")
            reference_time = ist_now()
    else:
        reference_time = ist_now()
    
    def is_complete(row) -> bool:
        return _candle_end_time(row['Date']) <= reference_time
    
    completeness_mask = candles.apply(is_complete, axis=1)
    incomplete = candles.loc[~completeness_mask]
    if not incomplete.empty:
        excluded_labels = ", ".join(format_ist_datetime(ts) for ts in incomplete['Date'])
        logger.info(f"Excluded {len(incomplete)} incomplete 1-hour candle(s): {excluded_labels}")
    
    closed_candles = candles.loc[completeness_mask].reset_index(drop=True)
    closed_candles['Date'] = closed_candles['Date'].dt.tz_localize(None)
    
    logger.info(f"Prepared {len(closed_candles)} closed 1-hour candles (source={source})")
    return closed_candles


def detect_inside_bar(candles: pd.DataFrame) -> Optional[Dict[str, Any]]:
    """
    Detect the preferred inside bar from the provided candles.
    Preserves the original mother candle until a new mother is formed and
    returns the most recent compression structure.
    """
    candles = _ensure_datetime_column(candles)
    if len(candles) < 2:
        logger.debug("Insufficient candles for inside bar detection")
        return None
    
    structure = _find_latest_inside_structure(candles)
    if not structure:
        logger.debug("No inside bar compression structure detected")
        return None

    mother_idx = structure['mother_idx']
    inside_indices = structure['inside_indices']
    latest_inside_idx = inside_indices[-1]

    mother_candle = candles.iloc[mother_idx]
    inside_candle = candles.iloc[latest_inside_idx]

    mother_time = to_ist(mother_candle['Date'])
    inside_time = to_ist(inside_candle['Date'])
    range_high = mother_candle['High']
    range_low = mother_candle['Low']
    range_width = range_high - range_low

    selected = {
        'mother_idx': mother_idx,
        'compression_inside_indices': inside_indices,
        'compression_count': len(inside_indices),
        'inside_bar_idx': latest_inside_idx,
        'inside_bar_time': inside_time,
        'inside_bar': {
            'Date': inside_time,
            'Open': inside_candle['Open'],
            'High': inside_candle['High'],
            'Low': inside_candle['Low'],
            'Close': inside_candle['Close'],
        },
        'signal_idx': mother_idx,
        'signal_time': mother_time,
        'signal_candle': {
            'Date': mother_time,
            'Open': mother_candle['Open'],
            'High': mother_candle['High'],
            'Low': mother_candle['Low'],
            'Close': mother_candle['Close'],
        },
        'range_high': range_high,
        'range_low': range_low,
        'range_width': range_width,
        'priority': (
            0 if inside_time.date() == ist_now().date() else 1,
            -latest_inside_idx,
            range_width,
            -len(inside_indices)
        )
    }

    logger.info(
        f"Inside bar selected at {format_ist_datetime(selected['inside_bar_time'])} | "
        f"Mother candle at {format_ist_datetime(selected['signal_time'])} | "
        f"Compression bars: {len(inside_indices)} | "
        f"Range: {selected['range_low']:.2f}-{selected['range_high']:.2f} "
        f"(width {selected['range_width']:.2f})"
    )
    return selected


def get_active_signal(
    candles: pd.DataFrame,
    previous_signal: Optional[Dict[str, Any]] = None,
    mark_signal_invalid: bool = False,
    exclude_before_time: Optional[datetime] = None
) -> Optional[Dict[str, Any]]:
    """
    Maintain the active signal using the most recent (preferably today's) inside bar.
    Keeps existing signal active until a newer inside bar supersedes it OR until explicitly invalidated.
    
    Args:
        candles: DataFrame with hourly candles
        previous_signal: Previously active signal (if any)
        mark_signal_invalid: If True, discard current signal (used after breakout attempt)
        exclude_before_time: If provided, only detect inside bars AFTER this time (used after breakout)
    
    Returns:
        Active signal dict or None
    """
    # If signal is being explicitly invalidated (e.g., after breakout attempt)
    if mark_signal_invalid and previous_signal:
        logger.info(
            f"🗑️ Signal invalidated: Inside bar from {format_ist_datetime(previous_signal['inside_bar_time'])} "
            f"discarded after breakout attempt"
        )
        return None
    
    # Invalidate signals that have already broken out but now closed beyond the opposite range boundary
    if previous_signal is not None and not candles.empty and previous_signal.get('breakout_direction'):
        last_close = float(candles['Close'].iloc[-1])
        prev_direction = previous_signal.get('breakout_direction')
        range_high = previous_signal.get('range_high')
        range_low = previous_signal.get('range_low')
        
        if prev_direction == "PE" and range_high is not None and last_close > range_high:
            logger.info(
                "🚫 Opposite move detected after PE breakout — invalidating previous signal. "
                f"Last close {last_close:.2f} > mother high {range_high:.2f}"
            )
            return None
        if prev_direction == "CE" and range_low is not None and last_close < range_low:
            logger.info(
                "🚫 Opposite move detected after CE breakout — invalidating previous signal. "
                f"Last close {last_close:.2f} < mother low {range_low:.2f}"
            )
            return None
    
    # Filter candles if we need to exclude old inside bars (after breakout)
    filtered_candles = candles
    if exclude_before_time:
        candles_date = pd.to_datetime(candles['Date'])
        if candles_date.dt.tz is None:
            candles_date_aware = candles_date.dt.tz_localize(IST)
        else:
            candles_date_aware = candles_date.dt.tz_convert(IST)
        filtered_candles = candles[candles_date_aware > exclude_before_time].copy()
        if filtered_candles.empty:
            logger.debug(f"No candles available after exclusion time {format_ist_datetime(exclude_before_time)}")
            return None
        logger.debug(f"Filtering inside bars: excluding any before {format_ist_datetime(exclude_before_time)}")
    
    candidate = detect_inside_bar(filtered_candles)
    if candidate is None:
        if previous_signal and not exclude_before_time:
            logger.debug("No new inside bar detected; retaining existing active signal")
            return previous_signal
        return None
    
    if previous_signal:
        prev_time = to_ist(previous_signal.get('inside_bar_time'))
        candidate_time = candidate['inside_bar_time']
        
        # Compare by timestamp, not index
        if prev_time == candidate_time:
            logger.debug("Inside bar unchanged; keeping existing active signal")
            return previous_signal
        if prev_time > candidate_time:
            logger.debug("Existing signal is more recent; retaining it")
            return previous_signal
    
    signal = {
        'mother_idx': candidate.get('mother_idx', candidate['signal_idx']),
        'inside_bar_idx': candidate['inside_bar_idx'],
        'inside_bar_time': candidate['inside_bar_time'],
        'inside_bar': candidate['inside_bar'],
        'signal_idx': candidate['signal_idx'],
        'signal_time': candidate['signal_time'],
        'signal_candle': candidate['signal_candle'],
        'compression_inside_indices': candidate.get('compression_inside_indices', [candidate['inside_bar_idx']]),
        'compression_count': candidate.get('compression_count', 1),
        'range_high': candidate['range_high'],
        'range_low': candidate['range_low'],
        'breakout_attempted': False,  # Track if breakout has been attempted
        'breakout_direction': None
    }
    
    logger.info(
        f"✨ Active signal updated → Inside bar {format_ist_datetime(signal['inside_bar_time'])} "
        f"| Signal range {signal['range_low']:.2f}-{signal['range_high']:.2f}"
    )
    log_candle("Signal candle", signal['signal_candle'])
    log_candle("Inside bar candle", signal['inside_bar'])
    return signal


def confirm_breakout_on_hour_close(
    candles: pd.DataFrame,
    signal: Optional[Dict[str, Any]],
    current_time: Optional[datetime] = None,
    check_missed_trade: bool = True
) -> Tuple[Optional[str], Optional[Dict[str, Any]], bool]:
    """
    Confirm breakout using only closed 1-hour candles.
    Uses TIMESTAMP-BASED comparison instead of indices to work across days.
    
    Args:
        candles: DataFrame with hourly candles
        signal: Active signal dict with inside bar info
        current_time: Current time for completeness checks
        check_missed_trade: If True, detect missed trade opportunities
    
    Returns:
        Tuple of:
        - direction ("CE"/"PE") if breakout detected, otherwise None
        - latest_closed_candle dict for observability/logging
        - is_missed_trade (True if breakout happened but trade was missed)
    """
    if signal is None:
        logger.debug("No active signal to evaluate breakout against")
        return None, None, False
    
    candles = _ensure_datetime_column(candles)
    if candles.empty:
        logger.debug("Candles DataFrame is empty")
        return None, None, False
    
    if current_time is None:
        current_time = ist_now()
    current_time = to_ist(current_time)
    
    # Get inside bar timestamp from signal (timestamp-based, not index-based)
    inside_bar_time = to_ist(signal['inside_bar_time'])
    logger.info(
        f"🔍 Checking for breakout AFTER inside bar at {format_ist_datetime(inside_bar_time)} | "
        f"Signal range: {signal['range_low']:.2f} - {signal['range_high']:.2f}"
    )
    
    # Filter candles that come AFTER the inside bar (timestamp-based)
    # Ensure timezone compatibility for comparison
    candles_date = pd.to_datetime(candles['Date'])
    # Localize timezone-naive dates to IST for comparison
    if candles_date.dt.tz is None:
        candles_date_aware = candles_date.dt.tz_localize(IST)
    else:
        candles_date_aware = candles_date.dt.tz_convert(IST)
    
    # Create comparison using timezone-aware values
    candles_after_inside = candles[candles_date_aware > inside_bar_time].copy()
    
    if candles_after_inside.empty:
        logger.debug(f"No candles available after inside bar time {format_ist_datetime(inside_bar_time)}")
        return None, None, False
    
    logger.info(f"Found {len(candles_after_inside)} candle(s) after inside bar for breakout evaluation")
    
    latest_closed: Optional[Dict[str, Any]] = None
    first_breakout_candle: Optional[Dict[str, Any]] = None
    breakout_direction: Optional[str] = None
    is_missed_trade = False
    
    # Check each candle AFTER inside bar (process in chronological order)
    for idx, candle in candles_after_inside.iterrows():
        candle_start = to_ist(candle['Date'])
        candle_end = candle_start + timedelta(hours=1)
        
        # Skip incomplete candles
        if candle_end > current_time:
            logger.debug(f"⏭️ Skipping incomplete candle at {format_ist_datetime(candle_start)}")
            continue
        
        close_price = candle['Close']
        open_price = candle['Open']
        high_price = candle['High']
        low_price = candle['Low']
        breakout_low = close_price < signal['range_low']
        breakout_high = close_price > signal['range_high']
        inside_range = not breakout_low and not breakout_high
        
        # Enhanced logging for EVERY hourly candle
        logger.info(
            f"\n{'='*80}\n"
            f"📊 Hourly Candle Check: {format_ist_datetime(candle_start)} to {format_ist_datetime(candle_end)}\n"
            f"   O={open_price:.2f}, H={high_price:.2f}, L={low_price:.2f}, C={close_price:.2f}\n"
            f"   Signal Range: Low={signal['range_low']:.2f}, High={signal['range_high']:.2f}\n"
            f"   Close < Low ({close_price:.2f} < {signal['range_low']:.2f}): {breakout_low}\n"
            f"   Close > High ({close_price:.2f} > {signal['range_high']:.2f}): {breakout_high}\n"
            f"   Inside Range: {inside_range}\n"
            f"{'='*80}"
        )
        
        latest_closed = {
            'index': idx,
            'Date': candle_end,
            'Open': open_price,
            'High': high_price,
            'Low': low_price,
            'Close': close_price,
            'candle_start': candle_start
        }
        
        # Check for breakout on THIS candle
        if breakout_high and first_breakout_candle is None:
            first_breakout_candle = latest_closed.copy()
            breakout_direction = "CE"
            signal['breakout_direction'] = "CE"
            logger.info(
                f"\n{'🟢'*40}\n"
                f"✅ FIRST BREAKOUT DETECTED (CE) at {format_ist_datetime(candle_end)}\n"
                f"   Close {close_price:.2f} > Signal High {signal['range_high']:.2f}\n"
                f"   Breakout by {close_price - signal['range_high']:.2f} points\n"
                f"{'🟢'*40}"
            )
            # Check if this is a missed trade (candle already closed more than 5 min ago)
            time_since_close = (current_time - candle_end).total_seconds()
            if check_missed_trade and time_since_close > 300:  # 5 minutes threshold
                is_missed_trade = True
                logger.warning(
                    f"⚠️ MISSED TRADE: Breakout candle closed {int(time_since_close/60)} minutes ago at {format_ist_datetime(candle_end)}. "
                    f"System was offline or delayed."
                )
            break  # Only process first breakout candle
        
        if breakout_low and first_breakout_candle is None:
            first_breakout_candle = latest_closed.copy()
            breakout_direction = "PE"
            signal['breakout_direction'] = "PE"
            logger.info(
                f"\n{'🔴'*40}\n"
                f"✅ FIRST BREAKOUT DETECTED (PE) at {format_ist_datetime(candle_end)}\n"
                f"   Close {close_price:.2f} < Signal Low {signal['range_low']:.2f}\n"
                f"   Breakout by {signal['range_low'] - close_price:.2f} points\n"
                f"{'🔴'*40}"
            )
            # Check if this is a missed trade
            time_since_close = (current_time - candle_end).total_seconds()
            if check_missed_trade and time_since_close > 300:  # 5 minutes threshold
                is_missed_trade = True
                logger.warning(
                    f"⚠️ MISSED TRADE: Breakout candle closed {int(time_since_close/60)} minutes ago at {format_ist_datetime(candle_end)}. "
                    f"System was offline or delayed."
                )
            break  # Only process first breakout candle
        
        if inside_range:
            logger.info(f"⏳ No breakout yet - candle closed inside signal range")
    
    if latest_closed and not first_breakout_candle:
        logger.info(
            f"📋 Latest closed candle: {format_ist_datetime(latest_closed['Date'])} | "
            f"Close={latest_closed['Close']:.2f} (still inside range)"
        )
    elif not latest_closed:
        logger.debug("No closed 1H candles available after inside bar yet")
    
    return breakout_direction, first_breakout_candle or latest_closed, is_missed_trade


def check_margin(
    broker: Optional[BrokerInterface],
    quantity_lots: int,
    lot_size: int,
    entry_price: Optional[float]
) -> Tuple[bool, float, float]:
    """
    Check available margin. Returns (has_margin, available_margin, required_margin).
    """
    if quantity_lots <= 0:
        logger.warning("Quantity lots must be positive for margin check")
        return False, 0.0, 0.0
    
    required_margin = (entry_price or 0) * quantity_lots * lot_size
    if required_margin <= 0:
        # Conservative fallback estimate per lot if entry price unavailable
        required_margin = quantity_lots * 50000
    
    if broker is None:
        logger.info("No broker instance; assuming sufficient margin for simulation mode")
        return True, float('inf'), required_margin
    
    try:
        available_margin = broker.get_available_margin()
    except Exception as err:
        logger.exception(f"Failed to retrieve available margin: {err}")
        return False, 0.0, required_margin
    
    if available_margin >= required_margin:
        logger.info(
            f"Margin check → available ₹{available_margin:,.2f} "
            f">= required ₹{required_margin:,.2f}"
        )
        return True, available_margin, required_margin
    
    logger.warning(
        f"Insufficient margin → available ₹{available_margin:,.2f} "
        f"< required ₹{required_margin:,.2f}"
    )
    return False, available_margin, required_margin


def place_order(
    broker: Optional[BrokerInterface],
    symbol: str,
    strike: int,
    direction: str,
    quantity_lots: int,
    live_mode: bool,
    execution_armed: bool
) -> Dict[str, Any]:
    """
    Place order with safety guardrails.
    Returns broker response or simulated result.
    """
    attempt_timestamp = format_ist_datetime(ist_now())
    logger.info(
        f"\n{'='*80}\n"
        f"🚨 ORDER PLACEMENT ATTEMPT\n"
        f"{'='*80}\n"
        f"   Timestamp: {attempt_timestamp}\n"
        f"   Direction: {direction}\n"
        f"   Symbol: {symbol}\n"
        f"   Strike: {strike}\n"
        f"   Quantity: {quantity_lots} lot(s)\n"
        f"   LIVE_MODE Global Flag: {LIVE_MODE}\n"
        f"   live_mode (instance): {live_mode}\n"
        f"   execution_armed: {execution_armed}\n"
        f"   Broker Available: {broker is not None}\n"
        f"{'='*80}"
    )
    
    if not live_mode:
        order_id = f"SIM_{ist_now().strftime('%Y%m%d%H%M%S')}"
        logger.warning(
            f"\n{'⚠️'*40}\n"
            f"🚫 TRADE BLOCKED: LIVE_MODE DISABLED\n"
            f"   Reason: live_mode={live_mode} (LIVE_MODE global={LIVE_MODE})\n"
            f"   Generated dry-run order: {order_id}\n"
            f"   ➡️ To enable: Set LIVE_MODE=True in inside_bar_breakout_strategy.py\n"
            f"{'⚠️'*40}"
        )
        return {
            'status': True,
            'order_id': order_id,
            'message': 'Simulated order (LIVE_MODE=False)',
            'response': None,
            'simulated': True
        }
    
    if not execution_armed:
        logger.error(
            f"\n{'🛑'*40}\n"
            f"🚫 TRADE BLOCKED: EXECUTION NOT ARMED\n"
            f"   Reason: execution_armed={execution_armed}\n"
            f"   ➡️ To enable: Call strategy.arm_live_execution() before trading\n"
            f"   This is a SAFETY mechanism to prevent accidental live trades\n"
            f"{'🛑'*40}"
        )
        return {
            'status': False,
            'order_id': None,
            'message': 'Execution not armed (dry run) - Call arm_live_execution() first',
            'response': None,
            'simulated': True
        }
    
    if broker is None:
        logger.error("Broker instance not available for live order placement")
        return {
            'status': False,
            'order_id': None,
            'message': 'Broker not configured',
            'response': None
        }
    
    try:
        response = broker.place_order(
            symbol=symbol,
            strike=strike,
            direction=direction,
            quantity=quantity_lots,
            order_type="MARKET",
            transaction_type="BUY"
        )
        logger.info(f"Order API response: {response}")
        return response
    except Exception as err:
        logger.exception(f"Order placement raised exception: {err}")
        return {
            'status': False,
            'order_id': None,
            'message': f'Exception during order placement: {err}',
            'response': None
        }


# Internal aliases so class methods can reuse functional helpers without recursion
_GET_HOURLY_CANDLES = get_hourly_candles
_DETECT_INSIDE_BAR = detect_inside_bar
_GET_ACTIVE_SIGNAL = get_active_signal
_CONFIRM_BREAKOUT = confirm_breakout_on_hour_close
_CHECK_MARGIN = check_margin
_PLACE_ORDER = place_order
_LOG_RECENT_CANDLES = log_recent_hourly_candles


def calculate_strike_price(current_price: float, direction: str, atm_offset: int = 0) -> int:
    """
    Calculate option strike price based on current NIFTY price.
    
    Args:
        current_price: Current NIFTY index price
        direction: "CE" for Call, "PE" for Put
        atm_offset: Offset from ATM (0 = ATM, positive = OTM for calls)
    
    Returns:
        Strike price rounded to nearest 50 (NIFTY strikes are multiples of 50)
    """
    # NIFTY strikes are in multiples of 50
    base_strike = round(current_price / 50) * 50
    
    if direction == "CE":
        return int(base_strike + atm_offset)
    elif direction == "PE":
        return int(base_strike - atm_offset)
    else:
        return int(base_strike)


def calculate_sl_tp_levels(
    entry_price: float,
    stop_loss_points: int,
    risk_reward_ratio: float
) -> Tuple[float, float]:
    """
    Calculate Stop Loss and Take Profit levels based on entry and risk parameters.
    
    Args:
        entry_price: Entry price of the option
        stop_loss_points: Stop loss in points
        risk_reward_ratio: Risk-Reward ratio (e.g., 1.8 = 1.8x risk)
    
    Returns:
        Tuple of (stop_loss_price, take_profit_price)
    """
    stop_loss = entry_price - stop_loss_points
    take_profit = entry_price + (stop_loss_points * risk_reward_ratio)
    
    return (stop_loss, take_profit)


class InsideBarBreakoutStrategy:
    """
    Production-grade Inside Bar Breakout Strategy implementation.
    """
    
    def __init__(
        self,
        broker: Optional[BrokerInterface] = None,
        market_data: Optional[MarketDataProvider] = None,
        symbol: str = "NIFTY",
        lot_size: int = 75,
        quantity_lots: int = 1,
        live_mode: bool = True,
        csv_export_path: Optional[str] = None,
        config: Optional[Dict] = None
    ):
        """
        Initialize Inside Bar Breakout Strategy.
        
        Args:
            broker: Broker interface instance (AngelOneBroker)
            market_data: MarketDataProvider instance
            symbol: Trading symbol (default: "NIFTY")
            lot_size: Lot size for options (default: 75 for NIFTY)
            quantity_lots: Number of lots per trade (default: 1)
            live_mode: If True, place real trades. If False, simulate only.
            csv_export_path: Optional path to export results CSV
        """
        self.broker = broker
        self.market_data = market_data
        self.symbol = symbol
        self.lot_size = lot_size
        self.quantity_lots = quantity_lots
        self.live_mode = bool(live_mode and LIVE_MODE)
        self.execution_armed = False
        self.csv_export_path = csv_export_path or "logs/inside_bar_breakout_results.csv"
        self.config = config or {}
        
        # Strategy parameters from config
        self.sl_points = self.config.get('strategy', {}).get('sl', 30)  # Stop loss in points
        self.rr_ratio = self.config.get('strategy', {}).get('rr', 1.8)  # Risk-reward ratio
        self.atm_offset = self.config.get('strategy', {}).get('atm_offset', 0)  # Strike offset
        
        # Strategy state
        self.active_signal: Optional[Dict[str, Any]] = None
        self.last_breakout_candle_idx: Optional[int] = None
        
        # Ensure CSV directory exists
        if self.csv_export_path:
            os.makedirs(os.path.dirname(self.csv_export_path) or '.', exist_ok=True)
            self._initialize_csv()
        
        logger.info(
            f"Inside Bar Breakout Strategy initialized "
            f"(Live Mode Enabled: {self.live_mode}, LIVE_MODE flag: {LIVE_MODE})"
        )
    
    def _initialize_csv(self):
        """Initialize CSV file with headers if it doesn't exist."""
        if os.path.exists(self.csv_export_path):
            return
        
        headers = [
            'Date', 'Time', 'Signal_Date', 'Signal_High', 'Signal_Low',
            'Current_Price', 'Breakout_Direction', 'Strike', 'Entry_Price',
            'Stop_Loss', 'Take_Profit', 'Order_ID', 'Status', 'Message'
        ]
        
        with open(self.csv_export_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(headers)
    
    def _export_to_csv(self, row_data: Dict):
        """Export result row to CSV."""
        if not self.csv_export_path:
            return
        
        try:
            with open(self.csv_export_path, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    row_data.get('Date', ''),
                    row_data.get('Time', ''),
                    row_data.get('Signal_Date', ''),
                    row_data.get('Signal_High', ''),
                    row_data.get('Signal_Low', ''),
                    row_data.get('Current_Price', ''),
                    row_data.get('Breakout_Direction', ''),
                    row_data.get('Strike', ''),
                    row_data.get('Entry_Price', ''),
                    row_data.get('Stop_Loss', ''),
                    row_data.get('Take_Profit', ''),
                    row_data.get('Order_ID', ''),
                    row_data.get('Status', ''),
                    row_data.get('Message', '')
                ])
        except Exception as e:
            logger.error(f"Error exporting to CSV: {e}")
    
    def _format_date_ist(self, dt: datetime) -> str:
        """
        Format datetime to DD-MMM-YYYY format in IST timezone.
        
        Args:
            dt: Datetime object (may be timezone-aware or naive)
        
        Returns:
            Formatted date string (e.g., "04-Nov-2025")
        """
        # Convert to IST if timezone-aware
        if dt.tzinfo is not None:
            dt_ist = dt.astimezone(IST)
        else:
            # Assume naive datetime is already in IST
            dt_ist = IST.localize(dt) if dt.tzinfo is None else dt
        
        return dt_ist.strftime("%d-%b-%Y")
    
    def _format_datetime_ist(self, dt: datetime) -> str:
        """
        Format datetime to DD-MMM-YYYY HH:MM:SS IST format.
        
        Args:
            dt: Datetime object
        
        Returns:
            Formatted datetime string (e.g., "04-Nov-2025 10:30:00 IST")
        """
        if dt.tzinfo is not None:
            dt_ist = dt.astimezone(IST)
        else:
            dt_ist = IST.localize(dt) if dt.tzinfo is None else dt
        
        return dt_ist.strftime("%d-%b-%Y %H:%M:%S IST")
    
    def _is_market_hours(self, dt: Optional[datetime] = None) -> bool:
        """
        Check if current time is within market hours (09:15 AM to 03:15 PM IST).
        
        Args:
            dt: Datetime to check (default: current time)
        
        Returns:
            True if within market hours, False otherwise
        """
        if dt is None:
            dt = datetime.now(IST)
        elif dt.tzinfo is None:
            dt = IST.localize(dt)
        else:
            dt = dt.astimezone(IST)
        
        # Get time components
        hour = dt.hour
        minute = dt.minute
        
        # Market opens at 09:15
        market_open = datetime(dt.year, dt.month, dt.day, MARKET_OPEN_HOUR, MARKET_OPEN_MINUTE, tzinfo=IST)
        # Market closes at 15:15
        market_close = datetime(dt.year, dt.month, dt.day, MARKET_CLOSE_HOUR, MARKET_CLOSE_MINUTE, tzinfo=IST)
        
        return market_open <= dt <= market_close
    
    def get_hourly_candles(
        self,
        window_hours: int = 48,
        data: Optional[pd.DataFrame] = None
    ) -> pd.DataFrame:
        """
        Wrapper around module-level get_hourly_candles to maintain backwards compatibility.
        """
        try:
            candles = _GET_HOURLY_CANDLES(
                market_data=self.market_data,
                window_hours=window_hours,
                data=data
            )
            return candles
        except Exception as err:
            logger.exception(f"Error retrieving hourly candles: {err}")
            return pd.DataFrame(columns=['Date', 'Open', 'High', 'Low', 'Close', 'Volume'])
    
    def detect_inside_bar(self, candles: pd.DataFrame) -> Optional[Dict[str, Any]]:
        """
        Backwards-compatible wrapper for module-level detect_inside_bar utility.
        """
        return _DETECT_INSIDE_BAR(candles)
    
    def check_breakout(
        self,
        candles: pd.DataFrame,
        signal_high: float,
        signal_low: float,
        start_idx: int = 0
    ) -> Optional[str]:
        """
        Compatibility wrapper around confirm_breakout_on_hour_close.
        """
        if candles is None or candles.empty:
            return None
        
        inside_idx = max(start_idx - 1, 0)
        signal_stub = {
            'inside_bar_idx': inside_idx,
            'range_high': signal_high,
            'range_low': signal_low
        }
        direction, _ = _CONFIRM_BREAKOUT(candles, signal_stub)
        return direction
    
    def calculate_strike_price(self, current_price: float, direction: str, atm_offset: int = 0) -> int:
        """
        Calculate option strike price based on current NIFTY price.
        Delegates to module-level function.
        
        Args:
            current_price: Current NIFTY index price
            direction: "CE" for Call, "PE" for Put
            atm_offset: Offset from ATM (0 = ATM, positive = OTM for calls)
        
        Returns:
            Strike price rounded to nearest 50 (NIFTY strikes are multiples of 50)
        """
        return calculate_strike_price(current_price, direction, atm_offset)
    
    def calculate_sl_tp_levels(
        self,
        entry_price: float,
        stop_loss_points: int,
        risk_reward_ratio: float
    ) -> Tuple[float, float]:
        """
        Calculate Stop Loss and Take Profit levels based on entry and risk parameters.
        Delegates to module-level function.
        
        Args:
            entry_price: Entry price of the option
            stop_loss_points: Stop loss in points
            risk_reward_ratio: Risk-Reward ratio (e.g., 1.8 = 1.8x risk)
        
        Returns:
            Tuple of (stop_loss_price, take_profit_price)
        """
        return calculate_sl_tp_levels(entry_price, stop_loss_points, risk_reward_ratio)
    
    def check_margin(self, entry_price: Optional[float]) -> Tuple[bool, float, float]:
        """
        Wrapper around module-level check_margin utility.
        """
        return _CHECK_MARGIN(
            broker=self.broker,
            quantity_lots=self.quantity_lots,
            lot_size=self.lot_size,
            entry_price=entry_price
        )
    
    def place_trade(
        self,
        direction: str,
        strike: int,
        entry_price: Optional[float]
    ) -> Dict[str, Any]:
        """
        Place or simulate trade via broker with safety checks.
        """
        has_margin, available_margin, required_margin = self.check_margin(entry_price)
        if not has_margin:
            message = (
                f'Insufficient margin: available ₹{available_margin:,.2f}, '
                f'required ₹{required_margin:,.2f}'
            )
            logger.warning(message)
            return {
                'status': False,
                'order_id': None,
                'message': message,
                'response': None,
                'simulated': not self.live_mode,
                'available_margin': available_margin,
                'required_margin': required_margin
            }
        
        order_response = _PLACE_ORDER(
            broker=self.broker,
            symbol=self.symbol,
            strike=strike,
            direction=direction,
            quantity_lots=self.quantity_lots,
            live_mode=self.live_mode,
            execution_armed=self.execution_armed
        )
        order_response.setdefault('available_margin', available_margin)
        order_response.setdefault('required_margin', required_margin)
        return order_response
    
    def get_active_signal(self, candles: pd.DataFrame) -> Optional[Dict[str, Any]]:
        """
        Update and return the active signal based on latest candles.
        """
        self.active_signal = _GET_ACTIVE_SIGNAL(candles, self.active_signal)
        return self.active_signal
    
    def arm_live_execution(self) -> bool:
        """
        Require explicit arming before actual orders are placed in live mode.
        """
        if not self.live_mode:
            logger.warning("Live execution cannot be armed because LIVE_MODE is disabled.")
            return False
        self.execution_armed = True
        logger.info("Live execution armed. Next eligible breakout will place a real order.")
        return True
    
    def disarm_live_execution(self):
        """
        Disarm live execution; subsequent trades will run as dry-run.
        """
        self.execution_armed = False
        logger.info("Live execution disarmed. Orders will remain in dry-run mode.")
    
    def run_strategy(self, data: Optional[pd.DataFrame] = None) -> Dict:
        """
        Execute one evaluation cycle of the Inside Bar breakout strategy.
        Now with improved signal invalidation after first breakout attempt.
        """
        try:
            now_ist = ist_now()
            current_time_str = format_ist_datetime(now_ist)
            
            if not self._is_market_hours(now_ist):
                logger.info(f"⏸️ Market is closed. Current time: {current_time_str}")
                return {
                    'status': 'market_closed',
                    'message': 'Market is closed',
                    'time': current_time_str
                }
            
            logger.info(f"🚀 Running Inside Bar Breakout Strategy | Time: {current_time_str}")
            
            candles = self.get_hourly_candles(window_hours=48, data=data)
            if candles is None or candles.empty:
                logger.error("No closed hourly candles available for strategy evaluation")
                return {
                    'status': 'error',
                    'message': 'Closed hourly candles unavailable',
                    'time': current_time_str
                }
            
            # Log candle data info for diagnostics
            logger.info(f"📦 Loaded {len(candles)} hourly candles for analysis")
            if not candles.empty:
                first_candle_date = format_ist_datetime(candles['Date'].iloc[0])
                last_candle_date = format_ist_datetime(candles['Date'].iloc[-1])
                logger.info(f"   Date range: {first_candle_date} to {last_candle_date}")
                
                # Log recent hourly candles table (before checking for active signal)
                candles_table = _LOG_RECENT_CANDLES(candles, count=10, signal=self.active_signal)
                logger.info(candles_table)
            
            # Check for volume data availability (AngelOne API may not provide volume for NIFTY index)
            if 'Volume' in candles.columns:
                volume_available = candles['Volume'].notna().any() and (candles['Volume'] > 0).any()
                if not volume_available:
                    logger.warning(
                        "⚠️ Volume data is not available or all zeros (Angel API limitation for NIFTY index). "
                        "Volume-based filters are DISABLED. Breakout confirmation uses price only."
                    )
            else:
                logger.warning("⚠️ Volume column not present in candles data. Volume checks disabled.")
            
            current_price = candles['Close'].iloc[-1] if not candles.empty else None
            
            # Get or update active signal
            active_signal = self.get_active_signal(candles)
            if active_signal is None:
                logger.info("📊 No qualifying inside bar signal active for current day")
                return {
                    'status': 'no_signal',
                    'message': 'No inside bar pattern detected for current session',
                    'current_price': current_price,
                    'time': current_time_str
                }
            
            breakout_direction, latest_closed, is_missed_trade = _CONFIRM_BREAKOUT(
                candles,
                active_signal,
                current_time=now_ist,
                check_missed_trade=True
            )
            
            if latest_closed is None and not candles.empty:
                last_candle = candles.iloc[-1]
                latest_closed = {
                    'index': len(candles) - 1,
                    'Date': to_ist(last_candle['Date']),
                    'Open': last_candle['Open'],
                    'High': last_candle['High'],
                    'Low': last_candle['Low'],
                    'Close': last_candle['Close']
                }
            
            if breakout_direction is None:
                return {
                    'status': 'no_breakout',
                    'message': 'Awaiting 1-hour candle close beyond signal range',
                    'signal_date': format_ist_date(active_signal['signal_time']),
                    'signal_high': active_signal['range_high'],
                    'signal_low': active_signal['range_low'],
                    'last_closed_close': latest_closed['Close'] if latest_closed else None,
                    'time': current_time_str
                }
            
            # Handle missed trade scenario
            if is_missed_trade:
                breakout_time_str = format_ist_datetime(latest_closed['Date']) if latest_closed else 'unknown time'
                logger.error(
                    f"\n{'⚠️'*40}\n"
                    f"🚨 MISSED TRADE DETECTED\n"
                    f"   Direction: {breakout_direction}\n"
                    f"   Breakout Candle Close: {breakout_time_str}\n"
                    f"   Signal Range: {active_signal['range_low']:.2f} - {active_signal['range_high']:.2f}\n"
                    f"   Close Price: {latest_closed['Close']:.2f}\n"
                    f"   Reason: System was offline/delayed when breakout occurred\n"
                    f"\n   ➡️ Invalidating signal and scanning for NEW inside bar\n"
                    f"{'⚠️'*40}"
                )
                
                # Invalidate signal and reset state
                self.active_signal = None
                if hasattr(self, 'last_breakout_timestamp'):
                    self.last_breakout_timestamp = None
                
                # Immediately try to detect NEW inside bar after invalidation
                # Exclude inside bars that occurred before or during the breakout candle
                breakout_candle_time = to_ist(latest_closed['Date'])
                logger.info(
                    f"🔄 Scanning for new inside bar pattern after missed trade...\n"
                    f"   Excluding inside bars before: {format_ist_datetime(breakout_candle_time)}"
                )
                new_signal = _GET_ACTIVE_SIGNAL(
                    candles, 
                    previous_signal=None, 
                    mark_signal_invalid=False,
                    exclude_before_time=breakout_candle_time
                )
                
                if new_signal:
                    self.active_signal = new_signal
                    logger.info(
                        f"✅ NEW inside bar detected: {format_ist_datetime(new_signal['inside_bar_time'])} | "
                        f"Range: {new_signal['range_low']:.2f} - {new_signal['range_high']:.2f}"
                    )
                    return {
                        'status': 'missed_trade_new_signal_found',
                        'message': f'Missed breakout {breakout_direction}. New inside bar found and tracking started.',
                        'missed_breakout_direction': breakout_direction,
                        'missed_breakout_time': breakout_time_str,
                        'new_signal_date': format_ist_date(new_signal['signal_time']),
                        'new_signal_high': new_signal['range_high'],
                        'new_signal_low': new_signal['range_low'],
                        'time': current_time_str
                    }
                else:
                    logger.info("⏳ No new inside bar found yet. Will continue scanning in next cycle.")
                    return {
                        'status': 'missed_trade',
                        'message': f'Missed breakout {breakout_direction}. Awaiting new inside bar pattern.',
                        'breakout_direction': breakout_direction,
                        'signal_date': format_ist_date(active_signal['signal_time']),
                        'signal_high': active_signal['range_high'],
                        'signal_low': active_signal['range_low'],
                        'breakout_candle_close_time': breakout_time_str,
                        'missed_reason': 'System was offline or delayed when breakout occurred',
                        'time': current_time_str
                    }
            
            # Check if this is a duplicate breakout (same candle timestamp)
            if latest_closed and hasattr(self, 'last_breakout_timestamp'):
                breakout_timestamp = to_ist(latest_closed.get('candle_start', latest_closed['Date']))
                if breakout_timestamp == self.last_breakout_timestamp:
                    logger.info(
                        f"⏭️ Breakout already processed for candle at {format_ist_datetime(breakout_timestamp)}; skipping duplicate"
                    )
                    return {
                        'status': 'duplicate_breakout',
                        'message': 'Breakout already processed for this candle',
                        'breakout_direction': breakout_direction,
                        'time': current_time_str
                    }
            
            # IMPORTANT: Mark signal as invalid after first breakout attempt
            # This ensures the signal is discarded and won't trigger again
            logger.info(
                f"\n{'🔔'*40}\n"
                f"🎯 BREAKOUT CONFIRMED & TRADE EXECUTION\n"
                f"   Direction: {breakout_direction}\n"
                f"   Signal from: {format_ist_date(active_signal['signal_time'])}\n"
                f"   Breakout Range: {active_signal['range_low']:.2f} - {active_signal['range_high']:.2f}\n"
                f"   ➡️ Signal will be discarded after this trade attempt\n"
                f"{'🔔'*40}"
            )
            
            entry_price = latest_closed['Close'] if latest_closed else current_price
            strike = self.calculate_strike_price(entry_price, breakout_direction, self.atm_offset)
            stop_loss, take_profit = self.calculate_sl_tp_levels(
                entry_price,
                self.sl_points,
                self.rr_ratio
            )
            
            order_response = self.place_trade(breakout_direction, strike, entry_price)
            order_success = bool(order_response.get('status'))
            status = 'breakout_confirmed' if order_success else 'order_failed'
            
            # Record breakout timestamp to prevent duplicates
            if latest_closed:
                self.last_breakout_timestamp = to_ist(latest_closed.get('candle_start', latest_closed['Date']))
            
            # Invalidate signal after breakout attempt (whether successful or not)
            old_signal_time = format_ist_date(active_signal['signal_time'])
            old_range = f"{active_signal['range_low']:.2f} - {active_signal['range_high']:.2f}"
            self.active_signal = None
            
            logger.info(
                f"\n{'🗑️'*40}\n"
                f"✅ SIGNAL DISCARDED AFTER BREAKOUT ATTEMPT\n"
                f"   Old Signal: {old_signal_time}\n"
                f"   Old Range: {old_range}\n"
                f"   ➡️ Will scan for NEW inside bar in next cycle\n"
                f"{'🗑️'*40}"
            )
            
            # Immediately try to detect NEW inside bar for next opportunity
            # Exclude inside bars that occurred before or during the breakout candle
            breakout_candle_time = to_ist(latest_closed.get('candle_start', latest_closed['Date']))
            logger.info(
                f"🔄 Scanning for new inside bar pattern after trade execution...\n"
                f"   Excluding inside bars before: {format_ist_datetime(breakout_candle_time)}"
            )
            new_signal = _GET_ACTIVE_SIGNAL(
                candles, 
                previous_signal=None, 
                mark_signal_invalid=False,
                exclude_before_time=breakout_candle_time
            )
            
            if new_signal:
                self.active_signal = new_signal
                logger.info(
                    f"\n{'✨'*40}\n"
                    f"🆕 NEW INSIDE BAR DETECTED\n"
                    f"   Signal Time: {format_ist_datetime(new_signal['inside_bar_time'])}\n"
                    f"   New Range: {new_signal['range_low']:.2f} - {new_signal['range_high']:.2f}\n"
                    f"   Status: Active and tracking\n"
                    f"{'✨'*40}"
                )
            else:
                logger.info("⏳ No new inside bar found yet. Will continue scanning in next cycle.")
            
            result = {
                'status': status,
                'breakout_direction': breakout_direction,
                'signal_date': format_ist_date(active_signal['signal_time']),
                'signal_high': active_signal['range_high'],
                'signal_low': active_signal['range_low'],
                'latest_candle_close': entry_price,
                'strike': strike,
                'entry_price': entry_price,
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'order_id': order_response.get('order_id'),
                'order_status': order_response.get('status'),
                'order_message': order_response.get('message'),
                'available_margin': order_response.get('available_margin'),
                'required_margin': order_response.get('required_margin'),
                'simulated': order_response.get('simulated', not self.live_mode),
                'live_mode': self.live_mode,
                'execution_armed': self.execution_armed,
                'time': current_time_str
            }
            
            if status in ('breakout_confirmed', 'order_failed'):
                self._export_to_csv({
                    'Date': format_ist_date(now_ist),
                    'Time': now_ist.strftime("%H:%M:%S"),
                    'Signal_Date': format_ist_date(active_signal['signal_time']),
                    'Signal_High': f"{active_signal['range_high']:.2f}",
                    'Signal_Low': f"{active_signal['range_low']:.2f}",
                    'Current_Price': f"{entry_price:.2f}",
                    'Breakout_Direction': breakout_direction,
                    'Strike': strike,
                    'Entry_Price': f"{entry_price:.2f}",
                    'Stop_Loss': f"{stop_loss:.2f}",
                    'Take_Profit': f"{take_profit:.2f}",
                    'Order_ID': order_response.get('order_id', ''),
                    'Status': 'SUCCESS' if order_success else 'FAILED',
                    'Message': order_response.get('message', '')
                })
            
            self._print_summary(result)
            return result
        
        except Exception as err:
            logger.exception(f"Error running strategy: {err}")
            return {
                'status': 'error',
                'message': f'Error: {err}',
                'time': format_ist_datetime(ist_now())
            }
    
    def get_current_state(self) -> Dict:
        """
        Get current strategy state as JSON for UI consumption.
        
        Returns:
            Dictionary with current strategy state
        """
        state = {
            'timestamp': format_ist_datetime(ist_now()),
            'has_active_signal': self.active_signal is not None,
            'signal': None,
            'last_breakout_timestamp': None,
            'live_mode': self.live_mode,
            'execution_armed': self.execution_armed
        }
        
        if self.active_signal:
            state['signal'] = {
                'inside_bar_time': format_ist_datetime(self.active_signal['inside_bar_time']),
                'signal_time': format_ist_datetime(self.active_signal['signal_time']),
                'range_high': float(self.active_signal['range_high']),
                'range_low': float(self.active_signal['range_low']),
                'range_width': float(self.active_signal['range_high'] - self.active_signal['range_low']),
                'breakout_attempted': self.active_signal.get('breakout_attempted', False)
            }
        
        if hasattr(self, 'last_breakout_timestamp') and self.last_breakout_timestamp:
            state['last_breakout_timestamp'] = format_ist_datetime(self.last_breakout_timestamp)
        
        return state
    
    def _print_summary(self, result: Dict):
        """
        Print formatted strategy summary.
        
        Args:
            result: Strategy execution result dictionary
        """
        print("\n" + "="*70)
        print("INSIDE BAR BREAKOUT STRATEGY - EXECUTION SUMMARY")
        print("="*70)
        
        if result.get('status') in ('breakout_confirmed', 'order_failed'):
            print(f"✅ Inside Bar Detected on {result.get('signal_date', 'N/A')}")
            print(f"Signal Candle: High={result.get('signal_high', 0):.2f}, Low={result.get('signal_low', 0):.2f}")
            print(f"Latest Close: {result.get('latest_candle_close', 0):.2f}")
            
            direction = result.get('breakout_direction', '')
            if direction == 'CE':
                print(f"🟢 Breakout Confirmed: CE")
            elif direction == 'PE':
                print(f"🔴 Breakout Confirmed: PE")
            
            print(f"Strike: {result.get('strike', 'N/A')}")
            print(f"Entry Price: {result.get('entry_price', 0):.2f}")
            print(f"Stop Loss: {result.get('stop_loss', 0):.2f}")
            print(f"Take Profit: {result.get('take_profit', 0):.2f}")
            print(f"Order ID: {result.get('order_id', 'N/A')}")
            print(f"Order Status: {'SUCCESS' if result.get('order_status') else 'FAILED'}")
            if result.get('order_message'):
                print(f"Message: {result.get('order_message')}")
        
        elif result.get('status') == 'no_breakout':
            print(f"✅ Inside Bar Detected on {result.get('signal_date', 'N/A')}")
            print(f"Signal Candle: High={result.get('signal_high', 0):.2f}, Low={result.get('signal_low', 0):.2f}")
            print(f"Latest Closed Price: {result.get('last_closed_close', 0):.2f}")
            print("⏳ No breakout yet")
        
        elif result.get('status') == 'no_signal':
            print("📊 No inside bar pattern detected")
            if result.get('current_price'):
                print(f"Current Price: {result.get('current_price', 0):.2f}")
        
        elif result.get('status') == 'duplicate_breakout':
            print("⚠️ Breakout already processed for this candle. No new trade executed.")
        
        elif result.get('status') == 'missed_trade':
            print(f"🚨 MISSED TRADE DETECTED")
            print(f"Breakout Direction: {result.get('breakout_direction')} (would have been {'Call' if result.get('breakout_direction') == 'CE' else 'Put'})")
            print(f"Missed Signal from: {result.get('signal_date', 'N/A')}")
            print(f"Breakout occurred at: {result.get('breakout_candle_close_time', 'N/A')}")
            print(f"Reason: {result.get('missed_reason', 'Unknown')}")
            print(f"\n⏳ Status: Awaiting new inside bar pattern")
        
        elif result.get('status') == 'missed_trade_new_signal_found':
            print(f"🚨 MISSED TRADE - But NEW inside bar found!")
            print(f"Missed: {result.get('missed_breakout_direction')} breakout at {result.get('missed_breakout_time', 'N/A')}")
            print(f"\n✅ NEW Inside Bar Active:")
            print(f"Signal Date: {result.get('new_signal_date', 'N/A')}")
            print(f"New Range: {result.get('new_signal_low', 0):.2f} - {result.get('new_signal_high', 0):.2f}")
            print(f"Status: Tracking for next breakout")
        
        print(f"\nTime: {result.get('time', 'N/A')}")
        
        # Print current state
        current_state = self.get_current_state()
        print(f"\n📊 Current State:")
        print(f"   Active Signal: {'Yes' if current_state['has_active_signal'] else 'No'}")
        if current_state['has_active_signal']:
            print(f"   Signal Range: {current_state['signal']['range_low']:.2f} - {current_state['signal']['range_high']:.2f}")
            print(f"   Signal Time: {current_state['signal']['signal_time']}")
        
        print("="*70 + "\n")


def create_strategy_from_config(
    broker_config: Dict,
    market_data: Optional[MarketDataProvider] = None,
    live_mode: bool = True
) -> InsideBarBreakoutStrategy:
    """
    Factory function to create InsideBarBreakoutStrategy from configuration.
    
    Args:
        broker_config: Broker configuration dictionary
        market_data: Optional MarketDataProvider instance (creates new if None)
        live_mode: Live mode flag (default: True)
    
    Returns:
        InsideBarBreakoutStrategy instance
    """
    # Create broker instance
    broker = AngelOneBroker(broker_config)
    
    # Create market data provider if not provided
    if market_data is None:
        market_data = MarketDataProvider(broker)
    
    # Create strategy
    strategy = InsideBarBreakoutStrategy(
        broker=broker,
        market_data=market_data,
        symbol="NIFTY",
        lot_size=75,
        quantity_lots=1,
        live_mode=live_mode
    )
    
    return strategy

