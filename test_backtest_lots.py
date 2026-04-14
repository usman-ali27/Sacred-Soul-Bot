"""Backtest Scalping vs Intraday on XAUUSD with specific lot sizes.
Scalping: 0.02 lot, $10K balance
Intraday: 0.04 lot, $10K balance
Gold: $1 per point per 0.01 lot → $100 per point per 1.0 lot
"""
import warnings
warnings.filterwarnings("ignore")

from data_fetcher import fetch_ohlcv
from trade_generator import generate_signals
from performance_tracker import compute_stats

BALANCE = 10_000

scenarios = {
    "Scalping": {
        "tfs": ["5m"],
        "rr": 1.5,
        "lb": 10,
        "lot": 0.02,
        "concepts": ["Liquidity Sweep", "FVG", "Order Flow"],
    },
    "Intraday": {
        "tfs": ["15m", "1h"],
        "rr": 2.0,
        "lb": 20,
        "lot": 0.04,
        "concepts": ["Liquidity Sweep", "MSS", "OB", "FVG"],
    },
}

# Gold: pip value per lot (1 standard lot = $100/point for XAUUSD)
GOLD_DOLLAR_PER_POINT_PER_LOT = 100  # $1/point per 0.01 lot = $100/point per 1.0 lot

print(f"{'='*70}")
print(f"  XAUUSD BACKTEST — Balance: ${BALANCE:,}")
print(f"{'='*70}")

for mode, cfg in scenarios.items():
    print(f"\n{'─'*70}")
    print(f"  {mode.upper()} — Lot: {cfg['lot']} | R:R {cfg['rr']}")
    print(f"  Concepts: {', '.join(cfg['concepts'])}")
    print(f"{'─'*70}")

    for tf in cfg["tfs"]:
        df = fetch_ohlcv("XAUUSD", tf)
        if df.empty:
            print(f"  [{tf}] No data")
            continue

        sigs = generate_signals(df, cfg["concepts"], rr_ratio=cfg["rr"], sweep_lookback=cfg["lb"])
        if sigs.empty:
            print(f"  [{tf}] 0 signals")
            continue

        stats = compute_stats(sigs)
        closed = sigs[sigs["status"] == "CLOSED"]

        # Dollar PnL calculation
        dollar_per_point = GOLD_DOLLAR_PER_POINT_PER_LOT * cfg["lot"]
        closed_pnl_points = closed["pnl"].values if not closed.empty else []
        dollar_pnls = [p * dollar_per_point for p in closed_pnl_points]
        total_dollar = sum(dollar_pnls)
        gross_profit = sum(p for p in dollar_pnls if p > 0)
        gross_loss = sum(p for p in dollar_pnls if p < 0)

        # Drawdown in dollars
        running = 0
        peak = 0
        max_dd_dollar = 0
        for p in dollar_pnls:
            running += p
            if running > peak:
                peak = running
            dd = peak - running
            if dd > max_dd_dollar:
                max_dd_dollar = dd

        # Average win/loss in dollars
        wins_d = [p for p in dollar_pnls if p > 0]
        losses_d = [p for p in dollar_pnls if p < 0]
        avg_win = sum(wins_d) / len(wins_d) if wins_d else 0
        avg_loss = abs(sum(losses_d) / len(losses_d)) if losses_d else 0

        # Average SL/TP distance in points
        avg_sl_dist = closed["risk"].mean() if not closed.empty else 0
        avg_tp_dist = (closed["risk"] * cfg["rr"]).mean() if not closed.empty else 0

        final_bal = BALANCE + total_dollar
        pct_return = (total_dollar / BALANCE) * 100

        print(f"\n  [{tf}] {len(df)} bars | {len(sigs)} signals | {len(closed)} closed")
        print(f"  ┌─────────────────────────────────────┐")
        print(f"  │ Win Rate:        {stats['win_rate']:>6}%           │")
        print(f"  │ Wins / Losses:   {stats['wins']:>4} / {stats['losses']:<4}         │")
        print(f"  │ Profit Factor:   {stats['profit_factor']:>6}            │")
        print(f"  │ Sharpe:          {stats['sharpe']:>6}            │")
        print(f"  │ Avg R:           {stats['avg_pnl_r']:>6}            │")
        print(f"  ├─────────────────────────────────────┤")
        print(f"  │ Lot Size:        {cfg['lot']:>6}            │")
        print(f"  │ $/point:         ${dollar_per_point:>6.2f}           │")
        print(f"  │ Avg SL dist:     {avg_sl_dist:>6.1f} pts         │")
        print(f"  │ Avg TP dist:     {avg_tp_dist:>6.1f} pts         │")
        print(f"  │ Avg Win ($):     ${avg_win:>8.2f}         │")
        print(f"  │ Avg Loss ($):   -${avg_loss:>8.2f}         │")
        print(f"  ├─────────────────────────────────────┤")
        print(f"  │ Gross Profit:    ${gross_profit:>10,.2f}       │")
        print(f"  │ Gross Loss:     -${abs(gross_loss):>10,.2f}       │")
        print(f"  │ Net PnL:         ${total_dollar:>10,.2f}       │")
        print(f"  │ Max DD ($):     -${max_dd_dollar:>10,.2f}       │")
        print(f"  │ Return:          {pct_return:>+7.2f}%          │")
        print(f"  │ Final Balance:   ${final_bal:>10,.2f}       │")
        print(f"  └─────────────────────────────────────┘")

        if max_dd_dollar > BALANCE * 0.10:
            print(f"  ⚠️  MAX DD (${max_dd_dollar:,.2f}) EXCEEDS 10% DD LIMIT (${BALANCE*0.10:,.2f})!")
        elif max_dd_dollar > BALANCE * 0.05:
            print(f"  🟡 Max DD is {max_dd_dollar/BALANCE*100:.1f}% — approaching daily loss limit")
        else:
            print(f"  ✅ Safe — Max DD is only {max_dd_dollar/BALANCE*100:.1f}% of balance")

print(f"\n{'='*70}")
print(f"  BACKTEST COMPLETE")
print(f"{'='*70}")
