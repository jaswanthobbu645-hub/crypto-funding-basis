A) Repo state:
git log --oneline | head -30:
8dc1115 refactor: move data fetchers into src/data/
eb374b0 refactor: move analysis scripts into src/analysis/
a72cdf0 refactor: move strategy code into src/strategy/
1f7f306 chore: create professional folder structure
8626d75 chore: archive debug and backup files to archive/
b0d9436 v2.0.0: Funding Rate Basis Harvest with leverage analysis

git tag:
v2.0.0

Full directory tree (src/, results_phase2/, data/, tests/, walk_forward/):
src/
src/analysis/.gitkeep
src/analysis/asset_quality.py
src/analysis/atr_regime.py
src/analysis/parameter_sweep.py
src/analysis/subset_test.py
src/analysis/volume_momentum.py
src/data/.gitkeep
src/data/download_expanded.py
src/data/download_original.py
src/strategy/.gitkeep
src/strategy/funding_basis.py
src/strategy/funding_basis_taker.py
src/strategy/leverage_analysis.py
src/strategy/multi_asset.py

results_phase2/
results_phase2/multi_asset_trades.csv
results_phase2/summary.txt

data/
data/ARB_USDT_PERP_2y.csv
data/combined_all.pkl
data/DOGE_USDT_PERP_2y.csv
data/expanded/APT_USDT_USDT.parquet
data/expanded/ARB_USDT_USDT.parquet
data/expanded/AVAX_USDT_USDT.parquet
data/expanded/DOGE_USDT_USDT.parquet
data/expanded/FIL_USDT_USDT.parquet
data/expanded/INJ_USDT_USDT.parquet
data/expanded/LINK_USDT_USDT.parquet
data/expanded/NEAR_USDT_USDT.parquet
data/expanded/OP_USDT_USDT.parquet
data/expanded/SEI_USDT_USDT.parquet
data/expanded/SOL_USDT_USDT.parquet
data/expanded/SUI_USDT_USDT.parquet
data/expanded/TIA_USDT_USDT.parquet
data/expanded/WIF_USDT_USDT.parquet
data/processed_all.pkl
data/SOL_USDT_PERP_2y.csv
data/SUI_USDT_PERP_2y.csv

tests/
tests/.gitkeep

walk_forward/
walk_forward/walk_forward_results.csv
walk_forward/walk_forward_summary.csv
walk_forward/walk_forward_summary.txt
walk_forward/window_results.json

B) Trade data:
ls results_phase2/:
total 189
drwxr-xr-x 1 Avinash 197121      0 Sep 22 23:41 .
drwxr-xr-x 1 Avinash 197121      0 Sep 23 21:31 ..
-rw-r--r-- 1 Avinash 197121 149804 Sep 22 23:42 multi_asset_trades.csv
-rw-r--r-- 1 Avinash 197121     95 Sep 22 23:42 summary.txt

ls *.csv in root:
-rw-r--r-- 1 Avinash 197121  21339 Sep 20 23:57 equity_curve.csv
-rw-r--r-- 1 Avinash 197121  70654 Sep 23 01:07 funding_basis_trades.csv
-rw-r--r-- 1 Avinash 197121 162288 Sep 20 23:57 trades_log.csv

Main trades CSV: results_phase2/multi_asset_trades.csv
Exact header row:
asset,entry_time,exit_time,direction,hours_held,funding_pnl_pct,cost_pct,net_pnl_pct,exit_reason

Shape and describe (using python):
df.shape: (1548, 9)
df["net_pnl_pct"].describe():
count    1548.000000
mean       -0.028275
std         0.067496
min        -0.160065
25%        -0.062640
50%        -0.040560
75%        -0.016280
max         0.674611
Name: net_pnl_pct, dtype: float64

Timestamp columns:
Time columns: ['entry_time', 'exit_time']
entry_time: min=2024-10-07 18:00:00, max=2026-09-14 16:00:00
exit_time: min=2024-10-08 00:00:00, max=2026-09-15 16:00:00

Compute trades per month:
Number of trades: 1548
Date range: 706 days (23.53 months)
Trades per month: 65.78

C) Code vs docs mismatch check:
grep -n "ENTRY_Z\|EXIT_Z\|MIN_FUNDING" in src/ and root .py files:
05b_taker_test.py:13:MIN_FUNDING = 0.0001   # 0.01% per 8h minimum
05b_taker_test.py:45:            if r['z'] > EZ and abs(r['fundingRate']) >= MIN_FUNDING: pos = -1; hh = 0; fp = 0.0
05b_taker_test.py:46:            elif r['z'] < -EZ and abs(r['fundingRate']) >= MIN_FUNDING: pos = 1; hh = 0; fp = 0.0
08b_walkforward_funding.py:10:ENTRY_Z = 1.2
08b_walkforward_funding.py:11:EXIT_Z = 0.5
08b_walkforward_funding.py:55:            if (pos == -1 and z < EXIT_Z) or (pos == 1 and z > -EXIT_Z):
08b_walkforward_funding.py:68:            if z > ENTRY_Z:
08b_walkforward_funding.py:72:            elif z < -ENTRY_Z:

grep -n "0.8\|0.3\|1.2\|0.5" README.md STRATEGY_SPEC.md:
README.md:18:When funding rate Z-score exceeds ±0.8, go delta-neutral:
README.md:19:- SHORT perp + LONG spot when Z > +0.8
README.md:20:- LONG perp + SHORT spot when Z < -0.8
STRATEGY_SPEC.md:25:- Z-score > +0.8
STRATEGY_SPEC.md:29:- Z-score < -0.8
STRATEGY_SPEC.md:36:- Z-score reverts to ±0.3 (signal invalidation)


D) Optimization trial count:
Find every script that loops over parameter grids (EZ, XZ, MF, etc.)
Scripts that likely contain parameter grids:
./05b_taker_test.py
./08b_walkforward.py
./archive/make_report.py
./archive/test_sweep.py
./config.py
./src/analysis/parameter_sweep.py

Now, we need to count the total number of parameter combinations tested.
Examining src/analysis/parameter_sweep.py:

E) Data availability:
ls data/expanded/ — list parquet files
total 8532
drwxr-xr-x 1 Avinash 197121      0 Sep 22 23:30 .
drwxr-xr-x 1 Avinash 197121      0 Sep 22 23:12 ..
-rw-r--r-- 1 Avinash 197121 716094 Sep 22 23:30 APT_USDT_USDT.parquet
-rw-r--r-- 1 Avinash 197121 583712 Sep 22 23:29 ARB_USDT_USDT.parquet
-rw-r--r-- 1 Avinash 197121 629925 Sep 22 23:29 AVAX_USDT_USDT.parquet
-rw-r--r-- 1 Avinash 197121 787715 Sep 22 23:29 DOGE_USDT_USDT.parquet
-rw-r--r-- 1 Avinash 197121 506948 Sep 22 23:30 FIL_USDT_USDT.parquet
-rw-r--r-- 1 Avinash 197121 601588 Sep 22 23:30 INJ_USDT_USDT.parquet
-rw-r--r-- 1 Avinash 197121 616749 Sep 22 23:29 LINK_USDT_USDT.parquet
-rw-r--r-- 1 Avinash 197121 474567 Sep 22 23:30 NEAR_USDT_USDT.parquet
-rw-r--r-- 1 Avinash 197121 613601 Sep 22 23:30 OP_USDT_USDT.parquet
-rw-r--r-- 1 Avinash 197121 562199 Sep 22 23:30 SEI_USDT_USDT.parquet
-rw-r--r-- 1 Avinash 197121 602776 Sep 22 23:29 SOL_USDT_USDT.parquet
-rw-r--r-- 1 Avinash 197121 695038 Sep 22 23:29 SUI_USDT_USDT.parquet
-rw-r--r-- 1 Avinash 197121 671006 Sep 22 23:30 TIA_USDT_USDT.parquet
-rw-r--r-- 1 Avinash 197121 644308 Sep 22 23:30 WIF_USDT_USDT.parquet

For one file, print columns and date range:
Using file: data/expanded/APT_USDT_USDT.parquet
Columns: ['timestamp', 'open', 'high', 'low', 'close', 'volume', 'fundingRate']
Date range:
min: 2024-09-22 19:00:00
max: 2026-09-22 18:00:00
