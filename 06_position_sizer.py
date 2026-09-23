"""
Position sizer module for crypto perpetual futures backtesting system.
Implements position sizing and risk management logic.
"""

import pandas as pd
import numpy as np
import logging
from typing import Tuple, List, Dict
from config import config

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PositionSizer:
    """
    Calculates position sizes based on risk management rules.
    
    Attributes:
        params (Dict): Configuration parameters for position sizing.
    """
    
    def __init__(self, params: Dict = None):
        """
        Initialize the PositionSizer.
        
        Args:
            params (Dict): Configuration parameters. If None, uses config.
        """
        if params is None:
            self.params = {
                'RISK_PCT_PER_TRADE': config.RISK_PCT_PER_TRADE,
                'MAX_LEVERAGE': config.MAX_LEVERAGE,
                'MAX_CONCURRENT': config.MAX_CONCURRENT,
                'MAX_POSITION_PCT': config.MAX_POSITION_PCT,
                'MIN_BARS_BETWEEN_TRADES': config.MIN_BARS_BETWEEN_TRADES,
                'MAX_DRAWDOWN_HALT': config.MAX_DRAWDOWN_HALT,
                'DAILY_LOSS_LIMIT': config.DAILY_LOSS_LIMIT,
                'DD_STEP1_THRESH': config.DD_STEP1_THRESH,
                'DD_STEP2_THRESH': config.DD_STEP2_THRESH,
                'DD_STEP3_THRESH': config.DD_STEP3_THRESH
            }
        else:
            self.params = {
                'RISK_PCT_PER_TRADE': params.get('RISK_PCT_PER_TRADE', config.RISK_PCT_PER_TRADE),
                'MAX_LEVERAGE': params.get('MAX_LEVERAGE', config.MAX_LEVERAGE),
                'MAX_CONCURRENT': params.get('MAX_CONCURRENT', config.MAX_CONCURRENT),
                'MAX_POSITION_PCT': params.get('MAX_POSITION_PCT', config.MAX_POSITION_PCT),
                'MIN_BARS_BETWEEN_TRADES': params.get('MIN_BARS_BETWEEN_TRADES', config.MIN_BARS_BETWEEN_TRADES),
                'MAX_DRAWDOWN_HALT': params.get('MAX_DRAWDOWN_HALT', config.MAX_DRAWDOWN_HALT),
                'DAILY_LOSS_LIMIT': params.get('DAILY_LOSS_LIMIT', config.DAILY_LOSS_LIMIT),
                'DD_STEP1_THRESH': params.get('DD_STEP1_THRESH', config.DD_STEP1_THRESH),
                'DD_STEP2_THRESH': params.get('DD_STEP2_THRESH', config.DD_STEP2_THRESH),
                'DD_STEP3_THRESH': params.get('DD_STEP3_THRESH', config.DD_STEP3_THRESH)
            }
    
    def calculate_size(self, equity: float, regime: str, current_dd: float, 
                     open_positions: List[Dict], sl_pct: float, instrument: str) -> Tuple[float, float, float]:
        """
        Calculate position size based on risk parameters.
        
        Args:
            equity (float): Current account equity.
            regime (str): Current market regime ('BULL', 'BEAR', 'SIDEWAYS', 'HIGH_VOL').
            current_dd (float): Current drawdown as a fraction (e.g., 0.05 for 5%).
            open_positions (List[Dict]): List of currently open positions.
            sl_pct (float): Stop loss percentage for this trade.
            instrument (str): Instrument being traded.
            
        Returns:
            Tuple[float, float, float]: (size_usd, leverage, margin_required)
        """
        # Check if trading is halted due to drawdown
        if current_dd >= self.params['MAX_DRAWDOWN_HALT']:
            logger.warning(f"Trading halted due to drawdown {current_dd:.2%} >= {self.params['MAX_DRAWDOWN_HALT']:.2%}")
            return 0.0, 0.0, 0.0
        
        # Base sizing: risk amount per trade
        risk_amount = equity * self.params['RISK_PCT_PER_TRADE']
        
        # Avoid division by zero or invalid SL
        if sl_pct <= 0:
            logger.warning(f"Invalid stop loss percentage: {sl_pct}")
            return 0.0, 0.0, 0.0
        
        # Base size in USD (notional)
        base_size = risk_amount / sl_pct
        
        # Apply regime multiplier
        regime_multiplier = 1.0
        if regime == 'BULL':
            regime_multiplier = 1.5
        elif regime == 'SIDEWAYS':
            regime_multiplier = 0.75
        elif regime == 'BEAR':
            regime_multiplier = 1.0
        elif regime == 'HIGH_VOL':
            regime_multiplier = 0.5  # Already handled in engine, but keep for consistency
        
        size = base_size * regime_multiplier
        
        # Apply drawdown step-down
        if current_dd > self.params['DD_STEP3_THRESH']:
            size *= 0.25
        elif current_dd > self.params['DD_STEP2_THRESH']:
            size *= 0.50
        elif current_dd > self.params['DD_STEP1_THRESH']:
            size *= 0.75
        
        # Apply leverage cap
        # Notional size cannot exceed equity * MAX_LEVERAGE
        max_notional_by_leverage = equity * self.params['MAX_LEVERAGE']
        if size > max_notional_by_leverage:
            size = max_notional_by_leverage
        
        # Apply max position cap (percentage of equity)
        max_position_usd = equity * self.params['MAX_POSITION_PCT']
        if size > max_position_usd:
            size = max_position_usd
        
        # Apply correlation cap: reduce size if we already have positions in correlated instruments
        # For simplicity, we'll consider all instruments as correlated if they have signals in the same regime
        # In a more sophisticated model, we'd use actual correlation coefficients
        correlated_positions = 0
        for pos in open_positions:
            # Simple approach: count positions in same regime direction
            # A more sophisticated approach would check actual price correlation
            if pos.get('instrument') != instrument:  # Don't count same instrument
                correlated_positions += 1
        
        if correlated_positions >= 2:  # If we already have 2+ other positions
            size *= 0.7  # Reduce by 30%
        
        # Calculate leverage and margin required
        leverage = size / equity if equity > 0 else 0
        # Ensure leverage doesn't exceed MAX_LEVERAGE (should already be capped by size calculation)
        leverage = min(leverage, self.params['MAX_LEVERAGE'])
        margin_required = size / leverage if leverage > 0 else 0
        
        # Final safety checks
        if size < 0:
            size = 0
        if leverage < 0:
            leverage = 0
        if margin_required < 0:
            margin_required = 0
        
        logger.debug(f"Position sizing: equity=${equity:.2f}, regime={regime}, DD={current_dd:.2%}, "
                    f"risk_amount=${risk_amount:.2f}, base_size=${base_size:.2f}, final_size=${size:.2f}, "
                    f"leverage={leverage:.2f}x, margin=${margin_required:.2f}")
        
        return size, leverage, margin_required
    
    def check_risk_limits(self, equity: float, open_positions: List[Dict]) -> Tuple[bool, str]:
        """
        Check if we can open a new position based on risk limits.
        
        Args:
            equity (float): Current account equity.
            open_positions (List[Dict]): List of currently open positions.
            
        Returns:
            Tuple[bool, str]: (can_trade, reason_if_not)
        """
        # Check concurrent position limit
        if len(open_positions) >= self.params['MAX_CONCURRENT']:
            return False, f"Max concurrent positions reached ({len(open_positions)} >= {self.params['MAX_CONCURRENT']})"
        
        # Additional checks could go here (daily loss limit, etc.)
        # These would typically be handled in the main engine based on daily PnL
        
        return True, "OK"

def test_position_sizer():
    """
    Unit test for the PositionSizer.
    """
    logger.info("Running position sizer unit test...")
    
    # Create a position sizer with default parameters
    position_sizer = PositionSizer()
    
    # Test base case
    equity = 100000.0
    regime = 'SIDEWAYS'
    current_dd = 0.0  # 0% drawdown
    open_positions = []  # No open positions
    sl_pct = 0.01  # 1% stop loss
    instrument = 'SOL-USDT-PERP'
    
    size, leverage, margin = position_sizer.calculate_size(
        equity, regime, current_dd, open_positions, sl_pct, instrument
    )
    
    # Expected calculations:
    # RISK_PCT_PER_TRADE = 0.01 (1%)
    # risk_amount = 100000 * 0.01 = 1000
    # base_size = 1000 / 0.01 = 100,000
    # SIDEWAYS multiplier = 0.75 -> size = 100,000 * 0.75 = 75,000
    # No drawdown adjustment
    # LEVERAGE cap: MAX_LEVERAGE = 5, so max notional = 100,000 * 5 = 500,000 -> our 75,000 is fine
    # POSITION cap: MAX_POSITION_PCT = 0.20, so max position = 100,000 * 0.20 = 20,000
    # Wait! Our size (75,000) exceeds the position cap (20,000), so it should be capped at 20,000
    # Then leverage = size / equity = 20,000 / 100,000 = 0.2x
    # Margin required = size / leverage = 20,000 / 0.2 = 100,000 (which equals equity, makes sense)
    
    expected_size = 20000.0  # Capped by MAX_POSITION_PCT
    expected_leverage = 0.2
    expected_margin = 100000.0
    
    assert abs(size - expected_size) < 0.01, f"Expected size {expected_size}, got {size}"
    assert abs(leverage - expected_leverage) < 0.001, f"Expected leverage {expected_leverage}, got {leverage}"
    assert abs(margin - expected_margin) < 0.01, f"Expected margin {expected_margin}, got {margin}"
    
    # Test BULL regime (should be larger)
    regime = 'BULL'
    size, leverage, margin = position_sizer.calculate_size(
        equity, regime, current_dd, open_positions, sl_pct, instrument
    )
    # BULL multiplier = 1.5
    # base_size = 100,000 (as before)
    # size before caps = 100,000 * 1.5 = 150,000
    # Still capped by position limit at 20,000
    # So should be same as SIDEWAYS? Wait no, let's recalculate:
    # Actually, the position cap is applied AFTER the regime multiplier, so:
    # risk_amount = 1,000
    # base_size = 1,000 / 0.01 = 100,000
    # BULL multiplier = 1.5 -> 150,000
    # Position cap = 20,000 -> size = 20,000
    # So BULL and SIDEWAYS give same size when position cap is binding
    
    # Let's test with a smaller risk percentage to avoid hitting the cap immediately
    position_sizer_low_risk = PositionSizer({'RISK_PCT_PER_TRADE': 0.005})  # 0.5%
    size, leverage, margin = position_sizer_low_risk.calculate_size(
        equity, regime, current_dd, open_positions, sl_pct, instrument
    )
    # risk_amount = 100,000 * 0.005 = 500
    # base_size = 500 / 0.01 = 50,000
    # BULL multiplier = 1.5 -> 75,000
    # Position cap = 20,000 -> still capped! 
    # We need to go even lower...
    
    position_sizer_very_low_risk = PositionSizer({'RISK_PCT_PER_TRADE': 0.001})  # 0.1%
    size, leverage, margin = position_sizer_very_low_risk.calculate_size(
        equity, regime, current_dd, open_positions, sl_pct, instrument
    )
    # risk_amount = 100,000 * 0.001 = 100
    # base_size = 100 / 0.01 = 10,000
    # BULL multiplier = 1.5 -> 15,000
    # This is under position cap of 20,000, so size should be 15,000
    # SIDEWAYS would be: 10,000 * 0.75 = 7,500
    
    size_bull, leverage_bull, margin_bull = position_sizer_very_low_risk.calculate_size(
        equity, 'BULL', current_dd, open_positions, sl_pct, instrument
    )
    size_sideways, leverage_sideways, margin_sideways = position_sizer_very_low_risk.calculate_size(
        equity, 'SIDEWAYS', current_dd, open_positions, sl_pct, instrument
    )
    
    assert abs(size_bull - 15000.0) < 0.01, f"Expected BULL size 15000, got {size_bull}"
    assert abs(size_sideways - 7500.0) < 0.01, f"Expected SIDEWAYS size 7500, got {size_sideways}"
    assert size_bull > size_sideways, "BULL size should be larger than SIDEWAYS size"
    
    # Test drawdown step-down
    size_dd_low, _, _ = position_sizer_very_low_risk.calculate_size(
        equity, 'SIDEWAYS', 0.03, open_positions, sl_pct, instrument  # 3% DD
    )
    size_dd_medium, _, _ = position_sizer_very_low_risk.calculate_size(
        equity, 'SIDEWAYS', 0.08, open_positions, sl_pct, instrument  # 8% DD
    )
    size_dd_high, _, _ = position_sizer_very_low_risk.calculate_size(
        equity, 'SIDEWAYS', 0.12, open_positions, sl_pct, instrument  # 12% DD
    )
    size_dd_very_high, _, _ = position_sizer_very_low_risk.calculate_size(
        equity, 'SIDEWAYS', 0.18, open_positions, sl_pct, instrument  # 18% DD
    )
    
    # With 0.1% risk: base_size = 10,000, SIDEWAYS mult = 0.75 -> 7,500
    # DD 3%: no step down -> 7,500
    # DD 8%: step down to 0.5 -> 7,500 * 0.5 = 3,750
    # DD 12%: step down to 0.25 -> 7,500 * 0.25 = 1,875
    # DD 18%: step down to 0.25 -> 7,500 * 0.25 = 1,875 (same as 12%, next step at 20% halt)
    
    assert abs(size_dd_low - 7500.0) < 0.01, f"Expected size 7500 at 3% DD, got {size_dd_low}"
    assert abs(size_dd_medium - 3750.0) < 0.01, f"Expected size 3750 at 8% DD, got {size_dd_medium}"
    assert abs(size_dd_high - 1875.0) < 0.01, f"Expected size 1875 at 12% DD, got {size_dd_high}"
    assert abs(size_dd_very_high - 1875.0) < 0.01, f"Expected size 1875 at 18% DD, got {size_dd_very_high}"
    
    # Test halt at max drawdown
    size_halt, _, _ = position_sizer_very_low_risk.calculate_size(
        equity, 'SIDEWAYS', 0.25, open_positions, sl_pct, instrument  # 25% DD > 20% halt
    )
    assert size_halt == 0.0, f"Expected size 0 at 25% DD (halt), got {size_halt}"
    
    # Test risk limits check
    can_trade, reason = position_sizer.check_risk_limits(equity, [])
    assert can_trade == True, f"Should be able to trade with no positions, got reason: {reason}"
    
    # Create fake open positions to test limit
    fake_positions = [{'instrument': 'SOL-USDT-PERP'}, {'instrument': 'DOGE-USDT-PERP'}, 
                     {'instrument': 'ARB-USDT-PERP'}]  # 3 positions
    can_trade, reason = position_sizer.check_risk_limits(equity, fake_positions)
    assert can_trade == False, f"Should not be able to trade at max positions, got reason: {reason}"
    assert "Max concurrent positions reached" in reason
    
    logger.info("Position sizer unit test PASSED")
    return True

if __name__ == "__main__":
    # Run unit test if executed directly
    test_position_sizer()