"""
Scenario Backtester — finds the best R:R across all preset × instrument
× timeframe × RR combinations.

Usage:
    python scenario_backtest.py          (prints results to console)
    OR imported by app.py for the dashboard page
"""

from __future__ import annotations

import itertools
import pandas as pd

from config import INSTRUMENTS, PRESETS
from data_fetcher import fetch_ohlcv
from trade_generator import generate_signals
from performance_tracker import compute_stats


# ===================================================================
# Extra concept combos worth testing beyond the 5 presets
# ===================================================================
EXTRA_COMBOS: dict[str, list[str]] = {
    "Sweep + FVG": ["Liquidity Sweep", "FVG"],
    "Sweep + OB + MSS": ["Liquidity Sweep", "OB", "MSS"],
    "Sweep + FVG + OTE": ["Liquidity Sweep", "FVG", "OTE"],
    "Sweep + OB + Order Flow": ["Liquidity Sweep", "OB", "Order Flow"],
    "MSS + OB + FVG": ["MSS", "OB", "FVG"],
    "MSS + FVG + OTE": ["MSS", "FVG", "OTE"],
    "Sweep + MSS + OB + FVG": ["Liquidity Sweep", "MSS", "OB", "FVG"],
    "Sweep + MSS + Breaker": ["Liquidity Sweep", "MSS", "Breaker Block"],
    "Sweep + OB + Mitigation": ["Liquidity Sweep", "OB", "Mitigation"],
    "OB + FVG + Order Flow": ["OB", "FVG", "Order Flow"],
}

ALL_SCENARIOS = {**PRESETS, **EXTRA_COMBOS}

TIMEFRAMES = ["1h", "4h", "Daily"]  # skip 15m for speed
RR_VALUES = [1.5, 2.0, 2.5, 3.0]
SWEEP_LOOKBACKS = [20]


def run_full_backtest(
    scenarios: dict[str, list[str]] | None = None,
    instruments: dict[str, str] | None = None,
    timeframes: list[str] | None = None,
    rr_values: list[float] | None = None,
    sweep_lookbacks: list[int] | None = None,
    progress_callback=None,
) -> pd.DataFrame:
    """Run backtest across all scenario × instrument × TF × RR combos.

    Args:
        scenarios:         dict of {name: [concepts]}
        instruments:       dict of {display_name: yf_ticker}
        timeframes:        list of timeframe strings
        rr_values:         list of R:R ratios to test
        sweep_lookbacks:   list of lookback values
        progress_callback: callable(current, total) for progress bars

    Returns:
        DataFrame with one row per combo, sorted by avg_pnl_r descending.
    """
    scenarios = scenarios or ALL_SCENARIOS
    instruments = instruments or INSTRUMENTS
    timeframes = timeframes or TIMEFRAMES
    rr_values = rr_values or RR_VALUES
    sweep_lookbacks = sweep_lookbacks or SWEEP_LOOKBACKS

    combos = list(itertools.product(
        scenarios.items(),
        instruments.keys(),
        timeframes,
        rr_values,
        sweep_lookbacks,
    ))
    total = len(combos)

    # Cache fetched data to avoid re-downloading
    data_cache: dict[tuple[str, str], pd.DataFrame] = {}
    rows: list[dict] = []

    for idx, ((preset_name, concepts), sym, tf, rr, lb) in enumerate(combos):
        if progress_callback:
            progress_callback(idx, total)

        cache_key = (sym, tf)
        if cache_key not in data_cache:
            try:
                data_cache[cache_key] = fetch_ohlcv(sym, tf)
            except Exception:
                data_cache[cache_key] = pd.DataFrame()

        df = data_cache[cache_key]
        if df.empty or len(df) < 30:
            continue

        try:
            signals = generate_signals(df, concepts, rr_ratio=rr, sweep_lookback=lb)
        except Exception:
            continue

        if signals.empty:
            continue

        stats = compute_stats(signals)
        if stats["total_trades"] < 3:
            continue

        rows.append({
            "scenario": preset_name,
            "concepts": ", ".join(concepts),
            "instrument": sym,
            "timeframe": tf,
            "rr_ratio": rr,
            "lookback": lb,
            "trades": stats["total_trades"],
            "wins": stats["wins"],
            "losses": stats["losses"],
            "win_rate": stats["win_rate"],
            "avg_pnl_r": stats["avg_pnl_r"],
            "max_drawdown": stats["max_drawdown"],
            "profit_factor": stats["profit_factor"],
            "sharpe": stats["sharpe"],
        })

    if progress_callback:
        progress_callback(total, total)

    if not rows:
        return pd.DataFrame()

    result = pd.DataFrame(rows)
    result = result.sort_values("avg_pnl_r", ascending=False).reset_index(drop=True)
    result.index += 1  # 1-based ranking
    result.index.name = "rank"
    return result


# ===================================================================
# Aggregated view — best scenario per instrument
# ===================================================================

def best_per_instrument(results: pd.DataFrame) -> pd.DataFrame:
    """From full results, pick the best combo per instrument."""
    if results.empty:
        return results
    return (
        results
        .sort_values("avg_pnl_r", ascending=False)
        .drop_duplicates(subset=["instrument"], keep="first")
        .reset_index(drop=True)
    )


def best_overall(results: pd.DataFrame, top_n: int = 10) -> pd.DataFrame:
    """Top N combos overall by average R."""
    if results.empty:
        return results
    return results.head(top_n).copy()


# ===================================================================
# CLI entry point
# ===================================================================

if __name__ == "__main__":
    print("=" * 80)
    print("  ICT BOT — SCENARIO BACKTEST  ".center(80))
    print("=" * 80)
    print(f"\nScenarios: {len(ALL_SCENARIOS)}")
    print(f"Instruments: {list(INSTRUMENTS.keys())}")
    print(f"Timeframes: {TIMEFRAMES}")
    print(f"R:R values: {RR_VALUES}")
    total_combos = len(ALL_SCENARIOS) * len(INSTRUMENTS) * len(TIMEFRAMES) * len(RR_VALUES)
    print(f"Total combos: {total_combos}")
    print("\nRunning backtest (this may take a few minutes)...\n")

    def _progress(cur, tot):
        if cur % 20 == 0 or cur == tot:
            print(f"  [{cur}/{tot}] ({cur * 100 // tot}%)")

    results = run_full_backtest(progress_callback=_progress)

    if results.empty:
        print("\nNo results — all combos produced fewer than 3 trades.")
    else:
        print("\n" + "=" * 80)
        print("  TOP 15 BEST R:R SCENARIOS".center(80))
        print("=" * 80)
        top = best_overall(results, 15)
        print(top.to_string())

        print("\n" + "=" * 80)
        print("  BEST SCENARIO PER INSTRUMENT".center(80))
        print("=" * 80)
        per_inst = best_per_instrument(results)
        print(per_inst.to_string())

        # Save full results
        results.to_csv("backtest_results.csv")
        print(f"\nFull results saved to backtest_results.csv ({len(results)} rows)")
