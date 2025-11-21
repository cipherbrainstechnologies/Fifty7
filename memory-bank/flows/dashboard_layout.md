# Dashboard Layout – Streamlit Dashboard (2025‑11‑21)

## Overview

The Streamlit dashboard now follows a minimalist, status-first layout optimized for live monitoring across desktop and tablet widths. Content is constrained to a `max-width: 1280px`, with a light gray background and 24 px spacing between major sections. Every section pulls data from existing engine services (`LiveStrategyRunner`, `TradeLogger`, `tick_streamer`, etc.) without increasing broker/API load.

## Section Map

1. **Sticky Status Ribbon**  
   - Lives at the top (`sticky top-0 z-50`) with three color-coded chips: Algo, Broker, Market.  
   - Right side houses both refresh controls: UI auto toggle + `⏱` interval popover, Backend toggle + `⚙` popover, plus the manual refresh icon.  
   - Chips reflect execution guard, broker type, and market calendars sourced from `live_runner`, `broker_connector`, and `market calendar helper`.

2. **Trading Controls Panel**  
   - Orange warning card containing: Start/Stop toggle button, Execution arm/disarm switch, Strategy settings shortcut.  
   - Buttons call into `LiveStrategyRunner.start/stop` and update `execution_armed` on both the runner and session state.  
   - Strategy settings open inside a `st.popover` so the full form appears as a lightweight popup inside the card.

3. **Hero Metrics Deck**  
   - Two-column grid: left card = Active Trade (symbol, qty, status plus four metric boxes: Buying Price, Take Profit, Stop Loss, Trailing SL, shown even when no trade is active). Right card = 2x2 metric grid (Signal Watching, NIFTY LTP, Realized P&L, Active P&L).  
   - Data sources: `TradeLogger`, `active_pnl_snapshot`, `tick_streamer`, `pnl_service`, CSV fallback.  
   - Metrics use emoji prefixes (green/red) to match guideline color cues.

4. **Inside Bar Snapshot Card**  
   - Three stacked sections (Mother Candle → Inside Candle → Range Diagnostics) rendered via custom HTML + CSS.  
   - Each section shows 4-value grids (OHLC / range stats). Range block also displays width, breakout status, and compression depth.

5. **Strategy Configuration Strip**  
   - Horizontal chip row listing live strategy settings: Risk-Reward, SL, ATM offset, lot size, filters, max positions, and timeframe pair.  
   - Values pulled from `config/config.yaml` (or runner overrides when available).

6. **Strategy Debug Area**  
   - Wrapped in `st.expander` accordions:  
     - **Inside Bar Detection Debug** – reuses the legacy diagnostics table, candle listings, and breakout verifications.  
     - **Range Persistence Analysis** – summarizes current mother range, latest close, and compression stats.  
     - **Breakout Events Log** – timeline badges for the last breakout alert and any `last_missed_trade`.  
   - The section also retains the existing live data, risk management, and backend sync instrumentation above it.

7. **Footer Actions Bar**  
   - Provides a quick link to `logs/trades.csv`, displays the last refresh timestamp/reason, and offers a secondary manual refresh button.

## Refresh Model

- **Front-end + backend toggles** sit in the status ribbon’s right column so both states and intervals are always visible.  
- **Interval inputs** are hidden inside popovers (`⏱` for UI, `⚙` for backend) and only shown when the icon is clicked; updates reset `next_auto_refresh_ts` (UI) or the background interval immediately.  
- **Manual refresh buttons** exist in the ribbon (icon) and footer (“Manual Refresh”), both reusing `_trigger_market_data_refresh` with different reasons.

## Data & Health Sources

| Section | Source |
| --- | --- |
| Status chips | `live_runner._is_market_open`, `broker_connected`, `execution_armed`, `active_pnl_snapshot["streamer"]` |
| Trading controls | `LiveStrategyRunner.start/stop`, `execution_armed` session state |
| Hero metrics | `TradeLogger`, `active_pnl_snapshot`, `tick_streamer`, `pnl_service`, CSV fallback |
| Inside Bar snapshot | `MarketDataProvider.get_1h_data`, `detect_inside_bar`, `find_mother_index`, `confirm_breakout` |
| Config strip | `config/config.yaml`, `live_runner.config`, `risk_management` overrides |
| Debug accordions | Existing diagnostics block, range stats (computed from snapshot), session state breakout history |
| Footer | `st.session_state.last_refresh_time`, manual refresh helper |

## Implementation Notes

- CSS classes live directly in `dashboard/ui_frontend.py` (e.g., `.status-ribbon`, `.trading-panel`, `.hero-grid`, `.snapshot-card`, `.config-strip`, `.footer-bar`).  
- HTML snippets are injected via `st.markdown(..., unsafe_allow_html=True)` to achieve the chip/grid structure while keeping interactive widgets inside Streamlit components.  
- Strategy settings and the refresh intervals use `st.popover`, which keeps the controls compact until a user clicks the icon/button.  
- Any future layout changes should update this document plus the CSS block to maintain design parity.

