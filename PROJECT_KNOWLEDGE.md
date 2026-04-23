# Sacred Soul Bot — Project Knowledge Base
> **Read this file at the start of every session.** It contains the full architecture, API contract, known issues, credentials, and fix history.
> Last Updated: 2026-04-22

---

## 1. Project Overview

**Sacred Soul Bot** is an XAUUSD-focused algorithmic trading dashboard with:
- **Python FastAPI backend** — interfaces MetaTrader 5 (MT5), runs grid trading engine
- **Next.js 14 frontend** — real-time dashboard replacing the old Streamlit `app.py`

The system runs two processes:
1. `api/main.py` — FastAPI server on `http://localhost:8000`
2. `frontend/` — Next.js dev server on `http://localhost:3000`

The old Streamlit app (`app.py`, 3440 lines) has been fully superseded by this setup. **Do NOT edit `app.py` for new features** — it is the reference doc only.

---

## 2. Demo MT5 Credentials

```
Login:    1513116939
Password: Z9$5v?ha
Server:   FTMO-Demo
```

Credentials are also stored in `.mt5_credentials.json` in the root directory.

---

## 3. Directory Structure

```
d:\Angular\ICT_BOT\
│
├── api/
│   ├── main.py          ← FastAPI app entry point (port 8000)
│   ├── endpoints.py     ← ALL API route definitions
│   ├── __init__.py
│   └── requirements.txt
│
├── frontend/            ← Next.js 14 app (TypeScript)
│   └── src/
│       ├── app/
│       │   └── page.tsx          ← Root page, data fetch loop, tab routing
│       ├── components/
│       │   ├── AccountStats.tsx   ← Equity/PnL/drawdown display
│       │   ├── AIAnalysisTab.tsx  ← ICT bias signals + confluence matrix
│       │   ├── AIInsightPanel.tsx ← Simple bias summary string
│       │   ├── BacktestPanel.tsx  ← Full Recharts backtest UI (equity/monthly/trades)
│       │   ├── ConfigForm.tsx     ← GridConfig editor (saves to backend)
│       │   ├── ConnectModal.tsx   ← MT5 connect dialog
│       │   ├── LogViewer.tsx      ← Audit log table (scrollable)
│       │   ├── NewsFeed.tsx       ← News items display (currently static placeholder)
│       │   ├── PropFirmPanel.tsx  ← Prop firm risk calculator + account health
│       │   ├── TradeTable.tsx     ← Open grid positions table
│       │   └── TradingChart.tsx   ← Simple SVG price line chart
│       └── utils/
│           └── api.ts             ← All axios API calls (tradingApi object)
│
├── app.py               ← LEGACY Streamlit app (reference only, do not run)
├── main.py              ← LEGACY Streamlit entry (reference only)
├── grid_engine.py       ← Core grid strategy engine (GridConfig, GridState)
├── grid_backtest.py     ← Backtest runner (BacktestConfig, run_grid_backtest)
├── grid_brain.py        ← AI recommendation engine (ML-based spacing/direction)
├── mt5_trader.py        ← All MT5 interactions (connect, orders, positions, audit)
├── mt5_connector.py     ← Simple MT5 connection wrapper (legacy)
├── ict_engine.py        ← ICT concept computation (FVG, MSS, OB, OTE, Sweep…)
├── data_fetcher.py      ← fetch_ohlcv() — OHLCV bars from MT5
├── config.py            ← TRADING_MODES, INSTRUMENTS, TIMEFRAMES, ALL_CONCEPTS, PRESETS
├── prop_firm.py         ← Prop firm simulation + position sizing
├── alerting.py          ← Webhook alert system (Telegram/Discord compatible)
├── performance_tracker.py ← Stats computation (Sharpe, Calmar, drawdown)
├── execution_worker.py  ← Background trade execution worker
├── worker_watchdog.py   ← Watchdog process for execution_worker
├── grid_state.json      ← Persisted GridState (active grid configuration)
├── grid_audit_log.jsonl ← Grid trade audit (JSONL, one entry per event)
├── mt5_audit_log.jsonl  ← MT5 execution audit log
├── worker_config.json   ← Worker process config
├── .mt5_credentials.json ← Saved MT5 login details
└── alert_config.json    ← Alert webhook configuration
```

---

## 4. How to Start the Project

### Step 1 — Start FastAPI Backend
```powershell
cd d:\Angular\ICT_BOT
.\.venv\Scripts\python.exe -m uvicorn api.main:app --reload --port 8000
```

### Step 2 — Start Next.js Frontend
```powershell
cd d:\Angular\ICT_BOT\frontend
npm run dev
```

Then open: `http://localhost:3000`
API docs available at: `http://localhost:8000/docs`

---

## 5. Complete API Endpoint Reference

All routes are under prefix `/api` (e.g., `GET /api/status`).

### System
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/status` | MT5 connection status + timestamp |
| GET | `/api/config/options` | All config options (modes, instruments, timeframes, concepts, presets) |

### MT5
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/mt5/connect` | Connect MT5 with `{login, password, server}` |
| GET | `/api/mt5/account` | Account info: balance, equity, profit, margin, daily_loss_pct, currency |
| GET | `/api/mt5/positions` | ✅ **ADDED 2026-04-22** — Live open positions list |

### Market
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/market/ticker?symbol=XAUUSD` | Live bid/ask/spread |
| GET | `/api/market/signals?symbol=XAUUSD&timeframe=15m` | ICT bias: BULLISH/BEARISH/NEUTRAL + confidence + signal details |

### Bot (Grid Engine)
| Method | Path | Body | Description |
|--------|------|------|-------------|
| GET | `/api/bot/state` | — | Current grid state (active, levels, pnl_usd, run_id) |
| GET | `/api/bot/config` | — | Current GridConfig dict |
| POST | `/api/bot/config` | GridConfig fields | Update grid configuration |
| POST | `/api/bot/activate` | — | Start the grid (builds levels, places orders) |
| POST | `/api/bot/deactivate` | — | Stop the grid (no orders closed automatically) |
| GET | `/api/bot/logs?limit=100` | — | Recent audit log entries |
| GET | `/api/bot/levels` | — | ✅ **ADDED 2026-04-22** — All grid levels with price, SL, TP, status for chart overlay |
| POST | `/api/bot/backtest` | `{symbol, timeframe, days, spread, slippage, base_lot}` | Run grid simulation |
| POST | `/api/bot/prop-sim` | `{symbol, timeframe, days}` | **Stub** — returns basic message (not fully implemented) |

### /api/mt5/account Response Schema
```json
{
  "balance": 100000.0,
  "equity": 99850.0,
  "profit": -150.0,
  "margin": 300.0,
  "margin_free": 99550.0,
  "daily_loss_pct": 0.15,
  "total_loss_pct": 0.15,
  "currency": "USD"
}
```

### /api/bot/state Response Schema
```json
{
  "active": true,
  "symbol": "XAUUSD",
  "timeframe": "15m",
  "open_levels": 3,
  "pending_levels": 5,
  "pnl_usd": 42.50,
  "run_id": "abc123"
}
```

### /api/mt5/positions Response Schema (one item)
```json
{
  "id": 12345678,
  "symbol": "XAUUSD",
  "type": "BUY",
  "entryPrice": 2345.67,
  "lotSize": 0.01,
  "pnl": 12.50,
  "status": "OPEN",
  "sl": 2335.0,
  "tp": 2360.0,
  "magic": 9991,
  "comment": "Grid L3",
  "time": "2026-04-22T07:10:00"
}
```

### /api/bot/levels Response Schema
```json
{
  "active": true,
  "anchor_price": 4763.37,
  "symbol": "XAUUSD",
  "levels": [
    {
      "level_id": "BUY_1",
      "price": 4760.31,
      "direction": "BUY",
      "lot": 0.01,
      "status": "PENDING",
      "sl_price": 4750.23,
      "tp_price": 4766.64,
      "entry_price": null,
      "profit_usd": 0.0,
      "ticket": null
    }
  ]
}
```

### /api/bot/backtest Response Schema
```json
{
  "summary": {
    "trades": 142, "wins": 98, "losses": 44,
    "win_rate": 69.01, "net_pnl": 1240.50,
    "max_dd": 380.0, "profit_factor": 2.31,
    "sharpe": 1.88, "calmar": 3.26,
    "max_consec_wins": 9, "max_consec_losses": 4,
    "avg_win": 18.50, "avg_loss": 12.30, "expectancy": 8.72
  },
  "equity_curve": [{"time": "ISO8601", "equity": 10042.0}, "..."],
  "monthly": [{"month": "2026-01", "end_equity": 10450.0, "min_equity": 9980.0, "max_equity": 10500.0, "month_pnl": 450.0}],
  "trades": [{"time": "ISO8601", "direction": "BUY", "entry": 2341.0, "exit": 2359.0, "lot": 0.01, "pnl": 18.0, "result": "WIN"}]
}
```

---

## 6. Frontend Data Flow

### Polling Loop (every 2 seconds — `page.tsx` useEffect)
```
Promise.all([
  GET /api/status        → setMt5Connected
  GET /api/mt5/account   → setAccount
  GET /api/market/ticker → setTicker + chartData
  GET /api/bot/state     → setBotState + setAutoTrading
  GET /api/market/signals → setSignals
  GET /api/bot/logs      → setLogs
  GET /api/mt5/positions → setTrades
  GET /api/bot/levels    → setGridLevels
])
```

### Static Fetches (once on mount)
```
GET /api/config/options → setOptions
GET /api/bot/config     → setConfig
```

### State → Component Mapping
| State Variable | Components |
|---|---|
| `mt5Connected` | Header status badge, ConnectModal trigger |
| `account` | `AccountStats`, `PropFirmPanel` |
| `ticker` | Header price/spread, `chartData` |
| `botState` | `AccountStats` (open_levels), Header toggle button |
| `signals` | `AIAnalysisTab`, `AIInsightPanel` |
| `logs` | `LogViewer` |
| `config` | `ConfigForm` |
| `options` | `ConfigForm`, `BacktestPanel` |
| `trades` | `TradeTable` |
| `chartData` | `TradingChart` |
| `gridLevels` | `TradingChart` (level overlay lines) |
| `anchorPrice` | `TradingChart` (anchor reference line) |

---

## 7. GridConfig Fields (Python dataclass → ConfigForm inputs)

These are the **exact field names** — the frontend `ConfigForm` must use these keys:

```python
symbol: str = "XAUUSD"
timeframe: str = "15m"
base_lot: float = 0.01
levels_buy: int = 3
levels_sell: int = 3
spacing_multiplier: float = 1.5      # ATR × this = grid spacing
tp_multiplier: float = 1.0           # spacing × this = take profit distance
sl_multiplier: float = 3.0           # spacing × this = stop loss distance
max_open_levels: int = 6
basket_take_profit_usd: float = 80.0
basket_stop_loss_usd: float = 120.0
basket_close_on_profit: bool = True
basket_close_on_loss: bool = True
ai_direction_enabled: bool = True    # Use ICT bias to set grid direction
ai_spacing_enabled: bool = True      # Use grid brain to adjust spacing
max_daily_loss_usd: float = 500.0
max_drawdown_pct: float = 8.0
```

---

## 8. Audit Log Schema (LogViewer fields)

The backend `load_audit_log()` in `mt5_trader.py` returns JSONL entries from `mt5_audit_log.jsonl`.
The `LogViewer` component reads these fields:

```json
{
  "timestamp": "2026-04-22T07:10:00.123Z",
  "event": "ORDER_PLACED | LEVEL_CLOSED | ERROR | GRID_ACTIVATED",
  "message": "Optional human text",
  "direction": "BUY | SELL",
  "symbol": "XAUUSD",
  "entry_price": 2345.67,
  "profit_usd": 18.50
}
```

---

## 9. Known Issues & Status

### ✅ Fixed (2026-04-22)

| # | Issue | File Fixed |
|---|---|---|
| 1 | "prop" tab label showed "Settings" (same as config tab) | `page.tsx` |
| 2 | `PropFirmPanel` received `botState?.account` (always undefined) | `page.tsx` |
| 3 | `trades` state was never fetched — TradeTable always empty | `page.tsx`, `api.ts`, `endpoints.py` |
| 4 | `/api/mt5/positions` endpoint was missing from backend | `endpoints.py` |
| 5 | `getPositions()` & `propSim()` missing from `tradingApi` | `api.ts` |
| 6 | Toggle bot: UI state not reverted on API failure | `page.tsx` |
| 7 | Unused `AxiosResponse` import in `page.tsx` | `page.tsx` |
| 8 | `trades` typed as `never[]` — TypeScript compile error | `page.tsx` |
| 9 | LogViewer showed `undefined` — wrong field names (event/entry_price) | `LogViewer.tsx` |
| 10 | TradingChart was SVG placeholder with no grid level overlay | `TradingChart.tsx` |
| 11 | `/api/bot/levels` endpoint missing — no way to show grid on chart | `endpoints.py` |
| 12 | `getLevels()` missing from `tradingApi` | `api.ts` |

### 🟡 Pending / Known Stubs

| # | Issue | Notes |
|---|---|---|
| 1 | `POST /api/bot/prop-sim` returns stub | Backend returns `{"status": "ready", "message": "..."}` — no real simulation |
| 2 | `NewsFeed` shows hardcoded data | No news API integrated. Backend has `# TODO: ForexFactory API` in `app.py` |
| 3 | `TradingChart` is SVG placeholder | Should be upgraded to full Recharts candlestick chart |
| 4 | `ConnectModal` shows no success toast on connect | `onSuccess()` is a no-op in `page.tsx` — polling loop catches it in 2s |
| 5 | Prop simulation not wired to real backtest | `PropFirmPanel` is purely local state (position sizing calculator only) |
| 6 | `AIInsightPanel` shows plain text string | Could be upgraded to rich component with trend icons |
| 7 | `AccountStats.tsx` hardcodes FTMO 4% daily / 10% max DD thresholds | Should be configurable from backend config |

---

## 10. Key Python Backend Modules

### `mt5_trader.py`
- `connect_mt5(MT5Config)` → `(bool, str)` — connects to MT5 terminal
- `disconnect_mt5()` — cleans up MT5 connection
- `is_mt5_alive()` → `bool`
- `get_account_info()` → `dict` (balance, equity, profit, margin, margin_free, currency)
- `get_open_positions()` → `list[dict]` — all open MT5 positions
- `get_live_price(symbol)` → `{bid, ask, time}`
- `execute_trade(cfg, signal)` → places live order
- `close_position(ticket)` → closes a specific position
- `load_audit_log()` → `list[dict]` from `mt5_audit_log.jsonl`
- `load_credentials()` / `save_credentials()` — `.mt5_credentials.json`

### `grid_engine.py`
- `GridConfig` — dataclass with all grid parameters
- `GridState` — runtime state with levels list
- `load_grid_state()` / `save_grid_state(gs)` — persists to `grid_state.json`
- `activate_grid(price, df, cfg, starting_balance)` → `GridState`
- `deactivate_grid(gs)` → `GridState`
- `build_grid_levels(price, atr, cfg)` → list of `GridLevel`
- `should_close_basket(gs, current_price)` → bool — checks TP/SL
- `basket_floating_pnl_usd(gs)` → float

### `grid_backtest.py`
- `BacktestConfig` — spread_points, slippage_points
- `run_grid_backtest(df, cfg, bt_cfg)` → dict with `summary`, `equity_curve`, `monthly`, `trades`

### `ict_engine.py`
- `compute_all(df)` → dict of DataFrames keyed by concept name
- Concepts: `FVG`, `MSS`, `OB`, `OTE`, `Liquidity Sweep`, `Breaker Block`, `Mitigation`, `PO3`

### `config.py`
```python
TRADING_MODES = {"Scalping": ..., "Intraday": ..., "Swing": ...}
INSTRUMENTS = {"XAUUSD": "XAUUSD", "EURUSD": "EURUSD", ...}
TIMEFRAMES = {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "4h": 240, "Daily": 1440}
ALL_CONCEPTS = ["FVG", "MSS", "OB", "OTE", "Liquidity Sweep", "Breaker Block", "Mitigation", "PO3"]
PRESETS = {"Conservative": [...], "Aggressive": [...], ...}
```

---

## 11. Frontend Tab Structure

```
Tabs: ["monitor", "ict", "backtest", "config", "prop"]
Labels: "Live Monitor" | "AI Analysis" | "Simulation" | "Settings" | "Prop Firm"
```

### Tab → Component Map
| Tab | Component | Data Source |
|-----|-----------|-------------|
| `monitor` | `TradingChart`, `TradeTable`, `NewsFeed`, `LogViewer`, `AccountStats`, `AIInsightPanel` | Polling loop |
| `ict` | `AIAnalysisTab` | `signals` state |
| `backtest` | `BacktestPanel` | On-demand `POST /api/bot/backtest` |
| `config` | `ConfigForm` | `config` + `options` state |
| `prop` | `PropFirmPanel` | `account` state + local state |

---

## 12. Improvement Wishlist (Future Sessions)

1. **Real Candlestick Chart** — Replace `TradingChart` SVG placeholder with Recharts `ComposedChart` pulling OHLCV data via a new `GET /api/market/ohlcv?symbol=X&tf=Y` endpoint
2. **News API** — Integrate ForexFactory/Myfxbook economic calendar for real news feed
3. **WebSocket** — Replace 2s polling with WebSocket for price tick and bot state updates
4. **Prop Sim** — Wire `PropFirmPanel` to actually call `POST /api/bot/prop-sim` and show real backtest results filtered through prop firm rules
5. **Alert Config UI** — Expose `alert_config.json` settings in the Settings tab (webhook URL, toggles)
6. **Worker Status** — Show execution worker and watchdog heartbeat status on the dashboard
7. **Multi-symbol** — Extend beyond XAUUSD to support EURUSD, GBPUSD grid strategies
8. **Chart Overlays** — Add ICT overlay drawing (FVG boxes, OB zones, MSS markers) on the chart

---

## 13. Change Log

| Date | Change | Files |
|------|--------|-------|
| 2026-04-22 | Migrated from Streamlit to Next.js + FastAPI | All |
| 2026-04-22 | Fixed prop tab label (showed "Settings" duplicate) | `page.tsx` |
| 2026-04-22 | Fixed PropFirmPanel receiving `botState?.account` (undefined) | `page.tsx` |
| 2026-04-22 | Added `GET /api/mt5/positions` endpoint | `endpoints.py` |
| 2026-04-22 | Added `getPositions()` and `propSim()` to `tradingApi` | `api.ts` |
| 2026-04-22 | Wired `trades` state from `/mt5/positions` into polling loop | `page.tsx` |
| 2026-04-22 | Fixed optimistic bot toggle (now reverts on API failure) | `page.tsx` |
| 2026-04-22 | Fixed `trades` state typed as `never[]` → `any[]` (TS error) | `page.tsx` |
| 2026-04-22 | Fixed positions endpoint: type was double-converted (BUY/SELL already a string) | `endpoints.py` |
| 2026-04-22 | **Live backtest run** — XAUUSD 15m 30d: 195 trades, 76.4% WR, +$1,828 net PnL, PF 2.17, Sharpe 8.92 | API |
| 2026-04-22 | Added backtest `spacing_multiplier` param support | `endpoints.py` |
