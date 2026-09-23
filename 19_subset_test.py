import pandas as pd
import numpy as np
import os

DATA_DIR = 'data/expanded'
ZSCORE_WINDOW = 30 * 24
ENTRY_Z = 0.8
EXIT_Z = 0.3
MAX_HOLD = 24
MIN_FUNDING = 0.0003
FUND_HOURS = [0, 8, 16]
P_MAKER = 0.70
P_TAKER = 0.20
P_MISSED = 0.05
FEE_MAKER = 0.0003
FEE_TAKER = 0.0005

np.random.seed(42)


def load_assets():
    assets = {}
    for f in sorted(os.listdir(DATA_DIR)):
        if not f.endswith('.parquet'): continue
        name = f.replace('.parquet', '').replace('_USDT_USDT', '')
        df = pd.read_parquet(os.path.join(DATA_DIR, f))
        df = df.sort_values('timestamp').reset_index(drop=True)
        df['fundingRate'] = df['fundingRate'].fillna(0)
        assets[name] = df
    return assets


def compute_zscore(s, w):
    m = s.rolling(w, min_periods=w//2).mean()
    sd = s.rolling(w, min_periods=w//2).std()
    return (s - m) / sd.replace(0, np.nan)


def simulate_cost():
    r = np.random.random()
    if r < P_MISSED: return None
    elif r < P_MISSED + P_MAKER: return FEE_MAKER * 2
    else: return FEE_TAKER * 2


def backtest(df):
    df = df.copy()
    df['z'] = compute_zscore(df['fundingRate'], ZSCORE_WINDOW)
    trades = []
    pos = 0; hh = 0; fp = 0.0
    for i in range(1, len(df)):
        r = df.iloc[i]
        ts = r['timestamp']; z = r['z']; fr = r['fundingRate']
        if pd.isna(z): continue
        if pos != 0 and ts.hour in FUND_HOURS:
            fp += -pos * fr
        if pos != 0:
            hh += 1
            reason = None
            if (pos == -1 and z < EXIT_Z) or (pos == 1 and z > -EXIT_Z):
                reason = 'REVERT'
            elif hh >= MAX_HOLD:
                reason = 'TIMEOUT'
            if reason:
                c = simulate_cost()
                if c is not None:
                    trades.append((fp - c) * 100)
                pos = 0; hh = 0; fp = 0.0
        if pos == 0:
            if z > ENTRY_Z and abs(fr) >= MIN_FUNDING:
                if simulate_cost() is not None:
                    pos = -1; hh = 0; fp = 0.0
            elif z < -ENTRY_Z and abs(fr) >= MIN_FUNDING:
                if simulate_cost() is not None:
                    pos = 1; hh = 0; fp = 0.0
    return trades


def summarize(assets, subset_names, label):
    all_t = []
    for name in subset_names:
        if name in assets:
            all_t.extend(backtest(assets[name]))
    if not all_t:
        print(f"{label}: No trades")
        return
    s = pd.Series(all_t)
    total = s.sum()
    wr = (s > 0).mean() * 100
    tpm = len(s) / 24
    annual = total / 24 * 12
    sharpe = s.mean() / s.std() * np.sqrt(len(s)/2) if s.std() > 0 else 0
    print(f"{label:>18}: {len(s):>5} trd, {tpm:>5.1f}/mo, WR {wr:>5.1f}%, "
          f"PnL {total:>+7.2f}%, PnL/yr {annual:>+6.1f}%, Sharpe {sharpe:>5.2f}")


def main():
    assets = load_assets()
    print(f"Loaded {len(assets)} assets\n")
    print("=" * 90)
    print("SUBSET TEST — Same strategy, different asset selections")
    print("=" * 90)

    subsets = {
        'Top 3 (SEI,APT,FIL)': ['SEI', 'APT', 'FIL'],
        'Top 5 (+ WIF,LINK)': ['SEI', 'APT', 'FIL', 'WIF', 'LINK'],
        'Top 8': ['SEI', 'APT', 'FIL', 'WIF', 'LINK', 'INJ', 'SOL', 'OP'],
        'Original (SOL,DOGE,ARB)': ['SOL', 'DOGE', 'ARB'],
        'Drop Bottom 4': ['SEI', 'APT', 'FIL', 'WIF', 'LINK', 'INJ', 'SOL', 'OP', 'TIA', 'SUI'],
        'All 14': list(assets.keys()),
    }

    print()
    for label, names in subsets.items():
        summarize(assets, names, label)


if __name__ == '__main__':
    main()