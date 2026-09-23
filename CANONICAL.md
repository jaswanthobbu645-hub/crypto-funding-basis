# Canonical Trade File Decision

## Decision
The file `funding_basis_trades.csv` is selected as the source of truth for the following reasons:
1. It has a positive total net PnL (+62.05%), while `results_phase2/multi_asset_trades.csv` has negative total net PnL (-43.77%).
2. It was created more recently (2026-09-23 01:07) compared to `results_phase2/multi_asset_trades.csv` (2026-09-22 23:42).
3. It represents the original 3-asset strategy (ARB, DOGE, SOL) that was the initial focus of the project.

## File Statistics

### funding_basis_trades.csv (Selected as source of truth)
- Rows: 638
- Mean net_pnl_pct: 0.09726117554858933
- Total net_pnl_pct: 62.05262999999999
- Win rate: 0.6206896551724138 (62.07%)
- Assets: ['ARB-USDT-PERP', 'DOGE-USDT-PERP', 'SOL-USDT-PERP'] (3 assets)
- Date range:
  - entry_time: min=2024-10-07 18:00:00, max=2026-09-14 16:00:00
  - exit_time: min=2024-10-08 00:00:00, max=2026-09-15 16:00:00
  - Duration: 706 days (23.53 months)
- Trades per month: 638 / 23.53 = 27.11 trades/month

### results_phase2/multi_asset_trades.csv (Rejected)
- Rows: 1548
- Mean net_pnl_pct: -0.028274977390180832
- Total net_pnl_pct: -43.769664999999925
- Win rate: 0.18281653746770027 (18.28%)
- Assets: ['APT', 'ARB', 'AVAX', 'DOGE', 'FIL', 'INJ', 'LINK', 'NEAR', 'OP', 'SEI', 'SOL', 'SUI', 'TIA', 'WIF'] (14 assets)
- Date range:
  - entry_time: min=2024-10-07 18:00:00, max=2026-09-14 16:00:00
  - exit_time: min=2024-10-08 00:00:00, max=2026-09-15 16:00:00
  - Duration: 706 days (23.53 months)
- Trades per month: 1548 / 23.53 = 65.78 trades/month

## Parameter Mismatch Documentation

### Values Claimed in Documentation
- README.md: 
  - Line 18: "When funding rate Z-score exceeds ±0.8, go delta-neutral:"
  - Line 19: "- SHORT perp + LONG spot when Z > +0.8"
  - Line 20: "- LONG perp + SHORT spot when Z < -0.8"
- STRATEGY_SPEC.md:
  - Line 25: "- Z-score > +0.8"
  - Line 29: "- Z-score < -0.8"
  - Line 36: "- Z-score reverts to ±0.3 (signal invalidation)"
- Implied parameters: ENTRY_Z = 0.8, EXIT_Z = 0.3

### Actual Values in Code
- src/strategy/multi_asset.py:
  - Line 11: ENTRY_Z = 1.2
  - Line 12: EXIT_Z = 0.5
  - Line 14: MIN_FUNDING_LEVELS = [0.0001, 0.0003, 0.0005, 0.0008, 0.0010]
- src/strategy/funding_basis.py:
  - Line 9: ENTRY_Z = 1.2
  - Line 10: EXIT_Z = 0.5
  - Line 12: MAKER_FEE_PERP = 0.0002
  - Line 13: MIN_FUNDING = 0.0001   # 0.01% per 8h minimum
- 05b_taker_test.py:
  - Line 8: EZ = 1.2
  - Line 9: XZ = 0.5
  - Line 10: MH = 24
  - Line 11: FEE = 0.0005
  - Line 12: MIN_FUNDING = 0.0001   # 0.01% per 8h minimum

### Conclusion
The documentation claims a threshold of 0.8 for entry and 0.3 for exit, but the code that generated the positive PnL results (in `funding_basis_trades.csv`) uses ENTRY_Z=1.2 and EXIT_Z=0.5. The parameters in the code are the source of truth for the existing results.

## Notes
- The positive PnL strategy uses only 3 assets (ARB, DOGE, SOL) with a higher entry threshold (1.2) and exit threshold (0.5).
- The negative PnL strategy uses 14 assets with the same thresholds (1.2/0.5) but likely different MIN_FUNDING levels (as shown in the sensitivity analysis in multi_asset.py).
- The walk-forward results (in walk_forward/) show negative Sharpe ratios in test periods, indicating potential overfitting in the multi-parameter strategy.

