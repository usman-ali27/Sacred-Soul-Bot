# Sacred Soul — Master Startup Script
Write-Host '🚀 Starting Sacred Soul AI Ecosystem...' -ForegroundColor Cyan

# 1. Start FastAPI Backend (Quiet mode)
Write-Host '📡 Starting Backend (FastAPI)...'
Start-Process powershell -ArgumentList "-NoExit", "-Command", "uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload --no-access-log" -NoNewWindow

# 2. Start Next.js Frontend
Write-Host '🎨 Starting Frontend (Next.js Dashboard)...'
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd frontend; npm run dev"

# 3. Fetch News and Start Grid Daemon (Bot 1)
Write-Host '🤖 Starting Grid Execution Daemon and News Guard...'
python news_fetcher.py
Start-Process python -ArgumentList "grid_daemon.py" -WindowStyle Hidden

# 4. Start ICT Worker (Bot 2)
Write-Host '🧠 Starting ICT Signal Worker...'
Start-Process python -ArgumentList "execution_worker.py" -WindowStyle Hidden

# 5. Start Signal Bridge (Social Signals)
Write-Host '📡 Starting Discord/Telegram Signal Bridge...'
Start-Process python -ArgumentList "signal_bridge.py" -WindowStyle Hidden

Write-Host '✅ All systems initiated!' -ForegroundColor Green
Write-Host 'Dashboard: http://localhost:3000'
Write-Host 'Backend: http://localhost:8000/docs'
Write-Host 'Check logs for details.'
