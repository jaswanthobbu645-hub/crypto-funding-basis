import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os

# Load the winning trades file (MF=0.0003 from chosen config, baseline slippage)
trades_file = 'results_phase2/multi_asset_trades_mf0_0003_slip1.0x.csv'
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

# Extract returns (net_pnl_pct column, convert to decimal)
returns = df['net_pnl_pct'].values / 100.0

# Monte Carlo simulation: bootstrap WITH replacement
n_sims = 1000
n_trades = len(returns)

final_pnls = []
max_drawdowns = []

for i in range(n_sims):
    # Bootstrap sample with replacement
    sample = np.random.choice(returns, size=n_trades, replace=True)
    # Calculate cumulative PnL
    cumsum = np.cumsum(sample)
    final_pnl = cumsum[-1]  # final PnL
    # Calculate max drawdown
    running_max = np.maximum.accumulate(cumsum)
    drawdown = (cumsum - running_max) / (running_max + 1e-10)  # avoid division by zero
    max_dd = np.min(drawdown)  # most negative drawdown
    
    final_pnls.append(final_pnl)
    max_drawdowns.append(max_dd)

final_pnls = np.array(final_pnls)
max_drawdowns = np.array(max_drawdowns)

# Calculate percentiles
final_pnl_percentiles = np.percentile(final_pnls, [5, 25, 50, 75, 95])
max_dd_percentiles = np.percentile(max_drawdowns, [5, 25, 50, 75, 95])

print("MONTE CARLO BOOTSTRAP RESULTS (1000 simulations)")
print("=" * 50)
print(f"Original strategy final PnL: {np.sum(returns):.4f}")
print(f"Original strategy max drawdown: {np.min(np.cumsum(returns) - np.maximum.accumulate(np.cumsum(returns))):.4f}")
print()
print("Final PnL percentiles:")
print(f"  5th:  {final_pnl_percentiles[0]:.4f}")
print(f"  25th: {final_pnl_percentiles[1]:.4f}")
print(f"  50th: {final_pnl_percentiles[2]:.4f} (median)")
print(f"  75th: {final_pnl_percentiles[3]:.4f}")
print(f"  95th: {final_pnl_percentiles[4]:.4f}")
print()
print("Max Drawdown percentiles (as negative values):")
print(f"  5th:  {max_dd_percentiles[0]:.4f}")
print(f"  25th: {max_dd_percentiles[1]:.4f}")
print(f"  50th: {max_dd_percentiles[2]:.4f} (median)")
print(f"  75th: {max_dd_percentiles[3]:.4f}")
print(f"  95th: {max_dd_percentiles[4]:.4f}")

# Create a simple chart
plt.figure(figsize=(12, 8))

# Plot 1: Distribution of final PnL
plt.subplot(2, 2, 1)
plt.hist(final_pnls, bins=30, alpha=0.7, edgecolor='black')
plt.axvline(np.sum(returns), color='red', linestyle='--', label='Original')
plt.axvline(np.median(final_pnls), color='green', linestyle='--', label='Median')
plt.xlabel('Final PnL')
plt.ylabel('Frequency')
plt.title('Distribution of Final PnL (Bootstrap)')
plt.legend()
plt.grid(True, alpha=0.3)

# Plot 2: Distribution of max drawdown
plt.subplot(2, 2, 2)
plt.hist(max_drawdowns, bins=30, alpha=0.7, edgecolor='black')
plt.axvline(np.min(np.cumsum(returns) - np.maximum.accumulate(np.cumsum(returns))), color='red', linestyle='--', label='Original')
plt.axvline(np.median(max_drawdowns), color='green', linestyle='--', label='Median')
plt.xlabel('Max Drawdown')
plt.ylabel('Frequency')
plt.title('Distribution of Max Drawdown (Bootstrap)')
plt.legend()
plt.grid(True, alpha=0.3)

# Plot 3: QQ plot for final PnL
plt.subplot(2, 2, 3)
from scipy import stats
stats.probplot(final_pnls, dist="norm", plot=plt)
plt.title('Q-Q Plot: Final PnL')
plt.grid(True, alpha=0.3)

# Plot 4: Time series of a few bootstrap samples
plt.subplot(2, 2, 4)
for i in range(min(5, n_sims)):
    sample = np.random.choice(returns, size=n_trades, replace=True)
    cumsum = np.cumsum(sample)
    plt.plot(cumsum, alpha=0.7, linewidth=1)
plt.plot(np.cumsum(returns), color='red', linewidth=2, label='Original')
plt.xlabel('Trade Number')
plt.ylabel('Cumulative PnL')
plt.title('Sample Bootstrap Paths')
plt.legend()
plt.grid(True, alpha=0.3)

plt.tight_layout()

# Save chart
charts_dir = 'charts'
os.makedirs(charts_dir, exist_ok=True)
chart_file = os.path.join(charts_dir, 'monte_carlo.png')
plt.savefig(chart_file, dpi=150, bbox_inches='tight')
print(f"\nChart saved to {chart_file}")

# Save results to file
output_dir = 'results_phase2'
os.makedirs(output_dir, exist_ok=True)
output_file = os.path.join(output_dir, 'monte_carlo_results.txt')
with open(output_file, 'w') as f:
    f.write("MONTE CARLO BOOTSTRAP RESULTS\n")
    f.write("=" * 40 + "\n\n")
    f.write(f"Number of simulations: {n_sims}\n")
    f.write(f"Number of trades: {n_trades}\n\n")
    f.write("ORIGINAL STRATEGY\n")
    f.write("-" * 20 + "\n")
    f.write(f"Final PnL: {np.sum(returns):.6f}\n")
    f.write(f"Max Drawdown: {np.min(np.cumsum(returns) - np.maximum.accumulate(np.cumsum(returns))):.6f}\n\n")
    f.write("FINAL PNL PERCENTILES\n")
    f.write("-" * 20 + "\n")
    for p, val in zip([5, 25, 50, 75, 95], final_pnl_percentiles):
        f.write(f"{p}th percentile: {val:.6f}\n")
    f.write("\n")
    f.write("MAX DRAWDOWN PERCENTILES\n")
    f.write("-" * 20 + "\n")
    for p, val in zip([5, 25, 50, 75, 95], max_dd_percentiles):
        f.write(f"{p}th percentile: {val:.6f}\n")

print(f"Results saved to {output_file}")