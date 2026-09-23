import pandas as pd
import numpy as np
import os

DATA_DIR = 'data/expanded'
OUTPUT_DIR = 'results_phase2b'
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Strategy parameters
ZSCORE_WINDOW = 30 * 24
ENTRY_Z = 1.2
EXIT_Z = 0.5
MAX_HOLD = 24
MIN_FUNDING_LEVELS = [0.0001, 0.0003, 0.0005, 0.0008, 0.0010]
FUND_HOURS = [0, 8, 16]

# Realistic execution model
P_MAKER = 0.70       # 70% maker fills
P_TAKER = 0.20       # 20% taker fills
P_MISSED = 0.10      # 10% missed (no trade)
FEE_MAKER = 0.0003   # 0.03% maker per side (problem statement)
FEE_TAKER = 0.0005   # 0.05% taker per side

np.random.seed(42)


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


def simulate_execution_cost():
    """Randomly decide maker/taker/missed for one round-trip."""
    r = np.random.random()
    if r < P_MISSED:
        return None  # trade missed
    elif r < P_MISSED + P_MAKER:
        return FEE_MAKER * 2  # maker both sides
    else:
        return FEE_TAKER * 2  # taker both sides


def backtest_asset_with_threshold(df, asset_name, min_funding):
    df = df.copy()
    df['z'] = compute_zscore(df['fundingRate'], ZSCORE_WINDOW)

    trades = []
    pos = 0
    hh = 0
    fp = 0.0
    entry_time = None

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
            reason = None
            if (pos == -1 and z < EXIT_Z) or (pos == 1 and z > -EXIT_Z):
                reason = 'REVERT'
            elif hh >= MAX_HOLD:
                reason = 'TIMEOUT'

            if reason:
                cost = simulate_execution_cost()
                if cost is not None:
                    net = (fp - cost) * 100
                    trades.append({
                        'asset': asset_name,
                        'net_pnl_pct': net,
                    })
                pos = 0
                hh = 0
                fp = 0.0

        if pos == 0:
            if z > ENTRY_Z and abs(fr) >= min_funding:
                if simulate_execution_cost() is not None:
                    pos = -1
                    hh = 0
                    fp = 0.0
                    entry_time = ts
            elif z < -ENTRY_Z and abs(fr) >= min_funding:
                if simulate_execution_cost() is not None:
                    pos = 1
                    hh = 0
                    fp = 0.0
                    entry_time = ts

    return trades


def main():
    print("=" * 70)
    print("PHASE 2b: MIN_FUNDING SENSITIVITY")
    print("=" * 70)

    assets = load_all_assets()
    print(f"Loaded {len(assets)} assets\n")

    for mf in MIN_FUNDING_LEVELS:
        all_trades = []
        for name, df in assets.items():
            t = backtest_asset_with_threshold(df, name, mf)
            all_trades.extend(t)
        
        if not all_trades:
            print(f"MIN_FUNDING={mf:.4f}: No trades")
            continue
        
        tdf = pd.DataFrame(all_trades)
        total = tdf['net_pnl_pct'].sum()
        wr = (tdf['net_pnl_pct'] > 0).mean() * 100
        tpm = len(tdf) / 24
        
        print(f"MIN_FUNDING={mf:.4f}: {len(tdf):4d} trades, "
              f"{tpm:5.1f}/mo, WR {wr:5.1f}%, "
              f"PnL {total:+7.2f}%, "
              f"PnL/year {total/24*12:+6.1f}%")


if __name__ == '__main__':
    main()