"""Safe preflight checks for Sacred Soul Bot auto-trade pipeline.

This script does NOT place real orders.
It validates the key runtime path before enabling live execution.

Run:
    .venv\Scripts\python.exe preflight_autotrade.py
"""

from __future__ import annotations

import importlib
import json
from datetime import datetime
from pathlib import Path

from data_fetcher import fetch_ohlcv
from trade_generator import generate_signals
from performance_tracker import compute_stats

BASE_DIR = Path(__file__).parent


def ok(msg: str):
    print(f"[OK]   {msg}")


def warn(msg: str):
    print(f"[WARN] {msg}")


def fail(msg: str):
    print(f"[FAIL] {msg}")


def check_file(path: Path):
    if path.exists():
        ok(f"{path.name} exists")
    else:
        warn(f"{path.name} missing")


def main():
    print("=" * 72)
    print("SACRED SOUL BOT - AUTO-TRADE PREFLIGHT")
    print(f"Time: {datetime.now().isoformat()}")
    print("=" * 72)

    # 1) Required project/runtime files
    for name in [
        "app.py",
        "execution_worker.py",
        "worker_watchdog.py",
        "mt5_trader.py",
        "alerting.py",
        "requirements.txt",
        "start_worker.ps1",
        "start_watchdog.ps1",
        "install_scheduled_tasks.ps1",
    ]:
        check_file(BASE_DIR / name)

    # 2) Python module import checks
    print("\n-- Import checks --")
    for mod in [
        "streamlit",
        "streamlit_autorefresh",
        "pandas",
        "numpy",
        "plotly",
        "yfinance",
        "scipy",
    ]:
        try:
            importlib.import_module(mod)
            ok(f"module import: {mod}")
        except Exception as exc:
            fail(f"module import failed: {mod} -> {exc}")

    # Optional package check (not always installed in cloud/local)
    try:
        importlib.import_module("MetaTrader5")
        ok("module import: MetaTrader5")
    except Exception as exc:
        warn(f"MetaTrader5 not importable: {exc}")

    # 3) Data + signal + stats pipeline
    print("\n-- Data/signal pipeline --")
    df = fetch_ohlcv("XAUUSD", "5m")
    if df.empty:
        fail("No 5m data returned for XAUUSD")
    else:
        ok(f"Fetched XAUUSD 5m bars: {len(df)}")
        sigs = generate_signals(
            df,
            ["Liquidity Sweep", "FVG", "Order Flow"],
            rr_ratio=1.5,
            sweep_lookback=10,
        )
        ok(f"Signal generation completed: {len(sigs)} rows")
        if not sigs.empty:
            s = compute_stats(sigs)
            ok(
                "Stats computed: "
                f"trades={s['total_trades']}, win_rate={s['win_rate']}%, pf={s['profit_factor']}"
            )
        else:
            warn("No signals for current test filter")

    # 4) Worker config/heartbeat IO checks
    print("\n-- Worker/watchdog/alert IO checks --")
    worker_cfg = BASE_DIR / "worker_config.json"
    worker_hb = BASE_DIR / "worker_heartbeat.json"
    watchdog_hb = BASE_DIR / "watchdog_heartbeat.json"
    alert_cfg = BASE_DIR / "alert_config.json"

    sample_worker_cfg = {
        "enabled": False,
        "auto_trade_enabled": False,
        "symbol": "XAUUSD",
        "timeframe": "5m",
        "concepts": ["Liquidity Sweep", "FVG", "Order Flow"],
        "rr": 1.5,
        "sweep_lookback": 10,
        "lot_size": 0.02,
        "poll_seconds": 5,
        "bars_window": 500,
    }
    worker_cfg.write_text(json.dumps(sample_worker_cfg, indent=2), encoding="utf-8")
    ok("worker_config.json write test passed")

    worker_hb.write_text(
        json.dumps({"timestamp": datetime.utcnow().isoformat(), "status": "test", "detail": "preflight"}, indent=2),
        encoding="utf-8",
    )
    ok("worker_heartbeat.json write test passed")

    watchdog_hb.write_text(
        json.dumps({"timestamp": datetime.utcnow().isoformat(), "status": "test", "detail": "preflight"}, indent=2),
        encoding="utf-8",
    )
    ok("watchdog_heartbeat.json write test passed")

    if not alert_cfg.exists():
        alert_cfg.write_text(
            json.dumps(
                {
                    "enabled": False,
                    "webhook_url": "",
                    "notify_on_worker_error": True,
                    "notify_on_worker_failed": True,
                    "notify_on_watchdog_restart": True,
                    "cooldown_seconds": 120,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        ok("alert_config.json bootstrap created")
    else:
        ok("alert_config.json already exists")

    # 5) Live-trading readiness reminders
    print("\n-- Live-trading readiness --")
    print("1) MT5 desktop app running and logged in")
    print("2) Saved credentials valid (login/password/server/symbol)")
    print("3) Worker Mode enabled and worker started")
    print("4) Watchdog running")
    print("5) Guardrails and policy profile set")
    print("6) Optional webhook test sent")

    print("\n" + "=" * 72)
    print("PREFLIGHT COMPLETE")
    print("=" * 72)


if __name__ == "__main__":
    main()
