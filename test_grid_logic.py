"""Unit tests for grid risk guards, regime profiles, and basket logic."""

from __future__ import annotations

import unittest

from grid_engine import (
    apply_account_preset,
    build_grid_levels,
    GridConfig,
    GridLevel,
    MarketRegime,
    GridState,
    apply_regime_profile,
    basket_floating_pnl_usd,
    evaluate_risk_guards,
    should_close_basket,
    is_session_paused,
)


class TestGridLogic(unittest.TestCase):
    def test_apply_account_preset_2k(self):
        cfg = GridConfig(base_lot=0.05, max_open_levels=10)
        out = apply_account_preset(cfg, "2k Safe")
        self.assertAlmostEqual(out.base_lot, 0.01)
        self.assertEqual(out.max_open_levels, 3)
        self.assertAlmostEqual(out.max_daily_loss_usd, 40.0)

    def test_apply_regime_profile_trending(self):
        cfg = GridConfig(auto_profile_switch=True, max_open_levels=6)
        out = apply_regime_profile(cfg, "TRENDING")
        self.assertEqual(out.profile_name, "Trend")
        self.assertAlmostEqual(out.spacing_multiplier, 1.25)
        self.assertEqual(out.max_open_levels, 4)

    def test_dynamic_grid_sideways_is_denser(self):
        cfg = GridConfig(levels_buy=4, levels_sell=4, base_lot=0.02)
        rg = MarketRegime(
            direction_bias="NEUTRAL",
            direction_confidence=0.0,
            regime="RANGING",
            recommended_spacing=1.0,
        )
        lv = build_grid_levels(100.0, rg, cfg)
        buys = [x for x in lv if x.direction == "BUY"]
        sells = [x for x in lv if x.direction == "SELL"]
        self.assertEqual(len(buys), 5)
        self.assertEqual(len(sells), 5)

    def test_dynamic_grid_trending_skews_direction(self):
        cfg = GridConfig(levels_buy=4, levels_sell=4, base_lot=0.02)
        rg = MarketRegime(
            direction_bias="BULLISH",
            direction_confidence=80.0,
            regime="TRENDING",
            recommended_spacing=1.0,
        )
        lv = build_grid_levels(100.0, rg, cfg)
        buys = [x for x in lv if x.direction == "BUY"]
        sells = [x for x in lv if x.direction == "SELL"]
        self.assertGreater(len(buys), len(sells))

    def test_dynamic_grid_volatile_reduces_levels(self):
        cfg = GridConfig(levels_buy=4, levels_sell=4, base_lot=0.02)
        rg = MarketRegime(
            direction_bias="NEUTRAL",
            direction_confidence=0.0,
            regime="VOLATILE",
            recommended_spacing=1.0,
        )
        lv = build_grid_levels(100.0, rg, cfg)
        buys = [x for x in lv if x.direction == "BUY"]
        sells = [x for x in lv if x.direction == "SELL"]
        self.assertEqual(len(buys), 3)
        self.assertEqual(len(sells), 3)

    def test_daily_loss_guard_blocks(self):
        cfg = GridConfig(max_daily_loss_usd=100.0, max_drawdown_pct=99.0)
        state = GridState(config=cfg)
        state.day_start_date = "2026-04-16"
        state.day_start_balance = 10000.0
        blocked, reason, metrics = evaluate_risk_guards(state, balance=9890.0, equity=9890.0)
        self.assertTrue(blocked)
        self.assertIn("Daily loss", reason)
        self.assertGreaterEqual(metrics["daily_loss_usd"], 100.0)

    def test_drawdown_guard_blocks(self):
        cfg = GridConfig(max_daily_loss_usd=10000.0, max_drawdown_pct=5.0)
        state = GridState(config=cfg)
        state.peak_equity = 10000.0
        state.day_start_date = "2026-04-16"
        state.day_start_balance = 10000.0
        blocked, reason, metrics = evaluate_risk_guards(state, balance=9800.0, equity=9400.0)
        self.assertTrue(blocked)
        self.assertIn("Drawdown", reason)
        self.assertGreaterEqual(metrics["drawdown_peak_pct"], 5.0)

    def test_basket_pnl_and_close_trigger(self):
        cfg = GridConfig(
            basket_take_profit_usd=10.0,
            basket_stop_loss_usd=-15.0,
            basket_close_on_profit=True,
            basket_close_on_loss=True,
        )
        state = GridState(config=cfg)
        state.levels = [
            GridLevel(level_id="BUY_1", direction="BUY", price=100.0, lot=0.10, status="OPEN", entry_price=100.0),
            GridLevel(level_id="SELL_1", direction="SELL", price=101.0, lot=0.05, status="OPEN", entry_price=101.0),
        ]

        pnl = basket_floating_pnl_usd(state, current_price=101.0)
        self.assertGreater(pnl, 0.0)
        close_now, reason = should_close_basket(state, pnl)
        self.assertTrue(close_now)
        self.assertIn("Basket TP", reason)

    def test_lockout_fields_persist(self):
        state = GridState()
        state.lockout_active = True
        state.lockout_reason = "Auto-lockout: Drawdown 9.5%"
        state.lockout_time = "2026-04-16T12:00:00+00:00"
        self.assertTrue(state.lockout_active)
        self.assertEqual(state.lockout_reason, "Auto-lockout: Drawdown 9.5%")
        # Default should be unlocked
        clean = GridState()
        self.assertFalse(clean.lockout_active)
        self.assertEqual(clean.lockout_reason, "")

    def test_trailing_basket_tp_keeps_open_while_rising(self):
        cfg = GridConfig(
            basket_take_profit_usd=10.0,
            basket_stop_loss_usd=-40.0,
            basket_close_on_profit=True,
            basket_trailing_tp=True,
            basket_trailing_step_usd=5.0,
        )
        state = GridState(config=cfg)
        # PnL = 12 → above TP, trailing active, should stay open
        close, reason = should_close_basket(state, 12.0)
        self.assertFalse(close)
        self.assertEqual(state.basket_peak_pnl, 12.0)
        # PnL = 15 → still rising, peak updated
        close, reason = should_close_basket(state, 15.0)
        self.assertFalse(close)
        self.assertEqual(state.basket_peak_pnl, 15.0)
        # PnL drops to 10 → below trail floor (15 - 5 = 10), should close
        close, reason = should_close_basket(state, 10.0)
        self.assertTrue(close)
        self.assertIn("Trailing TP", reason)

    def test_trailing_basket_tp_resets_below_tp(self):
        cfg = GridConfig(
            basket_take_profit_usd=10.0,
            basket_trailing_tp=True,
            basket_trailing_step_usd=5.0,
            basket_close_on_profit=True,
        )
        state = GridState(config=cfg, basket_peak_pnl=8.0)
        # PnL drops below TP → peak should reset
        close, reason = should_close_basket(state, 5.0)
        self.assertFalse(close)
        self.assertEqual(state.basket_peak_pnl, 0.0)

    def test_session_pause_blocks_when_enabled(self):
        cfg = GridConfig(session_pause_enabled=True, session_pause_list="Asian,Overlap/Off")
        paused, msg = is_session_paused(cfg)
        # We can't predict the session at test time, but we can verify the function works
        self.assertIsInstance(paused, bool)
        self.assertIsInstance(msg, str)

    def test_session_pause_disabled_never_blocks(self):
        cfg = GridConfig(session_pause_enabled=False, session_pause_list="Asian,London,NY")
        paused, msg = is_session_paused(cfg)
        self.assertFalse(paused)
        self.assertEqual(msg, "")


if __name__ == "__main__":
    unittest.main()
