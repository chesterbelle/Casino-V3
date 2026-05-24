# Session Close: Audit Infrastructure Refactor & Exit Edge Discovery Ready

## Summary: Audit & Discovery Infrastructure Certified
In this session, we refactored the audit pipeline to align with the actual SQLite schema of `historian.db`. We created `utils/trajectory_core.py` as the single source of truth for loading audit data (signals, trajectories, and decision traces).

### Key Accomplishments
1.  **Refactored Audit Data Extraction**:
    -   `utils/trajectory_core.py` now correctly queries the `signals` and `price_samples` tables using timestamp range correlation instead of non-existent `signal_id` columns.
    -   `utils/setup_edge_auditor.py` and `utils/exit_edge_auditor.py` are now compatible with this robust data extraction pipeline.
2.  **Audit Functionality Preserved**:
    -   The `--audit` flag in `backtest.py` already captures all necessary data (signals, price samples with `micro_z`, traces) and does **not** need modification.
3.  **Exit Strategy Tooling**:
    -   `utils/exit_edge_auditor.py` is now fully operational and ready to sweep rule families (`delta_z`, `time_stagnant`, etc.) against empirical trajectory data to define Pillar 4 (Delta Invalidation) and Pillar 5 (Time Exit).

---

## 📈 Next Steps (For Rule Discovery)
1.  **Data Collection**:
    -   Run `python utils/reset_data.py`.
    -   Run `python backtest.py --audit --symbol <SYMBOL>` for all 4 certified assets (BNB, SOL, SUI, AVAX).
2.  **Rule Discovery**:
    -   Run `python utils/exit_edge_auditor.py --db data/historian.db --out docs/exit_edge_report.txt`.
3.  **Implementation**:
    -   Review `docs/exit_edge_report.txt` to identify the rule with the highest `precision` (>0.7 recommended).
    -   Implement the winning rule as a new pillar in `croupier/components/slim_exit_engine.py`.
    -   Backtest the new strategy implementation using `strategy-audit.md` (without `--audit`) to verify PnL improvement.
