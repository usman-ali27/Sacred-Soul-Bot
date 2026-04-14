"""Worker watchdog: monitors heartbeat and restarts execution worker if stale.

Run:
    .venv\Scripts\python.exe worker_watchdog.py
"""

from __future__ import annotations

import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from alerting import load_alert_config, send_webhook_alert

BASE_DIR = Path(__file__).parent
WORKER_HEARTBEAT_FILE = BASE_DIR / "worker_heartbeat.json"
WATCHDOG_HEARTBEAT_FILE = BASE_DIR / "watchdog_heartbeat.json"
START_SCRIPT = BASE_DIR / "start_worker.ps1"
STOP_SCRIPT = BASE_DIR / "stop_worker.ps1"


def write_watchdog_heartbeat(status: str, detail: str) -> None:
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "detail": detail,
    }
    try:
        WATCHDOG_HEARTBEAT_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception:
        pass


def read_worker_heartbeat() -> dict | None:
    if not WORKER_HEARTBEAT_FILE.exists():
        return None
    try:
        return json.loads(WORKER_HEARTBEAT_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None


def restart_worker() -> str:
    if STOP_SCRIPT.exists():
        subprocess.run([
            "powershell.exe", "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", str(STOP_SCRIPT),
        ], check=False)

    if START_SCRIPT.exists():
        subprocess.run([
            "powershell.exe", "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", str(START_SCRIPT),
        ], check=False)
        return "restart command sent"

    return "start_worker.ps1 not found"


def main() -> None:
    print("[watchdog] started")
    stale_seconds = 45
    check_every = 10

    while True:
        alert_cfg = load_alert_config()
        hb = read_worker_heartbeat()
        if not hb or not hb.get("timestamp"):
            write_watchdog_heartbeat("waiting", "no worker heartbeat found yet")
            time.sleep(check_every)
            continue

        try:
            ts = datetime.fromisoformat(hb["timestamp"])
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - ts).total_seconds()
        except Exception:
            write_watchdog_heartbeat("warning", "invalid worker heartbeat timestamp")
            time.sleep(check_every)
            continue

        if age > stale_seconds:
            detail = f"stale heartbeat ({age:.0f}s) -> restarting worker"
            print(f"[watchdog] {detail}")
            write_watchdog_heartbeat("restarting", detail)
            if alert_cfg.get("notify_on_watchdog_restart", True):
                send_webhook_alert(
                    event="watchdog_restart",
                    severity="warning",
                    message=detail,
                )
            res = restart_worker()
            write_watchdog_heartbeat("restarted", res)
            time.sleep(20)
            continue

        status = hb.get("status", "unknown")
        if status in {"error", "failed"}:
            detail = f"worker status={status} -> restarting worker"
            print(f"[watchdog] {detail}")
            write_watchdog_heartbeat("restarting", detail)
            if alert_cfg.get("notify_on_watchdog_restart", True):
                send_webhook_alert(
                    event="watchdog_restart",
                    severity="warning",
                    message=detail,
                )
            res = restart_worker()
            write_watchdog_heartbeat("restarted", res)
            time.sleep(20)
            continue

        write_watchdog_heartbeat("healthy", f"worker heartbeat age {age:.0f}s")
        time.sleep(check_every)


if __name__ == "__main__":
    main()
