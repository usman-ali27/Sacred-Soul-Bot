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
    connect_mt5,
    disconnect_mt5,
    get_account_info,
    get_open_positions,
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

page = st.sidebar.radio(
    "Navigate",
    ["Live Analysis", "Performance", "Prop Firm", "MT5 Auto-Trade"],
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
if auto_refresh:
    refresh_count = st_autorefresh(
        interval=refresh_interval * 1000,
        key="auto_refresh_timer",
    )
    st.sidebar.caption(f"🔄 Refreshes every **{refresh_interval}s** (cycle #{refresh_count})")
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


@st.cache_data(ttl=10, show_spinner=False)
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

    return {
        "window_events": total,
        "filled": filled,
        "failed": failed,
        "blocked": blocked,
        "fill_rate": round(fill_rate, 1),
    }


# ===================================================================
# MT5 shared state — available to ALL tabs
# ===================================================================
# Auto-connect from saved credentials (runs once per session)
saved_creds = load_credentials()
if not st.session_state.get("mt5_connected") and saved_creds and saved_creds["login"] > 0:
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
                                     int(mt5_session_start_edit), int(mt5_session_end_edit))
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
                                        session_end_utc=int(mt5_session_end_edit))
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
            value=float(worker_cfg.get("lot_size", mode_cfg.get("default_lot", 0.01))),
            min_value=0.01,
            max_value=float(mt5_max_lot),
            step=0.01,
        )

        if st.button("💾 Save Worker Config"):
            new_worker_cfg = {
                "enabled": bool(worker_enabled),
                "auto_trade_enabled": bool(worker_auto_trade),
                "symbol": symbol,
                "timeframe": timeframe,
                "concepts": selected_concepts,
                "rr": float(rr),
                "sweep_lookback": int(sweep_lookback),
                "lot_size": float(worker_lot),
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

            st.dataframe(pos_df, use_container_width=True, hide_index=True)

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

        _def_lot = mode_cfg.get("default_lot", 0.01)
        trade_lot = st.number_input(
            "Lot Size",
            value=min(_def_lot, mt5_max_lot),
            step=0.01,
            min_value=0.01,
            max_value=mt5_max_lot,
        )
        st.caption("Default is mode-based. Manual lot is fastest for auto-refresh execution.")

        # Keep AI sizing available, but compute only on demand (not every refresh).
        ai_key = f"ai_rec_{symbol}_{timeframe}_{trading_mode}_{concepts_key}_{rr}_{sweep_lookback}"
        if st.button("🧠 Recalculate AI Lot (On Demand)"):
            bt_signals = load_signals(symbol, timeframe, concepts_key, rr, sweep_lookback)
            if bt_signals.empty:
                st.warning("No backtest signals available for AI lot sizing.")
            else:
                bt_stats = compute_stats(bt_signals)
                _mt5_bal = acc["balance"] if acc else mode_cfg.get("default_balance", 10_000)
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
        st.subheader(f"Live Signal Monitor — {symbol} {timeframe} ({trading_mode})")

        live_signals = load_live_signals(symbol, timeframe, concepts_key, rr, sweep_lookback)
        if live_signals.empty:
            st.info("No fresh signals in the live window.")
            latest_sig = None
        else:
            recent_live = live_signals.tail(5).copy()
            st.dataframe(
                recent_live[["signal_time", "direction", "entry", "sl", "tp",
                             "concepts_used", "status", "result"]],
                use_container_width=True,
                hide_index=True,
            )
            reference_ts = load_data(symbol, timeframe).index.max()
            latest_sig = get_latest_fresh_open_signal(live_signals, timeframe, reference_ts)

        auto_trade_enabled = st.checkbox(
            "⚡ Enable Auto-Trade on Fresh Signals",
            value=not worker_enabled,
            disabled=worker_enabled,
            help="Executes only recent OPEN signals in the live window; ignores old historical setups.",
        )
        if worker_enabled:
            st.info("Worker mode is enabled. In-app auto-trade is disabled to avoid duplicate orders.")
        if auto_trade_enabled and not auto_refresh:
            st.info("Enable Auto-Refresh in the sidebar so fresh signals are checked automatically.")

        if latest_sig is not None:
            price_info = ""
            if live:
                cur_price = live["ask"] if latest_sig["direction"] == "LONG" else live["bid"]
                diff = abs(cur_price - latest_sig["entry"])
                price_info = f" | **Live:** {cur_price:.2f} (Δ {diff:.2f})"

            st.markdown(
                f"**Fresh Signal:** {latest_sig['direction']} @ "
                f"{latest_sig['entry']:.2f} | SL: {latest_sig['sl']:.2f} | "
                f"TP: {latest_sig['tp']:.2f} | "
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
                    comment=f"ICT {trading_mode}",
                )
                if result.success:
                    st.success(f"✅ Trade executed! {result.message}")
                else:
                    st.error(f"❌ Trade failed: {result.message}")

            if auto_trade_enabled:
                sig_key = (
                    f"executed_{symbol}_{timeframe}_{latest_sig['signal_time']}_"
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
                        comment=f"ICT Auto {trading_mode}",
                    )
                    st.session_state[sig_key] = True
                    if result.success:
                        st.success(f"🤖 Auto-trade executed! {result.message}")
                    else:
                        st.error(f"🤖 Auto-trade failed: {result.message}")
        else:
            st.info("No fresh OPEN signal right now.")

        # ── Trade Log / Audit ───────────────────────────────────
        st.markdown("---")
        st.subheader("Execution Audit")
        log_entries = trade_log.to_list()
        if log_entries:
            st.caption("Session log (current runtime)")
            st.dataframe(pd.DataFrame(log_entries), use_container_width=True,
                         hide_index=True)
        else:
            st.info("No trades executed in this session.")

        audit_entries = load_audit_log(limit=200)
        if audit_entries:
            st.markdown("---")
            st.subheader("Execution Ops (Last 24h)")
            ops = summarize_audit_events(audit_entries, hours=24)
            oc1, oc2, oc3, oc4, oc5 = st.columns(5)
            oc1.metric("Events", ops["window_events"])
            oc2.metric("Filled", ops["filled"])
            oc3.metric("Failed", ops["failed"])
            oc4.metric("Blocked", ops["blocked"])
            oc5.metric("Fill Rate", f"{ops['fill_rate']}%")

            st.caption("Persistent audit log (last 200 events)")
            st.dataframe(pd.DataFrame(audit_entries), use_container_width=True,
                         hide_index=True)
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
