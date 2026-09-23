import pandas as pd
import numpy as np
import os

DATA_DIR = 'data/expanded'
OUTPUT_DIR = 'results_atr'
os.makedirs(OUTPUT_DIR, exist_ok=True)

ZSCORE_WINDOW = 30 * 24
ENTRY_Z = 0.8
EXIT_Z = 0.3
MAX_HOLD = 24
MIN_FUNDING = 0.0003
FUND_HOURS = [0, 8, 16]
FEE = 0.0006
ATR_PERIOD = 14
ATR_RANK_WINDOW = 30 * 24


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


def compute_atr(df, period=14):
    high, low, close = df['high'], df['low'], df['close']
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def compute_zscore(series, window):
    m = series.rolling(window, min_periods=window//2).mean()
    s = series.rolling(window, min_periods=window//2).std()
    return (series - m) / s.replace(0, np.nan)


def backtest(df, use_filter):
    df = df.copy()
    df['z'] = compute_zscore(df['fundingRate'], ZSCORE_WINDOW)
    if use_filter:
        df['atr'] = compute_atr(df, ATR_PERIOD)
        df['atr_pct'] = df['atr'] / df['close']
        df['atr_rank'] = df['atr_pct'].rolling(ATR_RANK_WINDOW, min_periods=ATR_RANK_WINDOW//2).rank(pct=True)

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
                trades.append((fp - FEE) * 100)
                pos = 0; hh = 0; fp = 0.0
        if pos == 0:
            if use_filter:
                ar = r.get('atr_rank', np.nan)
                if pd.notna(ar) and ar < 0.5:
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
    print(f"{label}: {len(s):>5} trades, {tpm:>5.1f}/mo, WR {wr:>5.1f}%, "
          f"PnL {total:>+7.2f}%, PnL/yr {annual:>+6.1f}%, Sharpe {sharpe:>5.2f}")


def main():
    print("=" * 80)
    print("ATR REGIME FILTER TEST")
    print("=" * 80)
    assets = load_assets()
    print(f"Loaded {len(assets)} assets\n")

    no_atr = [backtest(df, use_filter=False) for df in assets.values()]
    summarize(no_atr, "No ATR filter  ")

    with_atr = [backtest(df, use_filter=True) for df in assets.values()]
    summarize(with_atr, "With ATR filter")

    print()
    print("Per-asset comparison:")
    print(f"{'Asset':>8} {'No-Filter':>12} {'With-Filter':>14}")
    print("-" * 40)
    for name, df in assets.items():
        t1 = backtest(df, use_filter=False)
        t2 = backtest(df, use_filter=True)
        s1 = sum(t1) if t1 else 0
        s2 = sum(t2) if t2 else 0
        print(f"{name:>8} {len(t1):>3} trd {s1:>+6.2f}% {len(t2):>3} trd {s2:>+6.2f}%")


if __name__ == '__main__':
    main()