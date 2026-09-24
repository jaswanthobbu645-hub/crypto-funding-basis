import os
import pandas as pd
import numpy as np

# Directory where the threshold files are located
RESULTS_DIR = r'C:\Users\Avinash\crypto_backtest\results_phase2'

# List of the existing threshold files (with the bug in the filename)
THRESHOLD_FILES = [
    'multi_asset_trades_mf0_0001_csv',
    'multi_asset_trades_mf0_0003_csv',
    'multi_asset_trades_mf0_0005_csv',
    'multi_asset_trades_mf0_0008_csv',
    'multi_asset_trades_mf0_0010_csv'
]

def compute_max_drawdown(equity_curve):
    """Compute the maximum drawdown of an equity curve."""
    # equity_curve is a series of cumulative returns (in percent)
    # We'll compute the running maximum and then the drawdown
    running_max = np.maximum.accumulate(equity_curve)
    drawdown = (equity_curve - running_max) / (running_max + 1e-9)  # avoid division by zero
    max_drawdown = np.min(drawdown) * 100  # as percentage
    return max_drawdown

def analyze_threshold_file(filepath):
    """Load a threshold file and compute the required metrics."""
    if not os.path.exists(filepath):
        return None
    df = pd.read_csv(filepath)
    if df.empty:
        return None

    # Convert entry_time and exit_time to datetime if they exist
    if 'entry_time' in df.columns:
        df['entry_time'] = pd.to_datetime(df['entry_time'])
    if 'exit_time' in df.columns:
        df['exit_time'] = pd.to_datetime(df['exit_time'])

    # Number of trades
    n_trades = len(df)

    # Date range: use entry_time if available, else we cannot compute
    if 'entry_time' in df.columns and not df['entry_time'].isnull().all():
        start_date = df['entry_time'].min()
        end_date = df['entry_time'].max()
        # If we have exit_time, we might use the max of exit_time for the end?
        # But the problem says date range of the trades, so we'll use entry_time.
        months_spanned = (end_date - start_date).days / 30.0
        if months_spanned == 0:
            months_spanned = 1.0  # avoid division by zero
        trades_per_month = n_trades / months_spanned
    else:
        start_date = end_date = None
        months_spanned = None
        trades_per_month = None

    # Win rate
    win_rate = (df['net_pnl_pct'] > 0).mean() * 100

    # Total PnL (%)
    total_pnl = df['net_pnl_pct'].sum()

    # Mean PnL per trade (%)
    mean_pnl_per_trade = df['net_pnl_pct'].mean()

    # Sharpe ratio (annualized)
    # We'll use the formula: sharpe = (mean / std) * sqrt(trades_per_year)
    # where trades_per_year = (n_trades / months_spanned) * 12
    if months_spanned and months_spanned > 0 and df['net_pnl_pct'].std() > 0:
        mean_ret = df['net_pnl_pct'].mean()
        std_ret = df['net_pnl_pct'].std()
        trades_per_year = (n_trades / months_spanned) * 12
        sharpe = (mean_ret / std_ret) * np.sqrt(trades_per_year)
    else:
        sharpe = 0.0

    # Max drawdown: we need to compute the equity curve
    # We'll sort by entry_time and then compute cumulative sum of net_pnl_pct
    if 'entry_time' in df.columns and not df['entry_time'].isnull().all():
        df_sorted = df.sort_values('entry_time')
        equity_curve = df_sorted['net_pnl_pct'].cumsum()
        max_drawdown = compute_max_drawdown(equity_curve)
    else:
        max_drawdown = None

    # Average win and average loss
    wins = df[df['net_pnl_pct'] > 0]['net_pnl_pct']
    losses = df[df['net_pnl_pct'] <= 0]['net_pnl_pct']
    avg_win = wins.mean() if len(wins) > 0 else 0.0
    avg_loss = losses.mean() if len(losses) > 0 else 0.0
    # Avoid division by zero for R:R ratio
    if avg_loss != 0:
        rr_ratio = abs(avg_win / avg_loss)
    else:
        rr_ratio = float('inf') if avg_win > 0 else 0.0

    return {
        'file': os.path.basename(filepath),
        'trades': n_trades,
        'start_date': start_date,
        'end_date': end_date,
        'months_spanned': months_spanned,
        'trades_per_month': trades_per_month,
        'win_rate': win_rate,
        'total_pnl': total_pnl,
        'mean_pnl_per_trade': mean_pnl_per_trade,
        'sharpe': sharpe,
        'max_drawdown': max_drawdown,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'rr_ratio': rr_ratio
    }

def main():
    print("=" * 90)
    print("THRESHOLD DIAGNOSTIC")
    print("=" * 90)

    results = []
    for filename in THRESHOLD_FILES:
        filepath = os.path.join(RESULTS_DIR, filename)
        result = analyze_threshold_file(filepath)
        if result is None:
            print(f"Could not load or empty file: {filename}")
            continue
        results.append(result)

    # Print table
    if not results:
        print("No valid threshold files found.")
        return

    # Define the columns we want to print
    columns = [
        ('File', 30),
        ('Trades', 8),
        ('Trades/Month', 12),
        ('Win Rate (%)', 10),
        ('Total PnL (%)', 12),
        ('Mean PnL/Trade (%)', 15),
        ('Sharpe', 8),
        ('Max DD (%)', 10),
        ('Avg Win (%)', 10),
        ('Avg Loss (%)', 12),
        ('R:R', 8)
    ]

    # Print header
    header = ""
    for col, width in columns:
        header += f"{col:<{width}}"
    print(header)
    print("-" * len(header))

    # Print each row
    for res in results:
        row = ""
        row += f"{res['file']:<{columns[0][1]}}"
        row += f"{res['trades']:<{columns[1][1]}}"
        trades_per_month = res['trades_per_month']
        row += f"{trades_per_month if trades_per_month is not None else 0.0:<{columns[2][1]}.1f}"
        row += f"{res['win_rate']:<{columns[3][1]}.1f}"
        row += f"{res['total_pnl']:<{columns[4][1]}.2f}"
        row += f"{res['mean_pnl_per_trade']:<{columns[5][1]}.3f}"
        row += f"{res['sharpe']:<{columns[6][1]}.2f}"
        max_dd = res['max_drawdown']
        row += f"{max_dd if max_dd is not None else 0.0:<{columns[7][1]}.2f}"
        row += f"{res['avg_win']:<{columns[8][1]}.3f}"
        row += f"{res['avg_loss']:<{columns[9][1]}.3f}"
        rr = res['rr_ratio']
        rr_str = f"{rr:.2f}" if rr != float('inf') else "inf"
        row += f"{rr_str:<{columns[10][1]}}"
        print(row)

    # Save output to file
    output_file = os.path.join(RESULTS_DIR, 'threshold_diagnostic.txt')
    with open(output_file, 'w') as f:
        f.write("=" * 90 + "\n")
        f.write("THRESHOLD DIAGNOSTIC\n")
        f.write("=" * 90 + "\n\n")
        # Write the table again
        header = ""
        for col, width in columns:
            header += f"{col:<{width}}"
        f.write(header + "\n")
        f.write("-" * len(header) + "\n")
        for res in results:
            row = ""
            row += f"{res['file']:<{columns[0][1]}}"
            row += f"{res['trades']:<{columns[1][1]}}"
            trades_per_month = res['trades_per_month']
            row += f"{trades_per_month if trades_per_month is not None else 0.0:<{columns[2][1]}.1f}"
            row += f"{res['win_rate']:<{columns[3][1]}.1f}"
            row += f"{res['total_pnl']:<{columns[4][1]}.2f}"
            row += f"{res['mean_pnl_per_trade']:<{columns[5][1]}.3f}"
            row += f"{res['sharpe']:<{columns[6][1]}.2f}"
            max_dd = res['max_drawdown']
            row += f"{max_dd if max_dd is not None else 0.0:<{columns[7][1]}.2f}"
            row += f"{res['avg_win']:<{columns[8][1]}.3f}"
            row += f"{res['avg_loss']:<{columns[9][1]}.3f}"
            rr = res['rr_ratio']
            rr_str = f"{rr:.2f}" if rr != float('inf') else "inf"
            row += f"{rr_str:<{columns[10][1]}}"
            f.write(row + "\n")
    print(f"\nDiagnostic saved to: {output_file}")

if __name__ == '__main__':
    main()