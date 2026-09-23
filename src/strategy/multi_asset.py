import pandas as pd
import numpy as np
import os

DATA_DIR = 'data/expanded'
OUTPUT_DIR = 'results_phase2'
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Strategy parameters
ZSCORE_WINDOW = 30 * 24
ENTRY_Z = 1.2
EXIT_Z = 0.5
MAX_HOLD = 24
MIN_FUNDING_LEVELS = [0.0001, 0.0003, 0.0005, 0.0008, 0.0010]
FUND_HOURS = [0, 8, 16]

# Realistic execution model
P_MAKER = 0.70       # 70% maker fills
P_TAKER = 0.20       # 20% taker fills
P_MISSED = 0.10      # 10% missed (no trade)
FEE_MAKER = 0.0003   # 0.03% maker per side (problem statement)
FEE_TAKER = 0.0005   # 0.05% taker per side

np.random.seed(42)


def load_all_assets():
    assets = {}
    for f in sorted(os.listdir(DATA_DIR)):
        if not f.endswith('.parquet'): continue
        name = f.replace('.parquet', '').replace('_USDT_USDT', '')
        df = pd.read_parquet(os.path.join(DATA_DIR, f))
        df = df.sort_values('timestamp').reset_index(drop=True)
        df['fundingRate'] = df['fundingRate'].fillna(0)
        assets[name] = df
    return assets


def compute_zscore(series, window):
    m = series.rolling(window, min_periods=window // 2).mean()
    s = series.rolling(window, min_periods=window // 2).std()
    return (series - m) / s.replace(0, np.nan)


def simulate_execution_cost():
    """Randomly decide maker/taker/missed for one round-trip."""
    r = np.random.random()
    if r < P_MISSED:
        return None  # trade missed
    elif r < P_MISSED + P_MAKER:
        return FEE_MAKER * 2  # maker both sides
    else:
        return FEE_TAKER * 2  # taker both sides


def backtest_asset_with_threshold(df, asset_name, min_funding):
    df = df.copy()
    df['z'] = compute_zscore(df['fundingRate'], ZSCORE_WINDOW)

    trades = []
    pos = 0
    hh = 0
    fp = 0.0
    entry_time = None

    for i in range(1, len(df)):
        r = df.iloc[i]
        ts = r['timestamp']
        z = r['z']
        fr = r['fundingRate']
        if pd.isna(z):
            continue

        if pos != 0 and ts.hour in FUND_HOURS:
            fp += -pos * fr

        if pos != 0:
            hh += 1
            reason = None
            if (pos == -1 and z < EXIT_Z) or (pos == 1 and z > -EXIT_Z):
                reason = 'REVERT'
            elif hh >= MAX_HOLD:
                reason = 'TIMEOUT'

            if reason:
                # Simulate execution cost ONCE for this round-trip
                cost = simulate_execution_cost()
                if cost is not None:
                    net = (fp - cost) * 100
                    trades.append({
                        'asset': asset_name,
                        'net_pnl_pct': net,
                        'entry_time': entry_time,
                        'exit_time': ts,
                        'hours_held': hh,
                        'funding_pnl_pct': fp * 100,
                        'cost_pct': cost * 100,
                        'exit_reason': reason,
                    })
                pos = 0
                hh = 0
                fp = 0.0

        if pos == 0:
            if z > ENTRY_Z and abs(fr) >= min_funding:
                # Simulate execution cost ONCE for this trade attempt
                cost = simulate_execution_cost()
                if cost is not None:
                    pos = -1  # short perp
                    hh = 0
                    fp = 0.0
                    entry_time = ts
            elif z < -ENTRY_Z and abs(fr) >= min_funding:
                # Simulate execution cost ONCE for this trade attempt
                cost = simulate_execution_cost()
                if cost is not None:
                    pos = 1   # long perp
                    hh = 0
                    fp = 0.0
                    entry_time = ts

    return trades


def main():
    print("=" * 70)
    print("PHASE 2b: MIN_FUNDING SENSITIVITY (FIXED)")
    print("=" * 70)

    assets = load_all_assets()
    print(f"Loaded {len(assets)} assets\n")

    # Store results for each threshold
    threshold_results = []

    for mf in MIN_FUNDING_LEVELS:
        all_trades = []
        for name, df in assets.items():
            t = backtest_asset_with_threshold(df, name, mf)
            all_trades.extend(t)

        if not all_trades:
            print(f"MIN_FUNDING={mf:.4f}: No trades")
            threshold_results.append({
                'min_funding': mf,
                'trades': 0,
                'win_rate': 0.0,
                'total_pnl': 0.0,
                'sharpe': 0.0
            })
            continue

        tdf = pd.DataFrame(all_trades)
        total = tdf['net_pnl_pct'].sum()
        wr = (tdf['net_pnl_pct'] > 0).mean() * 100
        
        # Calculate Sharpe
        if len(tdf) > 1 and tdf['net_pnl_pct'].std() > 0:
            mean_ret = tdf['net_pnl_pct'].mean()
            std_ret = tdf['net_pnl_pct'].std()
            # Assuming trades are hourly opportunities, annualize
            trades_per_year = len(tdf) / 24 * 12  # monthly to yearly
            sharpe = (mean_ret / std_ret) * np.sqrt(trades_per_year)
        else:
            sharpe = 0.0

        print(f"MIN_FUNDING={mf:.4f}: {len(tdf):4d} trades, "
              f"WR {wr:5.1f}%, "
              f"PnL {total:+7.2f}%, "
              f"Sharpe {sharpe:5.2f}")

        threshold_results.append({
            'min_funding': mf,
            'trades': len(tdf),
            'win_rate': wr,
            'total_pnl': total,
            'sharpe': sharpe
        })

        # Save trades for this threshold
        if len(tdf) > 0:
            trades_file = os.path.join(OUTPUT_DIR, f'multi_asset_trades_mf{mf:.4f}.csv'.replace('.', '_'))
            tdf.to_csv(trades_file, index=False)
            print(f"  -> Trades saved to {trades_file}")

    # Print summary table
    print("\n" + "=" * 70)
    print("SUMMARY BY MIN_FUNDING THRESHOLD")
    print("=" * 70)
    print(f"{'Min Funding':<12} {'Trades':<8} {'Win Rate':<10} {'Total PnL':<12} {'Sharpe':<8}")
    print("-" * 70)
    for res in threshold_results:
        print(f"{res['min_funding']:<12.4f} {res['trades']:<8} {res['win_rate']:<10.1f} "
              f"{res['total_pnl']:<12.2f} {res['sharpe']:<8.2f}")

    # Save summary
    summary_file = os.path.join(OUTPUT_DIR, 'multi_asset_summary.txt')
    with open(summary_file, 'w') as f:
        f.write("MIN_FUNDING SENSITIVITY SUMMARY\n")
        f.write("=" * 50 + "\n")
        for res in threshold_results:
            f.write(f"Min Funding: {res['min_funding']:.4f}\n")
            f.write(f"  Trades: {res['trades']}\n")
            f.write(f"  Win Rate: {res['win_rate']:.1f}%\n")
            f.write(f"  Total PnL: {res['total_pnl']:.2f}%\n")
            f.write(f"  Sharpe: {res['sharpe']:.2f}\n")
            f.write("-" * 30 + "\n")

    print(f"\nSummary saved to {summary_file}")


if __name__ == '__main__':
    main()