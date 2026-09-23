"""
Cost model module for crypto perpetual futures backtesting system.
Calculates fees, slippage, and funding costs.
"""

import pandas as pd
import numpy as np
import logging
from typing import Dict, Tuple
from config import config

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CostModel:
    """
    Calculates trading costs including fees, slippage, and funding.
    
    Attributes:
        params (Dict): Configuration parameters for cost calculation.
    """
    
    def __init__(self, params: Dict = None):
        """
        Initialize the CostModel.
        
        Args:
            params (Dict): Configuration parameters. If None, uses config.
        """
        if params is None:
            self.params = {
                'MAKER_FEE_PCT': config.MAKER_FEE_PCT,
                'TAKER_FEE_PCT': config.TAKER_FEE_PCT,
                'SLIPPAGE_PCT': config.SLIPPAGE_PCT
            }
        else:
            self.params = {
                'MAKER_FEE_PCT': params.get('MAKER_FEE_PCT', config.MAKER_FEE_PCT),
                'TAKER_FEE_PCT': params.get('TAKER_FEE_PCT', config.TAKER_FEE_PCT),
                'SLIPPAGE_PCT': params.get('SLIPPAGE_PCT', config.SLIPPAGE_PCT)
            }
    
    def calculate_trade_cost(self, entry_price: float, exit_price: float, size: float, 
                           direction: str, entry_time: pd.Timestamp, exit_time: pd.Timestamp,
                           funding_series: pd.Series) -> Dict[str, float]:
        """
        Calculate the cost breakdown for a single trade.
        
        Args:
            entry_price (float): Entry price.
            exit_price (float): Exit price.
            size (float): Position size in USD (notional).
            direction (str): 'LONG' or 'SHORT'.
            entry_time (pd.Timestamp): Entry timestamp.
            exit_time (pd.Timestamp): Exit timestamp.
            funding_series (pd.Series): Series of funding rates indexed by timestamp.
            
        Returns:
            Dict[str, float]: Dictionary containing cost components and PnL.
        """
        # Calculate gross PnL
        if direction == 'LONG':
            gross_pnl = size * (exit_price / entry_price - 1)
        elif direction == 'SHORT':
            gross_pnl = size * (entry_price / exit_price - 1)
        else:
            raise ValueError("Direction must be 'LONG' or 'SHORT'")
        
        # Fees: entry fee (maker) and exit fee (taker)
        entry_fee = size * self.params['MAKER_FEE_PCT']
        exit_fee = size * self.params['TAKER_FEE_PCT']
        
        # Slippage
        slippage = size * self.params['SLIPPAGE_PCT']
        
        # Funding cost: calculate funding paid/received over the trade duration
        # We need to get the funding rates that occurred between entry_time and exit_time
        # Funding is paid every 8 hours, but we have a series with whatever frequency we have (hourly after ffill)
        # We'll filter the funding series for timestamps between entry and exit (inclusive of entry, exclusive of exit? Typically funding is paid at the end of the interval)
        # We'll assume that at each timestamp in the series, we pay/receive funding for the period since the last funding payment.
        # However, for simplicity, we'll assume the funding rate in the series is the rate for the upcoming period and we accrue it continuously.
        # Since our data is hourly and funding is every 8 hours, we have the same rate for 8 hours.
        # We'll calculate the number of hours the trade was open and apply the funding rate accordingly.
        
        # Ensure funding_series is a Series with DatetimeIndex
        if not isinstance(funding_series.index, pd.DatetimeIndex):
            # If it's a column, we need to set the index to timestamp
            # This function expects funding_series to be indexed by timestamp
            raise ValueError("funding_series must have a DatetimeIndex")
        
        # Filter funding rates that occurred during the trade
        mask = (funding_series.index >= entry_time) & (funding_series.index < exit_time)
        funding_during_trade = funding_series.loc[mask]
        
        # Calculate funding cost: for each funding interval, we pay/receive: size * funding_rate
        # Since our data is hourly and funding is every 8 hours, we have the same rate for 8 hours.
        # But we don't know the exact interval length in the series. We'll assume each timestamp represents a funding payment.
        # Actually, in our data, we have hourly data with funding rate forward filled to hourly.
        # So we have 8 identical values for each funding payment.
        # To avoid overcounting, we should only count each unique funding payment once.
        # We'll resample to 8h to get the actual funding payments.
        try:
            # Resample to 8h taking the last value in each interval (which is the funding rate for that interval)
            funding_8h = funding_during_trade.resample('8h').last()
            # Now calculate the cost: size * funding_rate for each 8h interval
            funding_cost = size * (funding_8h * 1).sum()  # Assuming the rate is per 8h period
        except:
            # If resample fails, we'll do a simple approximation: average funding rate * hours / 8
            hours = (exit_time - entry_time).total_seconds() / 3600
            if hours > 0 and len(funding_during_trade) > 0:
                avg_funding = funding_during_trade.mean()
                funding_cost = size * avg_funding * (hours / 8)
            else:
                funding_cost = 0.0
        
        # For LONG: positive funding rate means you pay (cost)
        # For SHORT: positive funding rate means you receive (negative cost)
        if direction == 'SHORT':
            funding_cost = -funding_cost
        
        # Total cost
        total_cost = entry_fee + exit_fee + slippage + abs(funding_cost)  # Note: funding_cost can be negative (profit) for shorts, but we want the magnitude of cost? 
        # Actually, we want to subtract funding cost from gross PnL to get net PnL.
        # So we'll keep funding_cost as is (can be negative) and then:
        net_pnl = gross_pnl - entry_fee - exit_fee - slippage - funding_cost
        
        # However, the spec says: net_pnl = gross_pnl - total_cost, where total_cost includes funding_cost as a positive cost.
        # Let's redefine: total_cost = entry_fee + exit_fee + slippage + abs(funding_cost)  [always a cost]
        # But then for a short, if funding is positive, you receive money, which is a negative cost (i.e., profit).
        # So it's better to keep funding_cost signed and then:
        # net_pnl = gross_pnl - (entry_fee + exit_fee + slippage) - funding_cost
        # where funding_cost is what you pay (positive) or receive (negative).
        #
        # We'll follow the spec: 
        #   total_cost = entry_fee + exit_fee + slippage + sum(funding_costs)
        #   net_pnl = gross_pnl - total_cost
        # where funding_costs are positive if you pay, negative if you receive.
        #
        # In our calculation above, we have:
        #   For LONG: funding_cost = size * sum(funding_rate)  [you pay if rate positive]
        #   For SHORT: funding_cost = - size * sum(funding_rate) [you pay if rate negative? Let's derive]
        #
        # Actually, for a short position:
        #   If funding rate is positive, shorts pay longs -> you (short) pay -> cost = size * funding_rate
        #   If funding rate is negative, shorts receive -> you receive -> cost = size * funding_rate (negative)
        # So for short, funding_cost = size * funding_rate (same as long) but then we have to adjust the sign in the PnL?
        #
        # Let me clarify:
        #   The funding rate is defined as: rate = (long pays short) / notional
        #   So if rate > 0, longs pay shorts.
        #   Therefore, for a long position, you pay: -size * rate
        #   For a short position, you receive: +size * rate
        #
        # So the cost (what you pay out) for:
        #   long:  -size * rate
        #   short: +size * rate   [because if rate>0, you receive money, which is negative cost]
        #
        # Alternatively, we can think of the funding PnL as:
        #   long:  -size * rate
        #   short: +size * rate
        #
        # So in the gross PnL, we have only the price change. Then we subtract fees and slippage, and then add the funding PnL.
        # But the spec says: net_pnl = gross_pnl - total_cost, where total_cost includes funding costs.
        # So if we define total_cost as the total amount of money you pay out (positive) or receive (negative) due to funding, then:
        #   total_cost = entry_fee + exit_fee + slippage + funding_cost_out
        #   where funding_cost_out = 
        #        for long:  size * rate   [you pay this if rate>0]
        #        for short: -size * rate  [you pay this if rate<0? Let's see: if rate<0, shorts pay longs? No, the formula is: longs pay shorts when rate>0.
        #   Actually, the definition is: rate = (interest longs - interest shorts) / notional
        #   and then at funding time, longs pay shorts: rate * notional.
        #   So if rate>0, longs pay, shorts receive.
        #   Therefore, for a long: you pay rate * notional -> cost = +size * rate
        #   for a short: you receive rate * notional -> cost = -size * rate (because receiving money reduces your cost)
        #
        # So we can compute:
        #   funding_cost_out = size * rate * (1 if long else -1)
        #
        # Then total_cost = entry_fee + exit_fee + slippage + funding_cost_out
        # and net_pnl = gross_pnl - total_cost
        #
        # Let's do that.
        #
        # We'll recalculate funding_cost_out properly.
        #
        # We'll compute the sum of funding rates over the trade (each rate is for 8 hours) and then multiply by size and by 1 for long, -1 for short.
        #
        # We already have funding_during_trade (hourly, but we resampled to 8h to avoid overcounting).
        # Let's use the resampled 8h funding rates.
        try:
            funding_8h = funding_during_trade.resample('8h').last()
            # Sum of funding rates over the 8h intervals
            sum_funding_rates = funding_8h.sum()
        except:
            hours = (exit_time - entry_time).total_seconds() / 3600
            if hours > 0 and len(funding_during_trade) > 0:
                avg_funding = funding_during_trade.mean()
                sum_funding_rates = avg_funding * (hours / 8)
            else:
                sum_funding_rates = 0.0
        
        if direction == 'LONG':
            funding_cost_out = size * sum_funding_rates
        else:  # SHORT
            funding_cost_out = -size * sum_funding_rates
        
        # Now total cost
        total_cost = entry_fee + exit_fee + slippage + funding_cost_out
        net_pnl = gross_pnl - total_cost
        
        return {
            'gross_pnl': gross_pnl,
            'entry_fee': entry_fee,
            'exit_fee': exit_fee,
            'slippage': slippage,
            'funding_cost': funding_cost_out,
            'total_cost': total_cost,
            'net_pnl': net_pnl
        }
    
    def monthly_cost_summary(self, trades_df: pd.DataFrame) -> Dict[str, float]:
        """
        Calculate monthly cost summary from a DataFrame of trades.
        
        Args:
            trades_df (pd.DataFrame): DataFrame with trade data, must have columns:
                'entry_fee', 'exit_fee', 'slippage', 'funding_cost', 'gross_pnl', 'net_pnl'
                
        Returns:
            Dict[str, float]: Summary statistics.
        """
        if trades_df.empty:
            return {
                'avg_cost_per_trade': 0.0,
                'total_fees': 0.0,
                'total_slippage': 0.0,
                'total_funding': 0.0,
                'cost_as_pct_of_gross': 0.0
            }
        
        total_fees = trades_df['entry_fee'].sum() + trades_df['exit_fee'].sum()
        total_slippage = trades_df['slippage'].sum()
        total_funding = trades_df['funding_cost'].sum()
        total_cost = trades_df['total_cost'].sum()
        total_gross_pnl = trades_df['gross_pnl'].sum()
        
        avg_cost_per_trade = total_cost / len(trades_df) if len(trades_df) > 0 else 0.0
        cost_as_pct_of_gross = (total_cost / total_gross_pnl * 100) if total_gross_pnl != 0 else 0.0
        
        return {
            'avg_cost_per_trade': avg_cost_per_trade,
            'total_fees': total_fees,
            'total_slippage': total_slippage,
            'total_funding': total_funding,
            'cost_as_pct_of_gross': cost_as_pct_of_gross
        }

def test_cost_model():
    """
    Unit test for the CostModel.
    """
    logger.info("Running cost model unit test...")
    
    # Create a cost model with default parameters
    cost_model = CostModel()
    
    # Test a long trade
    entry_price = 100.0
    exit_price = 110.0  # 10% gain
    size = 1000.0  # $1000 notional
    direction = 'LONG'
    entry_time = pd.Timestamp('2022-01-01 00:00:00', tz='UTC')
    exit_time = pd.Timestamp('2022-01-01 08:00:00', tz='UTC')  # 8 hours later, exactly one funding interval
    
    # Create a funding series with one 8h interval
    funding_index = pd.date_range(start='2022-01-01 00:00:00', end='2022-01-01 08:00:00', freq='H', tz='UTC')
    # Funding rate of 0.01% (0.0001) for the 8h period
    funding_rates = pd.Series([0.0001] * len(funding_index), index=funding_index)
    
    # Calculate cost
    cost_dict = cost_model.calculate_trade_cost(
        entry_price, exit_price, size, direction, entry_time, exit_time, funding_rates
    )
    
    # Expected calculations:
    # gross_pnl = 1000 * (110/100 - 1) = 1000 * 0.1 = 100
    # entry_fee = 1000 * 0.0003 = 0.3
    # exit_fee = 1000 * 0.0005 = 0.5
    # slippage = 1000 * 0.0002 = 0.2
    # funding_cost: for long, we pay if rate positive -> size * rate = 1000 * 0.0001 = 0.1
    # total_cost = 0.3 + 0.5 + 0.2 + 0.1 = 1.1
    # net_pnl = 100 - 1.1 = 98.9
    
    assert abs(cost_dict['gross_pnl'] - 100.0) < 0.01, f"Expected gross_pnl 100, got {cost_dict['gross_pnl']}"
    assert abs(cost_dict['entry_fee'] - 0.3) < 0.001, f"Expected entry_fee 0.3, got {cost_dict['entry_fee']}"
    assert abs(cost_dict['exit_fee'] - 0.5) < 0.001, f"Expected exit_fee 0.5, got {cost_dict['exit_fee']}"
    assert abs(cost_dict['slippage'] - 0.2) < 0.001, f"Expected slippage 0.2, got {cost_dict['slippage']}"
    assert abs(cost_dict['funding_cost'] - 0.1) < 0.001, f"Expected funding_cost 0.1, got {cost_dict['funding_cost']}"
    assert abs(cost_dict['total_cost'] - 1.1) < 0.001, f"Expected total_cost 1.1, got {cost_dict['total_cost']}"
    assert abs(cost_dict['net_pnl'] - 98.9) < 0.001, f"Expected net_pnl 98.9, got {cost_dict['net_pnl']}"
    
    # Test a short trade
    direction = 'SHORT'
    # For short, if price goes down, we profit
    exit_price_short = 90.0  # 10% down
    # gross_pnl = 1000 * (100/90 - 1) = 1000 * (1.1111 - 1) = 111.11
    cost_dict_short = cost_model.calculate_trade_cost(
        entry_price, exit_price_short, size, direction, entry_time, exit_time, funding_rates
    )
    # funding_cost for short: we receive if rate positive -> -size * rate = -1000 * 0.0001 = -0.1
    # total_cost = 0.3 + 0.5 + 0.2 + (-0.1) = 0.9
    # net_pnl = 111.11 - 0.9 = 110.21
    
    assert abs(cost_dict_short['gross_pnl'] - 1000*(100/90 - 1)) < 0.01, f"Expected gross_pnl ~111.11, got {cost_dict_short['gross_pnl']}"
    assert abs(cost_dict_short['funding_cost'] - (-0.1)) < 0.001, f"Expected funding_cost -0.1, got {cost_dict_short['funding_cost']}"
    assert abs(cost_dict_short['total_cost'] - 0.9) < 0.001, f"Expected total_cost 0.9, got {cost_dict_short['total_cost']}"
    assert abs(cost_dict_short['net_pnl'] - (1000*(100/90 - 1) - 0.9)) < 0.01, f"Expected net_pnl ~110.21, got {cost_dict_short['net_pnl']}"
    
    logger.info("Cost model unit test PASSED")
    return True

if __name__ == "__main__":
    # Run unit test if executed directly
    test_cost_model()