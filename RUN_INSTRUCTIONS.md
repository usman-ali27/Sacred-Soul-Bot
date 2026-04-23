# 🚀 Sacred Soul — Full System Startup Guide

### ⚡ QUICK START (Master Command)
To start everything at once (Backend, Frontend, and Both Bots), run:
```powershell
.\start_all.ps1
```

---

### 1. FastAPI Backend (The Engine)
This provides the data for the dashboard and the bots.
```powershell
# In the root directory (d:\Angular\ICT_BOT)
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

### 2. Next.js Frontend (The Dashboard)
This is your premium visual interface.
```powershell
# Go to the frontend folder
cd frontend
npm run dev
```
*Access at: http://localhost:3000*

### 3. Grid Strategy Daemon (Live Grid Bot)
This monitors and executes your Grid levels (BUY_1, SELL_1, etc.).
```powershell
# In the root directory
python grid_daemon.py
```

### 4. ICT Signal Worker (AI Analysis Bot)
This monitors "Human Traps" (Liquidity Sweeps, FVGs) and places smart signals.
```powershell
# In the root directory
python execution_worker.py
```

---

### 🔍 Monitoring Logs
If you want to see what the bots are doing in real-time, you can watch these files:
- **Grid Bot:** `grid_daemon.log` and `mt5_audit_log.jsonl`
- **ICT Worker:** `mt5_audit_log.jsonl`
- **API Errors:** Check the terminal running `api/main.py`

### 🛠️ Key Config Files
- `.mt5_credentials.json`: MT5 Login and Risk Guardrails (Max Drift, Max Spread).
- `grid_state.json`: Current active grid levels and profit/loss status.
