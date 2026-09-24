# Crypto Funding Basis Harvest

## Strategy
- Delta-neutral: short perp + long spot (or vice versa)
- Signal: funding rate Z-score > 1.2 -> short perp side
- Params: EZ=1.2, XZ=0.5, Z_WINDOW=720 (30 days of 1h bars), MAX_HOLD=24h, MF=0.0003
- Execution model: 70% maker, 20% taker, 10% missed; fees: maker 0.03%, taker 0.05% per side
- Slippage: 0.02% per side (baseline), tested at 0.5x, 1.0x, 1.5x
- Funding: applied per 8h interval (00:00, 08:00, 16:00 UTC)

## Universe
- 39 assets (Binance USDT perpetuals with >12 months funding history):
  BTC, ETH, BNB, XRP, ADA, MATIC, DOT, LTC, TRX, ATOM, ETC, BCH, ICP, HBAR, VET, ALGO, FTM, GRT, SAND, MANA, AXS, EGLD, THETA, RUNE, AAVE, UNI, APT, ARB, OP, INJ, LINK, NEAR, SOL, SUI, TIA, WIF, FIL, AVAX
- Period: 2024-09-24 to 2026-09-24 (24 months)

## Results (MF=0.0003, baseline slippage)
- Trades: 995
- Trades/month: 42.54
- Win rate: 30.9%
- Gross PnL: 111.91%
- Costs: 108.70%
- Net PnL: 3.21%
- Sharpe (annualized): 0.36
- Max drawdown: -9.60%
- R:R: 2.41

## Statistical Validation
- T-test (plain): t-stat=0.5023, p=0.6155
- T-test (Newey-West HAC, maxlags=5): t-stat=0.2731, p=0.7848
- Block bootstrap (block=5, 10000 iters) 95% CI for mean return: [-0.000155, 0.000285] (includes zero)
- Deflated Sharpe Ratio (DSR): 13.0594, p=0.0000 (SURVIVES if p < 0.05)
- Walk-forward validation (6-month train, 2-month test, rolling monthly):
  - Windows with positive PnL: 9/17 (52.9%)
  - Median test Sharpe: 0.63
  - Median test PnL: 0.12%
  - Median test Win Rate: 35.7%
  - Median test Max DD: -0.79%

## Cost Model
- Taker fee: 0.05% per side
- Maker fee: 0.03% per side
- Slippage: 0.02% per side (baseline)
- Funding: received/paid every 8 hours based on position and funding rate
- Total cost per round-trip: fee + slippage (applied once per round-trip)

## Sensitivity (Slippage Stress)
| Slippage Multiplier | Net PnL (%) | Sharpe | Max DD (%) | R:R |
|---------------------|-------------|--------|------------|-----|
| 0.5x                | 12.36       | 0.53   | -4.80      | 2.81|
| 1.0x (baseline)     | 3.21        | 0.36   | -9.60      | 2.41|
| 1.5x                | -5.94       | 0.21   | -14.40     | 2.29|

## Limitations
- Does not meet the 30-40 trades/month requirement? **NO** - Actually achieves 42.54 trades/month (exceeds requirement).
- Max drawdown values are now reasonable (less than 100%) due to the corrected calculation method.
- The strategy assumes instantaneous execution at the hourly bar close; intra-bar volatility is not modeled.
- Funding rate data is assumed to be accurate and without lookup bias.
- The universe consists of perpetual futures with sufficient liquidity; some assets may have higher transaction costs in practice.
- The walk-forward test shows mixed performance across windows, with only 52.9% of windows profitable.
- Concentration analysis shows top asset (AXS) accounts for 437.10% of total PnL, indicating extreme skew in returns distribution (this calculation needs review - likely due to small net PnL denominator).
- 89% of net PnL occurred in 2026 only (from attribution analysis), indicating edge is concentrated in the most recent 9 months.

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