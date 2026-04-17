"""
MT5 Auto-Trader — Connects to MetaTrader 5 and executes trades
when ICT signals are generated.

Usage:
    - Provide MT5 credentials (login, password, server) via the dashboard.
    - When a signal is generated, call execute_trade() to place the order.
    - Supports market orders with SL/TP, position sizing from prop firm rules.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import time
from base64 import b64decode, b64encode
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Credential persistence ───────────────────────────────────────
_CRED_FILE = Path(__file__).parent / ".mt5_credentials.json"
_AUDIT_FILE = Path(__file__).parent / "mt5_audit_log.jsonl"

# ── Performance: cached audit + tick data ─────────────────────────
_audit_cache: dict = {"data": [], "mtime": 0.0, "limit": 0}
_tick_cache: dict = {}          # symbol -> {"tick": dict, "ts": float}
_account_cache: dict = {"info": None, "ts": 0.0}
_daily_fill_count: dict = {"date": "", "symbol_counts": {}}
_TICK_CACHE_TTL = 0.5           # 500ms
_ACCOUNT_CACHE_TTL = 1.0        # 1 second

# ── Daily fill counter persistence file ──────────────────────────
_DAILY_FILLS_FILE = Path(__file__).parent / "_daily_fills.json"

# ── MT5 connection health tracking ───────────────────────────────
_mt5_health: dict = {"last_check": 0.0, "alive": False}
_MT5_HEALTH_TTL = 2.0           # check at most every 2 seconds


def save_credentials(login: int, password: str, server: str,
                     symbol: str = "XAUUSD", max_lot: float = 0.10,
                     max_spread_price: float = 0.60,
                     max_entry_drift_price: float = 2.00,
                     max_trades_per_day: int = 8,
                     max_open_positions: int = 2,
                     enforce_session_window: bool = False,
                     session_start_utc: int = 0,
                     session_end_utc: int = 23,
                     min_stop_distance_pips: float = 2.0,
                     max_stop_distance_pips: float = 200.0,
                     min_rr_ratio: float = 1.5):
    """Save MT5 credentials to a local JSON file.

    The password is base64-encoded (not secure encryption — just keeps
    it from being plain-text on disk).  The file is gitignored.
    """
    data = {
        "login": login,
        "password": b64encode(password.encode()).decode(),
        "server": server,
        "symbol": symbol,
        "max_lot": max_lot,
        "max_spread_price": max_spread_price,
        "max_entry_drift_price": max_entry_drift_price,
        "max_trades_per_day": max_trades_per_day,
        "max_open_positions": max_open_positions,
        "enforce_session_window": enforce_session_window,
        "session_start_utc": session_start_utc,
        "session_end_utc": session_end_utc,
        "min_stop_distance_pips": min_stop_distance_pips,
        "max_stop_distance_pips": max_stop_distance_pips,
        "min_rr_ratio": min_rr_ratio,
    }
    _CRED_FILE.write_text(json.dumps(data, indent=2))


def load_credentials() -> dict | None:
    """Load saved credentials.  Returns a dict or None."""
    if not _CRED_FILE.exists():
        return None
    try:
        data = json.loads(_CRED_FILE.read_text())
        data["password"] = b64decode(data["password"]).decode()
        return data
    except Exception:
        return None


def delete_credentials():
    """Remove saved credentials file."""
    if _CRED_FILE.exists():
        _CRED_FILE.unlink()


@dataclass
class MT5Config:
    login: int = 0
    password: str = ""
    server: str = ""
    symbol: str = "XAUUSD"
    max_lot: float = 1.0
    deviation: int = 20  # max slippage in points
    magic: int = 202604   # magic number for bot trades
    max_spread_price: float = 0.60
    max_entry_drift_price: float = 2.00
    kill_switch: bool = False
    max_trades_per_day: int = 8
    max_open_positions: int = 2
    enforce_session_window: bool = False
    session_start_utc: int = 0
    session_end_utc: int = 23
    min_stop_distance_pips: float = 2.0    # reject if SL distance < N pips
    max_stop_distance_pips: float = 200.0  # reject if SL distance > N pips
    min_rr_ratio: float = 1.5              # reject if TP/SL ratio < this


@dataclass
class TradeResult:
    success: bool
    order_id: int | None = None
    message: str = ""
    executed_price: float = 0.0
    lot_size: float = 0.0


@dataclass
class TradeLog:
    entries: list[dict] = field(default_factory=list)

    def add(self, entry: dict):
        entry["timestamp"] = datetime.now().isoformat()
        self.entries.append(entry)
        try:
            with _AUDIT_FILE.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=True) + "\n")
        except Exception:
            # Do not break trading flow if audit persistence fails.
            pass

    def to_list(self) -> list[dict]:
        return list(self.entries)


# Global trade log (session-scoped)
trade_log = TradeLog()


def mt5_runtime_supported() -> tuple[bool, str]:
    """Return whether this runtime can support MT5 terminal integration."""
    if platform.system().lower() != "windows":
        return (
            False,
            "MT5 auto-trade requires Windows + MT5 desktop terminal. "
            "Streamlit Community Cloud runs Linux, so direct MT5 trading is not supported there.",
        )
    return True, "OK"


def connect_mt5(config: MT5Config) -> tuple[bool, str]:
    """Initialize and login to MT5 terminal.

    Returns (success, message).
    """
    supported, reason = mt5_runtime_supported()
    if not supported:
        return False, reason

    try:
        import MetaTrader5 as mt5
    except ImportError:
        return (
            False,
            "MetaTrader5 package is not installed in this Python environment. "
            "Run: pip install MetaTrader5 (Windows runtime only).",
        )

    if not mt5.initialize():
        return False, f"MT5 initialize failed: {mt5.last_error()}"

    authorized = mt5.login(
        login=config.login,
        password=config.password,
        server=config.server,
    )
    if not authorized:
        err = mt5.last_error()
        mt5.shutdown()
        return False, f"MT5 login failed: {err}"

    account_info = mt5.account_info()
    if account_info is None:
        mt5.shutdown()
        return False, "Could not retrieve account info."

    msg = (
        f"Connected to {config.server} | "
        f"Account: {account_info.login} | "
        f"Balance: ${account_info.balance:,.2f} | "
        f"Equity: ${account_info.equity:,.2f} | "
        f"Leverage: 1:{account_info.leverage}"
    )
    return True, msg


def disconnect_mt5():
    """Shutdown MT5 connection."""
    global _mt5_health
    try:
        import MetaTrader5 as mt5
        mt5.shutdown()
    except Exception:
        pass
    _mt5_health = {"last_check": 0.0, "alive": False}


def is_mt5_alive() -> bool:
    """Quick health-check: is MT5 terminal still responding?

    Cached for ``_MT5_HEALTH_TTL`` seconds to avoid spamming the API.
    """
    global _mt5_health
    now = time.monotonic()
    if (now - _mt5_health["last_check"]) < _MT5_HEALTH_TTL:
        return _mt5_health["alive"]
    try:
        import MetaTrader5 as mt5
        info = mt5.terminal_info()
        alive = info is not None
    except Exception:
        alive = False
    _mt5_health = {"last_check": now, "alive": alive}
    return alive


def ensure_mt5_connected(config: "MT5Config") -> tuple[bool, str]:
    """Check MT5 health; if dead, attempt one reconnect.

    Returns (connected, message).
    """
    if is_mt5_alive():
        return True, "OK"
    # Connection lost — attempt reconnect
    logger.warning("MT5 connection lost — attempting reconnect")
    disconnect_mt5()
    ok, msg = connect_mt5(config)
    if ok:
        logger.info("MT5 reconnected successfully")
    else:
        logger.error("MT5 reconnect failed: %s", msg)
    return ok, msg


def get_deal_close_info(ticket: int) -> dict | None:
    """Retrieve actual close price and profit from deal history for a position.

    Returns ``{"close_price": float, "profit": float}`` or None if not found.
    """
    try:
        import MetaTrader5 as mt5
        from datetime import timedelta
        # Search last 7 days of deal history for this position
        now = datetime.now(timezone.utc)
        deals = mt5.history_deals_get(
            now - timedelta(days=7), now, position=ticket
        )
        if not deals:
            return None
        # The closing deal is the one with DEAL_ENTRY_OUT (1) or DEAL_ENTRY_INOUT (2)
        for d in reversed(deals):
            if d.entry in (1, 2):  # OUT or INOUT
                return {"close_price": d.price, "profit": d.profit}
        # Fallback: last deal in the list
        last = deals[-1]
        return {"close_price": last.price, "profit": last.profit}
    except Exception:
        return None


def get_account_info() -> dict | None:
    """Return current MT5 account info as a dict.

    Cached for 1 second to reduce MT5 API calls on fast-refresh pages.
    """
    global _account_cache
    now = time.monotonic()
    if _account_cache["info"] and (now - _account_cache["ts"]) < _ACCOUNT_CACHE_TTL:
        return _account_cache["info"]
    try:
        import MetaTrader5 as mt5
        info = mt5.account_info()
        if info is None:
            return None
        result = {
            "login": info.login,
            "balance": info.balance,
            "equity": info.equity,
            "margin": info.margin,
            "free_margin": info.margin_free,
            "leverage": info.leverage,
            "profit": info.profit,
            "server": info.server,
            "currency": info.currency,
        }
        _account_cache = {"info": result, "ts": now}
        return result
    except Exception:
        return None


def get_open_positions(symbol: str | None = None) -> list[dict]:
    """Return list of open positions, optionally filtered by symbol."""
    try:
        import MetaTrader5 as mt5
        if symbol:
            positions = mt5.positions_get(symbol=symbol)
        else:
            positions = mt5.positions_get()
        if positions is None:
            return []
        return [
            {
                "ticket": p.ticket,
                "symbol": p.symbol,
                "type": "BUY" if p.type == 0 else "SELL",
                "volume": p.volume,
                "price_open": p.price_open,
                "sl": p.sl,
                "tp": p.tp,
                "profit": p.profit,
                "swap": p.swap,
                "magic": p.magic,
                "time": datetime.fromtimestamp(p.time).isoformat(),
            }
            for p in positions
        ]
    except Exception:
        return []


def execute_trade(
    config: MT5Config,
    direction: str,  # "LONG" or "SHORT"
    entry_price: float,
    sl_price: float,
    tp_price: float,
    lot_size: float,
    comment: str = "ICT Bot",
) -> TradeResult:
    """Execute a market order on MT5.

    Args:
        config:      MT5Config with symbol, deviation, magic.
        direction:   "LONG" or "SHORT".
        entry_price: Reference price (market order uses current tick).
        sl_price:    Stop loss price.
        tp_price:    Take profit price.
        lot_size:    Position size in lots.
        comment:     Order comment.

    Returns:
        TradeResult with success status and details.
    """
    prepared = _prepare_trade_request(
        config=config,
        direction=direction,
        entry_price=entry_price,
        sl_price=sl_price,
        tp_price=tp_price,
        lot_size=lot_size,
        comment=comment,
        log_prefix="BLOCKED",
    )
    if not prepared["success"]:
        return TradeResult(False, message=prepared["message"])

    try:
        import MetaTrader5 as mt5
    except ImportError:
        return TradeResult(False, message="MetaTrader5 not installed")

    request = prepared["request"]
    live_sl = prepared["live_sl"]
    live_tp = prepared["live_tp"]
    price = prepared["price"]
    symbol = prepared["symbol"]
    lot_size = prepared["lot_size"]
    digits = prepared["digits"]
    min_stop = prepared["min_stop"]

    _t0 = time.perf_counter()
    result = mt5.order_send(request)
    response_ms = round((time.perf_counter() - _t0) * 1000.0, 2)
    if result is None:
        trade_log.add({
            "status": "FAILED",
            "reason": f"order_send returned None: {mt5.last_error()}",
            "direction": direction,
            "symbol": symbol,
            "lot_size": lot_size,
            "signal_entry": entry_price,
            "live_price": price,
            "response_ms": response_ms,
        })
        return TradeResult(False, message=f"order_send returned None: {mt5.last_error()}")

    if result.retcode != mt5.TRADE_RETCODE_DONE:
        trade_log.add({
            "status": "FAILED",
            "reason": f"{result.retcode} - {result.comment}",
            "direction": direction,
            "symbol": symbol,
            "lot_size": lot_size,
            "signal_entry": entry_price,
            "live_price": price,
            "sl": live_sl,
            "tp": live_tp,
            "response_ms": response_ms,
        })
        return TradeResult(
            False,
            message=(
                f"Order failed: {result.retcode} — {result.comment} | "
                f"price={price} sl={live_sl} tp={live_tp} "
                f"min_stop={min_stop:.{digits}f}"
            ),
        )

    trade_result = TradeResult(
        success=True,
        order_id=result.order,
        message=f"{direction} {lot_size} lots @ {result.price}",
        executed_price=result.price,
        lot_size=lot_size,
    )

    # Log the trade
    trade_log.add({
        "direction": direction,
        "symbol": symbol,
        "lot_size": lot_size,
        "entry": result.price,
        "sl": live_sl,
        "tp": live_tp,
        "signal_entry": entry_price,
        "signal_sl": sl_price,
        "signal_tp": tp_price,
        "order_id": result.order,
        "status": "FILLED",
        "response_ms": response_ms,
    })

    # Update in-memory daily fill counter (avoids re-reading audit log)
    _increment_daily_fill(symbol)

    return trade_result


def preview_trade_execution(
    config: MT5Config,
    direction: str,
    entry_price: float,
    sl_price: float,
    tp_price: float,
    lot_size: float,
    comment: str = "ICT Bot Preview",
) -> TradeResult:
    """Validate a trade end-to-end without sending a live order."""
    prepared = _prepare_trade_request(
        config=config,
        direction=direction,
        entry_price=entry_price,
        sl_price=sl_price,
        tp_price=tp_price,
        lot_size=lot_size,
        comment=comment,
        log_prefix="TEST",
    )
    if not prepared["success"]:
        return TradeResult(False, message=prepared["message"])

    msg = (
        f"DRY RUN OK | {direction} {prepared['lot_size']} lots @ {prepared['price']:.2f} | "
        f"SL {prepared['live_sl']:.2f} | TP {prepared['live_tp']:.2f} | "
        f"Spread {prepared['spread_price']:.2f} | MinStop {prepared['min_stop']:.2f}"
    )
    trade_log.add({
        "status": "TEST_OK",
        "reason": msg,
        "direction": direction,
        "symbol": prepared["symbol"],
        "lot_size": prepared["lot_size"],
        "signal_entry": entry_price,
        "live_price": prepared["price"],
        "sl": prepared["live_sl"],
        "tp": prepared["live_tp"],
    })
    return TradeResult(
        success=True,
        message=msg,
        executed_price=prepared["price"],
        lot_size=prepared["lot_size"],
    )


def close_position(ticket: int) -> TradeResult:
    """Close an open position by ticket number."""
    try:
        import MetaTrader5 as mt5
    except ImportError:
        return TradeResult(False, message="MetaTrader5 not installed")

    position = mt5.positions_get(ticket=ticket)
    if not position:
        return TradeResult(False, message=f"Position {ticket} not found")

    pos = position[0]
    symbol = pos.symbol
    lot = pos.volume

    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return TradeResult(False, message=f"No tick data for {symbol}")

    if pos.type == 0:  # BUY → close with SELL
        order_type = mt5.ORDER_TYPE_SELL
        price = tick.bid
    else:  # SELL → close with BUY
        order_type = mt5.ORDER_TYPE_BUY
        price = tick.ask

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lot,
        "type": order_type,
        "position": ticket,
        "price": price,
        "deviation": 20,
        "magic": pos.magic,
        "comment": "ICT Bot close",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    if result is None:
        return TradeResult(False, message=f"Close failed: {mt5.last_error()}")
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        return TradeResult(False, message=f"Close failed: {result.retcode} — {result.comment}")

    trade_log.add({
        "action": "CLOSE",
        "ticket": ticket,
        "symbol": symbol,
        "lot_size": lot,
        "close_price": result.price,
        "status": "CLOSED",
    })

    return TradeResult(True, order_id=result.order,
                       message=f"Closed {ticket} @ {result.price}")


def get_live_price(symbol: str) -> dict | None:
    """Return current bid/ask/last for *symbol*, or None on failure.

    Uses a short-lived cache (500ms) to avoid hammering MT5 on fast refresh.
    """
    global _tick_cache
    now = time.monotonic()
    cached = _tick_cache.get(symbol)
    if cached and (now - cached["ts"]) < _TICK_CACHE_TTL:
        return cached["tick"]
    try:
        import MetaTrader5 as mt5
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return None
        result = {
            "bid": tick.bid,
            "ask": tick.ask,
            "last": tick.last,
            "time": datetime.fromtimestamp(tick.time).isoformat(),
        }
        _tick_cache[symbol] = {"tick": result, "ts": now}
        return result
    except Exception:
        return None


def load_audit_log(limit: int = 300) -> list[dict]:
    """Load recent persistent MT5 audit entries from disk.

    Uses file-mtime caching: only re-reads if the file changed since last call.
    Reads from the tail of the file to avoid parsing the entire log.
    """
    global _audit_cache
    if not _AUDIT_FILE.exists():
        return []
    try:
        mtime = _AUDIT_FILE.stat().st_mtime
        if mtime == _audit_cache["mtime"] and limit <= _audit_cache["limit"]:
            return _audit_cache["data"][-limit:]

        # Read tail efficiently: read last ~64KB which covers ~300+ JSONL lines
        file_size = _AUDIT_FILE.stat().st_size
        chunk_size = min(file_size, max(limit * 512, 65536))
        rows: list[dict] = []
        with _AUDIT_FILE.open("rb") as fh:
            fh.seek(max(0, file_size - chunk_size))
            if fh.tell() > 0:
                fh.readline()  # skip partial first line
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except (json.JSONDecodeError, ValueError):
                    continue

        _audit_cache = {"data": rows, "mtime": mtime, "limit": max(limit, len(rows))}
        return rows[-limit:]
    except Exception:
        return []


def _prepare_trade_request(
    config: MT5Config,
    direction: str,
    entry_price: float,
    sl_price: float,
    tp_price: float,
    lot_size: float,
    comment: str,
    log_prefix: str,
) -> dict:
    supported, reason = mt5_runtime_supported()
    if not supported:
        return {"success": False, "message": reason}

    try:
        import MetaTrader5 as mt5
    except ImportError:
        return {"success": False, "message": "MetaTrader5 not installed"}

    symbol = config.symbol
    lot_size = min(lot_size, config.max_lot)
    lot_size = round(lot_size, 2)
    if lot_size < 0.01:
        return {"success": False, "message": f"Lot size too small: {lot_size}"}

    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        return {"success": False, "message": f"Symbol '{symbol}' not found in MT5"}
    if not symbol_info.visible:
        mt5.symbol_select(symbol, True)

    ok_policy, policy_msg = _check_trade_policy(config, symbol)
    if not ok_policy:
        trade_log.add({
            "status": log_prefix,
            "reason": policy_msg,
            "direction": direction,
            "symbol": symbol,
            "lot_size": lot_size,
            "signal_entry": entry_price,
        })
        return {"success": False, "message": policy_msg}

    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return {"success": False, "message": f"No tick data for {symbol}"}

    digits = symbol_info.digits
    point = symbol_info.point
    min_stop = symbol_info.trade_stops_level * point

    if direction == "LONG":
        order_type = mt5.ORDER_TYPE_BUY
        price = tick.ask
    else:
        order_type = mt5.ORDER_TYPE_SELL
        price = tick.bid

    if config.kill_switch:
        msg = "Kill-switch is ON. New trades are blocked."
        trade_log.add({
            "status": log_prefix,
            "reason": msg,
            "direction": direction,
            "symbol": symbol,
            "lot_size": lot_size,
            "signal_entry": entry_price,
        })
        return {"success": False, "message": msg}

    spread_price = abs(tick.ask - tick.bid)
    if config.max_spread_price > 0 and spread_price > config.max_spread_price:
        msg = (
            f"Spread too high: {spread_price:.2f} > {config.max_spread_price:.2f}. "
            "Trade blocked."
        )
        trade_log.add({
            "status": log_prefix,
            "reason": msg,
            "direction": direction,
            "symbol": symbol,
            "lot_size": lot_size,
            "signal_entry": entry_price,
        })
        return {"success": False, "message": msg}

    entry_drift_price = abs(price - entry_price)
    if config.max_entry_drift_price > 0 and entry_drift_price > config.max_entry_drift_price:
        msg = (
            f"Entry drift too large: {entry_drift_price:.2f} > {config.max_entry_drift_price:.2f}. "
            "Trade blocked."
        )
        trade_log.add({
            "status": log_prefix,
            "reason": msg,
            "direction": direction,
            "symbol": symbol,
            "lot_size": lot_size,
            "signal_entry": entry_price,
            "live_price": price,
        })
        return {"success": False, "message": msg}

    sl_dist = abs(entry_price - sl_price)
    tp_dist = abs(entry_price - tp_price)

    if min_stop > 0:
        sl_dist = max(sl_dist, min_stop + point)
        tp_dist = max(tp_dist, min_stop + point)

    # ── SL/TP distance guardrails ────────────────────────────────
    pip_size = point * 10  # 1 pip = 10 points (works for XAUUSD, forex 5-digit, JPY 3-digit)

    if sl_dist <= spread_price:
        msg = (
            f"SL distance ({sl_dist:.{digits}f}) is inside or equal to the spread "
            f"({spread_price:.{digits}f}). Trade blocked."
        )
        trade_log.add({
            "status": log_prefix, "reason": msg, "direction": direction,
            "symbol": symbol, "lot_size": lot_size, "signal_entry": entry_price,
        })
        return {"success": False, "message": msg}

    sl_pips = sl_dist / pip_size if pip_size > 0 else 0.0
    tp_pips = tp_dist / pip_size if pip_size > 0 else 0.0

    if config.min_stop_distance_pips > 0 and sl_pips < config.min_stop_distance_pips:
        msg = (
            f"SL too tight: {sl_pips:.1f} pips < minimum {config.min_stop_distance_pips:.1f} pips. "
            "Trade blocked."
        )
        trade_log.add({
            "status": log_prefix, "reason": msg, "direction": direction,
            "symbol": symbol, "lot_size": lot_size, "signal_entry": entry_price,
        })
        return {"success": False, "message": msg}

    if config.max_stop_distance_pips > 0 and sl_pips > config.max_stop_distance_pips:
        msg = (
            f"SL too wide: {sl_pips:.1f} pips > maximum {config.max_stop_distance_pips:.1f} pips. "
            "Trade blocked."
        )
        trade_log.add({
            "status": log_prefix, "reason": msg, "direction": direction,
            "symbol": symbol, "lot_size": lot_size, "signal_entry": entry_price,
        })
        return {"success": False, "message": msg}

    if config.min_rr_ratio > 0 and sl_dist > 0 and tp_dist < config.min_rr_ratio * sl_dist:
        actual_rr = round(tp_dist / sl_dist, 2)
        msg = (
            f"TP/SL ratio {actual_rr:.2f} < minimum {config.min_rr_ratio:.2f}. "
            "Trade blocked."
        )
        trade_log.add({
            "status": log_prefix, "reason": msg, "direction": direction,
            "symbol": symbol, "lot_size": lot_size, "signal_entry": entry_price,
        })
        return {"success": False, "message": msg}

    if direction == "LONG":
        live_sl = round(price - sl_dist, digits)
        live_tp = round(price + tp_dist, digits)
    else:
        live_sl = round(price + sl_dist, digits)
        live_tp = round(price - tp_dist, digits)

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lot_size,
        "type": order_type,
        "price": price,
        "sl": live_sl,
        "tp": live_tp,
        "deviation": config.deviation,
        "magic": config.magic,
        "comment": comment,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    return {
        "success": True,
        "message": "OK",
        "request": request,
        "symbol": symbol,
        "lot_size": lot_size,
        "price": price,
        "live_sl": live_sl,
        "live_tp": live_tp,
        "digits": digits,
        "min_stop": min_stop,
        "spread_price": spread_price,
    }


def _check_trade_policy(config: MT5Config, symbol: str) -> tuple[bool, str]:
    """Validate policy constraints before sending a new order.

    Uses a file-persisted daily fill counter so counts survive Streamlit
    reruns and process restarts.  Falls back to the audit log on date change.
    """
    global _daily_fill_count
    now_utc = datetime.now(timezone.utc)

    if config.enforce_session_window:
        start_h = max(0, min(23, int(config.session_start_utc)))
        end_h = max(0, min(23, int(config.session_end_utc)))
        h = now_utc.hour
        if start_h <= end_h:
            in_window = start_h <= h <= end_h
        else:
            in_window = h >= start_h or h <= end_h
        if not in_window:
            return False, (
                f"Session window block: UTC hour {h:02d} outside {start_h:02d}:00-{end_h:02d}:00"
            )

    if config.max_open_positions > 0:
        open_positions = get_open_positions(symbol)
        if len(open_positions) >= int(config.max_open_positions):
            return False, (
                f"Max open positions reached: {len(open_positions)}/{int(config.max_open_positions)}"
            )

    if config.max_trades_per_day > 0:
        today_str = now_utc.strftime("%Y-%m-%d")
        # Load persisted counter (survives Streamlit module reimports)
        if _daily_fill_count["date"] != today_str:
            _daily_fill_count = _load_daily_fills()
        # If still a different date, bootstrap from audit
        if _daily_fill_count["date"] != today_str:
            _daily_fill_count = {"date": today_str, "symbol_counts": {}}
            for row in load_audit_log(limit=500):
                if row.get("status") != "FILLED":
                    continue
                ts = row.get("timestamp", "")
                if ts.startswith(today_str):
                    s = row.get("symbol", "")
                    _daily_fill_count["symbol_counts"][s] = (
                        _daily_fill_count["symbol_counts"].get(s, 0) + 1
                    )
            _save_daily_fills()

        fills_today = _daily_fill_count["symbol_counts"].get(symbol, 0)
        if fills_today >= int(config.max_trades_per_day):
            return False, (
                f"Max trades/day reached for {symbol}: {fills_today}/{int(config.max_trades_per_day)}"
            )

    return True, "OK"


def _load_daily_fills() -> dict:
    """Load persisted daily fill counter from disk."""
    try:
        if _DAILY_FILLS_FILE.exists():
            raw = json.loads(_DAILY_FILLS_FILE.read_text(encoding="utf-8"))
            if isinstance(raw, dict) and "date" in raw and "symbol_counts" in raw:
                return raw
    except Exception:
        pass
    return {"date": "", "symbol_counts": {}}


def _save_daily_fills() -> None:
    """Persist the daily fill counter to disk (atomic write)."""
    try:
        tmp = _DAILY_FILLS_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(_daily_fill_count), encoding="utf-8")
        tmp.replace(_DAILY_FILLS_FILE)
    except Exception:
        pass


def _increment_daily_fill(symbol: str) -> None:
    """Increment the daily fill counter and persist to disk."""
    global _daily_fill_count
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if _daily_fill_count["date"] != today_str:
        _daily_fill_count = {"date": today_str, "symbol_counts": {}}
    _daily_fill_count["symbol_counts"][symbol] = (
        _daily_fill_count["symbol_counts"].get(symbol, 0) + 1
    )
    _save_daily_fills()
