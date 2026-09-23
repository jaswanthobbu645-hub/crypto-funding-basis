# Architecture

## System Layers

1. Data Layer (src/data/)
   - Downloads OHLCV + funding rates from Binance
   - Saves to parquet files

2. Strategy Layer (src/strategy/)
   - Computes funding Z-scores
   - Simulates delta-neutral trades
   - Applies realistic cost model

3. Analysis Layer (src/analysis/)
   - Asset quality scoring
   - Regime filter tests
   - Parameter sweeps
   - Subset comparison

4. Reporting Layer
   - Trade logs → CSV
   - Charts → PNG
   - Documentation → Markdown

## Data Flow

Binance API → src/data/download_expanded.py
           → data/expanded/*.parquet
           → src/strategy/multi_asset.py
           → results_phase2/multi_asset_trades.csv
           → charts/equity_curve.png

## Key Design Decisions

1. Delta-neutral structure: eliminates directional risk
2. Z-score based entry: adaptive to each asset's funding history
3. Multiple filters tested (ATR, volume, momentum): all reduced total PnL, dropped
