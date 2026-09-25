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
MIN_FUNDING_LEVELS = [0.0002, 0.0003, 0.0004, 0.0005]
FUND_HOURS = [0, 8, 16]

# Realistic execution model
P_MAKER = 0.70       # 70% maker fills
P_TAKER = 0.20       # 20% taker fills
P_MISSED = 0.10      # 10% missed (no trade)
FEE_MAKER = 0.0003   # 0.03% maker per side (problem statement)
FEE_TAKER = 0.0005   # 0.05% taker per side
BASE_SLIPPAGE_PER_SIDE = 0.0002  # 0.02% per side (from config.py in repo)

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


def simulate_execution_cost(slippage_multiplier=1.0):
    """Randomly decide maker/taker/missed for one round-trip and return total cost (fee + slippage)."""
    r = np.random.random()
    if r < P_MISSED:
        return None  # trade missed
    elif r < P_MISSED + P_MAKER:
        fee_cost = FEE_MAKER * 2  # maker both sides
    else:
        fee_cost = FEE_TAKER * 2  # taker both sides
    
    # Slippage: applied per side, round-trip
    slippage_per_side = BASE_SLIPPAGE_PER_SIDE * slippage_multiplier
    round_trip_slippage = slippage_per_side * 2
    
    total_cost = fee_cost + round_trip_slippage
    return total_cost


def backtest_asset_with_threshold(df, asset_name, min_funding, slippage_multiplier=1.0):
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
                cost = simulate_execution_cost(slippage_multiplier)
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
                cost = simulate_execution_cost(slippage_multiplier)
                if cost is not None:
                    pos = -1  # short perp
                    hh = 0
                    fp = 0.0
                    entry_time = ts
            elif z < -ENTRY_Z and abs(fr) >= min_funding:
                # Simulate execution cost ONCE for this trade attempt
                cost = simulate_execution_cost(slippage_multiplier)
                if cost is not None:
                    pos = 1   # long perp
                    hh = 0
                    fp = 0.0
                    entry_time = ts

    return trades


def apply_position_cap(trades_df, cap_fraction=0.15):
    """
    Cap each asset's contribution to total PnL at cap_fraction.
    Returns (capped_trades_df, raw_asset_pnl_series, capped_asset_pnl_series)
    """
    if trades_df.empty:
        return trades_df.copy(), pd.Series(dtype=float), pd.Series(dtype=float)

    # Compute asset PnL
    asset_pnl = trades_df.groupby('asset')['net_pnl_pct'].sum()
    total_pnl = asset_pnl.sum()

    # If total PnL <= 0, we don't cap (we could cap negative assets but skip for now)
    if total_pnl <= 0:
        return trades_df.copy(), asset_pnl, asset_pnl

    # Determine which assets exceed the cap
    exceeded = asset_pnl > cap_fraction * total_pnl
    if not any(exceeded):
        return trades_df.copy(), asset_pnl, asset_pnl

    # Create a copy of trades_df to modify
    capped_trades = trades_df.copy()

    # For each exceeded asset, compute scale factor and apply to its trades
    for asset in asset_pnl[exceeded].index:
        asset_total = asset_pnl[asset]
        target = cap_fraction * total_pnl
        scale_factor = target / asset_total
        # Apply to all trades of this asset
        mask = capped_trades['asset'] == asset
        capped_trades.loc[mask, 'net_pnl_pct'] *= scale_factor
        capped_trades.loc[mask, 'funding_pnl_pct'] *= scale_factor
        capped_trades.loc[mask, 'cost_pct'] *= scale_factor

    # Recompute asset PnL after capping
    capped_asset_pnl = capped_trades.groupby('asset')['net_pnl_pct'].sum()

    return capped_trades, asset_pnl, capped_asset_pnl


def calculate_metrics(trades_df):
    if trades_df.empty:
        return {
            'trades': 0,
            'win_rate': 0.0,
            'total_pnl': 0.0,
            'sharpe': 0.0,
            'max_dd': 0.0,
            'avg_win': 0.0,
            'avg_loss': 0.0,
            'rr': 0.0,
            'gross_pnl': 0.0,
            'net_pnl': 0.0,
            'cost_drag': 0.0,
            'months': 0.0
        }

    # Basic stats
    trades = len(trades_df)
    win_rate = (trades_df['net_pnl_pct'] > 0).mean() * 100
    total_pnl = trades_df['net_pnl_pct'].sum()

    # Sharpe with correct annualization
    if trades > 1:
        # Calculate months from actual trade timestamps
        min_time = trades_df['entry_time'].min()
        max_time = trades_df['exit_time'].max()
        months = (max_time - min_time).days / 30.44
        if months > 0:
            tpy = trades / months * 12
            ann_factor = np.sqrt(tpy)
            mean_ret = trades_df['net_pnl_pct'].mean()
            std_ret = trades_df['net_pnl_pct'].std()
            if std_ret > 0:
                sharpe = (mean_ret / std_ret) * ann_factor
            else:
                sharpe = 0.0
        else:
            sharpe = 0.0
    else:
        sharpe = 0.0
        months = 0.0

    # Max drawdown from equity curve (cumulative net PnL)
    df_sorted = trades_df.sort_values('exit_time')
    cum = df_sorted['net_pnl_pct'].cumsum()  # in percent
    peak = np.maximum.accumulate(cum)
    dd = cum - peak  # in percent
    max_dd = dd.min()  # already in percent (negative or zero)

    # Average win and loss
    wins = trades_df[trades_df['net_pnl_pct'] > 0]['net_pnl_pct']
    losses = trades_df[trades_df['net_pnl_pct'] < 0]['net_pnl_pct']
    avg_win = wins.mean() if len(wins) > 0 else 0
    avg_loss = abs(losses.mean()) if len(losses) > 0 else 0
    rr = avg_win / avg_loss if avg_loss != 0 else 0

    # Gross vs net
    gross_pnl = trades_df['funding_pnl_pct'].sum()
    net_pnl = trades_df['net_pnl_pct'].sum()
    cost_drag = gross_pnl - net_pnl  # or sum of cost_pct

    return {
        'trades': trades,
        'win_rate': win_rate,
        'total_pnl': total_pnl,
        'sharpe': sharpe,
        'max_dd': max_dd,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'rr': rr,
        'gross_pnl': gross_pnl,
        'net_pnl': net_pnl,
        'cost_drag': cost_drag,
        'months': months
    }


def main():
    print("=" * 70)
    print("PHASE 2: ADDING MISSING METRICS AND SLIPPAGE SENSITIVITY")
    print("=" * 70)

    assets = load_all_assets()
    print(f"Loaded {len(assets)} assets\n")

    # Slippage multipliers to test
    slippage_multipliers = [0.5, 1.0, 1.5]
    slippage_labels = ['0.5x', '1.0x', '1.5x']

    # Store all results
    all_results = []

    for sm, label in zip(slippage_multipliers, slippage_labels):
        print(f"\n{'='*20} SLIPPAGE {label} {'='*20}")
        threshold_results = []

        for mf in MIN_FUNDING_LEVELS:
            all_trades = []
            for name, df in assets.items():
                t = backtest_asset_with_threshold(df, name, mf, sm)
                all_trades.extend(t)

            if not all_trades:
                print(f"MIN_FUNDING={mf:.4f}: No trades")
                threshold_results.append({
                    'min_funding': mf,
                    'trades': 0,
                    'win_rate': 0.0,
                    'total_pnl': 0.0,
                    'sharpe': 0.0,
                    'max_dd': 0.0,
                    'avg_win': 0.0,
                    'avg_loss': 0.0,
                    'rr': 0.0,
                    'gross_pnl': 0.0,
                    'net_pnl': 0.0,
                    'cost_drag': 0.0,
                    'months': 0.0
                })
                continue

            tdf = pd.DataFrame(all_trades)
            metrics = calculate_metrics(tdf)
            metrics['min_funding'] = mf
            metrics['slippage'] = label
            threshold_results.append(metrics)

            print(f"MIN_FUNDING={mf:.4f}: {metrics['trades']:4d} trades, "
                  f"WR {metrics['win_rate']:5.1f}%, "
                  f"PnL {metrics['total_pnl']:+7.2f}%, "
                  f"Sharpe {metrics['sharpe']:5.2f}, "
                  f"MaxDD {metrics['max_dd']:6.2f}%, "
                  f"R:R {metrics['rr']:4.2f}")

            # Save trades for this threshold and slippage
            if len(tdf) > 0:
                mf_str = f'{mf:.4f}'.replace('.', '_')
                trades_file = os.path.join(OUTPUT_DIR, f'multi_asset_trades_mf{mf_str}_slip{label}.csv')
                tdf.to_csv(trades_file, index=False)
                
                # Apply position cap and save capped trades
                capped_trades, raw_asset_pnl, capped_asset_pnl = apply_position_cap(tdf, cap_fraction=0.15)
                if len(capped_trades) > 0:
                    # Calculate metrics for capped trades
                    capped_metrics = calculate_metrics(capped_trades)
                    
                    # Report: raw PnL, capped PnL, per-asset contribution after capping
                    total_raw_pnl = raw_asset_pnl.sum()
                    total_capped_pnl = capped_asset_pnl.sum()
                    
                    print(f"  Position capping (15% cap):")
                    print(f"    Raw PnL: {total_raw_pnl:+.2f}%")
                    print(f"    Capped PnL: {total_capped_pnl:+.2f}%")
                    
                    # Show top assets contributions before and after capping
                    if len(raw_asset_pnl) > 0:
                        top_asset_raw = raw_asset_pnl.idxmax()
                        top_asset_raw_pct = (raw_asset_pnl.max() / total_raw_pnl * 100) if total_raw_pnl != 0 else 0
                        top_asset_capped = capped_asset_pnl.idxmax() if len(capped_asset_pnl) > 0 else None
                        top_asset_capped_pct = (capped_asset_pnl.max() / total_capped_pnl * 100) if total_capped_pnl != 0 and len(capped_asset_pnl) > 0 else 0
                        
                        print(f"    Top asset raw: {top_asset_raw} ({top_asset_raw_pct:.1f}% of PnL)")
                        print(f"    Top asset capped: {top_asset_capped} ({top_asset_capped_pct:.1f}% of PnL)")
                    
                    # Save capped trades
                    capped_trades_file = os.path.join(OUTPUT_DIR, f'multi_asset_trades_mf{mf_str}_slip{label}_CAPPED.csv')
                    capped_trades.to_csv(capped_trades_file, index=False)
                    print(f"    Saved capped trades to: {capped_trades_file}")
                    
                    # STOP and report if capped PnL falls below +10%
                    if total_capped_pnl < 10.0:
                        print(f"    WARNING: Capped PnL ({total_capped_pnl:+.2f}%) is below +10% threshold!")
                else:
                    print(f"  Position capping: No trades after capping")

        all_results.extend(threshold_results)

        # Print summary table for this slippage
        print(f"\n--- SUMMARY FOR SLIPPAGE {label} ---")
        print(f"{'Min Funding':<12} {'Trades':<8} {'Win Rate':<10} {'Total PnL':<12} {'Sharpe':<8} {'Max DD':<10} {'R:R':<8}")
        print("-" * 70)
        for res in threshold_results:
            print(f"{res['min_funding']:<12.4f} {res['trades']:<8} {res['win_rate']:<10.1f} "
                  f"{res['total_pnl']:<12.2f} {res['sharpe']:<8.2f} {res['max_dd']:<10.2f} {res['rr']:<8.2f}")

    # Save full report
    report_file = os.path.join(OUTPUT_DIR, 'metrics_full_report.txt')
    with open(report_file, 'w') as f:
        f.write("METRICS FULL REPORT\n")
        f.write("=" * 80 + "\n\n")
        for sm, label in zip(slippage_multipliers, slippage_labels):
            f.write(f"SLIPPAGE MULTIPLIER: {label}\n")
            f.write("-" * 40 + "\n")
            f.write(f"{'MF':<10} {'Trades':<8} {'WR%':<8} {'PnL%':<10} {'Sharpe':<8} {'MaxDD%':<10} {'R:R':<8} {' Gross%':<10} {' Net%':<10} {'Cost%':<10} {'Months':<8}\n")
            f.write("-" * 100 + "\n")
            for res in all_results:
                if res['slippage'] == label:
                    f.write(f"{res['min_funding']:<10.4f} {res['trades']:<8} {res['win_rate']:<8.1f} "
                          f"{res['total_pnl']:<10.2f} {res['sharpe']:<8.2f} {res['max_dd']:<10.2f} "
                          f"{res['rr']:<8.2f} {res['gross_pnl']:<10.2f} {res['net_pnl']:<10.2f} "
                          f"{res['cost_drag']:<10.2f} {res['months']:<8.1f}\n")
            f.write("\n")

    print(f"\nFull report saved to {report_file}")

    # Also save a summary of the best configuration per slippage
    summary_file = os.path.join(OUTPUT_DIR, 'multi_asset_summary.txt')
    with open(summary_file, 'w') as f:
        f.write("MIN_FUNDING SENSITIVITY SUMMARY (with slippage sensitivity)\n")
        f.write("=" * 60 + "\n\n")
        for sm, label in zip(slippage_multipliers, slippage_labels):
            f.write(f"Slippage {label}:\n")
            f.write(f"{'Min Funding':<12} {'Trades':<8} {'Win Rate':<10} {'Total PnL':<12} {'Sharpe':<8} {'Max DD':<10} {'R:R':<8}\n")
            f.write("-" * 70 + "\n")
            for res in all_results:
                if res['slippage'] == label:
                    f.write(f"{res['min_funding']:<12.4f} {res['trades']:<8} {res['win_rate']:<10.1f} "
                          f"{res['total_pnl']:<12.2f} {res['sharpe']:<8.2f} {res['max_dd']:<10.2f} {res['rr']:<8.2f}\n")
            f.write("\n")

    print(f"Summary saved to {summary_file}")


if __name__ == '__main__':
    main()