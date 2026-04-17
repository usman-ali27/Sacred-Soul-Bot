"""
Grid backtest + walk-forward validation utilities.

This module intentionally keeps simulation lightweight:
- Uses historical OHLC bars with deterministic fills
- Applies spread/slippage haircuts in PnL
- Supports monthly walk-forward summaries
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from grid_engine import (
    GridConfig,
    GridState,
    analyze_market_direction,
    apply_regime_profile,
    basket_floating_pnl_usd,
    build_grid_levels,
    mark_level_open,
    should_close_basket,
)


@dataclass
class BacktestConfig:
    spread_points: float = 0.15
    slippage_points: float = 0.10
    rebalance_bars: int = 24


def run_grid_backtest(
    df: pd.DataFrame,
    cfg: GridConfig,
    bt_cfg: BacktestConfig | None = None,
) -> dict:
    """Run a simple but realistic grid simulation over OHLC data."""
    if bt_cfg is None:
        bt_cfg = BacktestConfig()

    if df.empty or len(df) < 120:
        return {
            "summary": {
                "trades": 0,
                "wins": 0,
                "losses": 0,
                "win_rate": 0.0,
                "net_pnl": 0.0,
                "max_dd": 0.0,
                "profit_factor": 0.0,
            },
            "equity_curve": pd.DataFrame(),
            "monthly": pd.DataFrame(),
        }

    work = df.copy().dropna().sort_index()
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    wins = 0
    losses = 0
    realized: list[float] = []

    # bootstrap state from first rebalance point
    regime = analyze_market_direction(work.iloc[:80], cfg.spacing_multiplier)
    sim_cfg = apply_regime_profile(cfg, regime.regime) if cfg.auto_profile_switch else cfg
    anchor = float(work.iloc[79]["Close"])
    state = GridState(config=sim_cfg, active=True, regime=regime, levels=build_grid_levels(anchor, regime, sim_cfg))

    eq_rows: list[dict] = []

    for i in range(80, len(work)):
        row = work.iloc[i]
        hi = float(row["High"])
        lo = float(row["Low"])
        close = float(row["Close"])

        # periodic regime refresh and grid rebalance
        if (i - 80) % bt_cfg.rebalance_bars == 0:
            regime = analyze_market_direction(work.iloc[max(0, i - 150):i + 1], cfg.spacing_multiplier)
            sim_cfg = apply_regime_profile(cfg, regime.regime) if cfg.auto_profile_switch else cfg
            state.config = sim_cfg
            state.regime = regime
            state.levels = build_grid_levels(close, regime, sim_cfg)

        # activate pending levels touched by bar range
        for lv in state.levels:
            if lv.status != "PENDING":
                continue
            if lo <= lv.price <= hi:
                mark_level_open(state, lv.level_id, 0, lv.price)

        # close OPEN levels if TP/SL touched
        for lv in [x for x in state.levels if x.status == "OPEN"]:
            closed = False
            # Conservative order: SL first, then TP when both touched.
            if lv.direction == "BUY":
                if lo <= lv.sl_price:
                    exit_price = lv.sl_price
                    closed = True
                elif hi >= lv.tp_price:
                    exit_price = lv.tp_price
                    closed = True
            else:
                if hi >= lv.sl_price:
                    exit_price = lv.sl_price
                    closed = True
                elif lo <= lv.tp_price:
                    exit_price = lv.tp_price
                    closed = True

            if closed:
                gross = (exit_price - lv.entry_price) * lv.lot * 100.0
                if lv.direction == "SELL":
                    gross = -gross
                costs = (bt_cfg.spread_points + bt_cfg.slippage_points) * lv.lot
                pnl = gross - costs
                _close_level_sim(state, lv.level_id, exit_price, pnl)
                realized.append(pnl)
                if pnl >= 0:
                    wins += 1
                else:
                    losses += 1
                equity += pnl

        # basket close logic inside backtest
        basket_pnl = basket_floating_pnl_usd(state, close)
        close_basket, _ = should_close_basket(state, basket_pnl)
        if close_basket:
            for lv in [x for x in state.levels if x.status == "OPEN"]:
                gross = (close - lv.entry_price) * lv.lot * 100.0
                if lv.direction == "SELL":
                    gross = -gross
                costs = (bt_cfg.spread_points + bt_cfg.slippage_points) * lv.lot
                pnl = gross - costs
                _close_level_sim(state, lv.level_id, close, pnl)
                realized.append(pnl)
                if pnl >= 0:
                    wins += 1
                else:
                    losses += 1
                equity += pnl

        peak = max(peak, equity)
        dd = peak - equity
        max_dd = max(max_dd, dd)
        eq_rows.append({"time": work.index[i], "equity": equity})

    trades = wins + losses
    win_rate = (wins / trades * 100.0) if trades else 0.0

    pos = sum(x for x in realized if x > 0)
    neg = abs(sum(x for x in realized if x < 0))
    profit_factor = (pos / neg) if neg > 0 else 0.0

    eq_df = pd.DataFrame(eq_rows)
    if not eq_df.empty:
        eq_df["month"] = eq_df["time"].dt.tz_localize(None).dt.to_period("M").astype(str)
        monthly = eq_df.groupby("month").agg(
            end_equity=("equity", "last"),
            min_equity=("equity", "min"),
            max_equity=("equity", "max"),
        ).reset_index()
        monthly["month_pnl"] = monthly["end_equity"].diff().fillna(monthly["end_equity"])
    else:
        monthly = pd.DataFrame()

    summary = {
        "trades": trades,
        "wins": wins,
        "losses": losses,
        "win_rate": round(win_rate, 2),
        "net_pnl": round(equity, 2),
        "max_dd": round(max_dd, 2),
        "profit_factor": round(profit_factor, 3),
    }

    return {
        "summary": summary,
        "equity_curve": eq_df,
        "monthly": monthly,
    }


def _close_level_sim(state: GridState, level_id: str, exit_price: float, profit_usd: float) -> None:
    """Simulation-only close updater (no persistent audit side effects)."""
    for lv in state.levels:
        if lv.level_id != level_id:
            continue
        lv.status = "CLOSED"
        lv.exit_price = exit_price
        lv.profit_usd = profit_usd
        state.total_closed += 1
        state.total_profit_usd += profit_usd
        if profit_usd >= 0:
            state.total_wins += 1
        else:
            state.total_losses += 1
        break
