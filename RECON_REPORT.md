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

D1. Comparing trade files:

D2. Parameters in strategy files:
src/strategy/multi_asset.py:
11:ENTRY_Z = 1.2
12:EXIT_Z = 0.5
14:MIN_FUNDING_LEVELS = [0.0001, 0.0003, 0.0005, 0.0008, 0.0010]
21:FEE_MAKER = 0.0003   # 0.03% maker per side (problem statement)
22:FEE_TAKER = 0.0005   # 0.05% taker per side
51:        return FEE_MAKER * 2  # maker both sides
53:        return FEE_TAKER * 2  # taker both sides
80:            if (pos == -1 and z < EXIT_Z) or (pos == 1 and z > -EXIT_Z):
98:            if z > ENTRY_Z and abs(fr) >= min_funding:
104:            elif z < -ENTRY_Z and abs(fr) >= min_funding:
116:    print("PHASE 2b: MIN_FUNDING SENSITIVITY")
122:    for mf in MIN_FUNDING_LEVELS:
129:            print(f"MIN_FUNDING={mf:.4f}: No trades")
137:        print(f"MIN_FUNDING={mf:.4f}: {len(tdf):4d} trades, "

src/strategy/funding_basis.py:
9:ENTRY_Z = 1.2
10:EXIT_Z = 0.5
12:MAKER_FEE_PERP = 0.0002
13:MIN_FUNDING = 0.0001   # 0.01% per 8h minimum
55:            if (position == -1 and z < EXIT_Z) or (position == 1 and z > -EXIT_Z):
63:                cost = MAKER_FEE_PERP * 2
82:            if z > ENTRY_Z and abs(funding) >= MIN_FUNDING:
88:            elif z < -ENTRY_Z and abs(funding) >= MIN_FUNDING:
116:        print("\nNo trades. Lower ENTRY_Z to 1.0 and rerun.")

D3. Parameters in 05b_taker_test.py (first 30 lines):
import pandas as pd
import numpy as np

data = pd.read_pickle('data/combined_all.pkl')
data = {k: v for k, v in data.items() if 'SUI' not in k}

ZW = 30 * 24
EZ = 1.2
XZ = 0.5
MH = 24
FEE = 0.0005
FH = [0, 8, 16]
MIN_FUNDING = 0.0001   # 0.01% per 8h minimum

def bt(df, asset):
    df = df.copy()
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df = df.sort_values('timestamp').reset_index(drop=True)
    df['fundingRate'] = df['fundingRate'].fillna(0)
    m = df['fundingRate'].rolling(ZW, min_periods=ZW//2).mean()
    s = df['fundingRate'].rolling(ZW, min_periods=ZW//2).std()
    df['z'] = (df['fundingRate'] - m) / s.replace(0, np.nan)

    t = []
    pos = 0
    hh = 0
    fp = 0.0

    for i in range(1, len(df)):
        r = df.iloc[i]

D4. Parameter sweep combinations:
src/analysis/parameter_sweep.py loop lines:
22:    for f in sorted(os.listdir(DATA_DIR)):
58:    for i in range(1, len(df)):
115:    for ez in entries:
116:        for xz in exits:
117:            for mh in holds:
118:                for mf in min_funds:
120:                    for name, df in assets.items():
160:        for _, r in top.iterrows():
171:        for _, r in pos.head(10).iterrows():

Analyzing parameter_sweep.py:

D5. Walk forward results:
walk_forward/walk_forward_summary.txt:
Walk-Forward Validation Results
==================================================

Window 1:
  Train: 2022-09-01 to 2024-01-01
  Test:  2024-01-01 to 2024-03-01
  Best Parameters: {'OI_THRESHOLD': 1.0, 'FUNDING_LONG_THRESH': -0.0005, 'FUNDING_SHORT_THRESH': 0.003, 'BOOK_LONG_THRESH': 0.6, 'BOOK_SHORT_THRESH': 0.35, 'MIN_CONFLUENCE_SCORE': 2, 'ADX_TREND_THRESH': 30, 'REGIME_CONFIRM_BARS': 2, 'BULL_TP_PCT': 0.006, 'BULL_SL_PCT': 0.005, 'SIDEWAYS_TP_PCT': 0.008, 'SIDEWAYS_SL_PCT': 0.002, 'RISK_PCT_PER_TRADE': 0.005, 'OI_SURGE_THRESH': 1.0, 'BAR_POS_SURGE_LONG': 0.6, 'BAR_POS_SURGE_SHORT': 0.3, 'FUNDING_NEUTRAL': 0.002, 'score': -999, 'net_pnl_pct': 17.576026591614074, 'sharpe_ratio': -0.7622955691520219, 'max_drawdown': 0.09855263684918912, 'win_rate': 0.44018691588785047, 'trades_per_month': 10.979320877761744}
  Test Performance:
    Net PnL %: 10.09%
    Sharpe Ratio: -0.80
    Max Drawdown: 0.00%
    Win Rate: 27.16%
    Total Trades: 81
    Profit Factor: 0.90
    Trades/Month: 3.38

Window 2:
  Train: 2022-09-01 to 2024-03-01
  Test:  2024-03-01 to 2024-05-01
  Best Parameters: {'OI_THRESHOLD': 1.0, 'FUNDING_LONG_THRESH': -0.0005, 'FUNDING_SHORT_THRESH': 0.003, 'BOOK_LONG_THRESH': 0.6, 'BOOK_SHORT_THRESH': 0.35, 'MIN_CONFLUENCE_SCORE': 2, 'ADX_TREND_THRESH': 30, 'REGIME_CONFIRM_BARS': 2, 'BULL_TP_PCT': 0.006, 'BULL_SL_PCT': 0.005, 'SIDEWAYS_TP_PCT': 0.008, 'SIDEWAYS_SL_PCT': 0.002, 'RISK_PCT_PER_TRADE': 0.005, 'OI_SURGE_THRESH': 1.0, 'BAR_POS_SURGE_LONG': 0.6, 'BAR_POS_SURGE_SHORT': 0.3, 'FUNDING_NEUTRAL': 0.002, 'score': -999, 'net_pnl_pct': 17.576026591614074, 'sharpe_ratio': -0.7622955691520219, 'max_drawdown': 0.09855263684918912, 'win_rate': 0.44018691588785047, 'trades_per_month': 10.979320877761744}
  Test Performance:
    Net PnL %: 9.55%
    Sharpe Ratio: -1.49
    Max Drawdown: 0.00%
    Win Rate: 28.97%
    Total Trades: 107
    Profit Factor: 0.83
    Trades/Month: 4.46

Window 3:
  Train: 2022-09-01 to 2024-05-01
  Test:  2024-05-01 to 2024-07-01
  Best Parameters: {'OI_THRESHOLD': 1.0, 'FUNDING_LONG_THRESH': -0.0005, 'FUNDING_SHORT_THRESH': 0.003, 'BOOK_LONG_THRESH': 0.6, 'BOOK_SHORT_THRESH': 0.35, 'MIN_CONFLUENCE_SCORE': 2, 'ADX_TREND_THRESH': 30, 'REGIME_CONFIRM_BARS': 2, 'BULL_TP_PCT': 0.006, 'BULL_SL_PCT': 0.005, 'SIDEWAYS_TP_PCT': 0.008, 'SIDEWAYS_SL_PCT': 0.002, 'RISK_PCT_PER_TRADE': 0.005, 'OI_SURGE_THRESH': 1.0, 'BAR_POS_SURGE_LONG': 0.6, 'BAR_POS_SURGE_SHORT': 0.3, 'FUNDING_NEUTRAL': 0.002, 'score': -999, 'net_pnl_pct': 17.576026591614074, 'sharpe_ratio': -0.7622955691520219, 'max_drawdown': 0.09855263684918912, 'win_rate': 0.44018691588785047, 'trades_per_month': 10.979320877761744}
  Test Performance:
    Net PnL %: 7.67%
    Sharpe Ratio: -1.94
    Max Drawdown: 0.00%
    Win Rate: 18.82%
    Total Trades: 85
    Profit Factor: 0.80
    Trades/Month: 3.54

Window 4:
  Train: 2022-09-01 to 2024-07-01
  Test:  2024-07-01 to 2024-09-01
  Best Parameters: {'OI_THRESHOLD': 1.0, 'FUNDING_LONG_THRESH': -0.0005, 'FUNDING_SHORT_THRESH': 0.003, 'BOOK_LONG_THRESH': 0.6, 'BOOK_SHORT_THRESH': 0.35, 'MIN_CONFLUENCE_SCORE': 2, 'ADX_TREND_THRESH': 30, 'REGIME_CONFIRM_BARS': 2, 'BULL_TP_PCT': 0.006, 'BULL_SL_PCT': 0.005, 'SIDEWAYS_TP_PCT': 0.008, 'SIDEWAYS_SL_PCT': 0.002, 'RISK_PCT_PER_TRADE': 0.005, 'OI_SURGE_THRESH': 1.0, 'BAR_POS_SURGE_LONG': 0.6, 'BAR_POS_SURGE_SHORT': 0.3, 'FUNDING_NEUTRAL': 0.002, 'score': -999, 'net_pnl_pct': 17.576026591614074, 'sharpe_ratio': -0.7622955691520219, 'max_drawdown': 0.09855263684918912, 'win_rate': 0.44018691588785047, 'trades_per_month': 10.979320877761744}
  Test Performance:
    Net PnL %: 6.86%
    Sharpe Ratio: -4.27
    Max Drawdown: 0.00%
    Win Rate: 18.97%
    Total Trades: 58
    Profit Factor: 0.43
    Trades/Month: 2.42


First 20 lines of walk_forward/walk_forward_results.csv:
window,train_start,train_end,test_start,test_end,total_trades,win_rate,net_pnl,net_pnl_pct,sharpe_ratio,max_drawdown,trades_per_month
1,2022-09-01,2024-01-01,2024-01-01,2024-03-01,81,0.2716,-539.81,10.0917,-0.8019,0.0,3.38
2,2022-09-01,2024-03-01,2024-03-01,2024-05-01,107,0.2897,-1884.84,9.5519,-1.4934,0.0,4.46
3,2022-09-01,2024-05-01,2024-05-01,2024-07-01,85,0.1882,-809.89,7.6671,-1.9388,0.0,3.54
4,2022-09-01,2024-07-01,2024-07-01,2024-09-01,58,0.1897,-2152.16,6.8572,-4.2748,0.0,2.42

D6. results_phase2/summary.txt:
Total trades: 1548
Trades/month: 64.5
Win rate: 18.3%
Total PnL: -43.77%
PnL/year: -21.9%

=== CASE DECISION ===
funding_basis_trades.csv total net_pnl_pct: POSITIVE (+62.05%)
results_phase2/multi_asset_trades.csv total net_pnl_pct: NEGATIVE (-43.77%)
=> CASE A: funding_basis_trades.csv has POSITIVE total net_pnl_pct
=> Setting it as the canonical trades file.
