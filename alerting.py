"""Simple webhook alerting helpers for worker/watchdog operations."""

from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).parent
ALERT_CONFIG_FILE = BASE_DIR / "alert_config.json"
ALERT_STATE_FILE = BASE_DIR / "alert_state.json"


def load_alert_config() -> dict:
    defaults = {
        "enabled": False,
        "webhook_url": "",
        "notify_on_worker_error": True,
        "notify_on_worker_failed": True,
        "notify_on_watchdog_restart": True,
        "cooldown_seconds": 120,
    }
    if not ALERT_CONFIG_FILE.exists():
        return defaults
    try:
        data = json.loads(ALERT_CONFIG_FILE.read_text(encoding="utf-8"))
        defaults.update(data)
        return defaults
    except Exception:
        return defaults


def save_alert_config(cfg: dict) -> None:
    ALERT_CONFIG_FILE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def _load_state() -> dict:
    if not ALERT_STATE_FILE.exists():
        return {}
    try:
        return json.loads(ALERT_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    try:
        ALERT_STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception:
        pass


def _allow_event(event_key: str, cooldown_seconds: int) -> bool:
    state = _load_state()
    now_ts = datetime.now(timezone.utc).timestamp()
    last_ts = float(state.get(event_key, 0.0))
    if now_ts - last_ts < max(1, cooldown_seconds):
        return False
    state[event_key] = now_ts
    _save_state(state)
    return True


def send_webhook_alert(event: str, message: str, severity: str = "info", metadata: dict | None = None) -> bool:
    cfg = load_alert_config()
    if not cfg.get("enabled"):
        return False

    url = str(cfg.get("webhook_url", "")).strip()
    if not url:
        return False

    cooldown = int(cfg.get("cooldown_seconds", 120))
    event_key = f"{event}:{severity}"
    if not _allow_event(event_key, cooldown):
        return False

    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "severity": severity,
        "message": message,
        "metadata": metadata or {},
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            return 200 <= getattr(resp, "status", 0) < 300
    except Exception:
        return False
