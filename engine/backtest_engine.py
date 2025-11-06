"""
Backtest Engine for historical strategy testing

— 1h close breakout of locked Signal Candle (no 15m logic)

— Option-premium simulation with trailing SL + expiry rules

"""

from __future__ import annotations

import pandas as pd
import numpy as np
import math
from typing import Dict, List, Optional
from datetime import datetime, time, timedelta
from logzero import logger

# Reuse your live strategy helpers
from engine.strategy_engine import detect_inside_bar  # keep using this for backward compatibility
from engine.inside_bar_breakout_strategy import InsideBarBreakoutStrategy  # NEW: Use new strategy


# ========== PATCH A: Utility Functions (backtest-only enhancements) ==========

def _atr_from_ohlc(df, n=14):
    """ATR on underlying (1h). df has Open/High/Low/Close."""
    h = df['High'].astype(float)
    l = df['Low'].astype(float)
    c = df['Close'].astype(float)
    prev_c = c.shift(1)
    tr = pd.concat([
        (h - l),
        (h - prev_c).abs(),
        (l - prev_c).abs()
    ], axis=1).max(axis=1)
    atr = tr.rolling(n, min_periods=n).mean()
    return atr


def _ema(series, n):
    return series.ewm(span=n, adjust=False).mean()


def _ema_slope_up(df, n=20):
    """Simple regime check: EMA slope >= 0 → uptrend bias."""
    ema = _ema(df['Close'].astype(float), n)
    slope = ema.diff(n)  # n-bar delta
    return slope.iloc[-1] >= 0


def _atr_pct(df, n=14):
    atr = _atr_from_ohlc(df, n)
    close = df['Close'].astype(float)
    return (atr / close) * 100.0


def _chandelier_trail(prem_series, lookback=6, mult=2.0, direction='CE'):
    """
    Returns trailing stop series on premium based on chandelier exit.
    direction CE trails on lows, PE trails on highs (premium).
    prem_series must be a DataFrame with columns: open/high/low/close
    """
    hi = prem_series['high'].astype(float)
    lo = prem_series['low'].astype(float)
    cl = prem_series['close'].astype(float)
    # ATR on premium (true range on premium bars)
    prev_c = cl.shift(1)
    tr = pd.concat([(hi - lo), (hi - prev_c).abs(), (lo - prev_c).abs()], axis=1).max(axis=1)
    atrp = tr.rolling(lookback, min_periods=lookback).mean()
    if direction == 'CE':
        ref = hi.rolling(lookback, min_periods=lookback).max()
        trail = ref - mult * atrp
    else:
        ref = lo.rolling(lookback, min_periods=lookback).min()
        trail = ref + mult * atrp
    return trail


def _hhmm(ts):
    """Extract hour, minute from timestamp."""
    return (ts.hour, ts.minute)


def _parse_hhmm(s, default=(0, 0)):
    """Parse 'HH:MM' string to (hour, minute) tuple."""
    try:
        h, m = map(int, s.split(":"))
        return (h, m)
    except Exception:
        return default


class BacktestEngine:
    """
    Backtesting framework with trade simulation and result calculation.
    - Uses 1h close breakout of the locked signal candle
    - Works with real options_df (preferred) or synthetic premium fallback
    """

    def __init__(self, config: Dict):
        self.config = config or {}
        self.trades: List[Dict] = []
        self.equity_curve: List[float] = []
        
        # ========== CAPITAL TRACKING (backtest-only analysis) ==========
        self.capital_exhausted = False
        self.capital_exhausted_at_trade = None
        self.capital_requirements: List[float] = []
        
        # ========== TRAILING STOP LOSS ANALYSIS (backtest-only) ==========
        self.winning_trades_trail_exit = 0  # Count of winning trades cut by trailing SL
        
        # ========== PATCH B: Feature flags (backtest-only) ==========
        self.flags = {
            "use_atr_filter": bool(self.config.get("strategy", {}).get("use_atr_filter", False)),
            "use_regime_filter": bool(self.config.get("strategy", {}).get("use_regime_filter", False)),
            "use_distance_guard": bool(self.config.get("strategy", {}).get("use_distance_guard", False)),
            "use_tiered_exits": bool(self.config.get("strategy", {}).get("use_tiered_exits", False)),
            "use_expiry_protocol": bool(self.config.get("strategy", {}).get("use_expiry_protocol", False)),
            "use_directional_sizing": bool(self.config.get("strategy", {}).get("use_directional_sizing", False)),
        }
        self.params = self.config.get("strategy", {})
        self.sizing = self.config.get("sizing", {})
        
        # Strike selection configuration
        self.strike_offset_base = self.config.get("strike_offset_base", 0)
        self.strike_is_itm = self.config.get("strike_is_itm", False)
        self.strike_is_otm = self.config.get("strike_is_otm", False)

    # ------------- Public API -------------

    def run_backtest(
        self,
        data_1h: pd.DataFrame,
        data_15m: Optional[pd.DataFrame] = None,   # kept for backward-compat (ignored by 1h breakout)
        initial_capital: float = 100000.0,
        *,
        options_df: Optional[pd.DataFrame] = None,   # NEW (safe default)
        expiries_df: Optional[pd.DataFrame] = None  # NEW (safe default)
    ) -> Dict:
        """
        Run the backtest.

        Args:
            data_1h: 1-hour OHLC(V) DataFrame indexed by Timestamp.
                     Expected columns (case-insensitive): Open, High, Low, Close
            data_15m: kept only for legacy signature (ignored by 1h breakout logic)
            initial_capital: starting capital
            options_df: (optional) 1-hour OHLC for options with columns:
                        ['timestamp','open','high','low','close','expiry','strike','type']
                        type ∈ {'CE','PE'}, expiry as date/datetime
            expiries_df: (optional) expiry calendar with column 'expiry'

        Returns:
            Results dictionary with trades, PnL, equity, etc.
        """
        self.trades = []
        self.equity_curve = [initial_capital]
        current_capital = initial_capital

        # --- config defaults ---
        strat = self.config.get('strategy', {})
        self.pct_sl = float(strat.get('premium_sl_pct', 35.0)) / 100.0  # 35%
        self.partial_lock_1 = float(strat.get('lock1_gain_pct', 60.0)) / 100.0  # +60%
        self.partial_lock_2 = float(strat.get('lock2_gain_pct', 80.0)) / 100.0  # +80%
        self.partial_lock_3 = float(strat.get('lock3_gain_pct', 100.0)) / 100.0 # +100%
        self.lot_qty = int(self.config.get('lot_size', 75))  # Nifty lot

        # normalize columns
        data = self._norm_ohlc(data_1h).copy()
        if options_df is not None:
            options_df = self._norm_options(options_df)

        # ========== PATCH C: Precompute ATR on spot for filters / vol-bands ==========
        spot_1h = data.copy()
        atr_pct_series = _atr_pct(spot_1h, n=14)
        atr_floor = float(self.params.get("atr_floor_pct_1h", 0.0))
        ema_len = int(self.params.get("ema_slope_len", 20))
        adx_min = float(self.params.get("adx_min", 0.0))  # (not used if 0, we keep EMA slope)

        # helper: get ATR% near a timestamp (use last available)
        def _atrpct_at(ts):
            idx = spot_1h.index.searchsorted(ts, side='right') - 1
            if idx < 0:
                return None
            return float(atr_pct_series.iloc[idx])

        # --- Step 1: find all inside-candle indices (signal lock) ---
        # IMPORTANT: For backtesting, we need ALL inside bars, not just the most recent one
        # InsideBarBreakoutStrategy.detect_inside_bar() only returns the most recent inside bar (for live trading)
        # For backtesting, we use detect_inside_bar() from strategy_engine which returns ALL inside bars
        # Pass tighten_signal=False to get all inside bars without filtering
        inside_idxs = detect_inside_bar(data, tighten_signal=False)
        
        if inside_idxs:
            logger.info(f"Found {len(inside_idxs)} inside bar pattern(s) for backtesting")
        
        if not inside_idxs:
            return self._generate_results(initial_capital, current_capital)

        # --- iterate every inside pattern; wait for 1h CLOSE breakout only ---
        for idx in inside_idxs:
            if idx < 2:
                continue

            signal_high = data['High'].iloc[idx-1]
            signal_low  = data['Low'].iloc[idx-1]
            signal_time = data.index[idx]             # time of the inside candle (current)
            
            # Use new strategy's check_breakout method if available
            try:
                # Create strategy instance for backtesting
                strategy = InsideBarBreakoutStrategy(
                    broker=None,
                    market_data=None,
                    symbol="NIFTY",
                    lot_size=self.lot_qty,
                    quantity_lots=1,
                    live_mode=False,
                    config=self.config
                )
                
                # Get candles after inside bar
                future_h = data[data.index > signal_time]
                if future_h.empty:
                    continue
                
                # Use new strategy's breakout check
                # Find start index for breakout check
                start_idx = 0
                breakout_direction = strategy.check_breakout(
                    future_h,
                    signal_high,
                    signal_low,
                    start_idx=start_idx
                )
                
                if breakout_direction:
                    # Find the breakout row
                    breakout_row = None
                    for _, row in future_h.iterrows():
                        c = row['Close']
                        if (breakout_direction == 'CE' and c > signal_high) or \
                           (breakout_direction == 'PE' and c < signal_low):
                            breakout_row = row
                            direction = breakout_direction
                            break
                else:
                    breakout_row = None
                    direction = None
                    
            except Exception as e:
                # Fallback to original breakout logic
                logger.warning(f"New strategy breakout check failed, using original: {e}")
                # we trade only after we get a 1h close outside the signal range
                future_h = data[data.index > signal_time]

                if future_h.empty:
                    continue

                breakout_row = None
                direction = None  # 'CE' or 'PE'

                for _, row in future_h.iterrows():
                    c = row['Close']
                    if c > signal_high:
                        breakout_row = row
                        direction = 'CE'
                        break
                    if c < signal_low:
                        breakout_row = row
                        direction = 'PE'
                        break

            if breakout_row is None or direction is None:
                logger.debug(f"No breakout found for inside bar at index {idx} (time: {signal_time})")
                continue
            
            logger.info(f"Breakout detected for inside bar at {signal_time}: {direction} direction")

            # ========== PATCH D: Guard each candidate breakout with filters ==========
            filters_ok = True
            reasons = []

            if self.flags["use_atr_filter"]:
                atr_now = _atrpct_at(breakout_row.name)
                if atr_now is None or atr_now < atr_floor:
                    filters_ok = False
                    reasons.append(f"ATR%<{atr_floor}")

            if filters_ok and self.flags["use_regime_filter"]:
                # simple EMA slope regime: bullish bias only CE unless we allow both
                regime_up = _ema_slope_up(spot_1h.loc[:breakout_row.name], n=ema_len)
                if regime_up and direction == 'PE':
                    # allow but tag for reduced size later
                    reasons.append("bearish_dir_under_bull_regime")

            if filters_ok and self.flags["use_distance_guard"]:
                # reject / reduce entries if breakout close is too stretched
                # compute ATR in points at breakout
                atr_now = _atrpct_at(breakout_row.name)
                if atr_now is not None:
                    # convert %ATR to points
                    close_px = float(breakout_row['Close'])
                    atr_pts = close_px * (atr_now / 100.0)
                    signal_edge = (signal_high if direction == 'CE' else signal_low)
                    dist = abs(float(breakout_row['Close']) - float(signal_edge))
                    if dist > self.params.get("distance_guard_atr", 0.6) * atr_pts:
                        reasons.append("distance_guard")
                # filters_ok remains True (we may half-size instead of rejecting)

            # bail if a hard filter failed
            if not filters_ok:
                logger.debug(f"Trade filtered out for inside bar at {signal_time}: {', '.join(reasons)}")
                continue

            # Entry on NEXT hour open
            entry_bar_idx = data.index.get_loc(breakout_row.name) + 1
            if entry_bar_idx >= len(data):
                logger.debug(f"No entry bar available after breakout at {breakout_row.name} (end of data)")
                continue  # no bar to enter

            entry_bar = data.iloc[entry_bar_idx]
            entry_ts = data.index[entry_bar_idx]
            spot_at_entry = entry_bar['Open']
            
            # Calculate strike price for option selection
            strike = self._calculate_strike(spot_at_entry, direction)

            # expiry handling
            expiry_dt = self._get_expiry_for(entry_ts, expiries_df)

            # expiry-day restrictions (Tuesday):
            if self._is_expiry_day(entry_ts, expiry_dt):
                # block new entries after 11:30
                if entry_ts.time() > time(11, 30):
                    continue

            # ========== PATCH E: Directional sizing & portfolio caps ==========
            risk_pct = float(self.sizing.get("risk_per_trade_pct", 0.0)) / 100.0
            pe_cap = float(self.sizing.get("pe_size_cap_vs_ce", 1.0))
            port_cap = float(self.sizing.get("portfolio_risk_cap_pct", 100.0)) / 100.0
            max_conc = int(self.sizing.get("max_concurrent_positions", 9999))

            # derive per-trade size multiplier (1.0 default)
            size_mult = 1.0
            if self.flags["use_directional_sizing"]:
                regime_up = _ema_slope_up(spot_1h.loc[:breakout_row.name], n=ema_len)
                if direction == 'PE' and regime_up:
                    size_mult = min(size_mult, pe_cap)  # reduce PE size under bullish regime

            if "distance_guard" in reasons:
                size_mult *= 0.5  # halve size if stretched breakout

            # for a single-lot backtester you can store size_mult; if you price by premium risk:
            # we'll record it to trade dict (quantity already equals lot_size)

            # --- determine option entry premium ---
            # Prefer real options_df; else fallback to synthetic using spot & delta 0.5
            if options_df is not None and expiry_dt is not None:
                # Use pre-calculated strike (already calculated above)
                strike_selection = self.config.get("strike_selection", "ATM 0")
                logger.debug(f"Strike selection: {strike_selection} | Spot: {spot_at_entry:.2f} | Direction: {direction} | Calculated Strike: {strike}")
                opt_slice = self._select_option_slice(
                    options_df, expiry_dt, strike, direction, entry_ts
                )
                if opt_slice.empty:
                    # if not found, skip gracefully
                    logger.debug(f"No option data found for trade at {entry_ts} (expiry: {expiry_dt}, strike: {strike}, direction: {direction})")
                    continue
                
                # Check if we used a different strike (nearest-strike fallback)
                actual_strike = int(opt_slice.iloc[0]['strike'])
                if actual_strike != strike:
                    logger.info(f"✓ Nearest-strike fallback applied: Using {actual_strike} instead of requested {strike}")
                    strike = actual_strike  # Update strike to actual for trade record
                
                # enter at first bar open on/after entry_ts
                entry_price = float(opt_slice.iloc[0]['open'])
                option_path = opt_slice  # we will iterate this for exit
            else:
                # synthetic premium path (safe fallback)
                entry_price = max(1.0, self._synthetic_entry_premium(spot_at_entry))
                option_path = self._build_synthetic_path(
                    data, start_ts=entry_ts, direction=direction, entry_price=entry_price
                )
            
            # ========== CAPITAL REQUIREMENT CHECK ==========
            # Capital required = qty * option premium (the amount paid to BUY the option)
            # NOTE: When buying options, you pay the PREMIUM, not the strike price!
            capital_required = self.lot_qty * entry_price
            
            # Check if current capital is sufficient
            if current_capital < capital_required:
                logger.debug(f"Trade skipped due to insufficient capital at {entry_ts}: "
                           f"Required: ₹{capital_required:.2f} (Premium: ₹{entry_price:.2f} × {self.lot_qty} qty), "
                           f"Available: ₹{current_capital:.2f}")
                continue

            # --- Calculate SL/TP using new strategy ---
            use_new_strategy_sl_tp = False
            try:
                strategy = InsideBarBreakoutStrategy(
                    broker=None,
                    market_data=None,
                    symbol="NIFTY",
                    lot_size=self.lot_qty,
                    quantity_lots=1,
                    live_mode=False,
                    config=self.config
                )
                sl_points = strategy.sl_points
                rr_ratio = strategy.rr_ratio
                stop_loss, take_profit = strategy.calculate_sl_tp_levels(
                    entry_price,
                    sl_points,
                    rr_ratio
                )
                use_new_strategy_sl_tp = True
                logger.debug(f"SL/TP calculated (new strategy): Entry={entry_price:.2f}, SL={stop_loss:.2f}, TP={take_profit:.2f}")
            except Exception as e:
                # Fallback to original SL/TP calculation
                logger.warning(f"New strategy SL/TP calculation failed, using original: {e}")
                use_new_strategy_sl_tp = False

            # Use new strategy's SL/TP if calculated, else fallback to vol-band or legacy
            if use_new_strategy_sl_tp:
                # Use SL/TP from new strategy
                sl_price = stop_loss
                tp_price = take_profit
            elif self.flags.get("use_tiered_exits", False):
                # Use vol-band SL if tiered exits enabled
                atr_now = _atrpct_at(entry_ts) or 0.0
                low_th = float(self.params.get("vol_bands", {}).get("low", 0.40))
                high_th = float(self.params.get("vol_bands", {}).get("high", 0.75))
                if atr_now < low_th:
                    sl_pct = float(self.params.get("premium_sl_pct_low", 22.0))
                elif atr_now < high_th:
                    sl_pct = float(self.params.get("premium_sl_pct_norm", 28.0))
                else:
                    sl_pct = float(self.params.get("premium_sl_pct_high", 35.0))
                sl_price = entry_price * (1.0 - sl_pct / 100.0)
                tp_price = entry_price * (1 + self.partial_lock_1)  # Use first target as TP
            else:
                # Legacy SL calculation
                sl_price = entry_price * (1.0 - self.pct_sl)  # 35% down (legacy)
                tp_price = entry_price * (1 + self.partial_lock_1)  # Use first target as TP
            trail_price = sl_price  # will update dynamically

            # --- simulate walk-forward on hourly option bars ---
            # Use enhanced tiered exits if enabled, else legacy
            if self.flags.get("use_tiered_exits", False):
                trade_result = self._simulate_trade_enhanced(
                    entry_candle=entry_bar,
                    future_data=option_path,
                    entry_price=entry_price,
                    stop_loss=sl_price,
                    direction=direction,
                    lot_size=self.lot_qty,
                    expiry_dt=expiry_dt,
                    reasons=reasons
                )
                if trade_result:
                    exit_price = trade_result['exit']
                    exit_time = trade_result['exit_time']
                    exit_reason = trade_result['exit_reason']
                    pnl = trade_result['pnl']  # already includes lot_size in calculation
                    notes = trade_result.get('notes', '')
                    pnl_per_unit = pnl / self.lot_qty  # derive per-unit PnL
                else:
                    continue
            else:
                exit_price, exit_time, exit_reason = self._walk_option_path(
                    option_path=option_path,
                    entry_price=entry_price,
                    trail_start=trail_price,
                    direction=direction,
                    entry_ts=entry_ts,
                    expiry_dt=expiry_dt
                )
                pnl_per_unit = exit_price - entry_price
                pnl = pnl_per_unit * self.lot_qty  # 75 qty
                notes = ""

            # ========== TRACK CAPITAL REQUIREMENT FOR THIS TRADE ==========
            self.capital_requirements.append(capital_required)
            
            # ========== TRACK TRAILING SL EXITS FOR WINNING TRADES ==========
            # Check if this is a winning trade that was cut by trailing stop loss
            if pnl > 0 and exit_reason == "TRAIL_EXIT":
                self.winning_trades_trail_exit += 1
                logger.info(f"📊 Winning trade #{len(self.trades)+1} cut by trailing SL: P&L=₹{pnl:.2f}")
            
            self.trades.append({
                'entry_time': entry_ts,
                'exit_time': exit_time,
                'direction': direction,
                'signal_high': float(signal_high),
                'signal_low': float(signal_low),
                'entry': float(entry_price),
                'exit': float(exit_price),
                'sl_initial': float(sl_price),
                'pnl': float(pnl),
                'pnl_per_unit': float(pnl_per_unit),
                'exit_reason': exit_reason,
                'expiry': expiry_dt.date().isoformat() if expiry_dt is not None else None,
                'quantity': self.lot_qty,
                'strike': int(strike),
                'capital_required': float(capital_required),  # Track capital used
                'notes': notes  # PATCH: filter/sizing reasons
            })

            current_capital += pnl
            self.equity_curve.append(current_capital)
            
            # ========== CHECK IF CAPITAL EXHAUSTED ==========
            if current_capital <= 0 and not self.capital_exhausted:
                self.capital_exhausted = True
                self.capital_exhausted_at_trade = len(self.trades)
                logger.warning(f"⚠️  CAPITAL EXHAUSTED after trade #{len(self.trades)} at {exit_time}")
                logger.warning(f"    Final capital: ₹{current_capital:.2f}")
                logger.warning(f"    Initial capital: ₹{initial_capital:.2f}")
                logger.warning(f"    Total loss: ₹{initial_capital - current_capital:.2f}")
            
            logger.info(f"✅ Trade executed: {direction} at {entry_ts}, Entry: ₹{entry_price:.2f}, Exit: ₹{exit_price:.2f}, P&L: ₹{pnl:.2f}")

        logger.info(f"Backtest complete: Processed {len(inside_idxs)} inside bars, executed {len(self.trades)} trades")
        return self._generate_results(initial_capital, current_capital)

    # ------------- Simulation helpers -------------

    @staticmethod
    def _norm_ohlc(df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        out = out.rename(columns={c: c.capitalize() for c in out.columns})
        if 'Open' not in out.columns:  out.rename(columns={'O':'Open'}, inplace=True)
        if 'High' not in out.columns:  out.rename(columns={'H':'High'}, inplace=True)
        if 'Low' not in out.columns:   out.rename(columns={'L':'Low'}, inplace=True)
        if 'Close' not in out.columns: out.rename(columns={'C':'Close'}, inplace=True)
        if not isinstance(out.index, pd.DatetimeIndex):
            if 'Timestamp' in out.columns:
                out['Timestamp'] = pd.to_datetime(out['Timestamp'])
                out = out.set_index('Timestamp')
            else:
                out.index = pd.to_datetime(out.index)
        out = out[['Open','High','Low','Close']].copy()
        out.sort_index(inplace=True)
        return out

    @staticmethod
    def _norm_options(df: pd.DataFrame) -> pd.DataFrame:
        d = df.copy()
        d.columns = [c.lower() for c in d.columns]
        # enforce schema
        rename = {
            'timestamp':'timestamp',
            'open':'open','high':'high','low':'low','close':'close',
            'type':'type','strike':'strike','expiry':'expiry'
        }
        d = d.rename(columns=rename)
        d['timestamp'] = pd.to_datetime(d['timestamp'])
        d['expiry'] = pd.to_datetime(d['expiry'])
        d['type'] = d['type'].str.upper()
        d = d[['timestamp','open','high','low','close','expiry','strike','type']]
        d.sort_values('timestamp', inplace=True)
        return d

    @staticmethod
    def _nearest_100(x: float) -> int:
        """Legacy method - rounds to nearest 100. Use _calculate_strike for proper strike calculation."""
        return int(round(x / 100.0) * 100)
    
    def _calculate_strike(self, spot_price: float, direction: str) -> int:
        """
        Calculate strike price based on spot, direction, and strike selection (ATM/ITM/OTM).
        
        For NIFTY: strikes are in multiples of 50
        - ATM 0: nearest 50 to spot
        - ITM: closer to spot (CE: lower strike, PE: higher strike)
        - OTM: away from spot (CE: higher strike, PE: lower strike)
        
        Args:
            spot_price: Current spot price
            direction: "CE" for Call, "PE" for Put
        
        Returns:
            Strike price rounded to nearest 50 with offset applied
        """
        # NIFTY strikes are in multiples of 50
        base_strike = round(spot_price / 50) * 50
        
        # If ATM, return base strike
        if self.strike_offset_base == 0:
            return int(base_strike)
        
        # Calculate offset based on direction and ITM/OTM
        if direction == "CE":
            # For Call options:
            # ITM = lower strike (closer to spot, more in the money) = negative offset
            # OTM = higher strike (away from spot, out of the money) = positive offset
            if self.strike_is_itm:
                offset = -self.strike_offset_base
            elif self.strike_is_otm:
                offset = self.strike_offset_base
            else:
                offset = 0
        elif direction == "PE":
            # For Put options:
            # ITM = higher strike (closer to spot, more in the money) = positive offset
            # OTM = lower strike (away from spot, out of the money) = negative offset
            if self.strike_is_itm:
                offset = self.strike_offset_base
            elif self.strike_is_otm:
                offset = -self.strike_offset_base
            else:
                offset = 0
        else:
            offset = 0
        
        strike = base_strike + offset
        return int(strike)

    @staticmethod
    def _get_expiry_for(ts: pd.Timestamp, expiries_df: Optional[pd.DataFrame]) -> Optional[pd.Timestamp]:
        if expiries_df is None or 'expiry' not in expiries_df.columns:
            return None
        e = expiries_df[expiries_df['expiry'] >= ts].sort_values('expiry')
        return e.iloc[0]['expiry'] if len(e) else None

    @staticmethod
    def _is_expiry_day(ts: pd.Timestamp, expiry_dt: Optional[pd.Timestamp]) -> bool:
        if expiry_dt is None: return False
        return ts.date() == expiry_dt.date()

    def _select_option_slice(
        self,
        options_df: pd.DataFrame,
        expiry_dt: pd.Timestamp,
        atm: int,
        direction: str,
        entry_ts: pd.Timestamp
    ) -> pd.DataFrame:
        """
        Select option data slice for the given parameters.
        Falls back to nearest available strike if exact match not found.
        
        Args:
            options_df: DataFrame with options data
            expiry_dt: Expiry timestamp
            atm: Target strike price (may be ATM, ITM, or OTM)
            direction: 'CE' or 'PE'
            entry_ts: Entry timestamp
        
        Returns:
            DataFrame with option data, or empty DataFrame if no data available
        """
        side = 'CE' if direction == 'CE' else 'PE'
        
        # First try exact match
        exact_mask = (
            (options_df['expiry'].dt.date == expiry_dt.date()) &
            (options_df['strike'] == atm) &
            (options_df['type'] == side) &
            (options_df['timestamp'] >= entry_ts)
        )
        exact_match = options_df.loc[exact_mask].copy()
        
        if not exact_match.empty:
            # Exact match found - use it
            return exact_match
        
        # No exact match - find nearest available strike
        logger.debug(f"Exact strike {atm} not found, searching for nearest available strike...")
        
        # Get all available strikes for this expiry/type combination
        candidates_mask = (
            (options_df['expiry'].dt.date == expiry_dt.date()) &
            (options_df['type'] == side) &
            (options_df['timestamp'] >= entry_ts)
        )
        candidates_df = options_df[candidates_mask]
        
        if candidates_df.empty:
            logger.debug(f"No option data available for {side} on {expiry_dt.date()} at/after {entry_ts}")
            return pd.DataFrame()
        
        # Get unique strikes
        available_strikes = candidates_df['strike'].unique()
        
        # Find nearest strike to target
        nearest_strike = int(available_strikes[np.abs(available_strikes - atm).argmin()])
        
        # Log the fallback
        strike_diff = abs(nearest_strike - atm)
        logger.info(
            f"📍 Using nearest available strike: {nearest_strike} "
            f"(requested: {atm}, difference: ±{strike_diff})"
        )
        
        # Select data for nearest strike
        nearest_mask = (
            (options_df['expiry'].dt.date == expiry_dt.date()) &
            (options_df['strike'] == nearest_strike) &
            (options_df['type'] == side) &
            (options_df['timestamp'] >= entry_ts)
        )
        
        return options_df.loc[nearest_mask].copy()

    # ----- synthetic fallback (only used if options_df not supplied) -----

    @staticmethod
    def _synthetic_entry_premium(spot_open: float) -> float:
        # keep it conservative: ~0.5% of spot, floor 50
        return max(50.0, 0.005 * spot_open)

    def _build_synthetic_path(
        self,
        spot_df_1h: pd.DataFrame,
        start_ts: pd.Timestamp,
        direction: str,
        entry_price: float
    ) -> pd.DataFrame:
        """Create a simple premium path from spot using delta~0.5."""
        future = spot_df_1h[spot_df_1h.index >= start_ts].copy()
        delta = 0.5
        base = float(future.iloc[0]['Open'])
        premium = [entry_price]
        for i in range(1, len(future)):
            move = float(future.iloc[i]['Close'] - base)
            chg = delta * move if direction == 'CE' else -delta * move
            premium.append(max(1.0, entry_price + chg))
        # Create DataFrame with timestamp as column (not index) for consistency with _walk_option_path
        out = pd.DataFrame({
            'timestamp': pd.to_datetime(future.index.values),
            'open': premium,
            'high': [p*1.05 for p in premium],
            'low':  [max(1.0, p*0.95) for p in premium],
            'close': premium
        })
        # Ensure timestamp is datetime type
        out['timestamp'] = pd.to_datetime(out['timestamp'])
        return out

    # ----- walk forward with trailing & expiry rules -----

    def _simulate_trade_enhanced(
        self,
        entry_candle: pd.Series,
        future_data: pd.DataFrame,
        entry_price: float,
        stop_loss: float,
        direction: str,
        lot_size: int,
        *,
        expiry_dt: Optional[pd.Timestamp] = None,
        reasons: Optional[list] = None
    ) -> Optional[Dict]:
        """
        ========== PATCH F: Enhanced simulation with tiered exits, BE conversion,
        ATR-premium trail, and expiry protocol. ==========
        Falls back to legacy behavior if flags are off.
        """
        if len(future_data) == 0:
            return None

        # Params
        be_at_r = float(self.params.get("be_at_r", 0.6))
        lookback = int(self.params.get("trail_lookback", 6))
        mult = float(self.params.get("trail_mult", 2.0))
        t1_r = float(self.params.get("t1_r", 1.2))
        t1_book = float(self.params.get("t1_book", 0.5))
        t2_r = float(self.params.get("t2_r", 2.0))
        t2_book = float(self.params.get("t2_book", 0.25))
        swing_lock = bool(self.params.get("swing_lock", True))
        tighten_days = float(self.params.get("tighten_trail_days_to_expiry", 1.5))
        tighten_factor = float(self.params.get("tighten_mult_factor", 1.3))

        # Build premium path DataFrame view
        prem = future_data.rename(columns=str.lower).copy()
        # Ensure we have timestamp as index or column
        if 'timestamp' in prem.columns:
            prem['timestamp'] = pd.to_datetime(prem['timestamp'])
            prem = prem.set_index('timestamp')
        elif not isinstance(prem.index, pd.DatetimeIndex):
            prem.index = pd.to_datetime(prem.index)

        # Get OHLC columns (case-insensitive)
        ohcl_cols = {}
        for col in prem.columns:
            col_lower = col.lower()
            if col_lower in ['open', 'high', 'low', 'close']:
                ohcl_cols[col_lower] = col

        if not all(k in ohcl_cols for k in ['open', 'high', 'low', 'close']):
            # Fallback: use available columns
            prem_cols = [c.lower() for c in prem.columns]
            if 'open' not in prem_cols and len(prem.columns) >= 4:
                prem.columns = ['open', 'high', 'low', 'close'] + list(prem.columns[4:])
            ohcl_cols = {'open': 'open', 'high': 'high', 'low': 'low', 'close': 'close'}

        prem_clean = prem[[ohcl_cols['open'], ohcl_cols['high'], ohcl_cols['low'], ohcl_cols['close']]].copy()
        prem_clean.columns = ['open', 'high', 'low', 'close']

        # R in premium terms
        risk_per_unit = entry_price - stop_loss
        if risk_per_unit <= 0:
            return None

        # Chandelier trail on premium
        trail_series = _chandelier_trail(prem_clean, lookback=lookback, mult=mult, direction=direction)

        # State
        qty = lot_size
        realized = 0.0
        remaining = 1.0  # fraction of position remaining
        sl = stop_loss
        be_locked = False
        hit_t1 = False
        hit_t2 = False
        exit_reason = "TIME_EXIT"
        exit_price = prem_clean['close'].iloc[-1]
        exit_time = prem_clean.index[-1]

        # Time/expiry helpers
        def _is_expiry_bar(ts):
            return (expiry_dt is not None) and (ts.date() == expiry_dt.date())

        no_new_after_hhmm = _parse_hhmm(self.params.get("no_new_after", "14:30"), (14, 30))
        force_partial_by_hhmm = _parse_hhmm(self.params.get("force_partial_by", "13:00"), (13, 0))

        for ts, row in prem_clean.iterrows():
            h = float(row['high'])
            l = float(row['low'])
            c = float(row['close'])

            # Tighten trail near expiry
            if expiry_dt is not None:
                days_to_exp = (expiry_dt - ts).total_seconds() / 86400.0
                if days_to_exp <= tighten_days:
                    # recompute tighter trail on the fly
                    prem_slice = prem_clean.loc[:ts]
                    if len(prem_slice) >= 3:
                        tight_lookback = max(3, lookback // 2)
                        tight_mult = max(1.2, mult / tighten_factor)
                        tight_trail_series = _chandelier_trail(prem_slice, lookback=tight_lookback, mult=tight_mult, direction=direction)
                        tight_trail = tight_trail_series.iloc[-1] if len(tight_trail_series) > 0 else None
                    else:
                        tight_trail = trail_series.loc[ts] if ts in trail_series.index else None
                else:
                    tight_trail = trail_series.loc[ts] if ts in trail_series.index else None
            else:
                tight_trail = trail_series.loc[ts] if ts in trail_series.index else None

            # Breakeven conversion
            if not be_locked and (c >= entry_price + be_at_r * risk_per_unit):
                sl = max(sl, entry_price)  # BE
                be_locked = True

            # Partial tiers
            if (not hit_t1) and (c >= entry_price + t1_r * risk_per_unit):
                realized += t1_book * (c - entry_price) * qty
                remaining -= t1_book
                hit_t1 = True
            if (not hit_t2) and (c >= entry_price + t2_r * risk_per_unit):
                realized += t2_book * (c - entry_price) * qty
                remaining -= t2_book
                hit_t2 = True

            # Update trail (never looser than tight_trail)
            if tight_trail is not None:
                if direction == 'CE':
                    sl = max(sl, tight_trail)
                else:
                    sl = min(sl, tight_trail)

            # Stop-loss hit on remaining
            if (direction == 'CE' and l <= sl) or (direction == 'PE' and h >= sl):
                exit_price = sl
                exit_reason = "SL_HIT" if remaining >= 0.999 else "TRAIL_EXIT"
                exit_time = ts
                realized += remaining * (exit_price - entry_price) * qty
                remaining = 0.0
                break

            # Expiry force exit by 14:45
            if _is_expiry_bar(ts):
                hh, mm = _hhmm(ts)
                if (hh, mm) >= (14, 45):
                    exit_price = c
                    exit_reason = "EXPIRY_FORCE_EXIT"
                    exit_time = ts
                    realized += remaining * (exit_price - entry_price) * qty
                    remaining = 0.0
                    break

                # Force partial by 13:00 if not BE yet
                if self.flags.get("use_expiry_protocol", False) and (hh, mm) >= force_partial_by_hhmm and not be_locked and remaining > 0.5:
                    take = 0.5
                    realized += take * (c - entry_price) * qty
                    remaining -= take

        # If still open
        if remaining > 0:
            realized += remaining * (exit_price - entry_price) * qty

        pnl = realized

        return {
            'direction': direction,
            'entry': entry_price,
            'exit': exit_price,
            'sl': stop_loss,
            'tp': None,
            'pnl': pnl,
            'exit_reason': exit_reason,
            'exit_time': exit_time,
            'quantity': lot_size,
            'notes': ";".join(reasons or [])
        }

    def _walk_option_path(
        self,
        option_path: pd.DataFrame,
        entry_price: float,
        trail_start: float,
        direction: str,
        entry_ts: pd.Timestamp,
        expiry_dt: Optional[pd.Timestamp]
    ) -> tuple[float, pd.Timestamp, str]:
        """
        Iterate hourly option bars and apply:
        - initial SL = -35%,
        - +40% BE lock,
        - +60/+80/+100% profit locks,
        - expiry-day exits (no carry; force close 14:45).
        """

        # levels
        sl = trail_start
        lock1 = entry_price * (1.0 + self.partial_lock_1)  # +60%
        lock2 = entry_price * (1.0 + self.partial_lock_2)  # +80%
        lock3 = entry_price * (1.0 + self.partial_lock_3)  # +100%

        # dynamic trail:
        # after +40% -> BE, then progressive locks
        be_locked = False

        # iterate bars (already from entry time forward)
        for i, r in option_path.reset_index(drop=True).iterrows():
            ts = pd.to_datetime(r['timestamp'])
            o, h, l, c = float(r['open']), float(r['high']), float(r['low']), float(r['close'])

            # expiry day hard exit 14:45
            if self._is_expiry_day(ts, expiry_dt):
                # block new entries handled earlier;
                # here we force exit by 14:45
                if ts.time() >= time(14, 45):
                    return (c, ts, 'EXPIRY_FORCE_EXIT')

            # hit SL?
            if l <= sl:
                return (sl, ts, 'SL_HIT')

            # BE lock after +40%
            if not be_locked and c >= entry_price * 1.40:
                sl = entry_price  # move to BE
                be_locked = True

            # progressive locks
            if c >= lock1:
                sl = max(sl, entry_price * 1.25)  # +25% locked
            if c >= lock2:
                sl = max(sl, entry_price * 1.45)  # +45% locked
            if c >= lock3:
                sl = max(sl, entry_price * 1.60)  # +60% locked

            # normal trailing: protect on bar lows when well in profit
            if c >= entry_price * 1.40:
                # trail under bar low (premium) with small cushion
                sl = max(sl, l * 0.995)

        # if never exited, close at last candle
        last = option_path.iloc[-1]
        return (float(last['close']), pd.to_datetime(last['timestamp']), 'TIME_EXIT')

    # ------------- Results & stats -------------

    def _generate_results(self, initial_capital: float, final_capital: float) -> Dict:
        # ========== CALCULATE CAPITAL METRICS (backtest-only) ==========
        avg_capital_required = 0.0
        if self.capital_requirements:
            avg_capital_required = float(sum(self.capital_requirements) / len(self.capital_requirements))
        
        # ========== CALCULATE TRAILING SL METRICS (backtest-only) ==========
        trail_exit_pct = 0.0
        if self.trades:
            winning_count = len([t for t in self.trades if t['pnl'] > 0])
            if winning_count > 0:
                trail_exit_pct = (self.winning_trades_trail_exit / winning_count) * 100.0
        
        if not self.trades:
            return {
                'total_trades': 0, 'winning_trades': 0, 'losing_trades': 0,
                'total_pnl': 0.0, 'win_rate': 0.0,
                'avg_win': 0.0, 'avg_loss': 0.0, 'max_drawdown': 0.0,
                'max_winning_streak': 0, 'max_losing_streak': 0,
                'initial_capital': initial_capital, 'final_capital': final_capital,
                'return_pct': 0.0, 'equity_curve': self.equity_curve, 'trades': [],
                # ========== CAPITAL ANALYSIS (backtest-only) ==========
                'capital_exhausted': False,
                'capital_exhausted_at_trade': None,
                'avg_capital_required': avg_capital_required,
                # ========== TRAILING SL ANALYSIS (backtest-only) ==========
                'winning_trades_trail_exit': 0,
                'trail_exit_pct_of_winners': 0.0
            }

        df = pd.DataFrame(self.trades)
        winners = df[df['pnl'] > 0]
        losers  = df[df['pnl'] < 0]
        total_pnl = float(df['pnl'].sum())
        win_rate  = float((len(winners) / len(df)) * 100.0)
        avg_win   = float(winners['pnl'].mean()) if not winners.empty else 0.0
        avg_loss  = float(losers['pnl'].mean()) if not losers.empty else 0.0
        max_dd    = self._calculate_max_drawdown()
        
        # ========== CALCULATE WINNING AND LOSING STREAKS ==========
        max_winning_streak = 0
        max_losing_streak = 0
        current_winning_streak = 0
        current_losing_streak = 0
        
        for _, trade in df.iterrows():
            if trade['pnl'] > 0:
                # Winning trade
                current_winning_streak += 1
                current_losing_streak = 0
                max_winning_streak = max(max_winning_streak, current_winning_streak)
            elif trade['pnl'] < 0:
                # Losing trade
                current_losing_streak += 1
                current_winning_streak = 0
                max_losing_streak = max(max_losing_streak, current_losing_streak)
            # If pnl == 0 (breakeven), we could reset both or continue - let's reset both
            else:
                current_winning_streak = 0
                current_losing_streak = 0

        return {
            'total_trades': int(len(df)),
            'winning_trades': int(len(winners)),
            'losing_trades': int(len(losers)),
            'total_pnl': total_pnl, 'win_rate': win_rate,
            'avg_win': avg_win, 'avg_loss': avg_loss,
            'max_drawdown': max_dd,
            'max_winning_streak': int(max_winning_streak),
            'max_losing_streak': int(max_losing_streak),
            'initial_capital': initial_capital, 'final_capital': final_capital,
            'return_pct': ((final_capital - initial_capital) / initial_capital * 100.0) if initial_capital > 0 else 0.0,
            'equity_curve': self.equity_curve,
            'trades': self.trades,
            # ========== CAPITAL ANALYSIS (backtest-only) ==========
            'capital_exhausted': self.capital_exhausted,
            'capital_exhausted_at_trade': self.capital_exhausted_at_trade,
            'avg_capital_required': avg_capital_required,
            # ========== TRAILING SL ANALYSIS (backtest-only) ==========
            'winning_trades_trail_exit': self.winning_trades_trail_exit,
            'trail_exit_pct_of_winners': trail_exit_pct
        }

    def _calculate_max_drawdown(self) -> float:
        if len(self.equity_curve) < 2:
            return 0.0
        eq = np.array(self.equity_curve, dtype=float)
        roll_max = np.maximum.accumulate(eq)
        dd = (eq - roll_max) / np.where(roll_max == 0, 1, roll_max) * 100.0
        return float(abs(np.min(dd)))


# ------------- Convenience wrapper (kept for compatibility) -------------

def run_backtest(
    data: pd.DataFrame,
    strategy_params: Dict,
    **kwargs
) -> Dict:
    """
    Convenience function to run backtest.
    Accepts optional options_df=..., expiries_df=..., data_15m=... (legacy, ignored)
    """
    engine = BacktestEngine(strategy_params)
    return engine.run_backtest(
        data_1h=data,
        data_15m=kwargs.get("data_15m"),                  # optional / ignored
        initial_capital=float(strategy_params.get("initial_capital", 100000.0)),
        options_df=kwargs.get("options_df"),
        expiries_df=kwargs.get("expiries_df"),
    )
