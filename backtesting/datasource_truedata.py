"""
TrueData API Data Source
Streams NIFTY spot (1h), ATM options (1h), and expiry calendar from TrueData Professional API.
Requires subscription: https://truedata.in
"""

from __future__ import annotations

import pandas as pd
from typing import Dict, Optional, List
from datetime import datetime, timedelta
import warnings
import time

try:
    from truedata_ws.websocket.TD import TD
    TRUEDATA_AVAILABLE = True
except ImportError:
    TRUEDATA_AVAILABLE = False
    warnings.warn("truedata-ws not installed. Install with: pip install truedata-ws")


# ---------- Symbol mappings ----------

SYMBOL_MAP = {
    "NIFTY": "NIFTY",
    "NIFTY50": "NIFTY",
    "BANKNIFTY": "BANKNIFTY",
    "FINNIFTY": "FINNIFTY",
    "MIDCPNIFTY": "MIDCPNIFTY",
}

# TrueData symbol format for options: SYMBOL{DDMMMYY}{STRIKE}{CE/PE}
# Example: NIFTY24NOV24000CE, BANKNIFTY24NOV50000PE


def _format_truedata_date(dt: pd.Timestamp) -> str:
    """Format date as DDMMMYY for TrueData symbol format (e.g., 24NOV24)."""
    return dt.strftime('%d%b%y').upper()


def _parse_truedata_date(date_str: str) -> pd.Timestamp:
    """Parse DDMMMYY format back to datetime (e.g., 24NOV24 -> 2024-11-24)."""
    return pd.to_datetime(date_str, format='%d%b%y')


def _get_client(username: str, password: str) -> 'TD':
    """Initialize TrueData client."""
    if not TRUEDATA_AVAILABLE:
        raise RuntimeError("truedata-ws is required. Install: pip install truedata-ws")
    
    # Initialize TrueData client
    td = TD(username, password)
    return td


def _load_spot_1h(td: 'TD', symbol: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """
    Fetch 1h spot OHLC data from TrueData.
    Returns DataFrame with DatetimeIndex and columns: Open, High, Low, Close
    """
    sym = SYMBOL_MAP.get(symbol.upper(), symbol)
    
    # TrueData get_historic_data parameters:
    # - symbol: str
    # - from_date: "YYYY-MM-DD"
    # - to_date: "YYYY-MM-DD"
    # - duration: "1h" (or "1m", "5m", "15m", "1d", etc.)
    
    try:
        data = td.get_historic_data(
            symbol=sym,
            from_date=start.strftime('%Y-%m-%d'),
            to_date=end.strftime('%Y-%m-%d'),
            duration='1h'
        )
        
        if data is None or not data:
            raise ValueError(f"No spot data returned for {sym}")
        
        # Convert to DataFrame
        # TrueData returns list of lists: [[timestamp, open, high, low, close, volume], ...]
        df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        # Convert timestamp to datetime and set as index
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')  # TrueData uses Unix timestamp
        df = df.set_index('timestamp')
        
        # Rename columns to match expected format (capitalized)
        df = df.rename(columns={
            'open': 'Open',
            'high': 'High',
            'low': 'Low',
            'close': 'Close'
        })
        
        # Return only OHLC columns (drop volume)
        return df[['Open', 'High', 'Low', 'Close']]
        
    except Exception as e:
        raise RuntimeError(f"Failed to fetch spot data for {sym}: {e}")


def _load_expiries(td: 'TD', symbol: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """
    Get expiry dates for the symbol within the date range.
    For NIFTY: Weekly expiries (Thursdays), Monthly expiries (last Thursday)
    
    Returns DataFrame with column: expiry
    """
    # For NIFTY options, expiries are every Thursday
    # We'll generate Thursday dates between start and end
    
    expiries = []
    current = start
    
    while current <= end:
        # Find next Thursday (weekday 3)
        days_ahead = (3 - current.weekday()) % 7
        if days_ahead == 0 and current.time() > pd.Timestamp('15:30').time():
            days_ahead = 7
        
        expiry = current + pd.Timedelta(days=days_ahead)
        
        if expiry <= end:
            expiries.append(expiry.normalize())  # Remove time component
        
        # Move to next week
        current = expiry + pd.Timedelta(days=1)
    
    # Return as DataFrame
    return pd.DataFrame({'expiry': pd.to_datetime(expiries)})


def _format_option_symbol(symbol: str, expiry: pd.Timestamp, strike: int, opt_type: str) -> str:
    """
    Format option symbol for TrueData API.
    Format: SYMBOL{DDMMMYY}{STRIKE}{CE/PE}
    Example: NIFTY24NOV24000CE
    """
    sym = SYMBOL_MAP.get(symbol.upper(), symbol)
    date_str = _format_truedata_date(expiry)
    return f"{sym}{date_str}{strike}{opt_type.upper()}"


def _nearest_strike(spot_price: float, strike_step: int = 50) -> int:
    """Round spot price to nearest strike (default: 50 for NIFTY)."""
    return int(round(spot_price / strike_step) * strike_step)


def _load_option_contract_1h(
    td: 'TD',
    symbol: str,
    expiry: pd.Timestamp,
    strike: int,
    opt_type: str,
    start: pd.Timestamp,
    end: pd.Timestamp
) -> Optional[pd.DataFrame]:
    """
    Fetch 1h option OHLC data for a specific contract.
    Returns DataFrame with columns: timestamp, open, high, low, close, expiry, strike, type
    """
    option_symbol = _format_option_symbol(symbol, expiry, strike, opt_type)
    
    try:
        # Add small delay to respect rate limits
        time.sleep(0.2)
        
        data = td.get_historic_data(
            symbol=option_symbol,
            from_date=start.strftime('%Y-%m-%d'),
            to_date=min(expiry, end).strftime('%Y-%m-%d'),  # Don't go past expiry
            duration='1h'
        )
        
        if data is None or not data:
            return None
        
        # Convert to DataFrame
        df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
        
        # Add metadata
        df['expiry'] = expiry
        df['strike'] = strike
        df['type'] = opt_type.upper()
        
        # Keep only data before expiry
        df = df[df['timestamp'] < expiry + pd.Timedelta(days=1)]
        
        return df[['timestamp', 'open', 'high', 'low', 'close', 'expiry', 'strike', 'type']]
        
    except Exception as e:
        warnings.warn(f"Failed to fetch {option_symbol}: {e}")
        return None


def _build_options_frame(
    td: 'TD',
    symbol: str,
    expiries: pd.DataFrame,
    spot_1h: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    strike_step: int = 50
) -> pd.DataFrame:
    """
    For each expiry in [start, end], find ATM and load CE+PE hourly candles.
    Concatenates all option contracts into a single DataFrame.
    """
    frames: List[pd.DataFrame] = []
    
    # Filter expiries to date range
    exps = expiries[(expiries['expiry'] >= start) & (expiries['expiry'] <= end)].copy()
    
    for expiry in exps['expiry']:
        # Find ATM based on spot price ~1 week before expiry
        mask = (spot_1h.index < expiry) & (spot_1h.index >= expiry - pd.Timedelta(days=7))
        
        if not mask.any():
            continue
        
        ref_close = float(spot_1h.loc[mask, 'Close'].iloc[-1])
        atm = _nearest_strike(ref_close, strike_step)
        
        # Try to load ATM CE and PE
        for opt_type in ['CE', 'PE']:
            # Try ATM first, then nearby strikes if ATM fails
            for offset in [0, strike_step, -strike_step, 2*strike_step, -2*strike_step]:
                strike = atm + offset
                
                if strike <= 0:
                    continue
                
                df = _load_option_contract_1h(td, symbol, expiry, strike, opt_type, start, end)
                
                if df is not None and not df.empty:
                    frames.append(df)
                    break  # Found data, move to next option type
        
        # Rate limiting: pause between expiries
        time.sleep(0.3)
    
    if frames:
        out = pd.concat(frames, ignore_index=True)
        out.sort_values('timestamp', inplace=True)
        return out
    
    # Return empty DataFrame with correct schema
    return pd.DataFrame({
        'timestamp': pd.to_datetime([]),
        'open': [], 'high': [], 'low': [], 'close': [],
        'expiry': pd.to_datetime([]), 'strike': [], 'type': []
    })


# ---------- Public API ----------

def stream_data(
    symbol: str = "NIFTY",
    start: str = "2021-01-01",
    end: str = "2021-03-31",
    username: Optional[str] = None,
    password: Optional[str] = None,
    strike_step: int = 50,  # 50 for NIFTY, 100 for BANKNIFTY
    **kwargs
) -> Dict:
    """
    Fetch historical data from TrueData API.
    
    Args:
        symbol: Trading symbol (NIFTY, BANKNIFTY, etc.)
        start: Start date (YYYY-MM-DD)
        end: End date (YYYY-MM-DD)
        username: TrueData username
        password: TrueData password
        strike_step: Strike price step (50 for NIFTY, 100 for BANKNIFTY)
        
    Returns:
        {
            'spot': 1h OHLC with DatetimeIndex and columns Open/High/Low/Close,
            'options': hourly options with ['timestamp','open','high','low','close','expiry','strike','type'],
            'expiries': DataFrame(['expiry'])
        }
    """
    if not TRUEDATA_AVAILABLE:
        raise RuntimeError("truedata-ws is required. Install: pip install truedata-ws")
    
    if not username or not password:
        raise ValueError("TrueData username and password are required")
    
    # Parse dates
    start_dt = pd.to_datetime(start)
    end_dt = pd.to_datetime(end)
    
    # Initialize TrueData client
    td = _get_client(username, password)
    
    # 1) Fetch spot data (1h)
    print(f"Fetching spot data for {symbol} from {start} to {end}...")
    spot_1h = _load_spot_1h(td, symbol, start_dt, end_dt)
    
    # Extend window for ATM detection (need prior week data)
    spot_window_start = start_dt - pd.Timedelta(days=10)
    if spot_window_start < spot_1h.index.min():
        # Fetch additional spot data if needed
        spot_extended = _load_spot_1h(td, symbol, spot_window_start, start_dt)
        spot_1h = pd.concat([spot_extended, spot_1h]).sort_index()
    
    # 2) Get expiries
    print(f"Generating expiry calendar...")
    expiries = _load_expiries(td, symbol, start_dt, end_dt)
    
    # 3) Fetch options data
    print(f"Fetching options data (this may take a while)...")
    options_1h = _build_options_frame(td, symbol, expiries, spot_1h, start_dt, end_dt, strike_step)
    
    # Final trim to requested period
    spot_1h = spot_1h[(spot_1h.index >= start_dt) & (spot_1h.index <= end_dt)]
    
    print(f"✅ Data fetch complete:")
    print(f"   - Spot: {len(spot_1h)} candles")
    print(f"   - Options: {len(options_1h)} candles")
    print(f"   - Expiries: {len(expiries)} dates")
    
    return {
        'spot': spot_1h,
        'options': options_1h,
        'expiries': expiries
    }
