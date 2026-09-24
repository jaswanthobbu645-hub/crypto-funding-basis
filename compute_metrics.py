import pandas as pd
import numpy as np
import os

mfs = [0.0002, 0.0003, 0.0004, 0.0005]
results = []

for mf in mfs:
    # Convert MF to filename format: e.g., 0.0002 -> mf0_0002
    mf_str = f"{mf:.4f}".replace('.', '_')
    file = f'results_phase2/multi_asset_trades_mf{mf_str}_slip1.0x.csv'
    if not os.path.exists(file):
        print(f"File not found: {file}")
        continue
    df = pd.read_csv(file)
    df['entry_time'] = pd.to_datetime(df['entry_time'])
    df['exit_time'] = pd.to_datetime(df['exit_time'])
    
    trades = len(df)
    min_time = df['entry_time'].min()
    max_time = df['exit_time'].max()
    months = (max_time - min_time).days / 30.44
    trades_per_month = trades / months if months > 0 else 0
    
    win_rate = (df['net_pnl_pct'] > 0).mean() * 100
    total_pnl = df['net_pnl_pct'].sum()
    
    returns = df['net_pnl_pct'].values / 100.0  # decimal
    mean_ret = np.mean(returns)
    std_ret = np.std(returns, ddof=1)
    tpy = trades / months * 12 if months > 0 else 0
    ann_factor = np.sqrt(tpy) if tpy > 0 else 0
    sharpe = mean_ret / std_ret * ann_factor if std_ret != 0 else 0
    
    # Max DD (additive)
    cumsum = np.cumsum(returns)
    running_max = np.maximum.accumulate(cumsum)
    dd = cumsum - running_max  # decimal
    max_dd = dd.min() * 100  # percentage
    
    # R:R
    avg_win = returns[returns > 0].mean() if any(returns > 0) else 0
    avg_loss = abs(returns[returns < 0].mean()) if any(returns < 0) else 0
    rr = avg_win / avg_loss if avg_loss != 0 else 0
    
    results.append({
        'mf': mf,
        'trades': trades,
        'months': months,
        'trades_per_month': trades_per_month,
        'win_rate': win_rate,
        'total_pnl': total_pnl,
        'sharpe': sharpe,
        'max_dd': max_dd,
        'rr': rr
    })

# Print table
print("MF       Trades  Months   Trades/mo  Win%   Total PnL%  Sharpe   Max DD%  R:R")
print("-" * 70)
for r in results:
    print(f"{r['mf']:.4f}  {r['trades']:7d}  {r['months']:7.2f}  {r['trades_per_month']:10.2f}  {r['win_rate']:5.1f}  {r['total_pnl']:10.2f}  {r['sharpe']:7.2f}  {r['max_dd']:8.2f}  {r['rr']:5.2f}")

# Save to file
output_dir = 'results_phase2'
os.makedirs(output_dir, exist_ok=True)
output_file = os.path.join(output_dir, 'frequency_report_v2.txt')
with open(output_file, 'w') as f:
    f.write("MF       Trades  Months   Trades/mo  Win%   Total PnL%  Sharpe   Max DD%  R:R\\n")
    f.write("-" * 70 + "\\n")
    for r in results:
        f.write(f"{r['mf']:.4f}  {r['trades']:7d}  {r['months']:7.2f}  {r['trades_per_month']:10.2f}  {r['win_rate']:5.1f}  {r['total_pnl']:10.2f}  {r['sharpe']:7.2f}  {r['max_dd']:8.2f}  {r['rr']:5.2f}\\n")
print(f"\\nSaved to {output_file}")