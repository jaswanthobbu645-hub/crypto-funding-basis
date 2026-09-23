"""
Parameter optimizer module for crypto perpetual futures backtesting system.
Implements a FAST vectorized parameter search using pandas/numpy operations only.
"""

import pandas as pd
import numpy as np
import logging
import json
import random
import pickle
from pathlib import Path
from typing import Dict, List, Tuple, Any
import config
from importlib import import_module

# Import the generate_signals function from 03_signals.py
_signals_module = import_module('03_signals')
generate_signals = _signals_module.generate_signals

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def generate_random_params(n_samples: int = 500) -> List[Dict]:
    """
    Generate random parameter combinations for optimization.

    Args:
        n_samples (int): Number of random parameter sets to generate.

    Returns:
        List[Dict]: List of parameter dictionaries.
    """
    # Set random seed for reproducibility
    random.seed(42)
    np.random.seed(42)

    # Define parameter ranges for random search
    param_ranges = {
        'OI_THRESHOLD': [1.0, 1.5, 2.0, 2.5, 3.0],
        'FUNDING_LONG_THRESH': [-0.0005, -0.001, -0.002, -0.003],
        'FUNDING_SHORT_THRESH': [0.001, 0.002, 0.003, 0.005],
        'BOOK_LONG_THRESH': [0.55, 0.60, 0.65, 0.70],
        'BOOK_SHORT_THRESH': [0.30, 0.35, 0.40, 0.45],
        'MIN_CONFLUENCE_SCORE': [2, 3],
        'ADX_TREND_THRESH': [20, 25, 30],  # Note: This parameter is not actually used in the strategy
        'REGIME_CONFIRM_BARS': [2, 3, 4],
        'BULL_TP_PCT': [0.006, 0.008, 0.010, 0.012],  # Increased TP for better reward:risk
        'BULL_SL_PCT': [0.003, 0.004, 0.005],         # Adjusted SL
        'SIDEWAYS_TP_PCT': [0.004, 0.005, 0.006, 0.008],  # Increased TP
        'SIDEWAYS_SL_PCT': [0.002, 0.0025, 0.003, 0.004], # Adjusted SL
        'RISK_PCT_PER_TRADE': [0.005, 0.01, 0.015],
        # New parameters for dual signal approach
        'OI_SURGE_THRESH': [1.0, 1.5, 2.0, 3.0],
        'BAR_POS_SURGE_LONG': [0.60, 0.65, 0.70],
        'BAR_POS_SURGE_SHORT': [0.30, 0.35, 0.40],
        'FUNDING_NEUTRAL': [0.0005, 0.001, 0.002],
    }

    param_list = []
    for _ in range(n_samples):
        params = {}
        for param_name, values in param_ranges.items():
            params[param_name] = random.choice(values)
        param_list.append(params)

    return param_list

def score_backtest_result(stats: Dict) -> float:
    """
    Calculate a score for backtest results based on multiple metrics.
    Encourages exploration rather than strict filtering.

    Args:
        stats (Dict): Performance statistics from backtest.

    Returns:
        float: Score for the parameter set (higher is better).
    """
    # Hard disqualifiers - only eliminate catastrophically bad results
    if stats.get('max_drawdown', 1) > 0.50:        # >50% drawdown is unacceptable
        return -999
    if stats.get('trades_per_month', 0) < 5:       # too few trades to matter
        return -999
    if stats.get('net_pnl_pct', 0) < -60:           # catastrophic loss
        return -999

    # Extract metrics
    net_pnl_pct = stats.get('net_pnl_pct', 0)
    sharpe = stats.get('sharpe_ratio', 0)
    max_dd = stats.get('max_drawdown', 0)
    win_rate = stats.get('win_rate', 0)
    trades_pm = stats.get('trades_per_month', 0)
    avg_win = stats.get('avg_win', 0)
    avg_loss = stats.get('avg_loss', 0)
    
    # Calculate reward:risk ratio
    if avg_loss != 0:
        rr = abs(avg_win / avg_loss)
    else:
        rr = float('inf') if avg_win > 0 else 0

    # Soft scoring - weighted sum (encourages exploration)
    score = 0
    score += net_pnl_pct * 2.0      # maximize profit
    score += sharpe * 10.0          # reward consistency
    score -= max_dd * 100.0         # penalize drawdown
    score += win_rate * 20.0        # reward win rate
    score += min(trades_pm, 60) * 0.5  # reward frequency up to 60/month
    score += rr * 15.0              # reward reward:risk

    return score

def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute indicators needed for regime detection and position sizing.

    Args:
        df: Raw DataFrame with OHLCV, OI, funding data

    Returns:
        DataFrame with selected indicator columns added
    """
    df = df.copy()

    # Ensure timestamp is datetime and set as index if not already
    if 'timestamp' in df.columns:
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df.set_index('timestamp', inplace=True)

    # Sort by timestamp
    df.sort_index(inplace=True)
    # Calculate total time days for annualization and trades per month
    if len(df) > 1:
        total_time_days = (df.index[-1] - df.index[0]).days
    else:
        total_time_days = 0

    # EMA calculations (for regime detection)
    df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()
    df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
    df['ema_slope'] = (df['ema_200'] - df['ema_200'].shift(10)) / df['ema_200'].shift(10) * 100

    # ADX calculation (simplified version)
    # True Range
    tr1 = df['high'] - df['low']
    tr2 = np.abs(df['high'] - df['close'].shift())
    tr3 = np.abs(df['low'] - df['close'].shift())
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # Directional Movement
    up_move = df['high'] - df['high'].shift()
    down_move = df['low'].shift() - df['low']

    # Plus and Minus DM
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    # Smoothed TR, +DM, -DM
    atr = tr.rolling(window=14).mean()
    plus_dm_smooth = pd.Series(plus_dm).rolling(window=14).mean()
    minus_dm_smooth = pd.Series(minus_dm).rolling(window=14).mean()

    # Directional Indicators
    plus_di = 100 * (plus_dm_smooth / atr.replace(0, np.nan))
    minus_di = 100 * (minus_dm_smooth / atr.replace(0, np.nan))

    # Directional Index (DX)
    dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan)

    # ADX (smoothed DX)
    df['adx_14'] = dx.rolling(window=14).mean()

    # 3-day funding rate mean (9 x 8h = 72h)
    df['funding_3d'] = df['fundingRate'].rolling(window=9).mean()

    # Volatility (20-period rolling std of returns, annualized)
    returns = df['close'].pct_change()
    df['vol_20'] = returns.rolling(window=20).std() * np.sqrt(24 * 365)  # Annualized

    return df

def detect_regime_vectorized(df: pd.DataFrame, confirmation_bars: int = 3) -> pd.DataFrame:
    """
    Vectorized regime detection (simplified version that avoids loops).

    Args:
        df: DataFrame with precomputed indicators
        confirmation_bars: Number of consecutive bars to confirm regime shift

    Returns:
        DataFrame with 'regime' and 'is_high_vol' columns added
    """
    df = df.copy()

    # Initialize regime column
    df['regime'] = 'SIDEWAYS'
    df['is_high_vol'] = False

    # Handle NaN values by filling with SIDEWAYS conditions
    ema_slope = df['ema_slope'].fillna(0)
    adx_14 = df['adx_14'].fillna(0)
    ema_50 = df['ema_50'].fillna(0)
    ema_200 = df['ema_200'].fillna(0)
    close = df['close'].fillna(0)
    funding_3d = df['funding_3d'].fillna(0)

    # Determine raw regime for each bar (without confirmation)
    # HIGH VOLATILITY OVERRIDE
    high_vol_mask = adx_14 >= config.ADX_TREND_THRESH  # Use config threshold

    # BULL conditions
    bull_mask = (ema_50 > ema_200) & (close > ema_50) & (adx_14 < config.ADX_TREND_THRESH)

    # BEAR conditions
    bear_mask = (ema_50 < ema_200) & (close < ema_50) & (adx_14 < config.ADX_TREND_THRESH)

    # Apply regimes in priority order: HIGH_VOL > BULL > BEAR > SIDEWAYS
    df.loc[high_vol_mask, 'regime'] = 'HIGH_VOL'
    df.loc[~high_vol_mask & bull_mask, 'regime'] = 'BULL'
    df.loc[~(high_vol_mask | bull_mask) & bear_mask, 'regime'] = 'BEAR'
    # Remaining are SIDEWAYS (default)

    # Apply confirmation using rolling window (simplified)
    # For each regime, check if it has been the same for 'confirmation_bars' periods
    for regime in ['BULL', 'BEAR', 'SIDEWAYS', 'HIGH_VOL']:
        regime_mask = (df['regime'] == regime)
        # Use rolling window to check for consecutive occurrences
        confirmed_mask = regime_mask.rolling(window=confirmation_bars, min_periods=1).sum() == confirmation_bars
        # Only keep the regime if it's been confirmed for the required consecutive bars
        df.loc[~confirmed_mask, 'regime'] = 'SIDEWAYS'  # Revert unconfirmed to SIDEWAYS

    # Update is_high_vol based on confirmed regime
    df['is_high_vol'] = (df['regime'] == 'HIGH_VOL')

    return df

def generate_signals_vectorized(df: pd.DataFrame, params: Dict) -> pd.DataFrame:
    """
    Generate signals using the centralized signal generation from 03_signals.py.

    Args:
        df: DataFrame with raw data (OHLCV, OI, funding) and any additional columns (like regime, vol_20) are ignored.
        params: Parameter dictionary

    Returns:
        DataFrame with signal columns added
    """
    # We call the centralized signal generation function.
    # Note: 03_signals.generate_signals expects the raw data with columns:
    #   open, high, low, close, volume, openInterest, fundingRate
    # Our df may have extra columns, but the function will ignore them.
    return generate_signals(df, params)

def simulate_trades_vectorized(df: pd.DataFrame, params: Dict, initial_equity: float = 100000.0) -> Dict:
    """
    Vectorized trade simulation (approximation of the backtest engine logic).

    Args:
        df: DataFrame with signals and regime data
        params: Parameter dictionary
        initial_equity: Starting equity

    Returns:
        Dictionary with performance statistics
    """
    # Make a copy to work with
    df = df.copy()
    # Calculate total time days for annualization and trades per month
    if len(df) > 1:
        total_time_days = (df.index[-1] - df.index[0]).days
    else:
        total_time_days = 0

    # Initialize tracking variables
    equity = initial_equity
    peak_equity = equity
    max_drawdown = 0.0
    trades = []  # List to store trade dictionaries

    i = 0
    n = len(df)

    while i < n:
        # Find the next entry signal from i onwards
        if i >= n:
            break
        entry_mask = df['entry_long'].values[i:] | df['entry_short'].values[i:]
        if not np.any(entry_mask):
            break   # no more entries
        # Find the first entry index
        j = i + np.argmax(entry_mask)   # first occurrence of True in the mask

        # Determine direction at bar j
        long_signal = df['entry_long'].iloc[j]
        short_signal = df['entry_short'].iloc[j]
        if long_signal and short_signal:
            # Use the score to break tie
            score_long = df['score_long'].iloc[j]
            score_short = df['score_short'].iloc[j]
            direction = 'LONG' if score_long >= score_short else 'SHORT'
        elif long_signal:
            direction = 'LONG'
        elif short_signal:
            direction = 'SHORT'
        else:
            # This should not happen because we checked the mask
            i = j + 1
            continue

        # We have an entry at bar j
        entry_price = df['close'].iloc[j]
        entry_time = df.index[j]

        # Get regime at entry (for TP/SL percentages)
        regime_at_entry = df['regime'].iloc[j]
        # Get volatility at entry for position sizing
        vol_at_entry = df['vol_20'].iloc[j]
        if pd.isna(vol_at_entry):
            vol_at_entry = 0.02   # fallback

        # Get regime-specific parameters
        if regime_at_entry == 'BULL':
            tp_pct_use = params['BULL_TP_PCT']
            sl_pct_use = params['BULL_SL_PCT']
            time_exit_bar_use = getattr(config, 'BULL_TIME_EXIT_BARS', 24)
        elif regime_at_entry == 'SIDEWAYS':
            tp_pct_use = params['SIDEWAYS_TP_PCT']
            sl_pct_use = params['SIDEWAYS_SL_PCT']
            time_exit_bar_use = getattr(config, 'SIDEWAYS_TIME_EXIT_BARS', 24)
        else:  # BEAR or HIGH_VOL or any other regime
            tp_pct_use = getattr(config, 'BEAR_TP_PCT', params['BULL_TP_PCT'])
            sl_pct_use = getattr(config, 'BEAR_SL_PCT', params['BULL_SL_PCT'])
            time_exit_bar_use = getattr(config, 'BEAR_TIME_EXIT_BARS', 24)

        # Calculate TP and SL levels
        if direction == 'LONG':
            tp_level = entry_price * (1 + tp_pct_use)
            sl_level = entry_price * (1 - sl_pct_use)
        else:  # SHORT
            tp_level = entry_price * (1 - tp_pct_use)
            sl_level = entry_price * (1 + sl_pct_use)

        # Look ahead for TP, SL, or time exit
        # We'll look from j to the end
        future_high = df['high'].values[j:]
        future_low = df['low'].values[j:]

        # For long:
        if direction == 'LONG':
            # TP hit: when future_high >= tp_level
            tp_hit = np.where(future_high >= tp_level)[0]
            # SL hit: when future_low <= sl_level
            sl_hit = np.where(future_low <= sl_level)[0]
        else:  # SHORT
            # TP hit: when future_low <= tp_level
            tp_hit = np.where(future_low <= tp_level)[0]
            # SL hit: when future_high >= sl_level
            sl_hit = np.where(future_high >= sl_level)[0]

        # Time exit: fixed number of bars from entry
        time_exit_offset = time_exit_bar_use   # in bars

        # Find the first hit among TP, SL, and time exit
        candidates = []
        if len(tp_hit) > 0:
            candidates.append(tp_hit[0])
        if len(sl_hit) > 0:
            candidates.append(sl_hit[0])
        candidates.append(time_exit_offset)   # time exit is always an option

        if not candidates:
            # This should not happen because we have time_exit_offset
            exit_offset = len(df) - j   # exit at the last bar
        else:
            exit_offset = min(candidates)

        exit_index = j + exit_offset
        if exit_index >= n:
            exit_index = n - 1

        exit_price = df['close'].iloc[exit_index]
        exit_time = df.index[exit_index]

        # Calculate holding period in bars
        held_bars = exit_index - j   # number of bars after the entry bar until the exit bar

        # Calculate position size
        risk_amount = equity * params['RISK_PCT_PER_TRADE']
        # Avoid division by zero
        if sl_pct_use == 0:
            size_usd = equity * params['RISK_PCT_PER_TRADE'] * 10   # fallback (should not happen)
        else:
            # Simplified position sizing: risk_amount / sl_pct
            size_usd = risk_amount / sl_pct_use

        # Calculate gross PnL
        if direction == 'LONG':
            gross_pnl = (exit_price / entry_price - 1) * size_usd
        else:  # SHORT
            gross_pnl = (entry_price / exit_price - 1) * size_usd

        # Calculate costs
        # Fees: maker on entry, taker on exit
        entry_fee = size_usd * config.MAKER_FEE
        exit_fee = size_usd * config.TAKER_FEE
        slippage = size_usd * config.SLIPPAGE   # one slip for entry and one for exit?
        # Funding cost:
        #   We assume funding is settled every 8 hours (3 bars if 1h bars? but we don't know the bar size)
        #   We'll assume each bar is 1 hour -> funding every 8 bars.
        #   We'll compute the average funding rate over the held bars and then multiply by the number of funding intervals.
        held_bars_count = exit_index - j + 1   # including both entry and exit bar
        funding_rates = df['fundingRate'].iloc[j:exit_index+1].values
        avg_funding = np.nanmean(funding_rates) if len(funding_rates) > 0 else 0
        # Number of funding intervals: each 8 bars -> floor(held_bars_count / 8)
        funding_intervals = max(1, held_bars_count // 8)
        funding_cost = size_usd * avg_funding * funding_intervals
        # For shorts, funding cost is negative if funding is positive
        if direction == 'SHORT':
            funding_cost = -funding_cost

        total_cost = entry_fee + exit_fee + slippage + funding_cost
        net_pnl = gross_pnl - total_cost

        # Record trade
        trade = {
            'entry_time': entry_time,
            'exit_time': exit_time,
            'direction': direction,
            'entry_price': entry_price,
            'exit_price': exit_price,
            'size_usd': size_usd,
            'gross_pnl': gross_pnl,
            'entry_fee': entry_fee,
            'exit_fee': exit_fee,
            'slippage': slippage,
            'funding_cost': funding_cost,
            'net_pnl': net_pnl,
            'held_bars': held_bars,
            'regime_at_entry': regime_at_entry,
            'vol_at_entry': vol_at_entry
        }
        trades.append(trade)

        # Update equity
        equity += net_pnl

        # Update peak equity and max drawdown
        if equity > peak_equity:
            peak_equity = equity
        else:
            drawdown = (peak_equity - equity) / peak_equity
            if drawdown > max_drawdown:
                max_drawdown = drawdown

        # Move to the next bar after the exit bar
        i = exit_index + 1

    # After processing all trades, compute statistics
    if trades:
        trades_df = pd.DataFrame(trades)
        net_pnl = trades_df['net_pnl'].sum()
        total_trades = len(trades_df)
        winning_trades = trades_df[trades_df['net_pnl'] > 0]
        losing_trades = trades_df[trades_df['net_pnl'] <= 0]
        win_rate = len(winning_trades) / total_trades if total_trades > 0 else 0
        avg_win = winning_trades['net_pnl'].mean() if len(winning_trades) > 0 else 0
        avg_loss = losing_trades['net_pnl'].mean() if len(losing_trades) > 0 else 0
        profit_factor = abs(avg_win / avg_loss) if avg_loss != 0 else float('inf') if avg_win > 0 else 0

        # Sharpe ratio: approximate using trade returns
        if len(trades_df) > 1:
            # Calculate the return per trade on the initial equity (approximation)
            returns = trades_df['net_pnl'] / initial_equity
            # Annualize assuming trades occur uniformly over the period
            # We approximate the number of trades per year from the time range
            total_time_years = total_time_days / 365.25 if total_time_days > 0 else 1
            trades_per_year = total_trades / total_time_years if total_time_years > 0 else total_trades
            sharpe_ratio = np.mean(returns) / np.std(returns) * np.sqrt(trades_per_year) if np.std(returns) > 0 else 0
        else:
            sharpe_ratio = 0

        net_pnl_pct = (net_pnl / initial_equity) * 100
    else:
        net_pnl = 0.0
        total_trades = 0
        win_rate = 0.0
        avg_win = 0.0
        avg_loss = 0.0
        profit_factor = 0.0
        sharpe_ratio = 0.0
        net_pnl_pct = 0.0
        trades_per_month = 0.0

    # Calculate trades per month
    total_time_months = total_time_days / 30.0 if total_time_days > 0 else 1
    trades_per_month = total_trades / total_time_months if total_time_months > 0 else 0

    stats = {
        'net_pnl': net_pnl,
        'net_pnl_pct': net_pnl_pct,
        'sharpe_ratio': sharpe_ratio,
        'max_drawdown': max_drawdown,
        'win_rate': win_rate,
        'trades_per_month': trades_per_month,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'profit_factor': profit_factor,
        'total_trades': total_trades
    }

    return stats

def run_parameter_optimization() -> Tuple[List[Dict], pd.DataFrame]:
    """
    Run parameter optimization using random search on in-sample period.
    Uses vectorized operations and avoids calling BacktestEngine.

    Returns:
        Tuple[List[Dict], pd.DataFrame]: (top_10_params, results_df)
    """
    logger.info("Starting parameter optimization (random search with 500 samples)...")

    # Load combined data once
    logger.info("Loading combined data...")
    with open(r"data/combined_all.pkl", "rb") as f:
        combined_data = pickle.load(f)

    # Extract individual instrument data (assuming combined_data is a dict of DataFrames)
    if isinstance(combined_data, dict):
        raw_data = combined_data
    else:
        # If it's a single DataFrame, split by some column (this would need adjustment)
        # For now, assume it's already structured correctly
        raw_data = {'DEFAULT': combined_data}

    logger.info(f"Loaded data for {len(raw_data)} instruments")

    # Generate random parameter combinations
    param_list = generate_random_params(n_samples=500)

    # Precompute indicators for each instrument once
    logger.info("Precomputing indicators for all instruments...")
    indicator_data = {}
    for instrument, df in raw_data.items():
        logger.info(f"Computing indicators for {instrument}")
        df_with_indicators = compute_indicators(df)
        indicator_data[instrument] = df_with_indicators

    results = []

    # Test each parameter set
    for i, params in enumerate(param_list):
        if (i + 1) % 50 == 0:
            logger.info(f"Processed {i + 1}/500 parameter sets...")

        # Process each instrument with current parameters
        instrument_results = []
        for instrument, df in indicator_data.items():
            # Detect regime for this parameter set's REGIME_CONFIRM_BARS
            regime_bars = params['REGIME_CONFIRM_BARS']
            df_with_regime = detect_regime_vectorized(df, regime_bars)

            # Generate signals
            df_with_signals = generate_signals_vectorized(df_with_regime, params)

            # Simulate trades (this is the sequential component, but optimized)
            stats = simulate_trades_vectorized(df_with_signals, params, 100000.0)  # Reset equity for each instrument

            # Store result
            result = {
                'instrument': instrument,
                'params': params.copy(),
                'net_pnl': stats.get('net_pnl', 0),
                'net_pnl_pct': stats.get('net_pnl_pct', 0),
                'sharpe_ratio': stats.get('sharpe_ratio', 0),
                'max_drawdown': stats.get('max_drawdown', 0),
                'win_rate': stats.get('win_rate', 0),
                'trades_per_month': stats.get('trades_per_month', 0),
                'profit_factor': stats.get('profit_factor', 0),
                'total_trades': stats.get('total_trades', 0)
            }
            instrument_results.append(result)

        # Aggregate results across all instruments
        # Sum net PnL and total trades, average other metrics weighted by trades
        total_net_pnl = sum(r['net_pnl'] for r in instrument_results)
        total_trades = sum(r['total_trades'] for r in instrument_results)

        if total_trades > 0:
            # Weighted averages by number of trades
            avg_win_rate = sum(r['win_rate'] * r['total_trades'] for r in instrument_results) / total_trades
            avg_sharpe = sum(r['sharpe_ratio'] * r['total_trades'] for r in instrument_results) / total_trades
            avg_max_dd = sum(r['max_drawdown'] * r['total_trades'] for r in instrument_results) / total_trades
            avg_profit_factor = sum(r['profit_factor'] * r['total_trades'] for r in instrument_results) / total_trades
        else:
            avg_win_rate = 0
            avg_sharpe = 0
            avg_max_dd = 0
            avg_profit_factor = 0

        # Calculate aggregated stats
        agg_stats = {
            'net_pnl': total_net_pnl,
            'net_pnl_pct': (total_net_pnl / (100000.0 * len(raw_data))) * 100,  # Normalize by initial equity * num_instruments
            'sharpe_ratio': avg_sharpe,
            'max_drawdown': avg_max_dd,
            'win_rate': avg_win_rate,
            'trades_per_month': sum(r['trades_per_month'] for r in instrument_results) / len(raw_data),  # Average across instruments
            'profit_factor': avg_profit_factor,
            'total_trades': total_trades
        }

        # Calculate score from aggregated stats
        score = score_backtest_result(agg_stats)

        # Store result
        result = {
            'params': params.copy(),
            'score': score,
            'net_pnl': agg_stats.get('net_pnl', 0),
            'net_pnl_pct': agg_stats.get('net_pnl_pct', 0),
            'sharpe_ratio': agg_stats.get('sharpe_ratio', 0),
            'max_drawdown': agg_stats.get('max_drawdown', 0),
            'win_rate': agg_stats.get('win_rate', 0),
            'trades_per_month': agg_stats.get('trades_per_month', 0),
            'profit_factor': agg_stats.get('profit_factor', 0),
            'total_trades': agg_stats.get('total_trades', 0)
        }
        results.append(result)

    # Convert results to DataFrame
    results_df = pd.DataFrame(results)

    # Extract parameter columns for easier viewing
    param_columns = ['OI_THRESHOLD', 'FUNDING_LONG_THRESH', 'FUNDING_SHORT_THRESH',
                     'BOOK_LONG_THRESH', 'BOOK_SHORT_THRESH', 'MIN_CONFLUENCE_SCORE',
                     'ADX_TREND_THRESH', 'REGIME_CONFIRM_BARS', 'BULL_TP_PCT',
                     'BULL_SL_PCT', 'SIDEWAYS_TP_PCT', 'SIDEWAYS_SL_PCT',
                     'RISK_PCT_PER_TRADE',
                     # New parameters for dual signal approach
                     'OI_SURGE_THRESH', 'BAR_POS_SURGE_LONG', 'BAR_POS_SURGE_SHORT', 'FUNDING_NEUTRAL']

    for col in param_columns:
        results_df[col] = results_df['params'].apply(lambda x: x.get(col, np.nan))

    # Sort by score (descending)
    results_df = results_df.sort_values('score', ascending=False).reset_index(drop=True)

    # Get top 10 parameter sets
    top_10 = results_df.head(10).copy()

    logger.info(f"Parameter optimization completed. Top score: {results_df.iloc[0]['score']:.4f}")

    return top_10[param_columns + ['score', 'net_pnl_pct', 'sharpe_ratio', 'max_drawdown', 'win_rate', 'trades_per_month']].to_dict('records'), results_df

def save_optimization_results(top_10_params: List[Dict], results_df: pd.DataFrame):
    """
    Save optimization results to files.

    Args:
        top_10_params (List[Dict]): Top 10 parameter sets.
        results_df (pd.DataFrame): Full results DataFrame.
    """
    # Create optimization directory
    opt_dir = Path("optimization")
    opt_dir.mkdir(exist_ok=True)

    # Save top 10 parameters as JSON
    with open(opt_dir / "top_10_params.json", 'w') as f:
        json.dump(top_10_params, f, indent=2)

    # Save full results as CSV
    results_df.to_csv(opt_dir / "param_search_results.csv", index=False)

    # Create a summary text file
    with open(opt_dir / "optimization_summary.txt", 'w') as f:
        f.write("Parameter Optimization Results\n")
        f.write("=" * 50 + "\n")
        f.write(f"Total parameter sets tested: {len(results_df)}\n")
        f.write(f"Top score: {results_df.iloc[0]['score']:.4f}\n\n")
        f.write("Top 10 Parameter Sets:\n")
        for i, params in enumerate(top_10_params):
            f.write(f"\n{i+1}. Score: {params['score']:.4f}\n")
            f.write(f"   Net PnL %: {params['net_pnl_pct']:.2f}%\n")
            f.write(f"   Sharpe Ratio: {params['sharpe_ratio']:.2f}\n")
            f.write(f"   Max Drawdown: {params['max_drawdown']:.2%}\n")
            f.write(f"   Win Rate: {params['win_rate']:.2%}\n")
            f.write(f"   Trades/Month: {params['trades_per_month']:.2f}\n")
            f.write("   Parameters:\n")
            # List the parameters
            param_keys = [k for k in params.keys() if k not in ['score', 'net_pnl_pct', 'sharpe_ratio', 'max_drawdown', 'win_rate', 'trades_per_month']]
            for key in param_keys:
                f.write(f"     {key}: {params[key]}\n")

    logger.info(f"Optimization results saved to {opt_dir}")

def test_parameter_optimizer():
    """
    Unit test for parameter optimizer.
    """
    logger.info("Running parameter optimizer unit test...")

    # Test random parameter generation
    param_list = generate_random_params(n_samples=10)
    assert len(param_list) == 10, f"Expected 10 parameter sets, got {len(param_list)}"

    # Check that all required parameters are present
    required_params = ['OI_THRESHOLD', 'FUNDING_LONG_THRESH', 'FUNDING_SHORT_THRESH',
                       'BOOK_LONG_THRESH', 'BOOK_SHORT_THRESH', 'MIN_CONFLUENCE_SCORE',
                       'ADX_TREND_THRESH', 'REGIME_CONFIRM_BARS', 'BULL_TP_PCT',
                       'BULL_SL_PCT', 'SIDEWAYS_TP_PCT', 'SIDEWAYS_SL_PCT',
                       'RISK_PCT_PER_TRADE',
                       # New parameters for dual signal approach
                       'OI_SURGE_THRESH', 'BAR_POS_SURGE_LONG', 'BAR_POS_SURGE_SHORT', 'FUNDING_NEUTRAL']

    for params in param_list:
        for param in required_params:
            assert param in params, f"Missing parameter {param} in parameter set"

    # Test scoring function with mock stats
    mock_stats = {
        'net_pnl_pct': 50.0,      # 50% return
        'sharpe_ratio': 1.5,      # Good Sharpe
        'max_drawdown': 0.10,     # 10% drawdown
        'win_rate': 0.60,         # 60% win rate
        'trades_per_month': 25.0, # 25 trades/month
        'avg_win': 100.0,
        'avg_loss': -50.0
    }

    score = score_backtest_result(mock_stats)
    # Should be a reasonable score (not disqualified)
    assert score > -999, f"Score should not be disqualified, got {score}"
    assert isinstance(score, float), f"Score should be float, got {type(score)}"

    # Test disqualification
    mock_stats_bad = mock_stats.copy()
    mock_stats_bad['max_drawdown'] = 0.25  # >20% -> should disqualify
    score_bad = score_backtest_result(mock_stats_bad)
    assert score_bad == -999, f"Should be disqualified for high drawdown, got {score_bad}"

    mock_stats_bad2 = mock_stats.copy()
    mock_stats_bad2['trades_per_month'] = 10  # <10 -> should disqualify (diagnostic)
    score_bad2 = score_backtest_result(mock_stats_bad2)
    assert score_bad2 == -999, f"Should be disqualified for low trades, got {score_bad2}"

    logger.info("Parameter optimizer unit test PASSED")
    return True

if __name__ == "__main__":
    # Run parameter optimization when executed directly
    logger.info("Running parameter optimization...")
    top_10, results_df = run_parameter_optimization()
    save_optimization_results(top_10, results_df)

    # Print summary
    print("\nParameter Optimization Complete!")
    print(f"Top 10 parameter sets saved to optimization/top_10_params.json")
    print(f"Full results saved to optimization/param_search_results.csv")
    print("\nTop 3 parameter sets:")
    for i, params in enumerate(top_10[:3]):
        print(f"\n{i+1}. Score: {params['score']:.4f}")
        print(f"   Net PnL %: {params['net_pnl_pct']:.2f}%")
        print(f"   Sharpe: {params['sharpe_ratio']:.2f}")
        print(f"   Max DD: {params['max_drawdown']:.2%}")
        print(f"   Win Rate: {params['win_rate']:.2f}")
        print(f"   Trades/Month: {params['trades_per_month']:.2f}")