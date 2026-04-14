"""
ICT Trading Bot — Flexible Concept Selection Dashboard

The system is **flexible by design**: users choose which ICT concepts
must be present for a trade entry.  No hard-coded "all concepts required".
Tick any subset of concepts in the sidebar → the backtest re-runs
dynamically.  If results are sparse, simply un-tick some boxes.

Run with:
    streamlit run app.py
"""

import streamlit as st
import pandas as pd

from config import ALL_CONCEPTS, INSTRUMENTS, PRESETS
from data_fetcher import fetch_ohlcv
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
from scenario_backtest import (
    run_full_backtest,
    best_per_instrument,
    best_overall,
    ALL_SCENARIOS,
)

# ===================================================================
# Page config
# ===================================================================
st.set_page_config(page_title="ICT Trading Bot", page_icon="📊", layout="wide")

# ===================================================================
# Sidebar
# ===================================================================
st.sidebar.title("ICT Trading Bot")

page = st.sidebar.radio("Navigate", ["Live Analysis", "Performance History", "Prop Firm Tracker", "Scenario Comparison"])

st.sidebar.markdown("---")
st.sidebar.subheader("Market")
symbol = st.sidebar.selectbox("Instrument", list(INSTRUMENTS.keys()))
timeframe = st.sidebar.selectbox("Timeframe", ["15m", "1h", "4h", "Daily"])

st.sidebar.markdown("---")
st.sidebar.subheader("Strategy Parameters")
rr = st.sidebar.slider("Risk : Reward", min_value=1.0, max_value=5.0, value=2.0, step=0.5)
sweep_lookback = st.sidebar.slider("Sweep lookback (bars)", min_value=5, max_value=60, value=20)

# ── Concept multi-select ─────────────────────────────────────────
st.sidebar.markdown("---")
st.sidebar.subheader("Required Concepts for Entry")
st.sidebar.caption(
    "Tick the concepts that **must** all be true for a signal. "
    "Fewer ticks → more trades (less strict)."
)

# Scenario presets
preset = st.sidebar.selectbox("Scenario Preset", ["(custom)"] + list(PRESETS.keys()))
if preset != "(custom)":
    default_concepts = PRESETS[preset]
else:
    default_concepts = ["Liquidity Sweep", "MSS"]

# Persist selection across preset changes
selected_concepts: list[str] = []
for c in ALL_CONCEPTS:
    val = st.sidebar.checkbox(c, value=(c in default_concepts), key=f"concept_{c}")
    if val:
        selected_concepts.append(c)

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

# ── User guide ───────────────────────────────────────────────────
with st.sidebar.expander("📖 User Guide"):
    st.markdown("""
**How it works**

1. **Pick an instrument & timeframe** from the dropdowns above.
2. **Select which ICT concepts** must *all* be confirmed before an
   entry signal is generated.  Use a preset or tick boxes manually.
3. **Adjust R:R and lookback** to taste.
4. The dashboard will compute *all* 10 ICT concepts on the chart
   and show/hide overlays via the toggles.
5. Only the **ticked concepts** gate trade entry — everything else
   is displayed for context.

**Concepts explained (briefly)**

| Concept | What it detects |
|---------|----------------|
| FVG | 3-candle price imbalance |
| MSS | Break of swing high/low + displacement |
| OB | Last candle before a strong move |
| OTE | 62–79 % Fibonacci retracement zone |
| SSL/BSL | Clustered equal lows / highs |
| Liq. Sweep | Wick into liquidity then reversal |
| PO3 | Asian accumulation → London manipulation → NY distribution |
| Breaker | Failed order block turned S/R |
| Mitigation | Return to OB / FVG / breaker zone |
| Order Flow | CVD slope confirms direction |

**Tip:** If no trades appear, *un-tick* some concepts to relax the
filter.  Conversely, tick more for higher-quality (but rarer) setups.
""")

# ===================================================================
# Data loading (cached 5 min)
# ===================================================================


@st.cache_data(ttl=300, show_spinner="Fetching market data …")
def load_data(sym: str, tf: str) -> pd.DataFrame:
    return fetch_ohlcv(sym, tf)


@st.cache_data(ttl=300, show_spinner="Generating signals …")
def load_signals(sym: str, tf: str, concepts_key: str,
                 _rr: float, _lookback: int) -> pd.DataFrame:
    df = load_data(sym, tf)
    if df.empty:
        return pd.DataFrame()
    concepts = concepts_key.split("|") if concepts_key else []
    return generate_signals(df, concepts, rr_ratio=_rr, sweep_lookback=_lookback)


# Stable cache key for selected concepts
concepts_key = "|".join(sorted(selected_concepts))

# ===================================================================
# PAGE: Live Analysis
# ===================================================================
if page == "Live Analysis":
    st.header(f"Live Analysis — {symbol} {timeframe}")
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
# PAGE: Performance History
# ===================================================================
elif page == "Performance History":
    st.header("Performance History")
    st.info(
        "Aggregated backtest across all instruments & timeframes "
        f"using concepts: **{', '.join(selected_concepts) or '(none)'}** | R:R = {rr}"
    )

    all_sigs: list[pd.DataFrame] = []
    combos = [(s, t) for s in INSTRUMENTS for t in ["15m", "1h", "4h", "Daily"]]
    bar = st.progress(0)

    for idx, (sym, tf) in enumerate(combos):
        try:
            sigs = load_signals(sym, tf, concepts_key, rr, sweep_lookback)
            if not sigs.empty:
                sigs = sigs.copy()
                sigs["symbol"] = sym
                sigs["timeframe"] = tf
                all_sigs.append(sigs)
        except Exception:
            pass
        bar.progress((idx + 1) / len(combos))
    bar.empty()

    if not all_sigs:
        st.warning("No signals found. Try relaxing the concept filter.")
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

    # Charts
    col_l, col_r = st.columns(2)
    with col_l:
        st.plotly_chart(equity_curve_fig(combined), use_container_width=True)
    with col_r:
        st.plotly_chart(win_loss_pie(combined), use_container_width=True)

    st.plotly_chart(drawdown_fig(combined), use_container_width=True)

    # Concept combination comparison
    st.subheader("Win Rate by Concept Combination")
    st.plotly_chart(concept_comparison_fig(combined), use_container_width=True)

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
elif page == "Prop Firm Tracker":
    st.header("Prop Firm Tracker — Funding Pips")

    # ── Account settings ──────────────────────────────────────────
    st.subheader("Account Settings")
    ac1, ac2, ac3, ac4, ac5 = st.columns(5)
    starting_balance = ac1.number_input("Starting Balance ($)", value=10_000, step=500)
    current_balance = ac2.number_input("Current Balance ($)", value=9_800, step=50)
    max_total_dd = ac3.number_input("Max Total DD (%)", value=10.0, step=0.5)
    max_daily_loss = ac4.number_input("Max Daily Loss (%)", value=5.0, step=0.5)
    risk_per_trade = ac5.number_input("Risk per Trade (%)", value=1.0, step=0.25)

    # ── Live account status ───────────────────────────────────────
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
    s3.metric("DD Buffer Left", f"${dd_buffer:,.0f} ({dd_buffer_pct:.1f}%)",
              delta_color="normal")
    s4.metric("Daily Loss Limit", f"${daily_limit:,.0f}")

    if dd_buffer <= 0:
        st.error("⚠️ ACCOUNT BREACHED — You have hit or exceeded the maximum drawdown!")
    elif dd_buffer_pct <= 2:
        st.error("🔴 CRITICAL — Less than 2% buffer remaining. Stop trading and review!")
    elif dd_buffer_pct <= 4:
        st.warning("🟡 CAUTION — Buffer is getting tight. Reduce risk or take smaller setups.")
    else:
        st.success("🟢 Account is within safe limits.")

    # ── Safe lot sizing calculator ────────────────────────────────
    st.markdown("---")
    st.subheader("Safe Position Sizing")
    lc1, lc2 = st.columns(2)
    sl_pips = lc1.number_input("Stop Loss (pips)", value=20.0, step=1.0)
    pip_value = lc2.number_input("Pip Value ($)", value=10.0, step=0.5,
                                  help="$10/pip for XAUUSD standard lot, $10 for EURUSD standard lot")

    lot_info = safe_lot_size(current_balance, risk_per_trade / 100, sl_pips, pip_value)
    lm1, lm2, lm3, lm4 = st.columns(4)
    lm1.metric("Max Risk ($)", f"${lot_info['risk_dollar']:.2f}")
    lm2.metric("Lot Size", f"{lot_info['lot_size']:.2f}")
    lm3.metric("Micro Lots", f"{lot_info['micro_lots']}")
    lm4.metric("Max Consecutive Losses",
               f"{int(dd_buffer / lot_info['risk_dollar'])}" if lot_info['risk_dollar'] > 0 else "∞",
               help="How many losses in a row before breaching")

    # ── Backtest simulation with prop firm rules ──────────────────
    st.markdown("---")
    st.subheader("Simulated Backtest with Prop Firm Rules")
    st.caption(
        f"Simulates your strategy ({', '.join(selected_concepts) or 'none'}) "
        f"against prop firm constraints to check for breaches."
    )

    # Run backtest on selected instrument
    signals = load_signals(symbol, timeframe, concepts_key, rr, sweep_lookback)

    if signals.empty:
        st.info("No signals found for the current settings. Try a different instrument/timeframe or relax concept filters.")
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

        # Summary metrics
        sm1, sm2, sm3, sm4, sm5 = st.columns(5)
        sm1.metric("Simulated Trades", summary["total_trades"])
        sm2.metric("Final Balance", f"${summary['final_equity']:,.0f}")
        sm3.metric("DD Buffer Left", f"${summary['remaining_dd_buffer']:,.0f}")
        sm4.metric("Max Consec. Losses", summary["consecutive_losses"])
        sm5.metric("Breached?",
                    "YES ⛔" if summary["breached"] else "NO ✅")

        if summary["breached"]:
            st.error(
                f"⚠️ This strategy BREACHES the account! "
                f"Breach reason: {summary.get('breach_reason', 'Drawdown exceeded')}. "
                f"Reduce risk per trade or tighten concept filters."
            )

        # Charts
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
        st.subheader("Recommendations")
        recs = []
        if summary["breached"]:
            recs.append("❌ **Reduce risk per trade** — current settings breach the account in simulation.")
            if risk_per_trade > 0.5:
                recs.append(f"💡 Try lowering risk to {max(0.25, risk_per_trade - 0.5):.2f}%.")
        if summary["consecutive_losses"] >= 3:
            recs.append("⚠️ Strategy shows 3+ consecutive losses — consider adding more concept filters for higher-quality entries.")
        if dd_buffer_pct <= 4:
            recs.append("🔴 Your DD buffer is tight. Use **minimum position sizes** and only take A+ setups.")
        if not summary["breached"] and dd_buffer_pct > 4:
            recs.append("✅ Strategy looks safe under current prop firm rules.")
            recs.append(f"📊 You can sustain ~{int(dd_buffer / lot_info['risk_dollar'])} consecutive losses before breach." if lot_info['risk_dollar'] > 0 else "")
        for r in recs:
            if r:
                st.markdown(r)


# ===================================================================
# PAGE: Scenario Comparison — find the best R:R
# ===================================================================
elif page == "Scenario Comparison":
    st.header("Scenario Comparison — Find the Best R:R")
    st.caption(
        "Backtests **15 different concept combos** across all instruments, "
        "timeframes, and R:R values to find the highest-performing setups."
    )

    # Controls
    sc1, sc2, sc3 = st.columns(3)
    with sc1:
        sel_instruments = st.multiselect(
            "Instruments",
            list(INSTRUMENTS.keys()),
            default=list(INSTRUMENTS.keys()),
        )
    with sc2:
        sel_timeframes = st.multiselect(
            "Timeframes", ["15m", "1h", "4h", "Daily"],
            default=["1h", "4h", "Daily"],
        )
    with sc3:
        sel_rr = st.multiselect(
            "R:R Values", [1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0],
            default=[1.5, 2.0, 2.5, 3.0],
        )

    if st.button("🚀 Run Scenario Backtest", type="primary"):
        filtered_instruments = {k: v for k, v in INSTRUMENTS.items() if k in sel_instruments}
        bar = st.progress(0, text="Running backtest...")

        def _update(cur, total):
            if total > 0:
                bar.progress(cur / total, text=f"Testing combo {cur}/{total}...")

        results = run_full_backtest(
            scenarios=ALL_SCENARIOS,
            instruments=filtered_instruments,
            timeframes=sel_timeframes,
            rr_values=sel_rr,
            progress_callback=_update,
        )
        bar.empty()

        if results.empty:
            st.warning("No combos produced ≥ 3 trades. Try broader settings.")
            st.stop()

        st.session_state["scenario_results"] = results

    # Display results if available
    if "scenario_results" in st.session_state:
        results = st.session_state["scenario_results"]

        # ── Top 10 overall ────────────────────────────────────────
        st.subheader("🏆 Top 10 Best Scenarios (by Avg R)")
        top10 = best_overall(results, 10)
        st.dataframe(
            top10[["scenario", "instrument", "timeframe", "rr_ratio",
                   "trades", "win_rate", "avg_pnl_r", "profit_factor",
                   "sharpe", "max_drawdown"]],
            use_container_width=True,
            hide_index=False,
        )

        # Highlight the #1
        best = top10.iloc[0]
        st.success(
            f"**Best combo:** {best['scenario']} on **{best['instrument']} "
            f"{best['timeframe']}** at **{best['rr_ratio']}R** — "
            f"Win Rate {best['win_rate']}%, Avg R {best['avg_pnl_r']}, "
            f"PF {best['profit_factor']}, Sharpe {best['sharpe']}"
        )

        # ── Best per instrument ───────────────────────────────────
        st.subheader("📊 Best Scenario per Instrument")
        per_inst = best_per_instrument(results)
        st.dataframe(
            per_inst[["instrument", "scenario", "timeframe", "rr_ratio",
                       "trades", "win_rate", "avg_pnl_r", "profit_factor",
                       "sharpe", "max_drawdown"]],
            use_container_width=True,
            hide_index=True,
        )

        # ── Charts ────────────────────────────────────────────────
        import plotly.express as px

        st.subheader("Avg R by Scenario")
        # Aggregate by scenario
        scenario_agg = (
            results.groupby("scenario")
            .agg({"avg_pnl_r": "mean", "win_rate": "mean", "trades": "sum",
                  "profit_factor": "mean"})
            .sort_values("avg_pnl_r", ascending=True)
            .reset_index()
        )
        fig_bar = px.bar(
            scenario_agg, x="avg_pnl_r", y="scenario",
            orientation="h",
            color="avg_pnl_r",
            color_continuous_scale=["#ff4444", "#ffaa00", "#00cc66"],
            text="avg_pnl_r",
        )
        fig_bar.update_layout(
            template="plotly_dark", height=max(400, len(scenario_agg) * 35),
            xaxis_title="Average R", yaxis_title="",
            coloraxis_showscale=False,
        )
        fig_bar.update_traces(texttemplate="%{text:.2f}R", textposition="outside")
        st.plotly_chart(fig_bar, use_container_width=True)

        # Win rate vs Avg R scatter
        st.subheader("Win Rate vs Avg R (all combos)")
        fig_scatter = px.scatter(
            results, x="win_rate", y="avg_pnl_r",
            color="instrument", symbol="timeframe",
            size="trades", hover_data=["scenario", "rr_ratio", "profit_factor"],
            labels={"win_rate": "Win Rate (%)", "avg_pnl_r": "Avg R"},
        )
        fig_scatter.update_layout(template="plotly_dark", height=500)
        st.plotly_chart(fig_scatter, use_container_width=True)

        # R:R heatmap — scenario × rr_ratio
        st.subheader("Heatmap: Scenario × R:R Ratio")
        heatmap_data = (
            results.groupby(["scenario", "rr_ratio"])["avg_pnl_r"]
            .mean()
            .reset_index()
        )
        pivot = heatmap_data.pivot(index="scenario", columns="rr_ratio", values="avg_pnl_r")
        fig_heat = px.imshow(
            pivot, text_auto=".2f",
            color_continuous_scale="RdYlGn",
            labels={"color": "Avg R"},
            aspect="auto",
        )
        fig_heat.update_layout(template="plotly_dark", height=max(400, len(pivot) * 30))
        st.plotly_chart(fig_heat, use_container_width=True)

        # ── Full results table ────────────────────────────────────
        st.subheader("Full Results Table")
        sort_by = st.selectbox("Sort by", ["avg_pnl_r", "win_rate", "profit_factor", "sharpe", "trades"], index=0)
        st.dataframe(
            results.sort_values(sort_by, ascending=False),
            use_container_width=True,
            hide_index=False,
        )
