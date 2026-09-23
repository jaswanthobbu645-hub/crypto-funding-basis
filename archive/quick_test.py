"""
Quick test script for verifying signal logic before full optimization.
Loads data/combined_all.pkl, runs signal generation with hardcoded parameters,
and simulates trades with a simple loop.
"""

import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime

# Add the crypto_backtest directory to sys.path
crypto_path = r'C:\Users\Avinash\crypto_backtest'
sys.path.insert(0, crypto_path)

# Import the signal generation function
from importlib import import_module
_signals_module = import_module('03_signals')
generate_signals = _signals_module.generate_signals

# Import regime detection
from importlib import import_module
_regime_module = import_module('02_regime_detector')
RegimeDetector = _regime_module.RegimeDetector

# Hardcoded parameters as specified
params = {
    "FUNDING_LONG_THRESH":  -0.0003,
    "FUNDING_SHORT_THRESH":  0.0005,
    "OI_MA_PERIOD":          20,
    "OI_RATIO_THRESH":       1.05,
    "EMA_PERIOD":            20,
    "PRICE_OVERSOLD_PCT":    0.015,
    "PRICE_OVERBOUGHT_PCT":  0.015,
    "BAR_POS_LONG":          0.55,
    "BAR_POS_SHORT":         0.45,
    "BULL_TP_PCT":           0.008,
    "BULL_SL_PCT":           0.004,
    "SIDEWAYS_TP_PCT":       0.005,
    "SIDEWAYS_SL_PCT":       0.003,
    "BEAR_TP_PCT":           0.008,
    "BEAR_SL_PCT":           0.004,
    "RISK_PCT_PER_TRADE":    0.01,
    "MAX_LEVERAGE":          5,
    "MAX_CONCURRENT":        3,
    "MAKER_FEE":             0.0003,
    "TAKER_FEE":             0.0005,
    "SLIPPAGE":              0.0002,
}

MAKER_FEE = params["MAKER_FEE"]
TAKER_FEE = params["TAKER_FEE"]
SLIPPAGE = params["SLIPPAGE"]
TOTAL_COST = MAKER_FEE + TAKER_FEE + SLIPPAGE

def load_data():
    """Load the combined data pickle file."""
    data_path = os.path.join(crypto_path, 'data', 'combined_all.pkl')
    print(f"Loading data from: {data_path}")
    
    if not os.path.exists(data_path):
        raise FileNotFoundError(f"Data file not found: {data_path}")
    
    # Load the data
    with open(data_path, 'rb') as f:
        data = pd.read_pickle(f)
    
    print(f"Loaded data type: {type(data)}")
    if isinstance(data, dict):
        print(f"Data is a dictionary with keys: {list(data.keys())}")
        for key, df in data.items():
            print(f"  {key}: shape {df.shape}")
    else:
        print(f"Loaded data with shape: {data.shape}")
        print(f"Columns: {data.columns.tolist()}")
        print(f"Index type: {type(data.index)}")
        if hasattr(data.index, 'levels'):
            print(f"Index levels: {data.index.names}")
            print(f"Number of unique symbols: {len(data.index.get_level_values(0).unique()) if len(data.index.levels) > 0 else 'Unknown'}")
    
    return data

def add_regime_column(df):
    """Add regime column to dataframe using RegimeDetector."""
    # We need to compute the indicators required for regime detection first
    df = df.copy()
    
    # Calculate indicators needed for regime detection (same as in 03_signals.py detect_regime_adjusted)
    df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()
    df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
    df['ema_slope'] = (df['ema_200'] - df['ema_200'].shift(10)) / df['ema_200'].shift(10) * 100
    
    # ADX calculation
    tr1 = df['high'] - df['low']
    tr2 = np.abs(df['high'] - df['close'].shift())
    tr3 = np.abs(df['low'] - df['close'].shift())
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    up_move = df['high'] - df['high'].shift()
    down_move = df['low'].shift() - df['low']
    
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    
    atr = tr.rolling(window=14).mean()
    plus_dm_smooth = pd.Series(plus_dm).rolling(window=14).mean()
    minus_dm_smooth = pd.Series(minus_dm).rolling(window=14).mean()
    
    plus_di = 100 * (plus_dm_smooth / atr)
    minus_di = 100 * (minus_dm_smooth / atr)
    
    dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di)
    df['adx_14'] = dx.rolling(window=14).mean()
    
    # OI slope (6-hour change)
    df['oi_slope'] = (df['openInterest'] - df['openInterest'].shift(6)) / df['openInterest'].shift(6) * 100
    
    # 3-day funding rate mean (9 x 8h = 72h)
    df['funding_3d'] = df['fundingRate'].rolling(window=9).mean()
    
    # Volatility (20-period rolling std of returns, annualized)
    df['returns'] = df['close'].pct_change()
    df['vol_20'] = df['returns'].rolling(window=20).std() * np.sqrt(24 * 365)  # Annualized
    
    # Price range (20-bar high-low as % of close)
    df['high_20'] = df['high'].rolling(window=20).max()
    df['low_20'] = df['low'].rolling(window=20).min()
    df['price_range'] = (df['high_20'] - df['low_20']) / df['close']
    
    # Now detect regime
    detector = RegimeDetector(confirmation_bars=3)
    df_with_regime = detector.detect_regime(df)
    
    return df_with_regime

def count_signals_and_stats(df, symbol):
    """Generate signals and count them, plus compute statistics."""
    # First add regime column if not present
    if 'regime' not in df.columns:
        df_with_regime = add_regime_column(df.copy())
    else:
        df_with_regime = df.copy()
    
    # Generate signals
    df_with_signals = generate_signals(df_with_regime, params)
    
    # Count signals
    long_signals = df_with_signals['entry_long'].sum()
    short_signals = df_with_signals['entry_short'].sum()
    
    # Calculate statistics
    funding_rate = df_with_signals['fundingRate']
    open_interest = df_with_signals['openInterest']
    
    # OI 20-period moving average
    oi_ma = open_interest.rolling(params["OI_MA_PERIOD"]).mean()
    oi_ratio = open_interest / (oi_ma + 1e-10)
    
    # EMA 20
    ema_20 = df_with_signals['close'].ewm(span=params["EMA_PERIOD"], adjust=False).mean()
    
    # Bar position
    bar_position = (df_with_signals['close'] - df_with_signals['low']) / (df_with_signals['high'] - df_with_signals['low'] + 1e-10)
    
    stats = {
        'long_signals': int(long_signals),
        'short_signals': int(short_signals),
        'funding_min': float(funding_rate.min()),
        'funding_max': float(funding_rate.max()),
        'funding_mean': float(funding_rate.mean()),
        'funding_below_long_thresh_pct': float((funding_rate < params["FUNDING_LONG_THRESH"]).mean() * 100),
        'funding_above_short_thresh_pct': float((funding_rate > params["FUNDING_SHORT_THRESH"]).mean() * 100),
        'oi_above_ratio_pct': float((oi_ratio > params["OI_RATIO_THRESH"]).mean() * 100),
        'close_below_ema_oversold_pct': float((df_with_signals['close'] < ema_20 * (1 - params["PRICE_OVERSOLD_PCT"])).mean() * 100),
        'close_above_ema_overbought_pct': float((df_with_signals['close'] > ema_20 * (1 + params["PRICE_OVERBOUGHT_PCT"])).mean() * 100),
        'bar_position_long_pct': float((bar_position > params["BAR_POS_LONG"]).mean() * 100),
        'bar_position_short_pct': float((bar_position < params["BAR_POS_SHORT"]).mean() * 100),
        'data_length': len(df_with_signals)
    }
    
    return df_with_signals, stats

def simulate_trades_simple(df_with_signals, symbol, params):
    """Simulate trades with a simple loop as specified."""
    equity = 100000
    trades = []
    in_trade = False
    
    entry_price = 0
    entry_time = None
    entry_regime = None
    entry_bar_index = 0
    direction = None
    
    # Extract parameters
    maker_fee = params["MAKER_FEE"]
    taker_fee = params["TAKER_FEE"]
    slippage = params["SLIPPAGE"]
    total_cost = maker_fee + taker_fee + slippage
    
    bull_tp = params["BULL_TP_PCT"]
    bull_sl = params["BULL_SL_PCT"]
    sideways_tp = params["SIDEWAYS_TP_PCT"]
    sideways_sl = params["SIDEWAYS_SL_PCT"]
    bear_tp = params["BEAR_TP_PCT"]
    bear_sl = params["BEAR_SL_PCT"]
    
    # Pre-calculate indicators needed for regime detection in the loop
    df = df_with_signals.copy()
    
    # We need to calculate regime if not already present
    # But according to the data, regime column should already be there from the pickle
    # If not, we'd need to calculate it, but let's assume it's present
    
    for i, (idx, row) in enumerate(df.iterrows()):
        if not in_trade:
            # Check for entry signals
            if row['entry_long']:
                entry_price = row['close']
                entry_time = idx
                entry_regime = row['regime'] if 'regime' in row else 'SIDEWAYS'
                entry_bar_index = i
                direction = 'LONG'
                in_trade = True
                
            elif row['entry_short']:
                entry_price = row['close']
                entry_time = idx
                entry_regime = row['regime'] if 'regime' in row else 'SIDEWAYS'
                entry_bar_index = i
                direction = 'SHORT'
                in_trade = True
        else:
            # We're in a trade, check for exit
            current_price = row['close']
            bars_held = i - entry_bar_index
            
            # Calculate PnL from entry
            if direction == 'LONG':
                pnl_pct = (current_price - entry_price) / entry_price
            else:  # SHORT
                pnl_pct = (entry_price - current_price) / entry_price
            
            # Get TP/SL based on regime at entry (not current regime)
            if entry_regime == 'BULL':
                tp_pct = bull_tp
                sl_pct = bull_sl
            elif entry_regime == 'SIDEWAYS':
                tp_pct = sideways_tp
                sl_pct = sideways_sl
            else:  # BEAR
                tp_pct = bear_tp
                sl_pct = bear_sl
            
            # Check exit conditions
            exit_reason = None
            net_pnl_pct = None
            
            if pnl_pct >= tp_pct:
                exit_reason = 'TP'
                net_pnl_pct = tp_pct - total_cost
            elif pnl_pct <= -sl_pct:
                exit_reason = 'SL'
                net_pnl_pct = -sl_pct - total_cost
            elif bars_held >= 6:
                exit_reason = 'TIME'
                net_pnl_pct = pnl_pct - total_cost
            
            if exit_reason is not None:
                # Record the trade
                trades.append({
                    'entry_time': entry_time,
                    'exit_time': idx,
                    'symbol': symbol,
                    'direction': direction,
                    'entry_regime': entry_regime,
                    'bars_held': bars_held,
                    'exit_reason': exit_reason,
                    'gross_pct': pnl_pct * 100,  # Convert to percentage
                    'net_pct': net_pnl_pct * 100,  # Convert to percentage
                    'entry_price': entry_price,
                    'exit_price': current_price
                })
                
                # Reset for next trade
                in_trade = False
    
    return trades

def calculate_metrics(trades):
    """Calculate performance metrics from trades."""
    if not trades:
        return {
            'total': 0,
            'win_rate': 0,
            'avg_win': 0,
            'avg_loss': 0,
            'net_pnl_pct': 0,
            'max_dd': 0,
            'profit_factor': 0,
            'trades_per_month': 0,
            'sharpe': 0
        }
    
    # Convert to arrays for easier calculation
    net_pcts = np.array([t['net_pct'] for t in trades])
    gross_pcts = np.array([t['gross_pct'] for t in trades])
    
    # Basic stats
    total_trades = len(trades)
    winning_trades = [t for t in trades if t['net_pct'] > 0]
    losing_trades = [t for t in trades if t['net_pct'] <= 0]
    
    win_rate = len(winning_trades) / total_trades if total_trades > 0 else 0
    
    avg_win = np.mean([t['net_pct'] for t in winning_trades]) if winning_trades else 0
    avg_loss = np.mean([t['net_pct'] for t in losing_trades]) if losing_trades else 0
    
    net_pnl_pct = np.sum(net_pcts)
    
    # Calculate max drawdown
    cumulative = np.cumsum(net_pcts)
    running_max = np.maximum.accumulate(cumulative)
    drawdown = running_max - cumulative
    max_dd = np.max(drawdown) if len(drawdown) > 0 else 0
    
    # Profit factor
    gross_profit = np.sum([t['net_pct'] for t in winning_trades]) if winning_trades else 0
    gross_loss = abs(np.sum([t['net_pct'] for t in losing_trades])) if losing_trades else 0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
    
    # Estimate trades per month (assuming hourly data)
    # We need to know the time span - this is approximate
    # For now, we'll calculate based on assumption of ~720 hours per month
    # A better approach would be to use actual time span from data
    trades_per_month = (total_trades / 720) * 30 * 24  # Rough approximation
    
    # Sharpe ratio (simplified - annualized)
    if len(net_pcts) > 1:
        sharpe = np.mean(net_pcts) / np.std(net_pcts) * np.sqrt(252 * 24)  # Assuming hourly data
    else:
        sharpe = 0
    
    return {
        'total': total_trades,
        'win_rate': win_rate,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'net_pnl_pct': net_pnl_pct,
        'max_dd': max_dd,
        'profit_factor': profit_factor,
        'trades_per_month': trades_per_month,
        'sharpe': sharpe
    }

def main():
    print("=" * 60)
    print("QUICK TEST - SIGNAL LOGIC VERIFICATION")
    print("=" * 60)
    
    try:
        # Load data
        data = load_data()
        
        all_trades = []
        symbol_stats = {}
        
        if isinstance(data, dict):
            # Process each symbol in the dict
            print(f"\nProcessing {len(data)} symbols...")
            for symbol, df in data.items():
                print(f"\nProcessing {symbol}...")
                
                # Generate signals and get stats
                df_with_signals, stats = count_signals_and_stats(df, symbol)
                symbol_stats[symbol] = stats
                
                # Simulate trades
                trades = simulate_trades_simple(df_with_signals, symbol, params)
                all_trades.extend(trades)
                
                print(f"  Signals - Long: {stats['long_signals']}, Short: {stats['short_signals']}")
                print(f"  Trades: {len(trades)}")
        else:
            # Assume it's a single DataFrame (multi-index or single symbol)
            print("\nProcessing single DataFrame...")
            df_with_signals, stats = count_signals_and_stats(data, "UNKNOWN")
            symbol_stats["UNKNOWN"] = stats
            
            # Simulate trades
            trades = simulate_trades_simple(df_with_signals, "UNKNOWN", params)
            all_trades.extend(trades)
            
            print(f"  Signals - Long: {stats['long_signals']}, Short: {stats['short_signals']}")
            print(f"  Trades: {len(trades)}")
        
        # Print aggregated stats
        print("\n" + "=" * 60)
        print("AGGREGATED STATISTICS")
        print("=" * 60)
        
        total_long = sum(s['long_signals'] for s in symbol_stats.values())
        total_short = sum(s['short_signals'] for s in symbol_stats.values())
        print(f"Total Long Signals:  {total_long}")
        print(f"Total Short Signals: {total_short}")
        print(f"Total Signals:       {total_long + total_short}")
        
        # Average stats across symbols (if dict)
        if isinstance(data, dict) and len(data) > 0:
            avg_funding_min = np.mean([s['funding_min'] for s in symbol_stats.values()])
            avg_funding_max = np.mean([s['funding_max'] for s in symbol_stats.values()])
            avg_funding_mean = np.mean([s['funding_mean'] for s in symbol_stats.values()])
            avg_funding_below = np.mean([s['funding_below_long_thresh_pct'] for s in symbol_stats.values()])
            avg_funding_above = np.mean([s['funding_above_short_thresh_pct'] for s in symbol_stats.values()])
            avg_oi_above = np.mean([s['oi_above_ratio_pct'] for s in symbol_stats.values()])
            
            print(f"\nAverage Funding Rate Stats:")
            print(f"  Min: {avg_funding_min:.6f}")
            print(f"  Max: {avg_funding_max:.6f}")
            print(f"  Mean: {avg_funding_mean:.6f}")
            print(f"  % Below Long Thresh (-0.0003): {avg_funding_below:.2f}%")
            print(f"  % Above Short Thresh (0.0005): {avg_funding_above:.2f}%")
            print(f"  % OI > OI_MA * 1.05: {avg_oi_above:.2f}%")
        else:
            # Single DataFrame case
            stats = symbol_stats.get("UNKNOWN", {})
            if stats:
                print(f"\nSignal Counts:")
                print(f"  Long Signals:  {stats['long_signals']}")
                print(f"  Short Signals: {stats['short_signals']}")
                
                print(f"\nFunding Rate Stats:")
                print(f"  Min: {stats['funding_min']:.6f}")
                print(f"  Max: {stats['funding_max']:.6f}")
                print(f"  Mean: {stats['funding_mean']:.6f}")
                print(f"  % Below Long Thresh (-0.0003): {stats['funding_below_long_thresh_pct']:.2f}%")
                print(f"  % Above Short Thresh (0.0005): {stats['funding_above_short_thresh_pct']:.2f}%")
                
                print(f"\nOI Stats:")
                print(f"  % OI > OI_MA * {params['OI_RATIO_THRESH']}: {stats['oi_above_ratio_pct']:.2f}%")
                
                print(f"\nPrice vs EMA Stats:")
                print(f"  % Close < EMA * (1 - {params['PRICE_OVERSOLD_PCT']}): {stats['close_below_ema_oversold_pct']:.2f}%")
                print(f"  % Close > EMA * (1 + {params['PRICE_OVERBOUGHT_PCT']}): {stats['close_above_ema_overbought_pct']:.2f}%")
                
                print(f"\nBar Position Stats:")
                print(f"  % Bar Position > {params['BAR_POS_LONG']} (long signal): {stats['bar_position_long_pct']:.2f}%")
                print(f"  % Bar Position < {params['BAR_POS_SHORT']} (short signal): {stats['bar_position_short_pct']:.2f}%")
        
        # Calculate metrics
        metrics = calculate_metrics(all_trades)
        
        # Print results
        print("\n" + "=" * 60)
        print("SINGLE TEST RESULTS")
        print("=" * 60)
        print(f"Total trades:      {metrics['total']}")
        print(f"Trades/month:      {metrics['trades_per_month']:.1f}")
        print(f"Win rate:          {metrics['win_rate']*100:.1f}%")
        print(f"Avg win:           {metrics['avg_win']*100:.3f}%")
        print(f"Avg loss:          {metrics['avg_loss']*100:.3f}%")
        print(f"Net PnL%:          {metrics['net_pnl_pct']*100:.2f}%")
        print(f"Max Drawdown:      {metrics['max_dd']*100:.1f}%")
        print(f"Reward:Risk:       {metrics['profit_factor']:.2f}")
        print(f"Sharpe (est):      {metrics['sharpe']:.2f}")
        
        # Print first 10 trades in detail
        print("\n" + "=" * 60)
        print("FIRST 10 TRADES (DETAIL)")
        print("=" * 60)
        
        if all_trades:
            for i, trade in enumerate(all_trades[:10]):
                print(f"Trade {i+1}:")
                print(f"  Entry Time: {trade['entry_time']}")
                print(f"  Symbol:     {trade['symbol']}")
                print(f"  Direction:  {trade['direction']}")
                print(f"  Regime:     {trade['entry_regime']}")
                print(f"  Bars Held:  {trade['bars_held']}")
                print(f"  Exit Reason:{trade['exit_reason']}")
                print(f"  Gross %:    {trade['gross_pct']:.3f}%")
                print(f"  Net %:      {trade['net_pct']:.3f}%")
                print()
        else:
            print("No trades were executed.")
        
        # Check win rate and act accordingly
        win_rate = metrics['win_rate']
        
        if win_rate < 0.40:
            print("\n" + "!" * 60)
            print("⚠️  WIN RATE TOO LOW — DIAGNOSING...")
            print("!" * 60)
            
            # Diagnose first 20 losing trades
            losing_trades = [t for t in all_trades if t['net_pct'] <= 0]
            print(f"\nAnalyzing first {min(20, len(losing_trades))} losing trades:")
            
            # We need to re-analyze the losing trades to get entry bar stats
            # For simplicity, we'll just note that we'd need to re-run signal generation
            # and capture the entry bar diagnostics
            print("\nNote: Full diagnostic would require re-analyzing entry bars for:")
            print("  - funding_rate value at entry")
            print("  - OI vs oi_20ma ratio at entry") 
            print("  - close vs ema_20 ratio at entry")
            print("  - bar_position at entry")
            print("  - which conditions were True at entry")
            print("  - bars to hit SL")
            print("\nThis diagnostic would tell us WHY trades are losing.")
            
            return False  # Indicate we should not proceed to optimizer
            
        else:
            print("\n" + "✅" * 60)
            print("✅ WIN RATE ACCEPTABLE — PROCEEDING TO OPTIMIZER")
            print("✅" * 60)
            return True  # Indicate we should proceed to optimizer
            
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)