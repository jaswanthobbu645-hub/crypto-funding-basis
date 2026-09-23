import pandas as pd
import numpy as np

# From 19_subset_test.py results (All 14 assets):
UNLEVERED_PNL_PER_YEAR = 6.6  # percent
SHARPE = 2.87

# India risk-free rate
INDIAN_RISK_FREE = 7.0

# After 30% crypto tax
TAX_RATE = 0.30

print("=" * 80)
print("LEVERAGE ANALYSIS — Indian Investor Perspective")
print("=" * 80)
print()
print(f"Unlevered PnL/year:      {UNLEVERED_PNL_PER_YEAR:+.2f}%")
print(f"Sharpe ratio:            {SHARPE:.2f}")
print(f"India risk-free (G-Sec): {INDIAN_RISK_FREE:.2f}%")
print(f"Crypto tax rate:         {TAX_RATE*100:.0f}%")
print()

print("=" * 80)
print("RETURN AT DIFFERENT LEVERAGE LEVELS")
print("=" * 80)
print()
print(f"{'Leverage':>10} {'Pre-Tax':>10} {'Post-Tax':>10} {'vs G-Sec':>12} {'Verdict':>12}")
print("-" * 60)

for lev in [1, 2, 3, 5, 8, 10]:
    pre_tax = UNLEVERED_PNL_PER_YEAR * lev
    post_tax = pre_tax * (1 - TAX_RATE) if pre_tax > 0 else pre_tax
    delta = post_tax - INDIAN_RISK_FREE
    
    if post_tax > INDIAN_RISK_FREE * 1.5:
        verdict = "EXCELLENT"
    elif post_tax > INDIAN_RISK_FREE:
        verdict = "WORTH IT"
    elif post_tax > 0:
        verdict = "MARGINAL"
    else:
        verdict = "USELESS"
    
    print(f"{lev:>9}x {pre_tax:>+9.1f}% {post_tax:>+9.1f}% {delta:>+11.1f}% {verdict:>12}")

print()
print("=" * 80)
print("LEVERAGE RISK ANALYSIS")
print("=" * 80)
print()
print("At 5x leverage:")
print("  - Position size = 5x capital")
print("  - Implied volatility of strategy = ???")
print("  - Probability of 20% adverse move = ???")
print()
print("Liquidation threshold at 5x:")
print("  - Exchange margin requirement = ~10%")
print("  - Adverse move to liquidation = 10% / 5 = 2%")
print("  - Since delta-neutral, adverse move has 0 impact on P&L")
print("  - BUT: If funding flips and stays negative, you bleed margin")
print()
print("Realistic safe leverage for delta-neutral: 3-5x")
print("Aggressive leverage: 8-10x (higher risk of exchange liquidation)")
print()
print("=" * 80)
print("RECOMMENDATION")
print("=" * 80)
print()
print("For Indian investor:")
print("  - Unlevered: NOT WORTH IT (below 7% G-Sec)")
print("  - At 5x: WORTH IT (post-tax +23%, Sharpe-adjusted return excellent)")
print("  - At 3x: MARGINAL (post-tax +14%, above G-Sec but thin margin)")
print()
print("For international HFT fund:")
print("  - Sharpe 2.87 is the metric that matters")
print("  - US risk-free is ~5%")
print("  - Strategy is viable unlevered for institutional capital")