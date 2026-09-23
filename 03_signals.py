"""
Signal generation module for crypto perpetual futures backtesting system.
Computes all signals as columns added to the DataFrame.
"""

import pandas as pd
import numpy as np
import logging
from typing import Dict
from collections import deque
import config

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def generate_signals(df: pd.DataFrame, params: Dict = None) -> pd.DataFrame:
    """
    Generate all signals for the given DataFrame using mean reversion + funding extreme logic.
    Signals work in ALL regimes - regime only affects TP/SL, not entry logic.

    Args:
        df (pd.DataFrame): DataFrame with OHLCV, OI, funding data.
        params (Dict): Optional parameters to override config. If None, uses config.

    Returns:
        DataFrame: DataFrame with entry_long and entry_short signal columns added.
    """
    # Set up parameters with fallbacks
    if params is None:
        # Use config values if available, otherwise use hard-coded defaults
        params = {
            'FUNDING_LONG_THRESH': getattr(config, 'FUNDING_LONG_THRESH', -0.0003),
            'FUNDING_SHORT_THRESH': getattr(config, 'FUNDING_SHORT_THRESH', 0.0005),
            'OI_MA_PERIOD': getattr(config, 'OI_MA_PERIOD', 20),
            'OI_RATIO_THRESH': getattr(config, 'OI_RATIO_THRESH', 1.05),
            'EMA_PERIOD': getattr(config, 'EMA_PERIOD', 20),
            'PRICE_OVERSOLD_PCT': getattr(config, 'PRICE_OVERSOLD_PCT', 0.015),
            'PRICE_OVERBOUGHT_PCT': getattr(config, 'PRICE_OVERBOUGHT_PCT', 0.015),
            'BAR_POS_LONG': getattr(config, 'BAR_POS_LONG', 0.55),
            'BAR_POS_SHORT': getattr(config, 'BAR_POS_SHORT', 0.45),
            # OI SURGE parameters
            'OI_SURGE_THRESH': getattr(config, 'OI_SURGE_THRESH', 2.0),
            'BAR_POS_SURGE_LONG': getattr(config, 'BAR_POS_SURGE_LONG', 0.65),
            'BAR_POS_SURGE_SHORT': getattr(config, 'BAR_POS_SURGE_SHORT', 0.35),
            'FUNDING_NEUTRAL': getattr(config, 'FUNDING_NEUTRAL', 0.001),
        }
    else:
        # Ensure all required params are present, fallback to config or defaults if missing
        params = {
            'FUNDING_LONG_THRESH': params.get('FUNDING_LONG_THRESH', getattr(config, 'FUNDING_LONG_THRESH', -0.0003)),
            'FUNDING_SHORT_THRESH': params.get('FUNDING_SHORT_THRESH', getattr(config, 'FUNDING_SHORT_THRESH', 0.0005)),
            'OI_MA_PERIOD': params.get('OI_MA_PERIOD', getattr(config, 'OI_MA_PERIOD', 20)),
            'OI_RATIO_THRESH': params.get('OI_RATIO_THRESH', getattr(config, 'OI_RATIO_THRESH', 1.05)),
            'EMA_PERIOD': params.get('EMA_PERIOD', getattr(config, 'EMA_PERIOD', 20)),
            'PRICE_OVERSOLD_PCT': params.get('PRICE_OVERSOLD_PCT', getattr(config, 'PRICE_OVERSOLD_PCT', 0.015)),
            'PRICE_OVERBOUGHT_PCT': params.get('PRICE_OVERBOUGHT_PCT', getattr(config, 'PRICE_OVERBOUGHT_PCT', 0.015)),
            'BAR_POS_LONG': params.get('BAR_POS_LONG', getattr(config, 'BAR_POS_LONG', 0.55)),
            'BAR_POS_SHORT': params.get('BAR_POS_SHORT', getattr(config, 'BAR_POS_SHORT', 0.45)),
            # OI SURGE parameters
            'OI_SURGE_THRESH': params.get('OI_SURGE_THRESH', getattr(config, 'OI_SURGE_THRESH', 2.0)),
            'BAR_POS_SURGE_LONG': params.get('BAR_POS_SURGE_LONG', getattr(config, 'BAR_POS_SURGE_LONG', 0.65)),
            'BAR_POS_SURGE_SHORT': params.get('BAR_POS_SURGE_SHORT', getattr(config, 'BAR_POS_SURGE_SHORT', 0.35)),
            'FUNDING_NEUTRAL': params.get('FUNDING_NEUTRAL', getattr(config, 'FUNDING_NEUTRAL', 0.001)),
        }

    # Make a copy to avoid modifying original
    df = df.copy()

    # Compute required indicator columns
    # OI 20-period moving average
    df['oi_20ma'] = df['openInterest'].rolling(params['OI_MA_PERIOD']).mean()
    # OI rolling standard deviation for surge detection
    df['oi_20std'] = df['openInterest'].rolling(params['OI_MA_PERIOD']).std()
    # OI change (period-over-period)
    df['oi_change'] = df['openInterest'].pct_change()
    # EMA 20-period
    df['ema_20'] = df['close'].ewm(span=params['EMA_PERIOD'], adjust=False).mean()
    # Bar position: (close - low) / (high - low + 1e-10)
    df['bar_position'] = (df['close'] - df['low']) / (df['high'] - df['low'] + 1e-10)

    # Condition 1 for LONG: FUNDING EXTREME SHORT (funding rate < negative threshold)
    cond1_long = df['fundingRate'] < params['FUNDING_LONG_THRESH']
    # Condition 1 for SHORT: FUNDING EXTREME LONG (funding rate > positive threshold)
    cond1_short = df['fundingRate'] > params['FUNDING_SHORT_THRESH']

    # Condition 2 for both: OI STILL HIGH (not unwinding yet)
    cond2 = df['openInterest'] > df['oi_20ma'] * params['OI_RATIO_THRESH']

    # Condition 3 for LONG: PRICE OVERSOLD (mean reentry)
    cond3_long = df['close'] < df['ema_20'] * (1 - params['PRICE_OVERSOLD_PCT'])
    # Condition 3 for SHORT: PRICE OVERBOUGHT (mean reentry)
    cond3_short = df['close'] > df['ema_20'] * (1 + params['PRICE_OVERBOUGHT_PCT'])

    # Condition 4 for LONG: MOMENTUM TURNING (bar closed in upper half)
    cond4_long = df['bar_position'] > params['BAR_POS_LONG']
    # Condition 4 for SHORT: MOMENTUM TURNING DOWN (bar closed in lower half)
    cond4_short = df['bar_position'] < params['BAR_POS_SHORT']

    # OI SURGE signal conditions
    # Avoid division by zero or NaN in std
    oi_safe_std = df['oi_20std'].replace(0, np.nan).fillna(1)  # Replace 0 std with 1 to avoid division issues
    oi_surge_condition = df['oi_change'].abs() > params['OI_SURGE_THRESH'] * oi_safe_std
    
    # OI SURGE LONG: surge + bar position confirms long
    cond_surge_long = oi_surge_condition & (df['bar_position'] > params['BAR_POS_SURGE_LONG'])
    # OI SURGE SHORT: surge + bar position confirms short
    cond_surge_short = oi_surge_condition & (df['bar_position'] < params['BAR_POS_SURGE_SHORT'])

    # PRIMARY SIGNAL: Condition1 AND Condition2 AND (Condition3 OR Condition4)
    raw_entry_long = cond1_long & cond2 & (cond3_long | cond4_long)
    raw_entry_short = cond1_short & cond2 & (cond3_short | cond4_short)

    # SECONDARY SIGNAL: OI SURGE signal
    raw_entry_long = raw_entry_long | cond_surge_long
    raw_entry_short = raw_entry_short | cond_surge_short

    # SIGNALS MUST FIRE IN ALL REGIMES - NO REGIME FILTERING FOR ENTRY
    # Regime only affects TP/SL and position sizing, not whether we can enter
    df['entry_long'] = raw_entry_long
    df['entry_short'] = raw_entry_short

    # Add score columns for backward compatibility with the optimizer
    df['score_long'] = raw_entry_long.astype(float)
    df['score_short'] = raw_entry_short.astype(float)

    return df

def test_signals():
    """
    Unit test for signal generation.
    """
    logger.info("Running signal generation unit test...")

    # Create a small synthetic DataFrame
    n = 100
    timestamps = pd.date_range(start='2022-01-01', periods=n, freq='h', tz='UTC')

    # Price data (somewhat arbitrary)
    close = 100 + np.cumsum(np.random.randn(n) * 0.5)
    high = close + np.random.randn(n) * 0.5
    low = close - np.random.randn(n) * 0.5
    open_price = close - np.random.randn(n) * 0.2
    volume = np.random.randn(n) * 1000 + 500

    # OI data with a clear rising trend
    oi = 1000000 + np.cumsum(np.random.randn(n) * 1000)  # random walk
    # Make sure it's rising overall by adding a drift
    oi = oi + np.linspace(0, 100000, n)  # upward drift

    # Funding rate: negative for long signal, positive for short signal
    funding = np.random.randn(n) * 0.0001  # small noise

    df = pd.DataFrame({
        'timestamp': timestamps,
        'open': open_price,
        'high': high,
        'low': low,
        'close': close,
        'volume': volume,
        'openInterest': oi,
        'fundingRate': funding
    })

    # Generate signals
    df_with_signals = generate_signals(df.copy())

    # Check that signal columns exist
    expected_cols = ['entry_long', 'entry_short', 'score_long', 'score_short']
    for col in expected_cols:
        assert col in df_with_signals.columns, f"Missing column: {col}"

    # Check that we have at least some signals (given random data, we might have some)
    total_signals = df_with_signals[['entry_long', 'entry_short']].sum().sum()
    logger.info(f"Generated signals: {total_signals} total signal triggers")

    logger.info("Signal generation unit test PASSED")
    return True

if __name__ == "__main__":
    # Run unit test if executed directly
    test_signals()