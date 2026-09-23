# Data Dictionary

## Input Data (data/combined_all.pkl and data/expanded/*.parquet)

| Column | Type | Description |
|--------|------|-------------|
| timestamp | datetime | Hourly bar timestamp (UTC) |
| open | float | Opening price |
| high | float | Highest price in bar |
| low | float | Lowest price in bar |
| close | float | Closing price |
| volume | float | Total volume (base units) |
| fundingRate | float | Funding rate at that hour |

## Output Files

| File | Description |
|------|-------------|
| funding_basis_trades.csv | Individual trade log |
| results_phase2/multi_asset_trades.csv | Multi-asset trade log |
| optimization/best_params.json | Optimal parameters |
| walk_forward/window_results.json | Walk-forward windows |

## Notes

- Funding rates are charged every 8 hours (00:00, 08:00, 16:00 UTC)
- All timestamps are in UTC
- Missing funding rates are filled forward from last known value
