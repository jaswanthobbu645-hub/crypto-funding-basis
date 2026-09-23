import pandas as pd
import numpy as np
import os

DATA_DIR = 'data/expanded'
ZSCORE_WINDOW = 30 * 24
VOL_WINDOW = 24 * 7
ENTRY_Z = 0.8
EXIT_Z = 0.3
MAX_HOLD = 24
MIN_FUNDING = 0.0003
FUND_HOURS = [0, 8, 16]
FEE = 0.0006


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


def compute_zscore(series, window):
    m = series.rolling(window, min_periods=window//2).mean()
    s = series.rolling(window, min_periods=window//2).std()
    return (series - m) / s.replace(0, np.nan)


def backtest(df, volume_filter, momentum_filter):
    df = df.copy()
    df['z'] = compute_zscore(df['fundingRate'], ZSCORE_WINDOW)
    df['vol_z'] = compute_zscore(df['volume'], VOL_WINDOW)
    df['ret_4h'] = df['close'].pct_change(4)

    trades = []
    pos = 0; hh = 0; fp = 0.0

    for i in range(1, len(df)):
        r = df.iloc[i]
        ts = r['timestamp']; z = r['z']; fr = r['fundingRate']
        vz = r['vol_z']; r4 = r['ret_4h']
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
                trades.append((fp - FEE) * 100)
                pos = 0; hh = 0; fp = 0.0
        if pos == 0:
            # Volume confirmation
            if volume_filter and (pd.isna(vz) or vz < 0):
                continue
            # Momentum: if shorting (z>0), price should be falling or flat
            if momentum_filter and pd.notna(r4):
                if z > ENTRY_Z and r4 > 0.005:  # short signal but price rising
                    continue
                if z < -ENTRY_Z and r4 < -0.005:  # long signal but price falling
                    continue
            if z > ENTRY_Z and abs(fr) >= MIN_FUNDING:
                pos = -1; hh = 0; fp = 0.0
            elif z < -ENTRY_Z and abs(fr) >= MIN_FUNDING:
                pos = 1; hh = 0; fp = 0.0
    return trades


def summarize(trades_list, label):
    all_t = []
    for t in trades_list: all_t.extend(t)
    if not all_t:
        print(f"{label}: No trades")
        return
    s = pd.Series(all_t)
    total = s.sum()
    wr = (s > 0).mean() * 100
    tpm = len(s) / 24
    annual = total / 24 * 12
    sharpe = s.mean() / s.std() * np.sqrt(len(s)/2) if s.std() > 0 else 0
    print(f"{label}: {len(s):>5} trd, {tpm:>5.1f}/mo, WR {wr:>5.1f}%, "
          f"PnL {total:>+7.2f}%, PnL/yr {annual:>+6.1f}%, Sharpe {sharpe:>5.2f}")


def main():
    print("=" * 80)
    print("VOLUME + MOMENTUM FILTER TEST")
    print("=" * 80)
    assets = load_assets()
    print(f"Loaded {len(assets)} assets\n")

    summarize([backtest(df, False, False) for df in assets.values()], "Baseline         ")
    summarize([backtest(df, True, False) for df in assets.values()], "+ Volume filter  ")
    summarize([backtest(df, False, True) for df in assets.values()], "+ Momentum filter")
    summarize([backtest(df, True, True) for df in assets.values()], "+ Both filters   ")


if __name__ == '__main__':
    main()