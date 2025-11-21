# Active P&L Tracker Pattern

## Pattern Overview

Real-time MTM visibility is critical for options trading dashboards. The Active P&L tracker pattern keeps the UI decoupled from broker polling by letting the backend maintain an always-fresh snapshot of open trades, quotes, and unrealized P&L that the UI (and other services) can read without recomputing.

## Intent / Use Case

- Provide ≤5 s updates for unrealized P&L across all open trades.
- Share a single quote cache (SmartAPI websocket + REST fallback) across the runner, dashboard, and monitors to avoid rate-limit spikes.
- Surface health diagnostics (tick streamer connectivity, quote age) to the UI so hosted deployments can spot stale data quickly.

## Structure

- `LiveStrategyRunner` starts a daemon thread alongside the main polling loop.
- Every `pnl_refresh_seconds` (default 5s) the tracker:
  - Pulls open trades from `TradeLogger`.
  - Ensures each tradingsymbol is subscribed on `LiveTickStreamer`.
  - Reads websocket quotes when fresh, otherwise calls `broker.get_option_price`.
  - Computes per-trade and aggregate MTM values (points + rupees) and stores them in `_active_pnl_snapshot`.
- The snapshot includes `trades[]`, `total_unrealized_value`, `total_unrealized_points`, `last_updated`, and `streamer` diagnostics (connection state, last tick age, subscription counts).
- Consumers call `LiveStrategyRunner.get_active_pnl_snapshot()` which returns a deepcopy guarded by a lock.
- `PositionMonitor` receives an optional `ltp_provider` callback (backed by the tracker) so SL/TP logic uses cached quotes before issuing new REST calls.

## When to Use

- Anytime the UI or downstream service needs frequent MTM updates but cannot rely on Streamlit reruns or repeated broker queries.
- When multiple components (dashboard, monitors, reconcilers) require the same option LTP feed.
- Hosted deployments where websocket ticks may stall and you need a deterministic fallback with visibility into quote age.

## When NOT to Use

- Strategies without persistent positions (nothing to snapshot) or when broker APIs already stream MTM to the UI over a websocket you control end-to-end.
- Environments where background threads are disallowed (e.g., serverless functions).

## Associated Risks

1. **Thread lifecycle leaks** – Always stop the tracker thread when the runner stops to avoid dangling threads between reruns/deployments.
2. **Stale quotes** – Snapshot exposes `quote_age_sec`; the UI must warn users when age > SLA instead of blindly trusting cached values.
3. **Rate limits** – REST fallback only fires when no fresh tick is available. Keep the stale threshold conservative (≤5 s) and share results across monitors/UI to avoid duplicate calls.

## Example Usage

```python
# Start tracker with runner
runner.start()
snapshot = runner.get_active_pnl_snapshot()
for trade in snapshot["trades"]:
    print(trade["tradingsymbol"], trade["unrealized_value"])

# Inject quote provider into PositionMonitor
monitor = PositionMonitor(
    broker=broker,
    ...,
    ltp_provider=runner._build_ltp_provider(tradingsymbol, symbol, strike, direction),
)
```

## References

- Implementation: `engine/live_runner.py` (`_compute_active_pnl_snapshot`, `_get_option_quote`, `get_active_pnl_snapshot`)
- Tick streamer health: `engine/tick_stream.py`
- Dashboard consumption: `dashboard/ui_frontend.py` (`active_pnl_snapshot` block)

