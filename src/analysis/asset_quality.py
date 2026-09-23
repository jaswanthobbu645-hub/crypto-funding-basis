import pandas as pd
import numpy as np
import os

DATA_DIR = 'data/expanded'
OUTPUT_DIR = 'results_quality'
os.makedirs(OUTPUT_DIR, exist_ok=True)

ZSCORE_WINDOW = 30 * 24
ENTRY_Z = 0.8
EXIT_Z = 0.3
MAX_HOLD = 24
MIN_FUNDING = 0.0003
FUND_HOURS = [0, 8, 16]
FEE = 0.0006  # maker round-trip


def load_all_assets():
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
    m = series.rolling(window, min_periods=window // 2).mean()
    s = series.rolling(window, min_periods=window // 2).std()
    return (series - m) / s.replace(0, np.nan)


def backtest_asset(df):
    df = df.copy()
    df['z'] = compute_zscore(df['fundingRate'], ZSCORE_WINDOW)

    trades = []
    pos = 0; hh = 0; fp = 0.0

    for i in range(1, len(df)):
        r = df.iloc[i]
        ts = r['timestamp']
        z = r['z']
        fr = r['fundingRate']
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
            if z > ENTRY_Z and abs(fr) >= MIN_FUNDING:
                pos = -1; hh = 0; fp = 0.0
            elif z < -ENTRY_Z and abs(fr) >= MIN_FUNDING:
                pos = 1; hh = 0; fp = 0.0
    return trades


def main():
    assets = load_all_assets()
    print(f"Loaded {len(assets)} assets")
    print()
    print(f"{'Asset':>8} {'Trades':>8} {'WR%':>7} {'TotalPnL%':>11} {'Sharpe':>8} {'Score':>8}")
    print("-" * 60)

    scores = []
    for name, df in assets.items():
        t = backtest_asset(df)
        if len(t) < 5:
            continue
        s = pd.Series(t)
        wr = (s > 0).mean()
        total = s.sum()
        if s.std() > 0:
            sharpe = s.mean() / s.std() * np.sqrt(len(s) / 2)
        else:
            sharpe = 0
        # Score: WR * total / vol
        score = wr * total / (s.std() + 1e-6)
        scores.append({
            'asset': name,
            'trades': len(s),
            'wr': wr * 100,
            'total_pnl': total,
            'sharpe': sharpe,
            'score': score
        })
        print(f"{name:>8} {len(s):>8} {wr*100:>7.1f} {total:>11.2f} {sharpe:>8.2f} {score:>8.2f}")

    sdf = pd.DataFrame(scores).sort_values('score', ascending=False)
    sdf.to_csv(os.path.join(OUTPUT_DIR, 'asset_ranking.csv'), index=False)

    print()
    print("=" * 60)
    print("TOP 5 ASSETS BY QUALITY SCORE")
    print("=" * 60)
    top5 = sdf.head(5)
    for _, r in top5.iterrows():
        print(f"{r['asset']:>8}: WR {r['wr']:.1f}%, Sharpe {r['sharpe']:.2f}, Score {r['score']:.2f}")

    print()
    print("BOTTOM 5 ASSETS (to avoid):")
    for _, r in sdf.tail(5).iterrows():
        print(f"{r['asset']:>8}: WR {r['wr']:.1f}%, Sharpe {r['sharpe']:.2f}, Score {r['score']:.2f}")


if __name__ == '__main__':
    main()