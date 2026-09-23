import pandas as pd
import numpy as np

DATA_FILE = 'data/combined_all.pkl'

data = pd.read_pickle(DATA_FILE)
data = {k: v for k, v in data.items() if 'SUI' not in k}

ZSCORE_WINDOW = 30 * 24
ENTRY_Z = 1.2
EXIT_Z = 0.5
MAX_HOLD = 24
FEE = 0.0002
FUND_HOURS = [0, 8, 16]


def backtest(df, asset, start_date=None, end_date=None):
    df = df.copy()
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df = df.sort_values('timestamp').reset_index(drop=True)

    if start_date is not None:
        df = df[df['timestamp'] >= start_date]
    if end_date is not None:
        df = df[df['timestamp'] <= end_date]

    df = df.reset_index(drop=True)
    if len(df) < ZSCORE_WINDOW:
        return []

    df['fundingRate'] = df['fundingRate'].fillna(0)
    m = df['fundingRate'].rolling(ZSCORE_WINDOW, min_periods=ZSCORE_WINDOW // 2).mean()
    s = df['fundingRate'].rolling(ZSCORE_WINDOW, min_periods=ZSCORE_WINDOW // 2).std()
    df['z'] = (df['fundingRate'] - m) / s.replace(0, np.nan)

    trades = []
    pos = 0
    hh = 0
    fp = 0.0

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
            exit_reason = None
            if (pos == -1 and z < EXIT_Z) or (pos == 1 and z > -EXIT_Z):
                exit_reason = 'REVERT'
            elif hh >= MAX_HOLD:
                exit_reason = 'TIMEOUT'

            if exit_reason:
                cost = FEE * 2
                trades.append({'asset': asset, 'net_pnl_pct': (fp - cost) * 100})
                pos = 0
                hh = 0
                fp = 0.0

        if pos == 0:
            if z > ENTRY_Z:
                pos = -1
                hh = 0
                fp = 0.0
            elif z < -ENTRY_Z:
                pos = 1
                hh = 0
                fp = 0.0
    return trades


# Walk-forward: 6-month train, 3-month test, roll by 3 months
# Data is Sep 2022 to Sep 2024 (24 months)
windows = [
    ('2023-03-01', '2023-06-01'),
    ('2023-06-01', '2023-09-01'),
    ('2023-09-01', '2023-12-01'),
    ('2023-12-01', '2024-03-01'),
    ('2024-03-01', '2024-06-01'),
    ('2024-06-01', '2024-09-01'),
]

print('=' * 70)
print('WALK-FORWARD VALIDATION')
print('=' * 70)
print()

for start, end in windows:
    all_t = []
    for asset, df in data.items():
        t = backtest(df, asset, start, end)
        all_t.extend(t)

    tdf = pd.DataFrame(all_t)
    if len(tdf) == 0:
        print(f'{start} to {end}: No trades')
        continue

    total_pnl = tdf['net_pnl_pct'].sum()
    wr = (tdf['net_pnl_pct'] > 0).mean() * 100
    print(f'{start} to {end}: {len(tdf)} trades, WR {wr:.1f}%, PnL {total_pnl:+.2f}%')