# ─────────────────────────────────────────────────────────────
# AI Context Filter — blocks grid fills in risky conditions
# ─────────────────────────────────────────────────────────────
def ai_context_filter(gs, grid_df, htf_df, audit_log):
    """
    Returns (blocked: bool, reason: str) if grid should be paused due to context:
      - High-impact news event imminent (stub: always False, add API integration)
      - Extreme volatility (ATR spike > 2.5× mean)
      - Low-liquidity session (Asian late, weekends)
      - Recent losing streak (3+ consecutive losses in audit)
    """
    # 1. News event (stub)
    # TODO: Integrate with ForexFactory/News API
    news_block = False
    news_reason = "High-impact news event imminent"

    # 2. Volatility spike
    if grid_df is not None and len(grid_df) > 50:
        from grid_engine import _atr
        atr = _atr(grid_df, 14)
        mean_atr = atr.rolling(50).mean()
        if not atr.empty and not mean_atr.empty:
            if atr.iloc[-1] > mean_atr.iloc[-1] * 2.5:
                return True, "Paused: Extreme volatility spike (ATR > 2.5× mean)"

    # 3. Low-liquidity session
    now_utc = datetime.now(timezone.utc)
    hour = now_utc.hour
    weekday = now_utc.weekday()
    if weekday >= 5:
        return True, "Paused: Weekend (no liquidity)"
    if hour < 2 or hour > 21:
        return True, "Paused: Off-hours (low liquidity)"

    # 4. Losing streak
    if audit_log is not None and len(audit_log) > 5:
        last5 = [row for row in audit_log[-5:] if row.get("status") == "CLOSED"]
        losses = 0
        for row in reversed(last5):
            if row.get("pnl", 0) < 0:
                losses += 1
            else:
                break
        if losses >= 3:
            return True, f"Paused: {losses} consecutive losses (AI risk guard)"

    # 5. News event (stub)
    if news_block:
        return True, news_reason

    return False, ""
"""
Sacred Soul — XAUUSD Focused Dashboard

Features:
  - TradingView-style charts with ICT overlays
  - Scalping / Intraday / Swing trading modes
  - Flexible ICT concept selection
  - Prop firm account protection
  - MT5 auto-trade integration
  - Backtesting on XAUUSD only (by default)

Run with:
    streamlit run app.py
"""

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import streamlit as st
import pandas as pd
from streamlit_autorefresh import st_autorefresh

from config import (
    ALL_CONCEPTS, DEFAULT_INSTRUMENT, INSTRUMENTS, PRESETS,
    TRADING_MODES, MT5_SYMBOL_MAP,
)
from data_fetcher import fetch_ohlcv
from alerting import load_alert_config, save_alert_config, send_webhook_alert
from trade_generator import generate_signals
from charts import build_chart
from performance_tracker import (
    compute_stats,
    concept_comparison_fig,
    drawdown_fig,
    equity_curve_fig,
    win_loss_pie,
)
from prop_firm import (
    simulate_prop_account,
    safe_lot_size,
    account_summary,
    prop_equity_fig,
    daily_pnl_fig,
    risk_gauge_fig,
)
from mt5_trader import (
    MT5Config,
    mt5_runtime_supported,
    connect_mt5,
    disconnect_mt5,
    is_mt5_alive,
    ensure_mt5_connected,
    get_deal_close_info,
    get_account_info,
    get_open_positions,
    preview_trade_execution,
    execute_trade,
    close_position,
    get_live_price,
    trade_log,
    load_audit_log,
    save_credentials,
    load_credentials,
    delete_credentials,
)

# ===================================================================
# Page config
# ===================================================================
from grid_engine import (
    load_grid_state,
    save_grid_state,
    activate_grid,
    deactivate_grid,
    analyze_market_direction,
    build_grid_levels,
    check_levels_hit,
    mark_level_open,
    mark_level_closed,
    count_open_levels,
    get_open_levels,
    get_pending_levels,
    get_closed_levels,
    apply_account_preset,
    apply_regime_profile,
    evaluate_risk_guards,
    basket_floating_pnl_usd,
    should_close_basket,
    is_session_paused,
    grid_levels_dataframe,
    grid_summary,
    place_grid_order_mt5,
    close_grid_position_mt5,
    load_grid_audit,
    GridConfig,
    GRID_MAGIC,
)
from grid_brain import (
    load_brain,
    save_brain,
    train as train_brain,
    get_recommendation,
    get_global_stats,
    regime_stats_dataframe,
)
from grid_backtest import BacktestConfig, run_grid_backtest
_APP_BASE_DIR = Path(__file__).parent
_LOGO_PATH = _APP_BASE_DIR / "assets" / "sacred-soul-logo.svg"
st.set_page_config(
    page_title="Sacred Soul — XAUUSD",
    page_icon=str(_LOGO_PATH) if _LOGO_PATH.exists() else "📊",
    layout="wide",
)

# ===================================================================
# Sidebar
# ===================================================================
if _LOGO_PATH.exists():
    try:
        _logo_svg = _LOGO_PATH.read_text(encoding="utf-8")
        _logo_uri = f"data:image/svg+xml;utf8,{quote(_logo_svg)}"
        st.sidebar.markdown(
            (
                "<div style='display:flex;justify-content:center;margin-bottom:8px;'>"
                f"<img src='{_logo_uri}' width='150' height='150' "
                "style='width:150px;height:150px;object-fit:contain;'/>"
                "</div>"
            ),
            unsafe_allow_html=True,
        )
    except Exception:
        st.sidebar.image(str(_LOGO_PATH), width=150)
st.sidebar.title("Sacred Soul")
st.sidebar.caption("XAUUSD Focused")

st.markdown(
        """
        <style>
        .block-container {padding-top: 1.2rem;}
        div[data-testid="stMetric"] {
            background: linear-gradient(135deg, rgba(17,24,39,0.88), rgba(30,41,59,0.78));
            border: 1px solid rgba(148,163,184,0.22);
            border-radius: 12px;
            padding: 0.4rem 0.8rem;
        }
        .scanner-shell {
            border: 1px solid rgba(56, 189, 248, 0.35);
            border-radius: 12px;
            background: linear-gradient(120deg, rgba(3, 10, 20, 0.95), rgba(13, 33, 56, 0.92));
            padding: 0.65rem 0.9rem;
            margin-bottom: 0.55rem;
        }
        .scanner-head {
            font-size: 0.8rem;
            letter-spacing: 0.08em;
            color: #7dd3fc;
            text-transform: uppercase;
            margin-bottom: 0.25rem;
        }
        .scanner-tape {
            font-family: "Consolas", "Courier New", monospace;
            font-size: 0.9rem;
            color: #34d399;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: clip;
            border: 1px solid rgba(52, 211, 153, 0.3);
            border-radius: 8px;
            padding: 0.25rem 0.45rem;
            background: rgba(5, 20, 14, 0.65);
        }
        .status-chip-row {
            display: flex;
            gap: 0.45rem;
            flex-wrap: wrap;
            margin-top: 0.45rem;
        }
        .status-chip {
            font-size: 0.72rem;
            padding: 0.2rem 0.5rem;
            border-radius: 999px;
            border: 1px solid rgba(148, 163, 184, 0.35);
            background: rgba(30, 41, 59, 0.55);
            color: #e2e8f0;
            animation: chipPulse 1.4s ease-in-out infinite;
        }
        .risk-badge-row {margin-top: 0.35rem;}
        .risk-badge {
            display: inline-block;
            border-radius: 999px;
            padding: 0.22rem 0.62rem;
            font-size: 0.76rem;
            font-weight: 600;
            letter-spacing: 0.02em;
            border: 1px solid transparent;
        }
        .risk-low {
            color: #052e16;
            background: #86efac;
            border-color: #16a34a;
        }
        .risk-medium {
            color: #422006;
            background: #fde68a;
            border-color: #d97706;
        }
        .risk-high {
            color: #450a0a;
            background: #fecaca;
            border-color: #dc2626;
        }
        @keyframes chipPulse {
            0% {opacity: 0.6; transform: translateY(0px);}
            50% {opacity: 1.0; transform: translateY(-1px);}
            100% {opacity: 0.6; transform: translateY(0px);}
        }
        </style>
        """,
        unsafe_allow_html=True,
)


# Set Grid Trading as the default/first page
_PAGES = ["Grid Trading", "Live Analysis", "Performance", "Prop Firm", "MT5 Auto-Trade"]
page = st.sidebar.radio(
    "Navigate",
    _PAGES,
    index=0,  # Default to Grid Trading
)

# ── Trading Mode ─────────────────────────────────────────────────
st.sidebar.markdown("---")
st.sidebar.subheader("Trading Mode")
trading_mode = st.sidebar.radio(
    "Style",
    list(TRADING_MODES.keys()),
    horizontal=True,
    help="Scalping (1m-5m), Intraday (15m-1h), Swing (4h-Daily)",
)
mode_cfg = TRADING_MODES[trading_mode]
st.sidebar.caption(mode_cfg["description"])

# ── Market ───────────────────────────────────────────────────────
st.sidebar.markdown("---")
st.sidebar.subheader("Market")
symbol = st.sidebar.selectbox(
    "Instrument",
    list(INSTRUMENTS.keys()),
    index=list(INSTRUMENTS.keys()).index(DEFAULT_INSTRUMENT),
)
_default_tf_idx = mode_cfg["timeframes"].index(mode_cfg.get("default_tf", mode_cfg["timeframes"][0])) \
    if mode_cfg.get("default_tf") in mode_cfg["timeframes"] else 0
timeframe = st.sidebar.selectbox(
    "Timeframe",
    mode_cfg["timeframes"],
    index=_default_tf_idx,
)

# ── Strategy Parameters ─────────────────────────────────────────
st.sidebar.markdown("---")
st.sidebar.subheader("Strategy")
rr = st.sidebar.slider(
    "Risk : Reward",
    min_value=1.0, max_value=5.0,
    value=mode_cfg["default_rr"], step=0.5,
)
sweep_lookback = st.sidebar.slider(
    "Sweep lookback (bars)",
    min_value=3, max_value=60,
    value=mode_cfg["sweep_lookback"],
)

# ── Concept multi-select ─────────────────────────────────────────
st.sidebar.markdown("---")
st.sidebar.subheader("Required Concepts")
st.sidebar.caption(
    "Tick concepts that must **all** confirm for a signal. "
    "Fewer ticks → more trades."
)

preset = st.sidebar.selectbox(
    "Preset",
    ["(use mode default)", "(custom)"] + list(PRESETS.keys()),
)
if preset == "(use mode default)":
    default_concepts = mode_cfg["recommended_concepts"]
elif preset == "(custom)":
    default_concepts = ["Liquidity Sweep", "MSS"]
else:
    default_concepts = PRESETS[preset]

selected_concepts: list[str] = []
for c in ALL_CONCEPTS:
    val = st.sidebar.checkbox(c, value=(c in default_concepts), key=f"concept_{c}")
    if val:
        selected_concepts.append(c)
# ── Auto-Refresh ─────────────────────────────────────────────
st.sidebar.markdown("---")
st.sidebar.subheader("Auto-Refresh")
auto_refresh = st.sidebar.checkbox("Enable auto-refresh", value=False,
                                    help="Periodically re-fetch data and check for new signals")
refresh_interval = st.sidebar.selectbox(
    "Interval",
    options=[30, 60, 120, 300],
    index=1,
    format_func=lambda s: f"{s}s" if s < 60 else f"{s // 60} min",
    disabled=not auto_refresh,
)

# MT5 page can run on a faster independent refresh cadence.
mt5_realtime_refresh = False
mt5_realtime_interval = 2
mt5_lean_ui = True
mt5_perf_guard = True
mt5_allow_ultra_fast = False
if page == "MT5 Auto-Trade":
    st.sidebar.markdown("---")
    st.sidebar.subheader("MT5 Real-Time")
    mt5_realtime_refresh = st.sidebar.checkbox(
        "Enable MT5 real-time updates",
        value=True,
        help="Uses fast refresh for MT5 page (orders, PnL, and signal checks).",
    )
    mt5_realtime_interval = st.sidebar.select_slider(
        "MT5 refresh interval",
        options=[1, 2, 3, 5, 10, 30],
        value=2,
        disabled=not mt5_realtime_refresh,
    )
    mt5_lean_ui = st.sidebar.checkbox(
        "Lean MT5 UI in ultra-fast mode",
        value=True,
        help="Skips heavy tables/charts at very fast refresh intervals to keep the page responsive.",
        disabled=not mt5_realtime_refresh,
    )
    mt5_perf_guard = st.sidebar.checkbox(
        "Performance guard",
        value=True,
        help="Auto-throttles very aggressive refresh to reduce lag.",
        disabled=not mt5_realtime_refresh,
    )
    mt5_allow_ultra_fast = st.sidebar.checkbox(
        "Allow ultra-fast 1s/2s",
        value=False,
        help="Use only on high-performance machine. Can cause lag on heavy sessions.",
        disabled=(not mt5_realtime_refresh) or (not mt5_perf_guard),
    )
    if mt5_realtime_refresh and mt5_realtime_interval <= 2:
        st.sidebar.caption("High-frequency mode can increase CPU/network load.")

effective_auto_refresh = auto_refresh or (page == "MT5 Auto-Trade" and mt5_realtime_refresh)
effective_refresh_interval = (
    mt5_realtime_interval if (page == "MT5 Auto-Trade" and mt5_realtime_refresh) else refresh_interval
)

if (
    page == "MT5 Auto-Trade"
    and mt5_realtime_refresh
    and mt5_perf_guard
    and (not mt5_allow_ultra_fast)
    and effective_refresh_interval < 3
):
    effective_refresh_interval = 3
    st.sidebar.caption("Performance guard active: MT5 refresh clamped to 3s.")

mt5_ultra_fast_mode = (
    page == "MT5 Auto-Trade"
    and mt5_realtime_refresh
    and mt5_realtime_interval <= 2
    and mt5_lean_ui
)

if effective_auto_refresh:
    refresh_count = st_autorefresh(
        interval=effective_refresh_interval * 1000,
        key="auto_refresh_timer",
    )
    st.sidebar.caption(f"🔄 Refreshes every **{effective_refresh_interval}s** (cycle #{refresh_count})")
else:
    refresh_count = 0
# ── Chart overlay toggles ────────────────────────────────────────
st.sidebar.markdown("---")
st.sidebar.subheader("Chart Overlays")
show_pdhl = st.sidebar.checkbox("PDH / PDL", value=True)
show_fvg = st.sidebar.checkbox("FVG", value=True)
show_mss = st.sidebar.checkbox("MSS", value=True)
show_ob = st.sidebar.checkbox("Order Blocks", value=True)
show_ote = st.sidebar.checkbox("OTE Zones", value=False)
show_sweep = st.sidebar.checkbox("Liquidity Sweeps", value=True)
show_ssl_bsl = st.sidebar.checkbox("SSL / BSL", value=False)
show_breaker = st.sidebar.checkbox("Breaker Blocks", value=False)
show_mitigation = st.sidebar.checkbox("Mitigation", value=False)
show_po3 = st.sidebar.checkbox("PO3 Phases", value=False)
show_order_flow = st.sidebar.checkbox("Order Flow (CVD/Delta)", value=True)


# ===================================================================
# Data loading (cached 5 min)
# ===================================================================


_cache_ttl = refresh_interval if auto_refresh else 300
_live_cache_ttl = max(1, int(effective_refresh_interval)) if page == "MT5 Auto-Trade" and mt5_realtime_refresh else 10


@st.cache_data(ttl=_cache_ttl, show_spinner="Fetching market data …")
def load_data(sym: str, tf: str) -> pd.DataFrame:
    return fetch_ohlcv(sym, tf)


@st.cache_data(ttl=_cache_ttl, show_spinner="Generating signals …")
def load_signals(sym: str, tf: str, concepts_key: str,
                 _rr: float, _lookback: int) -> pd.DataFrame:
    df = load_data(sym, tf)
    if df.empty:
        return pd.DataFrame()
    concepts = concepts_key.split("|") if concepts_key else []
    return generate_signals(df, concepts, rr_ratio=_rr, sweep_lookback=_lookback)


def _tf_to_minutes(tf: str) -> int:
    mapping = {
        "1m": 1,
        "5m": 5,
        "15m": 15,
        "1h": 60,
        "4h": 240,
        "Daily": 1440,
    }
    return mapping.get(tf, 5)


@st.cache_data(ttl=_live_cache_ttl, show_spinner=False)
def load_live_signals(sym: str, tf: str, concepts_key: str,
                      _rr: float, _lookback: int,
                      bars_window: int = 500) -> pd.DataFrame:
    """Fast signal generation for MT5 auto-trade using recent candles only."""
    df = load_data(sym, tf)
    if df.empty:
        return pd.DataFrame()

    live_df = df.tail(max(bars_window, _lookback * 10)).copy()
    concepts = concepts_key.split("|") if concepts_key else []
    sigs = generate_signals(live_df, concepts, rr_ratio=_rr, sweep_lookback=_lookback)
    if sigs.empty:
        return sigs

    # Keep only a short execution window so auto-trade does not process stale setups.
    now_ts = live_df.index.max()
    max_age = pd.Timedelta(minutes=_tf_to_minutes(tf) * 3)
    sigs = sigs[sigs["signal_time"] >= now_ts - max_age]
    return sigs.sort_values("signal_time")


def get_latest_fresh_open_signal(sigs: pd.DataFrame, tf: str,
                                 reference_ts: pd.Timestamp) -> pd.Series | None:
    if sigs.empty:
        return None

    open_sigs = sigs[sigs["status"] == "OPEN"].copy()
    if open_sigs.empty:
        return None

    max_age = pd.Timedelta(minutes=_tf_to_minutes(tf) * 2)
    fresh = open_sigs[open_sigs["signal_time"] >= reference_ts - max_age]
    if fresh.empty:
        return None

    return fresh.sort_values("signal_time", ascending=False).iloc[0]


def _concept_count(concepts_used: str) -> int:
    if not concepts_used:
        return 0
    if isinstance(concepts_used, str):
        parts = [p.strip() for p in concepts_used.replace("|", ",").split(",") if p.strip()]
        return len(parts)
    return 0


def signal_quality_score(sig: pd.Series, tf: str, reference_ts: pd.Timestamp) -> float:
    """Heuristic quality score (0-100) for execution filtering."""
    tf_min = _tf_to_minutes(tf)
    rr = float(sig.get("rr_ratio", 1.5))
    concepts = _concept_count(str(sig.get("concepts_used", "")))
    entry = float(sig.get("entry", 0.0))
    sl = float(sig.get("sl", entry))
    risk_pts = abs(entry - sl)

    try:
        age_min = max((reference_ts - sig["signal_time"]).total_seconds() / 60.0, 0.0)
    except Exception:
        age_min = tf_min * 2
    age_bars = age_min / max(tf_min, 1)

    score = 45.0
    score += min(concepts * 8.0, 24.0)
    score += min(rr * 8.0, 20.0)
    score += max(0.0, 20.0 - (age_bars * 6.0))

    # Penalize extremes in stop distance that often reduce execution quality.
    if risk_pts < 2.0:
        score -= 12.0
    elif risk_pts < 4.0:
        score -= 6.0
    elif 6.0 <= risk_pts <= 40.0:
        score += 8.0
    elif risk_pts > 90.0:
        score -= 10.0

    return round(max(0.0, min(score, 100.0)), 1)


def rank_live_signals(
    sigs: pd.DataFrame,
    tf: str,
    reference_ts: pd.Timestamp,
    min_quality: float,
    max_signal_age_bars: float,
) -> tuple[pd.DataFrame, pd.Series | None, str]:
    if sigs.empty:
        sigs = sigs.copy()
        sigs["quality_score"] = pd.Series(dtype=float)
        sigs["age_bars"] = pd.Series(dtype=float)
        return sigs, None, "No live signals in window"

    ranked = sigs.copy()
    ranked = ranked[ranked["status"] == "OPEN"].copy()
    if ranked.empty:
        ranked["quality_score"] = pd.Series(dtype=float)
        ranked["age_bars"] = pd.Series(dtype=float)
        return ranked, None, "No OPEN signal"

    tf_min = _tf_to_minutes(tf)
    ranked["age_min"] = (reference_ts - ranked["signal_time"]).dt.total_seconds().clip(lower=0) / 60.0
    ranked["age_bars"] = ranked["age_min"] / max(tf_min, 1)

    # ── vectorised quality score ────────────────────────────────
    _rr = ranked.get("rr_ratio", pd.Series(1.5, index=ranked.index)).astype(float).fillna(1.5)
    _concepts = ranked.get("concepts_used", pd.Series("", index=ranked.index)).astype(str).str.count(r"[+,|]") + 1
    _entry = ranked.get("entry", pd.Series(0.0, index=ranked.index)).astype(float).fillna(0.0)
    _sl = ranked.get("sl", _entry).astype(float).fillna(_entry)
    _risk = (_entry - _sl).abs()
    _age_bars = ranked["age_bars"]

    _qs = 45.0
    _qs = _qs + (_concepts * 8.0).clip(upper=24.0)
    _qs = _qs + (_rr * 8.0).clip(upper=20.0)
    _qs = _qs + (20.0 - _age_bars * 6.0).clip(lower=0.0)

    # risk-distance adjustment
    _qs = _qs - 12.0 * (_risk < 2.0).astype(float)
    _qs = _qs - 6.0 * ((_risk >= 2.0) & (_risk < 4.0)).astype(float)
    _qs = _qs + 8.0 * ((_risk >= 6.0) & (_risk <= 40.0)).astype(float)
    _qs = _qs - 10.0 * (_risk > 90.0).astype(float)

    ranked["quality_score"] = _qs.clip(0.0, 100.0).round(1)

    ranked = ranked[ranked["age_bars"] <= max_signal_age_bars]
    if ranked.empty:
        return ranked, None, "Signals are stale for configured max age"

    eligible = ranked[ranked["quality_score"] >= min_quality]
    if eligible.empty:
        best = ranked.sort_values(["quality_score", "signal_time"], ascending=[False, False]).iloc[0]
        return ranked.sort_values(["quality_score", "signal_time"], ascending=[False, False]), None, (
            f"No signal passed quality threshold {min_quality:.0f}. Best={best['quality_score']:.1f}"
        )

    best = eligible.sort_values(["quality_score", "signal_time"], ascending=[False, False]).iloc[0]
    return ranked.sort_values(["quality_score", "signal_time"], ascending=[False, False]), best, "OK"


def scanner_phase_label(cycle: int) -> str:
    phases = [
        "Booting scanner grid",
        "Sampling liquidity map",
        "Scanning structure breaks",
        "Validating confluence matrix",
        "Ranking executable setups",
        "Publishing trade readiness",
    ]
    return phases[cycle % len(phases)]


def scanner_stream_tape(cycle: int, width: int = 42) -> str:
    bits = []
    for i in range(width):
        bits.append("1" if ((i + cycle) % 3 == 0 or (i * 7 + cycle) % 11 == 0) else "0")
    return "".join(bits)


def classify_market_phase(ranked_live: pd.DataFrame) -> str:
    if ranked_live is None or ranked_live.empty or "direction" not in ranked_live.columns:
        return "Chop"

    seq = ranked_live.sort_values("signal_time").tail(6)["direction"].astype(str).tolist()
    if len(seq) < 3:
        return "Chop"

    switches = sum(1 for i in range(1, len(seq)) if seq[i] != seq[i - 1])
    if switches == 0:
        return "Trend"
    if switches >= max(2, len(seq) // 2):
        return "Chop"
    return "Pullback"


def filter_ranked_signals_by_entry_drift(
    ranked_live: pd.DataFrame,
    live_tick: dict | None,
    max_entry_drift_price: float,
) -> tuple[pd.DataFrame, pd.Series | None, str | None]:
    """Keep only executable signals by live entry-drift guardrail for market orders."""
    if ranked_live is None or ranked_live.empty:
        return ranked_live, None, None

    ranked = ranked_live.copy()
    if not live_tick:
        return ranked, ranked.iloc[0], None

    ask = float(live_tick.get("ask", 0.0) or 0.0)
    bid = float(live_tick.get("bid", 0.0) or 0.0)
    if ask <= 0 and bid <= 0:
        return ranked, ranked.iloc[0], None

    def _live_ref(direction: str) -> float:
        return ask if str(direction).upper() == "LONG" else bid

    ranked["live_ref"] = ranked["direction"].apply(_live_ref)
    ranked["entry_drift"] = (ranked["entry"] - ranked["live_ref"]).abs()

    if max_entry_drift_price <= 0:
        return ranked, ranked.iloc[0], None

    eligible = ranked[ranked["entry_drift"] <= float(max_entry_drift_price)]
    if eligible.empty:
        best_drift = float(ranked["entry_drift"].min()) if not ranked.empty else 0.0
        msg = (
            f"No executable signal within entry-drift guardrail ({max_entry_drift_price:.2f}). "
            f"Best drift={best_drift:.2f}."
        )
        return ranked, None, msg

    return ranked, eligible.iloc[0], None


def build_market_condition_summary(
    ranked_live: pd.DataFrame,
    latest_sig: pd.Series | None,
    live_tick: dict | None,
    gate_reason: str,
    spread_limit: float,
    min_quality: float,
) -> dict:
    if ranked_live is None or ranked_live.empty:
        return {
            "regime": "Quiet / No Setup",
            "bias": "Neutral",
            "conviction": "Low",
            "structure": "No directional structure confirmed",
            "market_phase": "Chop",
            "execution_risk": "Low",
            "headline": "No fresh OPEN setup in live window",
            "spread": None,
            "spread_util_pct": None,
            "regime_score": 15.0,
        }

    long_count = int((ranked_live["direction"] == "LONG").sum())
    short_count = int((ranked_live["direction"] == "SHORT").sum())
    if long_count > short_count:
        bias = "Bullish"
    elif short_count > long_count:
        bias = "Bearish"
    else:
        bias = "Balanced"

    top_quality = float(ranked_live["quality_score"].max()) if "quality_score" in ranked_live.columns else 0.0
    if top_quality >= 82:
        conviction = "High"
    elif top_quality >= 68:
        conviction = "Medium"
    else:
        conviction = "Low"

    mean_age = float(ranked_live["age_bars"].mean()) if "age_bars" in ranked_live.columns else 99.0
    phase = classify_market_phase(ranked_live)
    if mean_age <= 1.2 and top_quality >= max(70.0, min_quality):
        structure = "Trend continuation likely"
    elif mean_age <= 2.2:
        structure = "Transitional structure"
    else:
        structure = "Late-cycle / mean reversion risk"

    if latest_sig is not None and gate_reason == "OK":
        regime = f"{str(latest_sig['direction']).title()} Momentum"
        headline = (
            f"{latest_sig['direction']} setup is executable "
            f"(quality {float(latest_sig.get('quality_score', 0.0)):.1f})."
        )
    elif "quality threshold" in gate_reason.lower():
        regime = "Filtering / Selective"
        headline = "Signals exist, but quality gate is filtering current setups."
    elif "stale" in gate_reason.lower():
        regime = "Late Cycle / Stale"
        headline = "Setups exist but timing window is expired for execution."
    else:
        regime = "Range / Mixed"
        headline = "Market is mixed. Wait for cleaner directional confluence."

    spread = None
    spread_util_pct = None
    execution_risk = "Low"
    if live_tick:
        try:
            spread = abs(float(live_tick.get("ask", 0.0)) - float(live_tick.get("bid", 0.0)))
        except Exception:
            spread = None

    if spread is not None and spread_limit > 0:
        ratio = spread / spread_limit
        spread_util_pct = ratio * 100.0
        if ratio >= 0.9:
            execution_risk = "High"
        elif ratio >= 0.6:
            execution_risk = "Medium"
        else:
            execution_risk = "Low"
    elif "stale" in gate_reason.lower():
        execution_risk = "Medium"

    total = max(len(ranked_live), 1)
    dominance = abs(long_count - short_count) / total
    regime_score = max(0.0, min(100.0, (top_quality * 0.72) + (dominance * 28.0) - (mean_age * 8.0)))
    if "stale" in gate_reason.lower():
        regime_score = max(0.0, regime_score - 12.0)

    return {
        "regime": regime,
        "bias": bias,
        "conviction": conviction,
        "structure": structure,
        "market_phase": phase,
        "execution_risk": execution_risk,
        "headline": headline,
        "spread": spread,
        "spread_util_pct": spread_util_pct,
        "regime_score": round(regime_score, 1),
    }


concepts_key = "|".join(sorted(selected_concepts))

_BASE_DIR = Path(__file__).parent
WORKER_CONFIG_FILE = _BASE_DIR / "worker_config.json"
WORKER_HEARTBEAT_FILE = _BASE_DIR / "worker_heartbeat.json"
WATCHDOG_HEARTBEAT_FILE = _BASE_DIR / "watchdog_heartbeat.json"

POLICY_PROFILES = {
    "Conservative": {
        "max_spread_price": 0.40,
        "max_entry_drift_price": 1.20,
        "max_trades_per_day": 4,
        "max_open_positions": 1,
        "enforce_session_window": True,
        "session_start_utc": 6,
        "session_end_utc": 17,
    },
    "Balanced": {
        "max_spread_price": 0.60,
        "max_entry_drift_price": 2.00,
        "max_trades_per_day": 8,
        "max_open_positions": 2,
        "enforce_session_window": False,
        "session_start_utc": 0,
        "session_end_utc": 23,
    },
    "Aggressive": {
        "max_spread_price": 1.00,
        "max_entry_drift_price": 3.00,
        "max_trades_per_day": 14,
        "max_open_positions": 3,
        "enforce_session_window": False,
        "session_start_utc": 0,
        "session_end_utc": 23,
    },
}


def load_worker_config() -> dict:
    defaults = {
        "enabled": False,
        "auto_trade_enabled": True,
        "symbol": DEFAULT_INSTRUMENT,
        "timeframe": mode_cfg.get("default_tf", timeframe),
        "concepts": mode_cfg.get("recommended_concepts", []),
        "rr": mode_cfg.get("default_rr", 1.5),
        "sweep_lookback": mode_cfg.get("sweep_lookback", 10),
        "lot_size": mode_cfg.get("default_lot", 0.01),
        "min_quality_score": 68.0,
        "max_signal_age_bars": 2.0,
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


def save_worker_config(cfg: dict):
    WORKER_CONFIG_FILE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def load_worker_heartbeat() -> dict | None:
    if not WORKER_HEARTBEAT_FILE.exists():
        return None
    try:
        return json.loads(WORKER_HEARTBEAT_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None


def load_watchdog_heartbeat() -> dict | None:
    if not WATCHDOG_HEARTBEAT_FILE.exists():
        return None
    try:
        return json.loads(WATCHDOG_HEARTBEAT_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None


def summarize_audit_events(events: list[dict], hours: int = 24) -> dict:
    if not events:
        return {
            "window_events": 0,
            "filled": 0,
            "failed": 0,
            "blocked": 0,
            "fill_rate": 0.0,
            "avg_response_ms": 0.0,
            "p95_response_ms": 0.0,
        }

    cutoff = datetime.now(timezone.utc).timestamp() - (hours * 3600)
    rows = []
    for ev in events:
        ts_raw = ev.get("timestamp")
        if not ts_raw:
            continue
        try:
            ts = datetime.fromisoformat(ts_raw).replace(tzinfo=timezone.utc).timestamp()
        except Exception:
            continue
        if ts >= cutoff:
            rows.append(ev)

    filled = sum(1 for r in rows if r.get("status") == "FILLED")
    failed = sum(1 for r in rows if r.get("status") == "FAILED")
    blocked = sum(1 for r in rows if r.get("status") == "BLOCKED")
    total = len(rows)
    fill_rate = (filled / total * 100.0) if total else 0.0
    response_vals = []
    for r in rows:
        if "response_ms" in r:
            try:
                response_vals.append(float(r["response_ms"]))
            except Exception:
                pass

    if response_vals:
        response_vals = sorted(response_vals)
        avg_response_ms = round(sum(response_vals) / len(response_vals), 2)
        idx_95 = int(0.95 * (len(response_vals) - 1))
        p95_response_ms = round(response_vals[idx_95], 2)
    else:
        avg_response_ms = 0.0
        p95_response_ms = 0.0

    return {
        "window_events": total,
        "filled": filled,
        "failed": failed,
        "blocked": blocked,
        "fill_rate": round(fill_rate, 1),
        "avg_response_ms": avg_response_ms,
        "p95_response_ms": p95_response_ms,
    }


def status_trend_dataframe(events: list[dict], hours: int = 24) -> pd.DataFrame:
    """Build hourly status trend dataframe for ops monitoring."""
    cutoff = datetime.now(timezone.utc).timestamp() - (hours * 3600)
    rows = []
    for ev in events:
        ts_raw = ev.get("timestamp")
        status = str(ev.get("status", "")).upper()
        if not ts_raw or not status:
            continue
        try:
            ts_dt = datetime.fromisoformat(ts_raw).replace(tzinfo=timezone.utc)
        except Exception:
            continue
        if ts_dt.timestamp() < cutoff:
            continue
        rows.append({
            "hour": ts_dt.replace(minute=0, second=0, microsecond=0),
            "status": status,
            "count": 1,
        })

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    trend = df.groupby(["hour", "status"], as_index=False)["count"].sum()
    pivot = trend.pivot(index="hour", columns="status", values="count").fillna(0)
    return pivot.sort_index()


def summarize_rejection_reasons(events: list[dict], hours: int = 24) -> pd.DataFrame:
    """Return top FAILED/BLOCKED reasons in the selected lookback window."""
    cutoff = datetime.now(timezone.utc).timestamp() - (hours * 3600)
    rows: dict[str, int] = {}

    for ev in events:
        status = str(ev.get("status", "")).upper()
        if status not in {"FAILED", "BLOCKED"}:
            continue

        ts_raw = ev.get("timestamp")
        if not ts_raw:
            continue
        try:
            ts = datetime.fromisoformat(ts_raw).replace(tzinfo=timezone.utc).timestamp()
        except Exception:
            continue
        if ts < cutoff:
            continue

        reason = str(ev.get("reason", "unknown")).strip() or "unknown"
        short_reason = reason.split("|")[0].strip()
        if len(short_reason) > 90:
            short_reason = short_reason[:87] + "..."
        rows[short_reason] = rows.get(short_reason, 0) + 1

    if not rows:
        return pd.DataFrame(columns=["Reason", "Count"])

    df = pd.DataFrame(
        [{"Reason": k, "Count": v} for k, v in rows.items()]
    ).sort_values("Count", ascending=False)
    return df


def last_execution_attempt(events: list[dict]) -> dict | None:
    if not events:
        return None
    try:
        ordered = sorted(events, key=lambda x: x.get("timestamp", ""), reverse=True)
        return ordered[0]
    except Exception:
        return None


# ===================================================================
# MT5 shared state — available to ALL tabs
# ===================================================================
# Auto-connect from saved credentials (runs once per session)
saved_creds = load_credentials()
_mt5_supported, _mt5_support_reason = mt5_runtime_supported()
if _mt5_supported and (not st.session_state.get("mt5_connected")) and saved_creds and saved_creds["login"] > 0:
    if "mt5_auto_connect_tried" not in st.session_state:
        st.session_state["mt5_auto_connect_tried"] = True
        _cfg = MT5Config(
            login=int(saved_creds["login"]),
            password=saved_creds["password"],
            server=saved_creds["server"],
            symbol=saved_creds.get("symbol", "XAUUSD"),
            max_lot=saved_creds.get("max_lot", 0.10),
            max_spread_price=saved_creds.get("max_spread_price", 0.60),
            max_entry_drift_price=saved_creds.get("max_entry_drift_price", 2.00),
            max_trades_per_day=int(saved_creds.get("max_trades_per_day", 8)),
            max_open_positions=int(saved_creds.get("max_open_positions", 2)),
            enforce_session_window=bool(saved_creds.get("enforce_session_window", False)),
            session_start_utc=int(saved_creds.get("session_start_utc", 0)),
            session_end_utc=int(saved_creds.get("session_end_utc", 23)),
            min_stop_distance_pips=float(saved_creds.get("min_stop_distance_pips", 2.0)),
            max_stop_distance_pips=float(saved_creds.get("max_stop_distance_pips", 200.0)),
            min_rr_ratio=float(saved_creds.get("min_rr_ratio", 1.5)),
        )
        ok, msg = connect_mt5(_cfg)
        if ok:
            st.session_state["mt5_connected"] = True
            st.session_state["mt5_config"] = _cfg
            st.sidebar.success("MT5 auto-connected ✓")

# Fetch MT5 account data for cross-tab use
mt5_account: dict | None = None
mt5_positions: list[dict] = []
st.sidebar.markdown("---")
if st.session_state.get("mt5_connected"):
    # ── Health check: detect stale connection ─────────────────
    _mt5_cfg = st.session_state.get("mt5_config")
    if not is_mt5_alive() and _mt5_cfg:
        _recon_ok, _recon_msg = ensure_mt5_connected(_mt5_cfg)
        if not _recon_ok:
            st.session_state["mt5_connected"] = False
            st.sidebar.error(f"MT5 disconnected: {_recon_msg}")
        else:
            st.sidebar.info("MT5 reconnected ✓")

if st.session_state.get("mt5_connected"):
    mt5_account = get_account_info()
    _cfg = st.session_state.get("mt5_config")
    if _cfg:
        mt5_positions = get_open_positions(_cfg.symbol)
    if mt5_account:
        _pnl = mt5_account.get("profit", 0)
        _pnl_color = "green" if _pnl >= 0 else "red"
        st.sidebar.markdown(
            f'<div style="background:#1a1e2e;border-radius:8px;padding:10px;margin-bottom:6px">'
            f'<span style="color:#26a69a;font-weight:bold">● MT5 ACTIVE</span><br>'
            f'<span style="color:#adb5bd;font-size:13px">'
            f'Bal: ${mt5_account["balance"]:,.2f}<br>'
            f'Equity: ${mt5_account["equity"]:,.2f}<br>'
            f'<span style="color:{_pnl_color};font-weight:bold">'
            f'PnL: {"" if _pnl < 0 else "+"}${_pnl:,.2f}</span><br>'
            f'Positions: {len(mt5_positions)}'
            f'</span></div>',
            unsafe_allow_html=True,
        )
    else:
        st.sidebar.markdown(
            '<div style="background:#1a1e2e;border-radius:8px;padding:10px">'
            '<span style="color:#ef5350;font-weight:bold">● MT5 ERROR</span><br>'
            '<span style="color:#adb5bd;font-size:13px">Connected but no data</span></div>',
            unsafe_allow_html=True,
        )
else:
    st.sidebar.markdown(
        '<div style="background:#1a1e2e;border-radius:8px;padding:10px">'
        '<span style="color:#787b86">○ MT5 OFFLINE</span><br>'
        '<span style="color:#adb5bd;font-size:13px">Go to MT5 Auto-Trade to connect</span></div>',
        unsafe_allow_html=True,
    )


# ===================================================================
# AI Risk Advisor — uses backtest stats to recommend risk
# ===================================================================
def ai_risk_recommendation(stats: dict, balance: float,
                           max_dd_pct: float = 10.0) -> dict:
    """Compute optimal risk per trade from backtest statistics.

    Uses a fractional-Kelly approach:
      Kelly% = W - (1-W)/R   (W=win_rate, R=avg_win/avg_loss)
      We use ½-Kelly for safety, then cap at max_dd_pct / 10.
    """
    wr = stats.get("win_rate", 50) / 100.0
    pf = stats.get("profit_factor", 1.0)
    avg_r = stats.get("avg_pnl_r", 0.5)
    max_dd = stats.get("max_drawdown", -5)
    total = stats.get("total_trades", 0)

    # Kelly criterion
    if pf > 0 and avg_r != 0:
        avg_win_r = avg_r if avg_r > 0 else 1.0
        # W - (1-W)/R
        kelly = wr - (1 - wr) / max(avg_win_r, 0.01)
    else:
        kelly = 0.01

    # Half-Kelly, clamped
    half_kelly = max(0.25, min(kelly * 50, 5.0))  # as percentage

    # Also cap so max_consecutive_losses × risk < dd buffer
    # Estimate max consec losses from win rate (geometric)
    import math
    if wr > 0:
        est_consec = math.ceil(math.log(0.01) / math.log(1 - wr))
    else:
        est_consec = 20
    dd_safe = max_dd_pct / max(est_consec, 1)
    dd_safe = max(0.25, min(dd_safe, 3.0))

    recommended = round(min(half_kelly, dd_safe), 2)

    # Suggested lot size (assuming 20-pip SL on XAUUSD, $10/pip std lot)
    risk_dollar = balance * (recommended / 100)
    suggested_lot = round(risk_dollar / (20 * 10), 2)
    suggested_lot = max(0.01, min(suggested_lot, 1.0))

    confidence = "HIGH" if total >= 50 and pf >= 1.5 else \
                 "MEDIUM" if total >= 20 and pf >= 1.0 else "LOW"

    return {
        "recommended_risk_pct": recommended,
        "half_kelly_pct": round(half_kelly, 2),
        "dd_safe_pct": round(dd_safe, 2),
        "suggested_lot": suggested_lot,
        "risk_dollar": round(risk_dollar, 2),
        "est_consec_losses": est_consec,
        "confidence": confidence,
        "reasoning": (
            f"Win Rate {wr*100:.1f}%, PF {pf}, Avg R {avg_r} → "
            f"½-Kelly {half_kelly:.2f}%, DD-safe {dd_safe:.2f}% → "
            f"using {recommended:.2f}%"
        ),
    }


if page == "Live Analysis":
    st.header(f"📈 {symbol} — {timeframe} ({trading_mode})")

    if not selected_concepts:
        st.warning("No concepts selected — tick at least one in the sidebar.")

    df = load_data(symbol, timeframe)
    if df.empty:
        st.error("No data returned. Market may be closed or symbol unavailable.")
        st.stop()

    signals = load_signals(symbol, timeframe, concepts_key, rr, sweep_lookback)

    # Chart
    fig = build_chart(
        df, symbol, timeframe,
        signals=signals if not signals.empty else None,
        show_fvg=show_fvg, show_mss=show_mss, show_ob=show_ob,
        show_ote=show_ote, show_sweep=show_sweep,
        show_ssl_bsl=show_ssl_bsl, show_breaker=show_breaker,
        show_mitigation=show_mitigation, show_pdhl=show_pdhl,
        show_po3=show_po3, show_order_flow=show_order_flow,
    )
    st.plotly_chart(fig, use_container_width=True)

    # Signals table
    st.subheader("Trade Signals")
    if signals.empty:
        st.info("No setups match the selected concept filter. Try un-ticking some concepts.")
    else:
        display_cols = [
            "signal_time", "direction", "entry", "sl", "tp",
            "be_level", "risk", "rr_ratio", "concepts_used",
            "status", "result", "pnl",
        ]
        existing = [c for c in display_cols if c in signals.columns]
        st.dataframe(
            signals[existing].sort_values("signal_time", ascending=False),
            use_container_width=True, hide_index=True,
        )

    # Quick stats
    if not signals.empty:
        stats = compute_stats(signals)
        c1, c2, c3, c4, c5, c6 = st.columns(6)
        c1.metric("Trades", stats["total_trades"])
        c2.metric("Win Rate", f'{stats["win_rate"]}%')
        c3.metric("Avg R", stats["avg_pnl_r"])
        c4.metric("Max DD (R)", stats["max_drawdown"])
        c5.metric("Profit Factor", stats["profit_factor"])
        c6.metric("Sharpe", stats["sharpe"])


# ===================================================================
# PAGE: Performance (XAUUSD only, all timeframes for the mode)
# ===================================================================
elif page == "Performance":
    st.header(f"📊 Performance — {symbol} ({trading_mode})")

    mode_tfs = mode_cfg["timeframes"]
    st.info(
        f"Backtest on **{symbol}** across timeframes: "
        f"**{', '.join(mode_tfs)}** | "
        f"Concepts: **{', '.join(selected_concepts) or '(none)'}** | R:R = {rr}"
    )

    all_sigs: list[pd.DataFrame] = []
    bar = st.progress(0)

    for idx, tf in enumerate(mode_tfs):
        try:
            sigs = load_signals(symbol, tf, concepts_key, rr, sweep_lookback)
            if not sigs.empty:
                sigs = sigs.copy()
                sigs["symbol"] = symbol
                sigs["timeframe"] = tf
                all_sigs.append(sigs)
        except Exception:
            pass
        bar.progress((idx + 1) / len(mode_tfs))
    bar.empty()

    if not all_sigs:
        st.warning("No signals found. Try relaxing the concept filter or changing the trading mode.")
        st.stop()

    combined = pd.concat(all_sigs, ignore_index=True)

    # KPIs
    stats = compute_stats(combined)
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Total Trades", stats["total_trades"])
    c2.metric("Wins", stats["wins"])
    c3.metric("Losses", stats["losses"])
    c4.metric("Win Rate", f'{stats["win_rate"]}%')
    c5.metric("Profit Factor", stats["profit_factor"])
    c6.metric("Max DD (R)", stats["max_drawdown"])

    # AI Risk Advisor
    _perf_bal = mt5_account["balance"] if mt5_account else 10_000
    ai_rec = ai_risk_recommendation(stats, balance=_perf_bal)
    st.markdown("---")
    st.subheader("🤖 AI Risk Advisor")
    ar1, ar2, ar3, ar4 = st.columns(4)
    ar1.metric("Recommended Risk %", f"{ai_rec['recommended_risk_pct']}%")
    ar2.metric("Suggested Lot", f"{ai_rec['suggested_lot']}")
    ar3.metric("Risk per Trade ($)", f"${ai_rec['risk_dollar']:.0f}")
    ar4.metric("Confidence", ai_rec["confidence"])
    st.info(f"📊 {ai_rec['reasoning']}")
    if mt5_account:
        st.caption(f"Based on MT5 balance: ${mt5_account['balance']:,.2f}")
    else:
        st.caption("Connect MT5 for real balance — currently using $10,000 default.")

    # Charts
    col_l, col_r = st.columns(2)
    with col_l:
        st.plotly_chart(equity_curve_fig(combined), use_container_width=True)
    with col_r:
        st.plotly_chart(win_loss_pie(combined), use_container_width=True)

    st.plotly_chart(drawdown_fig(combined), use_container_width=True)

    # Concept comparison
    st.subheader("Win Rate by Concept Combination")
    st.plotly_chart(concept_comparison_fig(combined), use_container_width=True)

    # RR comparison — run multiple RRs to find best
    st.subheader("R:R Comparison")
    rr_results = []
    for test_rr in [1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0]:
        for tf in mode_tfs:
            try:
                test_sigs = load_signals(symbol, tf, concepts_key, test_rr, sweep_lookback)
                if not test_sigs.empty:
                    s = compute_stats(test_sigs)
                    rr_results.append({
                        "R:R": test_rr,
                        "Timeframe": tf,
                        "Trades": s["total_trades"],
                        "Win Rate %": s["win_rate"],
                        "Avg R": s["avg_pnl_r"],
                        "Profit Factor": s["profit_factor"],
                        "Max DD (R)": s["max_drawdown"],
                        "Sharpe": s["sharpe"],
                    })
            except Exception:
                pass

    if rr_results:
        rr_df = pd.DataFrame(rr_results)
        st.dataframe(rr_df.sort_values("Avg R", ascending=False),
                      use_container_width=True, hide_index=True)

        # Highlight best
        best = rr_df.sort_values("Avg R", ascending=False).iloc[0]
        st.success(
            f"**Best R:R for {symbol} ({trading_mode}):** "
            f"R:R = {best['R:R']} on {best['Timeframe']} — "
            f"Win Rate {best['Win Rate %']}%, Avg R {best['Avg R']}, "
            f"PF {best['Profit Factor']}, Sharpe {best['Sharpe']}"
        )

    # Trade log
    st.subheader("Trade Log")
    concept_filter = st.text_input("Filter by concepts (substring match)", "")
    log_cols = [
        "symbol", "timeframe", "signal_time", "direction",
        "entry", "sl", "tp", "concepts_used",
        "status", "result", "pnl",
    ]
    existing = [c for c in log_cols if c in combined.columns]
    log_df = combined[existing].sort_values("signal_time", ascending=False)
    if concept_filter and "concepts_used" in log_df.columns:
        log_df = log_df[log_df["concepts_used"].str.contains(concept_filter, case=False, na=False)]
    st.dataframe(log_df, use_container_width=True, hide_index=True)


# ===================================================================
# PAGE: Prop Firm Tracker
# ===================================================================
elif page == "Prop Firm":
    st.header("🏛️ Prop Firm Tracker — Funding Pips")

    # Account settings — use MT5 data if connected
    st.subheader("Account Settings")
    ac1, ac2, ac3, ac4, ac5 = st.columns(5)
    _mt5_bal = mt5_account["balance"] if mt5_account else 10_000
    _mt5_eq = mt5_account["equity"] if mt5_account else 9_800
    starting_balance = ac1.number_input("Starting Balance ($)", value=int(_mt5_bal),
                                         step=500)
    current_balance = ac2.number_input("Current Balance ($)", value=int(_mt5_eq),
                                        step=50)
    max_total_dd = ac3.number_input("Max Total DD (%)", value=10.0, step=0.5)
    max_daily_loss = ac4.number_input("Max Daily Loss (%)", value=5.0, step=0.5)
    risk_per_trade = ac5.number_input("Risk per Trade (%)", value=1.0, step=0.25)

    if mt5_account:
        st.caption(f"💡 Balance/Equity auto-filled from MT5 (${mt5_account['balance']:,.2f} / ${mt5_account['equity']:,.2f})")

    # Account status
    st.markdown("---")
    st.subheader("Account Status")

    dd_floor = starting_balance * (1 - max_total_dd / 100)
    dd_buffer = current_balance - dd_floor
    dd_buffer_pct = (dd_buffer / starting_balance) * 100
    daily_limit = current_balance * (max_daily_loss / 100)

    s1, s2, s3, s4 = st.columns(4)
    s1.metric("Balance", f"${current_balance:,.0f}",
              delta=f"${current_balance - starting_balance:,.0f}")
    s2.metric("DD Floor", f"${dd_floor:,.0f}")
    s3.metric("DD Buffer Left", f"${dd_buffer:,.0f} ({dd_buffer_pct:.1f}%)")
    s4.metric("Daily Loss Limit", f"${daily_limit:,.0f}")

    if dd_buffer <= 0:
        st.error("⚠️ ACCOUNT BREACHED — Maximum drawdown hit!")
    elif dd_buffer_pct <= 2:
        st.error("🔴 CRITICAL — Less than 2% buffer. Stop trading!")
    elif dd_buffer_pct <= 4:
        st.warning("🟡 CAUTION — Buffer getting tight.")
    else:
        st.success("🟢 Account within safe limits.")

    # Position sizing
    st.markdown("---")
    st.subheader("Safe Position Sizing")
    lc1, lc2 = st.columns(2)
    sl_pips = lc1.number_input("Stop Loss (pips)", value=20.0, step=1.0)
    pip_value = lc2.number_input("Pip Value ($)", value=10.0, step=0.5,
                                  help="$10/pip for standard lot on XAUUSD")

    lot_info = safe_lot_size(current_balance, risk_per_trade / 100, sl_pips, pip_value)
    lm1, lm2, lm3, lm4 = st.columns(4)
    lm1.metric("Max Risk ($)", f"${lot_info['risk_dollar']:.2f}")
    lm2.metric("Lot Size", f"{lot_info['lot_size']:.2f}")
    lm3.metric("Micro Lots", f"{lot_info['micro_lots']}")
    max_losses = int(dd_buffer / lot_info['risk_dollar']) if lot_info['risk_dollar'] > 0 else 999
    lm4.metric("Max Consec. Losses", f"{max_losses}",
               help="Losses before breaching DD floor")

    # Backtest simulation
    st.markdown("---")
    st.subheader("Simulated Backtest with Prop Firm Rules")
    st.caption(
        f"Testing **{symbol}** {timeframe} with concepts: "
        f"**{', '.join(selected_concepts) or 'none'}**"
    )

    signals = load_signals(symbol, timeframe, concepts_key, rr, sweep_lookback)

    if signals.empty:
        st.info("No signals found. Try different settings.")
    else:
        sim_df = simulate_prop_account(
            signals,
            starting_balance=starting_balance,
            current_balance=current_balance,
            max_total_dd_pct=max_total_dd / 100,
            max_daily_loss_pct=max_daily_loss / 100,
            risk_per_trade_pct=risk_per_trade / 100,
        )

        summary = account_summary(
            sim_df,
            starting_balance=starting_balance,
            current_balance=current_balance,
            max_total_dd_pct=max_total_dd / 100,
            max_daily_loss_pct=max_daily_loss / 100,
        )

        sm1, sm2, sm3, sm4, sm5 = st.columns(5)
        sm1.metric("Sim Trades", summary["total_trades"])
        sm2.metric("Final Balance", f"${summary['final_equity']:,.0f}")
        sm3.metric("DD Buffer Left", f"${summary['remaining_dd_buffer']:,.0f}")
        sm4.metric("Max Consec. Losses", summary["consecutive_losses"])
        sm5.metric("Breached?", "YES ⛔" if summary["breached"] else "NO ✅")

        if summary["breached"]:
            st.error("⚠️ This strategy BREACHES the account in simulation! Reduce risk.")

        ch1, ch2 = st.columns(2)
        with ch1:
            st.plotly_chart(prop_equity_fig(sim_df, starting_balance, max_total_dd / 100),
                            use_container_width=True)
        with ch2:
            st.plotly_chart(daily_pnl_fig(sim_df, daily_limit),
                            use_container_width=True)

        st.plotly_chart(risk_gauge_fig(summary["remaining_dd_buffer"],
                                        starting_balance * max_total_dd / 100),
                        use_container_width=True)

        # Recommendations
        st.markdown("---")
        st.subheader("🤖 AI Risk Advisor")

        # Get backtest stats for AI recommendation
        bt_stats = compute_stats(signals)
        ai_rec = ai_risk_recommendation(
            bt_stats,
            balance=current_balance,
            max_dd_pct=max_total_dd,
        )

        r1, r2, r3, r4 = st.columns(4)
        r1.metric("Recommended Risk %", f"{ai_rec['recommended_risk_pct']}%",
                   help="AI-optimized using ½-Kelly + DD safety cap")
        r2.metric("Suggested Lot", f"{ai_rec['suggested_lot']}")
        r3.metric("Risk per Trade ($)", f"${ai_rec['risk_dollar']:.0f}")
        r4.metric("Confidence", ai_rec["confidence"])

        st.info(f"📊 **AI Analysis:** {ai_rec['reasoning']}")

        if ai_rec["confidence"] == "LOW":
            st.warning("⚠️ Low confidence — not enough trades or profit factor < 1.0. Use minimum risk.")
        elif ai_rec["confidence"] == "HIGH":
            st.success(f"✅ High confidence. Safe to use {ai_rec['recommended_risk_pct']}% risk per trade.")

        st.caption(
            f"Est. max consecutive losses: {ai_rec['est_consec_losses']} | "
            f"½-Kelly: {ai_rec['half_kelly_pct']}% | "
            f"DD-safe cap: {ai_rec['dd_safe_pct']}%"
        )

        st.markdown("---")
        st.subheader("Additional Recommendations")
        if summary["breached"]:
            st.markdown("❌ **Reduce risk per trade** — current settings breach in simulation.")
            if risk_per_trade > 0.5:
                st.markdown(f"💡 Try lowering risk to {max(0.25, risk_per_trade - 0.5):.2f}%.")
        if summary["consecutive_losses"] >= 3:
            st.markdown("⚠️ 3+ consecutive losses — add more concept filters.")
        if dd_buffer_pct <= 4:
            st.markdown("🔴 DD buffer tight. Use minimum sizes, A+ setups only.")
        if not summary["breached"] and dd_buffer_pct > 4:
            st.markdown("✅ Strategy looks safe under prop firm rules.")
            if lot_info['risk_dollar'] > 0:
                st.markdown(f"📊 Can sustain ~{max_losses} consecutive losses before breach.")


# ===================================================================
# PAGE: MT5 Auto-Trade
# ===================================================================
elif page == "MT5 Auto-Trade":
    st.header("🤖 MT5 Auto-Trade")

    if not _mt5_supported:
        st.error(_mt5_support_reason)
        st.info(
            "Use Streamlit Cloud for dashboard/monitoring, and run execution locally on your Windows machine "
            "using execution_worker.py + worker_watchdog.py."
        )
        st.code(".venv\\Scripts\\python.exe execution_worker.py", language="powershell")
        st.code(".venv\\Scripts\\python.exe worker_watchdog.py", language="powershell")
        st.stop()

    # ── Load saved credentials ───────────────────────────────────
    saved = load_credentials()
    is_connected = st.session_state.get("mt5_connected", False)

    if is_connected:
        # ── Connected: hide credentials, show account ────────────
        acc = get_account_info()
        if acc:
            _pnl = acc.get("profit", 0)
            _pnl_sign = "+" if _pnl >= 0 else ""
            _pnl_icon = "🟢" if _pnl >= 0 else "🔴"
            st.success(
                f"✅ Connected to **{acc.get('server', 'MT5')}** | "
                f"Account **{acc['login']}** | "
                f"Balance **${acc['balance']:,.2f}** | "
                f"Equity **${acc['equity']:,.2f}** | "
                f"Leverage **1:{acc['leverage']}** | "
                f"{_pnl_icon} PnL **{_pnl_sign}${_pnl:,.2f}**"
            )

        dc1, dc2 = st.columns([1, 5])
        with dc1:
            if st.button("🔌 Disconnect"):
                disconnect_mt5()
                st.session_state["mt5_connected"] = False
                st.session_state.pop("mt5_config", None)
                st.rerun()
        with dc2:
            with st.expander("Edit Credentials"):
                mt_col1, mt_col2, mt_col3 = st.columns(3)
                mt5_login = mt_col1.number_input(
                    "MT5 Login (Account #)",
                    value=saved["login"] if saved else 0,
                    step=1, format="%d", key="edit_login",
                )
                mt5_password = mt_col2.text_input(
                    "Password", type="password",
                    value=saved["password"] if saved else "",
                    key="edit_pass",
                )
                mt5_server = mt_col3.text_input(
                    "Server",
                    value=saved["server"] if saved else "",
                    key="edit_server",
                )
                sym_list = list(MT5_SYMBOL_MAP.values())
                saved_sym_idx = sym_list.index(saved["symbol"]) if saved and saved.get("symbol") in sym_list else 0
                mt5_symbol_edit = st.selectbox("MT5 Symbol", sym_list,
                                               index=saved_sym_idx, key="edit_sym")
                mt5_max_lot_edit = st.number_input("Max Lot", value=saved["max_lot"] if saved else 0.10,
                                                    step=0.01, min_value=0.01, key="edit_lot")
                mt5_max_spread_edit = st.number_input(
                    "Max Spread ($)",
                    value=float(saved.get("max_spread_price", 0.60)) if saved else 0.60,
                    step=0.05,
                    min_value=0.0,
                    key="edit_spread",
                )
                mt5_max_drift_edit = st.number_input(
                    "Max Entry Drift ($)",
                    value=float(saved.get("max_entry_drift_price", 2.00)) if saved else 2.00,
                    step=0.10,
                    min_value=0.0,
                    key="edit_drift",
                )
                sl_c1, sl_c2, sl_c3 = st.columns(3)
                mt5_min_sl_pips_edit = sl_c1.number_input(
                    "Min SL Distance (pips)",
                    value=float(saved.get("min_stop_distance_pips", 2.0)) if saved else 2.0,
                    step=0.5,
                    min_value=0.0,
                    key="edit_min_sl_pips",
                    help="Reject trade if SL would be tighter than this many pips.",
                )
                mt5_max_sl_pips_edit = sl_c2.number_input(
                    "Max SL Distance (pips)",
                    value=float(saved.get("max_stop_distance_pips", 200.0)) if saved else 200.0,
                    step=5.0,
                    min_value=0.0,
                    key="edit_max_sl_pips",
                    help="Reject trade if SL would be wider than this many pips.",
                )
                mt5_min_rr_edit = sl_c3.number_input(
                    "Min TP/SL Ratio",
                    value=float(saved.get("min_rr_ratio", 1.5)) if saved else 1.5,
                    step=0.1,
                    min_value=0.0,
                    key="edit_min_rr",
                    help="Reject trade if TP distance is less than this multiple of SL distance.",
                )
                mt5_max_trades_day_edit = st.number_input(
                    "Max Trades / Day",
                    value=int(saved.get("max_trades_per_day", 8)) if saved else 8,
                    step=1,
                    min_value=1,
                    key="edit_max_day",
                )
                mt5_max_open_pos_edit = st.number_input(
                    "Max Open Positions",
                    value=int(saved.get("max_open_positions", 2)) if saved else 2,
                    step=1,
                    min_value=1,
                    key="edit_max_open",
                )
                mt5_session_enforce_edit = st.checkbox(
                    "Enforce Session Window (UTC)",
                    value=bool(saved.get("enforce_session_window", False)) if saved else False,
                    key="edit_session_enforce",
                )
                es1, es2 = st.columns(2)
                mt5_session_start_edit = es1.number_input(
                    "Session Start UTC",
                    value=int(saved.get("session_start_utc", 0)) if saved else 0,
                    step=1,
                    min_value=0,
                    max_value=23,
                    key="edit_session_start",
                )
                mt5_session_end_edit = es2.number_input(
                    "Session End UTC",
                    value=int(saved.get("session_end_utc", 23)) if saved else 23,
                    step=1,
                    min_value=0,
                    max_value=23,
                    key="edit_session_end",
                )
                if st.button("💾 Save & Reconnect"):
                    save_credentials(mt5_login, mt5_password, mt5_server,
                                     mt5_symbol_edit, mt5_max_lot_edit,
                                     mt5_max_spread_edit, mt5_max_drift_edit,
                                     int(mt5_max_trades_day_edit), int(mt5_max_open_pos_edit),
                                     bool(mt5_session_enforce_edit),
                                     int(mt5_session_start_edit), int(mt5_session_end_edit),
                                     float(mt5_min_sl_pips_edit), float(mt5_max_sl_pips_edit),
                                     float(mt5_min_rr_edit))
                    disconnect_mt5()
                    new_cfg = MT5Config(login=int(mt5_login), password=mt5_password,
                                        server=mt5_server, symbol=mt5_symbol_edit,
                                        max_lot=mt5_max_lot_edit,
                                        max_spread_price=mt5_max_spread_edit,
                                        max_entry_drift_price=mt5_max_drift_edit,
                                        max_trades_per_day=int(mt5_max_trades_day_edit),
                                        max_open_positions=int(mt5_max_open_pos_edit),
                                        enforce_session_window=bool(mt5_session_enforce_edit),
                                        session_start_utc=int(mt5_session_start_edit),
                                        session_end_utc=int(mt5_session_end_edit),
                                        min_stop_distance_pips=float(mt5_min_sl_pips_edit),
                                        max_stop_distance_pips=float(mt5_max_sl_pips_edit),
                                        min_rr_ratio=float(mt5_min_rr_edit))
                    ok, msg = connect_mt5(new_cfg)
                    if ok:
                        st.session_state["mt5_connected"] = True
                        st.session_state["mt5_config"] = new_cfg
                        st.success(f"Reconnected! {msg}")
                        st.rerun()
                    else:
                        st.error(msg)

        # Use stored config
        config = st.session_state.get("mt5_config", MT5Config())
        mt5_symbol = config.symbol
        mt5_max_lot = config.max_lot

        # ── Execution Guardrails ────────────────────────────────
        st.markdown("---")
        st.subheader("Execution Guardrails")
        gc1, gc2, gc3 = st.columns(3)
        config.max_spread_price = gc1.number_input(
            "Max Spread ($)",
            value=float(getattr(config, "max_spread_price", 0.60)),
            step=0.05,
            min_value=0.0,
            help="Blocks new orders if bid/ask spread is above this threshold.",
        )
        config.max_entry_drift_price = gc2.number_input(
            "Max Entry Drift ($)",
            value=float(getattr(config, "max_entry_drift_price", 2.00)),
            step=0.10,
            min_value=0.0,
            help="Blocks new orders if live market price is too far from signal entry.",
        )
        config.kill_switch = gc3.checkbox(
            "Kill-switch",
            value=bool(st.session_state.get("mt5_kill_switch", getattr(config, "kill_switch", False))),
            help="Immediately blocks any new trade execution while ON.",
        )
        st.session_state["mt5_kill_switch"] = config.kill_switch
        st.session_state["mt5_config"] = config
        if config.kill_switch:
            st.error("Kill-switch is ON: all new trade entries are blocked.")

        sg1, sg2, sg3 = st.columns(3)
        config.min_stop_distance_pips = sg1.number_input(
            "Min SL Distance (pips)",
            value=float(getattr(config, "min_stop_distance_pips", 2.0)),
            step=0.5,
            min_value=0.0,
            help="Reject trade if SL distance is tighter than this many pips.",
        )
        config.max_stop_distance_pips = sg2.number_input(
            "Max SL Distance (pips)",
            value=float(getattr(config, "max_stop_distance_pips", 200.0)),
            step=5.0,
            min_value=0.0,
            help="Reject trade if SL distance is wider than this many pips.",
        )
        config.min_rr_ratio = sg3.number_input(
            "Min TP/SL Ratio",
            value=float(getattr(config, "min_rr_ratio", 1.5)),
            step=0.1,
            min_value=0.0,
            help="Reject trade if TP/SL ratio is below this threshold.",
        )
        st.session_state["mt5_config"] = config

        pp1, pp2 = st.columns([2, 1])
        selected_profile = pp1.selectbox(
            "Policy Profile",
            options=list(POLICY_PROFILES.keys()),
            index=1,
            help="Quick preset for execution guardrails and policy limits.",
        )
        if pp2.button("Apply Profile"):
            profile = POLICY_PROFILES[selected_profile]
            config.max_spread_price = profile["max_spread_price"]
            config.max_entry_drift_price = profile["max_entry_drift_price"]
            config.max_trades_per_day = profile["max_trades_per_day"]
            config.max_open_positions = profile["max_open_positions"]
            config.enforce_session_window = profile["enforce_session_window"]
            config.session_start_utc = profile["session_start_utc"]
            config.session_end_utc = profile["session_end_utc"]
            st.session_state["mt5_config"] = config
            st.success(f"Applied {selected_profile} profile.")
            st.rerun()

        st.subheader("Execution Policy")
        pc1, pc2 = st.columns(2)
        config.max_trades_per_day = int(pc1.number_input(
            "Max Trades / Day",
            value=int(getattr(config, "max_trades_per_day", 8)),
            step=1,
            min_value=1,
            help="Blocks new entries after this many FILLED trades today.",
        ))
        config.max_open_positions = int(pc2.number_input(
            "Max Open Positions",
            value=int(getattr(config, "max_open_positions", 2)),
            step=1,
            min_value=1,
            help="Blocks new entries when symbol open positions reach this limit.",
        ))
        config.enforce_session_window = st.checkbox(
            "Enforce Session Window (UTC)",
            value=bool(getattr(config, "enforce_session_window", False)),
            help="Only allow new entries during configured UTC hours.",
        )
        ps1, ps2 = st.columns(2)
        config.session_start_utc = int(ps1.number_input(
            "Session Start UTC",
            value=int(getattr(config, "session_start_utc", 0)),
            step=1,
            min_value=0,
            max_value=23,
        ))
        config.session_end_utc = int(ps2.number_input(
            "Session End UTC",
            value=int(getattr(config, "session_end_utc", 23)),
            step=1,
            min_value=0,
            max_value=23,
        ))
        st.session_state["mt5_config"] = config

        # ── MT5 Execution Profile (persistent across refresh) ───
        worker_cfg_boot = load_worker_config()
        if "mt5_exec_profile_initialized" not in st.session_state:
            boot_style = str(worker_cfg_boot.get("trading_mode", trading_mode))
            if boot_style not in TRADING_MODES:
                boot_style = trading_mode
            boot_mode_cfg = TRADING_MODES[boot_style]

            boot_symbol = str(worker_cfg_boot.get("symbol", symbol))
            if boot_symbol not in INSTRUMENTS:
                boot_symbol = symbol

            boot_tf = str(worker_cfg_boot.get("timeframe", boot_mode_cfg.get("default_tf", timeframe)))
            if boot_tf not in boot_mode_cfg["timeframes"]:
                boot_tf = boot_mode_cfg["default_tf"]

            boot_concepts = worker_cfg_boot.get("concepts", selected_concepts)
            if not isinstance(boot_concepts, list):
                boot_concepts = selected_concepts
            boot_concepts = [c for c in boot_concepts if c in ALL_CONCEPTS]
            if not boot_concepts:
                boot_concepts = boot_mode_cfg.get("recommended_concepts", selected_concepts)

            st.session_state["mt5_exec_style"] = boot_style
            st.session_state["mt5_exec_symbol"] = boot_symbol
            st.session_state["mt5_exec_timeframe"] = boot_tf
            st.session_state["mt5_exec_rr"] = float(worker_cfg_boot.get("rr", mode_cfg.get("default_rr", rr)))
            st.session_state["mt5_exec_sweep"] = int(worker_cfg_boot.get("sweep_lookback", mode_cfg.get("sweep_lookback", sweep_lookback)))
            st.session_state["mt5_exec_concepts"] = boot_concepts
            st.session_state["mt5_exec_profile_initialized"] = True

        st.markdown("---")
        st.subheader("MT5 Execution Profile (Manual / Persistent)")
        st.caption("These execution settings stay fixed across refreshes until you change them manually.")

        ep1, ep2, ep3 = st.columns(3)
        mt5_exec_style = ep1.selectbox(
            "Execution Style",
            list(TRADING_MODES.keys()),
            key="mt5_exec_style",
        )
        mt5_exec_symbol = ep2.selectbox(
            "Execution Symbol",
            list(INSTRUMENTS.keys()),
            key="mt5_exec_symbol",
        )
        exec_mode_cfg = TRADING_MODES[mt5_exec_style]
        if st.session_state.get("mt5_exec_timeframe") not in exec_mode_cfg["timeframes"]:
            st.session_state["mt5_exec_timeframe"] = exec_mode_cfg["default_tf"]
        mt5_exec_timeframe = ep3.selectbox(
            "Execution Timeframe",
            exec_mode_cfg["timeframes"],
            key="mt5_exec_timeframe",
        )

        ep4, ep5 = st.columns(2)
        mt5_exec_rr = ep4.slider(
            "Execution R:R",
            min_value=1.0,
            max_value=5.0,
            step=0.5,
            key="mt5_exec_rr",
        )
        mt5_exec_sweep = ep5.slider(
            "Execution Sweep Lookback",
            min_value=3,
            max_value=60,
            step=1,
            key="mt5_exec_sweep",
        )

        if "mt5_exec_concepts" not in st.session_state:
            st.session_state["mt5_exec_concepts"] = exec_mode_cfg.get("recommended_concepts", selected_concepts)

        mt5_exec_concepts = st.multiselect(
            "Execution Concepts",
            options=ALL_CONCEPTS,
            key="mt5_exec_concepts",
            help="Only these concepts are used for MT5 live signal generation.",
        )
        if not mt5_exec_concepts:
            mt5_exec_concepts = exec_mode_cfg.get("recommended_concepts", selected_concepts)

        mt5_exec_concepts_key = "|".join(sorted(mt5_exec_concepts))

        st.markdown("---")
        st.subheader("Background Worker (Recommended)")
        worker_cfg = load_worker_config()
        wc1, wc2, wc3 = st.columns(3)
        worker_enabled = wc1.checkbox(
            "Enable Worker Mode",
            value=bool(worker_cfg.get("enabled", False)),
            help="When enabled, execution should run from execution_worker.py, not Streamlit reruns.",
        )
        worker_auto_trade = wc2.checkbox(
            "Worker Auto-Trade",
            value=bool(worker_cfg.get("auto_trade_enabled", True)),
        )
        worker_poll = wc3.number_input(
            "Worker Poll (sec)",
            value=int(worker_cfg.get("poll_seconds", 5)),
            min_value=2,
            max_value=60,
            step=1,
        )
        ww1, ww2 = st.columns(2)
        worker_bars = ww1.number_input(
            "Worker Bars Window",
            value=int(worker_cfg.get("bars_window", 500)),
            min_value=200,
            max_value=3000,
            step=50,
        )
        worker_lot = ww2.number_input(
            "Worker Lot Size",
            value=float(worker_cfg.get("lot_size", exec_mode_cfg.get("default_lot", 0.01))),
            min_value=0.01,
            max_value=float(mt5_max_lot),
            step=0.01,
        )
        wq1, wq2 = st.columns(2)
        worker_min_quality = wq1.slider(
            "Worker Min Quality",
            min_value=40,
            max_value=95,
            value=int(worker_cfg.get("min_quality_score", 68)),
            step=1,
        )
        worker_max_age = wq2.slider(
            "Worker Max Signal Age (bars)",
            min_value=1.0,
            max_value=6.0,
            value=float(worker_cfg.get("max_signal_age_bars", 2.0)),
            step=0.5,
        )

        if st.button("💾 Save Worker Config"):
            new_worker_cfg = {
                "enabled": bool(worker_enabled),
                "auto_trade_enabled": bool(worker_auto_trade),
                "trading_mode": mt5_exec_style,
                "symbol": mt5_exec_symbol,
                "timeframe": mt5_exec_timeframe,
                "concepts": mt5_exec_concepts,
                "rr": float(mt5_exec_rr),
                "sweep_lookback": int(mt5_exec_sweep),
                "lot_size": float(worker_lot),
                "min_quality_score": float(worker_min_quality),
                "max_signal_age_bars": float(worker_max_age),
                "poll_seconds": int(worker_poll),
                "bars_window": int(worker_bars),
            }
            save_worker_config(new_worker_cfg)
            st.success("Worker config saved.")

        st.code(".venv\\Scripts\\python.exe execution_worker.py", language="powershell")
        hb = load_worker_heartbeat()
        if hb and hb.get("timestamp"):
            try:
                hb_dt = datetime.fromisoformat(hb["timestamp"]).replace(tzinfo=timezone.utc)
                age = (datetime.now(timezone.utc) - hb_dt).total_seconds()
                stale_after = max(int(worker_poll) * 3, 30)
                msg = (
                    f"Worker heartbeat: {hb.get('status', 'unknown')} | "
                    f"{hb.get('detail', '')} | age {age:.0f}s"
                )
                if age > stale_after:
                    st.error(f"{msg} | STALE (>{stale_after}s). Check worker process.")
                elif hb.get("status") in {"error", "failed"}:
                    st.warning(msg)
                else:
                    st.caption(msg)
            except Exception:
                st.caption(f"Worker heartbeat: {hb.get('status', 'unknown')} | {hb.get('detail', '')}")
        else:
            st.caption("No worker heartbeat yet. Start worker from terminal using the command above.")

        st.code(".\\start_watchdog.ps1", language="powershell")
        wdhb = load_watchdog_heartbeat()
        if wdhb and wdhb.get("timestamp"):
            try:
                wd_dt = datetime.fromisoformat(wdhb["timestamp"])
                if wd_dt.tzinfo is None:
                    wd_dt = wd_dt.replace(tzinfo=timezone.utc)
                wd_age = (datetime.now(timezone.utc) - wd_dt).total_seconds()
                st.caption(
                    f"Watchdog: {wdhb.get('status', 'unknown')} | "
                    f"{wdhb.get('detail', '')} | age {wd_age:.0f}s"
                )
            except Exception:
                st.caption(f"Watchdog: {wdhb.get('status', 'unknown')} | {wdhb.get('detail', '')}")
        else:
            st.caption("No watchdog heartbeat yet. Start with .\\start_watchdog.ps1")

        st.caption("Auto-start on reboot (Task Scheduler):")
        st.code(".\\install_scheduled_tasks.ps1", language="powershell")
        st.caption("Remove auto-start tasks:")
        st.code(".\\uninstall_scheduled_tasks.ps1", language="powershell")

        st.markdown("---")
        st.subheader("Alerting (Webhook)")
        alert_cfg = load_alert_config()
        al1, al2 = st.columns([1, 2])
        alert_enabled = al1.checkbox(
            "Enable Alerts",
            value=bool(alert_cfg.get("enabled", False)),
            help="Send worker/watchdog alerts to your webhook URL.",
        )
        cooldown_sec = al2.number_input(
            "Alert Cooldown (sec)",
            value=int(alert_cfg.get("cooldown_seconds", 120)),
            min_value=10,
            max_value=3600,
            step=10,
        )
        webhook_url = st.text_input(
            "Webhook URL",
            value=str(alert_cfg.get("webhook_url", "")),
            placeholder="https://your-webhook-endpoint",
        )
        af1, af2, af3 = st.columns(3)
        notify_worker_error = af1.checkbox(
            "Notify Worker Errors",
            value=bool(alert_cfg.get("notify_on_worker_error", True)),
        )
        notify_worker_failed = af2.checkbox(
            "Notify Trade Failures",
            value=bool(alert_cfg.get("notify_on_worker_failed", True)),
        )
        notify_watchdog_restart = af3.checkbox(
            "Notify Watchdog Restarts",
            value=bool(alert_cfg.get("notify_on_watchdog_restart", True)),
        )

        aa1, aa2 = st.columns(2)
        if aa1.button("💾 Save Alert Config"):
            save_alert_config({
                "enabled": bool(alert_enabled),
                "webhook_url": str(webhook_url).strip(),
                "notify_on_worker_error": bool(notify_worker_error),
                "notify_on_worker_failed": bool(notify_worker_failed),
                "notify_on_watchdog_restart": bool(notify_watchdog_restart),
                "cooldown_seconds": int(cooldown_sec),
            })
            st.success("Alert configuration saved.")

        if aa2.button("🧪 Send Test Alert"):
            ok = send_webhook_alert(
                event="manual_test",
                severity="info",
                message="Sacred Soul test alert from MT5 page.",
                metadata={"source": "streamlit_mt5_page"},
            )
            if ok:
                st.success("Test alert sent successfully.")
            else:
                st.warning("Test alert not sent. Check enabled toggle, webhook URL, or cooldown.")

        # ── Live Price ───────────────────────────────────────────
        st.markdown("---")
        live = get_live_price(mt5_symbol)
        if live:
            pr1, pr2, pr3, pr4 = st.columns(4)
            pr1.metric("Bid", f"{live['bid']:.2f}")
            pr2.metric("Ask", f"{live['ask']:.2f}")
            spread_pts = (live["ask"] - live["bid"])
            pr3.metric("Spread", f"{spread_pts:.2f}")
            pr4.metric("Tick Time", live["time"][-8:])
        if mt5_ultra_fast_mode:
            st.caption("Lean MT5 UI active: heavy tables/charts are minimized for ultra-fast refresh.")

        st.markdown("---")
        st.subheader("Execution Test (Dry Run)")
        st.caption("Validates the MT5 order path without placing a real trade.")
        test_col1, test_col2 = st.columns([1, 3])
        test_lot = test_col1.number_input(
            "Test Lot",
            value=0.01,
            min_value=0.01,
            max_value=float(mt5_max_lot),
            step=0.01,
            key="dry_run_test_lot",
        )
        test_col2.caption(
            "Test LONG uses live ask as entry with a safe preview-only SL/TP distance to surface broker/runtime errors."
        )
        if st.button("🧪 Test LONG Order (Dry Run)", type="secondary"):
            if not live:
                st.error("No live price available for dry-run test.")
            else:
                test_entry = float(live["ask"])
                test_sl = test_entry - 10.0
                test_tp = test_entry + 15.0
                test_result = preview_trade_execution(
                    config,
                    direction="LONG",
                    entry_price=test_entry,
                    sl_price=test_sl,
                    tp_price=test_tp,
                    lot_size=float(test_lot),
                    comment="Sacred Soul Dry Run LONG",
                )
                if test_result.success:
                    st.success(test_result.message)
                else:
                    st.error(test_result.message)

        # ── Open Positions with Real-Time PnL ────────────────────
        st.subheader("Open Positions")
        positions = get_open_positions(mt5_symbol)
        if positions:
            pos_df = pd.DataFrame(positions)

            # Real-time PnL summary
            total_pnl = pos_df["profit"].sum()
            total_swap = pos_df["swap"].sum()
            net_pnl = total_pnl + total_swap
            pnl_color = "green" if net_pnl >= 0 else "red"
            pn1, pn2, pn3, pn4 = st.columns(4)
            pn1.metric("Open Trades", len(positions))
            pn2.metric("Floating PnL", f"${total_pnl:,.2f}",
                        delta=f"{'+'if total_pnl>=0 else ''}{total_pnl:,.2f}")
            pn3.metric("Swap", f"${total_swap:,.2f}")
            pn4.metric("Net PnL", f"${net_pnl:,.2f}",
                        delta=f"{'+'if net_pnl>=0 else ''}{net_pnl:,.2f}")

            if not mt5_ultra_fast_mode:
                st.dataframe(pos_df, use_container_width=True, hide_index=True)
            else:
                st.caption("Open positions table hidden in lean mode.")

            ticket_to_close = st.number_input(
                "Ticket # to close", value=0, step=1, format="%d",
            )
            if st.button("🔴 Close Position") and ticket_to_close > 0:
                result = close_position(ticket_to_close)
                if result.success:
                    st.success(result.message)
                else:
                    st.error(result.message)
        else:
            st.info("No open positions.")

        # ── Trade Size (manual by default, AI on demand) ─────────
        st.markdown("---")
        st.subheader("Trade Size")

        _def_lot = exec_mode_cfg.get("default_lot", 0.01)
        trade_lot = st.number_input(
            "Lot Size",
            value=min(_def_lot, mt5_max_lot),
            step=0.01,
            min_value=0.01,
            max_value=mt5_max_lot,
        )
        st.caption("Default is mode-based. Manual lot is fastest for auto-refresh execution.")

        # Keep AI sizing available, but compute only on demand (not every refresh).
        ai_key = (
            f"ai_rec_{mt5_exec_symbol}_{mt5_exec_timeframe}_{mt5_exec_style}_"
            f"{mt5_exec_concepts_key}_{mt5_exec_rr}_{mt5_exec_sweep}"
        )
        if st.button("🧠 Recalculate AI Lot (On Demand)"):
            bt_signals = load_signals(
                mt5_exec_symbol,
                mt5_exec_timeframe,
                mt5_exec_concepts_key,
                float(mt5_exec_rr),
                int(mt5_exec_sweep),
            )
            if bt_signals.empty:
                st.warning("No backtest signals available for AI lot sizing.")
            else:
                bt_stats = compute_stats(bt_signals)
                _mt5_bal = acc["balance"] if acc else exec_mode_cfg.get("default_balance", 10_000)
                st.session_state[ai_key] = ai_risk_recommendation(bt_stats, balance=_mt5_bal)

        ai_rec = st.session_state.get(ai_key)
        if ai_rec:
            ar1, ar2, ar3, ar4 = st.columns(4)
            ar1.metric("AI Risk %", f"{ai_rec['recommended_risk_pct']}%")
            ar2.metric("AI Lot Size", f"{ai_rec['suggested_lot']}")
            ar3.metric("Risk $", f"${ai_rec['risk_dollar']:.0f}")
            ar4.metric("Confidence", ai_rec["confidence"])
            st.caption(f"📊 {ai_rec['reasoning']}")

            if st.checkbox("Use cached AI-recommended lot", value=False):
                trade_lot = min(ai_rec["suggested_lot"], mt5_max_lot)
                st.info(f"Using cached AI lot: **{trade_lot}**")

        # ── Signal-Based Trading (live-only execution flow) ─────
        st.markdown("---")
        st.subheader(f"Live Signal Monitor — {mt5_exec_symbol} {mt5_exec_timeframe} ({mt5_exec_style})")

        q1, q2 = st.columns(2)
        ui_min_quality = q1.slider(
            "Min Signal Quality",
            min_value=40,
            max_value=95,
            value=68,
            step=1,
            help="Higher values reduce trade frequency and target higher-confluence setups.",
        )
        ui_max_age_bars = q2.slider(
            "Max Signal Age (bars)",
            min_value=1.0,
            max_value=6.0,
            value=2.0,
            step=0.5,
            help="Ignore stale signals older than this many bars.",
        )

        scan_cycle = int(refresh_count) if effective_auto_refresh else 0
        phase_text = scanner_phase_label(scan_cycle)
        stage_progress = ((scan_cycle % 6) + 1) / 6.0
        tape = scanner_stream_tape(scan_cycle)

        st.markdown(
            (
                "<div class='scanner-shell'>"
                f"<div class='scanner-head'>Digital Scanner // Cycle {scan_cycle + 1}</div>"
                f"<div class='scanner-tape'>{tape}</div>"
                "<div class='status-chip-row'>"
                f"<span class='status-chip'>PHASE: {phase_text.upper()}</span>"
                f"<span class='status-chip'>SYMBOL: {mt5_exec_symbol}</span>"
                f"<span class='status-chip'>TF: {mt5_exec_timeframe}</span>"
                "</div>"
                "</div>"
            ),
            unsafe_allow_html=True,
        )

        with st.status(f"Digital Scanner: {phase_text}", expanded=False) as scanner_box:
            st.progress(stage_progress, text=f"Cycle {scan_cycle + 1}: {phase_text}")
            live_signals = load_live_signals(
                mt5_exec_symbol,
                mt5_exec_timeframe,
                mt5_exec_concepts_key,
                float(mt5_exec_rr),
                int(mt5_exec_sweep),
            )
            scanner_box.update(label="Digital Scanner: scan complete", state="complete")

        reason = "No live signals in window"
        if live_signals.empty:
            st.info("No fresh signals in the live window.")
            latest_sig = None
            ranked_live = live_signals
        else:
            # Use live signal timestamps as reference to avoid extra data fetch during refresh.
            reference_ts = live_signals["signal_time"].max()
            ranked_live, latest_sig, reason = rank_live_signals(
                live_signals,
                mt5_exec_timeframe,
                reference_ts,
                min_quality=float(ui_min_quality),
                max_signal_age_bars=float(ui_max_age_bars),
            )

            ranked_live, drift_sig, drift_reason = filter_ranked_signals_by_entry_drift(
                ranked_live,
                live,
                float(getattr(config, "max_entry_drift_price", 0.0)),
            )
            if drift_sig is not None:
                latest_sig = drift_sig
            elif reason == "OK" and drift_reason:
                latest_sig = None
                reason = drift_reason

            if reason != "OK":
                st.warning(reason)

            recent_live = ranked_live.head(5).copy()
            drift_cols = ["entry_drift"] if "entry_drift" in recent_live.columns else []
            if not mt5_ultra_fast_mode:
                st.dataframe(
                    recent_live[["signal_time", "direction", "entry", "sl", "tp",
                                 "concepts_used", "status", "result", "quality_score", "age_bars"] + drift_cols],
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.caption("Recent signals table hidden in lean mode.")

        market_cond = build_market_condition_summary(
            ranked_live,
            latest_sig,
            live,
            reason,
            spread_limit=float(getattr(config, "max_spread_price", 0.0)),
            min_quality=float(ui_min_quality),
        )
        st.markdown("#### Market Condition Analysis")
        mc1, mc2, mc3, mc4, mc5, mc6 = st.columns(6)
        mc1.metric("Regime", market_cond["regime"])
        mc2.metric("Directional Bias", market_cond["bias"])
        mc3.metric("Conviction", market_cond["conviction"])
        mc4.metric("Structure", market_cond["structure"])
        mc5.metric("Execution Risk", market_cond["execution_risk"])
        mc6.metric("Market Phase", market_cond["market_phase"])

        risk_class = "risk-low"
        if str(market_cond["execution_risk"]).lower() == "high":
            risk_class = "risk-high"
        elif str(market_cond["execution_risk"]).lower() == "medium":
            risk_class = "risk-medium"

        if market_cond["spread_util_pct"] is None:
            risk_text = "Spread utilization: n/a"
        else:
            risk_text = f"Spread utilization: {float(market_cond['spread_util_pct']):.0f}% of limit"
        st.markdown(
            f"<div class='risk-badge-row'><span class='risk-badge {risk_class}'>{risk_text}</span></div>",
            unsafe_allow_html=True,
        )

        trace_key = f"regime_trace_{mt5_exec_symbol}_{mt5_exec_timeframe}"
        trace = st.session_state.get(trace_key, [])
        trace.append(float(market_cond["regime_score"]))
        trace = trace[-10:]
        st.session_state[trace_key] = trace

        if not mt5_ultra_fast_mode:
            st.caption("Regime score trend (last 10 scan cycles)")
            st.line_chart(pd.DataFrame({"Regime Score": trace}), use_container_width=True, height=120)
        if market_cond["spread"] is None:
            st.caption("Live spread: n/a")
        else:
            st.caption(f"Live spread: {float(market_cond['spread']):.2f}")
        st.caption(market_cond["headline"])

        worker_lock = False
        worker_lock_msg = ""
        if worker_enabled:
            worker_lock = True
            worker_lock_msg = "Worker mode is enabled and appears active. In-app auto-trade is locked to avoid duplicate orders."
            if hb and hb.get("timestamp"):
                try:
                    hb_dt = datetime.fromisoformat(hb["timestamp"])
                    if hb_dt.tzinfo is None:
                        hb_dt = hb_dt.replace(tzinfo=timezone.utc)
                    hb_age = (datetime.now(timezone.utc) - hb_dt).total_seconds()
                    stale_after = max(int(worker_poll) * 3, 30)
                    if hb_age > stale_after or str(hb.get("status", "")).lower() in {"error", "failed"}:
                        worker_lock = False
                        worker_lock_msg = (
                            "Worker mode is ON but heartbeat is stale/error. "
                            "In-app auto-trade is temporarily unlocked as fallback."
                        )
                except Exception:
                    worker_lock = False
                    worker_lock_msg = "Worker heartbeat time is unreadable. In-app auto-trade is temporarily unlocked as fallback."
            else:
                worker_lock = False
                worker_lock_msg = "Worker mode is ON but no heartbeat is present. In-app auto-trade is temporarily unlocked as fallback."

        auto_trade_enabled = st.checkbox(
            "⚡ Enable Auto-Trade on Fresh Signals",
            value=not worker_lock,
            disabled=worker_lock,
            help="Executes only recent OPEN signals in the live window; ignores old historical setups.",
        )
        if worker_enabled:
            if worker_lock:
                st.info(worker_lock_msg)
            else:
                st.warning(worker_lock_msg)
        if auto_trade_enabled and not effective_auto_refresh:
            st.info("Enable Auto-Refresh in the sidebar so fresh signals are checked automatically.")

        if latest_sig is not None:
            price_info = ""
            if live:
                cur_price = live["ask"] if latest_sig["direction"] == "LONG" else live["bid"]
                diff = abs(cur_price - latest_sig["entry"])
                drift_cap = float(getattr(config, "max_entry_drift_price", 0.0))
                if drift_cap > 0:
                    price_info = f" | **Live:** {cur_price:.2f} (Δ {diff:.2f}/{drift_cap:.2f})"
                else:
                    price_info = f" | **Live:** {cur_price:.2f} (Δ {diff:.2f})"

            st.markdown(
                f"**Fresh Signal:** {latest_sig['direction']} @ "
                f"{latest_sig['entry']:.2f} | SL: {latest_sig['sl']:.2f} | "
                f"TP: {latest_sig['tp']:.2f} | "
                f"Quality: {latest_sig.get('quality_score', 0):.1f} | "
                f"Concepts: {latest_sig['concepts_used']}"
                f"{price_info}"
            )

            if st.button("🟢 Execute Fresh Signal", type="primary"):
                result = execute_trade(
                    config,
                    direction=latest_sig["direction"],
                    entry_price=latest_sig["entry"],
                    sl_price=latest_sig["sl"],
                    tp_price=latest_sig["tp"],
                    lot_size=trade_lot,
                    comment=f"ICT {mt5_exec_style}",
                )
                if result.success:
                    st.success(f"✅ Trade executed! {result.message}")
                else:
                    st.error(f"❌ Trade failed: {result.message}")

            if auto_trade_enabled:
                sig_key = (
                    f"executed_{mt5_exec_symbol}_{mt5_exec_timeframe}_{latest_sig['signal_time']}_"
                    f"{latest_sig['direction']}_{round(latest_sig['entry'], 2)}"
                )
                if sig_key not in st.session_state:
                    result = execute_trade(
                        config,
                        direction=latest_sig["direction"],
                        entry_price=latest_sig["entry"],
                        sl_price=latest_sig["sl"],
                        tp_price=latest_sig["tp"],
                        lot_size=trade_lot,
                        comment=f"ICT Auto {mt5_exec_style}",
                    )
                    st.session_state[sig_key] = True
                    if result.success:
                        st.success(f"🤖 Auto-trade executed! {result.message}")
                    else:
                        st.error(f"🤖 Auto-trade failed: {result.message}")
        else:
            if isinstance(reason, str) and reason:
                st.info(reason)
            else:
                st.info("No fresh OPEN signal right now.")

        # ── Trade Log / Audit ───────────────────────────────────
        st.markdown("---")
        st.subheader("Execution Audit")
        log_entries = trade_log.to_list()
        if log_entries:
            st.caption("Session log (current runtime)")
            if not mt5_ultra_fast_mode:
                st.dataframe(pd.DataFrame(log_entries), use_container_width=True,
                             hide_index=True)
            else:
                st.caption(f"Session log entries: {len(log_entries)} (table hidden in lean mode)")
        else:
            st.info("No trades executed in this session.")

        ops_skip_fast_cycle = (
            effective_auto_refresh
            and effective_refresh_interval <= 3
            and int(refresh_count) % 3 != 0
        )

        audit_entries = [] if ops_skip_fast_cycle else load_audit_log(limit=200)
        if ops_skip_fast_cycle:
            st.caption("Execution Ops refresh throttled (updates every 3 cycles in fast mode).")
        if audit_entries and not ops_skip_fast_cycle:
            st.markdown("---")
            st.subheader("Execution Ops (Last 24h)")
            ops = summarize_audit_events(audit_entries, hours=24)
            oc1, oc2, oc3, oc4, oc5, oc6, oc7 = st.columns(7)
            oc1.metric("Events", ops["window_events"])
            oc2.metric("Filled", ops["filled"])
            oc3.metric("Failed", ops["failed"])
            oc4.metric("Blocked", ops["blocked"])
            oc5.metric("Fill Rate", f"{ops['fill_rate']}%")
            oc6.metric("Avg Broker ms", f"{ops['avg_response_ms']}")
            oc7.metric("P95 Broker ms", f"{ops['p95_response_ms']}")

            trend_df = status_trend_dataframe(audit_entries, hours=24)
            if not trend_df.empty and not mt5_ultra_fast_mode:
                st.markdown("#### Status Trend (Hourly, 24h)")
                st.line_chart(trend_df)

            last_try = last_execution_attempt(audit_entries)
            if last_try:
                st.markdown("#### Last Execution Attempt")
                lc1, lc2, lc3, lc4 = st.columns(4)
                lc1.metric("Status", str(last_try.get("status", "UNKNOWN")))
                lc2.metric("Symbol", str(last_try.get("symbol", "-")))
                lc3.metric("Direction", str(last_try.get("direction", "-")))
                lc4.metric("Time", str(last_try.get("timestamp", "-")[-8:]))
                st.caption(str(last_try.get("reason", last_try.get("message", "No details"))))

            reason_df = summarize_rejection_reasons(audit_entries, hours=24)
            if not reason_df.empty and not mt5_ultra_fast_mode:
                st.markdown("#### Rejection Reason Breakdown (24h)")
                st.dataframe(reason_df.head(10), use_container_width=True, hide_index=True)

            if not mt5_ultra_fast_mode:
                st.caption("Persistent audit log (last 200 events)")
                st.dataframe(pd.DataFrame(audit_entries), use_container_width=True,
                             hide_index=True)
            else:
                st.caption(f"Persistent audit events: {len(audit_entries)} (table hidden in lean mode)")
        else:
            st.caption("No persistent audit events recorded yet.")

    else:
        # ── Not connected: show credential form ─────────────────
        st.subheader("MT5 Credentials")
        mt_col1, mt_col2, mt_col3 = st.columns(3)
        mt5_login = mt_col1.number_input(
            "MT5 Login (Account #)",
            value=saved["login"] if saved else 0,
            step=1, format="%d",
        )
        mt5_password = mt_col2.text_input(
            "Password", type="password",
            value=saved["password"] if saved else "",
        )
        mt5_server = mt_col3.text_input(
            "Server",
            value=saved["server"] if saved else "",
            placeholder="e.g. FundingPips-Server",
        )

        sym_list = list(MT5_SYMBOL_MAP.values())
        saved_sym_idx = sym_list.index(saved["symbol"]) if saved and saved.get("symbol") in sym_list else 0
        mt5_symbol = st.selectbox(
            "MT5 Symbol Name", sym_list, index=saved_sym_idx,
            help="Must match the exact symbol name in your MT5 terminal",
        )

        mt5_max_lot = st.number_input(
            "Max Lot Size",
            value=saved["max_lot"] if saved else 0.10,
            step=0.01, min_value=0.01,
        )
        mt5_max_spread = st.number_input(
            "Max Spread ($)",
            value=float(saved.get("max_spread_price", 0.60)) if saved else 0.60,
            step=0.05,
            min_value=0.0,
        )
        mt5_max_drift = st.number_input(
            "Max Entry Drift ($)",
            value=float(saved.get("max_entry_drift_price", 2.00)) if saved else 2.00,
            step=0.10,
            min_value=0.0,
        )
        mt5_max_trades_day = st.number_input(
            "Max Trades / Day",
            value=int(saved.get("max_trades_per_day", 8)) if saved else 8,
            step=1,
            min_value=1,
        )
        mt5_max_open_pos = st.number_input(
            "Max Open Positions",
            value=int(saved.get("max_open_positions", 2)) if saved else 2,
            step=1,
            min_value=1,
        )
        mt5_enforce_session = st.checkbox(
            "Enforce Session Window (UTC)",
            value=bool(saved.get("enforce_session_window", False)) if saved else False,
        )
        ns1, ns2 = st.columns(2)
        mt5_session_start = ns1.number_input(
            "Session Start UTC",
            value=int(saved.get("session_start_utc", 0)) if saved else 0,
            step=1,
            min_value=0,
            max_value=23,
        )
        mt5_session_end = ns2.number_input(
            "Session End UTC",
            value=int(saved.get("session_end_utc", 23)) if saved else 23,
            step=1,
            min_value=0,
            max_value=23,
        )

        config = MT5Config(
            login=int(mt5_login),
            password=mt5_password,
            server=mt5_server,
            symbol=mt5_symbol,
            max_lot=mt5_max_lot,
            max_spread_price=mt5_max_spread,
            max_entry_drift_price=mt5_max_drift,
            max_trades_per_day=int(mt5_max_trades_day),
            max_open_positions=int(mt5_max_open_pos),
            enforce_session_window=bool(mt5_enforce_session),
            session_start_utc=int(mt5_session_start),
            session_end_utc=int(mt5_session_end),
        )

        cred_col1, cred_col2, cred_col3 = st.columns(3)
        with cred_col1:
            if st.button("🔌 Connect to MT5", type="primary",
                          disabled=(mt5_login == 0 or not mt5_password or not mt5_server)):
                with st.spinner("Connecting to MT5..."):
                    ok, msg = connect_mt5(config)
                if ok:
                    st.session_state["mt5_connected"] = True
                    st.session_state["mt5_config"] = config
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)
        with cred_col2:
            if st.button("💾 Save Credentials",
                          disabled=(mt5_login == 0 or not mt5_password or not mt5_server)):
                save_credentials(mt5_login, mt5_password, mt5_server,
                                 mt5_symbol, mt5_max_lot,
                                 mt5_max_spread, mt5_max_drift,
                                 int(mt5_max_trades_day), int(mt5_max_open_pos),
                                 bool(mt5_enforce_session),
                                 int(mt5_session_start), int(mt5_session_end))
                st.success("Credentials saved. They will auto-fill & auto-connect next time.")
        with cred_col3:
            if st.button("🗑️ Delete Saved"):
                delete_credentials()
                st.info("Saved credentials removed.")

        st.markdown("---")
        st.subheader("Setup Guide")
        st.markdown("""
1. **Install MT5**: Download from your broker (Funding Pips) and install
2. **Login**: Enter your account number, password, and server name
3. **Save & Connect**: Click 💾 then 🔌 — next time it auto-connects
4. **Symbol**: Make sure the symbol name matches exactly what's in MT5
5. **Execution Guardrails**: Set max spread, max entry drift, and keep kill-switch OFF only when ready
6. **Execution Policy**: Set max trades/day, max open positions, and optional UTC session window
7. **Auto-Refresh**: Enable in sidebar so the bot checks for fresh signals periodically
8. **Auto-Trade**: Enable only after verifying signals look correct

**How Auto-Trade Works:**
- When **Auto-Refresh** is ON, the bot re-fetches data every N seconds
- If a **new ICT signal** appears → executes at **live market price**
- **SL/TP** are recalculated as distance offsets from the live price (not raw signal prices) and enforce the broker's minimum stop level
- Trade is blocked if **spread** or **entry drift** exceeds your guardrail thresholds
- **Kill-switch** can instantly block all new entries without disconnecting MT5
- Policy engine can block trades by **max trades/day**, **max open positions**, or **session window**
- **AI Risk Advisor** calculates optimal lot size using ½-Kelly criterion capped by a drawdown-safe limit
- Each signal only executes **once** (duplicate prevention via signal hash tracking)
- All execution outcomes (FILLED / FAILED / BLOCKED) are written to a persistent audit log

**Default Settings (Backtested on 60 days / ~858 trades on XAUUSD):**

| Mode | TF | Lot | R:R | SL avg | TP avg | Win Rate | Max DD |
|---|---|---|---|---|---|---|---|
| Scalping | 5m | 0.02 | 1.5 | ~12.7 pts | ~19.1 pts | 53.5% | 4.7% ✅ |
| Intraday | 1h | 0.04 | 2.0 | ~20.7 pts | ~41.4 pts | 53.1% | 10.7% ⚠️ |

- **Scalping 5m** doubled a $10K account (+102%) with only 4.7% max DD — safest for Funding Pips
- **Intraday 1h** returned +83% but DD slightly exceeds 10% limit — consider 0.03 lot
- **ICT Concepts used**: Liquidity Sweep → sets bias, FVG/OB/OTE → entry zones, sweep candle → SL
- **Break-even**: SL moves to entry after price hits 1R profit
- **Gold multiplier**: $1/point per 0.01 lot ($100/point per 1.0 lot)
""")


# ===================================================================
# PAGE: Grid Trading
# ===================================================================
elif page == "Grid Trading":
    st.header("🕸️ Grid Trading — AI-Directed")
    st.caption("Small lots · Dynamic ATR spacing · AI direction analysis · Self-learning brain")

    # ── Load persistent state ─────────────────────────────────────
    if "grid_state" not in st.session_state:
        st.session_state.grid_state = load_grid_state()
    if "grid_brain" not in st.session_state:
        st.session_state.grid_brain = load_brain()

    gs = st.session_state.grid_state
    brain = st.session_state.grid_brain

    # ── Sidebar refresh cadence ───────────────────────────────────

    # Set a sensible minimum refresh (5s) to avoid constant reloads
    grid_refresh = st.sidebar.selectbox(
        "Grid Refresh", [5, 10, 15, 30, 60], index=0,
        key="grid_refresh_sel",
        help="Auto-refresh interval in seconds for grid monitoring (min 5s recommended)"
    )
    st_autorefresh(interval=grid_refresh * 1000, key="grid_autorefresh")

    # ─────────────────────────────────────────────────────────────
    # SECTION 1 — Configuration panel
    # ─────────────────────────────────────────────────────────────
    with st.expander("⚙️ Grid Configuration", expanded=not gs.active):
        gc1, gc2, gc3 = st.columns(3)
        with gc1:
            grid_symbol = st.selectbox(
                "Symbol", list(INSTRUMENTS.keys()), index=0, key="grid_symbol"
            )
            grid_tf = st.selectbox(
                "Timeframe", ["1m", "5m", "15m", "1h", "4h"], index=1, key="grid_tf"
            )
            grid_base_lot = st.number_input(
                "Base Lot", min_value=0.01, max_value=0.5, value=0.01, step=0.01,
                format="%.2f", key="grid_base_lot",
                help="Smallest lot per grid level. AI may scale slightly toward bias."
            )
        with gc2:
            grid_levels_buy = st.number_input(
                "Buy Levels (below price)", min_value=1, max_value=10, value=4,
                key="grid_levels_buy"
            )
            grid_levels_sell = st.number_input(
                "Sell Levels (above price)", min_value=1, max_value=10, value=4,
                key="grid_levels_sell"
            )
            grid_spacing_mult = st.slider(
                "Spacing Multiplier (ATR×)", min_value=0.3, max_value=3.0,
                value=1.0, step=0.1, key="grid_spacing_mult",
                help="Grid spacing = ATR × this multiplier. Brain will auto-tune over time."
            )
        with gc3:
            grid_tp_mult = st.slider(
                "TP Multiplier", min_value=0.5, max_value=4.0, value=1.5,
                step=0.25, key="grid_tp_mult",
                help="Take profit = spacing × TP multiplier"
            )
            grid_sl_mult = st.slider(
                "SL Multiplier", min_value=1.0, max_value=6.0, value=2.5,
                step=0.25, key="grid_sl_mult",
                help="Stop loss = spacing × SL multiplier (wide, full-grid risk)"
            )
            grid_max_open = st.number_input(
                "Max Open Levels", min_value=1, max_value=20, value=6,
                key="grid_max_open"
            )
        ga1, ga2 = st.columns(2)
        with ga1:
            grid_ai_dir = st.toggle(
                "AI Direction Enabled", value=True, key="grid_ai_dir",
                help="Let AI skew grid levels toward detected market bias"
            )
        with ga2:
            grid_ai_spacing = st.toggle(
                "AI Spacing Tuning (Brain)", value=True, key="grid_ai_spacing",
                help="Apply brain-learned spacing multiplier instead of manual value"
            )

        gp1, gp2, gp3 = st.columns(3)
        with gp1:
            grid_auto_profile = st.toggle(
                "Auto Regime Profile", value=True, key="grid_auto_profile",
                help="Auto-switch settings for RANGING/TRENDING/VOLATILE"
            )
            basket_tp_usd = st.number_input(
                "Basket TP ($)", min_value=1.0, max_value=5000.0, value=25.0,
                step=1.0, key="basket_tp_usd"
            )
        with gp2:
            basket_sl_usd = st.number_input(
                "Basket SL ($)", min_value=-5000.0, max_value=-1.0, value=-40.0,
                step=1.0, key="basket_sl_usd"
            )
            basket_close_profit = st.toggle(
                "Basket Close on Profit", value=True, key="basket_close_profit"
            )
        with gp3:
            basket_close_loss = st.toggle(
                "Basket Close on Loss", value=True, key="basket_close_loss"
            )
            st.caption("Basket close handles all OPEN levels when target/stop is reached.")

        gt1, gt2, gt3 = st.columns(3)
        with gt1:
            basket_trailing_tp = st.toggle(
                "Trailing Basket TP", value=False, key="basket_trailing_tp",
                help="After TP is hit, keep basket open and trail profits. "
                     "Close only when PnL drops by the trailing step from its peak."
            )
        with gt2:
            basket_trailing_step = st.number_input(
                "Trailing Step ($)", min_value=1.0, max_value=500.0, value=5.0,
                step=1.0, key="basket_trailing_step",
                disabled=not basket_trailing_tp,
                help="Close basket when PnL drops this amount below peak"
            )
        with gt3:
            session_pause_enabled = st.toggle(
                "Session Pause", value=False, key="session_pause_enabled",
                help="Pause new grid fills during selected low-liquidity sessions"
            )
            session_pause_list = st.text_input(
                "Paused Sessions", value="Asian",
                key="session_pause_list",
                disabled=not session_pause_enabled,
                help="Comma-separated: Asian, London, NY, Overlap/Off"
            )

        gr1, gr2, gr3 = st.columns(3)
        with gr1:
            risk_max_daily_loss = st.number_input(
                "Max Daily Loss ($)", min_value=0.0, max_value=20000.0, value=100.0,
                step=5.0, key="risk_max_daily_loss",
                help="Block new entries when daily realized loss reaches this value"
            )
        with gr2:
            risk_max_dd_pct = st.slider(
                "Max Drawdown (%)", min_value=0.5, max_value=30.0, value=8.0,
                step=0.5, key="risk_max_dd_pct",
                help="Block new entries when equity drawdown from peak exceeds this percent"
            )
        with gr3:
            risk_min_equity = st.number_input(
                "Min Equity ($)", min_value=0.0, max_value=1000000.0, value=0.0,
                step=10.0, key="risk_min_equity",
                help="If > 0, grid blocks entries below this equity level"
            )

        gp4, gp5, gp6 = st.columns(3)
        with gp4:
            grid_account_preset = st.selectbox(
                "Account Safety Preset",
                ["Custom", "2k Safe", "5k Safe", "10k Safe"],
                index=0,
                key="grid_account_preset",
                help="Applies conservative defaults for lot, caps, and risk limits",
            )
        with gp5:
            grid_enforce_portfolio_caps = st.toggle(
                "Enforce Portfolio Caps",
                value=True,
                key="grid_enforce_portfolio_caps",
                help="Prevents new fills if total account positions/lots exceed limits",
            )
        with gp6:
            st.caption("Portfolio caps apply to whole account, not only this grid symbol.")

        pc1, pc2 = st.columns(2)
        with pc1:
            grid_portfolio_max_positions = st.number_input(
                "Portfolio Max Positions",
                min_value=1,
                max_value=200,
                value=12,
                key="grid_portfolio_max_positions",
            )
        with pc2:
            grid_portfolio_max_lots = st.number_input(
                "Portfolio Max Lots",
                min_value=0.01,
                max_value=100.0,
                value=1.0,
                step=0.01,
                format="%.2f",
                key="grid_portfolio_max_lots",
            )

    # Build config from UI
    _grid_cfg = GridConfig(
        symbol=grid_symbol,
        timeframe=grid_tf,
        base_lot=grid_base_lot,
        levels_buy=grid_levels_buy,
        levels_sell=grid_levels_sell,
        spacing_multiplier=grid_spacing_mult,
        tp_multiplier=grid_tp_mult,
        sl_multiplier=grid_sl_mult,
        max_open_levels=grid_max_open,
        ai_direction_enabled=grid_ai_dir,
        ai_spacing_enabled=grid_ai_spacing,
        auto_profile_switch=grid_auto_profile,
        basket_take_profit_usd=basket_tp_usd,
        basket_stop_loss_usd=basket_sl_usd,
        basket_close_on_profit=basket_close_profit,
        basket_close_on_loss=basket_close_loss,
        basket_trailing_tp=basket_trailing_tp,
        basket_trailing_step_usd=basket_trailing_step,
        session_pause_enabled=session_pause_enabled,
        session_pause_list=session_pause_list,
        max_daily_loss_usd=risk_max_daily_loss,
        max_drawdown_pct=risk_max_dd_pct,
        min_equity_usd=risk_min_equity,
    )
    if grid_account_preset != "Custom":
        _grid_cfg = apply_account_preset(_grid_cfg, grid_account_preset)

    # ─────────────────────────────────────────────────────────────
    # SECTION 2 — AI Market Analysis
    # ─────────────────────────────────────────────────────────────
    st.subheader("🧠 AI Market Direction Analysis")


    # Use a moderate cache for stability (10s)
    @st.cache_data(ttl=10, show_spinner=False)
    def _grid_fetch_data(symbol, tf):
        return fetch_ohlcv(symbol, tf)

    @st.cache_data(ttl=10, show_spinner=False)
    def _grid_fetch_signals(symbol, tf, concepts, lookback, rr):
        df = fetch_ohlcv(symbol, tf)
        if df.empty:
            return df, None
        sigs = generate_signals(
            df,
            required_concepts=concepts,
            rr_ratio=rr,
            sweep_lookback=lookback,
        )
        return df, sigs

    # HTF mapping: grid TF → structure TF for stable directional bias
    _HTF_MAP = {"1m": "15m", "5m": "1h", "15m": "1h", "1h": "4h", "4h": "4h"}
    _htf_tf = _HTF_MAP.get(grid_tf, "1h")


    # Remove spinner for instant UI; rely on fast cache
    _concepts_default = ["Liquidity Sweep", "FVG", "MSS"]
    _grid_df, _grid_sigs = _grid_fetch_signals(
        grid_symbol, grid_tf, _concepts_default, 20, 1.5
    )
    _htf_df = _grid_fetch_data(grid_symbol, _htf_tf)

    if _grid_df is not None and not _grid_df.empty:
        # Single regime call: compute base regime to get brain rec, then
        # immediately derive the effective regime with brain multiplier.
        _base_regime = analyze_market_direction(
            _grid_df, grid_spacing_mult, _grid_sigs, None,
            htf_df=_htf_df,
        )
        _brain_rec = get_recommendation(grid_symbol, _base_regime.regime, brain)

        _effective_cfg = apply_regime_profile(_grid_cfg, _base_regime.regime)
        if _brain_rec["has_data"]:
            _effective_cfg.tp_multiplier = _brain_rec["tp_multiplier"]
            _effective_cfg.sl_multiplier = _brain_rec["sl_multiplier"]
            _effective_cfg.max_open_levels = int(max(1, _brain_rec["max_open_levels"]))

        _brain_mult = _brain_rec["spacing_multiplier"] if (grid_ai_spacing and _brain_rec["has_data"]) else None

        # Reuse _base_regime and only adjust spacing (avoids recomputing EMA/ATR)
        from dataclasses import replace as _dc_replace
        _effective_mult = _brain_mult if _brain_mult is not None else _effective_cfg.spacing_multiplier
        _regime = _dc_replace(
            _base_regime,
            recommended_spacing=round(_base_regime.atr * _effective_mult, 5),
        )

        # Brain is trained on-demand via the "Retrain Brain Now" button
        # (no longer retrained on every page load for performance).

        # When grid is active, show the LOCKED bias from activation.
        # When inactive, show the live HTF-derived bias.
        if gs.active:
            _display_bias = gs.regime.direction_bias
            _display_conf = gs.regime.direction_confidence
            _bias_label = f"AI Bias (locked)"
        else:
            _display_bias = _regime.direction_bias
            _display_conf = _regime.direction_confidence
            _bias_label = f"AI Bias ({_htf_tf} HTF)"

        # Metrics strip
        ma1, ma2, ma3, ma4, ma5 = st.columns(5)
        _bias_color = {"BULLISH": "🟢", "BEARISH": "🔴", "NEUTRAL": "⚪"}.get(
            _display_bias, "⚪"
        )
        ma1.metric(
            _bias_label,
            f"{_bias_color} {_display_bias}",
            f"{_display_conf:.0f}% confidence"
        )
        ma2.metric(
            "Market Regime",
            "SIDEWAYS" if _regime.regime == "RANGING" else _regime.regime,
            f"ATR ratio {_regime.atr_ratio:.2f}"
        )
        ma3.metric(
            "ATR",
            f"{_regime.atr:.4f}",
            f"Spacing → {_regime.recommended_spacing:.4f}"
        )
        ma4.metric(
            "Session",
            _regime.session,
            f"Bull signals {_regime.signal_bull_count} / Bear {_regime.signal_bear_count}"
        )
        _brain_txt = (
            f"Mult ×{_brain_rec['spacing_multiplier']:.2f} ({_brain_rec['total_trades']} trades)"
            if _brain_rec["has_data"] else "Learning…"
        )
        ma5.metric(
            "Brain Spacing",
            _brain_txt,
            f"Win rate {_brain_rec['win_rate']:.0f}%" if _brain_rec["has_data"] else "Need more trades"
        )
        st.caption(
            f"Profile: {_effective_cfg.profile_name} | "
            f"TP {_effective_cfg.tp_multiplier:.2f} | SL {_effective_cfg.sl_multiplier:.2f} | "
            f"Max Open {_effective_cfg.max_open_levels} | "
            f"Bias source: {_htf_tf.upper()} HTF EMA20/50"
        )

        # If grid active and live bias diverges from locked bias, auto-deactivate and notify
        if gs.active and _regime.direction_bias != gs.regime.direction_bias:
            gs = deactivate_grid(gs)
            save_grid_state(gs)
            st.session_state.grid_state = gs
            st.error(
                f"⚠️ Grid auto-deactivated: Live HTF bias is now **{_regime.direction_bias}** "
                f"but grid was activated with **{gs.regime.direction_bias}**. "
                f"You must re-activate to follow the new trend."
            )
            st.stop()

        # Only show grid level preview if grid is active
        if gs.active and not _grid_df.empty:
            st.markdown("**Grid Level Preview** (at current anchor price)")
            _preview_price = float(_grid_df["Close"].iloc[-1])
            _preview_levels = build_grid_levels(_preview_price, _regime, _effective_cfg)
            _preview_rows = []
            for _lv in _preview_levels:
                _dir_icon = "🟦 BUY" if _lv.direction == "BUY" else "🟥 SELL"
                _preview_rows.append({
                    "Level": _lv.level_id,
                    "Dir": _dir_icon,
                    "Price": f"{_lv.price:.4f}",
                    "Lot": _lv.lot,
                    "SL": f"{_lv.sl_price:.4f}",
                    "TP": f"{_lv.tp_price:.4f}",
                })
            st.dataframe(pd.DataFrame(_preview_rows), use_container_width=True, height=260)

            # ── Dynamic Plan Preview ────────────────────────────
            st.markdown("**Dynamic Plan Preview** — computed parameters before activation")
            _buy_count = sum(1 for lv in _preview_levels if lv.direction == "BUY")
            _sell_count = sum(1 for lv in _preview_levels if lv.direction == "SELL")
            _total_lots = sum(lv.lot for lv in _preview_levels)
            _buy_lots = sum(lv.lot for lv in _preview_levels if lv.direction == "BUY")
            _sell_lots = sum(lv.lot for lv in _preview_levels if lv.direction == "SELL")
            _regime_label = "SIDEWAYS" if _regime.regime == "RANGING" else _regime.regime
            dp1, dp2, dp3, dp4, dp5 = st.columns(5)
            dp1.metric("Regime", _regime_label)
            dp2.metric("Buy / Sell Levels", f"{_buy_count} / {_sell_count}")
            dp3.metric("Effective Spacing", f"{_regime.recommended_spacing:.5f}")
            dp4.metric("Total Lots", f"{_total_lots:.2f}")
            dp5.metric("Buy / Sell Lots", f"{_buy_lots:.2f} / {_sell_lots:.2f}")
            _lot_pressure = _buy_lots / max(_sell_lots, 0.001)
            _pressure_icon = "🟢 BUY" if _lot_pressure > 1.15 else ("🔴 SELL" if _lot_pressure < 0.85 else "⚖️ BALANCED")
            st.caption(
                f"Lot Pressure: {_pressure_icon} ({_lot_pressure:.2f}×) · "
                f"Spacing ×{_effective_mult:.2f} ATR · "
                f"TP ×{_effective_cfg.tp_multiplier:.2f} · SL ×{_effective_cfg.sl_multiplier:.2f}"
            )
    else:
        st.warning("Could not fetch market data for AI analysis. Check symbol/timeframe.")
        _regime = None

    # ─────────────────────────────────────────────────────────────
    # SECTION 3 — Grid Controls (Activate / Deactivate)
    # ─────────────────────────────────────────────────────────────
    st.subheader("🎛️ Grid Controls")

    # ── Hard lockout check ────────────────────────────────────────
    if gs.lockout_active:
        st.error(
            f"**GRID LOCKED** — {gs.lockout_reason}\n\n"
            f"Locked at: {gs.lockout_time}\n\n"
            "You must manually unlock before activating the grid."
        )
        _unlock_reason = st.text_input(
            "Unlock reason (required)", key="lockout_unlock_reason",
            placeholder="e.g. Reviewed risk, adjusted lot size"
        )
        if st.button("🔓 Unlock Grid", type="primary", disabled=not _unlock_reason.strip()):
            from grid_engine import append_grid_audit
            append_grid_audit({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event": "LOCKOUT_CLEARED",
                "symbol": gs.config.symbol,
                "reason": _unlock_reason.strip(),
                "locked_reason": gs.lockout_reason,
                "locked_time": gs.lockout_time,
                "run_id": gs.run_id,
            })
            gs.lockout_active = False
            gs.lockout_reason = ""
            gs.lockout_time = ""
            gs.risk_blocked = False
            gs.risk_reason = ""
            save_grid_state(gs)
            st.session_state.grid_state = gs
            st.success("Grid unlocked. You may now re-activate.")
            st.rerun()
        st.stop()

    _mt5_ok = mt5_runtime_supported()
    if not _mt5_ok:
        st.warning(
            "MT5 runtime not available on this OS. Grid level execution requires Windows + MetaTrader5. "
            "AI analysis and level preview are still active."
        )

    em1, em2 = st.columns([2, 3])

    with em1:
        grid_live_exec_enabled = st.toggle(
            "Enable Live MT5 Orders",
            value=True,
            key="grid_live_exec_enabled",
            help="Off = dry-run only. On + confirmation = real MT5 order placement.",
        )
    with em2:
        grid_live_exec_confirm = st.checkbox(
            "I confirm live mode can place real broker orders",
            value=True,
            key="grid_live_exec_confirm",
            disabled=not grid_live_exec_enabled,
        )

    grid_live_orders_allowed = _mt5_ok and grid_live_exec_enabled and grid_live_exec_confirm
    if grid_live_orders_allowed:
        st.success("Execution Mode: LIVE")
    else:
        st.info("Execution Mode: DRY-RUN (safe simulation)")

    ctrl_c1, ctrl_c2, ctrl_c3 = st.columns([2, 2, 3])
    with ctrl_c1:
        # Check all activation preconditions and collect reasons if not ready
        activation_ready = True
        activation_reason = ""
        if gs.active:
            activation_ready = False
            activation_reason = "Grid is already active."
        elif _grid_df is None or _grid_df.empty:
            activation_ready = False
            activation_reason = "Market data unavailable. Cannot activate grid."
        elif _regime is None:
            activation_ready = False
            activation_reason = "Market regime not available. Wait for analysis."
        else:
            _audit_log = load_audit_log(limit=100)
            blocked, reason = ai_context_filter(gs, _grid_df, _htf_df, _audit_log)
            if blocked:
                activation_ready = False
                activation_reason = reason
            elif grid_enforce_portfolio_caps:
                if grid_live_orders_allowed:
                    _all_pos = get_open_positions(None)
                    _port_positions = len(_all_pos)
                    _port_lots = sum(float(p.get("volume", 0.0)) for p in _all_pos)
                else:
                    _sim_open = get_open_levels(gs)
                    _port_positions = len(_sim_open)
                    _port_lots = sum(float(lv.lot) for lv in _sim_open)
                if _port_positions >= int(grid_portfolio_max_positions):
                    activation_ready = False
                    activation_reason = (
                        f"Activation blocked: portfolio positions {_port_positions} "
                        f">= cap {int(grid_portfolio_max_positions)}"
                    )
                elif _port_lots >= float(grid_portfolio_max_lots):
                    activation_ready = False
                    activation_reason = (
                        f"Activation blocked: portfolio lots {_port_lots:.2f} "
                        f">= cap {float(grid_portfolio_max_lots):.2f}"
                    )

        if not gs.active:
            if st.button(
                "🚀 Activate Grid",
                type="primary",
                use_container_width=True,
                key="activate_grid_btn",
                disabled=not activation_ready,
                help=activation_reason if not activation_ready else "Activate the grid with current settings."
            ):
                with st.spinner("Activating grid, please wait…"):
                    try:
                        _brain_mult2 = (
                            get_recommendation(grid_symbol, _regime.regime, brain)["spacing_multiplier"]
                            if grid_ai_spacing else None
                        )
                        _cfg_live = _effective_cfg if "_effective_cfg" in locals() else _grid_cfg
                        _live_price = float(_grid_df["Close"].iloc[-1])
                        _start_balance = 0.0
                        if _mt5_ok:
                            _tick = get_live_price(MT5_SYMBOL_MAP.get(grid_symbol, grid_symbol))
                            if _tick:
                                _live_price = (_tick["bid"] + _tick["ask"]) / 2
                            _acc = get_account_info()
                            if _acc:
                                _start_balance = float(_acc.get("balance", 0.0))

                        if _cfg_live.auto_profile_switch:
                            _cfg_live = apply_regime_profile(_cfg_live, _regime.regime)

                        new_gs = activate_grid(
                            current_price=_live_price,
                            df=_grid_df,
                            config=_cfg_live,
                            ict_signals=_grid_sigs,
                            brain_multiplier=_brain_mult2,
                            starting_balance=_start_balance,
                            htf_df=_htf_df,
                        )
                        st.session_state.grid_state = new_gs
                        save_grid_state(new_gs)
                        st.success(
                            f"Grid activated at {_live_price:.4f} — "
                            f"{len(new_gs.levels)} levels built | "
                            f"Bias: {new_gs.regime.direction_bias} ({new_gs.regime.direction_confidence:.0f}%) | "
                            f"Mode: {'LIVE' if grid_live_orders_allowed else 'DRY-RUN'}"
                        )
                        st.rerun()
                    except Exception as e:
                        st.error(f"Grid activation failed: {e}")
        else:
            if st.button("⏹️ Deactivate Grid", type="secondary", use_container_width=True):
                gs = deactivate_grid(gs)
                save_grid_state(gs)
                st.session_state.grid_state = gs
                st.warning("Grid deactivated. Open positions remain — close manually if needed.")
                st.rerun()
        if not activation_ready and activation_reason:
            st.info(f"Activate Grid unavailable: {activation_reason}")
        # Persistent debug info for missing variables
        if not gs.active:
            missing = []
            if _grid_df is None or (_grid_df is not None and _grid_df.empty):
                missing.append("Market data")
            if _regime is None:
                missing.append("Market regime analysis")
            if missing:
                st.warning(f"Waiting for: {', '.join(missing)}. Please wait for data to load before activating the grid.")

    with ctrl_c2:
        if st.button("🔄 Re-analyse Direction", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    with ctrl_c3:
        _gs_sum = grid_summary(gs)
        _status_color = "🟢 ACTIVE" if gs.active else "⚫ INACTIVE"
        st.info(
            f"**Grid Status:** {_status_color} | "
            f"Run ID: `{_gs_sum['run_id'] or 'n/a'}` | "
            f"Anchor: {_gs_sum['anchor_price']:.4f} | "
            f"Open: {_gs_sum['open_levels']} | Pending: {_gs_sum['pending_levels']}"
        )

    # ─────────────────────────────────────────────────────────────
    # SECTION 4 — Live Grid Monitor (when active)
    # ─────────────────────────────────────────────────────────────
    if gs.active:
        st.subheader("📡 Live Grid Monitor")

        # Refresh state from disk on each cycle
        gs = load_grid_state()
        st.session_state.grid_state = gs

        # Live price + trigger check
        _live_p = None
        _risk_metrics = {}
        _risk_blocked = False
        _risk_reason = ""
        if _mt5_ok:
            _tick2 = get_live_price(MT5_SYMBOL_MAP.get(gs.config.symbol, gs.config.symbol))
            if _tick2:
                _live_p = (_tick2["bid"] + _tick2["ask"]) / 2
            _acc_live = get_account_info()
            if _acc_live:
                _risk_blocked, _risk_reason, _risk_metrics = evaluate_risk_guards(
                    gs,
                    float(_acc_live.get("balance", 0.0)),
                    float(_acc_live.get("equity", 0.0)),
                )
                save_grid_state(gs)

        if _risk_metrics:
            rk1, rk2, rk3 = st.columns(3)
            rk1.metric("Daily Loss", f"${_risk_metrics.get('daily_loss_usd', 0.0):.2f}")
            rk2.metric("Drawdown", f"{_risk_metrics.get('drawdown_peak_pct', 0.0):.2f}%")
            rk3.metric("Floating PnL", f"${_risk_metrics.get('floating_pnl', 0.0):.2f}")

        _portfolio_blocked = False
        _portfolio_reason = ""
        _portfolio_positions = 0
        _portfolio_lots = 0.0
        if grid_enforce_portfolio_caps:
            if grid_live_orders_allowed:
                _all_open_pos = get_open_positions(None)
                _portfolio_positions = len(_all_open_pos)
                _portfolio_lots = sum(float(p.get("volume", 0.0)) for p in _all_open_pos)
            else:
                _sim_open = get_open_levels(gs)
                _portfolio_positions = len(_sim_open)
                _portfolio_lots = sum(float(lv.lot) for lv in _sim_open)

            if _portfolio_positions >= int(grid_portfolio_max_positions):
                _portfolio_blocked = True
                _portfolio_reason = (
                    f"Portfolio position cap reached ({_portfolio_positions}/"
                    f"{int(grid_portfolio_max_positions)})"
                )
            elif _portfolio_lots >= float(grid_portfolio_max_lots):
                _portfolio_blocked = True
                _portfolio_reason = (
                    f"Portfolio lot cap reached ({_portfolio_lots:.2f}/"
                    f"{float(grid_portfolio_max_lots):.2f})"
                )

            pc1, pc2 = st.columns(2)
            pc1.metric("Portfolio Positions", f"{_portfolio_positions}/{int(grid_portfolio_max_positions)}")
            pc2.metric("Portfolio Lots", f"{_portfolio_lots:.2f}/{float(grid_portfolio_max_lots):.2f}")
            if _portfolio_blocked:
                st.warning(_portfolio_reason)

        if _risk_blocked:
            st.error(f"Risk guard active: {_risk_reason}")
            gs = deactivate_grid(gs)
            gs.risk_blocked = True
            gs.risk_reason = _risk_reason
            gs.lockout_active = True
            gs.lockout_reason = f"Auto-lockout: {_risk_reason}"
            gs.lockout_time = datetime.now(timezone.utc).isoformat()
            save_grid_state(gs)
            st.warning("Grid auto-deactivated and LOCKED due to risk guard breach. Manual unlock required.")
            st.rerun()

        # Session pause check
        _session_paused, _session_pause_msg = is_session_paused(gs.config)
        if _session_paused:
            st.info(f"⏸️ {_session_pause_msg} — new fills paused, existing positions monitored.")

        if _live_p:
            st.markdown(f"**Live Price:** `{_live_p:.5f}`")

            # Check which levels price has reached
            _triggered = check_levels_hit(gs, _live_p)
            if _triggered and count_open_levels(gs) < gs.config.max_open_levels and not _risk_blocked and not _portfolio_blocked and not _session_paused:
                _runtime_positions = _portfolio_positions
                _runtime_lots = _portfolio_lots
                for _triggered_lv in _triggered:
                    if grid_enforce_portfolio_caps:
                        if (_runtime_positions + 1) > int(grid_portfolio_max_positions):
                            st.warning("Fill skipped: portfolio position cap would be exceeded.")
                            break
                        if (_runtime_lots + float(_triggered_lv.lot)) > float(grid_portfolio_max_lots):
                            st.warning("Fill skipped: portfolio lot cap would be exceeded.")
                            break

                    if grid_live_orders_allowed:
                        _order_result = place_grid_order_mt5(
                            _triggered_lv,
                            gs.config.symbol,
                            GRID_MAGIC,
                        )
                        if _order_result["success"]:
                            mark_level_open(
                                gs, _triggered_lv.level_id,
                                _order_result["ticket"],
                                _order_result["price"]
                            )
                            _ems = _order_result.get('exec_ms', 0)
                            st.success(
                                f"✅ Level {_triggered_lv.level_id} filled — "
                                f"ticket #{_order_result['ticket']} @ {_order_result['price']:.5f}"
                                f" ({_ems:.0f} ms)"
                            )
                            _runtime_positions += 1
                            _runtime_lots += float(_triggered_lv.lot)
                        else:
                            _ems = _order_result.get('exec_ms', 0)
                            st.error(f"❌ Level {_triggered_lv.level_id}: {_order_result['message']} ({_ems:.0f} ms)")
                    else:
                        # Dry-run: simulate fill
                        mark_level_open(gs, _triggered_lv.level_id, 0, _live_p)
                        st.info(f"[Dry-run] Level {_triggered_lv.level_id} would trigger at {_live_p:.5f}")
                        _runtime_positions += 1
                        _runtime_lots += float(_triggered_lv.lot)

                save_grid_state(gs)

            _basket_pnl = basket_floating_pnl_usd(gs, _live_p)
            _bm1, _bm2, _bm3 = st.columns(3)
            _bm1.metric("Basket Floating PnL", f"${_basket_pnl:.2f}")
            if gs.config.basket_trailing_tp:
                _trail_floor = gs.basket_peak_pnl - gs.config.basket_trailing_step_usd
                _bm2.metric("Basket Peak PnL", f"${gs.basket_peak_pnl:.2f}")
                _bm3.metric("Trail Floor", f"${_trail_floor:.2f}" if gs.basket_peak_pnl > 0 else "—")
            _close_basket, _basket_reason = should_close_basket(gs, _basket_pnl)
            save_grid_state(gs)  # persist basket_peak_pnl updates
            if _close_basket:
                st.warning(f"Basket close triggered: {_basket_reason}")
                for _olv in get_open_levels(gs):
                    if grid_live_orders_allowed and _olv.ticket:
                        _close_res = close_grid_position_mt5(
                            _olv.ticket, gs.config.symbol, _olv.lot, _olv.direction
                        )
                        if _close_res["success"]:
                            _cp = _close_res.get("price", _live_p) or _live_p
                            _pnl_est = (
                                (_cp - _olv.entry_price) * _olv.lot * 100
                                if _olv.direction == "BUY"
                                else (_olv.entry_price - _cp) * _olv.lot * 100
                            )
                            mark_level_closed(gs, _olv.level_id, _cp, _pnl_est)
                    else:
                        _pnl_est = (
                            (_live_p - _olv.entry_price) * _olv.lot * 100
                            if _olv.direction == "BUY"
                            else (_olv.entry_price - _live_p) * _olv.lot * 100
                        )
                        mark_level_closed(gs, _olv.level_id, _live_p, _pnl_est)
                save_grid_state(gs)
                st.session_state.grid_brain = train_brain(brain)
                st.rerun()

        # Open positions — check MT5 for closed/TP-hit levels
        if grid_live_orders_allowed:
            _mt5_positions = get_open_positions(gs.config.symbol)
            _mt5_tickets = {p["ticket"] for p in _mt5_positions}

            for _open_lv in get_open_levels(gs):
                if _open_lv.ticket and _open_lv.ticket not in _mt5_tickets and _open_lv.ticket != 0:
                    # Position closed by TP/SL — get actual close from deal history
                    _deal_info = get_deal_close_info(_open_lv.ticket)
                    if _deal_info:
                        _cp = _deal_info["close_price"]
                        _actual_pnl = _deal_info["profit"]
                        mark_level_closed(gs, _open_lv.level_id, _cp, _actual_pnl)
                    elif _live_p:
                        # Fallback: estimate from live price
                        _est_profit = (
                            (_live_p - _open_lv.entry_price) * _open_lv.lot * 100
                            if _open_lv.direction == "BUY"
                            else (_open_lv.entry_price - _live_p) * _open_lv.lot * 100
                        )
                        mark_level_closed(gs, _open_lv.level_id, _live_p, _est_profit)
                        # Trigger brain re-training
                        st.session_state.grid_brain = train_brain(brain)

            save_grid_state(gs)

        # ── Grid levels table ─────────────────────────────────────
        _lv_df = grid_levels_dataframe(gs)
        if not _lv_df.empty:
            def _style_level_row(row):
                if row["Status"] == "OPEN":
                    return ["background-color: rgba(52,211,153,0.15)"] * len(row)
                if row["Status"] == "CLOSED":
                    return ["background-color: rgba(148,163,184,0.10)"] * len(row)
                if row["Status"] == "CANCELLED":
                    return ["background-color: rgba(239,68,68,0.08)"] * len(row)
                return [""] * len(row)

            st.dataframe(
                _lv_df.style.apply(_style_level_row, axis=1),
                use_container_width=True, height=300,
            )

        # ── Grid metrics row ──────────────────────────────────────
        _gs_sum = grid_summary(gs)
        gm1, gm2, gm3, gm4, gm5 = st.columns(5)
        gm1.metric("Total P&L", f"${_gs_sum['total_profit_usd']:.2f}")
        gm2.metric("Closed Levels", str(_gs_sum["total_closed"]))
        gm3.metric("Win Rate", f"{_gs_sum['win_rate']:.1f}%")
        gm4.metric("Wins / Losses", f"{_gs_sum['total_wins']} / {_gs_sum['total_losses']}")
        gm5.metric("Open Now", str(_gs_sum["open_levels"]))

        # ── Manual close buttons ──────────────────────────────────
        _open_lvs = get_open_levels(gs)
        if _open_lvs:
            st.markdown("**Manual Close Open Levels**")
            _close_cols = st.columns(min(len(_open_lvs), 6))
            for _ci, _olv in enumerate(_open_lvs):
                with _close_cols[_ci % 6]:
                    if st.button(
                        f"Close {_olv.level_id}\n#{_olv.ticket}",
                        key=f"close_{_olv.level_id}",
                    ):
                        if grid_live_orders_allowed and _olv.ticket:
                            _close_res = close_grid_position_mt5(
                                _olv.ticket, gs.config.symbol,
                                _olv.lot, _olv.direction
                            )
                            if _close_res["success"]:
                                _cp = _close_res.get("price", _live_p or 0.0) or (_live_p or 0.0)
                                _pnl_est = (
                                    (_cp - _olv.entry_price) * _olv.lot * 100
                                    if _olv.direction == "BUY"
                                    else (_olv.entry_price - _cp) * _olv.lot * 100
                                )
                                mark_level_closed(gs, _olv.level_id, _cp, _pnl_est)
                                st.session_state.grid_brain = train_brain(brain)
                                save_grid_state(gs)
                                _ems = _close_res.get('exec_ms', 0)
                                st.success(f"Closed #{_olv.ticket} ({_ems:.0f} ms)")
                                st.rerun()
                            else:
                                _ems = _close_res.get('exec_ms', 0)
                                st.error(f"{_close_res['message']} ({_ems:.0f} ms)")

    # ─────────────────────────────────────────────────────────────
    # SECTION 5 — AI Brain Learning Stats
    # ─────────────────────────────────────────────────────────────
    st.subheader("🤖 AI Brain — Learning Stats")

    _global = get_global_stats(brain)
    bs1, bs2, bs3, bs4 = st.columns(4)
    bs1.metric("Total Grid Trades", str(_global["total_trades"]))
    bs2.metric("Global Win Rate", f"{_global['win_rate']:.1f}%")
    bs3.metric("Avg P&L / Trade", f"${_global['avg_profit_usd']:.4f}")
    bs4.metric("Regimes Tracked", str(_global["regimes_tracked"]))

    _brain_df = regime_stats_dataframe(brain)
    if not _brain_df.empty:
        st.markdown("**Learned performance by Symbol × Regime**")
        st.dataframe(_brain_df, use_container_width=True)
        st.caption(
            "Spacing Multiplier is auto-tuned via EMA learning from profitable trades. "
            "Direction Accuracy tracks how often AI bias predicted the winning direction."
        )
    else:
        st.info(
            "No grid trade history yet. The brain will learn once you run the grid "
            f"and close at least 5 trades per symbol/regime."
        )

    # ── Grid P&L Equity Curve ─────────────────────────────────────
    _pnl_audit = load_grid_audit(500)
    _pnl_closed = [
        e for e in _pnl_audit
        if e.get("event") == "LEVEL_CLOSED" and e.get("profit_usd") is not None
    ]
    if _pnl_closed:
        _cum_pnl = 0.0
        _eq_rows = []
        for e in reversed(_pnl_closed):  # oldest first
            _cum_pnl += float(e.get("profit_usd", 0.0))
            _eq_rows.append({
                "time": e.get("timestamp", "")[:16],
                "cumulative_pnl": round(_cum_pnl, 2),
            })
        _eq_pnl_df = pd.DataFrame(_eq_rows)
        st.markdown("**Grid P&L Equity Curve** (cumulative from audit log)")
        st.line_chart(_eq_pnl_df.set_index("time")["cumulative_pnl"])
    else:
        st.caption("No closed grid trades yet — equity chart will appear after first closed level.")

    if st.button("🔁 Retrain Brain Now", key="retrain_brain_btn"):
        st.session_state.grid_brain = train_brain(None)
        st.success("Brain retrained from audit log.")
        st.rerun()

    # ─────────────────────────────────────────────────────────────
    # SECTION 6 — Grid Audit Log
    # ─────────────────────────────────────────────────────────────
    with st.expander("📋 Grid Audit Log (recent 100 events)", expanded=False):
        _audit_entries = load_grid_audit(100)
        if _audit_entries:
            _audit_df = pd.DataFrame(_audit_entries)
            _display_cols = [c for c in [
                "timestamp", "event", "symbol", "level_id", "direction",
                "entry_price", "exit_price", "profit_usd", "profit_pips",
                "regime", "bias", "lot", "run_id"
            ] if c in _audit_df.columns]
            st.dataframe(_audit_df[_display_cols], use_container_width=True, height=300)
        else:
            st.info("No grid audit events yet.")

        st.markdown("**Daily Grid Report Export**")
        _all_audit_entries = load_grid_audit(2000)
        _default_day = datetime.now(timezone.utc).date()
        _report_day = st.date_input(
            "Report Date (UTC)",
            value=_default_day,
            key="grid_daily_report_date",
        )
        _report_day_str = _report_day.strftime("%Y-%m-%d")
        _daily = [
            e for e in _all_audit_entries
            if str(e.get("timestamp", "")).startswith(_report_day_str)
        ]

        if _daily:
            _daily_df = pd.DataFrame(_daily)
            _filled = int((_daily_df.get("event", pd.Series(dtype=str)) == "LEVEL_CLOSED").sum())
            _pnl = float(_daily_df.get("profit_usd", pd.Series(dtype=float)).fillna(0.0).sum())
            _wins = int((_daily_df.get("profit_usd", pd.Series(dtype=float)).fillna(0.0) > 0).sum())
            _losses = int((_daily_df.get("profit_usd", pd.Series(dtype=float)).fillna(0.0) <= 0).sum())
            dr1, dr2, dr3, dr4 = st.columns(4)
            dr1.metric("Closed Events", str(_filled))
            dr2.metric("Daily PnL", f"${_pnl:.2f}")
            dr3.metric("Wins", str(_wins))
            dr4.metric("Losses", str(_losses))

            st.download_button(
                "Download Daily Grid Report CSV",
                data=_daily_df.to_csv(index=False).encode("utf-8"),
                file_name=f"grid_daily_report_{_report_day_str}.csv",
                mime="text/csv",
                key="dl_grid_daily_report",
            )
        else:
            st.caption("No audit events for the selected UTC date.")

    # ─────────────────────────────────────────────────────────────
    # SECTION 7 — Grid Backtest and Walk-Forward
    # ─────────────────────────────────────────────────────────────
    st.subheader("🧪 Grid Backtest + Walk-Forward")
    bt1, bt2, bt3 = st.columns(3)
    with bt1:
        bt_spread = st.number_input(
            "Spread points", min_value=0.0, max_value=10.0, value=0.15, step=0.01,
            key="grid_bt_spread"
        )
    with bt2:
        bt_slippage = st.number_input(
            "Slippage points", min_value=0.0, max_value=10.0, value=0.10, step=0.01,
            key="grid_bt_slippage"
        )
    with bt3:
        bt_rebalance = st.number_input(
            "Rebalance bars", min_value=4, max_value=240, value=24, step=1,
            key="grid_bt_rebalance"
        )

    if st.button("▶ Run Grid Backtest", key="run_grid_backtest_btn"):
        if _grid_df is None or _grid_df.empty:
            st.error("No OHLC data available for backtest.")
        else:
            _cfg_bt = _effective_cfg if "_effective_cfg" in locals() else _grid_cfg
            _bt_cfg = BacktestConfig(
                spread_points=float(bt_spread),
                slippage_points=float(bt_slippage),
                rebalance_bars=int(bt_rebalance),
            )
            with st.spinner("Running grid backtest..."):
                _bt = run_grid_backtest(_grid_df, _cfg_bt, _bt_cfg)
            st.session_state["grid_last_backtest"] = _bt

    _bt_render = st.session_state.get("grid_last_backtest")
    if _bt_render:
        _sum = _bt_render["summary"]
        btm1, btm2, btm3, btm4 = st.columns(4)
        btm1.metric("Trades", str(_sum["trades"]))
        btm2.metric("Win Rate", f"{_sum['win_rate']:.2f}%")
        btm3.metric("Net PnL", f"${_sum['net_pnl']:.2f}")
        btm4.metric("Max DD", f"${_sum['max_dd']:.2f}")

        _summary_df = pd.DataFrame([_sum])
        _eq_df = _bt_render["equity_curve"]
        _mo_df = _bt_render["monthly"]

        if not _eq_df.empty:
            st.line_chart(_eq_df.set_index("time")["equity"])

        if not _mo_df.empty:
            st.markdown("**Monthly Walk-Forward Summary**")
            st.dataframe(_mo_df, use_container_width=True)

        dl1, dl2, dl3 = st.columns(3)
        with dl1:
            st.download_button(
                "Download Summary CSV",
                data=_summary_df.to_csv(index=False).encode("utf-8"),
                file_name="grid_backtest_summary.csv",
                mime="text/csv",
                key="dl_grid_bt_summary",
            )
        with dl2:
            _eq_csv = _eq_df.copy()
            if not _eq_csv.empty:
                _eq_csv["time"] = _eq_csv["time"].astype(str)
            st.download_button(
                "Download Equity Curve CSV",
                data=_eq_csv.to_csv(index=False).encode("utf-8"),
                file_name="grid_backtest_equity_curve.csv",
                mime="text/csv",
                key="dl_grid_bt_equity",
            )
        with dl3:
            st.download_button(
                "Download Monthly CSV",
                data=_mo_df.to_csv(index=False).encode("utf-8"),
                file_name="grid_backtest_monthly_walkforward.csv",
                mime="text/csv",
                key="dl_grid_bt_monthly",
            )

    # ─────────────────────────────────────────────────────────────
    # SECTION 8 — How Grid Trading Works
    # ─────────────────────────────────────────────────────────────
    with st.expander("ℹ️ How Grid Trading Works", expanded=False):
        st.markdown("""
**Grid trading** places small-lot orders at regular price intervals above and below the current price,
profiting from oscillation in both directions.

**AI Direction Analysis:**
- Counts recent ICT bullish vs bearish signals
- Evaluates EMA(20) vs EMA(50) slope and crossover
- Classifies regime: TRENDING / RANGING / VOLATILE
- Weighs London/NY sessions higher (more liquid)
- Output: BULLISH / BEARISH / NEUTRAL bias with 0–100% confidence

**Adaptive Grid Levels:**
- Neutral grid: equal buy levels below price + sell levels above
- Directional: AI skews extra levels toward detected bias direction
- Lot scaling: slightly larger lots toward bias, smaller on counter-direction levels
- Spacing: ATR × multiplier (Brain auto-tunes multiplier over time)

**AI Brain (Self-Learning):**
- Every closed trade is logged to `grid_audit_log.jsonl`
- Brain learns **optimal spacing multiplier** per symbol and market regime
- Brain tracks **direction accuracy** — was the AI bias correct?
- After 5+ trades per regime, the brain overrides the manual multiplier
- Learning rate: slow EMA (α=0.15) for stability

**Risk Controls:**
- Base lot is small (default 0.01 = micro-lot)
- SL is wide (SL multiplier × ATR spacing) to survive oscillation
- Max open levels cap prevents over-exposure
- Kill-switch: Deactivate Grid removes all PENDING levels instantly
- Open positions remain until TP/SL hit or manual close
        """)
