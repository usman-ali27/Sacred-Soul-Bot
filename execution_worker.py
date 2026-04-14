"""Background MT5 execution worker for live ICT auto-trading.

Run:
    .venv\Scripts\python.exe execution_worker.py

This worker is intentionally separate from Streamlit so execution timing is not
coupled to UI reruns or heavy dashboard calculations.
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

from alerting import load_alert_config, send_webhook_alert
from data_fetcher import fetch_ohlcv
from mt5_trader import MT5Config, connect_mt5, execute_trade, load_credentials
from trade_generator import generate_signals

BASE_DIR = Path(__file__).parent
WORKER_CONFIG_FILE = BASE_DIR / "worker_config.json"
WORKER_STATE_FILE = BASE_DIR / "worker_state.json"
WORKER_HEARTBEAT_FILE = BASE_DIR / "worker_heartbeat.json"


def _tf_to_minutes(tf: str) -> int:
    return {
        "1m": 1,
        "5m": 5,
        "15m": 15,
        "1h": 60,
        "4h": 240,
        "Daily": 1440,
    }.get(tf, 5)


def load_worker_config() -> dict:
    defaults = {
        "enabled": False,
        "auto_trade_enabled": True,
        "symbol": "XAUUSD",
        "timeframe": "5m",
        "concepts": ["Liquidity Sweep", "FVG", "Order Flow"],
        "rr": 1.5,
        "sweep_lookback": 10,
        "lot_size": 0.02,
        "poll_seconds": 5,
        "bars_window": 500,
    }
    if not WORKER_CONFIG_FILE.exists():
        return defaults
    try:
        data = json.loads(WORKER_CONFIG_FILE.read_text(encoding="utf-8"))
        defaults.update(data)
        return defaults
    except Exception:
        return defaults


def load_state() -> dict:
    if not WORKER_STATE_FILE.exists():
        return {"executed_keys": []}
    try:
        return json.loads(WORKER_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"executed_keys": []}


def save_state(state: dict) -> None:
    try:
        WORKER_STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception:
        pass


def write_heartbeat(status: dict) -> None:
    status["timestamp"] = datetime.utcnow().isoformat()
    try:
        WORKER_HEARTBEAT_FILE.write_text(json.dumps(status, indent=2), encoding="utf-8")
    except Exception:
        pass


def build_live_signals(cfg: dict):
    df = fetch_ohlcv(cfg["symbol"], cfg["timeframe"])
    if df.empty:
        return df, None

    live_df = df.tail(max(int(cfg.get("bars_window", 500)), int(cfg.get("sweep_lookback", 10)) * 10)).copy()
    sigs = generate_signals(
        live_df,
        cfg.get("concepts", []),
        rr_ratio=float(cfg.get("rr", 1.5)),
        sweep_lookback=int(cfg.get("sweep_lookback", 10)),
    )
    if sigs.empty:
        return live_df, None

    now_ts = live_df.index.max()
    fresh_age = _tf_to_minutes(cfg["timeframe"]) * 2
    fresh = sigs[(sigs["status"] == "OPEN") & (sigs["signal_time"] >= now_ts - pd.Timedelta(minutes=fresh_age))]
    if fresh.empty:
        return live_df, None

    latest = fresh.sort_values("signal_time", ascending=False).iloc[0]
    return live_df, latest


def build_mt5_config_from_credentials(creds: dict) -> MT5Config:
    return MT5Config(
        login=int(creds["login"]),
        password=creds["password"],
        server=creds["server"],
        symbol=creds.get("symbol", "XAUUSD"),
        max_lot=float(creds.get("max_lot", 0.10)),
        max_spread_price=float(creds.get("max_spread_price", 0.60)),
        max_entry_drift_price=float(creds.get("max_entry_drift_price", 2.00)),
        max_trades_per_day=int(creds.get("max_trades_per_day", 8)),
        max_open_positions=int(creds.get("max_open_positions", 2)),
        enforce_session_window=bool(creds.get("enforce_session_window", False)),
        session_start_utc=int(creds.get("session_start_utc", 0)),
        session_end_utc=int(creds.get("session_end_utc", 23)),
    )


def main() -> None:
    print("[worker] started")
    connected = False

    while True:
        alert_cfg = load_alert_config()
        cfg = load_worker_config()
        poll_seconds = max(2, int(cfg.get("poll_seconds", 5)))

        if not cfg.get("enabled", False):
            write_heartbeat({"status": "idle", "detail": "worker disabled in config"})
            time.sleep(poll_seconds)
            continue

        creds = load_credentials()
        if not creds or int(creds.get("login", 0)) <= 0:
            write_heartbeat({"status": "error", "detail": "no valid MT5 credentials saved"})
            if alert_cfg.get("notify_on_worker_error", True):
                send_webhook_alert(
                    event="worker_error",
                    severity="warning",
                    message="Execution worker has no valid MT5 credentials.",
                )
            time.sleep(poll_seconds)
            continue

        mt5_cfg = build_mt5_config_from_credentials(creds)
        mt5_cfg.symbol = cfg.get("symbol", mt5_cfg.symbol)

        if not connected:
            ok, msg = connect_mt5(mt5_cfg)
            connected = ok
            write_heartbeat({"status": "connect", "detail": msg})
            if not ok:
                if alert_cfg.get("notify_on_worker_error", True):
                    send_webhook_alert(
                        event="worker_connect_failed",
                        severity="error",
                        message=f"Execution worker failed MT5 connect: {msg}",
                    )
                time.sleep(poll_seconds)
                continue

        try:
            _, latest_sig = build_live_signals(cfg)
            if latest_sig is None:
                write_heartbeat({
                    "status": "monitoring",
                    "detail": "no fresh open signal",
                    "symbol": cfg["symbol"],
                    "timeframe": cfg["timeframe"],
                })
                time.sleep(poll_seconds)
                continue

            sig_key = (
                f"{cfg['symbol']}_{cfg['timeframe']}_{latest_sig['signal_time']}_"
                f"{latest_sig['direction']}_{round(float(latest_sig['entry']), 2)}"
            )
            state = load_state()
            executed = set(state.get("executed_keys", []))

            if sig_key in executed:
                write_heartbeat({
                    "status": "monitoring",
                    "detail": "signal already executed",
                    "signal_key": sig_key,
                })
                time.sleep(poll_seconds)
                continue

            if not cfg.get("auto_trade_enabled", True):
                write_heartbeat({
                    "status": "monitoring",
                    "detail": "auto_trade disabled in worker config",
                    "signal_key": sig_key,
                })
                time.sleep(poll_seconds)
                continue

            lot = min(float(cfg.get("lot_size", 0.02)), mt5_cfg.max_lot)
            result = execute_trade(
                mt5_cfg,
                direction=str(latest_sig["direction"]),
                entry_price=float(latest_sig["entry"]),
                sl_price=float(latest_sig["sl"]),
                tp_price=float(latest_sig["tp"]),
                lot_size=lot,
                comment=f"ICT Worker {cfg.get('timeframe', '5m')}",
            )

            executed.add(sig_key)
            state["executed_keys"] = list(executed)[-3000:]
            save_state(state)

            write_heartbeat({
                "status": "executed" if result.success else "failed",
                "detail": result.message,
                "signal_key": sig_key,
                "symbol": cfg["symbol"],
                "timeframe": cfg["timeframe"],
                "lot_size": lot,
            })
            if (not result.success) and alert_cfg.get("notify_on_worker_failed", True):
                send_webhook_alert(
                    event="worker_trade_failed",
                    severity="error",
                    message=f"Worker trade failed: {result.message}",
                    metadata={
                        "symbol": cfg["symbol"],
                        "timeframe": cfg["timeframe"],
                        "signal_key": sig_key,
                    },
                )

        except Exception as exc:
            write_heartbeat({"status": "error", "detail": f"worker exception: {exc}"})
            if alert_cfg.get("notify_on_worker_error", True):
                send_webhook_alert(
                    event="worker_exception",
                    severity="error",
                    message=f"Execution worker exception: {exc}",
                )
            connected = False

        time.sleep(poll_seconds)


if __name__ == "__main__":
    main()
