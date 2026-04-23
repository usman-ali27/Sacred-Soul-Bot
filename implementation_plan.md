# Migration to Modern Dashboard (Next.js + FastAPI)

This plan outlines the steps to move the trading UI from the current Streamlit implementation (`app.py`) to the professional Next.js frontend, utilizing a FastAPI backend for real-time data handling.

## User Review Required

> [!IMPORTANT]
> This is a major architectural change. Once we switch, the primary control for the bot will move to the Next.js web interface. The Streamlit app will remain as a backup.

- **Real-time Engine**: We will implement high-frequency polling or WebSockets to ensure the price on the dashboard matches the broker exactly without page refreshes.
- **Unified Sidebar**: The complex settings from the Streamlit sidebar will be reimagined as a responsive React sidebar.

## Proposed Changes

### 1. Backend API (Python/FastAPI)
We will build out the `api/` directory into a full-featured bridge between the trading engine and the web frontend.

#### [MODIFY] [endpoints.py](file:///d:/Angular/ICT_BOT/api/endpoints.py)
- Expand endpoints to include:
  - `GET /api/market/ticker`: Live price and spread.
  - `GET /api/market/htf`: ICT analysis and bias.
  - `POST /api/grid/configure`: Update grid parameters.
  - `GET /api/stats/pnl`: Historical and daily PnL data.
  - `POST /api/backtest/run`: Trigger historical simulations.

#### [MODIFY] [main.py](file:///d:/Angular/ICT_BOT/api/main.py)
- Ensure robust CORS handling and startup/shutdown logic for the MT5 connection.

---

### 2. Frontend (React/Next.js)
We will wire the existing UI components to the new API.

#### [MODIFY] [page.tsx](file:///d:/Angular/ICT_BOT/frontend/src/app/page.tsx)
- Replace all mock `useState` initializers with data fetched from the API.
- Implement a 1-second refresh cycle for market data.
- Wire the "Engage Smart Bot" button to the `/api/bot/start` endpoint.

#### [MODIFY] [AccountStats.tsx](file:///d:/Angular/ICT_BOT/frontend/src/components/AccountStats.tsx) [NEW]
- Ensure the account metrics component is reactive to the API data.

---

### 3. Execution & Performance
- **Unified Settings**: Move the sidebar logic to a dedicated React component.
- **Cache Management**: Use the backend caches (`_account_cache`, `_tick_cache`) to serve frontend requests instantly.

## Verification Plan

### Automated Tests
- Test API endpoints using `curl` or a test script to ensure they return correct data from the trading engine.
- Verify that the FastAPI server can run alongside the bot processes.

### Manual Verification
- Run the Next.js dev server and verify that the price updates match the MT5 terminal.
- Test activating/deactivating the grid from the web UI and observing the state change in `grid_state.json`.
