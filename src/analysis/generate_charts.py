import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os
from datetime import datetime
import re
import subprocess
import sys

# Set style
plt.style.use('seaborn-v0_8-darkgrid')

# Load the winning trades file (MF=0.0004, baseline slippage)
trades_file = 'results_phase2/multi_asset_trades_mf0_0004_slip1.0x.csv'
if not os.path.exists(trades_file):
    # Fallback to any available trades file
    import glob
    files = glob.glob('results_phase2/multi_asset_trades_mf*_slip1.0x.csv')
    if not files:
        raise FileNotFoundError("No trades file found for slippage 1.0x in results_phase2/")
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
# Calculate drawdown: (cum - running_max) in percent (additive)
running_max = np.maximum.accumulate(df['cum_pnl'])
drawdown = df['cum_pnl'] - running_max  # in percent
df['drawdown'] = drawdown  # already in percent

# Calculate months from data for annualization
min_time = df['entry_time'].min()
max_time = df['exit_time'].max()
months = (max_time - min_time).days / 30.44
trades_per_month = len(df) / months if months > 0 else 0

# Calculate Sharpe ratio (annualized) with correct annualization
returns = df['net_pnl_pct'].values / 100.0  # decimal
mean_ret = np.mean(returns)
std_ret = np.std(returns, ddof=1)
tpy = len(returns) / months * 12 if months > 0 else 0
ann_factor = np.sqrt(tpy) if tpy > 0 else 0
sharpe = mean_ret / std_ret * ann_factor if std_ret != 0 else 0

# Calculate win rate
win_rate = (df['net_pnl_pct'] > 0).mean() * 100

# Calculate average win and loss for R:R
avg_win = df[df['net_pnl_pct'] > 0]['net_pnl_pct'].mean()
avg_loss = abs(df[df['net_pnl_pct'] < 0]['net_pnl_pct'].mean())
rr = avg_win / avg_loss if avg_loss != 0 else 0

# Load walk-forward results
wf_file = 'results_phase2/walk_forward_funding.txt'
wf_data = []
if os.path.exists(wf_file):
    with open(wf_file, 'r') as f:
        lines = f.readlines()
    # Find the table
    in_table = False
    for line in lines:
        if line.startswith('Window'):
            in_table = True
            continue
        if in_table and line.strip() == '':
            break
        if in_table and not line.startswith('-'):
            # Split by whitespace and filter out empty strings
            parts = [p for p in line.split() if p]
            # Expected format: Window Best_MF Train_Sharpe Test_Sharpe Test_PnL Test_WR Test_MDD Test_Trades
            # Example: "1      0.0005     -0.05        -1.06        -0.12      37.5    % -0.32       % 16"
            # After splitting: ['1', '0.0005', '-0.05', '-1.06', '-0.12', '37.5', '%', '-0.32', '%', '16']
            # We need to handle the '%' tokens: they are separate but we can ignore them and take the numbers.
            # We'll look for the pattern: a number, then possibly a '%' sign attached or separate.
            # Let's rebuild by scanning the parts and extracting numbers.
            nums = []
            for p in parts:
                # Remove any trailing '%' and try to convert to float
                p_clean = p.rstrip('%')
                try:
                    val = float(p_clean)
                    nums.append(val)
                except ValueError:
                    pass
            # Now we expect at least 8 numbers: window, best_mf, train_sharpe, test_sharpe, test_pnl, test_wr, test_dd, test_trades
            if len(nums) >= 8:
                try:
                    window = int(nums[0])
                    best_mf = nums[1]
                    train_sharpe = nums[2]
                    test_sharpe = nums[3]
                    test_pnl = nums[4]
                    test_wr = nums[5]
                    test_dd = nums[6]
                    test_trades = int(nums[7])
                    wf_data.append({
                        'window': window,
                        'best_mf': best_mf,
                        'train_sharpe': train_sharpe,
                        'test_sharpe': test_sharpe,
                        'test_pnl': test_pnl,
                        'test_wr': test_wr,
                        'test_dd': test_dd,
                        'test_trades': test_trades
                    })
                except (ValueError, IndexError) as e:
                    # If parsing fails, we skip this line but continue
                    pass

# Monte Carlo data: we will generate it ourselves if not available, using the same parameters as monte_carlo.py
mc_final_pnl = np.array([])
mc_max_dd = np.array([])
# Check if we have the numpy files from a previous run (maybe we saved them elsewhere)
mc_final_pnl_file = 'results_phase2/monte_carlo_final_pnl.npy'
mc_max_dd_file = 'results_phase2/monte_carlo_max_dd.npy'
if os.path.exists(mc_final_pnl_file) and os.path.exists(mc_max_dd_file):
    try:
        mc_final_pnl = np.load(mc_final_pnl_file)
        mc_max_dd = np.load(mc_max_dd_file)
        print(f"Loaded Monte Carlo data: {len(mc_final_pnl)} samples")
    except Exception as e:
        print(f"Error loading Monte Carlo data: {e}")
        mc_final_pnl = np.array([])
        mc_max_dd = np.array([])
else:
    print("Monte Carlo raw data files not found, will generate by bootstrapping.")

# If we don't have the monte carlo data, generate it by bootstrapping.
if len(mc_final_pnl) == 0 or len(mc_max_dd) == 0:
    print("Generating Monte Carlo data via bootstrapping...")
    n_sims = 1000
    n_trades = len(returns)
    # Bootstrap final PnL
    final_pnl_sim = np.zeros(n_sims)
    # Bootstrap max drawdown
    max_dd_sim = np.zeros(n_sims)
    for i in range(n_sims):
        # Sample with replacement
        idx = np.random.randint(0, n_trades, n_trades)
        boot_returns = returns[idx]
        # Cumulative returns
        cum = np.cumsum(boot_returns)
        # Max drawdown
        drawdown = cum - np.maximum.accumulate(cum)
        final_pnl_sim[i] = np.sum(boot_returns)
        max_dd_sim[i] = np.min(drawdown)
    mc_final_pnl = final_pnl_sim * 100.0  # convert to percent
    mc_max_dd = max_dd_sim * 100.0       # convert to percent
    print(f"Generated Monte Carlo data: {len(mc_final_pnl)} samples")
    # Optionally, we could save them, but not required.

# Define a function to add source annotation
def add_source_annotation(ax, fontsize=8):
    ax.text(0.5, -0.05, 'Data: Binance perps, 2024-10 to 2026-09', 
            transform=ax.transAxes, ha='center', fontsize=fontsize, 
            bbox=dict(boxstyle='round,pad=0.3', facecolor='lightgray', alpha=0.5))

# Define the charts directory
charts_dir = 'charts'
os.makedirs(charts_dir, exist_ok=True)

# We'll now generate each chart in a try-except block to report errors but continue.

# 1. Equity curve and drawdown
try:
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    # Top panel: equity curve
    ax1.plot(df['exit_time'], df['cum_pnl'], color='green', linewidth=2)
    ax1.fill_between(df['exit_time'], df['cum_pnl'], alpha=0.3, color='green')
    ax1.set_ylabel('Cumulative Net PnL (%)')
    ax1.set_title('Equity Curve', fontweight='bold')
    ax1.grid(True, alpha=0.3)
    # Mark peak equity and trough points
    peak_idx = df['cum_pnl'].argmax()
    trough_idx = df['drawdown'].argmin()
    ax1.scatter(df['exit_time'].iloc[peak_idx], df['cum_pnl'].iloc[peak_idx], 
                color='gold', s=100, zorder=5, label='Peak')
    ax1.scatter(df['exit_time'].iloc[trough_idx], df['cum_pnl'].iloc[trough_idx], 
                color='red', s=100, zorder=5, label='Trough')
    ax1.legend()

    # Bottom panel: drawdown
    ax2.fill_between(df['exit_time'], df['drawdown'], 0, alpha=0.7, color='red')
    ax2.set_ylabel('Drawdown (%)')
    ax2.set_xlabel('Date')
    ax2.set_title('Drawdown', fontweight='bold')
    ax2.grid(True, alpha=0.3)

    # Add source annotation
    add_source_annotation(ax2)
    plt.tight_layout()
    plt.savefig(os.path.join(charts_dir, '01_equity_curve.png'), dpi=300, bbox_inches='tight')
    plt.close()
    print("Chart 01_equity_curve.png generated successfully.")
except Exception as e:
    print(f"Error generating chart 01_equity_curve.png: {e}")

# 2. Rolling Sharpe (50-trade window)
try:
    window = 50
    if len(returns) >= window:
        rolling_mean = pd.Series(returns).rolling(window).mean()
        rolling_std = pd.Series(returns).rolling(window).std()
        rolling_sharpe = (rolling_mean / rolling_std) * np.sqrt(tpy) if tpy > 0 else 0
        # Align with the exit times (starting from the window-th trade)
        rolling_sharpe = rolling_sharpe[window-1:]
        roll_times = df['exit_time'].iloc[window-1:]
    else:
        rolling_sharpe = pd.Series([0]*len(df))
        roll_times = df['exit_time']

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(roll_times, rolling_sharpe, color='blue', linewidth=2)
    ax.axhline(y=0, color='black', linestyle='-', alpha=0.3)
    ax.axhline(y=1, color='green', linestyle='--', alpha=0.5, label='Sharpe = 1')
    ax.fill_between(roll_times, rolling_sharpe, 0, where=(rolling_sharpe < 0), color='red', alpha=0.3)
    ax.set_ylabel('Rolling Sharpe (50-trade window)')
    ax.set_xlabel('Date')
    ax.set_title('Rolling Sharpe Ratio', fontweight='bold')
    ax.legend()
    ax.grid(True, alpha=0.3)
    add_source_annotation(ax)
    plt.tight_layout()
    plt.savefig(os.path.join(charts_dir, '02_rolling_sharpe.png'), dpi=300, bbox_inches='tight')
    plt.close()
    print("Chart 02_rolling_sharpe.png generated successfully.")
except Exception as e:
    print(f"Error generating chart 02_rolling_sharpe.png: {e}")

# 3. Trade distribution
try:
    fig, ax = plt.subplots(figsize=(10, 6))
    n, bins, patches = ax.hist(df['net_pnl_pct'], bins=50, alpha=0.7, edgecolor='black', color='skyblue')
    ax.axvline(x=0, color='red', linestyle='--', linewidth=2, label='Break-even')
    ax.axvline(x=df['net_pnl_pct'].mean(), color='green', linestyle='--', linewidth=2, label='Mean')
    # Text box with stats
    textstr = f'N = {len(df)}\nMean = {df["net_pnl_pct"].mean():.2f}%\nStd = {df["net_pnl_pct"].std():.2f}%\nSkew = {df["net_pnl_pct"].skew():.2f}\nKurtosis = {df["net_pnl_pct"].kurtosis():.2f}'
    props = dict(boxstyle='round', facecolor='wheat', alpha=0.5)
    ax.text(0.05, 0.95, textstr, transform=ax.transAxes, fontsize=10,
            verticalalignment='top', bbox=props)
    ax.set_xlabel('PnL per Trade (%)')
    ax.set_ylabel('Frequency')
    ax.set_title('Trade PnL Distribution', fontweight='bold')
    ax.legend()
    ax.grid(True, alpha=0.3)
    add_source_annotation(ax)
    plt.tight_layout()
    plt.savefig(os.path.join(charts_dir, '03_trade_distribution.png'), dpi=300, bbox_inches='tight')
    plt.close()
    print("Chart 03_trade_distribution.png generated successfully.")
except Exception as e:
    print(f"Error generating chart 03_trade_distribution.png: {e}")

# 4. Monthly returns
try:
    # We'll resample to monthly frequency by summing the PnL of trades that exited in that month
    df['exit_month'] = df['exit_time'].dt.to_period('M')
    monthly_pnl = df.groupby('exit_month')['net_pnl_pct'].sum()
    # Convert period to timestamp for plotting
    monthly_pnl.index = monthly_pnl.index.to_timestamp()
    fig, ax = plt.subplots(figsize=(12, 6))
    colors = ['green' if x >= 0 else 'red' for x in monthly_pnl.values]
    ax.bar(monthly_pnl.index, monthly_pnl.values, color=colors, alpha=0.7, edgecolor='black')
    ax.axhline(y=0, color='black', linestyle='-', alpha=0.3)
    ax.set_ylabel('Monthly PnL (%)')
    ax.set_xlabel('Month')
    ax.set_title('Monthly Returns', fontweight='bold')
    # Format x-axis as YYYY-MM
    ax.xaxis.set_major_formatter(plt.matplotlib.dates.DateFormatter('%Y-%m'))
    plt.xticks(rotation=45)
    ax.grid(True, alpha=0.3, axis='y')
    add_source_annotation(ax)
    plt.tight_layout()
    plt.savefig(os.path.join(charts_dir, '04_monthly_returns.png'), dpi=300, bbox_inches='tight')
    plt.close()
    print("Chart 04_monthly_returns.png generated successfully.")
except Exception as e:
    print(f"Error generating chart 04_monthly_returns.png: {e}")

# 5. PnL by asset (top 15)
try:
    asset_pnl = df.groupby('asset')['net_pnl_pct'].sum().sort_values(ascending=False)
    top_assets = asset_pnl.head(15)
    total_pnl = asset_pnl.sum()
    top_1_pct = abs(top_assets.iloc[0]) / abs(total_pnl) * 100 if total_pnl != 0 else 0
    fig, ax = plt.subplots(figsize=(10, 8))
    # Horizontal bar chart
    y_pos = np.arange(len(top_assets))
    ax.barh(y_pos, top_assets.values, color=['green' if x >= 0 else 'red' for x in top_assets.values])
    ax.set_yticks(y_pos)
    ax.set_yticklabels(top_assets.index)
    ax.invert_yaxis()  # To have the highest at the top
    ax.set_xlabel('PnL Contribution (%)')
    ax.set_title(f'Top 15 Assets by PnL Contribution\nTop-1 Asset Concentration: {top_1_pct:.1f}%', fontweight='bold')
    ax.grid(True, alpha=0.3, axis='x')
    add_source_annotation(ax)
    plt.tight_layout()
    plt.savefig(os.path.join(charts_dir, '05_pnl_by_asset.png'), dpi=300, bbox_inches='tight')
    plt.close()
    print("Chart 05_pnl_by_asset.png generated successfully.")
except Exception as e:
    print(f"Error generating chart 05_pnl_by_asset.png: {e}")

# 6. Walk-forward test Sharpe per window
try:
    if wf_data:
        windows = [d['window'] for d in wf_data]
        test_sharpes = [d['test_sharpe'] for d in wf_data]
        positive_count = sum(1 for s in test_sharpes if s > 0)
        fig, ax = plt.subplots(figsize=(12, 6))
        colors = ['green' if s >= 0 else 'red' for s in test_sharpes]
        ax.bar(windows, test_sharpes, color=colors, alpha=0.7, edgecolor='black')
        ax.axhline(y=0, color='black', linestyle='-', alpha=0.3)
        ax.set_ylabel('Test Sharpe Ratio')
        ax.set_xlabel('Walk-Forward Window')
        ax.set_title(f'Walk-Forward Test Sharpe per Window ({positive_count} of {len(wf_data)} windows positive)', fontweight='bold')
        ax.set_xticks(windows)
        ax.grid(True, alpha=0.3, axis='y')
        add_source_annotation(ax)
        plt.tight_layout()
        plt.savefig(os.path.join(charts_dir, '06_walk_forward.png'), dpi=300, bbox_inches='tight')
        plt.close()
        print("Chart 06_walk_forward.png generated successfully.")
    else:
        print("Walk-forward data not found, skipping chart 06_walk_forward.png")
except Exception as e:
    print(f"Error generating chart 06_walk_forward.png: {e}")

# 7. Monte Carlo
try:
    if len(mc_final_pnl) > 0 and len(mc_max_dd) > 0:
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
        # Final PnL distribution
        ax1.hist(mc_final_pnl, bins=50, alpha=0.7, edgecolor='black', color='skyblue')
        ax1.axvline(x=np.mean(mc_final_pnl), color='green', linestyle='--', linewidth=2, label='Mean')
        ax1.axvline(x=df['net_pnl_pct'].sum(), color='red', linestyle='-', linewidth=2, label='Actual')
        ax1.set_xlabel('Final PnL (%)')
        ax1.set_ylabel('Frequency')
        ax1.set_title('Final PnL Distribution (Monte Carlo)', fontweight='bold')
        # Text box with percentiles
        p5, p25, p50, p75, p95 = np.percentile(mc_final_pnl, [5, 25, 50, 75, 95])
        textstr = f'5th: {p5:.2f}%\n25th: {p25:.2f}%\n50th: {p50:.2f}%\n75th: {p75:.2f}%\n95th: {p95:.2f}%\nActual: {df["net_pnl_pct"].sum():.2f}%'
        props = dict(boxstyle='round', facecolor='wheat', alpha=0.5)
        ax1.text(0.05, 0.95, textstr, transform=ax1.transAxes, fontsize=10,
                 verticalalignment='top', bbox=props)
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # Max DD distribution
        ax2.hist(mc_max_dd, bins=50, alpha=0.7, edgecolor='black', color='salmon')
        ax2.axvline(x=np.mean(mc_max_dd), color='green', linestyle='--', linewidth=2, label='Mean')
        ax2.axvline(x=df['drawdown'].min(), color='red', linestyle='-', linewidth=2, label='Actual')
        ax2.set_xlabel('Max Drawdown (%)')
        ax2.set_ylabel('Frequency')
        ax2.set_title('Max Drawdown Distribution (Monte Carlo)', fontweight='bold')
        # Text box with percentiles
        p5, p25, p50, p75, p95 = np.percentile(mc_max_dd, [5, 25, 50, 75, 95])
        textstr = f'5th: {p5:.2f}%\n25th: {p25:.2f}%\n50th: {p50:.2f}%\n75th: {p75:.2f}%\n95th: {p95:.2f}%\nActual: {df["drawdown"].min():.2f}%'
        props = dict(boxstyle='round', facecolor='wheat', alpha=0.5)
        ax2.text(0.05, 0.95, textstr, transform=ax2.transAxes, fontsize=10,
                 verticalalignment='top', bbox=props)
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        
        add_source_annotation(ax1)
        add_source_annotation(ax2)
        plt.tight_layout()
        plt.savefig(os.path.join(charts_dir, '07_monte_carlo.png'), dpi=300, bbox_inches='tight')
        plt.close()
        print("Chart 07_monte_carlo.png generated successfully.")
    else:
        print("Monte Carlo data not available, skipping chart 07_monte_carlo.png")
except Exception as e:
    print(f"Error generating chart 07_monte_carlo.png: {e}")

# 8. Slippage sensitivity (for MF=0.0004 only)
try:
    # We have the trades files for different slippage multipliers for MF=0.0004
    slippage_levels = [0.5, 1.0, 1.5]
    slippage_pnl = []
    for mult in slippage_levels:
        file = f'results_phase2/multi_asset_trades_mf0_0004_slip{mult}x.csv'
        if os.path.exists(file):
            df_slip = pd.read_csv(file)
            total_pnl = df_slip['net_pnl_pct'].sum()
            slippage_pnl.append(total_pnl)
        else:
            slippage_pnl.append(0)
            print(f"Warning: {file} not found")

    fig, ax = plt.subplots(figsize=(10, 6))
    bars = ax.bar([f'{x}x' for x in slippage_levels], slippage_pnl, 
                  color=['green' if x >= 0 else 'red' for x in slippage_pnl],
                  alpha=0.7, edgecolor='black')
    # Annotate values on bars
    for bar, pnl in zip(bars, slippage_pnl):
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height + (0.01 if height >=0 else -0.03),
                f'{pnl:.2f}%', ha='center', va='bottom' if height >=0 else 'top', fontweight='bold')
    ax.set_ylabel('Net PnL (%)')
    ax.set_xlabel('Slippage Multiplier')
    ax.set_title('Slippage Sensitivity (MF=0.0004)', fontweight='bold')
    ax.axhline(y=0, color='black', linestyle='-', alpha=0.3)
    ax.grid(True, alpha=0.3, axis='y')
    add_source_annotation(ax)
    plt.tight_layout()
    plt.savefig(os.path.join(charts_dir, '08_slippage_sensitivity.png'), dpi=300, bbox_inches='tight')
    plt.close()
    print("Chart 08_slippage_sensitivity.png generated successfully.")
except Exception as e:
    print(f"Error generating chart 08_slippage_sensitivity.png: {e}")

# 9. Signal example (single asset, e.g., INJ)
try:
    # We need to load the signal data for an asset. We'll use INJ as an example.
    data_dir = 'data/expanded/'
    asset = 'INJ'  # example asset
    # The data files are named like 'AAVE_USDT_USDT.parquet'
    asset_file = os.path.join(data_dir, f'{asset}_USDT_USDT.parquet')
    if not os.path.exists(asset_file):
        raise FileNotFoundError(f"Data file for {asset} not found at {asset_file}")
    
    # Load the data
    df_asset = pd.read_parquet(asset_file)
    # We expect columns: timestamp, open, high, low, close, volume, fundingRate
    # Ensure we have a datetime index
    if 'timestamp' in df_asset.columns:
        df_asset['timestamp'] = pd.to_datetime(df_asset['timestamp'])
        df_asset = df_asset.set_index('timestamp')
    # If the index is not a datetime, we try to convert it.
    if not isinstance(df_asset.index, pd.DatetimeIndex):
        # Try to convert the index to datetime
        try:
            df_asset.index = pd.to_datetime(df_asset.index)
        except:
            # If we can't, we look for a column that might be the date
            # We'll skip for now.
            raise ValueError("Could not determine datetime index for asset data.")
    
    # We'll compute the Z-score: (funding_rate - mean) / std over a rolling window of 720 hours (30 days)
    window = 720
    if 'fundingRate' in df_asset.columns:
        funding_rate = df_asset['fundingRate']
        mean_funding = funding_rate.rolling(window=window, min_periods=1).mean()
        std_funding = funding_rate.rolling(window=window, min_periods=1).std()
        z_score = (funding_rate - mean_funding) / std_funding
        # Replace infinite and NaN due to zero std
        z_score = z_score.replace([np.inf, -np.inf], np.nan).fillna(0)
        
        # Now, we need to mark the entries and exits from the trades file for this asset.
        # We'll filter the trades for this asset.
        df_asset_trades = df[df['asset'] == asset].copy()
        if len(df_asset_trades) > 0:
            # We'll pick a 2-3 month window where trades occurred.
            # Let's take the first trade and last trade for this asset and expand a bit.
            start_trade = df_asset_trades['entry_time'].min()
            end_trade = df_asset_trades['exit_time'].max()
            # Extend by 1 month on each side to have context.
            start_plot = start_trade - pd.DateOffset(months=1)
            end_plot = end_trade + pd.DateOffset(months=1)
            # Slice the z_score and funding_rate for this period.
            z_score_plot = z_score.loc[start_plot:end_plot]
            funding_rate_plot = funding_rate.loc[start_plot:end_plot]
            
            fig, ax = plt.subplots(figsize=(12, 6))
            ax.plot(z_score_plot.index, z_score_plot.values, color='blue', linewidth=2, label='Funding Rate Z-Score')
            ax.axhline(y=1.2, color='green', linestyle='--', alpha=0.7, label='Entry Threshold (+1.2)')
            ax.axhline(y=-1.2, color='red', linestyle='--', alpha=0.7, label='Exit Threshold (-1.2)')
            # Mark entries (green up triangles) and exits (red down triangles)
            # We need to align the trade times with the z_score index.
            entries = df_asset_trades['entry_time']
            exits = df_asset_trades['exit_time']
            # Only consider those within the plot window
            entries_plot = entries[(entries >= start_plot) & (entries <= end_plot)]
            exits_plot = exits[(exits >= start_plot) & (exits <= end_plot)]
            # Get the z_score at those times (we need to align to the index, we can use the closest)
            entry_zs = []
            for t in entries_plot:
                if t in z_score_plot.index:
                    entry_zs.append(z_score_plot.loc[t])
                else:
                    # Find the closest index
                    idx = z_score_plot.index.get_indexer([t], method='nearest')[0]
                    entry_zs.append(z_score_plot.iloc[idx])
            exit_zs = []
            for t in exits_plot:
                if t in z_score_plot.index:
                    exit_zs.append(z_score_plot.loc[t])
                else:
                    idx = z_score_plot.index.get_indexer([t], method='nearest')[0]
                    exit_zs.append(z_score_plot.iloc[idx])
            
            ax.scatter(entries_plot, entry_zs, color='green', marker='^', s=100, zorder=5, label='Entry')
            ax.scatter(exits_plot, exit_zs, color='red', marker='v', s=100, zorder=5, label='Exit')
            
            ax.set_ylabel('Z-Score')
            ax.set_xlabel('Date')
            ax.set_title(f'Signal Example: {asset} Funding Rate Z-Score', fontweight='bold')
            ax.legend()
            ax.grid(True, alpha=0.3)
            add_source_annotation(ax)
            plt.tight_layout()
            plt.savefig(os.path.join(charts_dir, '09_signal_example.png'), dpi=300, bbox_inches='tight')
            plt.close()
            print("Chart 09_signal_example.png generated successfully.")
        else:
            print(f"No trades found for {asset} in the winning config, skipping chart 09_signal_example.png")
    else:
        print(f"Funding rate column not found in data for {asset}, skipping chart 09_signal_example.png")
except Exception as e:
    print(f"Error generating chart 09_signal_example.png: {e}")

# 10. Master tearsheet (3x2 grid)
try:
    # We'll create a 3x2 grid combining:
    #   - equity curve (top left)
    #   - drawdown (top middle)
    #   - rolling Sharpe (top right)
    #   - trade histogram (middle left)
    #   - PnL by asset (middle middle)
    #   - monthly returns (middle right)

    fig = plt.figure(figsize=(16, 12))
    # Define the grid
    # Row 0: equity curve, drawdown
    # Row 1: rolling Sharpe, trade histogram
    # Row 2: PnL by asset, monthly returns

    ax1 = plt.subplot(3, 2, 1)  # equity curve
    ax2 = plt.subplot(3, 2, 2)  # drawdown
    ax3 = plt.subplot(3, 2, 3)  # rolling Sharpe
    ax4 = plt.subplot(3, 2, 4)  # trade histogram
    ax5 = plt.subplot(3, 2, 5)  # PnL by asset
    ax6 = plt.subplot(3, 2, 6)  # monthly returns

    # Equity curve
    ax1.plot(df['exit_time'], df['cum_pnl'], color='green', linewidth=2)
    ax1.fill_between(df['exit_time'], df['cum_pnl'], alpha=0.3, color='green')
    ax1.set_ylabel('Cumulative Net PnL (%)')
    ax1.set_title('Equity Curve', fontweight='bold')
    ax1.grid(True, alpha=0.3)
    # Mark peak and trough
    peak_idx = df['cum_pnl'].argmax()
    trough_idx = df['drawdown'].argmin()
    ax1.scatter(df['exit_time'].iloc[peak_idx], df['cum_pnl'].iloc[peak_idx], 
                color='gold', s=50, zorder=5)
    ax1.scatter(df['exit_time'].iloc[trough_idx], df['cum_pnl'].iloc[trough_idx], 
                color='red', s=50, zorder=5)

    # Drawdown
    ax2.fill_between(df['exit_time'], df['drawdown'], 0, alpha=0.7, color='red')
    ax2.set_ylabel('Drawdown (%)')
    ax2.set_title('Drawdown', fontweight='bold')
    ax2.grid(True, alpha=0.3)

    # Rolling Sharpe (we'll use the same as in chart 2, but we'll recompute for consistency)
    window = 50
    if len(returns) >= window:
        rolling_mean = pd.Series(returns).rolling(window).mean()
        rolling_std = pd.Series(returns).rolling(window).std()
        rolling_sharpe = (rolling_mean / rolling_std) * np.sqrt(tpy) if tpy > 0 else 0
        rolling_sharpe = rolling_sharpe[window-1:]
        roll_times = df['exit_time'].iloc[window-1:]
    else:
        rolling_sharpe = pd.Series([0]*len(df))
        roll_times = df['exit_time']
    ax3.plot(roll_times, rolling_sharpe, color='blue', linewidth=2)
    ax3.axhline(y=0, color='black', linestyle='-', alpha=0.3)
    ax3.axhline(y=1, color='green', linestyle='--', alpha=0.5)
    ax3.fill_between(roll_times, rolling_sharpe, 0, where=(rolling_sharpe < 0), color='red', alpha=0.3)
    ax3.set_ylabel('Rolling Sharpe (50-trade)')
    ax3.set_title('Rolling Sharpe', fontweight='bold')
    ax3.grid(True, alpha=0.3)

    # Trade histogram
    n, bins, patches = ax4.hist(df['net_pnl_pct'], bins=50, alpha=0.7, edgecolor='black', color='skyblue')
    ax4.axvline(x=0, color='red', linestyle='--', linewidth=2)
    ax4.axvline(x=df['net_pnl_pct'].mean(), color='green', linestyle='--', linewidth=2)
    ax4.set_xlabel('PnL per Trade (%)')
    ax4.set_ylabel('Frequency')
    ax4.set_title('Trade PnL Distribution', fontweight='bold')
    ax4.grid(True, alpha=0.3)

    # PnL by asset (top 10 for space)
    asset_pnl = df.groupby('asset')['net_pnl_pct'].sum().sort_values(ascending=False)
    top_assets = asset_pnl.head(10)
    y_pos = np.arange(len(top_assets))
    ax5.barh(y_pos, top_assets.values, color=['green' if x >= 0 else 'red' for x in top_assets.values])
    ax5.set_yticks(y_pos)
    ax5.set_yticklabels(top_assets.index)
    ax5.invert_yaxis()
    ax5.set_xlabel('PnL Contribution (%)')
    ax5.set_title('Top 10 Assets by PnL', fontweight='bold')
    ax5.grid(True, alpha=0.3, axis='x')

    # Monthly returns
    df['exit_month'] = df['exit_time'].dt.to_period('M')
    monthly_pnl = df.groupby('exit_month')['net_pnl_pct'].sum()
    monthly_pnl.index = monthly_pnl.index.to_timestamp()
    colors = ['green' if x >= 0 else 'red' for x in monthly_pnl.values]
    ax6.bar(monthly_pnl.index, monthly_pnl.values, color=colors, alpha=0.7, edgecolor='black')
    ax6.axhline(y=0, color='black', linestyle='-', alpha=0.3)
    ax6.set_ylabel('Monthly PnL (%)')
    ax6.set_xlabel('Month')
    ax6.set_title('Monthly Returns', fontweight='bold')
    ax6.xaxis.set_major_formatter(plt.matplotlib.dates.DateFormatter('%Y-%m'))
    plt.setp(ax6.xaxis.get_majorticklabels(), rotation=45, ha='right')
    ax6.grid(True, alpha=0.3, axis='y')

    # Overall title
    fig.suptitle('Funding Basis Harvest — Strategy Tearsheet', fontsize=16, fontweight='bold')
    # Subtitle with key metrics
    subtitle = f'MF=0.0004 | Trades/Month: {trades_per_month:.2f} | Net PnL: {df["net_pnl_pct"].sum():.2f}% | Sharpe: {sharpe:.2f} | Max DD: {df["drawdown"].min():.2f}% | R:R: {rr:.2f}'
    fig.text(0.5, 0.01, subtitle, ha='center', fontsize=10, style='italic')

    # Source annotation
    fig.text(0.5, 0.005, 'Data: Binance perps, 2024-10 to 2026-09', ha='center', fontsize=8, 
             bbox=dict(boxstyle='round,pad=0.3', facecolor='lightgray', alpha=0.5))

    plt.tight_layout(rect=[0, 0.03, 1, 0.95])  # Adjust for the subtitle and source
    plt.savefig(os.path.join(charts_dir, '10_master_tearsheet.png'), dpi=300, bbox_inches='tight')
    plt.close()
    print("Chart 10_master_tearsheet.png generated successfully.")
except Exception as e:
    print(f"Error generating chart 10_master_tearsheet.png: {e}")

print("Chart generation process finished.")