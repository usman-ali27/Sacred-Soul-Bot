"""
Prop Firm Risk Manager — Funding Pips account protection.

Simulates the strategy on a prop firm account with real constraints:
  - Starting / current balance
  - Max total drawdown (absolute floor)
  - Max daily loss limit
  - Position sizing per trade (% of equity risked)

Outputs:
  - Trade-by-trade equity curve in $ with breach detection
  - Safe lot-size calculator
  - Daily P&L breakdown
  - Risk-adjusted recommendations
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go


# ===================================================================
# Prop firm account simulation
# ===================================================================


def simulate_prop_account(
    signals: pd.DataFrame,
    starting_balance: float,
    current_balance: float,
    max_total_dd_pct: float,       # e.g. 0.10 for 10%
    max_daily_loss_pct: float,     # e.g. 0.05 for 5%
    risk_per_trade_pct: float,     # e.g. 0.01 for 1%
) -> pd.DataFrame:
    """Walk through signals and simulate $ equity on a prop firm account.

    For each trade:
      - risk$ = equity × risk_per_trade_pct
      - pnl$  = risk$ × (pnl / risk)   (R-multiple → dollars)
      - Check daily loss and total drawdown after each trade.

    Returns DataFrame with columns:
      signal_time, direction, entry, sl, tp, concepts_used, result,
      risk_dollar, pnl_dollar, equity, daily_pnl, breached, breach_reason
    """
    closed = signals[signals["status"].isin(["CLOSED", "BE"])].copy()
    if closed.empty:
        return pd.DataFrame()

    closed = closed.sort_values("signal_time").reset_index(drop=True)

    equity = current_balance
    dd_floor = starting_balance * (1 - max_total_dd_pct)
    daily_limit = starting_balance * max_daily_loss_pct

    rows = []
    daily_pnl_tracker: dict[str, float] = {}

    for _, sig in closed.iterrows():
        pnl_r = sig["pnl"] / sig["risk"] if sig["risk"] != 0 else 0
        risk_dollar = equity * risk_per_trade_pct
        pnl_dollar = risk_dollar * pnl_r

        equity += pnl_dollar
        day_key = str(sig["signal_time"])[:10]
        daily_pnl_tracker[day_key] = daily_pnl_tracker.get(day_key, 0) + pnl_dollar
        daily_pnl = daily_pnl_tracker[day_key]

        breached = False
        breach_reason = ""
        if equity <= dd_floor:
            breached = True
            breach_reason = f"Total DD breach (equity ${equity:.2f} < floor ${dd_floor:.2f})"
        elif abs(daily_pnl) >= daily_limit and daily_pnl < 0:
            breached = True
            breach_reason = f"Daily loss breach (${daily_pnl:.2f} exceeds -${daily_limit:.2f})"

        rows.append({
            "signal_time": sig["signal_time"],
            "direction": sig["direction"],
            "entry": sig["entry"],
            "sl": sig["sl"],
            "tp": sig["tp"],
            "concepts_used": sig.get("concepts_used", ""),
            "result": sig["result"],
            "pnl_r": round(pnl_r, 2),
            "risk_dollar": round(risk_dollar, 2),
            "pnl_dollar": round(pnl_dollar, 2),
            "equity": round(equity, 2),
            "daily_pnl": round(daily_pnl, 2),
            "breached": breached,
            "breach_reason": breach_reason,
        })

        if breached:
            break  # account blown — stop simulation

    return pd.DataFrame(rows)


# ===================================================================
# Safe position size calculator
# ===================================================================


def safe_lot_size(
    current_balance: float,
    risk_per_trade_pct: float,
    sl_pips: float,
    pip_value: float = 10.0,  # $/pip for 1 standard lot
) -> dict:
    """Calculate the maximum safe lot size.

    Args:
        current_balance:    Account equity in $.
        risk_per_trade_pct: Risk % per trade (e.g. 0.01).
        sl_pips:            Stop-loss distance in pips.
        pip_value:          Dollar value per pip per standard lot.

    Returns:
        dict with risk_dollar, lot_size, micro_lots.
    """
    risk_dollar = current_balance * risk_per_trade_pct
    if sl_pips <= 0 or pip_value <= 0:
        return {"risk_dollar": round(risk_dollar, 2), "lot_size": 0, "micro_lots": 0}
    lot_size = risk_dollar / (sl_pips * pip_value)
    return {
        "risk_dollar": round(risk_dollar, 2),
        "lot_size": round(lot_size, 4),
        "micro_lots": round(lot_size * 100, 2),  # 1 lot = 100 micro
    }


# ===================================================================
# Account summary stats
# ===================================================================


def account_summary(sim_df: pd.DataFrame, starting_balance: float,
                    current_balance: float, max_total_dd_pct: float,
                    max_daily_loss_pct: float) -> dict:
    """Compute prop-firm-specific summary."""
    if sim_df.empty:
        return {
            "total_trades": 0, "total_pnl": 0, "final_equity": current_balance,
            "peak_equity": current_balance, "max_dd_dollar": 0,
            "max_dd_pct": 0, "worst_daily_loss": 0, "breached": False,
            "remaining_dd_buffer": current_balance - starting_balance * (1 - max_total_dd_pct),
            "remaining_daily_buffer": starting_balance * max_daily_loss_pct,
            "consecutive_losses": 0,
        }

    final_eq = sim_df.iloc[-1]["equity"]
    peak_eq = sim_df["equity"].max()
    min_eq = sim_df["equity"].min()
    max_dd_dollar = peak_eq - min_eq
    max_dd_pct = (max_dd_dollar / peak_eq * 100) if peak_eq > 0 else 0
    worst_daily = sim_df["daily_pnl"].min()
    breached = sim_df["breached"].any()
    dd_floor = starting_balance * (1 - max_total_dd_pct)
    daily_limit = starting_balance * max_daily_loss_pct

    # Consecutive losses
    results = sim_df["result"].tolist()
    max_consec = 0
    curr_consec = 0
    for r in results:
        if r in ("LOSS", "BE"):
            curr_consec += 1
            max_consec = max(max_consec, curr_consec)
        else:
            curr_consec = 0

    return {
        "total_trades": len(sim_df),
        "total_pnl": round(final_eq - current_balance, 2),
        "final_equity": round(final_eq, 2),
        "peak_equity": round(peak_eq, 2),
        "max_dd_dollar": round(max_dd_dollar, 2),
        "max_dd_pct": round(max_dd_pct, 2),
        "worst_daily_loss": round(worst_daily, 2),
        "breached": breached,
        "remaining_dd_buffer": round(final_eq - dd_floor, 2),
        "remaining_daily_buffer": round(daily_limit, 2),
        "consecutive_losses": max_consec,
    }


# ===================================================================
# Plotly figures for prop firm tracking
# ===================================================================


def prop_equity_fig(sim_df: pd.DataFrame, starting_balance: float,
                    max_total_dd_pct: float) -> go.Figure:
    """Equity curve with drawdown floor line."""
    fig = go.Figure()
    if sim_df.empty:
        fig.update_layout(title="Prop Firm Equity (no data)")
        return fig

    dd_floor = starting_balance * (1 - max_total_dd_pct)

    fig.add_trace(go.Scatter(
        x=sim_df["signal_time"], y=sim_df["equity"],
        mode="lines+markers", name="Equity ($)",
        line=dict(color="#00c896", width=2),
        marker=dict(
            color=["#ff4d4d" if b else "#00c896" for b in sim_df["breached"]],
            size=6,
        ),
    ))

    # Floor line
    fig.add_hline(
        y=dd_floor, line_dash="dash", line_color="#ff4d4d",
        annotation_text=f"DD Floor ${dd_floor:,.0f}",
        annotation_position="top left",
    )

    # Starting balance line
    fig.add_hline(
        y=starting_balance, line_dash="dot", line_color="#ffc107",
        annotation_text=f"Start ${starting_balance:,.0f}",
        annotation_position="bottom right",
    )

    fig.update_layout(
        title="Prop Firm Equity Curve ($)",
        xaxis_title="Time", yaxis_title="Equity ($)",
        template="plotly_dark", height=400,
    )
    return fig


def daily_pnl_fig(sim_df: pd.DataFrame, daily_limit: float) -> go.Figure:
    """Daily P&L bar chart with daily loss limit line."""
    fig = go.Figure()
    if sim_df.empty:
        fig.update_layout(title="Daily P&L (no data)")
        return fig

    # Group by day
    sim_df = sim_df.copy()
    sim_df["day"] = sim_df["signal_time"].astype(str).str[:10]
    daily = sim_df.groupby("day")["pnl_dollar"].sum().reset_index()
    daily.columns = ["day", "pnl"]

    colors = ["#00c896" if p >= 0 else "#ff4d4d" for p in daily["pnl"]]
    fig.add_trace(go.Bar(
        x=daily["day"], y=daily["pnl"], name="Daily P&L",
        marker_color=colors,
    ))

    fig.add_hline(
        y=-daily_limit, line_dash="dash", line_color="#ff4d4d",
        annotation_text=f"Daily Loss Limit -${daily_limit:,.0f}",
    )

    fig.update_layout(
        title="Daily P&L ($)",
        xaxis_title="Date", yaxis_title="P&L ($)",
        template="plotly_dark", height=350,
    )
    return fig


def risk_gauge_fig(remaining_buffer: float, total_allowed: float,
                   label: str = "DD Buffer") -> go.Figure:
    """Gauge chart showing how much drawdown room is left."""
    pct_used = max(0, 1 - remaining_buffer / total_allowed) * 100 if total_allowed > 0 else 0

    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=remaining_buffer,
        number={"prefix": "$", "font": {"size": 28}},
        delta={"reference": total_allowed, "decreasing": {"color": "#ff4d4d"}},
        title={"text": label},
        gauge={
            "axis": {"range": [0, total_allowed]},
            "bar": {"color": "#00c896" if pct_used < 60 else "#ffc107" if pct_used < 80 else "#ff4d4d"},
            "steps": [
                {"range": [0, total_allowed * 0.5], "color": "rgba(0,200,150,0.1)"},
                {"range": [total_allowed * 0.5, total_allowed * 0.8], "color": "rgba(255,193,7,0.1)"},
                {"range": [total_allowed * 0.8, total_allowed], "color": "rgba(255,77,77,0.1)"},
            ],
            "threshold": {
                "line": {"color": "#ff4d4d", "width": 3},
                "thickness": 0.8,
                "value": total_allowed * 0.9,
            },
        },
    ))
    fig.update_layout(template="plotly_dark", height=280, margin=dict(t=60, b=20))
    return fig
