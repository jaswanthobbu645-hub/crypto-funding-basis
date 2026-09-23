import pandas as pd
import numpy as np
import os

DATA_DIR = 'data/expanded'
OUTPUT_DIR = 'results_phase3'
os.makedirs(OUTPUT_DIR, exist_ok=True)

ZSCORE_WINDOW = 30 * 24
FUND_HOURS = [0, 8, 16]
P_MAKER = 0.70
P_TAKER = 0.20
P_MISSED = 0.05  # Lower missed fill rate to 5%
FEE_MAKER = 0.0003
FEE_TAKER = 0.0005

np.random.seed(42)


def load_all_assets():
    assets = {}
    for f in sorted(os.listdir(DATA_DIR)):
        if not f.endswith('.parquet'):
            continue
        name = f.replace('.parquet', '').replace('_USDT_USDT', '')
        df = pd.read_parquet(os.path.join(DATA_DIR, f))
        df = df.sort_values('timestamp').reset_index(drop=True)
        df['fundingRate'] = df['fundingRate'].fillna(0)
        # Precompute zscore
        df['z'] = compute_zscore(df['fundingRate'], ZSCORE_WINDOW)
        assets[name] = df
    return assets


def compute_zscore(series, window):
    m = series.rolling(window, min_periods=window // 2).mean()
    s = series.rolling(window, min_periods=window // 2).std()
    return (series - m) / s.replace(0, np.nan)


def simulate_execution_cost():
    r = np.random.random()
    if r < P_MISSED:
        return None
    elif r < P_MISSED + P_MAKER:
        return FEE_MAKER * 2
    else:
        return FEE_TAKER * 2


def backtest_asset(df, asset_name, entry_z, exit_z, max_hold, min_funding):
    # df already has 'z' column
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
            reason = None
            if (pos == -1 and z < exit_z) or (pos == 1 and z > -exit_z):
                reason = 'REVERT'
            elif hh >= max_hold:
                reason = 'TIMEOUT'

            if reason:
                cost = simulate_execution_cost()
                if cost is not None:
                    trades.append({'net_pnl_pct': (fp - cost) * 100})
                pos = 0
                hh = 0
                fp = 0.0

        if pos == 0:
            if z > entry_z and abs(fr) >= min_funding:
                if simulate_execution_cost() is not None:
                    pos = -1
                    hh = 0
                    fp = 0.0
            elif z < -entry_z and abs(fr) >= min_funding:
                if simulate_execution_cost() is not None:
                    pos = 1
                    hh = 0
                    fp = 0.0

    return trades


def main():
    print("=" * 90)
    print("PHASE 3: PARAMETER SWEEP")
    print("=" * 90)

    assets = load_all_assets()
    print(f"Loaded {len(assets)} assets\n")

    entries = [0.8, 1.0, 1.2, 1.5]
    exits = [0.2, 0.3, 0.5]
    holds = [12, 24, 48]
    min_funds = [0.0003, 0.0005, 0.0008]

    results = []

    for ez in entries:
        for xz in exits:
            for mh in holds:
                for mf in min_funds:
                    all_trades = []
                    for name, df in assets.items():
                        t = backtest_asset(df, name, ez, xz, mh, mf)
                        all_trades.extend(t)

                    if not all_trades:
                        continue

                    tdf = pd.DataFrame(all_trades)
                    total = tdf['net_pnl_pct'].sum()
                    wr = (tdf['net_pnl_pct'] > 0).mean() * 100
                    tpm = len(tdf) / 24
                    annual = total / 24 * 12

                    results.append({
                        'entry_z': ez,
                        'exit_z': xz,
                        'max_hold': mh,
                        'min_funding': mf,
                        'trades': len(tdf),
                        'trades_per_month': tpm,
                        'win_rate': wr,
                        'total_pnl': total,
                        'annual_pnl': annual,
                    })

    rdf = pd.DataFrame(results)
    rdf.to_csv(os.path.join(OUTPUT_DIR, 'sweep_results.csv'), index=False)

    # Filter: >= 20 trades/month AND positive PnL/year
    viable = rdf[(rdf['trades_per_month'] >= 20) & (rdf['annual_pnl'] > 0)]

    print(f"Total combinations tested: {len(rdf)}")
    print(f"Viable combinations (trades/mo >= 20 AND PnL/year > 0): {len(viable)}")
    print()

    if len(viable) > 0:
        viable = viable.sort_values('annual_pnl', ascending=False)
        print("TOP 10 VIABLE COMBINATIONS:")
        print("-" * 90)
        top = viable.head(10)
        for _, r in top.iterrows():
            print(f"EZ={r['entry_z']:.1f} XZ={r['exit_z']:.1f} MH={r['max_hold']:>2} "
                  f"MF={r['min_funding']:.4f} | "
                  f"{r['trades_per_month']:>5.1f}/mo, "
                  f"WR {r['win_rate']:>5.1f}%, "
                  f"PnL/yr {r['annual_pnl']:>+6.1f}%")
    else:
        print("NO viable combinations found.")
        print()
        print("Closest to viable (sorted by trades/month descending, PnL > 0):")
        pos = rdf[rdf['annual_pnl'] > 0].sort_values('trades_per_month', ascending=False)
        for _, r in pos.head(10).iterrows():
            print(f"EZ={r['entry_z']:.1f} XZ={r['exit_z']:.1f} MH={r['max_hold']:>2} "
                  f"MF={r['min_funding']:.4f} | "
                  f"{r['trades_per_month']:>5.1f}/mo, "
                  f"WR {r['win_rate']:>5.1f}%, "
                  f"PnL/yr {r['annual_pnl']:>+6.1f}%")


if __name__ == '__main__':
    main()