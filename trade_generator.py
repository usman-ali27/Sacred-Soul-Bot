"""
Flexible Trade Signal Generator — ICT Concepts.

The user selects *which* ICT concepts must be present for an entry.
This module checks every bar for concept confluence and only generates
a signal when **all** user-selected concepts confirm the direction.

Design principle: no hard-coded "all concepts required".  The caller
passes a list of concept names; the generator AND's them.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ict_engine import compute_all

# ===================================================================
# Concept condition checkers (per-bar, per-direction)
# ===================================================================
# Each checker returns True/False for a given bar index and direction.
# ``ict`` is the dict returned by ict_engine.compute_all().
# ``lookback`` is the number of bars to search backward.


def _check_mss(ict, idx, direction, lookback, df):
    mss = ict["MSS"]
    start = max(0, idx - lookback)
    window = mss.iloc[start:idx + 1]
    return (window["mss_type"] == direction).any()


def _check_sweep(ict, idx, direction, lookback, df):
    sw = ict["Liquidity Sweep"]
    start = max(0, idx - lookback)
    window = sw.iloc[start:idx + 1]
    return (window["sweep_type"] == direction).any()


def _check_ob(ict, idx, direction, lookback, df):
    ob = ict["OB"]
    start = max(0, idx - lookback)
    window = ob.iloc[start:idx + 1]
    return (window["ob_type"] == direction).any()


def _check_fvg(ict, idx, direction, lookback, df):
    fvg = ict["FVG"]
    start = max(0, idx - lookback)
    window = fvg.iloc[start:idx + 1]
    return (window["fvg_type"] == direction).any()


def _check_ote(ict, idx, direction, _lookback, df):
    ote = ict["OTE"]
    return ote.iloc[idx]["ote_type"] == direction


def _check_po3(ict, idx, direction, _lookback, df):
    po3 = ict["PO3"]
    row = po3.iloc[idx]
    return row["po3_phase"] == "distribution" and row["po3_bias"] == direction


def _check_ssl_bsl(ict, idx, direction, lookback, df):
    sb = ict["SSL/BSL"]
    start = max(0, idx - lookback)
    window = sb.iloc[start:idx + 1]
    if direction == "bullish":
        return window["ssl_level"].notna().any()
    return window["bsl_level"].notna().any()


def _check_breaker(ict, idx, direction, lookback, df):
    bb = ict["Breaker Block"]
    start = max(0, idx - lookback)
    window = bb.iloc[start:idx + 1]
    return (window["bb_type"] == direction).any()


def _check_mitigation(ict, idx, direction, lookback, df):
    mit = ict["Mitigation"]
    start = max(0, idx - lookback)
    window = mit.iloc[start:idx + 1]
    return (window["mit_type"] == direction).any()


def _check_order_flow(ict, idx, direction, lookback, df):
    of = ict["Order Flow"]
    start = max(0, idx - lookback)
    window = of.iloc[start:idx + 1]
    if len(window) < 3:
        return False
    slope = window["cvd"].iloc[-1] - window["cvd"].iloc[0]
    if direction == "bullish":
        return slope > 0
    return slope < 0


CHECKERS = {
    "MSS": _check_mss,
    "Liquidity Sweep": _check_sweep,
    "OB": _check_ob,
    "FVG": _check_fvg,
    "OTE": _check_ote,
    "PO3": _check_po3,
    "SSL/BSL": _check_ssl_bsl,
    "Breaker Block": _check_breaker,
    "Mitigation": _check_mitigation,
    "Order Flow": _check_order_flow,
}


# ===================================================================
# Entry helpers – find the best entry price from confluence
# ===================================================================


def _best_entry(ict, idx, direction, lookback):
    """Pick entry price from the nearest available zone."""
    prices = []

    # FVG CE
    fvg = ict["FVG"]
    start = max(0, idx - lookback)
    w = fvg.iloc[start:idx + 1]
    match = w[w["fvg_type"] == direction]
    if not match.empty:
        prices.append(float(match.iloc[-1]["fvg_ce"]))

    # OB midpoint
    ob = ict["OB"]
    w = ob.iloc[start:idx + 1]
    match = w[w["ob_type"] == direction]
    if not match.empty:
        prices.append(float((match.iloc[-1]["ob_top"] + match.iloc[-1]["ob_bottom"]) / 2))

    # OTE midpoint
    ote = ict["OTE"]
    if ote.iloc[idx]["ote_type"] == direction:
        prices.append(float((ote.iloc[idx]["ote_top"] + ote.iloc[idx]["ote_bottom"]) / 2))

    if prices:
        return float(np.mean(prices))
    return None


# ===================================================================
# Signal generation
# ===================================================================


def generate_signals(
    df: pd.DataFrame,
    required_concepts: list[str],
    rr_ratio: float = 2.0,
    sweep_lookback: int = 20,
) -> pd.DataFrame:
    """Generate ICT trade signals honouring only the user-selected concepts.

    For each bar the logic is:
      1. Check if a liquidity sweep occurred in the last *sweep_lookback* bars
         to establish directional bias (bullish / bearish).
      2. For that direction verify that every concept in *required_concepts*
         is confirmed.
      3. If all pass → create entry signal.

    If "Liquidity Sweep" is *not* in required_concepts the generator still
    uses sweep detection to determine bias (direction), but does not require
    it as a filter.

    Args:
        df:                 OHLCV DataFrame.
        required_concepts:  User-selected list of concept names.
        rr_ratio:           Risk-reward ratio.
        sweep_lookback:     How many bars back to search for sweeps.

    Returns:
        DataFrame of trade signals.
    """
    if df.empty or len(df) < 30:
        return _empty_signals()

    ict = compute_all(df)
    sweeps = ict["Liquidity Sweep"]
    n = len(df)
    signals: list[dict] = []
    cooldown = 0  # prevent duplicate signals

    for i in range(sweep_lookback, n):
        if cooldown > 0:
            cooldown -= 1
            continue

        # Step 1 – determine bias from recent sweep
        sw_window = sweeps.iloc[max(0, i - sweep_lookback):i + 1]
        bull_sweep = (sw_window["sweep_type"] == "bullish").any()
        bear_sweep = (sw_window["sweep_type"] == "bearish").any()

        for direction, has_sweep in [("bullish", bull_sweep), ("bearish", bear_sweep)]:
            if not has_sweep:
                continue

            # Step 2 – check required concepts
            all_pass = True
            confirmed = []
            for concept in required_concepts:
                checker = CHECKERS.get(concept)
                if checker is None:
                    continue
                if checker(ict, i, direction, sweep_lookback, df):
                    confirmed.append(concept)
                else:
                    all_pass = False
                    break

            if not all_pass or not confirmed:
                continue

            # Step 3 – build signal
            entry = _best_entry(ict, i, direction, sweep_lookback)
            if entry is None:
                entry = float(df.iloc[i]["Close"])

            # SL – beyond the sweep candle
            sw_match = sw_window[sw_window["sweep_type"] == direction]
            if not sw_match.empty:
                sweep_bar = sw_match.index[-1]
                if direction == "bullish":
                    sl = float(df.loc[sweep_bar, "Low"])
                else:
                    sl = float(df.loc[sweep_bar, "High"])
            else:
                if direction == "bullish":
                    sl = float(df.iloc[max(0, i - sweep_lookback):i + 1]["Low"].min())
                else:
                    sl = float(df.iloc[max(0, i - sweep_lookback):i + 1]["High"].max())

            risk = abs(entry - sl)
            if risk <= 0:
                continue

            if direction == "bullish":
                tp = entry + rr_ratio * risk
            else:
                tp = entry - rr_ratio * risk

            signals.append({
                "signal_time": df.index[i],
                "direction": "LONG" if direction == "bullish" else "SHORT",
                "entry": round(entry, 5),
                "sl": round(sl, 5),
                "tp": round(tp, 5),
                "be_level": round(entry, 5),
                "risk": round(risk, 5),
                "rr_ratio": rr_ratio,
                "concepts_used": "+".join(confirmed),
            })
            cooldown = max(3, sweep_lookback // 4)
            break  # one signal per bar

    if not signals:
        return _empty_signals()

    sig_df = pd.DataFrame(signals)
    sig_df = _backtest_signals(sig_df, df)
    return sig_df


# ===================================================================
# Backtester
# ===================================================================


def _backtest_signals(sig_df: pd.DataFrame, df: pd.DataFrame) -> pd.DataFrame:
    """Walk-forward resolution: WIN / LOSS / BE / OPEN."""
    statuses, results, pnls = [], [], []

    for _, sig in sig_df.iterrows():
        entry_time = sig["signal_time"]
        direction = sig["direction"]
        entry = sig["entry"]
        sl = sig["sl"]
        tp = sig["tp"]
        risk = sig["risk"]

        future = df.loc[entry_time:]
        if len(future) <= 1:
            statuses.append("OPEN"); results.append(None); pnls.append(0.0)
            continue

        status, result, pnl = "OPEN", None, 0.0
        be_active = False

        for _, candle in future.iloc[1:].iterrows():
            high, low = candle["High"], candle["Low"]

            if direction == "LONG":
                if not be_active and high >= entry + risk:
                    be_active = True
                    sl = entry
                if low <= sl:
                    status = "CLOSED"
                    result = "BE" if be_active else "LOSS"
                    pnl = sl - entry
                    break
                if high >= tp:
                    status, result = "CLOSED", "WIN"
                    pnl = tp - entry
                    break
            else:
                if not be_active and low <= entry - risk:
                    be_active = True
                    sl = entry
                if high >= sl:
                    status = "CLOSED"
                    result = "BE" if be_active else "LOSS"
                    pnl = entry - sl
                    break
                if low <= tp:
                    status, result = "CLOSED", "WIN"
                    pnl = entry - tp
                    break

        statuses.append(status)
        results.append(result)
        pnls.append(round(pnl, 5))

    sig_df["status"] = statuses
    sig_df["result"] = results
    sig_df["pnl"] = pnls
    return sig_df


def _empty_signals() -> pd.DataFrame:
    return pd.DataFrame(columns=[
        "signal_time", "direction", "entry", "sl", "tp",
        "be_level", "risk", "rr_ratio", "concepts_used",
        "status", "result", "pnl",
    ])
