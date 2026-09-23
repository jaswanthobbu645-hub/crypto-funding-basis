import pandas as pd
import numpy as np

DATA_FILE = 'data/combined_all.pkl'
OUTPUT_FILE = 'funding_basis_trades.csv'
SUMMARY_FILE = 'funding_basis_summary.txt'

ZSCORE_WINDOW = 30 * 24
ENTRY_Z = 1.2
EXIT_Z = 0.5
MAX_HOLD_HOURS = 24
MAKER_FEE_PERP = 0.0002
MIN_FUNDING = 0.0001   # 0.01% per 8h minimum

FUNDING_HOURS = [0, 8, 16]


def compute_funding_zscore(series, window):
    mean = series.rolling(window, min_periods=window // 2).mean()
    std = series.rolling(window, min_periods=window // 2).std()
    return (series - mean) / std.replace(0, np.nan)


def backtest_asset(df, asset_name):
    df = df.copy()
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df = df.sort_values('timestamp').reset_index(drop=True)
    df['fundingRate'] = df['fundingRate'].fillna(0)
    df['funding_zscore'] = compute_funding_zscore(df['fundingRate'], ZSCORE_WINDOW)

    trades = []
    position = 0
    entry_time = None
    entry_z = 0
    hours_held = 0
    funding_pnl = 0.0

    for i in range(1, len(df)):
        row = df.iloc[i]
        ts = row['timestamp']
        z = row['funding_zscore']
        funding = row['fundingRate']

        if pd.isna(z):
            continue

        if position != 0 and ts.hour in FUNDING_HOURS:
            funding_pnl += -position * funding

        if position != 0:
            hours_held += 1
            should_exit = False
            reason = None

            if (position == -1 and z < EXIT_Z) or (position == 1 and z > -EXIT_Z):
                should_exit = True
                reason = 'REVERT'
            elif hours_held >= MAX_HOLD_HOURS:
                should_exit = True
                reason = 'TIMEOUT'

            if should_exit:
                cost = MAKER_FEE_PERP * 2
                net_pnl = funding_pnl - cost
                trades.append({
                    'asset': asset_name,
                    'entry_time': entry_time,
                    'exit_time': ts,
                    'direction': 'SHORT' if position == -1 else 'LONG',
                    'entry_zscore': round(entry_z, 3),
                    'hours_held': hours_held,
                    'funding_pnl_pct': round(funding_pnl * 100, 5),
                    'cost_pct': round(cost * 100, 5),
                    'net_pnl_pct': round(net_pnl * 100, 5),
                    'exit_reason': reason,
                })
                position = 0
                hours_held = 0
                funding_pnl = 0.0

        if position == 0:
            if z > ENTRY_Z and abs(funding) >= MIN_FUNDING:
                position = -1
                entry_time = ts
                entry_z = z
                hours_held = 0
                funding_pnl = 0.0
            elif z < -ENTRY_Z and abs(funding) >= MIN_FUNDING:
                position = 1
                entry_time = ts
                entry_z = z
                hours_held = 0
                funding_pnl = 0.0

    return trades


def main():
    print("=" * 70)
    print("FUNDING RATE BASIS HARVEST - BACKTEST")
    print("=" * 70)

    data = pd.read_pickle(DATA_FILE)
    data = {k: v for k, v in data.items() if 'SUI' not in k}

    all_trades = []
    for asset, df in data.items():
        print(f"\nProcessing {asset}...")
        trades = backtest_asset(df, asset)
        all_trades.extend(trades)
        print(f"  {len(trades)} trades")

    trades_df = pd.DataFrame(all_trades)

    if len(trades_df) == 0:
        print("\nNo trades. Lower ENTRY_Z to 1.0 and rerun.")
        return

    trades_df.to_csv(OUTPUT_FILE, index=False)

    total_trades = len(trades_df)
    months = 24

    winners = trades_df[trades_df['net_pnl_pct'] > 0]
    losers = trades_df[trades_df['net_pnl_pct'] <= 0]

    win_rate = len(winners) / total_trades * 100
    avg_win = winners['net_pnl_pct'].mean() if len(winners) else 0
    avg_loss = losers['net_pnl_pct'].mean() if len(losers) else 0
    total_pnl = trades_df['net_pnl_pct'].sum()

    print("\n" + "=" * 70)
    print("PERFORMANCE SUMMARY")
    print("=" * 70)
    print(f"Total trades:     {total_trades}")
    print(f"Trades/month:     {total_trades / months:.1f}")
    print(f"Win rate:         {win_rate:.1f}%")
    print(f"Avg win:          {avg_win:+.4f}%")
    print(f"Avg loss:         {avg_loss:+.4f}%")
    print(f"Total PnL:        {total_pnl:+.2f}%")
    print(f"PnL/month:        {total_pnl / months:+.2f}%")
    print(f"PnL/year (est):   {total_pnl / months * 12:+.1f}%")

    print("\nPer-asset breakdown:")
    for asset in trades_df['asset'].unique():
        a_df = trades_df[trades_df['asset'] == asset]
        a_pnl = a_df['net_pnl_pct'].sum()
        a_wr = (a_df['net_pnl_pct'] > 0).mean() * 100
        print(f"  {asset}: {len(a_df)} trades, {a_wr:.1f}% WR, {a_pnl:+.2f}% total")

    with open(SUMMARY_FILE, 'w') as f:
        f.write(f"Total trades: {total_trades}\n")
        f.write(f"Trades/month: {total_trades / months:.1f}\n")
        f.write(f"Win rate: {win_rate:.1f}%\n")
        f.write(f"Total PnL: {total_pnl:+.2f}%\n")
        f.write(f"PnL/month: {total_pnl / months:+.2f}%\n")
        f.write(f"PnL/year: {total_pnl / months * 12:+.1f}%\n")


if __name__ == '__main__':
    main()