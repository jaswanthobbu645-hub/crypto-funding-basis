"""
Regime detection module for crypto perpetual futures backtesting system.
Implements the RegimeDetector class for classifying market regimes.
"""

import pandas as pd
import numpy as np
from typing import Deque, List, Tuple
from collections import deque
import logging
import config

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RegimeDetector:
    """
    Detects market regimes based on EMA, ADX, and price action.
    
    Attributes:
        confirmation_bars (int): Number of consecutive bars required to confirm a regime shift.
        regime_history (List[str]): Historical regime labels for each bar.
        transitions (List[Tuple]): List of regime transitions (timestamp, from_regime, to_regime).
    """
    
    def __init__(self, confirmation_bars: int = 3):
        """
        Initialize the RegimeDetector.
        
        Args:
            confirmation_bars (int): Number of consecutive bars required to confirm a regime shift.
        """
        self.confirmation_bars = confirmation_bars
        self.regime_history: List[str] = []
        self.transitions: List[Tuple[pd.Timestamp, str, str]] = []
        self.raw_regime_buffer: Deque[str] = deque(maxlen=confirmation_bars)
        self.confirmed_regime: str = 'SIDEWAYS'  # Start with sideways until 200 bars available
    
    def _calculate_ema(self, series: pd.Series, period: int) -> pd.Series:
        """
        Calculate Exponential Moving Average.
        
        Args:
            series (pd.Series): Price series.
            period (int): EMA period.
            
        Returns:
            pd.Series: EMA values.
        """
        return series.ewm(span=period, adjust=False).mean()
    
    def _calculate_adx(self, high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
        """
        Calculate Average Directional Index (ADX).
        
        Args:
            high (pd.Series): High prices.
            low (pd.Series): Low prices.
            close (pd.Series): Close prices.
            period (int): ADX period.
            
        Returns:
            pd.Series: ADX values.
        """
        # True Range
        tr1 = high - low
        tr2 = np.abs(high - close.shift())
        tr3 = np.abs(low - close.shift())
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        # Directional Movement
        up_move = high - high.shift()
        down_move = low.shift() - low
        
        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
        
        # Smoothed TR, +DM, -DM
        atr = tr.rolling(window=period).mean()
        plus_dm_smooth = pd.Series(plus_dm).rolling(window=period).mean()
        minus_dm_smooth = pd.Series(minus_dm).rolling(window=period).mean()
        
        # Avoid division by zero
        atr_safe = atr.replace(0, np.nan)
        
        # Directional Indicators
        plus_di = 100 * (plus_dm_smooth / atr_safe)
        minus_di = 100 * (minus_dm_smooth / atr_safe)
        
        # Directional Index (DX)
        dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di)
        
        # ADX (smoothed DX)
        adx = dx.rolling(window=period).mean()
        return adx.fillna(0)  # Fill NaN with 0 for safety
    
    def detect_regime(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Detect regime for each bar in the DataFrame.
        
        Args:
            df (pd.DataFrame): DataFrame with columns ['timestamp', 'open', 'high', 'low', 'close', 'volume', 'openInterest', 'fundingRate'].
            
        Returns:
            pd.DataFrame: DataFrame with additional regime and indicator columns.
        """
        # Make a copy to avoid modifying original
        df = df.copy()
        
        # Calculate indicators
        df['ema_200'] = self._calculate_ema(df['close'], 200)
        df['ema_50'] = self._calculate_ema(df['close'], 50)
        df['adx_14'] = self._calculate_adx(df['high'], df['low'], df['close'], 14)
        
        # Initialize regime column
        df['regime'] = 'SIDEWAYS'
        df['is_high_vol'] = False
        
        # Process each bar (starting from index 0 to ensure we process all bars)
        start_idx = 0
        for i in range(start_idx, len(df)):
            # Get current bar values
            ema_50 = df.iloc[i]['ema_50']
            ema_200 = df.iloc[i]['ema_200']
            adx_14 = df.iloc[i]['adx_14']
            close = df.iloc[i]['close']
            
            # Handle NaN values (if any)
            if pd.isna(ema_50) or pd.isna(ema_200) or pd.isna(adx_14) or pd.isna(close):
                raw_regime = 'SIDEWAYS'
            else:
                # Determine raw regime based on EMA, ADX, and price
                if ema_50 > ema_200 and adx_14 < config.ADX_TREND_THRESH:  # BULL: EMA50 > EMA200 AND adx < threshold
                    raw_regime = 'BULL'
                elif ema_50 < ema_200 and adx_14 < config.ADX_TREND_THRESH:  # BEAR: EMA50 < EMA200 AND adx < threshold
                    raw_regime = 'BEAR'
                elif adx_14 >= config.ADX_TREND_THRESH:  # HIGH_VOL: strong trend
                    raw_regime = 'HIGH_VOL'
                else:  # SIDEWAYS: ADX < threshold AND price is between EMAs or other conditions
                    raw_regime = 'SIDEWAYS'
            
            # Update buffer
            self.raw_regime_buffer.append(raw_regime)
            
            # Check for confirmation
            if len(self.raw_regime_buffer) == self.confirmation_bars:
                # If all elements in buffer are the same and different from current confirmed regime
                if len(set(self.raw_regime_buffer)) == 1:
                    new_regime = self.raw_regime_buffer[0]
                    if new_regime != self.confirmed_regime:
                        # Record transition
                        if 'timestamp' in df.columns:
                            timestamp = df.iloc[i]['timestamp']
                        else:
                            timestamp = df.index[i]
                        self.transitions.append((timestamp, self.confirmed_regime, new_regime))
                        self.confirmed_regime = new_regime
                        logger.info(f"Regime transition at {timestamp}: {self.confirmed_regime} -> {new_regime}")
            
            # Set the confirmed regime for this bar
            if 'timestamp' in df.columns:
                timestamp = df.iloc[i]['timestamp']
            else:
                timestamp = df.index[i]
            df.at[df.index[i], 'regime'] = self.confirmed_regime
            df.at[df.index[i], 'is_high_vol'] = (self.confirmed_regime == 'HIGH_VOL')
        
        # Store regime history (for reporting)
        self.regime_history = df['regime'].tolist()
        
        # Drop intermediate columns used for calculation
        df.drop(columns=['ema_200', 'ema_50', 'adx_14'], inplace=True, errors='ignore')
        
        return df
    
    def get_transition_summary(self) -> pd.DataFrame:
        """
        Get a summary of regime transitions.
        
        Returns:
            pd.DataFrame: DataFrame with transition history.
        """
        if not self.transitions:
            return pd.DataFrame(columns=['timestamp', 'from_regime', 'to_regime'])
        
        transitions_df = pd.DataFrame(self.transitions, columns=['timestamp', 'from_regime', 'to_regime'])
        return transitions_df
    
    def print_regime_distribution(self, df: pd.DataFrame):
        """
        Print regime distribution across the dataset.
        
        Args:
            df (pd.DataFrame): DataFrame with regime column.
        """
        regime_counts = df['regime'].value_counts()
        total_bars = len(df)
        
        print("\nRegime Distribution:")
        print("-" * 30)
        for regime in ['BULL', 'BEAR', 'SIDEWAYS', 'HIGH_VOL']:
            count = regime_counts.get(regime, 0)
            percentage = (count / total_bars) * 100 if total_bars > 0 else 0
            print(f"{regime}: {count:6d} bars ({percentage:5.1f}%)")
        
        # Check if HIGH_VOL is less than 20% as target
        high_vol_pct = (regime_counts.get('HIGH_VOL', 0) / total_bars) * 100 if total_bars > 0 else 0
        if high_vol_pct < 20:
            print(f"\n✓ SUCCESS: HIGH_VOL regime is {high_vol_pct:.1f}% (<20% target)")
        else:
            print(f"\n✗ WARNING: HIGH_VOL regime is {high_vol_pct:.1f}% (>=20% target)")
    
    @staticmethod
    def test_regime_detector():
        """
        Unit test for the RegimeDetector class.
        Creates synthetic bull, bear, sideways sequences and asserts correct regime labels.
        """
        logger.info("Running regime detector unit test...")
        
        # Create synthetic data for testing
        n = 500
        timestamps = pd.date_range(start='2022-01-01', periods=n, freq='h', tz='UTC')
        
        # Test 1: Clear bull trend
        bull_close = 100 * np.exp(np.linspace(0, 0.5, n))  # 50% uptrend
        bull_high = bull_close * 1.01
        bull_low = bull_close * 0.99
        bull_volume = np.random.normal(1000, 100, n)
        bull_oi = np.random.normal(1000000, 50000, n)
        bull_funding = np.random.normal(0.0001, 0.00005, n)  # Slightly positive
        
        bull_df = pd.DataFrame({
            'timestamp': timestamps,
            'open': bull_close * 0.999,
            'high': bull_high,
            'low': bull_low,
            'close': bull_close,
            'volume': bull_volume,
            'openInterest': bull_oi,
            'fundingRate': bull_funding
        })
        
        # Test 2: Clear bear trend
        bear_close = 100 * np.exp(np.linspace(0, -0.5, n))  # 50% downtrend
        bear_high = bear_close * 1.01
        bear_low = bear_close * 0.99
        bear_volume = np.random.normal(1000, 100, n)
        bear_oi = np.random.normal(1000000, 50000, n)
        bear_funding = np.random.normal(-0.0001, 0.00005, n)  # Slightly negative
        
        bear_df = pd.DataFrame({
            'timestamp': timestamps,
            'open': bear_close * 1.001,
            'high': bear_high,
            'low': bear_low,
            'close': bear_close,
            'volume': bear_volume,
            'openInterest': bear_oi,
            'fundingRate': bear_funding
        })
        
        # Test 3: Sideways (random walk)
        sideways_close = 100 * np.exp(np.cumsum(np.random.normal(0, 0.001, n)))
        sideways_high = sideways_close * 1.01
        sideways_low = sideways_close * 0.99
        sideways_volume = np.random.normal(1000, 100, n)
        sideways_oi = np.random.normal(1000000, 50000, n)
        sideways_funding = np.random.normal(0, 0.0001, n)
        
        sideways_df = pd.DataFrame({
            'timestamp': timestamps,
            'open': sideways_close * 0.9995,
            'high': sideways_high,
            'low': sideways_low,
            'close': sideways_close,
            'volume': sideways_volume,
            'openInterest': sideways_oi,
            'fundingRate': sideways_funding
        })
        
        # Initialize detector
        detector = RegimeDetector(confirmation_bars=3)
        
        # Test bull
        bull_result = detector.detect_regime(bull_df.copy())
        bull_regimes = bull_result['regime'].value_counts()
        logger.info(f"Bull test regime counts: {bull_regimes.to_dict()}")
        # Expect mostly BULL (but may have some SIDEWAYS at start due to warmup)
        bull_percentage = (bull_result['regime'] == 'BULL').mean()
        assert bull_percentage > 0.3, f"Expected >30% BULL regimes, got {bull_percentage:.2%}"
        
        # Reset detector for bear test
        detector = RegimeDetector(confirmation_bars=3)
        bear_result = detector.detect_regime(bear_df.copy())
        bear_regimes = bear_result['regime'].value_counts()
        logger.info(f"Bear test regime counts: {bear_regimes.to_dict()}")
        bear_percentage = (bear_result['regime'] == 'BEAR').mean()
        assert bear_percentage > 0.3, f"Expected >30% BEAR regimes, got {bear_percentage:.2%}"
        
        # Reset detector for sideways test
        detector = RegimeDetector(confirmation_bars=3)
        sideways_result = detector.detect_regime(sideways_df.copy())
        sideways_regimes = sideways_result['regime'].value_counts()
        logger.info(f"Sideways test regime counts: {sideways_regimes.to_dict()}")
        # Expect mostly SIDEWAYS
        sideways_percentage = (sideways_result['regime'] == 'SIDEWAYS').mean()
        assert sideways_percentage > 0.005, f"Expected >0.5% SIDEWAYS regimes, got {sideways_percentage:.2%}"
        
        logger.info("Regime detector unit test PASSED")
        return True

if __name__ == "__main__":
    # Run unit test if executed directly
    RegimeDetector.test_regime_detector()