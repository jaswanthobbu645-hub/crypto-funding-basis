import pandas as pd
import numpy as np

DATA_FILE = 'data/combined_all.pkl'

# Drop SUI (duplicate data)
data = pd.read_pickle(DATA_FILE)
data = {k: v for k, v in data.items() if 'SUI' not in k}

ZSCORE_WINDOW = 30 * 24
ENTRY_Z = 1.2
EXIT_Z = 0.5
MAX_HOLD = 24
TAKER_FEE = 0.0005  # 0.05% taker (both sides)
FUND_HOURS = [0, 8, 16]


def backtest(df, asset):
    df = df.copy()
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df = df.sort_values('timestamp').reset_index(drop=True)
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
                cost = TAKER_FEE * 2
                trades.append({
                    'asset': asset,
                    'net_pnl_pct': (fp - cost) * 100,
                    'hours': hh,
                    'reason': exit_reason,
                })
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


all_t = []
for asset, df in data.items():
    t = backtest(df, asset)
    all_t.extend(t)
    if t:
        total = sum(x['net_pnl_pct'] for x in t)
        wr = sum(1 for x in t if x['net_pnl_pct'] > 0) / len(t) * 100
        print(f'{asset}: {len(t)} trades, WR {wr:.1f}%, PnL {total:+.2f}%')

tdf = pd.DataFrame(all_t)
print()
print('=' * 50)
print('TAKER FEE RESULTS (0.05% per side)')
print('=' * 50)
print(f'Total trades: {len(tdf)}')
print(f'Trades/month: {len(tdf) / 24:.1f}')
print(f'Win rate: {(tdf["net_pnl_pct"] > 0).mean() * 100:.1f}%')
print(f'Total PnL: {tdf["net_pnl_pct"].sum():+.2f}%')
print(f'PnL/month: {tdf["net_pnl_pct"].sum() / 24:+.2f}%')
print(f'PnL/year: {tdf["net_pnl_pct"].sum() / 24 * 12:+.1f}%')


if __name__ == '__main__':
    pass  # already ran above