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
    ict_data: dict[str, pd.DataFrame] | None = None,
) -> pd.DataFrame:
    """Generate ICT trade signals honouring only the user-selected concepts."""
    if df.empty or len(df) < 30:
        return _empty_signals()

    if ict_data is None:
        ict_data = compute_all(df)
    ict = ict_data
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
    """Vectorized walk-forward resolution: WIN / LOSS / BE / OPEN."""
    if sig_df.empty:
        return sig_df

    h = df["High"].values
    l = df["Low"].values
    t = df.index.values
    
    # Map timestamps to integer indices for fast slicing
    t_idx = {val: i for i, val in enumerate(t)}
    
    statuses, results, pnls = [], [], []

    for _, sig in sig_df.iterrows():
        entry_idx = t_idx.get(sig["signal_time"])
        if entry_idx is None or entry_idx >= len(h) - 1:
            statuses.append("OPEN"); results.append(None); pnls.append(0.0)
            continue

        direction = sig["direction"]
        entry = sig["entry"]
        sl = sig["sl"]
        tp = sig["tp"]
        risk = sig["risk"]
        
        # Future window
        fh = h[entry_idx + 1:]
        fl = l[entry_idx + 1:]
        
        if direction == "LONG":
            # 1. Find when BE triggers (High >= Entry + Risk)
            be_triggers = np.where(fh >= entry + risk)[0]
            be_i = be_triggers[0] if len(be_triggers) > 0 else len(fh)
            
            # 2. Check for exit BEFORE BE triggers
            # (Note: we check up to be_i because the candle that triggers BE might also trigger SL/TP)
            pre_be_sl = np.where(fl[:be_i + 1] <= sl)[0]
            pre_be_tp = np.where(fh[:be_i + 1] >= tp)[0]
            
            first_sl = pre_be_sl[0] if len(pre_be_sl) > 0 else 9999999
            first_tp = pre_be_tp[0] if len(pre_be_tp) > 0 else 9999999
            
            if first_sl < first_tp and first_sl <= be_i:
                statuses.append("CLOSED"); results.append("LOSS"); pnls.append(round(sl - entry, 5))
            elif first_tp < first_sl and first_tp <= be_i:
                statuses.append("CLOSED"); results.append("WIN"); pnls.append(round(tp - entry, 5))
            elif be_i < len(fh):
                # BE triggered, now SL is entry
                post_be_sl = np.where(fl[be_i + 1:] <= entry)[0]
                post_be_tp = np.where(fh[be_i + 1:] >= tp)[0]
                
                f_sl = post_be_sl[0] if len(post_be_sl) > 0 else 9999999
                f_tp = post_be_tp[0] if len(post_be_tp) > 0 else 9999999
                
                if f_sl < f_tp:
                    statuses.append("CLOSED"); results.append("BE"); pnls.append(0.0)
                elif f_tp < f_sl:
                    statuses.append("CLOSED"); results.append("WIN"); pnls.append(round(tp - entry, 5))
                else:
                    statuses.append("OPEN"); results.append(None); pnls.append(0.0)
            else:
                statuses.append("OPEN"); results.append(None); pnls.append(0.0)
                
        else: # SHORT
            be_triggers = np.where(fl <= entry - risk)[0]
            be_i = be_triggers[0] if len(be_triggers) > 0 else len(fh)
            
            pre_be_sl = np.where(fh[:be_i + 1] >= sl)[0]
            pre_be_tp = np.where(fl[:be_i + 1] <= tp)[0]
            
            first_sl = pre_be_sl[0] if len(pre_be_sl) > 0 else 9999999
            first_tp = pre_be_tp[0] if len(pre_be_tp) > 0 else 9999999
            
            if first_sl < first_tp and first_sl <= be_i:
                statuses.append("CLOSED"); results.append("LOSS"); pnls.append(round(entry - sl, 5))
            elif first_tp < first_sl and first_tp <= be_i:
                statuses.append("CLOSED"); results.append("WIN"); pnls.append(round(entry - tp, 5))
            elif be_i < len(fh):
                post_be_sl = np.where(fh[be_i + 1:] >= entry)[0]
                post_be_tp = np.where(fl[be_i + 1:] <= tp)[0]
                
                f_sl = post_be_sl[0] if len(post_be_sl) > 0 else 9999999
                f_tp = post_be_tp[0] if len(post_be_tp) > 0 else 9999999
                
                if f_sl < f_tp:
                    statuses.append("CLOSED"); results.append("BE"); pnls.append(0.0)
                elif f_tp < f_sl:
                    statuses.append("CLOSED"); results.append("WIN"); pnls.append(round(entry - tp, 5))
                else:
                    statuses.append("OPEN"); results.append(None); pnls.append(0.0)
            else:
                statuses.append("OPEN"); results.append(None); pnls.append(0.0)

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
