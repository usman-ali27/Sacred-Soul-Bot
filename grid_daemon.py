"""
Sacred Soul — Grid Execution Daemon
Monitors grid_state.json and executes levels on MT5.
"""
import time
import json
import logging
from pathlib import Path
from datetime import datetime

from grid_engine import (
    load_grid_state, save_grid_state, check_levels_hit, 
    mark_level_open, place_grid_order_mt5, count_open_levels,
    should_close_basket, basket_floating_pnl_usd, mark_level_closed,
    close_grid_position_mt5, analyze_market_direction, reanchor_grid
)
from mt5_trader import load_credentials, connect_mt5, is_mt5_alive, ensure_mt5_connected, get_live_price, build_mt5_config_from_credentials, modify_sl_tp
from data_fetcher import fetch_ohlcv

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.FileHandler("grid_daemon.log"), logging.StreamHandler()]
)
logger = logging.getLogger("grid_daemon")

def sync_with_mt5_positions(state, mt5_cfg):
    """Checks if OPEN levels in state still exist as positions in MT5."""
    from mt5_trader import get_open_positions
    from grid_engine import mark_level_closed
    
    positions = get_open_positions()
    active_tickets = [p.get("ticket") for p in positions]
    
    changed = False
    for lv in state.levels:
        if lv.status == "OPEN" and lv.ticket:
            if lv.ticket not in active_tickets:
                logger.info(f"Detected manual close for {lv.level_id} (Ticket: {lv.ticket})")
                # We mark it closed. In a manual close, we don't know the exact profit 
                # easily without history, so we'll mark it 0 or look it up.
                mark_level_closed(state, lv.level_id, 0.0, 0.0)
                changed = True
    return changed

def apply_individual_trailing_stop(state, current_price):
    """
    Check each OPEN level for trailing SL opportunities.
    If the price has moved significantly in favor, move the SL to lock in profit.
    """
    if not getattr(state.config, 'trailing_sl_enabled', False):
        return False
    
    changed = False
    # Gold: 1 pip = 0.1 price units. 30 pips = 3.0$
    step_price = getattr(state.config, 'trailing_sl_step_pips', 30.0) / 10.0
    
    for lv in state.levels:
        if lv.status != "OPEN" or not lv.ticket:
            continue
            
        # Ensure peak_price is initialized
        if not hasattr(lv, 'peak_price') or lv.peak_price == 0:
            lv.peak_price = lv.entry_price if lv.entry_price > 0 else current_price

        # Update Peak Price and check SL move
        if lv.direction == "BUY":
            if current_price > lv.peak_price:
                lv.peak_price = current_price
                changed = True
            
            # Trailing SL floor
            new_sl = lv.peak_price - step_price
            # Move SL up if it's at least 1.0$ above current SL
            if new_sl > (lv.sl_price + 1.0):
                logger.info(f"Trailing SL: {lv.level_id} {lv.sl_price} -> {new_sl}")
                if modify_sl_tp(lv.ticket, new_sl):
                    lv.sl_price = new_sl
                    changed = True
                    
        elif lv.direction == "SELL":
            if current_price < lv.peak_price or lv.peak_price == 0:
                lv.peak_price = current_price
                changed = True
            
            # Trailing SL ceiling
            new_sl = lv.peak_price + step_price
            # Move SL down if it's at least 1.0$ below current SL
            if new_sl < (lv.sl_price - 1.0) and lv.sl_price > 0:
                logger.info(f"Trailing SL: {lv.level_id} {lv.sl_price} -> {new_sl}")
                if modify_sl_tp(lv.ticket, new_sl):
                    lv.sl_price = new_sl
                    changed = True
                    
    return changed

def main():
    logger.info("Grid Daemon starting...")
    
    # 1. Load MT5 Credentials
    creds = load_credentials()
    if not creds:
        logger.error("No MT5 credentials found. Exiting.")
        return
    
    mt5_cfg = build_mt5_config_from_credentials(creds)
    
    # 2. Initial Connect
    ok, msg = connect_mt5(mt5_cfg)
    if not ok:
        logger.error(f"Failed to connect to MT5: {msg}")
        return
    logger.info("Connected to MT5.")

    loop_counter = 0
    while True:
        try:
            loop_counter += 1
            # 3. Load State
            state = load_grid_state()
            if not state.active:
                time.sleep(5)
                continue
            
            # ── DYNAMIC RE-SPACING / RE-ANCHORING ──
            # Re-anchor if: 
            # a) It's the first loop and we are active
            # b) Periodic check (every 150 loops / ~5 mins)
            # c) Price drift is significant (> 1.5 * spacing) and no open positions
            
            should_reanchor = False
            price_data = get_live_price(mt5_cfg.symbol)
            current_bid = price_data["bid"] if price_data else 0
            
            if state.active and current_bid > 0:
                spacing = state.regime.recommended_spacing if state.regime.recommended_spacing > 0 else 10.0
                drift = abs(current_bid - state.anchor_price)
                
                if loop_counter == 1:
                    logger.info("Startup check: Re-anchoring grid to current price.")
                    should_reanchor = True
                elif loop_counter % 150 == 0:
                    logger.info("Periodic check: Performing ATR re-analysis and re-anchoring.")
                    should_reanchor = True
                elif drift > (spacing * 1.5) and count_open_levels(state) == 0:
                    logger.info(f"Drift detected ({drift:.2f} > {spacing*1.5:.2f}): Re-anchoring grid.")
                    should_reanchor = True

            if should_reanchor:
                df = fetch_ohlcv(mt5_cfg.symbol, state.config.timeframe)
                if not df.empty:
                    new_regime = analyze_market_direction(df, state.config.spacing_multiplier)
                    state.regime = new_regime
                    if reanchor_grid(state, current_bid):
                        logger.info(f"Grid re-anchored at {current_bid}. New Spacing: {new_regime.recommended_spacing:.2f}")
                        save_grid_state(state)

            # 4. Health Check
            if not is_mt5_alive():
                ensure_mt5_connected(mt5_cfg)
            
            # ── SYNC: Check if user manually closed trades ──
            if sync_with_mt5_positions(state, mt5_cfg):
                save_grid_state(state)
            
            # ── NEWS GUARD: Check for high-impact events ──
            from news_guard import is_trading_blocked_by_news
            news_blocked, news_reason = is_trading_blocked_by_news()
            
            if news_blocked:
                logger.warning(f"GRID BLOCKED: {news_reason}")
                time.sleep(10)
                continue

            # 5. Get Live Price
            price_data = get_live_price(mt5_cfg.symbol)
            if not price_data or "bid" not in price_data:
                time.sleep(1)
                continue
            
            price = price_data["bid"]
            if price <= 0:
                time.sleep(1)
                continue
            
            # 6. Check for Level Hits
            triggered = check_levels_hit(state, price)
            for lv in triggered:
                logger.info(f"Triggered level: {lv.level_id} at {price}")
                
                # Check max open levels
                if count_open_levels(state) >= state.config.max_open_levels:
                    logger.warning(f"Max open levels reached ({state.config.max_open_levels}). Skipping {lv.level_id}")
                    continue
                
                # Place order
                res = place_grid_order_mt5(lv, mt5_cfg.symbol, state.config.magic if hasattr(state.config, "magic") else 202606)
                if res.get("success"):
                    logger.info(f"Order filled: {lv.level_id} | Ticket: {res.get('ticket')}")
                    mark_level_open(state, lv.level_id, res.get("ticket"), res.get("price"))
                    save_grid_state(state)
                else:
                    logger.error(f"Failed to fill {lv.level_id}: {res.get('message')}")
            
            # 7. Check Basket Management (Exit logic)
            open_lvs = [l for l in state.levels if l.status == "OPEN"]
            if open_lvs:
                floating_pnl = basket_floating_pnl_usd(state, price)
                should_close, reason = should_close_basket(state, floating_pnl)
                
                if should_close:
                    logger.info(f"Basket close triggered: {reason} | PnL: ${floating_pnl:.2f}")
                    for olv in open_lvs:
                        c_res = close_grid_position_mt5(mt5_cfg, olv)
                        if c_res.get("success"):
                            mark_level_closed(state, olv.level_id, c_res.get("price"), c_res.get("profit"))
                            logger.info(f"Closed {olv.level_id} at {c_res.get('price')}")
                        else:
                            logger.error(f"Failed to close {olv.level_id}: {c_res.get('message')}")
                    save_grid_state(state)

                # ── TRAILING SL: Update individual trailing stops ──
                if apply_individual_trailing_stop(state, price):
                    save_grid_state(state)

        except Exception as e:
            logger.exception(f"Loop error: {e}")
            
        time.sleep(2)

if __name__ == "__main__":
    main()
