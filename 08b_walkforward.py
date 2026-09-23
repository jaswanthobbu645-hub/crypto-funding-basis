import pandas as pd
import numpy as np

data = pd.read_pickle('data/combined_all.pkl')
data = {k: v for k, v in data.items() if 'SUI' not in k}

ZW = 30 * 24
EZ = 1.2
XZ = 0.5
MH = 24
FEE = 0.0002
FH = [0, 8, 16]

def bt(df, asset, start, end):
    df = df.copy()
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df = df.sort_values('timestamp').reset_index(drop=True)
    df = df[(df['timestamp'] >= start) & (df['timestamp'] <= end)].reset_index(drop=True)
    if len(df) < ZW: return []
    df['fundingRate'] = df['fundingRate'].fillna(0)
    m = df['fundingRate'].rolling(ZW, min_periods=ZW//2).mean()
    s = df['fundingRate'].rolling(ZW, min_periods=ZW//2).std()
    df['z'] = (df['fundingRate'] - m) / s.replace(0, np.nan)

    t = []
    pos = 0; hh = 0; fp = 0.0
    for i in range(1, len(df)):
        r = df.iloc[i]
        if pd.isna(r['z']): continue
        if pos != 0 and r['timestamp'].hour in FH:
            fp += -pos * r['fundingRate']
        if pos != 0:
            hh += 1
            er = None
            if (pos == -1 and r['z'] < XZ) or (pos == 1 and r['z'] > -XZ):
                er = 'REVERT'
            elif hh >= MH:
                er = 'TIMEOUT'
            if er:
                t.append({'net': (fp - FEE*2) * 100})
                pos = 0; hh = 0; fp = 0.0
        if pos == 0:
            if r['z'] > EZ: pos = -1; hh = 0; fp = 0.0
            elif r['z'] < -EZ: pos = 1; hh = 0; fp = 0.0
    return t

windows = [
    ('2023-03-01','2023-06-01'),
    ('2023-06-01','2023-09-01'),
    ('2023-09-01','2023-12-01'),
    ('2023-12-01','2024-03-01'),
    ('2024-03-01','2024-06-01'),
    ('2024-06-01','2024-09-01'),
]

print('WALK-FORWARD VALIDATION')
for start, end in windows:
    all_t = []
    for a, df in data.items():
        all_t.extend(bt(df, a, start, end))
    tdf = pd.DataFrame(all_t)
    if len(tdf) == 0:
        print(f'{start} to {end}: No trades')
        continue
    print(f'{start} to {end}: {len(tdf)} trades, WR {(tdf["net"]>0).mean()*100:.1f}%, PnL {tdf["net"].sum():+.2f}%')