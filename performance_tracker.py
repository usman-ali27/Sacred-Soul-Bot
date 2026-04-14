"""
Performance Tracker — statistics, equity curve, drawdown, concept comparison.

All figures use Plotly with the ``plotly_dark`` template.
PnL is expressed in R-multiples (risk units) for comparability.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go


# ===================================================================
# Statistics
# ===================================================================


def compute_stats(signals: pd.DataFrame) -> dict:
    """High-level performance statistics.

    Returns dict with: total_trades, wins, losses, be_trades,
    open_trades, win_rate, avg_pnl_r, max_drawdown, profit_factor, sharpe.
    """
    closed = signals[signals["status"].isin(["CLOSED", "BE"])].copy()
    open_n = int((signals["status"] == "OPEN").sum()) if "status" in signals.columns else 0
    if closed.empty:
        return dict(total_trades=0, wins=0, losses=0, be_trades=0,
                    open_trades=open_n, win_rate=0.0, avg_pnl_r=0.0,
                    max_drawdown=0.0, profit_factor=0.0, sharpe=0.0)

    wins = int((closed["result"] == "WIN").sum())
    losses = int((closed["result"] == "LOSS").sum())
    be = int((closed["result"] == "BE").sum())

    closed = closed.copy()
    closed["pnl_r"] = closed.apply(
        lambda r: r["pnl"] / r["risk"] if r["risk"] != 0 else 0, axis=1
    )
    eq = closed["pnl_r"].cumsum()
    dd = eq - eq.cummax()
    max_dd = float(dd.min()) if len(dd) else 0.0

    gross_profit = closed.loc[closed["pnl_r"] > 0, "pnl_r"].sum()
    gross_loss = abs(closed.loc[closed["pnl_r"] < 0, "pnl_r"].sum())
    pf = round(gross_profit / gross_loss, 2) if gross_loss > 0 else float("inf")

    avg = closed["pnl_r"].mean()
    std = closed["pnl_r"].std()
    sharpe = round(avg / std, 2) if std > 0 else 0.0

    total = len(closed)
    return dict(
        total_trades=total,
        wins=wins,
        losses=losses,
        be_trades=be,
        open_trades=open_n,
        win_rate=round(wins / total * 100, 1) if total else 0.0,
        avg_pnl_r=round(float(avg), 2),
        max_drawdown=round(max_dd, 2),
        profit_factor=pf,
        sharpe=sharpe,
    )


# ===================================================================
# Plotly figures
# ===================================================================


def equity_curve_fig(signals: pd.DataFrame) -> go.Figure:
    """Cumulative R equity curve."""
    closed = signals[signals["status"].isin(["CLOSED", "BE"])].copy()
    if closed.empty:
        fig = go.Figure()
        fig.update_layout(title="Equity Curve (no closed trades)")
        return fig
    closed = closed.sort_values("signal_time")
    closed["pnl_r"] = closed.apply(
        lambda r: r["pnl"] / r["risk"] if r["risk"] != 0 else 0, axis=1)
    closed["cum_r"] = closed["pnl_r"].cumsum()
    fig = go.Figure(go.Scatter(
        x=closed["signal_time"], y=closed["cum_r"],
        mode="lines+markers", name="Equity (R)",
        line=dict(color="#00c896", width=2)))
    fig.update_layout(title="Equity Curve (R-multiples)",
                      xaxis_title="Time", yaxis_title="Cumulative R",
                      template="plotly_dark", height=400)
    return fig


def drawdown_fig(signals: pd.DataFrame) -> go.Figure:
    """Drawdown in R-multiples."""
    closed = signals[signals["status"].isin(["CLOSED", "BE"])].copy()
    if closed.empty:
        fig = go.Figure()
        fig.update_layout(title="Drawdown (no data)")
        return fig
    closed = closed.sort_values("signal_time")
    closed["pnl_r"] = closed.apply(
        lambda r: r["pnl"] / r["risk"] if r["risk"] != 0 else 0, axis=1)
    eq = closed["pnl_r"].cumsum()
    dd = eq - eq.cummax()
    fig = go.Figure(go.Scatter(
        x=closed["signal_time"], y=dd,
        fill="tozeroy", mode="lines", name="Drawdown (R)",
        line=dict(color="#ff4d4d", width=1)))
    fig.update_layout(title="Drawdown (R-multiples)",
                      xaxis_title="Time", yaxis_title="DD",
                      template="plotly_dark", height=300)
    return fig


def win_loss_pie(signals: pd.DataFrame) -> go.Figure:
    """Win / Loss / BE pie chart."""
    closed = signals[signals["status"].isin(["CLOSED", "BE"])]
    if closed.empty:
        fig = go.Figure()
        fig.update_layout(title="Outcomes (no data)")
        return fig
    counts = closed["result"].value_counts()
    fig = go.Figure(go.Pie(
        labels=counts.index.tolist(), values=counts.values.tolist(),
        marker=dict(colors=["#00c896", "#ff4d4d", "#ffc107"]), hole=0.4))
    fig.update_layout(title="Trade Outcomes", template="plotly_dark", height=350)
    return fig


def concept_comparison_fig(signals: pd.DataFrame) -> go.Figure:
    """Bar chart of win-rate per concept combination used."""
    closed = signals[signals["status"].isin(["CLOSED", "BE"])].copy()
    if closed.empty or "concepts_used" not in closed.columns:
        fig = go.Figure()
        fig.update_layout(title="Concept Comparison (no data)")
        return fig

    groups = closed.groupby("concepts_used")
    data = []
    for name, grp in groups:
        total = len(grp)
        wins = (grp["result"] == "WIN").sum()
        wr = round(wins / total * 100, 1) if total else 0.0
        data.append({"combo": name, "win_rate": wr, "trades": total})

    cdf = pd.DataFrame(data).sort_values("win_rate", ascending=False)
    fig = go.Figure(go.Bar(
        x=cdf["combo"], y=cdf["win_rate"],
        text=cdf["trades"].apply(lambda t: f"n={t}"), textposition="auto",
        marker_color="#22d3ee"))
    fig.update_layout(title="Win Rate by Concept Combination",
                      xaxis_title="Concepts", yaxis_title="Win Rate %",
                      template="plotly_dark", height=400)
    return fig
