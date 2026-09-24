import pandas as pd
import numpy as np
import os
import re

# Read the metrics full report
report_file = 'results_phase2/metrics_full_report.txt'
with open(report_file, 'r') as f:
    lines = f.readlines()

# Parse the report into sections for each slippage multiplier
slippage_sections = {}
current_label = None
for line in lines:
    line = line.strip()
    if line.startswith('SLIPPAGE MULTIPLIER:'):
        # Extract label
        match = re.search(r'SLIPPAGE MULTIPLIER:\s*(\d+\.?\d*x)', line)
        if match:
            current_label = match.group(1)
            slippage_sections[current_label] = []
    elif line.startswith('MF         Trades'):
        # Header line, skip
        continue
    elif line.startswith('---') or line == '':
        # Separator or empty line, skip
        continue
    elif current_label is not None and line:
        # Data line
        parts = line.split()
        if len(parts) >= 10:
            mf = float(parts[0])
            trades = int(parts[1])
            win_rate = float(parts[2].rstrip('%'))
            total_pnl = float(parts[3].rstrip('%'))
            sharpe = float(parts[4])
            max_dd = float(parts[5].rstrip('%'))
            rr = float(parts[6])
            gross_pnl = float(parts[7].rstrip('%'))
            net_pnl = float(parts[8].rstrip('%'))
            cost_pct = float(parts[9].rstrip('%'))
            months = float(parts[10]) if len(parts) > 10 else 0.0
            slippage_sections[current_label].append({
                'mf': mf,
                'trades': trades,
                'win_rate': win_rate,
                'total_pnl': total_pnl,
                'sharpe': sharpe,
                'max_dd': max_dd,
                'rr': rr,
                'gross_pnl': gross_pnl,
                'net_pnl': net_pnl,
                'cost_pct': cost_pct,
                'months': months
            })

# Focus on baseline slippage 1.0x
label = '1.0x'
if label not in slippage_sections:
    # Try without 'x'
    label = '1.0'
    if label not in slippage_sections:
        label = '1.0x'  # default
        print("Warning: Could not find 1.0x section, using first available")
        label = list(slippage_sections.keys())[0]

data = slippage_sections[label]
print(f"Found {len(data)} MF levels for slippage {label}:")
for d in data:
    print(f"  MF={d['mf']:.4f}: trades={d['trades']}, WR={d['win_rate']:.1f}%, PnL={d['total_pnl']:.2f}%, Sharpe={d['sharpe']:.2f}, MaxDD={d['max_dd']:.2f}%, R:R={d['rr']:.2f}")

# Compute trades per month
for d in data:
    if d['months'] > 0:
        d['trades_per_month'] = d['trades'] / d['months'] * 12
    else:
        d['trades_per_month'] = 0.0

print("\nWith trades/month:")
for d in data:
    print(f"  MF={d['mf']:.4f}: {d['trades_per_month']:.2f} trades/month, WR={d['win_rate']:.1f}%, PnL={d['total_pnl']:.2f}%, Sharpe={d['sharpe']:.2f}")

# Decision rule: Priority 1: Highest Sharpe with trades/month >= 30
candidates = [d for d in data if d['trades_per_month'] >= 30 and d['sharpe'] > 0]
if candidates:
    winner = max(candidates, key=lambda x: x['sharpe'])
    print(f"\nWINNER (Priority 1): MF={winner['mf']:.4f} with Sharpe={winner['sharpe']:.2f} and {winner['trades_per_month']:.2f} trades/month")
else:
    # Priority 2: If none qualify, pick the highest trades/month with positive PnL
    candidates = [d for d in data if d['trades_per_month'] >= 30 and d['total_pnl'] > 0]
    if candidates:
        winner = max(candidates, key=lambda x: x['trades_per_month'])
        print(f"\nWINNER (Priority 2): MF={winner['mf']:.4f} with {winner['trades_per_month']:.2f} trades/month and PnL={winner['total_pnl']:.2f}%")
    else:
        # Priority 3: Highest trades/month regardless
        winner = max(data, key=lambda x: x['trades_per_month'])
        print(f"\nWINNER (Priority 3): MF={winner['mf']:.4f} with {winner['trades_per_month']:.2f} trades/month (PnL={winner['total_pnl']:.2f}%)")

# Output the winner info for later use
print(f"\nWINNER_MF={winner['mf']:.4f}")
print(f"WINNER_TRADES_PER_MONTH={winner['trades_per_month']:.2f}")
print(f"WINNER_WIN_RATE={winner['win_rate']:.2f}")
print(f"WINNER_TOTAL_PNL={winner['total_pnl']:.2f}")
print(f"WINNER_SHARPE={winner['sharpe']:.2f}")
print(f"WINNER_MAX_DD={winner['max_dd']:.2f}")
print(f"WINNER_RR={winner['rr']:.2f}")
print(f"WINNER_GROSS_PNL={winner['gross_pnl']:.2f}")
print(f"WINNER_COST_PCT={winner['cost_pct']:.2f}")