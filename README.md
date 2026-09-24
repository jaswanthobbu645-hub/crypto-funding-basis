# Crypto Funding Basis Harvest

A market-neutral strategy capturing funding rate inefficiencies in cryptocurrency perpetual futures.

## Key Results (MF=0.0004, Baseline Slippage)
| Metric | Value |
|--------|-------|
| Trades per month | 25.22 |
| Net PnL (23.39 months) | +22.19% |
| Annualized Sharpe ratio | 2.58 |
| Maximum drawdown | -2.19% |
| Profit-to-loss ratio (R:R) | 2.70 |
| Newey-West HAC p-value | 0.0441 |
| Deflated Sharpe Ratio (DSR) | 3.42 (p=0.0003) |
| Walk-forward windows profitable | 12/17 (70.6%) |

## Quick Start
1. Clone the repository and install dependencies:
   ```bash
   git clone https://github.com/jaswanthobbu645-hub/crypto-funding-basis.git
   cd crypto-funding-basis
   pip install -r requirements.txt
   ```
2. Run the data downloader (may take 30-60 minutes):
   ```bash
   python src/data/download_expanded_v2.py
   ```
3. Run the backtest for MF sensitivity:
   ```bash
   python src/strategy/multi_asset.py
   ```
4. Perform walk-forward validation:
   ```bash
   python src/analysis/walk_forward_funding.py
   ```
5. Run statistical tests:
   ```bash
   python src/analysis/statistical_tests.py
   ```
6. Generate the professional chart suite and report:
   ```bash
   python src/analysis/generate_charts.py
   ```
7. All results will be saved in the `results_phase2/` directory and charts in `charts/`.

## Strategy Summary
- **Signal**: Funding rate Z-score > 1.2 -> short perp side (or < -1.2 -> long perp side)
- **Parameters**: EZ=1.2, XZ=0.5, Z_WINDOW=720 (30 days of 1h bars), MAX_HOLD=24h, MF=0.0004
- **Execution model**: 70% maker, 20% taker, 10% missed; fees: maker 0.03%, taker 0.05% per side
- **Slippage**: 0.02% per side (baseline), tested at 0.5x, 1.0x, 1.5x
- **Funding**: Applied per 8-hour interval (00:00, 08:00, 16:00 UTC)
- **Universe**: 39 Binance USDT perpetuals with >12 months funding history
- **Period**: 2024-10-09 to 2026-09-22 (23.39 months)

## Details & Visualizations
- [Full Executive Report](REPORT.md): 2-page deep dive with embedded charts and analysis
- [Chart Suite](charts/): 10 publication-quality visualizations (equity curve, monthly returns, walk-forward, etc.)

## Repository Structure
```
crypto-funding-basis/
├── src/
│   ├── strategy/       # Core backtest logic
│   ├── analysis/       # Statistical tests, walk-forward, tearsheets, charts
│   └── data/           # Data downloaders
├── results_phase2/     # All outputs: trades, statistics, charts (via symlink)
├── charts/             # Generated publication-quality figures
├── data/expanded/      # Historical funding and price data (39 assets)
├── REPORT.md           # Executive summary (this README is the 1-pager)
├── STRATEGY_SPEC.md    # Exact strategy specification
├── requirements.txt    # Dependency versions
└── README.md           # This file
```

## Limitations
- Execution assumes hourly bar close; intra-bar volatility not modeled.
- Funding rate data accuracy and lookup bias not tested.
- Some assets may have higher transaction costs in practice.
- Walk-forward shows mixed performance (70.6% profitable windows).
- Top asset (INJ) contributes ~49% of total PnL.
- 76% of net PnL occurred in 2026 only (edge concentrated in recent 9 months).