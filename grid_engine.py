"""
Grid Trading Engine — AI-Directed Dynamic Grid Orders.

Analyzes market direction using ICT confluence + statistical regime,
computes grid price levels dynamically (ATR-based spacing), manages
grid state, and provides hooks for MT5 order placement.

AI Direction Logic:
  - Counts recent ICT bullish vs bearish signals → bias ratio
  - EMA(20) vs EMA(50) slope → trend confirmation
  - ATR ratio (current / rolling mean) → regime (trending vs ranging)
  - Session time weighting (London/NY preferred)

Grid Modes:
  - NEUTRAL  : buy levels below price + sell levels above (range grid)
  - BULLISH  : more buy levels below current price, ride upward
  - BEARISH  : more sell levels above current price, ride downward

Learning:
  - Every closed grid trade is appended to GridBrain (grid_brain.py)
  - Brain feeds back optimal_spacing_multiplier per symbol/regime
  - Brain feeds back direction_confidence adjustments
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).parent
GRID_STATE_FILE = BASE_DIR / "grid_state.json"
GRID_MAGIC = 202606          # MT5 magic number — distinct from ICT bot trades
GRID_AUDIT_FILE = BASE_DIR / "grid_audit_log.jsonl"

DirectionBias = Literal["BULLISH", "BEARISH", "NEUTRAL"]


# ───────────────────────────────────────────────────────────────────────────
# Data structures
# ───────────────────────────────────────────────────────────────────────────

@dataclass
class GridLevel:
    level_id: str            # e.g. "BUY_3" or "SELL_2"
    price: float             # target price for this level
    direction: str           # "BUY" or "SELL"
    lot: float               # position size for this level
    status: str = "PENDING"  # PENDING | OPEN | CLOSED | CANCELLED
    ticket: int | None = None
    entry_price: float = 0.0
    exit_price: float = 0.0
    profit_pips: float = 0.0
    profit_usd: float = 0.0
    opened_at: str = ""
    closed_at: str = ""
    sl_price: float = 0.0
    tp_price: float = 0.0


@dataclass
class MarketRegime:
    direction_bias: DirectionBias = "NEUTRAL"
    direction_confidence: float = 0.0   # 0-100
    regime: str = "RANGING"             # TRENDING | RANGING | VOLATILE
    atr: float = 0.0
    atr_ratio: float = 1.0              # current ATR / mean ATR
    ema_slope: float = 0.0              # EMA20 slope in price units
    signal_bull_count: int = 0
    signal_bear_count: int = 0
    recommended_spacing: float = 0.0   # ATR-derived price spacing
    session: str = "UNKNOWN"
    analysis_time: str = ""


@dataclass
class GridConfig:
    symbol: str = "XAUUSD"
    timeframe: str = "15m"
    base_lot: float = 0.01
    levels_buy: int = 4               # number of buy levels below price
    levels_sell: int = 4              # number of sell levels above price
    spacing_multiplier: float = 1.0   # spacing = ATR * multiplier
    tp_multiplier: float = 1.5        # TP = spacing * tp_multiplier
    sl_multiplier: float = 2.5        # SL = spacing * sl_multiplier (wide)
    max_open_levels: int = 6          # maximum simultaneous open grid orders
    ai_direction_enabled: bool = True
    ai_spacing_enabled: bool = True   # let brain tune spacing_multiplier
    lot_scale_with_direction: bool = True  # scale lots toward bias direction
    auto_profile_switch: bool = True
    profile_name: str = "Balanced"
    basket_take_profit_usd: float = 25.0
    basket_stop_loss_usd: float = -40.0
    basket_close_on_profit: bool = True
    basket_close_on_loss: bool = True
    basket_trailing_tp: bool = False
    basket_trailing_step_usd: float = 5.0
    session_pause_enabled: bool = False
    session_pause_list: str = "Asian"        # comma-separated sessions to pause
    max_daily_loss_usd: float = 100.0
    max_drawdown_pct: float = 8.0
    min_equity_usd: float = 0.0


@dataclass
class GridState:
    config: GridConfig = field(default_factory=GridConfig)
    active: bool = False
    regime: MarketRegime = field(default_factory=MarketRegime)
    levels: list[GridLevel] = field(default_factory=list)
    anchor_price: float = 0.0        # price when grid was built
    created_at: str = ""
    updated_at: str = ""
    total_profit_usd: float = 0.0
    total_closed: int = 0
    total_wins: int = 0
    total_losses: int = 0
    run_id: str = ""                  # unique session ID
    starting_balance: float = 0.0
    peak_equity: float = 0.0
    day_start_balance: float = 0.0
    day_start_date: str = ""
    daily_realized_pnl: float = 0.0
    risk_blocked: bool = False
    risk_reason: str = ""
    lockout_active: bool = False
    lockout_reason: str = ""
    lockout_time: str = ""
    basket_peak_pnl: float = 0.0


# ───────────────────────────────────────────────────────────────────────────
# State persistence
# ───────────────────────────────────────────────────────────────────────────

def load_grid_state() -> GridState:
    """Load active grid state from disk; returns default if missing/corrupt."""
    if not GRID_STATE_FILE.exists():
        return GridState()
    try:
        raw = json.loads(GRID_STATE_FILE.read_text(encoding="utf-8"))
        cfg = GridConfig(**raw.get("config", {}))
        reg = MarketRegime(**raw.get("regime", {}))
        levels = [GridLevel(**lv) for lv in raw.get("levels", [])]
        state = GridState(
            config=cfg,
            regime=reg,
            levels=levels,
            active=raw.get("active", False),
            anchor_price=raw.get("anchor_price", 0.0),
            created_at=raw.get("created_at", ""),
            updated_at=raw.get("updated_at", ""),
            total_profit_usd=raw.get("total_profit_usd", 0.0),
            total_closed=raw.get("total_closed", 0),
            total_wins=raw.get("total_wins", 0),
            total_losses=raw.get("total_losses", 0),
            run_id=raw.get("run_id", ""),
            starting_balance=raw.get("starting_balance", 0.0),
            peak_equity=raw.get("peak_equity", 0.0),
            day_start_balance=raw.get("day_start_balance", 0.0),
            day_start_date=raw.get("day_start_date", ""),
            daily_realized_pnl=raw.get("daily_realized_pnl", 0.0),
            risk_blocked=raw.get("risk_blocked", False),
            risk_reason=raw.get("risk_reason", ""),
            lockout_active=raw.get("lockout_active", False),
            lockout_reason=raw.get("lockout_reason", ""),
            lockout_time=raw.get("lockout_time", ""),
            basket_peak_pnl=raw.get("basket_peak_pnl", 0.0),
        )
        return state
    except Exception:
        return GridState()


def save_grid_state(state: GridState) -> None:
    """Persist grid state to disk."""
    state.updated_at = _now()
    raw = {
        "config": asdict(state.config),
        "regime": asdict(state.regime),
        "levels": [asdict(lv) for lv in state.levels],
        "active": state.active,
        "anchor_price": state.anchor_price,
        "created_at": state.created_at,
        "updated_at": state.updated_at,
        "total_profit_usd": state.total_profit_usd,
        "total_closed": state.total_closed,
        "total_wins": state.total_wins,
        "total_losses": state.total_losses,
        "run_id": state.run_id,
        "starting_balance": state.starting_balance,
        "peak_equity": state.peak_equity,
        "day_start_balance": state.day_start_balance,
        "day_start_date": state.day_start_date,
        "daily_realized_pnl": state.daily_realized_pnl,
        "risk_blocked": state.risk_blocked,
        "risk_reason": state.risk_reason,
        "lockout_active": state.lockout_active,
        "lockout_reason": state.lockout_reason,
        "lockout_time": state.lockout_time,
        "basket_peak_pnl": state.basket_peak_pnl,
    }
    GRID_STATE_FILE.write_text(json.dumps(raw, indent=2), encoding="utf-8")


def append_grid_audit(entry: dict) -> None:
    """Append a single grid trade event to the audit JSONL log."""
    try:
        with GRID_AUDIT_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass


def load_grid_audit(limit: int = 200) -> list[dict]:
    """Load the most recent N grid audit log entries."""
    if not GRID_AUDIT_FILE.exists():
        return []
    try:
        lines = GRID_AUDIT_FILE.read_text(encoding="utf-8").strip().splitlines()
        entries = []
        for ln in lines[-limit:]:
            try:
                entries.append(json.loads(ln))
            except Exception:
                pass
        return list(reversed(entries))
    except Exception:
        return []


# ───────────────────────────────────────────────────────────────────────────
# Market regime / AI direction analysis
# ───────────────────────────────────────────────────────────────────────────

def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    hl = df["High"] - df["Low"]
    hc = (df["High"] - df["Close"].shift(1)).abs()
    lc = (df["Low"] - df["Close"].shift(1)).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def _current_session(dt: datetime) -> str:
    h = dt.hour
    if 0 <= h < 6:
        return "Asian"
    if 7 <= h < 12:
        return "London"
    if 12 <= h < 17:
        return "NY"
    return "Overlap/Off"


def _session_weight(session: str) -> float:
    """Higher weight for high-liquidity sessions."""
    return {"London": 1.3, "NY": 1.2, "Asian": 0.85, "Overlap/Off": 0.9}.get(session, 1.0)


def is_session_paused(config: GridConfig) -> tuple[bool, str]:
    """Check if the current session should pause new grid fills."""
    if not config.session_pause_enabled:
        return False, ""
    now_utc = datetime.now(timezone.utc)
    session = _current_session(now_utc)
    paused_sessions = [s.strip() for s in config.session_pause_list.split(",") if s.strip()]
    if session in paused_sessions:
        return True, f"Session paused: {session} (UTC {now_utc.strftime('%H:%M')})"
    return False, ""


def analyze_market_direction(
    df: pd.DataFrame,
    spacing_multiplier: float = 1.0,
    ict_signals: pd.DataFrame | None = None,
    brain_multiplier: float | None = None,
    htf_df: pd.DataFrame | None = None,
) -> MarketRegime:
    """
    AI direction analysis for grid placement.

    Args:
        df:                OHLCV DataFrame (recent bars) — grid timeframe.
        spacing_multiplier: Base ATR multiplier for spacing.
        ict_signals:       Optional signal DataFrame from generate_signals().
        brain_multiplier:  Optional learned multiplier from GridBrain.
        htf_df:            Optional HIGHER timeframe OHLCV for structural bias.
                           When provided the directional bias is derived from
                           HTF EMA structure (stable) while ATR/spacing still
                           comes from the grid timeframe (precise).

    Returns:
        MarketRegime with direction bias, confidence, ATR, spacing.
    """
    if df.empty or len(df) < 30:
        return MarketRegime(analysis_time=_now())

    close = df["Close"]
    ema20 = _ema(close, 20)
    ema50 = _ema(close, 50)
    atr_series = _atr(df, 14)
    atr_mean = atr_series.rolling(50).mean()

    current_atr = float(atr_series.iloc[-1]) if not atr_series.empty else 0.0
    mean_atr = float(atr_mean.iloc[-1]) if not atr_mean.empty else current_atr
    atr_ratio = current_atr / mean_atr if mean_atr > 0 else 1.0

    # Regime classification (from grid timeframe — determines spacing/lot behaviour)
    if atr_ratio > 1.5:
        regime = "VOLATILE"
    elif abs(float(ema20.iloc[-1]) - float(ema50.iloc[-1])) > current_atr * 0.3:
        regime = "TRENDING"
    else:
        regime = "RANGING"

    # ── Directional bias — prefer HTF structure when available ──
    # HTF EMAs change slowly (1H/4H), giving a stable structural direction
    # that doesn't flip on every 5m candle.
    if htf_df is not None and len(htf_df) >= 50:
        htf_close = htf_df["Close"]
        htf_ema20 = _ema(htf_close, 20)
        htf_ema50 = _ema(htf_close, 50)
        htf_e20 = float(htf_ema20.iloc[-1])
        htf_e50 = float(htf_ema50.iloc[-1])
        htf_slope = float(htf_ema20.iloc[-1] - htf_ema20.iloc[-3]) if len(htf_ema20) >= 3 else 0.0

        ema_bull_pts = 0
        ema_bear_pts = 0
        # EMA cross: worth 3 points (HTF is strong signal)
        if htf_e20 > htf_e50:
            ema_bull_pts = 3
        elif htf_e20 < htf_e50:
            ema_bear_pts = 3
        # HTF slope: worth 2 points
        if htf_slope > 0:
            ema_bull_pts += 2
        elif htf_slope < 0:
            ema_bear_pts += 2

        ema_slope = htf_slope  # record HTF slope for diagnostics
    else:
        # No HTF available — fallback to grid-timeframe EMAs (original behaviour)
        ema_slope = float(ema20.iloc[-1] - ema20.iloc[-3]) if len(ema20) >= 3 else 0.0
        ema_bull_pts = 0
        ema_bear_pts = 0
        e20 = float(ema20.iloc[-1])
        e50 = float(ema50.iloc[-1])
        if e20 > e50:
            ema_bull_pts = 2
        elif e20 < e50:
            ema_bear_pts = 2
        if ema_slope > 0:
            ema_bull_pts += 1
        elif ema_slope < 0:
            ema_bear_pts += 1

    # ICT signal counting (last 20 signals)
    bull_count = 0
    bear_count = 0
    if ict_signals is not None and not ict_signals.empty:
        recent = ict_signals.tail(20)
        bull_count = int((recent["direction"] == "bullish").sum())
        bear_count = int((recent["direction"] == "bearish").sum())

    # Combine all evidence
    total_bull = ema_bull_pts + bull_count
    total_bear = ema_bear_pts + bear_count
    total_signals = total_bull + total_bear

    if total_signals == 0:
        direction_bias: DirectionBias = "NEUTRAL"
        raw_confidence = 0.0
    else:
        ratio = total_bull / total_signals
        if ratio > 0.60:
            direction_bias = "BULLISH"
            raw_confidence = (ratio - 0.5) * 200.0   # 0-100 scale
        elif ratio < 0.40:
            direction_bias = "BEARISH"
            raw_confidence = (0.5 - ratio) * 200.0
        else:
            direction_bias = "NEUTRAL"
            raw_confidence = 0.0

    raw_confidence = min(100.0, raw_confidence)

    # Session weighting
    now_utc = datetime.now(timezone.utc)
    session = _current_session(now_utc)
    sw = _session_weight(session)
    direction_confidence = min(100.0, raw_confidence * sw)

    # Spacing: ATR * multiplier (use brain-learned multiplier if available)
    effective_multiplier = brain_multiplier if brain_multiplier is not None else spacing_multiplier
    recommended_spacing = current_atr * effective_multiplier

    return MarketRegime(
        direction_bias=direction_bias,
        direction_confidence=round(direction_confidence, 1),
        regime=regime,
        atr=round(current_atr, 5),
        atr_ratio=round(atr_ratio, 3),
        ema_slope=round(ema_slope, 5),
        signal_bull_count=bull_count,
        signal_bear_count=bear_count,
        recommended_spacing=round(recommended_spacing, 5),
        session=session,
        analysis_time=_now(),
    )


# ───────────────────────────────────────────────────────────────────────────
# Grid level computation
# ───────────────────────────────────────────────────────────────────────────

def build_grid_levels(
    current_price: float,
    regime: MarketRegime,
    config: GridConfig,
) -> list[GridLevel]:
    """
    Compute grid BUY/SELL levels around current price.

    Directional mode:
      - BULLISH bias → extra buy levels below, fewer sell levels above
      - BEARISH bias → extra sell levels above, fewer buy levels below
      - NEUTRAL → symmetric grid

    Args:
        current_price: Live market ask/bid mid price.
        regime:        Output from analyze_market_direction().
        config:        GridConfig with lot, levels, multipliers.

    Returns:
        List of GridLevel objects (sorted by price).
    """
    spacing = regime.recommended_spacing
    if spacing <= 0:
        spacing = current_price * 0.001   # fallback: 0.1% spacing

    levels: list[GridLevel] = []
    bias = regime.direction_bias
    confidence = regime.direction_confidence
    regime_name = regime.regime

    # Dynamic regime behavior:
    # - RANGING (sideways): tighter spacing, denser symmetric grid
    # - TRENDING: wider spacing and stronger directional skew
    # - VOLATILE: widest spacing, fewer levels, reduced lot pressure
    lot_regime_factor = 1.0
    tp_mult = config.tp_multiplier
    sl_mult = config.sl_multiplier

    buy_count = config.levels_buy
    sell_count = config.levels_sell
    if regime_name == "RANGING":
        spacing *= 0.85
        tp_mult *= 0.90
        sl_mult *= 0.90
        buy_count += 1
        sell_count += 1
        lot_regime_factor = 0.95
    elif regime_name == "TRENDING":
        spacing *= 1.15
        tp_mult *= 1.15
        sl_mult *= 1.10
        if bias == "BULLISH":
            buy_count += 2
            sell_count = max(1, sell_count - 1)
        elif bias == "BEARISH":
            sell_count += 2
            buy_count = max(1, buy_count - 1)
    elif regime_name == "VOLATILE":
        spacing *= 1.40
        tp_mult *= 1.25
        sl_mult *= 1.30
        buy_count = max(1, buy_count - 1)
        sell_count = max(1, sell_count - 1)
        lot_regime_factor = 0.80

    # Additional AI directional skew on top of regime defaults
    if config.ai_direction_enabled and bias != "NEUTRAL":
        skew_strength = {
            "RANGING": 0.5,
            "TRENDING": 1.0,
            "VOLATILE": 0.75,
        }.get(regime_name, 1.0)
        extra = math.floor((confidence / 25) * skew_strength)
        if bias == "BULLISH":
            buy_count += extra
            sell_count = max(1, sell_count - extra)
        elif bias == "BEARISH":
            sell_count += extra
            buy_count = max(1, buy_count - extra)

    tp_dist = spacing * tp_mult
    sl_dist = spacing * sl_mult

    # BUY levels below current price
    for i in range(1, buy_count + 1):
        level_price = round(current_price - spacing * i, 5)
        lot = _scale_lot(config.base_lot, i, bias, "BUY", config.lot_scale_with_direction)
        lot = _apply_regime_lot_factor(lot, lot_regime_factor)
        levels.append(GridLevel(
            level_id=f"BUY_{i}",
            price=level_price,
            direction="BUY",
            lot=lot,
            sl_price=round(level_price - sl_dist, 5),
            tp_price=round(level_price + tp_dist, 5),
        ))

    # SELL levels above current price
    for i in range(1, sell_count + 1):
        level_price = round(current_price + spacing * i, 5)
        lot = _scale_lot(config.base_lot, i, bias, "SELL", config.lot_scale_with_direction)
        lot = _apply_regime_lot_factor(lot, lot_regime_factor)
        levels.append(GridLevel(
            level_id=f"SELL_{i}",
            price=level_price,
            direction="SELL",
            lot=lot,
            sl_price=round(level_price + sl_dist, 5),
            tp_price=round(level_price - tp_dist, 5),
        ))

    levels.sort(key=lambda lv: lv.price)
    return levels


def _scale_lot(base_lot: float, level_index: int, bias: DirectionBias,
               direction: str, enabled: bool) -> float:
    """
    Scale lot slightly toward the AI-biased direction.
    Furthest levels from bias get reduced lots (capital efficiency).
    """
    if not enabled or bias == "NEUTRAL":
        return round(base_lot, 2)

    is_bias_dir = (bias == "BULLISH" and direction == "BUY") or \
                  (bias == "BEARISH" and direction == "SELL")

    if is_bias_dir:
        # First level: full lot, further levels: slight increase (pyramid)
        factor = 1.0 + (level_index - 1) * 0.1
    else:
        # Counter-bias direction: reduce lots slightly
        factor = max(0.5, 1.0 - (level_index - 1) * 0.1)

    return round(max(0.01, base_lot * factor), 2)


def _apply_regime_lot_factor(lot: float, lot_regime_factor: float) -> float:
    """Apply regime-wide lot pressure scaling while preserving micro-lot floor."""
    return round(max(0.01, lot * lot_regime_factor), 2)


# ───────────────────────────────────────────────────────────────────────────
# Grid activation / deactivation
# ───────────────────────────────────────────────────────────────────────────

def activate_grid(
    current_price: float,
    df: pd.DataFrame,
    config: GridConfig,
    ict_signals: pd.DataFrame | None = None,
    brain_multiplier: float | None = None,
    starting_balance: float = 0.0,
    htf_df: pd.DataFrame | None = None,
) -> GridState:
    """
    Build and activate a new grid around current_price.

    Returns new GridState (not yet saved — caller must call save_grid_state()).
    """
    import uuid
    regime = analyze_market_direction(
        df, config.spacing_multiplier, ict_signals, brain_multiplier,
        htf_df=htf_df,
    )
    levels = build_grid_levels(current_price, regime, config)

    state = GridState(
        config=config,
        active=True,
        regime=regime,
        levels=levels,
        anchor_price=current_price,
        created_at=_now(),
        updated_at=_now(),
        run_id=str(uuid.uuid4())[:8],
        starting_balance=starting_balance,
        peak_equity=starting_balance,
        day_start_balance=starting_balance,
        day_start_date=_today_utc(),
        daily_realized_pnl=0.0,
        risk_blocked=False,
        risk_reason="",
    )
    return state


def deactivate_grid(state: GridState) -> GridState:
    """Mark grid inactive, cancel all PENDING levels."""
    state.active = False
    for lv in state.levels:
        if lv.status == "PENDING":
            lv.status = "CANCELLED"
    return state


# ───────────────────────────────────────────────────────────────────────────
# Grid level monitoring / update
# ───────────────────────────────────────────────────────────────────────────

def check_levels_hit(
    state: GridState,
    current_price: float,
    price_tolerance_pct: float = 0.05,
) -> list[GridLevel]:
    """
    Return PENDING levels that current_price has reached (within tolerance).

    Args:
        state:               Active GridState.
        current_price:       Live bid/ask price.
        price_tolerance_pct: % of spacing to consider "hit" (default 5%).

    Returns:
        List of GridLevel objects that should be activated/executed.
    """
    if not state.active:
        return []

    spacing = state.regime.recommended_spacing
    tolerance = spacing * price_tolerance_pct

    triggered = []
    for lv in state.levels:
        if lv.status != "PENDING":
            continue
        if abs(current_price - lv.price) <= tolerance:
            triggered.append(lv)

    return triggered


def mark_level_open(state: GridState, level_id: str,
                    ticket: int, entry_price: float) -> None:
    """Update a level as OPEN after MT5 fills it."""
    for lv in state.levels:
        if lv.level_id == level_id:
            lv.status = "OPEN"
            lv.ticket = ticket
            lv.entry_price = entry_price
            lv.opened_at = _now()
            break


def mark_level_closed(state: GridState, level_id: str,
                      exit_price: float, profit_usd: float) -> None:
    """Update a level as CLOSED and update state totals."""
    for lv in state.levels:
        if lv.level_id == level_id:
            lv.status = "CLOSED"
            lv.exit_price = exit_price
            lv.profit_usd = profit_usd
            if lv.entry_price > 0:
                if lv.direction == "BUY":
                    lv.profit_pips = round((exit_price - lv.entry_price) * 10, 1)
                else:
                    lv.profit_pips = round((lv.entry_price - exit_price) * 10, 1)
            lv.closed_at = _now()

            state.total_closed += 1
            state.total_profit_usd += profit_usd
            if profit_usd >= 0:
                state.total_wins += 1
            else:
                state.total_losses += 1

            # Audit log entry
            append_grid_audit({
                "event": "LEVEL_CLOSED",
                "run_id": state.run_id,
                "level_id": level_id,
                "symbol": state.config.symbol,
                "direction": lv.direction,
                "entry_price": lv.entry_price,
                "exit_price": exit_price,
                "profit_usd": profit_usd,
                "profit_pips": lv.profit_pips,
                "spacing_used": state.regime.recommended_spacing,
                "regime": state.regime.regime,
                "bias": state.regime.direction_bias,
                "bias_confidence": state.regime.direction_confidence,
                "lot": lv.lot,
                "timeframe": state.config.timeframe,
                "tp_multiplier": state.config.tp_multiplier,
                "sl_multiplier": state.config.sl_multiplier,
                "max_open_levels": state.config.max_open_levels,
                "levels_buy": state.config.levels_buy,
                "levels_sell": state.config.levels_sell,
                "profile_name": state.config.profile_name,
                "timestamp": _now(),
            })
            break


def count_open_levels(state: GridState) -> int:
    return sum(1 for lv in state.levels if lv.status == "OPEN")


def get_open_levels(state: GridState) -> list[GridLevel]:
    return [lv for lv in state.levels if lv.status == "OPEN"]


def get_pending_levels(state: GridState) -> list[GridLevel]:
    return [lv for lv in state.levels if lv.status == "PENDING"]


def get_closed_levels(state: GridState) -> list[GridLevel]:
    return [lv for lv in state.levels if lv.status == "CLOSED"]


def apply_regime_profile(config: GridConfig, regime: str) -> GridConfig:
    """Return a config copy with regime-aware defaults applied."""
    if not config.auto_profile_switch:
        return config

    profiles = {
        "RANGING": {
            "spacing_multiplier": 0.9,
            "tp_multiplier": 1.4,
            "sl_multiplier": 2.3,
            "max_open_levels": max(4, config.max_open_levels),
            "profile_name": "Sideways",
        },
        "TRENDING": {
            "spacing_multiplier": 1.25,
            "tp_multiplier": 1.8,
            "sl_multiplier": 3.0,
            "max_open_levels": min(config.max_open_levels, 4),
            "profile_name": "Trend",
        },
        "VOLATILE": {
            "spacing_multiplier": 1.5,
            "tp_multiplier": 2.0,
            "sl_multiplier": 3.4,
            "max_open_levels": min(config.max_open_levels, 3),
            "profile_name": "Volatility",
        },
    }
    p = profiles.get(regime, {})
    if not p:
        return config

    return replace(
        config,
        spacing_multiplier=float(p["spacing_multiplier"]),
        tp_multiplier=float(p["tp_multiplier"]),
        sl_multiplier=float(p["sl_multiplier"]),
        max_open_levels=int(p["max_open_levels"]),
        profile_name=str(p["profile_name"]),
    )


def apply_account_preset(config: GridConfig, preset_name: str) -> GridConfig:
    """Return a config copy tuned for common account-size safety tiers."""
    presets = {
        "2k Safe": {
            "base_lot": 0.01,
            "max_open_levels": 3,
            "basket_take_profit_usd": 10.0,
            "basket_stop_loss_usd": -20.0,
            "max_daily_loss_usd": 40.0,
            "max_drawdown_pct": 4.0,
        },
        "5k Safe": {
            "base_lot": 0.01,
            "max_open_levels": 4,
            "basket_take_profit_usd": 20.0,
            "basket_stop_loss_usd": -40.0,
            "max_daily_loss_usd": 90.0,
            "max_drawdown_pct": 6.0,
        },
        "10k Safe": {
            "base_lot": 0.02,
            "max_open_levels": 5,
            "basket_take_profit_usd": 35.0,
            "basket_stop_loss_usd": -70.0,
            "max_daily_loss_usd": 160.0,
            "max_drawdown_pct": 8.0,
        },
    }
    p = presets.get(preset_name)
    if not p:
        return config

    return replace(
        config,
        base_lot=float(p["base_lot"]),
        max_open_levels=int(p["max_open_levels"]),
        basket_take_profit_usd=float(p["basket_take_profit_usd"]),
        basket_stop_loss_usd=float(p["basket_stop_loss_usd"]),
        max_daily_loss_usd=float(p["max_daily_loss_usd"]),
        max_drawdown_pct=float(p["max_drawdown_pct"]),
        profile_name=f"{config.profile_name} | {preset_name}",
    )


def update_equity_tracking(state: GridState, balance: float, equity: float) -> dict:
    """Update peak/day metrics and return live risk metrics."""
    today = _today_utc()
    if not state.day_start_date:
        state.day_start_date = today
        state.day_start_balance = balance

    if state.day_start_date != today:
        state.day_start_date = today
        state.day_start_balance = balance
        state.daily_realized_pnl = 0.0

    if state.starting_balance <= 0:
        state.starting_balance = balance
    if state.peak_equity <= 0:
        state.peak_equity = equity

    state.peak_equity = max(state.peak_equity, equity)

    dd_peak_pct = 0.0
    if state.peak_equity > 0:
        dd_peak_pct = max(0.0, (state.peak_equity - equity) / state.peak_equity * 100.0)

    daily_loss = max(0.0, state.day_start_balance - balance)
    floating_pnl = equity - balance
    return {
        "daily_loss_usd": round(daily_loss, 2),
        "drawdown_peak_pct": round(dd_peak_pct, 3),
        "equity": round(equity, 2),
        "balance": round(balance, 2),
        "floating_pnl": round(floating_pnl, 2),
    }


def evaluate_risk_guards(state: GridState, balance: float, equity: float) -> tuple[bool, str, dict]:
    """Return (blocked, reason, metrics) based on configured hard risk limits."""
    metrics = update_equity_tracking(state, balance, equity)
    cfg = state.config

    if cfg.min_equity_usd > 0 and equity <= cfg.min_equity_usd:
        reason = f"Equity {equity:.2f} <= min_equity_usd {cfg.min_equity_usd:.2f}"
        state.risk_blocked = True
        state.risk_reason = reason
        return True, reason, metrics

    if cfg.max_daily_loss_usd > 0 and metrics["daily_loss_usd"] >= cfg.max_daily_loss_usd:
        reason = (
            f"Daily loss {metrics['daily_loss_usd']:.2f} >= "
            f"max_daily_loss_usd {cfg.max_daily_loss_usd:.2f}"
        )
        state.risk_blocked = True
        state.risk_reason = reason
        return True, reason, metrics

    if cfg.max_drawdown_pct > 0 and metrics["drawdown_peak_pct"] >= cfg.max_drawdown_pct:
        reason = (
            f"Drawdown {metrics['drawdown_peak_pct']:.2f}% >= "
            f"max_drawdown_pct {cfg.max_drawdown_pct:.2f}%"
        )
        state.risk_blocked = True
        state.risk_reason = reason
        return True, reason, metrics

    state.risk_blocked = False
    state.risk_reason = ""
    return False, "", metrics


def basket_floating_pnl_usd(state: GridState, current_price: float) -> float:
    """Estimate floating basket PnL from OPEN levels and current price."""
    pnl = 0.0
    for lv in get_open_levels(state):
        if lv.entry_price <= 0:
            continue
        if lv.direction == "BUY":
            pnl += (current_price - lv.entry_price) * lv.lot * 100.0
        else:
            pnl += (lv.entry_price - current_price) * lv.lot * 100.0
    return round(pnl, 2)


def should_close_basket(state: GridState, basket_pnl_usd: float) -> tuple[bool, str]:
    """Determine whether basket-level TP/SL should close all open levels.

    Trailing TP: once basket PnL exceeds TP, the basket stays open while PnL
    keeps rising.  A trailing stop is placed at (peak_pnl - trailing_step).
    If PnL drops below that trailing stop, the basket closes with profit.
    """
    cfg = state.config

    if cfg.basket_close_on_profit and basket_pnl_usd >= cfg.basket_take_profit_usd:
        if cfg.basket_trailing_tp:
            # Update peak
            if basket_pnl_usd > state.basket_peak_pnl:
                state.basket_peak_pnl = basket_pnl_usd
            trailing_floor = state.basket_peak_pnl - cfg.basket_trailing_step_usd
            if basket_pnl_usd <= trailing_floor and state.basket_peak_pnl > cfg.basket_take_profit_usd:
                return True, (
                    f"Trailing TP closed (PnL ${basket_pnl_usd:.2f} fell below "
                    f"trail floor ${trailing_floor:.2f}, peak ${state.basket_peak_pnl:.2f})"
                )
            # Still rising or within step — keep open
            return False, ""
        return True, f"Basket TP reached ({basket_pnl_usd:.2f} >= {cfg.basket_take_profit_usd:.2f})"

    # Below TP — reset peak tracking so next TP entry starts fresh
    if basket_pnl_usd < cfg.basket_take_profit_usd:
        state.basket_peak_pnl = 0.0

    if cfg.basket_close_on_loss and basket_pnl_usd <= cfg.basket_stop_loss_usd:
        return True, f"Basket SL reached ({basket_pnl_usd:.2f} <= {cfg.basket_stop_loss_usd:.2f})"
    return False, ""


# ───────────────────────────────────────────────────────────────────────────
# Grid summary for display
# ───────────────────────────────────────────────────────────────────────────

def grid_levels_dataframe(state: GridState) -> pd.DataFrame:
    """Return a DataFrame of all grid levels for Streamlit display."""
    if not state.levels:
        return pd.DataFrame()

    rows = []
    for lv in state.levels:
        rows.append({
            "Level": lv.level_id,
            "Direction": lv.direction,
            "Price": lv.price,
            "Lot": lv.lot,
            "SL": lv.sl_price,
            "TP": lv.tp_price,
            "Status": lv.status,
            "Entry": lv.entry_price if lv.entry_price else "-",
            "P&L ($)": round(lv.profit_usd, 2) if lv.profit_usd else "-",
            "Opened": lv.opened_at[:16] if lv.opened_at else "-",
        })
    df = pd.DataFrame(rows)
    df = df.sort_values("Price", ascending=False).reset_index(drop=True)
    return df


def grid_summary(state: GridState) -> dict:
    """Quick stats dict for the dashboard metrics strip."""
    win_rate = 0.0
    if state.total_closed > 0:
        win_rate = round(state.total_wins / state.total_closed * 100, 1)
    return {
        "active": state.active,
        "bias": state.regime.direction_bias,
        "confidence": state.regime.direction_confidence,
        "regime": state.regime.regime,
        "atr": state.regime.atr,
        "spacing": state.regime.recommended_spacing,
        "session": state.regime.session,
        "open_levels": count_open_levels(state),
        "pending_levels": len(get_pending_levels(state)),
        "total_closed": state.total_closed,
        "total_wins": state.total_wins,
        "total_losses": state.total_losses,
        "win_rate": win_rate,
        "total_profit_usd": round(state.total_profit_usd, 2),
        "anchor_price": state.anchor_price,
        "run_id": state.run_id,
        "created_at": state.created_at,
        "profile_name": state.config.profile_name,
        "risk_blocked": state.risk_blocked,
        "risk_reason": state.risk_reason,
        "max_daily_loss_usd": state.config.max_daily_loss_usd,
        "max_drawdown_pct": state.config.max_drawdown_pct,
    }


# ───────────────────────────────────────────────────────────────────────────
# MT5 execution helpers (thin wrappers — keep MT5 import optional)
# ───────────────────────────────────────────────────────────────────────────

def place_grid_order_mt5(
    level: GridLevel,
    symbol: str,
    config_magic: int = GRID_MAGIC,
    deviation: int = 20,
    max_retries: int = 2,
) -> dict:
    """
    Place a grid market order via MT5 with retry on transient failures.

    Returns dict with keys: success, ticket, message, price, exec_ms.
    """
    import time as _time
    _t0 = _time.perf_counter()
    for attempt in range(1, max_retries + 1):
        try:
            import MetaTrader5 as mt5
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                if attempt < max_retries:
                    continue
                return {"success": False, "ticket": None, "message": "No tick data",
                        "price": 0.0, "exec_ms": round((_time.perf_counter() - _t0) * 1000, 1)}

            if level.direction == "BUY":
                order_type = mt5.ORDER_TYPE_BUY
                price = tick.ask
            else:
                order_type = mt5.ORDER_TYPE_SELL
                price = tick.bid

            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": level.lot,
                "type": order_type,
                "price": price,
                "sl": level.sl_price,
                "tp": level.tp_price,
                "deviation": deviation,
                "magic": config_magic,
                "comment": f"Grid {level.level_id}",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }

            result = mt5.order_send(request)
            exec_ms = round((_time.perf_counter() - _t0) * 1000, 1)
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                return {
                    "success": True,
                    "ticket": result.order,
                    "message": "Filled",
                    "price": result.price,
                    "exec_ms": exec_ms,
                }
            # Transient retcodes worth retrying
            if result and result.retcode in (
                mt5.TRADE_RETCODE_REQUOTE,
                mt5.TRADE_RETCODE_PRICE_OFF,
                mt5.TRADE_RETCODE_CONNECTION,
            ) and attempt < max_retries:
                continue
            msg = result.comment if result else "No response"
            return {"success": False, "ticket": None, "message": msg,
                    "price": 0.0, "exec_ms": exec_ms}

        except ImportError:
            return {"success": False, "ticket": None,
                    "message": "MetaTrader5 not installed", "price": 0.0, "exec_ms": 0.0}
        except Exception as exc:
            if attempt < max_retries:
                continue
            exec_ms = round((_time.perf_counter() - _t0) * 1000, 1)
            return {"success": False, "ticket": None, "message": str(exc),
                    "price": 0.0, "exec_ms": exec_ms}

    exec_ms = round((_time.perf_counter() - _t0) * 1000, 1)
    return {"success": False, "ticket": None, "message": "Max retries exhausted",
            "price": 0.0, "exec_ms": exec_ms}


def close_grid_position_mt5(ticket: int, symbol: str,
                             lot: float, direction: str,
                             deviation: int = 20,
                             max_retries: int = 2) -> dict:
    """Close an open grid position by ticket with retry on transient errors."""
    import time as _time
    _t0 = _time.perf_counter()
    try:
        import MetaTrader5 as mt5
        _TRANSIENT = {mt5.TRADE_RETCODE_REQUOTE, mt5.TRADE_RETCODE_PRICE_OFF,
                      mt5.TRADE_RETCODE_CONNECTION}

        for attempt in range(1, max_retries + 2):  # 1..max_retries+1
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                if attempt <= max_retries:
                    _time.sleep(0.05)
                    continue
                exec_ms = round((_time.perf_counter() - _t0) * 1000, 1)
                return {"success": False, "message": "No tick",
                        "price": 0.0, "exec_ms": exec_ms}

            if direction == "BUY":
                close_type = mt5.ORDER_TYPE_SELL
                price = tick.bid
            else:
                close_type = mt5.ORDER_TYPE_BUY
                price = tick.ask

            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": lot,
                "type": close_type,
                "position": ticket,
                "price": price,
                "deviation": deviation,
                "magic": GRID_MAGIC,
                "comment": "Grid close",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            result = mt5.order_send(request)
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                exec_ms = round((_time.perf_counter() - _t0) * 1000, 1)
                return {"success": True, "message": "Closed",
                        "price": result.price, "exec_ms": exec_ms}
            # Retry on transient failures
            if result and result.retcode in _TRANSIENT and attempt <= max_retries:
                _time.sleep(0.05)
                continue
            msg = result.comment if result else "No response"
            exec_ms = round((_time.perf_counter() - _t0) * 1000, 1)
            return {"success": False, "message": msg,
                    "price": 0.0, "exec_ms": exec_ms}

        exec_ms = round((_time.perf_counter() - _t0) * 1000, 1)
        return {"success": False, "message": "Max retries exhausted",
                "price": 0.0, "exec_ms": exec_ms}
    except ImportError:
        exec_ms = round((_time.perf_counter() - _t0) * 1000, 1)
        return {"success": False, "message": "MetaTrader5 not installed",
                "price": 0.0, "exec_ms": exec_ms}
    except Exception as exc:
        exec_ms = round((_time.perf_counter() - _t0) * 1000, 1)
        return {"success": False, "message": str(exc),
                "price": 0.0, "exec_ms": exec_ms}


# ───────────────────────────────────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")
