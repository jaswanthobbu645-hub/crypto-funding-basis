import pickle, json, sys, os
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime

sys.path.insert(0, r'C:\Users\Avinash\crypto_backtest')

print("Loading data...")
with open('data/processed_all.pkl', 'rb') as f:
    all_data = pickle.load(f)

print("Loading best params...")
with open('optimization/best_params.json') as f:
    best_params = json.load(f)

# Add missing params with defaults
best_params.setdefault('BULL_TP_PCT',       0.006)
best_params.setdefault('BULL_SL_PCT',       0.003)
best_params.setdefault('SIDEWAYS_TP_PCT',   0.004)
best_params.setdefault('SIDEWAYS_SL_PCT',   0.002)
best_params.setdefault('BEAR_TP_PCT',       0.006)
best_params.setdefault('BEAR_SL_PCT',       0.003)
best_params.setdefault('RISK_PCT_PER_TRADE',0.01)
best_params.setdefault('MAX_LEVERAGE',      5)
best_params.setdefault('MAX_CONCURRENT',    3)
best_params.setdefault('REGIME_CONFIRM_BARS',3)

MAKER_FEE  = 0.0003
TAKER_FEE  = 0.0005
SLIPPAGE   = 0.0002
START_EQ   = 100_000.0

from importlib import import_module
sig_mod = import_module('03_signals')
generate_signals = sig_mod.generate_signals

def compute_ema(s, span):
    return s.ewm(span=span, adjust=False).mean()

def compute_adx(df, period=14):
    h,l,c = df['high'],df['low'],df['close']
    pc = c.shift(1)
    tr = pd.concat([h-l,(h-pc).abs(),(l-pc).abs()],axis=1).max(axis=1)
    up = (h-h.shift(1)).clip(0)
    dn = (l.shift(1)-l).clip(0)
    pdm = up.where(up>dn,0)
    ndm = dn.where(dn>up,0)
    atr = tr.ewm(span=period,adjust=False).mean()
    pdi = 100*pdm.ewm(span=period,adjust=False).mean()/(atr+1e-10)
    ndi = 100*ndm.ewm(span=period,adjust=False).mean()/(atr+1e-10)
    dx  = 100*(pdi-ndi).abs()/(pdi+ndi+1e-10)
    return dx.ewm(span=period,adjust=False).mean()

def add_regime(df):
    close = df['close']
    high = df['high']
    low = df['low']
    ema50 = close.ewm(span=50, adjust=False).mean()
    ema200 = close.ewm(span=200, adjust=False).mean()
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)
    plus_dm = (high - high.shift()).clip(lower=0)
    minus_dm = (low.shift() - low).clip(lower=0)
    atr14 = tr.ewm(alpha=1/14, adjust=False).mean().replace(0, float('nan'))
    plus_di = 100 * plus_dm.ewm(alpha=1/14, adjust=False).mean() / atr14
    minus_di = 100 * minus_dm.ewm(alpha=1/14, adjust=False).mean() / atr14
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    adx = dx.ewm(alpha=1/14, adjust=False).mean().fillna(0)
    regime = pd.Series('SIDEWAYS', index=df.index)
    regime[ema50 > ema200] = 'BULL'
    regime[ema50 < ema200] = 'BEAR'
    regime[adx >= 35] = 'HIGH_VOL'
    df = df.copy()
    df['regime'] = regime
    return df

print("Running backtest on all instruments...")
trades = []
equity = START_EQ
peak_eq = START_EQ
open_pos = {}  # symbol -> position dict

# Use TP and SL from best_params.json (regime-specific)
TP_MAP = {
    'BULL':     best_params['BULL_TP_PCT'],
    'SIDEWAYS': best_params['SIDEWAYS_TP_PCT'],
    'BEAR':     best_params['BEAR_TP_PCT'],
    'HIGH_VOL': best_params['SIDEWAYS_TP_PCT'],  # treat HIGH_VOL as SIDEWAYS for TP/SL
}
SL_MAP = {
    'BULL':     best_params['BULL_SL_PCT'],
    'SIDEWAYS': best_params['SIDEWAYS_SL_PCT'],
    'BEAR':     best_params['BEAR_SL_PCT'],
    'HIGH_VOL': best_params['SIDEWAYS_SL_PCT'],
}
# Increased time exit bars (double the original from config.py? we'll use 2x)
# Original config.py: BULL_TIME_EXIT_BARS=24, etc. We'll double.
TB_MAP = {'BULL':48, 'SIDEWAYS':48, 'BEAR':48, 'HIGH_VOL':48}  # double of 24? Actually we want to give more time, but let's use 2x original.
# However, we don't have original in this script; we'll use 24 as base and double.
BASE_TB = {'BULL':24, 'SIDEWAYS':24, 'BEAR':24, 'HIGH_VOL':24}
TB_MAP = {k: v*2 for k,v in BASE_TB.items()}
SM_MAP = {'BULL':1.5,'SIDEWAYS':0.75,'BEAR':1.0,'HIGH_VOL':0.5}

frames = {}
for sym, df in all_data.items():
    df = df.copy()
    if 'timestamp' not in df.columns:
        df = df.reset_index().rename(columns={'index': 'timestamp'})
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
    df = df.sort_values('timestamp').reset_index(drop=True)
    df = add_regime(df)
    df = generate_signals(df.copy(), best_params)
    frames[sym] = df
    print(f"  {sym}: {len(df)} bars | longs={df['entry_long'].sum()} shorts={df['entry_short'].sum()}")

# Get all timestamps sorted
all_ts = sorted(set().union(*[set(df['timestamp']) for df in frames.values()]))
print(f"Processing {len(all_ts)} timestamps...")

eq_curve = []
last_date = None

for ts in all_ts:
    cur_date = ts.date()
    if last_date != cur_date:
        eq_curve.append({'date':cur_date,'equity':equity})
        last_date = cur_date

    peak_eq = max(peak_eq, equity)
    cur_dd  = (peak_eq - equity) / peak_eq
    if cur_dd >= 0.20:
        pass  # Removed DD halt - run full period for accurate reporting

    for sym, df in frames.items():
        rows = df[df['timestamp']==ts]
        if rows.empty: continue
        row = rows.iloc[0]
        idx = rows.index[0]
        close = float(row['close'])
        reg   = row['regime']

        # Check exits
        if sym in open_pos:
            pos  = open_pos[sym]
            ep   = pos['entry_price']
            size = pos['size_usd']
            dire = pos['direction']
            tp   = pos['tp']
            sl   = pos['sl']
            bars_held = idx - pos['entry_idx']

            pnl_pct = (close-ep)/ep if dire==1 else (ep-close)/ep
            exit_r  = None
            if pnl_pct >= tp:       exit_r='TP'
            elif pnl_pct <= -sl:    exit_r='SL'
            elif bars_held >= pos['time_bars']: exit_r='TIME'
            elif (reg=='BEAR' and dire==1) or (reg=='BULL' and dire==-1):
                exit_r='REGIME_FLIP'

            if exit_r:
                gross   = size * pnl_pct
                fi      = bars_held // 8
                fund_c  = size * abs(float(row.get('funding_rate',row.get('fundingRate',0)))) * fi
                costs   = size*(MAKER_FEE+TAKER_FEE+SLIPPAGE) + fund_c
                net_pnl = gross - costs
                equity += net_pnl
                peak_eq = max(peak_eq, equity)

                trades.append({
                    'instrument':    sym,
                    'direction':     'LONG' if dire==1 else 'SHORT',
                    'entry_time':    pos['entry_time'],
                    'exit_time':     ts,
                    'entry_price':   ep,
                    'exit_price':    close,
                    'size_usd':      size,
                    'bars_held':     bars_held,
                    'exit_reason':   exit_r,
                    'regime_at_entry': pos['entry_reg'],
                    'gross_pnl':     gross,
                    'costs':         costs,
                    'net_pnl':       net_pnl,
                    'net_pnl_pct':   net_pnl/size if size>0 else 0,
                    'running_equity':equity,
                    'drawdown':      (peak_eq-equity)/peak_eq,
                })
                del open_pos[sym]

        # Check entries
        if (sym not in open_pos and
            len(open_pos) < best_params['MAX_CONCURRENT'] and
            cur_dd < 0.20 and idx > 250):

            sig_l = bool(row.get('entry_long', False))
            sig_s = bool(row.get('entry_short', False))

            if sig_l or sig_s:
                dire   = 1 if sig_l else -1
                tp_pct = TP_MAP.get(reg, best_params['SIDEWAYS_TP_PCT'])
                sl_pct = SL_MAP.get(reg, best_params['SIDEWAYS_SL_PCT'])
                s_mult = SM_MAP.get(reg, 1.0)

                dd_mult = 1.0
                if cur_dd>0.05:  dd_mult=0.75
                if cur_dd>0.10:  dd_mult=0.50
                if cur_dd>0.15:  dd_mult=0.25

                risk_amt = equity * best_params['RISK_PCT_PER_TRADE'] * s_mult * dd_mult
                size_usd = min(
                    risk_amt / (sl_pct+1e-10),
                    equity * 0.20,
                    equity * best_params['MAX_LEVERAGE'] * 0.20
                )
                size_usd = max(size_usd, 10)

                open_pos[sym] = {
                    'entry_price': close,
                    'entry_time':  ts,
                    'entry_idx':   idx,
                    'entry_reg':   reg,
                    'direction':   dire,
                    'size_usd':    size_usd,
                    'tp':          tp_pct,
                    'sl':          sl_pct,
                    'time_bars':   TB_MAP.get(reg,48),
                }

# Save trades
tdf = pd.DataFrame(trades)
tdf.to_csv('trades_log.csv', index=False)
print(f"\nSaved {len(tdf)} trades to trades_log.csv")

# Save equity curve
edf = pd.DataFrame(eq_curve)
edf.to_csv('equity_curve.csv', index=False)

# Print results
if len(tdf) > 0:
    months = 24
    w = tdf[tdf['net_pnl']>0]
    l = tdf[tdf['net_pnl']<=0]
    tpm   = len(tdf)/months
    wr    = len(w)/len(tdf)*100
    avgw  = w['net_pnl'].mean() if len(w) else 0
    avgl  = abs(l['net_pnl'].mean()) if len(l) else 1
    rr    = avgw/avgl
    roll_max = tdf['running_equity'].cummax()
    max_dd   = ((roll_max-tdf['running_equity'])/roll_max).max()*100
    end_eq   = tdf['running_equity'].iloc[-1]
    net_pct  = (end_eq-START_EQ)/START_EQ*100

    print(f"\n{'='*50}")
    print(f"BACKTEST RESULTS")
    print(f"{'='*50}")
    print(f"Total trades:    {len(tdf)}")
    print(f"Trades/month:    {tpm:.1f}")
    print(f"Win rate:        {wr:.1f}%")
    print(f"Reward:Risk:     {rr:.2f}:1")
    print(f"Net PnL:         {net_pct:+.1f}%")
    print(f"Max Drawdown:    {max_dd:.1f}%")
    print(f"End equity:      ${end_eq:,.2f}")
    print(f"{'='*50}")
    print(f"\nACCEPTANCE CRITERIA:")
    print(f"  Trades/month >= 30: {'PASS' if tpm>=30 else 'FAIL'} ({tpm:.1f})")
    print(f"  Max DD <= 20%:      {'PASS' if max_dd<=20 else 'FAIL'} ({max_dd:.1f}%)")
    print(f"  Reward:Risk > 1:    {'PASS' if rr>1 else 'FAIL'} ({rr:.2f})")
    print(f"  Win rate >= 45%:    {'PASS' if wr>=45 else 'FAIL'} ({wr:.1f}%)")
    print(f"  Net PnL positive:   {'PASS' if net_pct>0 else 'FAIL'} ({net_pct:+.1f}%)")

    # Regime breakdown
    if 'regime_at_entry' in tdf.columns:
        print(f"\nREGIME BREAKDOWN:")
        rg = tdf.groupby('regime_at_entry')['net_pnl'].agg(['count','sum','mean'])
        for i,r in rg.iterrows():
            print(f"  {i}: {int(r['count'])} trades | PnL: ${r['sum']:,.0f} | Avg: ${r['mean']:,.2f}")
    else:
        print("WARNING: No trades generated. Check signal conditions.")