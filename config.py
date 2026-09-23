"""
Configuration module for crypto perpetual futures backtesting system.
Contains parameter grids, constants, and default values.
"""

import os

# Data paths
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
COMBINED_DATA_PATH = os.path.join(DATA_DIR, 'combined_all.pkl')
RESULTS_DIR = os.path.join(os.path.dirname(__file__), 'optimization')

# Create directories if they don't exist
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)

# Backtesting constants
MAKER_FEE = 0.0003
TAKER_FEE = 0.0005
SLIPPAGE = 0.0002
TOTAL_FEES = MAKER_FEE + TAKER_FEE + SLIPPAGE

# Default values for signal generation (used when params not provided)
OI_MA_PERIOD = 20
OI_RATIO_THRESH = 1.05
EMA_PERIOD = 20
PRICE_OVERSOLD_PCT = 0.008
PRICE_OVERBOUGHT_PCT = 0.008
BAR_POS_LONG = 0.45
BAR_POS_SHORT = 0.55
FUNDING_LONG_THRESH = -0.0003
FUNDING_SHORT_THRESH = 0.0005
ADX_TREND_THRESH = 35  # ADX threshold above which market is considered HIGH_VOL (set to sensible value)

# Additional constants required by the backtest engine
START_DATE = '2022-09-01'
END_DATE = '2024-09-01'
INSTRUMENTS = ['SOL-USDT-PERP', 'DOGE-USDT-PERP', 'ARB-USDT-PERP', 'SUI-USDT-PERP']
MAX_CONCURRENT = 2  # increased from 1 to help trade frequency
MAX_DRAWDOWN_HALT = 0.20
MIN_BARS_BETWEEN_TRADES = 6
REGIME_CONFIRM_BARS = 2
MIN_CONFLUENCE_SCORE = 2
BULL_TP_PCT = 0.008
BULL_SL_PCT = 0.003
BULL_TIME_EXIT_BARS = 24
BEAR_TP_PCT = 0.008
BEAR_SL_PCT = 0.003
BEAR_TIME_EXIT_BARS = 24
SIDEWAYS_TP_PCT = 0.006
SIDEWAYS_SL_PCT = 0.002
SIDEWAYS_TIME_EXIT_BARS = 24
# HIGH_VOL regime parameters (new)
HIGH_VOL_SL_PCT = 0.004  # wider stop loss for volatile regime
HIGH_VOL_TP_PCT = 0.010  # wider take profit for volatile regime
HIGH_VOL_TIME_EXIT_BARS = 24
MAX_LEVERAGE = 3  # decreased from 5 to 3 as specified
MAX_POSITION_PCT = 0.20
DAILY_LOSS_LIMIT = 0.05
DD_STEP1_THRESH = 0.05
DD_STEP2_THRESH = 0.10
DD_STEP3_THRESH = 0.15
RISK_PCT_PER_TRADE = 0.005  # Default risk percentage per trade

# Fee percentages for cost model (same as the above constants)
MAKER_FEE_PCT = MAKER_FEE
TAKER_FEE_PCT = TAKER_FEE
SLIPPAGE_PCT = SLIPPAGE

# Parameter grid for optimization
PARAM_GRID = {
    "FUNDING_LONG_THRESH":  [-0.0002, -0.0003, -0.0005, -0.0008],
    "FUNDING_SHORT_THRESH": [0.0003, 0.0005, 0.0008, 0.0010],
    "OI_MA_PERIOD":         [12, 20, 24],
    "OI_RATIO_THRESH":      [1.02, 1.05, 1.08],
    "EMA_PERIOD":           [12, 20, 24],
    "PRICE_OVERSOLD_PCT":   [0.010, 0.015, 0.020],
    "PRICE_OVERBOUGHT_PCT": [0.010, 0.015, 0.020],
    "BAR_POS_LONG":         [0.50, 0.55, 0.60],
    "BAR_POS_SHORT":        [0.40, 0.45, 0.50],
    "BULL_TP_PCT":          [0.008, 0.010, 0.012, 0.014],  # updated min to 0.008
    "BULL_SL_PCT":          [0.003, 0.004, 0.005],
    "SIDEWAYS_TP_PCT":      [0.006, 0.008, 0.010, 0.012],  # updated min to 0.006
    "SIDEWAYS_SL_PCT":      [0.002, 0.0025, 0.003, 0.004],
    "BEAR_TP_PCT":          [0.008, 0.010, 0.012],  # updated min to 0.008
    "BEAR_SL_PCT":          [0.003, 0.004, 0.005],
    "RISK_PCT_PER_TRADE":   [0.005, 0.008, 0.010],
    # New parameters for dual signal approach
    "OI_SURGE_THRESH":      [1.0, 1.5, 2.0, 3.0],
    "BAR_POS_SURGE_LONG":   [0.60, 0.65, 0.70],
    "BAR_POS_SURGE_SHORT":  [0.30, 0.35, 0.40],
    "FUNDING_NEUTRAL":      [0.0005, 0.001, 0.002],
}

# Optimization settings
N_SAMPLES = 500
SEED = 42

# Create a config object that holds the configuration for backward compatibility
class _Config:
    pass

config = _Config()
config.DATA_DIR = DATA_DIR
config.COMBINED_DATA_PATH = COMBINED_DATA_PATH
config.RESULTS_DIR = RESULTS_DIR
config.MAKER_FEE = MAKER_FEE
config.TAKER_FEE = TAKER_FEE
config.SLIPPAGE = SLIPPAGE
config.TOTAL_FEES = TOTAL_FEES
config.OI_MA_PERIOD = OI_MA_PERIOD
config.OI_RATIO_THRESH = OI_RATIO_THRESH
config.EMA_PERIOD = EMA_PERIOD
config.PRICE_OVERSOLD_PCT = PRICE_OVERSOLD_PCT
config.PRICE_OVERBOUGHT_PCT = PRICE_OVERBOUGHT_PCT
config.BAR_POS_LONG = BAR_POS_LONG
config.BAR_POS_SHORT = BAR_POS_SHORT
config.FUNDING_LONG_THRESH = FUNDING_LONG_THRESH
config.FUNDING_SHORT_THRESH = FUNDING_SHORT_THRESH
config.ADX_TREND_THRESH = ADX_TREND_THRESH
config.START_DATE = START_DATE
config.END_DATE = END_DATE
config.INSTRUMENTS = INSTRUMENTS
config.MAX_CONCURRENT = MAX_CONCURRENT
config.MAX_DRAWDOWN_HALT = MAX_DRAWDOWN_HALT
config.MIN_BARS_BETWEEN_TRADES = MIN_BARS_BETWEEN_TRADES
config.REGIME_CONFIRM_BARS = REGIME_CONFIRM_BARS
config.MIN_CONFLUENCE_SCORE = MIN_CONFLUENCE_SCORE
config.BULL_SL_PCT = BULL_SL_PCT
config.BULL_TP_PCT = BULL_TP_PCT
config.BULL_TIME_EXIT_BARS = BULL_TIME_EXIT_BARS
config.BEAR_SL_PCT = BEAR_SL_PCT
config.BEAR_TP_PCT = BEAR_TP_PCT
config.BEAR_TIME_EXIT_BARS = BEAR_TIME_EXIT_BARS
config.SIDEWAYS_SL_PCT = SIDEWAYS_SL_PCT
config.SIDEWAYS_TP_PCT = SIDEWAYS_TP_PCT
config.SIDEWAYS_TIME_EXIT_BARS = SIDEWAYS_TIME_EXIT_BARS
# HIGH_VOL regime parameters
config.HIGH_VOL_SL_PCT = HIGH_VOL_SL_PCT
config.HIGH_VOL_TP_PCT = HIGH_VOL_TP_PCT
config.HIGH_VOL_TIME_EXIT_BARS = HIGH_VOL_TIME_EXIT_BARS
config.MAX_LEVERAGE = MAX_LEVERAGE
config.MAX_POSITION_PCT = MAX_POSITION_PCT
config.DAILY_LOSS_LIMIT = DAILY_LOSS_LIMIT
config.DD_STEP1_THRESH = DD_STEP1_THRESH
config.DD_STEP2_THRESH = DD_STEP2_THRESH
config.DD_STEP3_THRESH = DD_STEP3_THRESH
config.RISK_PCT_PER_TRADE = RISK_PCT_PER_TRADE
config.MAKER_FEE_PCT = MAKER_FEE_PCT
config.TAKER_FEE_PCT = TAKER_FEE_PCT
config.SLIPPAGE_PCT = SLIPPAGE_PCT
config.PARAM_GRID = PARAM_GRID
config.N_SAMPLES = N_SAMPLES
config.SEED = SEED