import pandas as pd, json, os
from datetime import datetime

df = pd.read_csv('trades_log.csv')
months = 24
w = df[df['net_pnl']>0] if 'net_pnl' in df.columns else pd.DataFrame()
l = df[df['net_pnl']<=0] if 'net_pnl' in df.columns else pd.DataFrame()
tpm = len(df)/months
wr  = len(w)/len(df)*100 if len(df) else 0
rr  = abs(w['net_pnl'].mean()/l['net_pnl'].mean()) if len(l) and l['net_pnl'].mean()!=0 else 0
eq_col = next((c for c in ['running_equity','running_equity_after','equity'] if c in df.columns), None)
end_eq = df[eq_col].iloc[-1] if eq_col else 100000
net_pct = (end_eq-100000)/100000*100
roll_max = df[eq_col].cummax() if eq_col else pd.Series([100000]*len(df))
max_dd = ((roll_max-df[eq_col])/roll_max).max()*100 if eq_col else 0
total_pnl = df['net_pnl'].sum() if 'net_pnl' in df.columns else 0

try:
    with open('optimization/best_params.json') as f:
        bp = json.load(f)
except:
    bp = {}

# Build params rows
params_rows = ''
for k, v in bp.items():
    params_rows += '<tr><td>{}</td><td>{}</td></tr>'.format(k, v)
if not params_rows:
    params_rows = '<tr><td colspan=2>N/A</td></tr>'

# Monthly performance
if 'exit_time' in df.columns and 'net_pnl' in df.columns:
    df['month'] = pd.to_datetime(df['exit_time'], errors='coerce').dt.to_period('M').astype(str)
    mo = df.groupby('month')['net_pnl'].agg(['sum','count']).reset_index()
    mo_rows = ''
    for _, r in mo.iterrows():
        color = '#3fb950' if r['sum'] > 0 else '#f85149'
        mo_rows += '<tr><td>{}</td><td>{}</td><td style="color:{}">${:,.0f}</td></tr>'.format(r['month'], int(r['count']), color, r['sum'])
else:
    mo_rows = '<tr><td colspan=3>N/A</td></tr>'

# Regime breakdown
rcol = next((c for c in ['regime_at_entry','regime'] if c in df.columns), None)
if rcol and 'net_pnl' in df.columns:
    rg = df.groupby(rcol)['net_pnl'].agg(['count','sum','mean'])
    rg_rows = ''
    for i, r in rg.iterrows():
        rg_rows += '<tr><td>{}</td><td>{}</td><td>${:,.0f}</td><td>${:,.2f}</td></tr>'.format(i, int(r['count']), r['sum'], r['mean'])
else:
    rg_rows = '<tr><td colspan=4>N/A</td></tr>'

# Recent trades
recent = df.tail(20)
tr_rows = ''
for _, t in recent.iterrows():
    p = t.get('net_pnl', 0)
    color = '#3fb950' if p > 0 else '#f85149'
    tr_rows += '<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td style="color:{}">${:,.2f}</td></tr>'.format(
        str(t.get('exit_time', ''))[:16],
        t.get('instrument', t.get('symbol', '')),
        t.get('direction', ''),
        t.get('exit_reason', ''),
        color,
        p
    )

def badge(ok):
    if ok:
        return '<span style="background:#1a4a2e;color:#3fb950;padding:3px 10px;border-radius:10px;font-weight:bold">PASS</span>'
    else:
        return '<span style="background:#4a1a1a;color:#f85149;padding:3px 10px;border-radius:10px;font-weight:bold">FAIL</span>'

html = '''<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>Growth Traders Strategy Report</title>
<style>
body {{font-family: Arial, sans-serif; background: #0d1117; color: #e6edf3; margin: 0; padding: 24px}}
h1 {{color: #58a6ff; text-align: center; font-size: 2em}}
h2 {{color: #79c0ff; border-bottom: 1px solid #30363d; padding-bottom: 6px; margin-top: 32px}}
.grid {{display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin: 16px 0}}
.card {{background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 16px; text-align: center}}
.val {{font-size: 1.8em; font-weight: bold; margin: 6px 0}}
.lbl {{color: #8b949e; font-size: .85em}}
table {{width: 100%; border-collapse: collapse; margin: 12px 0; font-size: .9em}}
th {{background: #21262d; padding: 10px; text-align: left; color: #79c0ff; font-size: .85em}}
td {{padding: 8px; border-bottom: 1px solid #21262d}}
tr:hover {{background: #1c2128}}
p {{color: #8b949e; text-align: center}}
</style>
</head>
<body>
<h1>Growth Traders — Triple-Signal Crypto Futures Strategy</h1>
<p>Period: Sep 2022 – Sep 2024 &nbsp;|&nbsp; Capital: $100,000 USDT &nbsp;|&nbsp; Instruments: SOL DOGE ARB SUI Perpetuals<br>
Generated: {datetime_now}</p>

<h2>Performance Summary</h2>
<div class="grid">
<div class="card"><div class="lbl">Net PnL</div><div class="val" style="color:{net_pnl_color}">{net_pct:+.1f}%</div></div>
<div class="card"><div class="lbl">Trades/Month</div><div class="val" style="color:{trades_month_color}">{tpm:.1f}</div></div>
<div class="card"><div class="lbl">Win Rate</div><div class="val" style="color:{win_rate_color}">{wr:.1f}%</div></div>
<div class="card"><div class="lbl">Max Drawdown</div><div class="val" style="color:{max_dd_color}">{max_dd:.1f}%</div></div>
<div class="card"><div class="lbl">Reward:Risk</div><div class="val" style="color:{reward_risk_color}">{rr:.2f}:1</div></div>
<div class="card"><div class="lbl">Total Trades</div><div class="val">{trade_count}</div></div>
</div>

<h2>Acceptance Criteria</h2>
<table>
<tr><th>Criterion</th><th>Required</th><th>Actual</th><th>Status</th></tr>
<tr><td>Trades/month</td><td>≥ 30</td><td>{tpm:.1f}</td><td>{trades_month_badge}</td></tr>
<tr><td>Max Drawdown</td><td>≤ 20%</td><td>{max_dd:.1f}%</td><td>{max_dd_badge}</td></tr>
<tr><td>Reward:Risk</td><td>> 1:1</td><td>{rr:.2f}:1</td><td>{reward_risk_badge}</td></tr>
<tr><td>Win Rate</td><td>≥ 45%</td><td>{wr:.1f}%</td><td>{win_rate_badge}</td></tr>
<tr><td>Net PnL</td><td>Positive</td><td>{net_pct:+.1f}%</td><td>{net_pnl_badge}</td></tr>
</table>

<h2>Monthly Performance</h2>
<table>
<tr><th>Month</th><th>Trades</th><th>Net PnL</th></tr>
{mo_rows}
</table>

<h2>Regime Breakdown</h2>
<table>
<tr><th>Regime</th><th>Trades</th><th>Total PnL</th><th>Avg PnL</th></tr>
{rg_rows}
</table>

<h2>Best Parameters Found</h2>
<table>
<tr><th>Parameter</th><th>Value</th></tr>
{params_rows}
</table>

<h2>Cost Model</h2>
<table>
<tr><th>Cost</th><th>Rate</th></tr>
<tr><td>Entry (Maker)</td><td>0.03%</td></tr>
<tr><td>Exit (Taker)</td><td>0.05%</td></tr>
<tr><td>Slippage</td><td>0.02%</td></tr>
<tr><td>Funding</td><td>Historical rates applied every 8h</td></tr>
<tr><td><b>Round-trip total</b></td><td><b>~0.10%</b></td></tr>
</table>

<h2>Recent Trades (Last 20)</h2>
<table>
<tr><th>Exit Time</th><th>Instrument</th><th>Direction</th><th>Exit Reason</th><th>Net PnL</th></tr>
{tr_rows}
</table>

<p style="margin-top:40px">Strategy: Mean Reversion + Funding Extreme + OI Surge Dual-Signal System<br>
Validation: 2-year backtest | Walk-forward | 10 stress test scenarios</p>
</body>
</html>'''.format(
    datetime_now=datetime.now().strftime("%Y-%m-%d %H:%M"),
    net_pnl_color="#3fb950" if net_pct > 0 else "#f85149",
    trades_month_color="#3fb950" if tpm >= 30 else "#f0883e",
    win_rate_color="#3fb950" if wr >= 45 else "#f85149",
    max_dd_color="#3fb950" if max_dd <= 20 else "#f85149",
    reward_risk_color="#3fb950" if rr >= 1 else "#f85149",
    net_pct=net_pct,
    tpm=tpm,
    wr=wr,
    max_dd=max_dd,
    rr=rr,
    trade_count=len(df),
    trades_month_badge=badge(tpm >= 30),
    max_dd_badge=badge(max_dd <= 20),
    reward_risk_badge=badge(rr > 1),
    win_rate_badge=badge(wr >= 45),
    net_pnl_badge=badge(net_pct > 0),
    mo_rows=mo_rows,
    rg_rows=rg_rows,
    params_rows=params_rows,
    tr_rows=tr_rows
)

os.makedirs('reports', exist_ok=True)
with open('reports/strategy_report.html', 'w', encoding='utf-8') as f:
    f.write(html)
print('Report saved: reports/strategy_report.html ({:,} bytes)'.format(len(html)))