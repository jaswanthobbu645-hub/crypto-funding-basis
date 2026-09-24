import pandas as pd
import numpy as np
import os

# Load the summary from the latest run
summary_file = 'results_phase2/multi_asset_summary.txt'
if not os.path.exists(summary_file):
    print("Summary file not found")
    exit(1)

# Parse the summary file to get data for slippage 1.0x (baseline)
# The file has sections for each slippage
with open(summary_file, 'r') as f:
    content = f.read()

# Extract the section for slippage 1.0x
lines = content.split('\n')
in_1x_section = False
data_1x = []
for line in lines:
    if '--- SUMMARY FOR SLIPPAGE 1.0x ---' in line:
        in_1x_section = True
        continue
    if in_1x_section and line.startswith('---') and 'SUMMARY FOR' in line:
        break
    if in_1x_section and line.strip() and not line.startswith('Min Funding') and not line.startswith('-'):
        parts = line.split()
        if len(parts) >= 8:
            mf = float(parts[0])
            trades = int(parts[1])
            win_rate = float(parts[2].rstrip('%'))
            total_pnl = float(parts[3].rstrip('%'))
            sharpe = float(parts[4])
            max_dd = float(parts[5].rstrip('%'))
            rr = float(parts[6])
            data_1x.append({
                'mf': mf,
                'trades': trades,
                'win_rate': win_rate,
                'total_pnl': total_pnl,
                'sharpe': sharpe,
                'max_dd': max_dd,
                'rr': rr
            })

print("Baseline (1.0x slippage) results:")
for d in data_1x:
    print(f"MF={d['mf']:.4f}: {d['trades']:4d} trades, WR {d['win_rate']:5.1f}%, PnL {d['total_pnl']:+7.2f}%, Sharpe {d['sharpe']:5.2f}, MaxDD {d['max_dd']:7.2f}%, R:R {d['rr']:4.2f}")

# Calculate months from the data (we can get it from the full report or estimate)
# Let's use the frequency report which has trades/month
freq_file = 'results_phase2/frequency_report.txt'
if os.path.exists(freq_file):
    with open(freq_file, 'r') as f:
        freq_lines = f.readlines()
    # Skip header and find the data lines
    for line in freq_lines:
        if '|' in line and 'MF Level' not in line and '-' not in line:
            parts = [p.strip() for p in line.split('|')]
            if len(parts) >= 6 and parts[0] and parts[0] != 'MF Level':
                mf_val = float(parts[0])
                trades_per_month = float(parts[3])
                # Find matching MF in data_1x
                for d in data_1x:
                    if abs(d['mf'] - mf_val) < 0.0001:
                        d['trades_per_month'] = trades_per_month
                        break

print("\nWith trades/month:")
for d in data_1x:
    if 'trades_per_month' in d:
        print(f"MF={d['mf']:.4f}: {d['trades_per_month']:6.2f} trades/month, WR {d['win_rate']:5.1f}%, PnL {d['total_pnl']:+7.2f}%, Sharpe {d['sharpe']:5.2f}")

# Apply decision rule: Priority 1: Highest Sharpe with trades/month >= 30
candidates = [d for d in data_1x if d.get('trades_per_month', 0) >= 30 and d['sharpe'] > 0]
if candidates:
    winner = max(candidates, key=lambda x: x['sharpe'])
    print(f"\nWINNER (Priority 1): MF={winner['mf']:.4f} with Sharpe={winner['sharpe']:.2f} and {winner.get('trades_per_month', 0):.2f} trades/month")
else:
    # Priority 2: If none qualify, pick the highest trades/month with positive PnL
    candidates = [d for d in data_1x if d.get('trades_per_month', 0) >= 30 and d['total_pnl'] > 0]
    if candidates:
        winner = max(candidates, key=lambda x: x['trades_per_month'])
        print(f"\nWINNER (Priority 2): MF={winner['mf']:.4f} with {winner['trades_per_month']:.2f} trades/month and PnL={winner['total_pnl']:.2f}%")
    else:
        # Priority 3: Highest trades/month regardless
        winner = max(data_1x, key=lambda x: x.get('trades_per_month', 0))
        print(f"\nWINNER (Priority 3): MF={winner['mf']:.4f} with {winner.get('trades_per_month', 0):.2f} trades/month (PnL={winner['total_pnl']:.2f}%)")