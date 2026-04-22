"""
ICT (Inner Circle Trader) Logic Engine — 10 Concept Detectors.

Each function is standalone and returns a DataFrame aligned to the input
OHLCV data.  ALL concepts are always computed; only the user-selected
subset is required for entry generation (see trade_generator.py).

Concepts:
  1. FVG  – Fair Value Gap (3-candle imbalance)
  2. MSS  – Market Structure Shift (swing break with displacement)
  3. PO3  – Power of Three phases (Accumulate → Manipulate → Distribute)
  4. OB   – Order Block (last candle before displacement)
  5. OTE  – Optimal Trade Entry (62–79 %% Fibonacci retracement)
  6. SSL / BSL – Sell-Side / Buy-Side Liquidity (clustered swing lows/highs)
  7. Liquidity Sweep – price spikes into SSL/BSL or PDH/PDL then reverses
  8. Breaker Block – failed OB turned opposite S/R
  9. Mitigation – price returns to OB, FVG, or breaker-block zone
 10. Order Flow – approximated CVD, delta, absorption from OHLCV
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from config import SESSIONS

# ===================================================================
# Helpers
# ===================================================================


def swing_highs(df: pd.DataFrame, order: int = 5) -> pd.Series:
    """Boolean Series marking local swing highs."""
    highs = df["High"]
    roll_max = highs.rolling(window=2 * order + 1, center=True).max()
    return highs == roll_max


def swing_lows(df: pd.DataFrame, order: int = 5) -> pd.Series:
    """Boolean Series marking local swing lows."""
    lows = df["Low"]
    roll_min = lows.rolling(window=2 * order + 1, center=True).min()
    return lows == roll_min


def previous_day_high_low(df: pd.DataFrame) -> pd.DataFrame:
    """PDH / PDL for each bar (NaN on the first trading day)."""
    daily = df.groupby(df.index.date).agg({"High": "max", "Low": "min"})
    daily.columns = ["DayHigh", "DayLow"]
    daily["PDH"] = daily["DayHigh"].shift(1)
    daily["PDL"] = daily["DayLow"].shift(1)
    date_map = pd.Series(df.index.date, index=df.index)
    out = pd.DataFrame(index=df.index)
    out["PDH"] = date_map.map(daily["PDH"].to_dict()).astype(float)
    out["PDL"] = date_map.map(daily["PDL"].to_dict()).astype(float)
    return out


# ===================================================================
# 1. FVG – Fair Value Gap
# ===================================================================


def detect_fvg(df: pd.DataFrame) -> pd.DataFrame:
    """Vectorized three-candle Fair Value Gaps."""
    h = df["High"]
    lo = df["Low"]
    
    # Shift to get previous candles
    h2 = h.shift(2)
    lo2 = lo.shift(2)
    
    bull_mask = (lo > h2)
    bear_mask = (h < lo2)
    
    fvg_type = pd.Series(None, index=df.index, dtype=object)
    fvg_type.loc[bull_mask] = "bullish"
    fvg_type.loc[bear_mask] = "bearish"
    
    fvg_top = pd.Series(np.nan, index=df.index)
    fvg_top.loc[bull_mask] = lo
    fvg_top.loc[bear_mask] = lo2
    
    fvg_bottom = pd.Series(np.nan, index=df.index)
    fvg_bottom.loc[bull_mask] = h2
    fvg_bottom.loc[bear_mask] = h
    
    fvg_ce = (fvg_top + fvg_bottom) / 2.0
    
    return pd.DataFrame({
        "fvg_type": fvg_type,
        "fvg_top": fvg_top,
        "fvg_bottom": fvg_bottom,
        "fvg_ce": fvg_ce
    }, index=df.index).astype({"fvg_top": float, "fvg_bottom": float, "fvg_ce": float})


# ===================================================================
# 2. MSS – Market Structure Shift
# ===================================================================


def detect_mss(df: pd.DataFrame, order: int = 5) -> pd.DataFrame:
    """Vectorized Market Structure Shift detection.
    
    Uses forward-filled swing highs/lows to detect breaks with displacement.
    """
    sh = swing_highs(df, order)
    sl = swing_lows(df, order)
    
    # Forward fill last swing levels
    last_sh = df["High"].where(sh).ffill().shift(1)
    last_sl = df["Low"].where(sl).ffill().shift(1)
    
    close = df["Close"]
    open_ = df["Open"]
    high = df["High"]
    low = df["Low"]
    
    # Displacement logic
    body = (close - open_).abs()
    rng = high - low
    disp = (rng > 0) & ((body / rng) > 0.5)
    
    bull_mss = (close > last_sh) & disp & last_sh.notna()
    bear_mss = (close < last_sl) & disp & last_sl.notna()
    
    mss_type = pd.Series(None, index=df.index, dtype=object)
    mss_type.loc[bull_mss] = "bullish"
    mss_type.loc[bear_mss] = "bearish"
    
    mss_level = pd.Series(np.nan, index=df.index)
    mss_level.loc[bull_mss] = last_sh
    mss_level.loc[bear_mss] = last_sl
    
    return pd.DataFrame({
        "mss_type": mss_type,
        "mss_level": mss_level
    }, index=df.index).astype({"mss_level": float})


# ===================================================================
# 3. PO3 – Power of Three
# ===================================================================


def detect_po3(df: pd.DataFrame) -> pd.DataFrame:
    """Label bars: accumulation / manipulation / distribution.

    Asian session (00:00-06:00)  → accumulation
    London open   (07:00-09:30)  → manipulation
    Rest of day   (09:30-17:00)  → distribution

    po3_bias: 'bullish' if manipulation sweeps Asian low,
              'bearish' if it sweeps Asian high, else 'none'.

    Returns: [po3_phase, po3_bias]
    """
    times = df.index.strftime("%H:%M")
    phase = pd.Series("none", index=df.index)
    phase[(times >= "00:00") & (times < "06:00")] = "accumulation"
    phase[(times >= "07:00") & (times < "09:30")] = "manipulation"
    phase[(times >= "09:30") & (times < "17:00")] = "distribution"

    bias = pd.Series("none", index=df.index)
    for day in np.unique(df.index.date):
        dm = df.index.date == day
        acc = df.loc[dm & (phase == "accumulation")]
        man = df.loc[dm & (phase == "manipulation")]
        if acc.empty or man.empty:
            continue
        a_hi = acc["High"].max()
        a_lo = acc["Low"].min()
        if man["Low"].min() < a_lo:
            bias.loc[dm] = "bullish"
        elif man["High"].max() > a_hi:
            bias.loc[dm] = "bearish"

    return pd.DataFrame({"po3_phase": phase, "po3_bias": bias}, index=df.index)


# ===================================================================
# 4. OB – Order Block
# ===================================================================


def detect_ob(df: pd.DataFrame, disp_mult: float = 1.5) -> pd.DataFrame:
    """Vectorized Order Block detection.
    
    OB is the candle *before* a strong displacement move.
    """
    h = df["High"]
    lo = df["Low"]
    o = df["Open"]
    c = df["Close"]
    
    atr = (h - lo).rolling(14).mean()
    body = (c - o).abs()
    
    # Displacement mask
    disp = body > (disp_mult * atr)
    bull_disp = (c > o) & disp
    bear_disp = (c < o) & disp
    
    # Check previous candle
    prev_c = c.shift(1)
    prev_o = o.shift(1)
    prev_bear = (prev_c < prev_o)
    prev_bull = (prev_c > prev_o)
    
    # Bullish OB: prev candle was bear, current is bull displacement
    bull_ob_mask = bull_disp & prev_bear
    # Bearish OB: prev candle was bull, current is bear displacement
    bear_ob_mask = bear_disp & prev_bull
    
    ob_type = pd.Series(None, index=df.index, dtype=object)
    ob_type.loc[bull_ob_mask.shift(-1).fillna(False)] = "bullish"
    ob_type.loc[bear_ob_mask.shift(-1).fillna(False)] = "bearish"
    
    ob_top = pd.Series(np.nan, index=df.index)
    ob_bottom = pd.Series(np.nan, index=df.index)
    
    # The OB is the candle BEFORE the displacement, so we mark index i if i+1 is displacement
    # Wait, the original code marks index i-1. So if i has displacement, i-1 is OB.
    # My shift(-1) does exactly that.
    
    ob_top_vals = pd.concat([o, c], axis=1).max(axis=1)
    ob_bot_vals = pd.concat([o, c], axis=1).min(axis=1)
    
    ob_top.loc[ob_type.notna()] = ob_top_vals
    ob_bottom.loc[ob_type.notna()] = ob_bot_vals
    
    return pd.DataFrame({
        "ob_type": ob_type,
        "ob_top": ob_top,
        "ob_bottom": ob_bottom
    }, index=df.index).astype({"ob_top": float, "ob_bottom": float})


# ===================================================================
# 5. OTE – Optimal Trade Entry
# ===================================================================


def detect_ote(df: pd.DataFrame, order: int = 10) -> pd.DataFrame:
    """OTE zone — 62-79 % Fibonacci retracement of the most recent swing.

    Bullish OTE: price retraces 62-79 % of a swing-low→swing-high.
    Bearish OTE: price retraces 62-79 % of a swing-high→swing-low.

    Returns: [ote_type, ote_top, ote_bottom]
    """
    sh = swing_highs(df, order)
    sl = swing_lows(df, order)
    h = df["High"].values
    lo = df["Low"].values
    n = len(df)

    otype = [None] * n
    otop = [np.nan] * n
    obot = [np.nan] * n
    last_sh_val = np.nan
    last_sl_val = np.nan
    last_sh_i = -1
    last_sl_i = -1

    lsh_val = df["High"].where(sh).ffill()
    lsl_val = df["Low"].where(sl).ffill()
    sh_idx = pd.Series(np.arange(len(df)), index=df.index).where(sh).ffill()
    sl_idx = pd.Series(np.arange(len(df)), index=df.index).where(sl).ffill()
    rng = lsh_val - lsl_val
    valid = (rng > 0)
    
    bull_mask = (sl_idx < sh_idx) & (df["Low"] <= lsh_val - 0.618*rng) & (df["Low"] >= lsh_val - 0.786*rng) & valid
    bear_mask = (sh_idx < sl_idx) & (df["High"] >= lsl_val + 0.618*rng) & (df["High"] <= lsl_val + 0.786*rng) & valid
    
    otype = pd.Series(None, index=df.index, dtype=object)
    otype.loc[bull_mask] = "bullish"
    otype.loc[bear_mask] = "bearish"
    
    otop = pd.Series(np.nan, index=df.index)
    otop.loc[bull_mask] = lsh_val - 0.618*rng
    otop.loc[bear_mask] = lsl_val + 0.786*rng
    
    obot = pd.Series(np.nan, index=df.index)
    obot.loc[bull_mask] = lsh_val - 0.786*rng
    obot.loc[bear_mask] = lsl_val + 0.618*rng

    return pd.DataFrame(
        {"ote_type": otype, "ote_top": otop, "ote_bottom": obot}, index=df.index
    ).astype({"ote_top": float, "ote_bottom": float})


# ===================================================================
# 6. SSL / BSL – Sell-Side / Buy-Side Liquidity
# ===================================================================


def detect_ssl_bsl(df: pd.DataFrame, order: int = 5, tol_pct: float = 0.001) -> pd.DataFrame:
    """Clustered equal-highs (BSL) and equal-lows (SSL).

    When ≥ 2 recent swing highs sit within *tol_pct* of each other →
    buy-side liquidity (BSL) rests above them.
    Mirror logic for SSL below clustered swing lows.

    Returns: [ssl_level, bsl_level]
    """
    sh = swing_highs(df, order)
    sl = swing_lows(df, order)
    h = df["High"].values
    lo = df["Low"].values
    n = len(df)

    ssl_out = [np.nan] * n
    bsl_out = [np.nan] * n
    sh_vals: list[float] = []
    sl_vals: list[float] = []

    for i in range(n):
        if sh.iloc[i]:
            sh_vals.append(h[i])
        if sl.iloc[i]:
            sl_vals.append(lo[i])

        # BSL check
        if len(sh_vals) >= 2:
            lp = sh_vals[-1]
            tol = lp * tol_pct
            cluster = [v for v in sh_vals[-10:] if abs(v - lp) <= tol]
            if len(cluster) >= 2:
                bsl_out[i] = float(np.mean(cluster))

        # SSL check
        if len(sl_vals) >= 2:
            lp = sl_vals[-1]
            tol = lp * tol_pct
            cluster = [v for v in sl_vals[-10:] if abs(v - lp) <= tol]
            if len(cluster) >= 2:
                ssl_out[i] = float(np.mean(cluster))

    return pd.DataFrame(
        {"ssl_level": ssl_out, "bsl_level": bsl_out}, index=df.index
    ).astype(float)


# ===================================================================
# 7. Liquidity Sweep
# ===================================================================


def detect_liquidity_sweep(df: pd.DataFrame, order: int = 5) -> pd.DataFrame:
    """Sweep of SSL / BSL / PDH / PDL with wick rejection.

    Bullish sweep: wick below SSL or PDL, close back above.
    Bearish sweep: wick above BSL or PDH, close back below.

    Returns: [sweep_type, sweep_level]
    """
    pdhl = previous_day_high_low(df)
    sslbsl = detect_ssl_bsl(df, order)
    h = df["High"].values
    lo = df["Low"].values
    c = df["Close"].values
    n = len(df)
    pdh = pdhl["PDH"].values
    pdl = pdhl["PDL"].values
    ssl = sslbsl["ssl_level"].values
    bsl = sslbsl["bsl_level"].values

    st_ = [None] * n
    sv = [np.nan] * n

    for i in range(n):
        # Bullish sweep (sell-side grab)
        for lv in (ssl[i], pdl[i]):
            if not np.isnan(lv) and lo[i] < lv and c[i] > lv:
                st_[i] = "bullish"
                sv[i] = lv
                break
        if st_[i] is not None:
            continue
        # Bearish sweep (buy-side grab)
        for lv in (bsl[i], pdh[i]):
            if not np.isnan(lv) and h[i] > lv and c[i] < lv:
                st_[i] = "bearish"
                sv[i] = lv
                break

    return pd.DataFrame(
        {"sweep_type": st_, "sweep_level": sv}, index=df.index
    ).astype({"sweep_level": float})


# ===================================================================
# 8. Breaker Block
# ===================================================================


def detect_breaker_block(df: pd.DataFrame, disp_mult: float = 1.5) -> pd.DataFrame:
    """Order Block that was broken through → now opposite S/R.

    Bullish breaker: a former bearish OB broken to the upside.
    Bearish breaker: a former bullish OB broken to the downside.

    Returns: [bb_type, bb_top, bb_bottom]
    """
    obs = detect_ob(df, disp_mult)
    c = df["Close"].values
    n = len(df)

    bt = [None] * n
    btop = [np.nan] * n
    bbot = [np.nan] * n
    active: list[tuple] = []  # (type, top, bottom)

    for i in range(n):
        obt = obs.iat[i, 0]  # ob_type
        if isinstance(obt, str) and obt in ("bullish", "bearish"):
            active.append((obt, obs.iat[i, 1], obs.iat[i, 2]))

        still = []
        for a_type, a_top, a_bot in active:
            if np.isnan(a_top) or np.isnan(a_bot):
                continue
            if a_type == "bearish" and c[i] > a_top:
                bt[i] = "bullish"
                btop[i] = a_top
                bbot[i] = a_bot
            elif a_type == "bullish" and c[i] < a_bot:
                bt[i] = "bearish"
                btop[i] = a_top
                bbot[i] = a_bot
            else:
                still.append((a_type, a_top, a_bot))
        active = still[-50:]

    return pd.DataFrame(
        {"bb_type": bt, "bb_top": btop, "bb_bottom": bbot}, index=df.index
    ).astype({"bb_top": float, "bb_bottom": float})


# ===================================================================
# 9. Mitigation
# ===================================================================


def detect_mitigation(df: pd.DataFrame) -> pd.DataFrame:
    """Price returning to a previously formed OB, FVG, or breaker block.

    Returns: [mit_type, mit_source, mit_level]
    """
    fvgs = detect_fvg(df)
    obs = detect_ob(df)
    bbs = detect_breaker_block(df)
    lo = df["Low"].values
    h = df["High"].values
    n = len(df)

    mtype = [None] * n
    msrc = [None] * n
    mlev = [np.nan] * n
    zones: list[tuple] = []  # (dir, top, bot, source)

    for i in range(n):
        # Register new zones
        for src_df, src_name, tc, topc, botc in (
            (fvgs, "FVG", "fvg_type", "fvg_top", "fvg_bottom"),
            (obs, "OB", "ob_type", "ob_top", "ob_bottom"),
            (bbs, "BB", "bb_type", "bb_top", "bb_bottom"),
        ):
            val = src_df.at[df.index[i], tc]
            if isinstance(val, str) and val in ("bullish", "bearish"):
                zones.append(
                    (val, float(src_df.at[df.index[i], topc]),
                     float(src_df.at[df.index[i], botc]), src_name)
                )

        # Check mitigation
        new_zones = []
        for z_dir, z_top, z_bot, z_src in zones:
            if np.isnan(z_top) or np.isnan(z_bot):
                continue
            mitigated = False
            if z_dir == "bullish" and lo[i] <= z_top and lo[i] >= z_bot:
                mtype[i] = "bullish"
                msrc[i] = z_src
                mlev[i] = (z_top + z_bot) / 2
                mitigated = True
            elif z_dir == "bearish" and h[i] >= z_bot and h[i] <= z_top:
                mtype[i] = "bearish"
                msrc[i] = z_src
                mlev[i] = (z_top + z_bot) / 2
                mitigated = True
            if not mitigated:
                new_zones.append((z_dir, z_top, z_bot, z_src))
        zones = new_zones[-100:]

    return pd.DataFrame(
        {"mit_type": mtype, "mit_source": msrc, "mit_level": mlev}, index=df.index
    ).astype({"mit_level": float})


# ===================================================================
# 10. Order Flow – CVD & Delta (approximated from OHLCV)
# ===================================================================


def compute_order_flow(df: pd.DataFrame) -> pd.DataFrame:
    """Approximate order-flow metrics from OHLCV.

    Delta  = Volume × (Close − Open) / (High − Low).
    CVD    = cumulative sum of delta.
    Absorption = high volume + small body → exhaustion signal.

    Returns: [delta, cvd, absorption]
    """
    rng = (df["High"] - df["Low"]).replace(0, np.nan)
    delta = df["Volume"] * (df["Close"] - df["Open"]) / rng
    delta = delta.fillna(0)
    cvd = delta.cumsum()

    body = (df["Close"] - df["Open"]).abs()
    avg_vol = df["Volume"].rolling(20, min_periods=1).mean()
    avg_body = body.rolling(20, min_periods=1).mean()
    absorption = (df["Volume"] > 1.5 * avg_vol) & (body < 0.5 * avg_body)

    return pd.DataFrame(
        {"delta": delta, "cvd": cvd, "absorption": absorption}, index=df.index
    )


# ===================================================================
# Convenience: compute everything at once
# ===================================================================


def compute_all(df: pd.DataFrame, order: int = 5) -> dict[str, pd.DataFrame]:
    """Run every detector and return results keyed by concept name."""
    return {
        "FVG": detect_fvg(df),
        "MSS": detect_mss(df, order),
        "PO3": detect_po3(df),
        "OB": detect_ob(df),
        "OTE": detect_ote(df, order * 2),
        "SSL/BSL": detect_ssl_bsl(df, order),
        "Liquidity Sweep": detect_liquidity_sweep(df, order),
        "Breaker Block": detect_breaker_block(df),
        "Mitigation": detect_mitigation(df),
        "Order Flow": compute_order_flow(df),
    }
