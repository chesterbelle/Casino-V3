#!/usr/bin/env python3
"""
Simulation Parity Check - Validator
Compares two historian SQLite databases (Demo vs Backtest) to ensure 
1:1 execution parity and identify "Simulation Leaks".
"""

import argparse
import sqlite3
import pandas as pd
import logging

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("Parity-Validator")

def load_db(db_path: str):
    try:
        conn = sqlite3.connect(db_path)
        # In Casino V4, historian.db only has 'trades' and 'heartbeats' or similar
        # no 'signals' table.
        query = "SELECT * FROM trades"
        # Check if table exists first
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='trades';")
        if not cursor.fetchone():
            return pd.DataFrame()
        trades = pd.read_sql_query(query, conn)
        conn.close()
        return trades
    except Exception as e:
        logger.error(f"❌ Error loading {db_path}: {e}")
        return pd.DataFrame()

def compare_parity(demo_db: str, backtest_db: str, start_ts: float = None, end_ts: float = None, tolerance: float = 0.005):
    logger.info("=" * 60)
    logger.info(f"⚖️ SIMULATION PARITY CHECK")
    logger.info(f"   Demo DB    : {demo_db}")
    logger.info(f"   Backtest DB: {backtest_db}")
    if start_ts and end_ts:
        logger.info(f"   Window     : {start_ts} to {end_ts}")
    logger.info("=" * 60)

    demo_trades = load_db(demo_db)
    bt_trades = load_db(backtest_db)
    
    # Strictly filter out historical trades from Live Testnet that fall outside our golden window
    if not demo_trades.empty and start_ts and end_ts:
        demo_trades['ts_numeric'] = pd.to_numeric(demo_trades['timestamp'], errors='coerce')
        demo_trades = demo_trades[(demo_trades['ts_numeric'] >= start_ts) & (demo_trades['ts_numeric'] <= end_ts)].copy()
        
    if not bt_trades.empty and start_ts and end_ts:
        bt_trades['ts_numeric'] = pd.to_numeric(bt_trades['timestamp'], errors='coerce')
        bt_trades = bt_trades[(bt_trades['ts_numeric'] >= start_ts) & (bt_trades['ts_numeric'] <= end_ts)].copy()

    if demo_trades.empty and bt_trades.empty:
        logger.error("❌ SIMULATION FAILED: Both databases have 0 legitimate trades.")
        logger.error("❌ Cannot mathematically prove execution parity on an idle dataset (0 vs 0).")
        logger.error("❌ Rerun the Golden Session and ensure the strategy triggers at least 1 execution.")
        import sys
        sys.exit(1)

    # 1. Macro Reconciliation
    logger.info("📊 MACRO RECONCILIATION")
    logger.info(f"   Total Trades : Demo={len(demo_trades)} | Backtest={len(bt_trades)}")
    
    demo_pnl = demo_trades['net_pnl'].sum() if not demo_trades.empty and 'net_pnl' in demo_trades.columns else 0
    bt_pnl = bt_trades['net_pnl'].sum() if not bt_trades.empty and 'net_pnl' in bt_trades.columns else 0
    logger.info(f"   Total PnL    : Demo={demo_pnl:+.4f} USDT | Backtest={bt_pnl:+.4f} USDT")
    
    # 2. Match Trades
    logger.info("-" * 60)
    logger.info("🔍 MICRO RECONCILIATION (Trade by Trade)")
    
    # V4 Schema uses t0_signal_ts or t4_fill_ts. We'll use t0_signal_ts as the anchor for time.
    time_col = 't0_signal_ts'
    
    # Sort both by entry time to attempt chronological match
    if not demo_trades.empty and time_col in demo_trades.columns:
        demo_trades = demo_trades.sort_values(by=time_col).reset_index(drop=True)
    if not bt_trades.empty and time_col in bt_trades.columns:
        bt_trades = bt_trades.sort_values(by=time_col).reset_index(drop=True)

    matches = 0
    misses_demo = []
    misses_bt = []
    
    # Simple pairing by time proximity (within 10 seconds)
    paired_bt = set()
    slippage_accum = 0.0
    
    for i, d_row in demo_trades.iterrows():
        time_val = d_row.get(time_col)
        if time_val is None or pd.isna(time_val):
            time_val = d_row.get('timestamp')  # Fallback to execution timestamp for recovered ghosts
        
        try:
            d_time = float(time_val) if time_val else 0.0
        except ValueError:
            d_time = 0.0
            
        # Optional: Skip ghost trades with 0.0 entry price to prevent validating noise
        if float(d_row.get('entry_price', 0.0)) == 0.0:
            continue
        
        # Find closest backtest trade
        match = None
        min_diff = 10.0 # Max 10s difference
        
        for j, b_row in bt_trades.iterrows():
            if j in paired_bt:
                continue
                
            diff = abs(d_time - float(b_row.get(time_col, 0)))
            if diff < min_diff:
                min_diff = diff
                match = (j, b_row)
                
        if match:
            b_idx, b_row = match
            paired_bt.add(b_idx)
            matches += 1
            
            # Compare Entry Price
            d_entry = float(d_row.get('entry_price', 0))
            b_entry = float(b_row.get('entry_price', 0))
            slip_pct = abs((d_entry - b_entry) / b_entry) * 100 if b_entry > 0 else 0
            
            # Compare PnL Leakage
            d_pnl = float(d_row.get('net_pnl', 0))
            b_pnl = float(b_row.get('net_pnl', 0))
            pnl_diff = d_pnl - b_pnl
            slippage_accum += pnl_diff
            
            status = "✅ MATCH" if slip_pct < tolerance else "⚠️ SLIPPAGE"
            logger.info(f"   {status} | Demo Entry: {d_entry:.4f} vs BT Entry: {b_entry:.4f} (Diff: {slip_pct:.3f}%) | PnL Leak: {pnl_diff:+.4f}")
        else:
            misses_demo.append(d_row)
            
    # Any backtest trades not paired are misses
    for j, b_row in bt_trades.iterrows():
        if j not in paired_bt:
            misses_bt.append(b_row)

    logger.info("-" * 60)
    logger.info("👻 SIMULATION LEAKS (GHOSTS & ORPHANS)")
    
    if len(misses_demo) > 0:
        logger.error(f"   ❌ Demo executed {len(misses_demo)} trades NOT seen in Backtest (Simulation False Negative).")
    
    if len(misses_bt) > 0:
        logger.error(f"   ❌ Backtest executed {len(misses_bt)} trades NOT seen in Demo (Simulation False Positive - Liquidity/Latency Limit).")
        
    if len(misses_demo) == 0 and len(misses_bt) == 0:
        logger.info("   ✅ 100% TRADE PARITY (Exact match of opportunities).")
        
    logger.info("=" * 60)
    logger.info(f"💧 TOTAL SIMULATION LEAKAGE (PnL Diff): {slippage_accum:+.4f} USDT")
    
    if matches == len(demo_trades) and matches == len(bt_trades) and abs(slippage_accum) < 1.0:
        logger.info("🏆 VERDICT: Simulation is HIGHLY ACCURATE.")
        import sys
        sys.exit(0)
    else:
        logger.error("🐢 VERDICT: Simulation structure deviates from reality.")
        import sys
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simulation Parity Check Validator")
    parser.add_argument("--demo", type=str, required=True, help="Path to Demo historian.db")
    parser.add_argument("--backtest", type=str, required=True, help="Path to Backtest historian.db")
    parser.add_argument("--start", type=float, default=None, help="Start timestamp of Golden Session window")
    parser.add_argument("--end", type=float, default=None, help="End timestamp of Golden Session window")
    
    args = parser.parse_args()
    compare_parity(args.demo, args.backtest, args.start, args.end)
