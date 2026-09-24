import pandas as pd
import numpy as np
import os
from datetime import datetime

# Load the winning trades file (MF=0.0003 from Phase 1)
trades_file = 'results_phase2/multi_asset_trades_mf0_0003.csv'
if not os.path.exists(trades_file):
    # Fallback to any available trades file
    import glob
    files = glob.glob('results_phase2/multi_asset_trades_mf*.csv')
    if not files:
        raise FileNotFoundError("No trades file found in results_phase2/")
    trades_file = files[0]
    print(f"Using fallback trades file: {trades_file}")

df = pd.read_csv(trades_file)
print(f"Loaded {len(df)} trades from {trades_file}")

# Ensure we have datetime columns
df['entry_time'] = pd.to_datetime(df['entry_time'])
df['exit_time'] = pd.to_datetime(df['exit_time'])

# We'll compute PnL by various groups

# 1. By asset
asset_pnl = df.groupby('asset')['net_pnl_pct'].sum().sort_values(ascending=False)
print("\nPnL by asset (top 10):")
print(asset_pnl.head(10))

# 2. By direction (we don't have direction explicitly, but we can infer from the trade? 
#    Actually, we don't have long/short in the trade record. We'll skip for now or note that the strategy is market neutral.
#    Instead, we can look at the exit_reason or the asset? Not available. We'll skip direction.

# 3. By exit_reason
if 'exit_reason' in df.columns:
    reason_pnl = df.groupby('exit_reason')['net_pnl_pct'].sum().sort_values(ascending=False)
    print("\nPnL by exit_reason:")
    print(reason_pnl)
else:
    print("\nNo 'exit_reason' column in trades file.")

# 4. By year (using exit_time)
df['exit_year'] = df['exit_time'].dt.year
year_pnl = df.groupby('exit_year')['net_pnl_pct'].sum()
print("\nPnL by year:")
print(year_pnl)

# 5. By quarter (using exit_time)
df['exit_quarter'] = df['exit_time'].dt.to_period('Q')
quarter_pnl = df.groupby('exit_quarter')['net_pnl_pct'].sum()
print("\nPnL by quarter:")
print(quarter_pnl)

# Concentration: top-1 asset share of total PnL
total_pnl = df['net_pnl_pct'].sum()
top_asset_pnl = asset_pnl.iloc[0] if len(asset_pnl) > 0 else 0
concentration = abs(top_asset_pnl) / abs(total_pnl) if total_pnl != 0 else 0
print(f"\nConcentration (top-1 asset share of total PnL): {concentration:.2%}")
if concentration > 0.5:
    print("WARNING: Top asset accounts for more than 50% of total PnL.")
else:
    print("Concentration is within acceptable bounds (<50%).")

# Save results to file
output_dir = 'results_phase2'
os.makedirs(output_dir, exist_ok=True)
output_file = os.path.join(output_dir, 'attribution.txt')
with open(output_file, 'w') as f:
    f.write("ATTRIBUTION ANALYSIS\n")
    f.write("=" * 50 + "\n\n")
    f.write(f"Trades file: {trades_file}\n")
    f.write(f"Number of trades: {len(df)}\n")
    f.write(f"Total PnL: {total_pnl:.4f}%\n\n")
    f.write("PNL BY ASSET (TOP 10)\n")
    f.write("-" * 30 + "\n")
    for asset, pnl in asset_pnl.head(10).items():
        f.write(f"{asset}: {pnl:.4f}%\n")
    f.write("\n")
    if 'exit_reason' in df.columns:
        f.write("PNL BY EXIT_REASON\n")
        f.write("-" * 30 + "\n")
        for reason, pnl in reason_pnl.items():
            f.write(f"{reason}: {pnl:.4f}%\n")
        f.write("\n")
    f.write("PNL BY YEAR\n")
    f.write("-" * 30 + "\n")
    for year, pnl in year_pnl.items():
        f.write(f"{year}: {pnl:.4f}%\n")
    f.write("\n")
    f.write("PNL BY QUARTER\n")
    f.write("-" * 30 + "\n")
    for quarter, pnl in quarter_pnl.items():
        f.write(f"{quarter}: {pnl:.4f}%\n")
    f.write("\n")
    f.write("CONCENTRATION ANALYSIS\n")
    f.write("-" * 30 + "\n")
    f.write(f"Top-1 asset: {asset_pnl.index[0] if len(asset_pnl) > 0 else 'N/A'}\n")
    f.write(f"Top-1 asset PnL: {top_asset_pnl:.4f}%\n")
    f.write(f"Total PnL: {total_pnl:.4f}%\n")
    f.write(f"Concentration (share of total PnL): {concentration:.2%}\n")
    if concentration > 0.5:
        f.write("WARNING: Top asset accounts for more than 50% of total PnL.\n")
    else:
        f.write("Concentration is within acceptable bounds (<50%).\n")

print(f"\nResults saved to {output_file}")