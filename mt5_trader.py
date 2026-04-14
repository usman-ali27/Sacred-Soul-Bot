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
from base64 import b64decode, b64encode
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Credential persistence ───────────────────────────────────────
_CRED_FILE = Path(__file__).parent / ".mt5_credentials.json"
_AUDIT_FILE = Path(__file__).parent / "mt5_audit_log.jsonl"


def save_credentials(login: int, password: str, server: str,
                     symbol: str = "XAUUSD", max_lot: float = 0.10,
                     max_spread_price: float = 0.60,
                     max_entry_drift_price: float = 2.00,
                     max_trades_per_day: int = 8,
                     max_open_positions: int = 2,
                     enforce_session_window: bool = False,
                     session_start_utc: int = 0,
                     session_end_utc: int = 23):
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


def connect_mt5(config: MT5Config) -> tuple[bool, str]:
    """Initialize and login to MT5 terminal.

    Returns (success, message).
    """
    try:
        import MetaTrader5 as mt5
    except ImportError:
        return False, "MetaTrader5 package not installed. Run: pip install MetaTrader5"

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
    try:
        import MetaTrader5 as mt5
        mt5.shutdown()
    except Exception:
        pass


def get_account_info() -> dict | None:
    """Return current MT5 account info as a dict."""
    try:
        import MetaTrader5 as mt5
        info = mt5.account_info()
        if info is None:
            return None
        return {
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
    try:
        import MetaTrader5 as mt5
    except ImportError:
        return TradeResult(False, message="MetaTrader5 not installed")

    symbol = config.symbol
    lot_size = min(lot_size, config.max_lot)
    lot_size = round(lot_size, 2)
    if lot_size < 0.01:
        return TradeResult(False, message=f"Lot size too small: {lot_size}")

    # Validate symbol
    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        return TradeResult(False, message=f"Symbol '{symbol}' not found in MT5")
    if not symbol_info.visible:
        mt5.symbol_select(symbol, True)

    # Policy checks before market execution.
    ok_policy, policy_msg = _check_trade_policy(config, symbol)
    if not ok_policy:
        trade_log.add({
            "status": "BLOCKED",
            "reason": policy_msg,
            "direction": direction,
            "symbol": symbol,
            "lot_size": lot_size,
            "signal_entry": entry_price,
        })
        return TradeResult(False, message=policy_msg)

    # Get current price
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return TradeResult(False, message=f"No tick data for {symbol}")

    digits = symbol_info.digits
    point = symbol_info.point
    min_stop = symbol_info.trade_stops_level * point  # minimum SL/TP distance

    if direction == "LONG":
        order_type = mt5.ORDER_TYPE_BUY
        price = tick.ask
    else:
        order_type = mt5.ORDER_TYPE_SELL
        price = tick.bid

    if config.kill_switch:
        msg = "Kill-switch is ON. New trades are blocked."
        trade_log.add({
            "status": "BLOCKED",
            "reason": msg,
            "direction": direction,
            "symbol": symbol,
            "lot_size": lot_size,
            "signal_entry": entry_price,
        })
        return TradeResult(False, message=msg)

    spread_price = abs(tick.ask - tick.bid)
    if config.max_spread_price > 0 and spread_price > config.max_spread_price:
        msg = (
            f"Spread too high: {spread_price:.2f} > {config.max_spread_price:.2f}. "
            "Trade blocked."
        )
        trade_log.add({
            "status": "BLOCKED",
            "reason": msg,
            "direction": direction,
            "symbol": symbol,
            "lot_size": lot_size,
            "signal_entry": entry_price,
        })
        return TradeResult(False, message=msg)

    entry_drift_price = abs(price - entry_price)
    if config.max_entry_drift_price > 0 and entry_drift_price > config.max_entry_drift_price:
        msg = (
            f"Entry drift too large: {entry_drift_price:.2f} > {config.max_entry_drift_price:.2f}. "
            "Trade blocked."
        )
        trade_log.add({
            "status": "BLOCKED",
            "reason": msg,
            "direction": direction,
            "symbol": symbol,
            "lot_size": lot_size,
            "signal_entry": entry_price,
            "live_price": price,
        })
        return TradeResult(False, message=msg)

    # ── Recalculate SL/TP as offsets from live price ─────────────
    # The signal's entry/sl/tp are historical.  Preserve the *distance*
    # but anchor it to the current market price so MT5 accepts them.
    sl_dist = abs(entry_price - sl_price)
    tp_dist = abs(entry_price - tp_price)

    # Enforce minimum stop distance
    if min_stop > 0:
        sl_dist = max(sl_dist, min_stop + point)
        tp_dist = max(tp_dist, min_stop + point)

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

    result = mt5.order_send(request)
    if result is None:
        trade_log.add({
            "status": "FAILED",
            "reason": f"order_send returned None: {mt5.last_error()}",
            "direction": direction,
            "symbol": symbol,
            "lot_size": lot_size,
            "signal_entry": entry_price,
            "live_price": price,
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
    })

    return trade_result


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
    """Return current bid/ask/last for *symbol*, or None on failure."""
    try:
        import MetaTrader5 as mt5
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return None
        return {
            "bid": tick.bid,
            "ask": tick.ask,
            "last": tick.last,
            "time": datetime.fromtimestamp(tick.time).isoformat(),
        }
    except Exception:
        return None


def load_audit_log(limit: int = 300) -> list[dict]:
    """Load recent persistent MT5 audit entries from disk."""
    if not _AUDIT_FILE.exists():
        return []
    rows: list[dict] = []
    try:
        with _AUDIT_FILE.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except Exception:
        return []
    return rows[-limit:]


def _check_trade_policy(config: MT5Config, symbol: str) -> tuple[bool, str]:
    """Validate policy constraints before sending a new order."""
    now_utc = datetime.utcnow()

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
        today = datetime.now().date()
        fills_today = 0
        for row in load_audit_log(limit=5000):
            if row.get("status") != "FILLED":
                continue
            if row.get("symbol") != symbol:
                continue
            ts = row.get("timestamp")
            if not ts:
                continue
            try:
                dt = datetime.fromisoformat(ts)
            except Exception:
                continue
            if dt.date() == today:
                fills_today += 1
        if fills_today >= int(config.max_trades_per_day):
            return False, (
                f"Max trades/day reached for {symbol}: {fills_today}/{int(config.max_trades_per_day)}"
            )

    return True, "OK"
