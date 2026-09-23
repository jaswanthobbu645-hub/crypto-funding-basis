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
                t.append({'asset': asset, 'net': (fp - FEE*2) * 100})
                pos = 0; hh = 0; fp = 0.0
        if pos == 0:
            if r['z'] > EZ and abs(r['fundingRate']) >= MIN_FUNDING: pos = -1; hh = 0; fp = 0.0
            elif r['z'] < -EZ and abs(r['fundingRate']) >= MIN_FUNDING: pos = 1; hh = 0; fp = 0.0
    return t

all_t = []
for a, df in data.items():
    t = bt(df, a)
    all_t.extend(t)
    if t:
        print(f'{a}: {len(t)} trades, PnL {sum(x["net"] for x in t):+.2f}%')

tdf = pd.DataFrame(all_t)
print()
print('TAKER FEE RESULTS (0.05% per side)')
print(f'Total trades: {len(tdf)}')
print(f'Trades/month: {len(tdf)/24:.1f}')
print(f'Win rate: {(tdf["net"]>0).mean()*100:.1f}%')
print(f'Total PnL: {tdf["net"].sum():+.2f}%')
print(f'PnL/year: {tdf["net"].sum()/24*12:+.1f}%')