import pandas as pd
import numpy as np
import os
import sys
from datetime import timedelta

# Add the strategy directory to the path so we can import from multi_asset
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../strategy'))
from multi_asset import backtest_asset_with_threshold, load_all_assets

# CHOSEN CONFIG: MF=0.0003 (from frequency_report_v2.txt, trades/month=42.54 >=30, highest Sharpe among those)
MF_CANDIDATES = [0.0003]  # ONLY THE CHOSEN CONFIG
TRAIN_MONTHS = 6
TEST_MONTHS = 2
# We'll roll the window by 1 month each step

def calculate_sharpe(trades_df):
    """Calculate Sharpe ratio from trades dataframe with correct annualization."""
    if trades_df.empty or len(trades_df) < 2:
        return 0.0
    # Use actual trade timestamps to compute months
    min_time = trades_df['entry_time'].min()
    max_time = trades_df['exit_time'].max()
    if pd.isna(min_time) or pd.isna(max_time):
        return 0.0
    months = (max_time - min_time).days / 30.44
    if months <= 0:
        return 0.0
    tpy = len(trades_df) / months * 12
    ann_factor = np.sqrt(tpy)
    mean_ret = trades_df['net_pnl_pct'].mean()
    std_ret = trades_df['net_pnl_pct'].std()
    if std_ret == 0:
        return 0.0
    return (mean_ret / std_ret) * ann_factor

def calculate_max_dd(trades_df):
    """Calculate max drawdown from equity curve (cumulative net PnL)."""
    if trades_df.empty:
        return 0.0
    df_sorted = trades_df.sort_values('exit_time')
    cum = df_sorted['net_pnl_pct'].cumsum()  # in percent
    peak = np.maximum.accumulate(cum)
    dd = cum - peak  # in percent
    return dd.min()  # already in percent (negative or zero)

def main():
    print("Loading assets...")
    assets = load_all_assets()
    print(f"Loaded {len(assets)} assets\n")
    
    # Determine the overall date range from the data
    all_timestamps = []
    for name, df in assets.items():
        all_timestamps.extend(df['timestamp'].tolist())
    if not all_timestamps:
        print("No data found!")
        return
    min_time = pd.Timestamp(min(all_timestamps))
    max_time = pd.Timestamp(max(all_timestamps))
    print(f"Data range: {min_time} to {max_time}\n")
    
    # We'll create rolling windows: train for TRAIN_MONTHS, test for TEST_MONTHS, then roll by 1 month
    window_start = min_time
    results = []
    window_count = 0
    
    while True:
        train_end = window_start + pd.DateOffset(months=TRAIN_MONTHS)
        test_end = train_end + pd.DateOffset(months=TEST_MONTHS)
        
        if test_end > max_time:
            break  # Not enough data for another full window
        
        window_count += 1
        print(f"Window {window_count}: Train {window_start.date()} to {train_end.date()}, Test {train_end.date()} to {test_end.date()}")
        
        # --- TRAINING: pick best MF by Sharpe on training data (now only one MF) ---
        best_mf = None
        best_sharpe = -np.inf
        best_train_trades = None
        
        for mf in MF_CANDIDATES:
            train_trades = []
            for asset_name, df in assets.items():
                # Filter data to training period
                mask = (df['timestamp'] >= window_start) & (df['timestamp'] < train_end)
                df_train = df.loc[mask].copy()
                if df_train.empty:
                    continue
                trades = backtest_asset_with_threshold(df_train, asset_name, mf)
                train_trades.extend(trades)
            
            if not train_trades:
                sharpe = 0.0
            else:
                train_df = pd.DataFrame(train_trades)
                sharpe = calculate_sharpe(train_df)
            
            if sharpe > best_sharpe:
                best_sharpe = sharpe
                best_mf = mf
                best_train_trades = train_trades
        
        if best_mf is None:
            print("  No valid MF found in training, skipping window.")
            window_start += pd.DateOffset(months=1)  # Roll by 1 month
            continue
        
        print(f"  Best MF from training: {best_mf} (Sharpe={best_sharpe:.2f})")
        
        # --- TESTING: apply best MF on test data ---
        test_trades = []
        for asset_name, df in assets.items():
            # Filter data to test period
            mask = (df['timestamp'] >= train_end) & (df['timestamp'] < test_end)
            df_test = df.loc[mask].copy()
            if df_test.empty:
                continue
            trades = backtest_asset_with_threshold(df_test, asset_name, best_mf)
            test_trades.extend(trades)
        
        if test_trades:
            test_df = pd.DataFrame(test_trades)
            test_sharpe = calculate_sharpe(test_df)
            test_pnl = test_df['net_pnl_pct'].sum()
            test_wr = (test_df['net_pnl_pct'] > 0).mean() * 100
            test_max_dd = calculate_max_dd(test_df)
            test_trades_count = len(test_df)
        else:
            test_sharpe = 0.0
            test_pnl = 0.0
            test_wr = 0.0
            test_max_dd = 0.0
            test_trades_count = 0
        
        results.append({
            'window': window_count,
            'train_start': window_start,
            'train_end': train_end,
            'test_start': train_end,
            'test_end': test_end,
            'best_mf': best_mf,
            'train_sharpe': best_sharpe,
            'test_sharpe': test_sharpe,
            'test_pnl': test_pnl,
            'test_wr': test_wr,
            'test_max_dd': test_max_dd,
            'test_trades': test_trades_count
        })
        
        # Roll the window by 1 month
        window_start += pd.DateOffset(months=1)
    
    print(f"\nCompleted {window_count} windows.\n")
    
    # Print summary table
    print("=" * 100)
    print("WALK-FORWARD RESULTS (6-month train, 2-month test, rolling monthly)")
    print("=" * 100)
    print(f"{'Window':<6} {'Best MF':<10} {'Train Sharpe':<12} {'Test Sharpe':<12} {'Test PnL':<10} {'Test WR':<8} {'Test MaxDD':<12} {'Test Trades':<12}")
    print("-" * 100)
    for r in results:
        print(f"{r['window']:<6} {r['best_mf']:<10.4f} {r['train_sharpe']:<12.2f} {r['test_sharpe']:<12.2f} "
              f"{r['test_pnl']:<10.2f} {r['test_wr']:<8.1f}% {r['test_max_dd']:<12.2f}% {r['test_trades']:<12}")
    
    # Aggregate statistics
    if results:
        test_sharpes = [r['test_sharpe'] for r in results if r['test_sharpe'] != 0]
        test_pnls = [r['test_pnl'] for r in results]
        test_wrs = [r['test_wr'] for r in results]
        test_max_dds = [r['test_max_dd'] for r in results]
        positive_windows = sum(1 for r in results if r['test_pnl'] > 0)
        
        print("\n" + "=" * 50)
        print("AGGREGATE METRICS")
        print("=" * 50)
        print(f"Windows with positive PnL: {positive_windows}/{len(results)} ({positive_windows/len(results)*100:.1f}%)")
        if test_sharpes:
            print(f"Median test Sharpe: {np.median(test_sharpes):.2f}")
            print(f"Average test Sharpe: {np.mean(test_sharpes):.2f}")
        print(f"Median test PnL: {np.median(test_pnls):.2f}%")
        print(f"Average test PnL: {np.mean(test_pnls):.2f}%")
        print(f"Median test Win Rate: {np.median(test_wrs):.1f}%")
        print(f"Median test Max DD: {np.median(test_max_dds):.2f}%")
    
    # Save results to file
    output_dir = 'results_phase2'
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, 'walk_forward_funding.txt')
    with open(output_file, 'w') as f:
        f.write("WALK-FORWARD RESULTS ON FUNDING STRATEGY\n")
        f.write("=" * 80 + "\n\n")
        f.write(f"Data range: {min_time} to {max_time}\n")
        f.write(f"Training period: {TRAIN_MONTHS} months\n")
        f.write(f"Testing period: {TEST_MONTHS} months\n")
        f.write(f"Roll step: 1 month\n")
        f.write(f"MF candidates: {MF_CANDIDATES}\n\n")
        f.write("Per-window results:\n")
        f.write("-" * 80 + "\n")
        f.write(f"{'Window':<6} {'Best MF':<10} {'Train Sharpe':<12} {'Test Sharpe':<12} {'Test PnL':<10} {'Test WR':<8} {'Test MaxDD':<12} {'Test Trades':<12}\n")
        f.write("-" * 80 + "\n")
        for r in results:
            f.write(f"{r['window']:<6} {r['best_mf']:<10.4f} {r['train_sharpe']:<12.2f} {r['test_sharpe']:<12.2f} "
                    f"{r['test_pnl']:<10.2f} {r['test_wr']:<8.1f}% {r['test_max_dd']:<12.2f}% {r['test_trades']:<12}\n")
        f.write("\n")
        f.write("Aggregate metrics:\n")
        f.write("-" * 80 + "\n")
        f.write(f"Windows with positive PnL: {positive_windows}/{len(results)} ({positive_windows/len(results)*100:.1f}%)\n")
        if test_sharpes:
            f.write(f"Median test Sharpe: {np.median(test_sharpes):.2f}\n")
            f.write(f"Average test Sharpe: {np.mean(test_sharpes):.2f}\n")
        f.write(f"Median test PnL: {np.median(test_pnls):.2f}%\n")
        f.write(f"Average test PnL: {np.mean(test_pnls):.2f}%\n")
        f.write(f"Median test Win Rate: {np.median(test_wrs):.1f}%\n")
        f.write(f"Median test Max DD: {np.median(test_max_dds):.2f}%\n")
    
    print(f"\nResults saved to {output_file}")

if __name__ == '__main__':
    main()