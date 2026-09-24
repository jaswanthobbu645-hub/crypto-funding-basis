import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
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

# Sort by exit time for equity curve
df = df.sort_values('exit_time').reset_index(drop=True)

# Calculate cumulative net PnL (in percent)
df['cum_pnl'] = df['net_pnl_pct'].cumsum()

# Calculate drawdown: (equity - running_max) / running_max
running_max = df['cum_pnl'].cummax()
drawdown = (df['cum_pnl'] - running_max) / running_max.abs().replace(0, np.nan)
df['drawdown'] = drawdown * 100  # as percentage

# For rolling Sharpe, we need to compute Sharpe over a window of trades.
# We'll use a window of 30 trades (approx) and annualize based on trade frequency.
# But the instruction says "rolling Sharpe (correct ann)".
# We'll compute the Sharpe ratio for a rolling window of trades, annualized using the trade frequency in that window.
# However, to keep it simple, we can compute the Sharpe ratio for expanding window or fixed window of trades.
# Let's do a rolling window of 30 trades and annualize based on the time span of those trades.
# But that is complex. Alternatively, we can compute the Sharpe ratio per month and then roll.
# Given time, we'll compute the Sharpe ratio for a rolling window of 30 trades, assuming the trades are evenly spaced in time?
# We'll approximate: use the same annualization factor as overall? Not correct.
# Let's do a simpler approach: compute the Sharpe ratio for expanding window of trades, annualized using the overall trade frequency.
# But the instruction likely expects rolling window of time (e.g., 30-day rolling Sharpe).
# We'll compute daily PnL? We don't have daily PnL, we have per trade.
# We can resample trades to daily frequency by assigning each trade's PnL to its exit day.
# Then compute daily returns, then rolling Sharpe on daily returns.
# Let's do that.

# Create a DataFrame indexed by exit date with daily PnL
df['exit_date'] = df['exit_time'].dt.date
daily_pnl = df.groupby('exit_date')['net_pnl_pct'].sum()
# Create a date index from min to max date
all_dates = pd.date_range(start=daily_pnl.index.min(), end=daily_pnl.index.max(), freq='D')
daily_pnl = daily_pnl.reindex(all_dates, fill_value=0)
# Daily returns in decimal
daily_ret = daily_pnl.values / 100.0

# Rolling Sharpe on daily returns with window of 30 days, annualized by sqrt(252) (trading days per year)
window = 30
rolling_mean = pd.Series(daily_ret).rolling(window).mean()
rolling_std = pd.Series(daily_ret).rolling(window).std()
rolling_sharpe = (rolling_mean / rolling_std) * np.sqrt(252)  # assuming 252 trading days per year
# Align with dates
rolling_sharpe_index = all_dates[window-1:]  # because rolling window starts at index window-1
rolling_sharpe = rolling_sharpe[window-1:]   # drop NaNs

# For the plot, we'll align the rolling Sharpe with the dates (starting from the window-th date)

# Now, cumulative by top-5 assets
top_assets = df.groupby('asset')['net_pnl_pct'].sum().nlargest(5).index.tolist()
top_df = df[df['asset'].isin(top_assets)]
# Cumulative PnL per top asset
top_cumulative = {}
for asset in top_assets:
    asset_trades = df[df['asset'] == asset].sort_values('exit_time')
    top_cumulative[asset] = asset_trades['net_pnl_pct'].cumsum().values

# Monthly PnL bar
df['exit_month'] = df['exit_time'].dt.to_period('M')
monthly_pnl = df.groupby('exit_month')['net_pnl_pct'].sum()
# Convert period to string for plotting
monthly_pnl.index = monthly_pnl.index.astype(str)

# Create the figure with 6 panels
fig, axes = plt.subplots(3, 2, figsize=(16, 12))
fig.suptitle('Crypto Funding Basis Strategy Tearsheet', fontsize=16)

# 1. Equity curve
ax = axes[0, 0]
ax.plot(df['exit_time'], df['cum_pnl'], linewidth=2)
ax.set_title('Equity Curve (Cumulative Net PnL)')
ax.set_ylabel('Net PnL (%)')
ax.set_xlabel('Date')
ax.grid(True, alpha=0.3)

# 2. Drawdown
ax = axes[0, 1]
ax.fill_between(df['exit_time'], df['drawdown'], 0, alpha=0.7, color='red')
ax.set_title('Drawdown')
ax.set_ylabel('Drawdown (%)')
ax.set_xlabel('Date')
ax.grid(True, alpha=0.3)

# 3. Trade histogram (PnL distribution)
ax = axes[1, 0]
ax.hist(df['net_pnl_pct'], bins=50, alpha=0.7, edgecolor='black')
ax.set_title('Trade PnL Distribution')
ax.set_xlabel('PnL per Trade (%)')
ax.set_ylabel('Frequency')
ax.axvline(df['net_pnl_pct'].mean(), color='red', linestyle='--', label=f'Mean: {df["net_pnl_pct"].mean():.2f}%')
ax.axvline(0, color='black', linestyle='-')
ax.legend()
ax.grid(True, alpha=0.3)

# 4. Rolling Sharpe (daily)
ax = axes[1, 1]
ax.plot(rolling_sharpe_index, rolling_sharpe, linewidth=2, color='green')
ax.set_title('Rolling Sharpe (30-day window, annualized)')
ax.set_ylabel('Sharpe Ratio')
ax.set_xlabel('Date')
ax.axhline(0, color='black', linestyle='-')
ax.axhline(1, color='red', linestyle='--', alpha=0.5, label='Sharpe = 1')
ax.axhline(2, color='red', linestyle='--', alpha=0.5, label='Sharpe = 2')
ax.legend()
ax.grid(True, alpha=0.3)

# 5. Cumulative by top-5 assets
ax = axes[2, 0]
for asset in top_assets:
    # We need to align the cumulative PnL with time. We'll plot against the trade index for simplicity.
    asset_trades = df[df['asset'] == asset].sort_values('exit_time')
    ax.plot(asset_trades['exit_time'], asset_trades['net_pnl_pct'].cumsum(), label=asset, linewidth=2)
ax.set_title('Cumulative PnL by Top 5 Assets')
ax.set_ylabel('Cumulative PnL (%)')
ax.set_xlabel('Date')
ax.legend()
ax.grid(True, alpha=0.3)

# 6. Monthly PnL bar
ax = axes[2, 1]
ax.bar(range(len(monthly_pnl)), monthly_pnl.values, alpha=0.7, edgecolor='black')
ax.set_title('Monthly PnL')
ax.set_ylabel('PnL (%)')
ax.set_xlabel('Month')
ax.set_xticks(range(len(monthly_pnl)))
ax.set_xticklabels(monthly_pnl.index, rotation=45, ha='right')
ax.axhline(0, color='black', linestyle='-')
ax.grid(True, alpha=0.3, axis='y')

plt.tight_layout()

# Save chart
charts_dir = 'charts'
os.makedirs(charts_dir, exist_ok=True)
chart_file = os.path.join(charts_dir, 'master_tearsheet.png')
plt.savefig(chart_file, dpi=150, bbox_inches='tight')
print(f"Tearsheet saved to {chart_file}")

# Also save some summary statistics to a text file for reference
output_dir = 'results_phase2'
os.makedirs(output_dir, exist_ok=True)
stats_file = os.path.join(output_dir, 'tearsheet_stats.txt')
with open(stats_file, 'w') as f:
    f.write("TEARSHEET SUMMARY STATISTICS\n")
    f.write("=" * 40 + "\n")
    f.write(f"Number of trades: {len(df)}\n")
    f.write(f"Date range: {df['exit_time'].min()} to {df['exit_time'].max()}\n")
    f.write(f"Total net PnL: {df['net_pnl_pct'].sum():.2f}%\n")
    f.write(f"Sharpe ratio (annualized): {df['net_pnl_pct'].mean() / df['net_pnl_pct'].std() * np.sqrt(len(df) / ((df['exit_time'].max() - df['exit_time'].min()).days / 30.44 * 12)):.2f}\n")
    f.write(f"Win rate: {(df['net_pnl_pct'] > 0).mean() * 100:.1f}%\n")
    f.write(f"Max drawdown: {df['drawdown'].min():.2f}%\n")
    f.write(f"Average win: {df[df['net_pnl_pct'] > 0]['net_pnl_pct'].mean():.2f}%\n")
    f.write(f"Average loss: {abs(df[df['net_pnl_pct'] < 0]['net_pnl_pct'].mean()):.2f}%\n")
    f.write(f"R:R: {df[df['net_pnl_pct'] > 0]['net_pnl_pct'].mean() / abs(df[df['net_pnl_pct'] < 0]['net_pnl_pct'].mean()):.2f}\n")

print(f"Tearsheet stats saved to {stats_file}")