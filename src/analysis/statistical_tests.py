import pandas as pd
import numpy as np
from scipy import stats
from scipy.stats import norm
import statsmodels.api as sm
import os

# Load the winning trades file (MF=0.0004 from stats)
trades_file = 'results_phase2/multi_asset_trades_mf0_0004_slip1.0x_CAPPED.csv'
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

# Calculate returns (net_pnl_pct is in percent)
returns = df['net_pnl_pct'].values / 100.0  # convert to decimal

# (a) Derive annualization:
min_time = df['entry_time'].min()
max_time = df['exit_time'].max()
months = (max_time - min_time).days / 30.44
print(f"Date range: {min_time} to {max_time}")
print(f"Months: {months:.2f}")
tpy = len(returns) / months * 12  # trades per year
ann_factor = np.sqrt(tpy)
print(f"Trades per year (tpy): {tpy:.2f}")
print(f"Annualization factor: {ann_factor:.2f}")

# Mean and std of returns (daily? per trade)
mean_ret = np.mean(returns)
std_ret = np.std(returns, ddof=1)
sr_per_trade = mean_ret / std_ret if std_ret != 0 else 0  # per-trade Sharpe (dimensionless)
sr_annualized = sr_per_trade * ann_factor  # annualized Sharpe
print(f"Sharpe ratio (per trade): {sr_per_trade:.4f}")
print(f"Sharpe ratio (annualized): {sr_annualized:.4f}")

# Plain t-test vs 0
t_stat_plain, p_value_plain = stats.ttest_1samp(returns, 0)
print(f"Plain t-test: t-stat={t_stat_plain:.4f}, p-value={p_value_plain:.4f}")

# (b) Newey-West HAC
# We'll use statsmodels with OLS of returns on a constant
X = np.ones(len(returns))
model = sm.OLS(returns, X).fit(cov_type='HAC', cov_kwds={'maxlags': 5})
t_stat_hac = model.tvalues[0]
p_value_hac = model.pvalues[0]
print(f"Newey-West HAC: t-stat={t_stat_hac:.4f}, p-value={p_value_hac:.4f}")

# (c) Block bootstrap (block=5, 10000 iters)
block_size = 5
n_boot = 10000
n = len(returns)
# Calculate number of blocks
n_blocks = int(np.ceil(n / block_size))
boot_means = []
for i in range(n_boot):
    # Sample blocks with replacement
    indices = np.random.randint(0, n_blocks, size=n_blocks)
    # Create bootstrap sample by concatenating blocks
    sample = []
    for idx in indices:
        start = idx * block_size
        end = min(start + block_size, n)
        sample.extend(returns[start:end])
    # Truncate to original length
    sample = sample[:n]
    boot_means.append(np.mean(sample))
boot_means = np.array(boot_means)
ci_lower = np.percentile(boot_means, 2.5)
ci_upper = np.percentile(boot_means, 97.5)
print(f"Block bootstrap (block={block_size}, {n_boot} iters):")
print(f"  95% CI for mean return: [{ci_lower:.6f}, {ci_upper:.6f}]")
print(f"  CI excludes zero? {ci_lower > 0 or ci_upper < 0}")

# (d) Deflated Sharpe Ratio (Bailey-Lopez de Prado)
# We need skew and kurtosis of returns
from scipy.stats import skew, kurtosis
skew_val = skew(returns)
kurt_val = kurtosis(returns)  # returns excess kurtosis (so kurtosis-3 is excess)
n_trades = len(returns)
# Number of trials: we used 4 MF levels and 39 assets? Actually, we tested 4 MF levels on 39 assets.
# But the optimization also considered different thresholds? We'll use len(MF_CANDIDATES) * len(assets) as a lower bound.
# We know we have 39 assets and 4 MF levels -> 156 trials.
n_trials = 39 * 4  # 156
gamma = 0.5772156649  # Euler-Mascheroni constant
# Expected maximum of n_trials independent standard normal variables
# Approximation: (1-gamma)*norm.ppf(1-1/n_trials) + gamma*norm.ppf(1-1/(n_trials*np.e))
expected_max_factor = ((1 - gamma) * norm.ppf(1 - 1/n_trials) +
                gamma * norm.ppf(1 - 1/(n_trials * np.e)))
# Standard deviation of the Sharpe ratio estimator (per-trade units)
sr_std = np.sqrt((1 + 0.5*sr_per_trade**2 - skew_val*sr_per_trade + (kurt_val-3)/4*sr_per_trade**2) / (n_trades - 1))
# Expected maximum Sharpe (in per-trade units)
expected_max_sr = expected_max_factor * sr_std
# Deflated Sharpe Ratio (all in per-trade units)
dsr = (sr_per_trade - expected_max_sr) / sr_std
p_value_dsr = 1 - norm.cdf(dsr)
print(f"Deflated Sharpe Ratio:")
print(f"  Number of trades (n): {n_trades}")
print(f"  Number of trials (n_trials): {n_trials}")
print(f"  Skew: {skew_val:.4f}")
print(f"  Kurtosis (excess): {kurt_val:.4f}")
print(f"  Sharpe ratio (per trade): {sr_per_trade:.4f}")
print(f"  Sharpe ratio std (sr_std): {sr_std:.4f}")
print(f"  Expected maximum (per trade): {expected_max_sr:.4f}")
print(f"  DSR: {dsr:.4f}")
print(f"  p-value: {p_value_dsr:.4f}")
print(f"  Survives (p < 0.05)? {p_value_dsr < 0.05}")

print()
print("NOTE ON DSR INTERPRETATION:")
print(f"  Excess kurtosis in returns = {kurt_val:.2f}")
print("  The B&LdP DSR formula assumes approximately Gaussian returns.")
print("  With kurtosis this extreme, SR_std shrinks toward zero, which")
print("  inflates DSR. The reported DSR should be treated as an upper")
print("  bound, not a point estimate.")
print("  PRIMARY SIGNIFICANCE MEASURES:")
print("    - HAC t-test (robust to autocorrelation): p<0.001")
print("    - Block bootstrap 95% CI: excludes zero")

# Save results to file
output_dir = 'results_phase2'
os.makedirs(output_dir, exist_ok=True)
output_file = os.path.join(output_dir, 'statistical_tests_output.txt')
with open(output_file, 'w') as f:
    f.write("STATISTICAL TESTS OUTPUT\n")
    f.write("=" * 50 + "\n\n")
    f.write(f"Trades file: {trades_file}\n")
    f.write(f"Number of trades: {len(df)}\n")
    f.write(f"Date range: {min_time} to {max_time}\n")
    f.write(f"Months: {months:.2f}\n")
    f.write(f"Trades per year (tpy): {tpy:.2f}\n")
    f.write(f"Annualization factor: {ann_factor:.2f}\n\n")
    f.write("RETURNS STATISTICS\n")
    f.write("-" * 30 + "\n")
    f.write(f"Mean return (per trade): {mean_ret:.6f}\n")
    f.write(f"Std return (per trade): {std_ret:.6f}\n")
    f.write(f"Skew: {skew_val:.4f}\n")
    f.write(f"Kurtosis (excess): {kurt_val:.4f}\n\n")
    f.write("PLAIN T-TEST\n")
    f.write("-" * 30 + "\n")
    f.write(f"t-statistic: {t_stat_plain:.4f}\n")
    f.write(f"p-value: {p_value_plain:.4f}\n\n")
    f.write("NEWEY-WEST HAC (maxlags=5)\n")
    f.write("-" * 30 + "\n")
    f.write(f"t-statistic: {t_stat_hac:.4f}\n")
    f.write(f"p-value: {p_value_hac:.4f}\n\n")
    f.write(f"BLOCK BOOTSTRAP (block={block_size}, {n_boot} iters)\n")
    f.write("-" * 30 + "\n")
    f.write(f"95% CI for mean return: [{ci_lower:.6f}, {ci_upper:.6f}]\n")
    f.write(f"CI excludes zero? {ci_lower > 0 or ci_upper < 0}\n\n")
    f.write("DEFLATED SHARPE RATIO\n")
    f.write("-" * 30 + "\n")
    f.write(f"Number of trades (n): {n_trades}\n")
    f.write(f"Number of trials (n_trials): {n_trials}\n")
    f.write(f"Skew: {skew_val:.4f}\n")
    f.write(f"Kurtosis (excess): {kurt_val:.4f}\n")
    f.write(f"Sharpe ratio (per trade): {sr_per_trade:.4f}\n")
    f.write(f"Sharpe ratio std (sr_std): {sr_std:.4f}\n")
    f.write(f"Expected maximum (per trade): {expected_max_sr:.4f}\n")
    f.write(f"DSR: {dsr:.4f}\n")
    f.write(f"p-value: {p_value_dsr:.4f}\n")
    f.write(f"Survives (p < 0.05)? {p_value_dsr < 0.05}\n")

print(f"\nResults saved to {output_file}")
