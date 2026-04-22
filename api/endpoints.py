
from fastapi import APIRouter, Request
from typing import Any
import sys
sys.path.append("..")
from mt5_connector import MT5Connector
from mt5_trader import _account_cache, _tick_cache
from grid_engine import GRID_STATE_FILE
from ict_engine import *
import json
import os

router = APIRouter()
mt5 = MT5Connector()

@router.post("/mt5/connect")
def mt5_connect(credentials: dict):
    login = credentials.get("login")
    password = credentials.get("password")
    server = credentials.get("server")
    ok, msg = mt5.connect(login, password, server)
    return {"status": "connected" if ok else "error", "message": msg}

@router.get("/mt5/status")
def mt5_status():
    # Return account info, price, open trades
    account = _account_cache.get("info")
    tick = _tick_cache.get("XAUUSD", {}).get("tick")
    # Load grid trades from state file
    grid_trades = []
    if os.path.exists(GRID_STATE_FILE):
        with open(GRID_STATE_FILE) as f:
            grid_trades = json.load(f).get("levels", [])
    return {
        "account": account,
        "tick": tick,
        "positions": grid_trades,
    }

@router.post("/bot/start")
def bot_start(config: dict):
    # TODO: Actually start grid engine
    return {"message": "Bot started (stub)"}

@router.post("/bot/stop")
def bot_stop():
    # TODO: Actually stop grid engine
    return {"message": "Bot stopped (stub)"}

@router.get("/bot/config")
def bot_config():
    # Return live grid config from grid_state.json
    import os
    config = {}
    grid_state_path = os.path.join(os.path.dirname(__file__), "..", "grid_state.json")
    if os.path.exists(grid_state_path):
        with open(grid_state_path) as f:
            try:
                data = json.load(f)
                config = data.get("config", {})
            except Exception as e:
                config = {"error": str(e)}
    else:
        config = {"error": "grid_state.json not found"}
    return config

@router.get("/ai/insight")
def ai_insight():
    # Return live ICT analysis for XAUUSD using ict_engine
    import pandas as pd
    from data_fetcher import fetch_ohlcv
    from ict_engine import swing_highs, swing_lows
    try:
        df = fetch_ohlcv("XAUUSD", "5m")
        if df.empty:
            return {"error": "No data for XAUUSD 5m"}
        # Example: return swing highs/lows as a preview
        highs = swing_highs(df).tolist()
        lows = swing_lows(df).tolist()
        return {
            "symbol": "XAUUSD",
            "timeframe": "5m",
            "swing_highs": highs,
            "swing_lows": lows,
            "count_highs": sum(highs),
            "count_lows": sum(lows)
        }
    except Exception as e:
        return {"error": str(e)}

@router.get("/backtest/run")
def backtest_run():
    # TODO: Run scenario_backtest and return results
    return {"message": "Backtest run (stub)"}
