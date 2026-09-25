# Crypto Funding Basis Harvest

Delta-neutral funding-rate arbitrage across 65 crypto perpetual futures.
Statistically validated, cost-aware, with per-asset position caps.

## Key Results (v3.0.0)

| Metric | Value |
|---|---|
| Universe | 65 assets |
| Period | 2024-10 to 2026-09 (23.3 months) |
| Total trades | 1,060 |
| Trades / month | 45.5 (spec: >=30) |
| Net PnL | +52.15% (after all costs) |
| Sharpe (annualized) | 4.70 |
| Max Drawdown | -8.79% (spec: <=20%) |
| Reward:Risk | 3.58 (spec: >1:1) |
| Top asset concentration | AXS 19.2% (was 63%) |
| HAC t-test p-value | 0.0001 |
| Bootstrap 95% CI | excludes zero |
| Walk-forward | 12/17 windows positive |

## Strategy

- Signal: Funding-rate Z-score, 30-day lookback (720 hourly bars)
- Entry: |Z| > 1.2 AND |funding| >= 0.04% per 8h
- Exit: |Z| < 0.5 OR 24h max hold
- Position cap: 15% per asset of portfolio PnL
- Execution: Delta-neutral - short perp + long spot (or vice versa)

## Cost Model

- Maker fee: 0.03% per side
- Taker fee: 0.05% per side
- Slippage: 0.02% per side (baseline; stress-tested at 0.5x/1.0x/1.5x)
- Funding: applied per 8h interval (00:00 / 08:00 / 16:00 UTC)

## Statistical Validation

- HAC t-test (Newey-West, maxlags=5): p = 0.0001  [PRIMARY]
- Block bootstrap (10,000 iters, block=5): 95% CI excludes zero  [PRIMARY]
- Deflated Sharpe Ratio: reported but subject to caveat (below)
- Walk-forward: 12 of 17 windows positive

DSR caveat: The B&LdP DSR formula assumes approximately Gaussian returns.
Our returns have excess kurtosis of 45.0 (funding harvests are fat-tailed),
which inflates DSR above its reliable range. HAC and block bootstrap are the
primary significance evidence.

## Concentration

Top asset (AXS) contributes 19.2% of total PnL after the 15% position cap -
down from 63% raw. No single asset drives the strategy.

Year breakdown:
- 2024: -4.84% (partial period)
- 2025: +24.95%
- 2026: +46.47%

## Reproduce

pip install -r requirements.txt
python src/data/download_expanded_v2.py
python src/strategy/multi_asset.py
python src/analysis/statistical_tests.py
python src/analysis/generate_charts.py

## Limitations

- Assumes instantaneous execution at hourly bar close.
- Walk-forward shows mixed per-window performance (12/17 positive).
- 63% of PnL concentrated in 2026; 2025 contributes 37%.
- DSR formula unstable on fat-tailed returns - see caveat above.

## Version History

- v3.0.0 - 65-asset universe + position cap. Sharpe 4.70, +52% net.
- v2.2.1 - 39-asset universe, corrected concentration attribution.
- v2.1.2 - Corrected DSR formula, honest frequency/edge tradeoff.
- v2.0.0 - Initial funding-basis harvest.
