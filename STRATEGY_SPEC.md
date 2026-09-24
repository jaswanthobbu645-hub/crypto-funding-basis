# Strategy Specification: Crypto Funding Basis Harvest

## Core Logic
The strategy takes delta-neutral positions in cryptocurrency perpetual futures to capture funding rate anomalies.

### Position
- **Long spot + short perp** when funding rate is excessively positive (perps trading at premium)
- **Short spot + long perp** when funding rate is excessively negative (perps trading at discount)
- **Delta-neutral**: The spot and perpetual positions offset each other, eliminating directional exposure to price movements.

### Signal Generation
1. Calculate the funding rate z-score over a rolling window:
   ```
   z-score = (funding_rate - mean(funding_rate)) / std(funding_rate)
   ```
   where mean and standard deviation are computed over `Z_WINDOW` periods.
2. Enter a position when the absolute z-score exceeds the entry threshold (`EZ`):
   - If z-score > `+EZ`: short perp, long spot
   - If z-score < `-EZ`: long perp, short spot
3. Exit the position when:
   - The absolute z-score falls below the exit threshold (`XZ`), OR
   - The position has been held for `MAX_HOLD` hours, whichever comes first.

## Parameters
| Parameter | Value | Description |
|-----------|-------|-------------|
| `EZ` | 1.2 | Entry threshold (z-score absolute value) |
| `XZ` | 0.5 | Exit threshold (z-score absolute value) |
| `Z_WINDOW` | 720 | Lookback window in hours (30 days of hourly data) |
| `MAX_HOLD` | 24 | Maximum position hold time in hours |
| `MF` | 0.0004 | Minimum funding rate magnitude filter (absolute value) |

*Note: Only trades where the absolute funding rate exceeds `MF` are considered for entry, even if the z-score condition is met.*

## Universe
- **Assets**: 39 Binance USDT-margined perpetual futures contracts with >12 months of funding history
- **Assets List**: BTC, ETH, BNB, XRP, ADA, MATIC, DOT, LTC, TRX, ATOM, ETC, BCH, ICP, HBAR, VET, ALGO, FTM, GRT, SAND, MANA, AXS, EGLD, THETA, RUNE, AAVE, UNI, APT, ARB, OP, INJ, LINK, NEAR, SOL, SUI, TIA, WIF, FIL, AVAX
- **Data Period**: 2024-10-09 to 2026-09-22 (23.39 months)
- **Data Source**: Binance funding rate and mark price data (hourly intervals)

## Cost Model
All costs are applied per round-trip (entry + exit):

| Cost Type | Rate | Notes |
|-----------|------|-------|
| **Maker Fee** | 0.03% | Charged when providing liquidity (limit orders) |
| **Taker Fee** | 0.05% | Charged when taking liquidity (market orders) |
| **Slippage** | 0.02% per side | Assumed baseline; tested at 0.5x, 1.0x, 1.5x multipliers |
| **Execution Model** | 70% maker, 20% taker, 10% missed | Order fill assumption |
| **Funding Payment** | Received/paid every 8 hours | Based on position size and prevailing funding rate |

### Total Cost Per Round-Trip
- **Fees**: (0.7 × 0.03% + 0.2 × 0.05%) × 2 sides = 0.082%
- **Slippage**: 0.02% × 2 sides = 0.04%
- **Total**: 0.122% per round-trip (baseline slippage)

## Entry/Exit Logic (Precise)
1. **At each hourly bar** (timestamp `t`):
   - Calculate the funding rate z-score using the previous `Z_WINDOW` hours of funding rate data.
   - Check if the absolute funding rate at `t` exceeds `MF` (to avoid noisy signals from near-zero funding).
   - If both conditions are met and no position is open:
     - If z-score > `+EZ`: open short perp + long spot position at the close of bar `t`.
     - If z-score < `-EZ`: open long perp + short spot position at the close of bar `t`.
2. **Position Monitoring** (while position is open):
   - At each subsequent hourly bar, check:
     - If the absolute z-score falls below `XZ`: close position at the close of the current bar.
     - Else if the position has been open for `MAX_HOLD` hours: close position at the close of the current bar.
   - Upon exit, realize the funding PnL accumulated since entry and close the spot/perp positions at the close price.

## Assumptions
- **Execution**: Trades are executed at the close of the hourly bar when the signal triggers.
- **Funding Accrual**: Funding payments are accrued continuously and realized upon position closure.
- **No Leverage**: The strategy assumes 1x leverage (no margin borrowing beyond the spot position).
- **No Liquidation Risk**: Delta-neutral position minimizes liquidation risk under normal market conditions.
- **Data Integrity**: Hourly funding rate and price data are accurate and survivorship-bias free.

## References
- The implementation follows the methodology described in the repository's source code, primarily in `src/strategy/multi_asset.py`.
- For exact calculations, refer to the commented source code.