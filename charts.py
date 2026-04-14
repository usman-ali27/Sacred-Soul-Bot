"""
Charting — TradingView-style interactive Plotly candlestick chart
with ICT overlays, volume bars, and order-flow subplot.

Styled to closely match TradingView: #131722 background, proper green/red
candle colors, volume overlay, crosshair, grid lines, and realistic
signal rendering with horizontal SL/TP zones.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from ict_engine import (
    compute_order_flow,
    detect_breaker_block,
    detect_fvg,
    detect_liquidity_sweep,
    detect_mitigation,
    detect_mss,
    detect_ob,
    detect_ote,
    detect_po3,
    detect_ssl_bsl,
    previous_day_high_low,
)

# ── TradingView colour palette ──────────────────────────────────
TV_BG = "#131722"
TV_GRID = "#1e222d"
TV_TEXT = "#d1d4dc"
TV_GREEN = "#26a69a"
TV_RED = "#ef5350"
TV_GREEN_FILL = "rgba(38,166,154,0.35)"
TV_RED_FILL = "rgba(239,83,80,0.35)"
TV_WICK_GREEN = "#26a69a"
TV_WICK_RED = "#ef5350"
TV_VOL_GREEN = "rgba(38,166,154,0.30)"
TV_VOL_RED = "rgba(239,83,80,0.30)"

# Zone colours (semi-transparent like TV drawings)
TV_FVG_BULL = "rgba(38,166,154,0.12)"
TV_FVG_BEAR = "rgba(239,83,80,0.12)"
TV_OB_BULL = "rgba(33,150,243,0.14)"
TV_OB_BEAR = "rgba(255,152,0,0.14)"
TV_OTE = "rgba(156,39,176,0.12)"
TV_BB_BULL = "rgba(0,188,212,0.14)"
TV_BB_BEAR = "rgba(255,87,34,0.14)"
TV_SL_COLOR = "#ef5350"
TV_TP_COLOR = "#26a69a"
TV_ENTRY_COLOR = "#2196f3"

# TradingView-like plotly layout template
TV_LAYOUT = dict(
    paper_bgcolor=TV_BG,
    plot_bgcolor=TV_BG,
    font=dict(family="Trebuchet MS, sans-serif", size=12, color=TV_TEXT),
    xaxis=dict(
        gridcolor=TV_GRID, gridwidth=1, zeroline=False,
        showline=False, tickfont=dict(color="#787b86"),
    ),
    yaxis=dict(
        gridcolor=TV_GRID, gridwidth=1, zeroline=False,
        showline=False, tickfont=dict(color="#787b86"), side="right",
    ),
    hovermode="x unified",
    dragmode="pan",
)


def _time_offset(df: pd.DataFrame, n_bars: int = 5):
    """Estimate the duration of n_bars to extend signal zones horizontally."""
    if len(df) < 2:
        return pd.Timedelta(hours=1)
    median_delta = pd.Series(df.index).diff().median()
    return median_delta * n_bars


def build_chart(
    df: pd.DataFrame,
    symbol: str,
    timeframe: str,
    signals: pd.DataFrame | None = None,
    *,
    show_fvg: bool = True,
    show_mss: bool = True,
    show_ob: bool = True,
    show_ote: bool = True,
    show_sweep: bool = True,
    show_ssl_bsl: bool = True,
    show_breaker: bool = True,
    show_mitigation: bool = True,
    show_pdhl: bool = True,
    show_po3: bool = True,
    show_order_flow: bool = True,
    max_bars: int = 300,
    max_signals: int = 20,
) -> go.Figure:
    """Build a TradingView-style ICT chart.

    Performance: trims data to the last *max_bars* for display and
    caps signal shapes at *max_signals*. ICT detectors run on the
    trimmed data only, keeping render time fast.

    Returns a Plotly Figure with up to 3 rows:
      row 1 – candlestick + ICT overlays + signal markers
      row 2 – volume bars
      row 3 – order-flow (CVD + delta)  [optional]
    """
    # ── Trim data for chart performance ──────────────────────────
    display = df.tail(max_bars).copy()

    n_rows = 3 if show_order_flow else 2
    row_heights = [0.65, 0.12, 0.23] if show_order_flow else [0.80, 0.20]

    fig = make_subplots(
        rows=n_rows, cols=1, shared_xaxes=True,
        vertical_spacing=0.02,
        row_heights=row_heights,
    )

    # ── Candlestick (hollow candles like TV) ─────────────────────
    fig.add_trace(
        go.Candlestick(
            x=display.index, open=display["Open"], high=display["High"],
            low=display["Low"], close=display["Close"], name="",
            increasing_line_color=TV_GREEN, increasing_fillcolor=TV_GREEN,
            decreasing_line_color=TV_RED, decreasing_fillcolor=TV_RED,
            line=dict(width=1),
            whiskerwidth=0.5,
        ),
        row=1, col=1,
    )

    # ── Volume bars (row 2) ──────────────────────────────────────
    vol_colors = [TV_VOL_GREEN if c >= o else TV_VOL_RED
                  for c, o in zip(display["Close"], display["Open"])]
    fig.add_trace(
        go.Bar(
            x=display.index, y=display["Volume"], name="Volume",
            marker_color=vol_colors, showlegend=False,
        ),
        row=2, col=1,
    )

    bar_dur = _time_offset(display, 8)  # width of signal zones
    chart_start = display.index[0]

    # ── PDH / PDL ────────────────────────────────────────────────
    if show_pdhl:
        pdhl = previous_day_high_low(display).dropna()
        if not pdhl.empty:
            fig.add_trace(go.Scatter(
                x=pdhl.index, y=pdhl["PDH"], mode="lines", name="PDH",
                line=dict(color="#00bcd4", width=1, dash="dash"), opacity=0.6,
            ), row=1, col=1)
            fig.add_trace(go.Scatter(
                x=pdhl.index, y=pdhl["PDL"], mode="lines", name="PDL",
                line=dict(color="#ff9800", width=1, dash="dash"), opacity=0.6,
            ), row=1, col=1)

    # ── FVG rectangles ───────────────────────────────────────────
    if show_fvg:
        fvgs = detect_fvg(display).dropna(subset=["fvg_type"]).tail(30)
        for ts, r in fvgs.iterrows():
            color = TV_FVG_BULL if r["fvg_type"] == "bullish" else TV_FVG_BEAR
            border = TV_GREEN if r["fvg_type"] == "bullish" else TV_RED
            end = ts + bar_dur
            fig.add_shape(type="rect", x0=ts, x1=end,
                          y0=r["fvg_bottom"], y1=r["fvg_top"],
                          fillcolor=color,
                          line=dict(color=border, width=0.5), layer="below",
                          row=1, col=1)

    # ── MSS markers ──────────────────────────────────────────────
    if show_mss:
        mss = detect_mss(display)
        for t, clr, sym in [("bullish", TV_GREEN, "triangle-up"),
                             ("bearish", TV_RED, "triangle-down")]:
            sub = mss[mss["mss_type"] == t].tail(30)
            if not sub.empty:
                fig.add_trace(go.Scatter(
                    x=sub.index, y=sub["mss_level"].astype(float),
                    mode="markers", name=f"MSS {t.title()}",
                    marker=dict(symbol=sym, size=10, color=clr,
                                line=dict(color="white", width=0.5)),
                ), row=1, col=1)

    # ── Order Blocks ─────────────────────────────────────────────
    if show_ob:
        obs = detect_ob(display).dropna(subset=["ob_type"]).tail(20)
        for ts, r in obs.iterrows():
            color = TV_OB_BULL if r["ob_type"] == "bullish" else TV_OB_BEAR
            border = "#2196f3" if r["ob_type"] == "bullish" else "#ff9800"
            end = ts + bar_dur
            fig.add_shape(type="rect", x0=ts, x1=end,
                          y0=r["ob_bottom"], y1=r["ob_top"],
                          fillcolor=color,
                          line=dict(color=border, width=0.8),
                          layer="below", row=1, col=1)

    # ── OTE shading ──────────────────────────────────────────────
    if show_ote:
        ote = detect_ote(display).dropna(subset=["ote_type"]).tail(15)
        for ts, r in ote.iterrows():
            end = ts + bar_dur
            fig.add_shape(type="rect", x0=ts, x1=end,
                          y0=r["ote_bottom"], y1=r["ote_top"],
                          fillcolor=TV_OTE,
                          line=dict(color="#9c27b0", width=0.8, dash="dot"),
                          layer="below", row=1, col=1)

    # ── SSL / BSL levels ─────────────────────────────────────────
    if show_ssl_bsl:
        sb = detect_ssl_bsl(display)
        ssl_valid = sb["ssl_level"].dropna().tail(30)
        bsl_valid = sb["bsl_level"].dropna().tail(30)
        if not ssl_valid.empty:
            fig.add_trace(go.Scatter(
                x=ssl_valid.index, y=ssl_valid, mode="markers", name="SSL",
                marker=dict(symbol="line-ew", size=8, color=TV_RED,
                            line=dict(color=TV_RED, width=2)),
            ), row=1, col=1)
        if not bsl_valid.empty:
            fig.add_trace(go.Scatter(
                x=bsl_valid.index, y=bsl_valid, mode="markers", name="BSL",
                marker=dict(symbol="line-ew", size=8, color="#2196f3",
                            line=dict(color="#2196f3", width=2)),
            ), row=1, col=1)

    # ── Liquidity Sweeps ─────────────────────────────────────────
    if show_sweep:
        sw = detect_liquidity_sweep(display)
        bull = sw[sw["sweep_type"] == "bullish"]
        bear = sw[sw["sweep_type"] == "bearish"]
        if not bull.empty:
            fig.add_trace(go.Scatter(
                x=bull.index, y=display.loc[bull.index, "Low"],
                mode="markers", name="Bull Sweep",
                marker=dict(symbol="triangle-up", size=13, color=TV_GREEN,
                            line=dict(color="white", width=1)),
            ), row=1, col=1)
        if not bear.empty:
            fig.add_trace(go.Scatter(
                x=bear.index, y=display.loc[bear.index, "High"],
                mode="markers", name="Bear Sweep",
                marker=dict(symbol="triangle-down", size=13, color=TV_RED,
                            line=dict(color="white", width=1)),
            ), row=1, col=1)

    # ── Breaker Blocks ───────────────────────────────────────────
    if show_breaker:
        bb = detect_breaker_block(display).dropna(subset=["bb_type"]).tail(15)
        for ts, r in bb.iterrows():
            color = TV_BB_BULL if r["bb_type"] == "bullish" else TV_BB_BEAR
            border = "#00bcd4" if r["bb_type"] == "bullish" else "#ff5722"
            end = ts + bar_dur
            fig.add_shape(type="rect", x0=ts, x1=end,
                          y0=r["bb_bottom"], y1=r["bb_top"],
                          fillcolor=color,
                          line=dict(color=border, width=0.8, dash="dashdot"),
                          layer="below", row=1, col=1)

    # ── Mitigation markers ───────────────────────────────────────
    if show_mitigation:
        mit = detect_mitigation(display).dropna(subset=["mit_type"]).tail(30)
        if not mit.empty:
            fig.add_trace(go.Scatter(
                x=mit.index, y=mit["mit_level"].astype(float),
                mode="markers", name="Mitigation",
                marker=dict(symbol="x", size=9, color="#ffc107",
                            line=dict(color="#ffc107", width=1.5)),
            ), row=1, col=1)

    # ── PO3 background highlight (consolidated bands) ────────────
    if show_po3:
        po3 = detect_po3(display)
        phase_colors = {
            "accumulation": "rgba(63,81,181,0.05)",
            "manipulation": "rgba(239,83,80,0.05)",
            "distribution": "rgba(38,166,154,0.05)",
        }
        # Batch PO3 shapes — add_vrect with row= is extremely slow
        po3_shapes = []
        for phase, color in phase_colors.items():
            mask = po3["po3_phase"] == phase
            if not mask.any():
                continue
            in_phase = False
            band_start = None
            for ts, val in mask.items():
                if val and not in_phase:
                    band_start = ts
                    in_phase = True
                elif not val and in_phase:
                    po3_shapes.append(dict(
                        type="rect", x0=band_start, x1=ts,
                        y0=0, y1=1, yref="y domain", xref="x",
                        fillcolor=color, layer="below",
                        line=dict(width=0),
                    ))
                    in_phase = False
            if in_phase and band_start is not None:
                po3_shapes.append(dict(
                    type="rect", x0=band_start, x1=display.index[-1],
                    y0=0, y1=1, yref="y domain", xref="x",
                    fillcolor=color, layer="below",
                    line=dict(width=0),
                ))
        if po3_shapes:
            existing = list(fig.layout.shapes or [])
            fig.update_layout(shapes=existing + po3_shapes)

    # ── Trade signals (TradingView style: horizontal SL/TP zones) ─
    if signals is not None and not signals.empty:
        # Only show signals within the displayed time range, capped
        vis_sigs = signals[signals["signal_time"] >= chart_start].tail(max_signals)
        for _, sig in vis_sigs.iterrows():
            t = sig["signal_time"]
            is_long = sig["direction"] == "LONG"
            t_end = t + bar_dur

            # Entry line
            fig.add_shape(type="line", x0=t, x1=t_end,
                          y0=sig["entry"], y1=sig["entry"],
                          line=dict(color=TV_ENTRY_COLOR, width=2),
                          row=1, col=1)

            # SL zone (entry → SL as filled rect)
            sl_fill = "rgba(239,83,80,0.10)"
            fig.add_shape(type="rect", x0=t, x1=t_end,
                          y0=sig["entry"], y1=sig["sl"],
                          fillcolor=sl_fill,
                          line=dict(color=TV_SL_COLOR, width=1, dash="dot"),
                          row=1, col=1)

            # TP zone (entry → TP as filled rect)
            tp_fill = "rgba(38,166,154,0.10)"
            fig.add_shape(type="rect", x0=t, x1=t_end,
                          y0=sig["entry"], y1=sig["tp"],
                          fillcolor=tp_fill,
                          line=dict(color=TV_TP_COLOR, width=1, dash="dot"),
                          row=1, col=1)

            # Entry marker
            entry_marker_color = TV_GREEN if is_long else TV_RED
            fig.add_trace(go.Scatter(
                x=[t], y=[sig["entry"]], mode="markers",
                marker=dict(symbol="diamond", size=10, color=entry_marker_color,
                            line=dict(color="white", width=1)),
                showlegend=False,
                hovertext=f"{sig['direction']} | E:{sig['entry']:.2f} SL:{sig['sl']:.2f} TP:{sig['tp']:.2f}",
            ), row=1, col=1)

            # SL / TP labels
            fig.add_annotation(x=t_end, y=sig["sl"], text=f"SL {sig['sl']:.1f}",
                               font=dict(color=TV_SL_COLOR, size=9),
                               showarrow=False, xanchor="left", row=1, col=1)
            fig.add_annotation(x=t_end, y=sig["tp"], text=f"TP {sig['tp']:.1f}",
                               font=dict(color=TV_TP_COLOR, size=9),
                               showarrow=False, xanchor="left", row=1, col=1)

    # ── Order Flow subplot ───────────────────────────────────────
    if show_order_flow:
        oflow = compute_order_flow(display)
        of_colors = [TV_GREEN if d >= 0 else TV_RED for d in oflow["delta"]]
        fig.add_trace(go.Bar(
            x=display.index, y=oflow["delta"], name="Delta",
            marker_color=of_colors, opacity=0.6, showlegend=False,
        ), row=3, col=1)
        fig.add_trace(go.Scatter(
            x=display.index, y=oflow["cvd"], mode="lines", name="CVD",
            line=dict(color="#ab47bc", width=1.5),
        ), row=3, col=1)

    # ── TradingView-style layout ─────────────────────────────────
    chart_h = 900 if show_order_flow else 700
    fig.update_layout(
        **TV_LAYOUT,
        xaxis_rangeslider_visible=False,
        height=chart_h,
        legend=dict(orientation="h", yanchor="bottom", y=1.01,
                    xanchor="right", x=1,
                    bgcolor="rgba(19,23,34,0.8)",
                    font=dict(size=10, color=TV_TEXT)),
        margin=dict(l=10, r=60, t=40, b=30),
    )

    # Apply TV styling to all axes
    for i in range(1, n_rows + 1):
        xax = f"xaxis{i}" if i > 1 else "xaxis"
        yax = f"yaxis{i}" if i > 1 else "yaxis"
        fig.update_layout(**{
            xax: dict(gridcolor=TV_GRID, gridwidth=1, zeroline=False,
                      showline=False, tickfont=dict(color="#787b86")),
            yax: dict(gridcolor=TV_GRID, gridwidth=1, zeroline=False,
                      showline=False, tickfont=dict(color="#787b86"), side="right"),
        })

    # Title
    fig.add_annotation(
        text=f"<b>{symbol}</b> · {timeframe}",
        xref="paper", yref="paper", x=0.01, y=0.99,
        showarrow=False, font=dict(size=16, color=TV_TEXT),
    )

    return fig
