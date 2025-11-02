"""
DesiQuant S3 Data Source
Streams NIFTY spot (1h), ATM options (1h), and expiry calendar directly from DesiQuant S3.
No local downloads required.
"""

from __future__ import annotations

import pandas as pd
from typing import Dict, Optional, List
from datetime import time
import warnings

# Suppress pandas resample deprecation warning for 'H' alias
# We're using '1h' (lowercase) which is correct, but pandas still warns
warnings.filterwarnings("ignore", category=FutureWarning, message=".*'H' is deprecated.*")

try:
    import s3fs
    S3FS_AVAILABLE = True
except ImportError:
    S3FS_AVAILABLE = False
    warnings.warn("s3fs not installed. Install with: pip install s3fs>=2024.3.1")

# ---------- Public S3 credentials (free read-only) ----------

S3_PARAMS: Dict = {
    "endpoint_url": "https://cbabd13f6c54798a9ec05df5b8070a6e.r2.cloudflarestorage.com",
    "key": "5c8ea9c516abfc78987bc98c70d2868a",
    "secret": "0cf64f9f0b64f6008cf5efe1529c6772daa7d7d0822f5db42a7c6a1e41b3cadf",
    "client_kwargs": {"region_name": "auto"},
}

# ---------- Symbol path mappings ----------

SYMBOL_SPOT_MAP = {
    "NIFTY": "NIFTY50",       # spot candles folder
    "NIFTY50": "NIFTY50",
    "BANKNIFTY": "BANKNIFTY",
    "FINNIFTY": "FINNIFTY",
    "MIDCPNIFTY": "MIDCPNIFTY",
}

SYMBOL_OPT_MAP = {
    "NIFTY": "NIFTY",         # options folder
    "NIFTY50": "NIFTY",
    "BANKNIFTY": "BANKNIFTY",
    "FINNIFTY": "FINNIFTY",
    "MIDCPNIFTY": "MIDCPNIFTY",
}

# ---------- Strikes catalog cache ----------

_STRIKES_CACHE = None
_FS_CACHE = None


def _fs():
    """Get or create s3fs filesystem instance."""
    global _FS_CACHE
    if _FS_CACHE is None:
        if not S3FS_AVAILABLE:
            raise RuntimeError("s3fs is required to stream from DesiQuant S3.")
        import s3fs
        _FS_CACHE = s3fs.S3FileSystem(**S3_PARAMS)
    return _FS_CACHE


def _load_strikes(symbol: str = "NIFTY") -> pd.DataFrame:
    """
    Streams the strikes catalog for the symbol.
    Path: s3://desiquant/data/strikes/nse/<SYMBOL>.parquet
    Columns typically: ['symbol','expiry','strike','type','exchange'] (wide list)
    Always returns DataFrame with 'expiry' and 'strike' columns (may be empty).
    """
    global _STRIKES_CACHE
    # Note: Cache could contain invalid data from previous runs, so we validate it
    if _STRIKES_CACHE is not None:
        # Ensure cached data has required columns
        if "expiry" in _STRIKES_CACHE.columns and "strike" in _STRIKES_CACHE.columns:
            return _STRIKES_CACHE
        else:
            # Clear invalid cache
            _STRIKES_CACHE = None
    
    try:
        sym_opt = SYMBOL_OPT_MAP.get(symbol.upper(), symbol)
        uri = f"s3://desiquant/data/strikes/nse/{sym_opt}.parquet"
        df = pd.read_parquet(uri, storage_options=S3_PARAMS)
        df.columns = [c.lower() for c in df.columns]
        
        # Ensure expiry column exists (normalize column name)
        try:
            df = _ensure_expiry_column(df)
        except (KeyError, ValueError) as e:
            warnings.warn(f"Could not normalize expiry column in strikes file: {e}")
            # Return empty strikes frame with correct schema
            return pd.DataFrame({
                "expiry": pd.to_datetime([]),
                "strike": []
            })
        
        # Ensure strike column exists
        strike_col = None
        lowmap = {c.lower(): c for c in df.columns}
        for candidate in ("strike", "strikeprice", "st", "k"):
            if candidate in lowmap:
                strike_col = lowmap[candidate]
                break
        
        if strike_col is None:
            warnings.warn(f"No strike-like column found in strikes file. Columns: {list(df.columns)}")
            return pd.DataFrame({
                "expiry": pd.to_datetime([]),
                "strike": []
            })
        
        # Normalize strike column name
        df = df.rename(columns={strike_col: "strike"})
        
        # Keep only expiry + strike (both CE/PE share strikes)
        # Double-check both columns exist before accessing
        if "expiry" not in df.columns or "strike" not in df.columns:
            warnings.warn(f"Missing required columns after normalization. Columns: {list(df.columns)}")
            return pd.DataFrame({
                "expiry": pd.to_datetime([]),
                "strike": []
            })
        
        df = df[["expiry", "strike"]].drop_duplicates().sort_values(["expiry","strike"])
        _STRIKES_CACHE = df
        return df
    except Exception as e:
        # Catch any unexpected errors during loading and return empty frame with correct schema
        warnings.warn(f"Error loading strikes file: {e}")
        return pd.DataFrame({
            "expiry": pd.to_datetime([]),
            "strike": []
        })


def _nearest_listed_strike(spot: float, expiry: pd.Timestamp, strikes_df: pd.DataFrame) -> Optional[int]:
    """Return the actually listed strike closest to spot for that expiry."""
    day_strikes = strikes_df.loc[strikes_df["expiry"].dt.date == expiry.date(), "strike"]
    if day_strikes.empty:
        return None
    target = float(spot)
    # choose strike with minimum absolute distance
    s = day_strikes.iloc[(day_strikes - target).abs().argmin()]
    return int(s)


# ---------- Helpers ----------

def _ensure_timestamp_column(df: pd.DataFrame) -> pd.DataFrame:
    """
    Creates/normalizes a 'timestamp' column from common variants or from a DatetimeIndex.
    Does not mutate the original df.
    """
    d = df.copy()
    # normalize column case first
    d.columns = [str(c).strip() for c in d.columns]
    lower = {c.lower(): c for c in d.columns}
    
    # candidates we'll accept for time
    candidates = ["timestamp", "datetime", "date", "time", "date_time", "date time", "ts"]
    
    for key in candidates:
        if key in lower:
            col = lower[key]
            d["timestamp"] = pd.to_datetime(d[col], errors="coerce", utc=False)
            break
    else:
        # no explicit time column; try index
        if isinstance(d.index, pd.DatetimeIndex):
            # Handle timezone-aware or naive DatetimeIndex
            if d.index.tz is not None:
                d["timestamp"] = d.index.tz_localize(None)
            else:
                d["timestamp"] = d.index
            d = d.reset_index(drop=True)
        else:
            raise KeyError(
                f"No time column found. Available columns: {list(d.columns)}. "
                "Expected one of: timestamp/datetime/date/time (any case), or a DatetimeIndex."
            )
    
    # final sanity
    if d["timestamp"].isna().all():
        raise ValueError("All timestamps parsed as NaT. Check source schema/timezone.")
    return d


def _ensure_ohlc_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalizes OHLC column names to lower-case 'open','high','low','close'.
    If missing, tries common alternates; else raises.
    """
    d = df.copy()
    # permissive mapping
    candidates = {
        "open":  ["open", "o", "Open", "OPEN"],
        "high":  ["high", "h", "High", "HIGH"],
        "low":   ["low", "l", "Low", "LOW"],
        "close": ["close", "c", "Close", "CLOSE", "last", "Last"]
    }
    out = {}
    lower = {c.lower(): c for c in d.columns}
    for std, opts in candidates.items():
        found = None
        for name in opts:
            if name.lower() in lower:
                found = lower[name.lower()]
                break
        if not found:
            raise KeyError(f"Missing OHLC column for '{std}'. Columns present: {list(d.columns)}")
        out[std] = d[found]
    # rebuild in the desired order
    return pd.concat(out, axis=1).reset_index(drop=True)


def _resample_to_hour(df: pd.DataFrame) -> pd.DataFrame:
    """
    Accepts any reasonable time/ohlc schema and returns:
    columns: timestamp, open, high, low, close (lower-case), 1h resampled.
    """
    d = _ensure_timestamp_column(df)
    d = d.sort_values("timestamp")
    d_ohlc = _ensure_ohlc_columns(d)
    
    # bring timestamp back
    d_ohlc.insert(0, "timestamp", d["timestamp"].reset_index(drop=True))
    
    d_ohlc = d_ohlc.set_index("timestamp")
    hourly = d_ohlc.resample("1h").agg({  # use '1h' instead of '1H' to avoid FutureWarning
        "open": "first",
        "high": "max",
        "low":  "min",
        "close":"last",
    }).dropna().reset_index()
    return hourly  # timestamp, open, high, low, close


def _ensure_expiry_column(df: pd.DataFrame) -> pd.DataFrame:
    """Return df with a real datetime 'expiry' column, regardless of source naming."""
    d = df.copy()
    d.columns = [str(c).strip() for c in d.columns]
    low = {c.lower(): c for c in d.columns}
    # Include 'date' as it's commonly used in CSV files
    for candidate in ("expiry", "exp", "expiry_date", "maturity", "maturitydate", "expdate", "exdate", "date"):
        if candidate in low:
            col = low[candidate]
            d["expiry"] = pd.to_datetime(d[col], errors="coerce")
            if d["expiry"].isna().all():
                raise ValueError("All expiry values parsed as NaT.")
            return d
    raise KeyError(f"No expiry-like column found. Columns: {list(d.columns)}")


def _ensure_symbol_filter(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Filter to symbol if a symbol/underlying column exists; otherwise return df unchanged."""
    low = {c.lower(): c for c in df.columns}
    for cname in ("symbol", "underlying", "name"):
        if cname in low:
            col = low[cname]
            return df[df[col].astype(str).str.upper() == symbol.upper()]
    return df


def _nearest_100(x: float) -> int:
    return int(round(x / 100.0) * 100)


def _load_parquet(path: str) -> pd.DataFrame:
    if not S3FS_AVAILABLE:
        raise RuntimeError("s3fs is required to stream from DesiQuant S3.")
    return pd.read_parquet(path, storage_options=S3_PARAMS)


def _load_csv(path: str) -> pd.DataFrame:
    if not S3FS_AVAILABLE:
        raise RuntimeError("s3fs is required to stream from DesiQuant S3.")
    return pd.read_csv(path, storage_options=S3_PARAMS)


# ---------- Loaders ----------

def _load_spot_1h(symbol: str) -> pd.DataFrame:
    """
    Spot comes as 1-min under: s3://desiquant/data/candles/{SYMBOL}/EQ.parquet.gz
    We resample to 1h and return OHLC with DatetimeIndex and columns Open/High/Low/Close (cased).
    """
    sym_spot = SYMBOL_SPOT_MAP.get(symbol.upper(), symbol)
    uri = f"s3://desiquant/data/candles/{sym_spot}/EQ.parquet.gz"
    try:
        spot_1m = _load_parquet(uri)
    except FileNotFoundError:
        # conservative fallback: try the raw symbol in case others differ
        alt_uri = f"s3://desiquant/data/candles/{symbol}/EQ.parquet.gz"
        spot_1m = _load_parquet(alt_uri)
    
    # normalize + resample
    spot_1h = _resample_to_hour(spot_1m)  # timestamp, open, high, low, close
    # rename to match engine expectations and set index
    out = spot_1h.rename(columns=str.capitalize).set_index("Timestamp")
    return out[["Open","High","Low","Close"]]


def _load_expiries(symbol: str) -> pd.DataFrame:
    """
    Return DataFrame with a single column 'expiry' (datetime).
    Tries, in order:
      1) CSV: s3://desiquant/data/expiries/nse.csv  (any schema)
      2) Strikes parquet: s3://desiquant/data/strikes/nse/<SYMBOL>.parquet
      3) Folder listing: s3://desiquant/data/candles/<SYMBOL_FOR_OPTIONS>/YYYY-MM-DD/
    """
    # 1) CSV
    try:
        csv_uri = "s3://desiquant/data/expiries/nse.csv"
        raw = _load_csv(csv_uri)
        raw = _ensure_symbol_filter(raw, symbol)
        raw = _ensure_expiry_column(raw)
        exp = raw[["expiry"]].dropna().drop_duplicates().sort_values("expiry")
        if not exp.empty:
            return exp
    except Exception as e:
        warnings.warn(f"Expiry CSV fallback: {e}")
    
    # 2) Strikes parquet
    try:
        strikes = _load_strikes(SYMBOL_OPT_MAP.get(symbol.upper(), symbol))
        # _load_strikes should always return DataFrame with 'expiry' column (even if empty)
        # Double-check it's a valid DataFrame with the required column
        if isinstance(strikes, pd.DataFrame) and "expiry" in strikes.columns:
            if not strikes.empty:
                exp = strikes[["expiry"]].drop_duplicates().sort_values("expiry")
                if not exp.empty:
                    return exp
    except Exception as e:
        warnings.warn(f"Expiry from strikes fallback failed: {e}")
    
    # 3) Folder listing
    try:
        fs = _fs()
        sym_opt = SYMBOL_OPT_MAP.get(symbol.upper(), symbol)
        base = f"desiquant/data/candles/{sym_opt}"
        candidates = fs.ls(base)
        dates = []
        for p in candidates:
            name = p.rstrip("/").split("/")[-1]
            # only directory names like YYYY-MM-DD
            try:
                dt = pd.to_datetime(name, errors="raise")
                dates.append(dt)
            except Exception:
                continue
        exp = pd.DataFrame({"expiry": sorted(set(dates))})
        if not exp.empty:
            return exp
    except Exception as e:
        warnings.warn(f"Expiry from folder listing failed: {e}")
    
    # Nothing worked
    warnings.warn("No expiries could be derived; returning empty calendar.")
    return pd.DataFrame({"expiry": pd.to_datetime([])})


def _option_uri(symbol: str, expiry: pd.Timestamp, strike: int, opt_type: str) -> str:
    """Generate the S3 URI for an option contract."""
    sym_opt = SYMBOL_OPT_MAP.get(symbol.upper(), symbol)
    exp_str = expiry.date().isoformat()
    return f"s3://desiquant/data/candles/{sym_opt}/{exp_str}/{strike}{opt_type}.parquet.gz"


def _option_exists(symbol: str, expiry: pd.Timestamp, strike: int, opt_type: str) -> bool:
    """Check if an option contract file exists in S3."""
    uri = _option_uri(symbol, expiry, strike, opt_type)
    # s3fs expects path without "s3://"
    path_without_s3 = uri.replace("s3://", "")
    return _fs().exists(path_without_s3)


def _load_option_contract_1h(symbol: str, expiry: pd.Timestamp, strike: int, opt_type: str) -> pd.DataFrame:
    """
    Option candles live at: s3://desiquant/data/candles/{SYMBOL}/{YYYY-MM-DD}/{STRIKE}{TYPE}.parquet.gz
    Returns hourly candles with required columns and metadata.
    """
    uri = _option_uri(symbol, expiry, strike, opt_type)
    df_1m = _load_parquet(uri)  # raises if truly missing
    df_1h = _resample_to_hour(df_1m)  # timestamp, open, high, low, close
    df_1h["expiry"] = pd.to_datetime(expiry)
    df_1h["strike"] = int(strike)
    df_1h["type"]   = opt_type.upper()
    return df_1h[["timestamp","open","high","low","close","expiry","strike","type"]]


def _build_options_frame(symbol: str, expiries: pd.DataFrame, spot_1h: pd.DataFrame,
                         start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """
    For each expiry ∈ [start, end], find ATM and load CE+PE hourly candles; concat all.
    Uses strikes catalog to find actual listed strikes and verifies files exist before reading.
    """
    # Guard: ensure expiry column exists before accessing it
    if "expiry" not in expiries.columns or expiries.empty:
        # Return empty options frame with correct schema
        return pd.DataFrame({
            "timestamp": pd.to_datetime([]),
            "open": [], "high": [], "low": [], "close": [],
            "expiry": pd.to_datetime([]), "strike": [], "type": []
        })
    
    frames: List[pd.DataFrame] = []
    exps = expiries[(expiries["expiry"] >= start) & (expiries["expiry"] <= end)].copy()
    strikes_df = _load_strikes(SYMBOL_OPT_MAP.get(symbol.upper(), symbol))
    
    for e in exps["expiry"]:
        # pick last close in the prior week window to anchor ATM selection
        mask = (spot_1h.index < e) & (spot_1h.index >= e - pd.Timedelta(days=7))
        if not mask.any():
            continue
        ref_close = float(spot_1h.loc[mask, "Close"].iloc[-1])
        
        # choose real, listed ATM (not just round(100))
        atm = _nearest_listed_strike(ref_close, e, strikes_df)
        if atm is None:
            continue
        
        # try CE/PE — and if the exact strike is missing, search neighbors ±(100,200,...)
        for side in ("CE","PE"):
            candidate = atm
            tried: List[int] = []
            found = False
            for step in [0, 50, 100, 150, 200, 250, 300]:   # widen if needed; NIFTY moved lot over years
                # Prefer 100-step ladders; add 50 only if catalog had such (older series sometimes 50)
                for s in {atm - step, atm + step}:
                    if s in tried or s <= 0:
                        continue
                    tried.append(s)
                    if _option_exists(symbol, e, s, side):
                        try:
                            df = _load_option_contract_1h(symbol, e, s, side)
                            df = df[(pd.to_datetime(df["timestamp"]) < e + pd.Timedelta(days=1))]
                            frames.append(df)
                            found = True
                            break
                        except Exception as ex:
                            warnings.warn(f"Read fail {symbol} {e.date()} {s}{side}: {ex}")
                if found:
                    break
            if not found:
                warnings.warn(f"No {side} file available near ATM for {symbol} {e.date()} (ATM={atm})")
    
    if frames:
        out = pd.concat(frames, ignore_index=True)
        out.sort_values("timestamp", inplace=True)
        return out
    
    # empty structure with correct columns
    return pd.DataFrame({
        "timestamp": pd.to_datetime([]),
        "open": [], "high": [], "low": [], "close": [],
        "expiry": pd.to_datetime([]), "strike": [], "type": []
    })


# ---------- Public API ----------

def stream_data(
    symbol: str = "NIFTY",
    start: str = "2021-01-01",
    end: str = "2021-03-31",
    bucket: Optional[str] = None,  # ignored (fixed public bucket)
    **kwargs
) -> Dict:
    """
    Returns:
      {
        'spot':     1h OHLC with DatetimeIndex and columns Open/High/Low/Close,
        'options':  hourly options with ['timestamp','open','high','low','close','expiry','strike','type'],
        'expiries': DataFrame(['expiry'])
      }
    """
    if not S3FS_AVAILABLE:
        raise RuntimeError("s3fs is required. Install: pip install s3fs>=2024.3.1 pyarrow>=15")

    # Parse dates
    start_dt = pd.to_datetime(start)
    end_dt   = pd.to_datetime(end)

    # 1) Spot (1h)
    try:
        spot_1h = _load_spot_1h(symbol)
    except FileNotFoundError as e:
        sym_spot = SYMBOL_SPOT_MAP.get(symbol.upper(), symbol)
        raise FileNotFoundError(
            f"Spot file not found. Tried '{sym_spot}/EQ.parquet.gz' "
            f"and '{symbol}/EQ.parquet.gz'. Original: {e}"
        )

    # Trim to a slightly wider window so ATM detection can see prior week
    spot_1h = spot_1h[(spot_1h.index >= start_dt - pd.Timedelta(days=10)) &
                      (spot_1h.index <= end_dt + pd.Timedelta(days=1))]

    # 2) Expiry calendar
    expiries = _load_expiries(symbol)

    # If we still don't have a valid 'expiry' column or it's empty, return spot-only
    if "expiry" not in expiries.columns or expiries.empty:
        warnings.warn("No valid expiries found; returning spot only (options empty).")
        # final clip to requested range
        spot_1h = spot_1h[(spot_1h.index >= start_dt) & (spot_1h.index <= end_dt)]
        empty_opts = pd.DataFrame({
            "timestamp": pd.to_datetime([]),
            "open": [], "high": [], "low": [], "close": [],
            "expiry": pd.to_datetime([]), "strike": [], "type": []
        })
        return {"spot": spot_1h, "options": empty_opts, "expiries": expiries}

    # 3) Options (only if expiries valid)
    options_1h = _build_options_frame(symbol, expiries, spot_1h, start_dt, end_dt)

    # final clip to requested period
    spot_1h = spot_1h[(spot_1h.index >= start_dt) & (spot_1h.index <= end_dt)]
    return {"spot": spot_1h, "options": options_1h, "expiries": expiries}
