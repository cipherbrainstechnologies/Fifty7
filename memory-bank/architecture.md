# NIFTY Options Algo Trading System - Architecture

## System Overview

The NIFTY Options Algo Trading System is a secure, cloud-ready algorithmic trading platform designed for NIFTY options trading using an Inside Bar + 15-minute Breakout strategy.

## Architecture Components

### 1. Core Engine (`engine/`)
- **strategy_engine.py**: Core strategy logic for Inside Bar detection and breakout confirmation
- **signal_handler.py**: Signal processing, validation, and trade signal generation
- **trade_logger.py**: Comprehensive trade logging to CSV format
- **broker_connector.py**: Abstract broker interface supporting multiple broker APIs (Angel One, Fyers)
- **backtest_engine.py**: Historical backtesting framework with trade simulation, now supporting configurable strategy timeframes (1H or 4H) via resampled spot data

### 2. Dashboard (`dashboard/`)
- **ui_frontend.py**: Main Streamlit application with authentication and a backtesting timeframe selector (1H vs 4H) that pipes directly into the backtest engine
- **streamlit_app.py**: Application entry point wrapper

### 3. Configuration (`config/`)
- **config.yaml**: Strategy parameters, lot sizes, SL/TP, filters
- **.streamlit/secrets.toml**: Secure credentials and broker API keys

### 4. Data Management
- **data/historical/**: Historical market data for backtesting
- **logs/**: Application logs and trade journal CSV files
- **Angel SmartAPI Backtesting**: Optional `backtesting.angel_smartapi` config taps the SmartAPI Historical app (api key `oV0N6xt7`) for short-window spot candles (≈3–6 months, no options OHLC). Intended for validation/overlap checks, not full-scale simulations; reads credentials exclusively from `.streamlit/secrets.toml`.
- **Trade Persistence**: Every executed trade logged via `TradeLogger` now writes both to CSV (`logs/trades.csv`) and the `trades` Postgres table once `org_id`/`user_id` are resolved (see `tenant_context`). Missed trades detected by the signal handler are also archived in the `missed_trades` table with strike, range, entry/SL/TP, and breakout close so post-analysis can compute potential gain/loss on skipped setups.

### 5. Documentation (`docs/`)
- **setup/**: Quick start guides, local run instructions, credential setup, and automation helpers
  - **marketdata/**: Market data onboarding, API setup, and implementation notes
- **auth/**: Authentication fixes, password handling procedures, and login diagnostics
- **strategy/**: Strategy primers, comparative analyses, and enhancement notes
- **operations/**: Live trading readiness, execution fixes, and operational playbooks
- **deployment/**: Render and Streamlit deployment workflows
- **api/**: External API capability and integration references
- **postmortems/**: Incident reviews and fix summaries
  - **capital/**, **strategy/**, **strike/**, **infrastructure/**, **operations/**: Domain-specific retrospectives
- **troubleshooting/**: Aggregated troubleshooting guide
- **run/**: Reserved for runbook-style automation (currently empty)

### SmartAPI Credential Roles

Reference: `docs/api/API-Documentation-File.md`

- **Trading API (SmartAPI Trading App)**  
  - Credentials: `api_key` + `secret_key` (current pair `sz5neY7b` / `8a5bd331-9445-4d0e-a975-24ef7c73162a`).  
  - Usage: `engine/broker_connector.py`, `engine/signal_handler.py`, and dashboard order controls issue session logins, JWT refresh, order placement, RMS/funds requests, and portfolio pulls via Angel One SmartAPI REST endpoints (X-PrivateKey header).  
  - Notes: Sessions last 28 hours; authenticate with client code, PIN, and TOTP. Tokens must be persisted in memory only and refreshed via `generateTokens`. As of 2025-11-17 the broker connector auto-regenerates a fresh session whenever refresh calls return `AG8001/Invalid Token`, preventing silent expiry loops.

- **Historical Data API (SmartAPI Historical App)**  
  - Credentials: `api_key` + `secret_key` pair `oV0N6xt7` / `4ab84310-301a-4114-be83-4b171e322e49`.  
  - Usage: `engine/market_data.py` and backtesting flows call SmartAPI historical OHLC endpoints so live trading quota is not consumed. Live trading now initializes a dedicated SmartConnect session for this app (using the trader’s login + TOTP) and automatically falls back to the trading session if the data-only login is unavailable.  
  - Notes: Rate limited separately; integrate through the market data provider class so requests can be throttled/thinned centrally.

- **Publisher API (SmartAPI Publisher App)**  
  - Credentials: Publisher `api_key` + `api_secret` pair `MIavKEDZ` / `899402fe-2641-4ffa-9683-545e60329642`.  
  - Usage: Streamlit dashboard feed widgets and any websocket quote consumers obtain `auth_token` + `feed_token` via the publisher login redirect flow documented in `docs/api/API-Documentation-File.md`, then subscribe to live ticks.  
  - Notes: Provides read-only quote distribution; do not use for authenticated trade actions. Feed token refresh ties to publisher session duration.

## System Flow

1. **Strategy Detection**: 1-hour timeframe scanned for Inside Bar patterns
2. **Breakout Confirmation**: 1-hour timeframe monitors every closed candle for mother-range breakouts
3. **Signal Generation**: Valid signals trigger trade execution logic
4. **Order Execution**: Broker API integration places orders with SL/TP
5. **Trade Logging**: All trades logged with entry/exit, PnL, and reasoning
6. **Dashboard Monitoring**: Real-time dashboard provides control and visibility

## Technology Stack

- **Frontend**: Streamlit with streamlit-authenticator
- **Backend**: Python 3.10+
- **Data Processing**: Pandas, NumPy
- **Configuration**: YAML, TOML
- **Broker APIs**: Angel One SmartAPI, Fyers API (extensible)

## Security Model

- Password-based authentication via streamlit-authenticator
- Secrets stored in `.streamlit/secrets.toml` (git-ignored)
- Session-based cookie authentication
- Configurable expiry for security tokens

## Deployment Architecture

- **Platform**: Render.com (Web Service)
- **Runtime**: Python 3.10+
- **Start Command**: `streamlit run dashboard/ui_frontend.py`
- **Secrets Management**: Environment variables or Render secrets config

## Strategy Logic

Live runs continue to use 1-hour candles for detection and confirmation, while the backtesting stack can now resample to either 1H or 4H via the new timeframe selector. Logic and filters remain identical regardless of the selected cadence.

### Inside Bar Pattern Detection (1H Timeframe)
- Detects when a candle is completely contained within the previous candle's range
- Pattern condition: `current_high < prev_high AND current_low > prev_low`
- Requires at least 2 candles of historical data
- Persists the original mother candle (first container) as the breakout range until a new mother forms

### Breakout Confirmation (1H Timeframe)
- Monitors every subsequent 1-hour candle for a decisive close outside the mother range (indefinite window)
- **Bullish Breakout (CE)**: Close > range_high AND Volume > threshold
- **Bearish Breakout (PE)**: Close < range_low AND Volume > threshold
- Volume threshold = Average volume of recent reference candles × multiplier (default 1.0)
- Direction determines Call (CE) or Put (PE) option selection

### Strike Selection
- ATM (At The Money) based on current NIFTY price
- Strike rounded to nearest 50 (NIFTY strikes are multiples of 50)
- Configurable `atm_offset` parameter for strike adjustment (default: 0)

### Risk Management
- Fixed Stop Loss (configurable, default 30 points)
- Risk-Reward Ratio (configurable, default 1.8)
- Stop Loss: Entry - sl_points
- Take Profit: Entry + (sl_points × rr_ratio)
- Volume spike filter (optional)
- Open range avoidance filter (optional)

### Signal Output
- Direction (CE/PE)
- Strike price
- Entry price
- Stop Loss level
- Take Profit level
- Range high/low
- Signal reason and timestamp

## Timezone Handling

- Market data refresh normalizes fallback 1-hour candle timestamps to timezone-aware IST values before comparisons (2025-11-07 fix).
- 15-minute candles remain timezone-naive (assumed IST) to preserve compatibility with existing aggregation routines.
- 2025-11-07: Market data provider now sources all scheduling timestamps using Asia/Kolkata, preventing UTC-hosted deployments from truncating candle windows relative to local runs.
- 2025-11-07: All dashboard timestamps render in 12-hour IST format (HH:MM AM/PM) matching NSE market hours (09:15 AM – 03:30 PM IST).
- 2025-11-07: Debug view now displays raw timestamp dtype/timezone before normalization to detect double-localization or UTC drift across environments.
- 2025-11-07: Historical fetch windows pin to NSE close (15:15 IST) when server clocks lag, and stale direct interval responses automatically fall back to resampling 1-minute candles.
- 2025-11-10: Historical candle requests clamp `to_date` to the most recent completed 15m/1h candle boundary to prevent SmartAPI AB1004 errors during live sessions.
- 2025-11-10: 1H data window auto-extends to include the previous trading session start (09:15 IST) after weekends/holidays, keeping prior inside-bar structures available for breakout checks.
- 2025-11-13: Fixed `ValueError: Cannot mix tz-aware with tz-naive values` in `_ensure_datetime_column()` by normalizing all datetime values to UTC first, then stripping timezone info to maintain timezone-naive consistency across the system.

## Debug Instrumentation

- 2025-11-07: Streamlit dashboard adds an `🧭 Debug Snapshot` panel that captures environment origin (local vs hosted), data source path, candle counts, range diagnostics, and recent timestamps to troubleshoot mismatched datasets.
- 2025-11-07: Dashboard normalizes visible 1H/15m candle tables to Asia/Kolkata by localizing raw timestamps to UTC and converting to IST before presentation.
- 2025-11-07: Streamlit cache TTL for broker portfolio/order fetches set to 0 seconds to avoid serving stale remote data during comparative debugging.
- 2025-11-10: Dashboard removes embedded TradingView charts, adds a live inside-bar snapshot deck, and wraps Option Greeks plus strategy settings in lightweight controls for faster runtime refresh.

