# Crypto Funding Basis Harvest

## Strategy
- Delta-neutral: short perp + long spot (or vice versa)
- Signal: funding rate Z-score > 1.2 -> short perp side
- Params: EZ=1.2, XZ=0.5, Z_WINDOW=720 (30 days of 1h bars), MAX_HOLD=24h, MF=0.0004
- Execution model: 70% maker, 20% taker, 10% missed; fees: maker 0.03%, taker 0.05% per side
- Slippage: 0.02% per side (baseline), tested at 0.5x, 1.0x, 1.5x
- Funding: applied per 8h interval (00:00, 08:00, 16:00 UTC)

## Universe
- 39 assets (Binance USDT perpetuals with >12 months funding history):
  BTC, ETH, BNB, XRP, ADA, MATIC, DOT, LTC, TRX, ATOM, ETC, BCH, ICP, HBAR, VET, ALGO, FTM, GRT, SAND, MANA, AXS, EGLD, THETA, RUNE, AAVE, UNI, APT, ARB, OP, INJ, LINK, NEAR, SOL, SUI, TIA, WIF, FIL, AVAX
- Period: 2024-09-24 to 2026-09-24 (24 months)

## Results (MF=0.0004, baseline slippage)
- Trades: 589
- Trades/month: 25.22
- Win rate: 44.0%
- Gross PnL: 51.51%
- Costs: 29.32%
- Net PnL: 22.19%
- Sharpe (annualized): 2.58
- Max drawdown: -2.19%
- R:R: 2.70

## Statistical Validation
- T-test (plain): t-stat=3.5930, p=0.0004
- T-test (Newey-West HAC, maxlags=5): t-stat=2.0133, p=0.0441
- Block bootstrap (block=5, 10000 iters) 95% CI for mean return: [0.000095, 0.000730] (excludes zero)
- Deflated Sharpe Ratio (DSR): 3.4180, p=0.0003 (SURVIVES if p < 0.05)
- Walk-forward validation (6-month train, 2-month test, rolling monthly):
  - Windows with positive PnL: 12/17 (70.6%)
  - Median test Sharpe: 6.42
  - Median test PnL: 0.69%
  - Median test Win Rate: 58.3%
  - Median test Max DD: -0.16%

## Cost Model
- Taker fee: 0.05% per side
- Maker fee: 0.03% per side
- Slippage: 0.02% per side (baseline)
- Funding: received/paid every 8 hours based on position and funding rate
- Total cost per round-trip: fee + slippage (applied once per round-trip)

## Sensitivity (Slippage Stress)
| Slippage Multiplier | Net PnL (%) | Sharpe | Max DD (%) | R:R |
|---------------------|-------------|--------|------------|-----|
| 0.5x                | 28.24       | 3.24   | -1.10      | 3.15|
| 1.0x (baseline)     | 22.19       | 2.58   | -2.19      | 2.70|
| 1.5x                | 14.57       | 2.03   | -5.17      | 2.63|

## Limitations
- Max drawdown values are now reasonable (less than 100%) due to the corrected calculation method.
- The strategy assumes instantaneous execution at the hourly bar close; intra-bar volatility is not modeled.
- Funding rate data is assumed to be accurate and without lookup bias.
- The universe consists of perpetual futures with sufficient liquidity; some assets may have higher transaction costs in practice.
- The walk-forward test shows mixed performance across windows, with 70.6% of windows profitable.
- Concentration analysis shows top asset (AXS) accounts for a significant portion of total PnL (see attribution analysis).
- 76% of net PnL occurred in 2026 only (from attribution analysis), indicating edge is concentrated in the most recent 9 months.

## The Frequency/Edge Tension
As we tighten the funding threshold to boost edge quality, trade count falls. As we loosen it to hit frequency, edge collapses. This is the central tradeoff the problem statement describes. Our strategy sits on this frontier; we document where and why.

- **MF=0.0002**: Very high frequency (75.5 trades/month) but strongly negative edge (Sharpe=-5.50, PnL=-52.74%) – too loose, captures noise or adverse selection.
- **MF=0.0003**: Frequency compliant (42.5 trades/month) but edge too weak to be statistically significant (HAC p=0.78, DSR does not survive).
- **MF=0.0004**: Near-frequency (25.2 trades/month) with statistically significant edge (HAC p=0.044, DSR survives) and solid PnL (+22.19%). Represents the best balance.
- **MF=0.0005**: Low frequency (14.7 trades/month) but strong edge (Sharpe=3.82, HAC p=0.0037) and highest PnL (+32.92%). Statistically valid but does not meet frequency requirement.

## Reproduce
1. Clone the repository and install dependencies (if any).
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
6. Generate tearsheet:
   ```bash
   python src/analysis/generate_tearsheet.py
   ```
7. All results will be saved in the `results_phase2/` directory.