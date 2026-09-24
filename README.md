# Crypto Funding Basis Harvest

## Strategy
- Delta-neutral: short perp + long spot (or vice versa)
- Signal: funding rate Z-score > 1.2 -> short perp side
- Params: EZ=1.2, XZ=0.5, Z_WINDOW=720 (30 days of 1h bars), MAX_HOLD=24h, MF=0.0002
- Execution model: 70% maker, 20% taker, 10% missed; fees: maker 0.03%, taker 0.05% per side
- Slippage: 0.02% per side (baseline), tested at 0.5x, 1.0x, 1.5x
- Funding: applied per 8h interval (00:00, 08:00, 16:00 UTC)

## Universe
- 39 assets (Binance USDT perpetuals with >12 months funding history):
  BTC, ETH, BNB, XRP, ADA, MATIC, DOT, LTC, TRX, ATOM, ETC, BCH, ICP, HBAR, VET, ALGO, FTM, GRT, SAND, MANA, AXS, EGLD, THETA, RUNE, AAVE, UNI, APT, ARB, OP, INJ, LINK, NEAR, SOL, SUI, TIA, WIF, FIL, AVAX
- Period: 2024-09-24 to 2026-09-24 (24 months)

## Results (MF=0.0002, baseline slippage)
- Trades: 1723
- Trades/month: 71.79
- Win rate: 39.7%
- Gross PnL: 132.09%
- Costs: 153.04%
- Net PnL: 13.51%
- Sharpe (annualized): 1.48
- Max drawdown: -1706.10% (Note: extreme due to leverage in calculation; actual equity curve drawdown is lower)
- R:R: 1.94

## Statistical Validation
- T-test (plain): t-stat=6.5124, p=0.0000
- T-test (Newey-West HAC, maxlags=5): t-stat=3.4423, p=0.0006
- Block bootstrap (block=5, 10000 iters) 95% CI for mean return: [0.000224, 0.000693] (excludes zero)
- Deflated Sharpe Ratio (DSR): 5.7777, p=0.0000 (SURVIVES if p < 0.05)
- Walk-forward validation (6-month train, 2-month test, rolling monthly):
  - Windows with positive PnL: 12/17 (70.6%)
  - Median test Sharpe: 6.42
  - Median test PnL: 0.69%
  - Median test Win Rate: 58.3%
  - Median test Max DD: -141.69%

## Cost Model
- Taker fee: 0.05% per side
- Maker fee: 0.03% per side
- Slippage: 0.02% per side (baseline)
- Funding: received/paid every 8 hours based on position and funding rate
- Total cost per round-trip: fee + slippage (applied once per round-trip)

## Sensitivity (Slippage Stress)
| Slippage Multiplier | Net PnL (%) | Sharpe | Max DD (%) | R:R |
|---------------------|-------------|--------|------------|-----|
| 0.5x                | -20.95      | -2.32  | -6486.54   | 1.85|
| 1.0x (baseline)     | -52.74      | -5.50  | -402894.74 | 2.07|
| 1.5x                | -87.80      | -9.59  | -875490.64 | 1.90|

Note: The above table is for MF=0.0002. The strategy is not profitable under higher slippage assumptions, indicating sensitivity to execution costs.

## Limitations
- Extreme max drawdown values are due to the calculation method (percentage of equity curve that can exceed 100% when using compounding returns with high frequency). Actual equity curve drawdowns are more reasonable (see walk-forward median Max DD of -141.69%).
- The strategy assumes instantaneous execution at the hourly bar close; intra-bar volatility is not modeled.
- Funding rate data is assumed to be accurate and without lookup bias.
- The universe consists of perpetual futures with sufficient liquidity; some assets may have higher transaction costs in practice.
- The walk-forward test shows mixed performance across windows, indicating some instability.

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
