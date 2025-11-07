"""
Market Data API Data Source
Fetches historical NIFTY spot and options data from marketdata.app API for backtesting.
API Documentation: https://www.marketdata.app/docs/api/options/chain
"""

from __future__ import annotations

import pandas as pd
import requests
from typing import Dict, Optional, List
from datetime import datetime, timedelta
import warnings
import time
from logzero import logger

# ---------- Configuration ----------

DEFAULT_API_URL = "https://api.marketdata.app/v1"
REQUEST_DELAY = 0.2  # Delay between requests to respect rate limits (200ms)

# Symbol mapping: NIFTY index to Market Data API symbols
SYMBOL_MAP = {
    "NIFTY": "NIFTY",
    "NIFTY50": "NIFTY",
    "BANKNIFTY": "BANKNIFTY",
    "FINNIFTY": "FINNIFTY",
}

# Strike rounding (NIFTY = 50, BANKNIFTY = 100)
STRIKE_STEP = {
    "NIFTY": 50,
    "BANKNIFTY": 100,
    "FINNIFTY": 50,
}


class MarketDataAPIError(Exception):
    """Custom exception for Market Data API errors"""
    pass


class MarketDataSource:
    """
    Market Data API data source for backtesting.
    Fetches historical option chains and spot data.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Market Data API source.
        
        Args:
            api_key: Market Data API key (optional for AAPL testing, required for other tickers)
        """
        self.api_key = api_key
        self.base_url = DEFAULT_API_URL
        self.session = requests.Session()
        
        # Set headers
        if self.api_key:
            self.session.headers.update({"Authorization": f"Bearer {self.api_key}"})
    
    def _make_request(self, endpoint: str, params: Optional[Dict] = None) -> Dict:
        """
        Make API request with error handling and rate limiting.
        
        Args:
            endpoint: API endpoint path
            params: Query parameters
            
        Returns:
            JSON response as dictionary
            
        Raises:
            MarketDataAPIError: If API request fails
        """
        url = f"{self.base_url}/{endpoint}"
        
        try:
            # Add delay to respect rate limits
            time.sleep(REQUEST_DELAY)
            
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            # Check for API-level errors
            if data.get("s") == "error":
                error_msg = data.get("errmsg", "Unknown API error")
                raise MarketDataAPIError(f"API Error: {error_msg}")
            
            return data
            
        except requests.exceptions.RequestException as e:
            raise MarketDataAPIError(f"Request failed: {e}")
    
    def _get_option_chain(
        self,
        symbol: str,
        date: Optional[str] = None,
        expiration: Optional[str] = None,
        strike: Optional[int] = None,
        side: Optional[str] = None,
        **filters
    ) -> pd.DataFrame:
        """
        Fetch option chain from Market Data API.
        
        Args:
            symbol: Underlying symbol (e.g., "NIFTY")
            date: Historical date in YYYY-MM-DD format (optional, omit for live)
            expiration: Filter by expiration date YYYY-MM-DD (optional)
            strike: Filter by strike price (optional)
            side: Filter by side "call" or "put" (optional)
            **filters: Additional filters (range, dte, monthly, etc.)
            
        Returns:
            DataFrame with columns: optionSymbol, underlying, expiration, strike, side, firstTraded
        """
        endpoint = f"options/chain/{symbol}"
        
        params = {}
        if date:
            params["date"] = date
        if expiration:
            params["expiration"] = expiration
        if strike:
            params["strike"] = strike
        if side:
            params["side"] = side
        
        # Add additional filters
        params.update(filters)
        
        try:
            data = self._make_request(endpoint, params)
            
            # Parse response
            if not data.get("optionSymbol"):
                return pd.DataFrame()
            
            # Convert to DataFrame
            df = pd.DataFrame({
                "optionSymbol": data["optionSymbol"],
                "underlying": data["underlying"],
                "expiration": pd.to_datetime(data["expiration"]),
                "strike": data["strike"],
                "side": data["side"],
                "firstTraded": pd.to_datetime(data.get("firstTraded", data["expiration"]))
            })
            
            return df
            
        except MarketDataAPIError as e:
            logger.warning(f"Failed to fetch option chain: {e}")
            return pd.DataFrame()
    
    def _get_option_quotes(
        self,
        option_symbols: List[str],
        date: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Fetch option quotes (OHLCV) for multiple option symbols.
        
        Args:
            option_symbols: List of option symbols
            date: Historical date in YYYY-MM-DD format (optional)
            
        Returns:
            DataFrame with columns: timestamp, open, high, low, close, volume, 
                                   expiration, strike, side
        """
        all_data = []
        
        for symbol in option_symbols:
            try:
                endpoint = f"options/quotes/{symbol}"
                params = {}
                if date:
                    params["date"] = date
                
                data = self._make_request(endpoint, params)
                
                # Parse OHLCV data
                if "timestamp" in data:
                    quote = {
                        "timestamp": pd.to_datetime(data["timestamp"], unit="s"),
                        "open": data.get("open", data.get("bid", 0)),
                        "high": data.get("high", data.get("bid", 0)),
                        "low": data.get("low", data.get("ask", 0)),
                        "close": data.get("close", data.get("mid", 0)),
                        "volume": data.get("volume", 0),
                        "expiration": pd.to_datetime(data.get("expiration")),
                        "strike": data.get("strike"),
                        "side": data.get("side", "").upper()
                    }
                    all_data.append(quote)
                
            except MarketDataAPIError as e:
                logger.warning(f"Failed to fetch quote for {symbol}: {e}")
                continue
        
        if not all_data:
            return pd.DataFrame()
        
        return pd.DataFrame(all_data)
    
    def _get_candles(
        self,
        symbol: str,
        resolution: str,
        from_date: str,
        to_date: str
    ) -> pd.DataFrame:
        """
        Fetch historical candles for a symbol.
        
        Args:
            symbol: Trading symbol
            resolution: Candle resolution (e.g., "1h", "D")
            from_date: Start date in YYYY-MM-DD format
            to_date: End date in YYYY-MM-DD format
            
        Returns:
            DataFrame with columns: timestamp, open, high, low, close, volume
        """
        endpoint = f"stocks/candles/{resolution}/{symbol}"
        
        params = {
            "from": from_date,
            "to": to_date
        }
        
        try:
            data = self._make_request(endpoint, params)
            
            if not data.get("t"):
                return pd.DataFrame()
            
            # Convert to DataFrame
            df = pd.DataFrame({
                "timestamp": pd.to_datetime(data["t"], unit="s"),
                "open": data["o"],
                "high": data["h"],
                "low": data["l"],
                "close": data["c"],
                "volume": data.get("v", [0] * len(data["t"]))
            })
            
            return df
            
        except MarketDataAPIError as e:
            logger.warning(f"Failed to fetch candles: {e}")
            return pd.DataFrame()
    
    def _build_option_ohlc(
        self,
        symbol: str,
        expiries: List[pd.Timestamp],
        strikes: List[int],
        start_date: str,
        end_date: str
    ) -> pd.DataFrame:
        """
        Build hourly OHLC data for options by fetching chains for each date.
        
        Args:
            symbol: Underlying symbol
            expiries: List of expiry dates to fetch
            strikes: List of strikes to fetch
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            
        Returns:
            DataFrame with columns: timestamp, open, high, low, close, 
                                   expiration, strike, type (CE/PE)
        """
        all_data = []
        
        # Generate date range
        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(end_date)
        dates = pd.date_range(start_dt, end_dt, freq="D")
        
        logger.info(f"Fetching option data for {len(dates)} days, {len(expiries)} expiries, {len(strikes)} strikes")
        
        for date in dates:
            date_str = date.strftime("%Y-%m-%d")
            
            for expiry in expiries:
                # Skip if expiry is before this date
                if expiry.date() < date.date():
                    continue
                
                expiry_str = expiry.strftime("%Y-%m-%d")
                
                for strike in strikes:
                    # Fetch CE and PE
                    for side in ["call", "put"]:
                        try:
                            chain = self._get_option_chain(
                                symbol=symbol,
                                date=date_str,
                                expiration=expiry_str,
                                strike=strike,
                                side=side
                            )
                            
                            if not chain.empty:
                                # For simplicity, create synthetic hourly data
                                # In production, you'd fetch actual intraday data
                                # Market Data API provides daily data, so we simulate hourly
                                
                                # Get the option symbol
                                opt_symbol = chain.iloc[0]["optionSymbol"]
                                
                                # Fetch quote for this option
                                quotes = self._get_option_quotes([opt_symbol], date_str)
                                
                                if not quotes.empty:
                                    quote = quotes.iloc[0]
                                    
                                    # Create hourly bars (9:30 to 15:30 IST)
                                    # Note: This is simplified - actual data would need proper timezone handling
                                    for hour in range(9, 16):
                                        timestamp = pd.Timestamp(date.year, date.month, date.day, hour, 30)
                                        
                                        all_data.append({
                                            "timestamp": timestamp,
                                            "open": quote["open"],
                                            "high": quote["high"],
                                            "low": quote["low"],
                                            "close": quote["close"],
                                            "expiry": expiry,
                                            "strike": strike,
                                            "type": "CE" if side == "call" else "PE"
                                        })
                        
                        except Exception as e:
                            logger.debug(f"Failed to fetch {side} {strike} for {date_str}: {e}")
                            continue
        
        if not all_data:
            logger.warning("No option data fetched")
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", 
                                        "expiry", "strike", "type"])
        
        df = pd.DataFrame(all_data)
        df = df.sort_values("timestamp")
        return df


def stream_data(
    symbol: str = "NIFTY",
    start: str = "2021-01-01",
    end: str = "2021-03-31",
    api_key: Optional[str] = None,
    **kwargs
) -> Dict:
    """
    Fetch historical data from Market Data API for backtesting.
    
    Args:
        symbol: Underlying symbol (e.g., "NIFTY", "BANKNIFTY")
        start: Start date in YYYY-MM-DD format
        end: End date in YYYY-MM-DD format
        api_key: Market Data API key (optional for AAPL, required for others)
        **kwargs: Additional parameters (unused, for compatibility)
    
    Returns:
        Dictionary with:
            - spot: 1h OHLC DataFrame (DatetimeIndex, columns: Open/High/Low/Close)
            - options: 1h options OHLC DataFrame (columns: timestamp/open/high/low/close/expiry/strike/type)
            - expiries: DataFrame with expiry dates (column: expiry)
    
    Note:
        Market Data API provides daily option data. This implementation creates
        synthetic hourly data by replicating daily values across trading hours.
        For production use, consider using a different API that provides intraday data,
        or implement proper intraday interpolation logic.
    """
    logger.info(f"Fetching data from Market Data API: {symbol} from {start} to {end}")
    
    # Initialize source
    source = MarketDataSource(api_key=api_key)
    
    # Map symbol
    api_symbol = SYMBOL_MAP.get(symbol.upper(), symbol)
    
    # Parse dates
    start_dt = pd.to_datetime(start)
    end_dt = pd.to_datetime(end)
    
    # ========== 1. FETCH SPOT DATA (1h candles) ==========
    
    logger.info("Fetching spot data (1h candles)...")
    try:
        spot_1h = source._get_candles(
            symbol=api_symbol,
            resolution="1h",
            from_date=start,
            to_date=end
        )
        
        if spot_1h.empty:
            raise MarketDataAPIError("No spot data available")
        
        # Convert to expected format (DatetimeIndex, capitalized columns)
        spot_1h = spot_1h.rename(columns={
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume"
        })
        spot_1h = spot_1h.set_index("timestamp")
        spot_1h = spot_1h[["Open", "High", "Low", "Close"]]
        
        logger.info(f"✓ Fetched {len(spot_1h)} spot candles")
        
    except Exception as e:
        logger.error(f"Failed to fetch spot data: {e}")
        raise
    
    # ========== 2. FETCH EXPIRY CALENDAR ==========
    
    logger.info("Fetching expiry calendar...")
    try:
        # Get option chain for date range to extract expiries
        chain_sample = source._get_option_chain(
            symbol=api_symbol,
            from_date=start,
            to_date=end
        )
        
        if chain_sample.empty:
            logger.warning("No option chain data available, using synthetic expiries")
            # Generate weekly expiries (Thursdays for NIFTY)
            expiries_list = pd.date_range(start_dt, end_dt, freq="W-THU")
            expiries = pd.DataFrame({"expiry": expiries_list})
        else:
            expiries = pd.DataFrame({
                "expiry": chain_sample["expiration"].unique()
            })
            expiries["expiry"] = pd.to_datetime(expiries["expiry"])
            expiries = expiries.sort_values("expiry").drop_duplicates()
        
        logger.info(f"✓ Found {len(expiries)} expiry dates")
        
    except Exception as e:
        logger.warning(f"Failed to fetch expiries, using synthetic: {e}")
        expiries_list = pd.date_range(start_dt, end_dt, freq="W-THU")
        expiries = pd.DataFrame({"expiry": expiries_list})
    
    # ========== 3. FETCH OPTIONS DATA (1h) ==========
    
    logger.info("Fetching options data (1h)...")
    try:
        # Determine ATM strikes for each expiry
        strike_step = STRIKE_STEP.get(symbol.upper(), 50)
        
        # Get average spot price to determine strike range
        avg_spot = spot_1h["Close"].mean()
        atm_base = round(avg_spot / strike_step) * strike_step
        
        # Fetch strikes around ATM (±500 points for NIFTY)
        strike_range = 500
        strikes = list(range(
            int(atm_base - strike_range),
            int(atm_base + strike_range + strike_step),
            strike_step
        ))
        
        logger.info(f"Fetching options for {len(strikes)} strikes around ATM {atm_base}")
        
        # Build option OHLC data
        options_1h = source._build_option_ohlc(
            symbol=api_symbol,
            expiries=expiries["expiry"].tolist(),
            strikes=strikes,
            start_date=start,
            end_date=end
        )
        
        if options_1h.empty:
            logger.warning("No options data fetched, returning empty options DataFrame")
            options_1h = pd.DataFrame(columns=[
                "timestamp", "open", "high", "low", "close",
                "expiry", "strike", "type"
            ])
        else:
            logger.info(f"✓ Fetched {len(options_1h)} option data points")
        
    except Exception as e:
        logger.error(f"Failed to fetch options data: {e}")
        # Return empty options DataFrame to allow backtest to run with spot only
        options_1h = pd.DataFrame(columns=[
            "timestamp", "open", "high", "low", "close",
            "expiry", "strike", "type"
        ])
    
    # ========== RETURN DATA ==========
    
    return {
        "spot": spot_1h,
        "options": options_1h,
        "expiries": expiries
    }


# Convenience function for testing
def test_connection(api_key: Optional[str] = None) -> bool:
    """
    Test Market Data API connection.
    
    Args:
        api_key: API key (optional for AAPL testing)
    
    Returns:
        True if connection successful, False otherwise
    """
    try:
        source = MarketDataSource(api_key=api_key)
        
        # Test with AAPL (no API key required)
        chain = source._get_option_chain("AAPL")
        
        if not chain.empty:
            logger.info("✓ Market Data API connection successful")
            return True
        else:
            logger.warning("Market Data API returned empty data")
            return False
            
    except Exception as e:
        logger.error(f"Market Data API connection failed: {e}")
        return False
