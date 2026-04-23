"""
Grid backtest + walk-forward validation utilities.

This module intentionally keeps simulation lightweight:
- Uses historical OHLC bars with deterministic fills
- Applies spread/slippage haircuts in PnL
- Supports monthly walk-forward summaries
- Returns enriched stats: Sharpe, Calmar, consecutive W/L, trade log
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List

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
    commission_per_lot: float = 7.00  # $7 per round turn per lot
    swap_long_per_lot: float = -20.00 # $ per day per lot
    swap_short_per_lot: float = 10.00  # $ per day per lot
    rebalance_bars: int = 24


def _max_consecutive(results: List[bool]) -> tuple[int, int]:
    """Return (max_consecutive_wins, max_consecutive_losses)."""
    max_wins = max_losses = cur_wins = cur_losses = 0
    for win in results:
        if win:
            cur_wins += 1
            cur_losses = 0
        else:
            cur_losses += 1
            cur_wins = 0
        max_wins = max(max_wins, cur_wins)
        max_losses = max(max_losses, cur_losses)
    return max_wins, max_losses


def _sharpe_ratio(pnl_series: List[float], periods_per_year: int = 252) -> float:
    """Annualised Sharpe ratio (daily PnL series assumed)."""
    if len(pnl_series) < 2:
        return 0.0
    mean = sum(pnl_series) / len(pnl_series)
    variance = sum((x - mean) ** 2 for x in pnl_series) / (len(pnl_series) - 1)
    std = math.sqrt(variance) if variance > 0 else 0.0
    if std == 0:
        return 0.0
    return round((mean / std) * math.sqrt(periods_per_year), 3)


def _calmar_ratio(net_pnl: float, max_dd: float) -> float:
    """Net PnL / Max Drawdown (simple version)."""
    if max_dd <= 0:
        return 0.0
    return round(net_pnl / max_dd, 3)


def run_grid_backtest(
    df: pd.DataFrame,
    cfg: GridConfig,
    bt_cfg: BacktestConfig | None = None,
) -> dict:
    """Run a simple but realistic grid simulation over OHLC data."""
    if bt_cfg is None:
        bt_cfg = BacktestConfig()

    empty_result = {
        "summary": {
            "trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0,
            "net_pnl": 0.0,
            "max_dd": 0.0,
            "profit_factor": 0.0,
            "sharpe": 0.0,
            "calmar": 0.0,
            "max_consec_wins": 0,
            "max_consec_losses": 0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "expectancy": 0.0,
        },
        "equity_curve": pd.DataFrame(),
        "monthly": pd.DataFrame(),
        "trades": [],
    }

    if df.empty or len(df) < 120:
        return empty_result

    work = df.copy().dropna().sort_index()
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    wins = 0
    losses = 0
    realized: list[float] = []
    win_flags: list[bool] = []
    trade_log: list[dict] = []

    # bootstrap state
    regime = analyze_market_direction(work.iloc[:80], cfg.spacing_multiplier)
    sim_cfg = apply_regime_profile(cfg, regime.regime) if cfg.auto_profile_switch else cfg
    anchor = float(work.iloc[79]["Close"])
    state = GridState(config=sim_cfg, active=True, regime=regime, levels=build_grid_levels(anchor, regime, sim_cfg))

    eq_rows: list[dict] = []
    daily_pnl: list[float] = []
    prev_equity = 0.0
    prev_date = None

    for i in range(80, len(work)):
        row = work.iloc[i]
        hi = float(row["High"])
        lo = float(row["Low"])
        open_ = float(row["Open"])
        close = float(row["Close"])
        time = work.index[i]

        # periodic regime refresh
        if (i - 80) % bt_cfg.rebalance_bars == 0:
            regime = analyze_market_direction(work.iloc[max(0, i - 150):i + 1], cfg.spacing_multiplier)
            sim_cfg = apply_regime_profile(cfg, regime.regime) if cfg.auto_profile_switch else cfg
            state.config = sim_cfg
            state.regime = regime
            state.levels = build_grid_levels(close, regime, sim_cfg)

        # activate pending
        for lv in state.levels:
            if lv.status != "PENDING":
                continue
            if lo <= lv.price <= hi:
                mark_level_open(state, lv.level_id, 0, lv.price)
                lv.entry_time = time

        # close OPEN levels
        for lv in [x for x in state.levels if x.status == "OPEN"]:
            exit_price = None
            if lv.direction == "BUY":
                sl_hit = lo <= lv.sl_price
                tp_hit = hi >= lv.tp_price
                if sl_hit and tp_hit:
                    if abs(lv.sl_price - open_) < abs(lv.tp_price - open_):
                        exit_price = lv.sl_price
                    else:
                        exit_price = lv.tp_price
                elif sl_hit:
                    exit_price = lv.sl_price
                elif tp_hit:
                    exit_price = lv.tp_price
            else:  # SELL
                sl_hit = hi >= lv.sl_price
                tp_hit = lo <= lv.tp_price
                if sl_hit and tp_hit:
                    if abs(lv.sl_price - open_) < abs(lv.tp_price - open_):
                        exit_price = lv.sl_price
                    else:
                        exit_price = lv.tp_price
                elif sl_hit:
                    exit_price = lv.sl_price
                elif tp_hit:
                    exit_price = lv.tp_price

            if exit_price is not None:
                gross = (exit_price - lv.entry_price) * lv.lot * 100.0
                if lv.direction == "SELL":
                    gross = -gross
                days_held = max(1, (time - (getattr(lv, 'entry_time', time))).days)
                swap = days_held * lv.lot * (bt_cfg.swap_long_per_lot if lv.direction == "BUY" else bt_cfg.swap_short_per_lot)
                costs = (bt_cfg.spread_points + bt_cfg.slippage_points) * lv.lot + (bt_cfg.commission_per_lot * lv.lot)
                pnl = gross - costs + swap

                _close_level_sim(state, lv.level_id, exit_price, pnl)
                realized.append(pnl)
                win_flags.append(pnl >= 0)
                if pnl >= 0:
                    wins += 1
                else:
                    losses += 1
                equity += pnl

                trade_log.append({
                    "time": time.isoformat() if hasattr(time, "isoformat") else str(time),
                    "direction": lv.direction,
                    "entry": round(lv.entry_price, 2),
                    "exit": round(exit_price, 2),
                    "lot": lv.lot,
                    "pnl": round(pnl, 2),
                    "result": "WIN" if pnl >= 0 else "LOSS",
                })

        # basket close
        basket_pnl = basket_floating_pnl_usd(state, close)
        close_basket, _ = should_close_basket(state, basket_pnl)
        if close_basket:
            for lv in [x for x in state.levels if x.status == "OPEN"]:
                gross = (close - lv.entry_price) * lv.lot * 100.0
                if lv.direction == "SELL":
                    gross = -gross
                days_held = max(1, (time - (getattr(lv, 'entry_time', time))).days)
                swap = days_held * lv.lot * (bt_cfg.swap_long_per_lot if lv.direction == "BUY" else bt_cfg.swap_short_per_lot)
                costs = (bt_cfg.spread_points + bt_cfg.slippage_points) * lv.lot + (bt_cfg.commission_per_lot * lv.lot)
                pnl = gross - costs + swap

                _close_level_sim(state, lv.level_id, close, pnl)
                realized.append(pnl)
                win_flags.append(pnl >= 0)
                if pnl >= 0:
                    wins += 1
                else:
                    losses += 1
                equity += pnl

                trade_log.append({
                    "time": time.isoformat() if hasattr(time, "isoformat") else str(time),
                    "direction": lv.direction,
                    "entry": round(lv.entry_price, 2),
                    "exit": round(close, 2),
                    "lot": lv.lot,
                    "pnl": round(pnl, 2),
                    "result": "WIN" if pnl >= 0 else "LOSS",
                })

        peak = max(peak, equity)
        dd = peak - equity
        max_dd = max(max_dd, dd)
        eq_rows.append({"time": work.index[i], "equity": equity})

        # Daily P&L tracking for Sharpe
        cur_date = time.date() if hasattr(time, "date") else None
        if cur_date and cur_date != prev_date:
            daily_pnl.append(equity - prev_equity)
            prev_equity = equity
            prev_date = cur_date

    trades = wins + losses
    win_rate = (wins / trades * 100.0) if trades else 0.0

    pos_trades = [x for x in realized if x > 0]
    neg_trades = [x for x in realized if x < 0]
    pos = sum(pos_trades)
    neg = abs(sum(neg_trades))
    profit_factor = (pos / neg) if neg > 0 else 0.0

    avg_win = (pos / len(pos_trades)) if pos_trades else 0.0
    avg_loss = (neg / len(neg_trades)) if neg_trades else 0.0
    expectancy = (win_rate / 100 * avg_win) - ((1 - win_rate / 100) * avg_loss)

    max_consec_wins, max_consec_losses = _max_consecutive(win_flags)
    sharpe = _sharpe_ratio(daily_pnl)
    calmar = _calmar_ratio(equity, max_dd)

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
        "sharpe": sharpe,
        "calmar": calmar,
        "max_consec_wins": max_consec_wins,
        "max_consec_losses": max_consec_losses,
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "expectancy": round(expectancy, 2),
    }

    return {
        "summary": summary,
        "equity_curve": eq_df,
        "monthly": monthly,
        "trades": trade_log,
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
