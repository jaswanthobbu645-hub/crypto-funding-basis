# Strategy Specification: Funding Rate Basis Harvest v2.0

## Executive Summary

Delta-neutral funding rate strategy. Captures funding rate payments when 
funding reaches statistically extreme levels (crowded positioning).

- Universe: 14 perpetual futures (SEI, APT, FIL, WIF, LINK, INJ, SOL, 
  OP, TIA, SUI, DOGE, ARB, NEAR, AVAX)
- Trades/month: 20.0
- Unlevered PnL/year: +6.6%
- Sharpe ratio: 2.87 (institutional-grade)
- Walk-forward: 6/6 positive windows

## Signal

Funding Rate Z-Score:
  Z = (current funding - 30-day rolling mean) / 30-day rolling std

Computed hourly on rolling 720-hour window (30 days).

## Entry Rules

SHORT Perp + LONG Spot when:
- Z-score > +0.8
- AND |funding rate| >= 0.03% per 8h

LONG Perp + SHORT Spot when:
- Z-score < -0.8
- AND |funding rate| >= 0.03% per 8h

Both positions equal notional (delta-neutral).

## Exit Rules

- Z-score reverts to ±0.3 (signal invalidation)
- OR 24-hour time stop
- Whichever occurs first

## Cost Model (Problem Statement Compliant)

- Maker fee: 0.03% per side
- Taker fee: 0.05% per side
- Realistic fills: 70% maker, 20% taker, 5% missed
- Funding collected every 8 hours (00:00, 08:00, 16:00 UTC)

## Backtest Results (Sep 2022 - Sep 2024, 24 months)

| Metric | Value |
|--------|-------|
| Total trades | 479 |
| Trades/month | 20.0 |
| Win rate | 52.0% |
| Total PnL | +13.23% |
| PnL/year (unlevered) | +6.6% |
| Sharpe ratio | 2.87 |

## Walk-Forward Validation

All 6 non-overlapping 3-month windows positive.

## Leverage Analysis (Indian Investor Perspective)

| Leverage | Pre-Tax | Post-Tax (30%) | vs G-Sec (7%) |
|----------|---------|----------------|---------------|
| 1x | +6.6% | +4.6% | -2.4% (NOT worth) |
| 3x | +19.8% | +13.9% | +6.9% (WORTH IT) |
| 5x | +33.0% | +23.1% | +16.1% (EXCELLENT) |
| 8x | +52.8% | +37.0% | +30.0% (EXCELLENT) |

Delta-neutral position supports 3-5x leverage safely. Sharpe 2.87 
implies low probability of sustained drawdown.

## Known Limitations

1. Thin edge unlevered: +6.6% is below India's 7% G-Sec
2. Requires 3-5x leverage to be personally viable
3. ARB and SEI concentration risk documented
4. No live paper trading deployed yet
5. Requires 30% crypto tax compliance

## Future Work (HFT-Grade Roadmap)

1. Add CVD (Cumulative Volume Delta) signal — requires raw taker data
2. Add OI change signal — requires OI history
3. Cross-exchange funding arbitrage — Binance vs Bybit vs OKX
4. Order book imbalance — requires L2 data
5. Live deployment with monitoring dashboard
6. Multi-leg portfolio optimization (Kelly sizing)

## Files Reference

- 12_multi_asset_strategy.py — Main strategy backtest
- 16_asset_quality.py — Asset quality scoring
- 17_atr_regime.py — ATR regime filter test
- 18_volume_momentum_test.py — Volume/momentum test
- 19_subset_test.py — Asset subset comparison
- 20_leverage_analysis.py — Leverage analysis

================================================================================