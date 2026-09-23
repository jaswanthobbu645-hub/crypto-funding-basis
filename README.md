# Crypto Funding Rate Basis Harvest

Delta-neutral strategy that captures funding rate payments on perpetual futures.

## Performance Summary (Sep 2022 - Sep 2024)

| Metric | Value |
|--------|-------|
| Trades/month | 20.0 |
| Win rate | 52.0% |
| Sharpe ratio | 2.87 |
| Unlevered PnL/year | +6.6% |
| Post-tax at 5x leverage | +23.1% |
| Walk-forward windows | 6/6 positive |

## Strategy Logic

When funding rate Z-score exceeds ±0.8, go delta-neutral:
- SHORT perp + LONG spot when Z > +0.8
- LONG perp + SHORT spot when Z < -0.8

## Repository Structure

src/
  data/      - Data fetchers
  strategy/  - Strategy backtest code
  analysis/  - Asset scoring, regime tests

data/       

data/        - Input data files
charts/      - Generated visualizations
docs/        - Strategy documentation
tests/       - Unit tests
scripts/     - Utility scripts

## Setup

pip install -r requirements.txt

## Reproduce Results

python src/strategy/multi_asset.py

## Documentation

- STRATEGY_SPEC.md — Full strategy specification
- RESULTS_SUMMARY.txt — One-page results
- docs/ — Additional documentation

## Limitations

- Unlevered edge (6.6%) is below India's G-Sec (7%)
- Requires 3-5x leverage to be personally viable
- ARB and SEI concentration risk documented
- No live paper trading deployed
