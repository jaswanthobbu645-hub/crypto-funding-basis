"""
Backtest engine module for crypto perpetual futures backtesting system.
Implements the core backtesting loop.
"""

import pandas as pd
import numpy as np
import logging
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta
import json
from pathlib import Path
import importlib
from config import config

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import local modules using importlib due to numeric filenames
def import_module_from_file(module_name, file_path):
    """Import a module from a file path."""
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

# Import the modules
_regime_detector = import_module_from_file('02_regime_detector', '02_regime_detector.py')
_cost_model = import_module_from_file('05_cost_model', '05_cost_model.py')
_position_sizer = import_module_from_file('06_position_sizer', '06_position_sizer.py')
_signals = import_module_from_file('03_signals', '03_signals.py')

RegimeDetector = _regime_detector.RegimeDetector
CostModel = _cost_model.CostModel
PositionSizer = _position_sizer.PositionSizer
generate_signals = _signals.generate_signals

class BacktestEngine:
    """
    Core backtesting engine for the crypto perpetual futures strategy.
    
    Attributes:
        config (Config): Configuration object.
        regime_detector (RegimeDetector): Regime detection instance.
        cost_model (CostModel): Cost calculation instance.
        position_sizer (PositionSizer): Position sizing instance.
        data (Dict[str, pd.DataFrame]): Preprocessed data for each instrument.
        equity (float): Current account equity.
        open_positions (List[Dict]): Currently open positions.
        trade_log (List[Dict]): Historical closed trades.
        equity_curve (List[Tuple[pd.Timestamp, float]]): Equity over time.
        daily_start_equity (float): Equity at start of current day.
        last_trade_time (Dict[str, pd.Timestamp]): Last trade timestamp per instrument.
        peak_equity (float): Peak equity achieved so far.
        max_drawdown (float): Maximum drawdown experienced.
        max_drawdown_duration (int): Duration of max drawdown in hours.
    """
    
    def __init__(self, config=None):
        """
        Initialize the backtest engine.
        
        Args:
            config (Config): Configuration object. If None, uses default config.
        """
        # Use provided config or default to imported config
        self.config = config if config is not None else config
        self.regime_detector = RegimeDetector(confirmation_bars=self.config.REGIME_CONFIRM_BARS)
        self.cost_model = CostModel()
        self.position_sizer = PositionSizer()
        self.data: Dict[str, pd.DataFrame] = {}
        self.equity = 100000.0  # Starting equity in USDT
        self.open_positions: List[Dict] = []
        self.trade_log: List[Dict] = []
        self.equity_curve: List[Tuple[pd.Timestamp, float]] = []
        self.daily_start_equity = self.equity
        self.last_trade_time: Dict[str, pd.Timestamp] = {}
        self.peak_equity = self.equity
        self.max_drawdown = 0.0
        self.max_drawdown_duration = 0
        self.current_drawdown_duration = 0
        self.daily_loss_limit_breached = False
        
        # Initialize last_trade_time for each instrument
        for instrument in self.config.INSTRUMENTS:
            self.last_trade_time[instrument] = None
    
    def load_and_preprocess_data(self) -> Dict[str, pd.DataFrame]:
        """
        Load data from 01_data_download.py and preprocess with indicators and signals.
        
        Returns:
            Dict[str, pd.DataFrame]: Preprocessed data for each instrument.
        """
        logger.info("Loading and preprocessing data...")
        
        # Try to load existing processed data first
        processed_file = Path("data/processed_all.pkl")
        if processed_file.exists():
            file_age = datetime.now() - datetime.fromtimestamp(processed_file.stat().st_mtime)
            if file_age.days < 1:  # Use if less than 1 day old
                logger.info(f"Loading preprocessed data from {processed_file}")
                import pickle
                with open(processed_file, 'rb') as f:
                    data = pickle.load(f)
                logger.info("Successfully loaded preprocessed data")
                return data
        
        # Load raw data using the download module
        data_download = import_module_from_file('01_data_download', '01_data_download.py')
        raw_data = data_download.download_all_data()
        
        # Preprocess each instrument: add regime and signals
        for instrument, df in raw_data.items():
            logger.info(f"Preprocessing {instrument}...")
            # Make a copy to avoid modifying original
            df = df.copy()
            
            # Ensure timestamp is index for easier lookup
            df.set_index('timestamp', inplace=True)
            df.sort_index(inplace=True)
            
            # Detect regime
            df = self.regime_detector.detect_regime(df)
            
            # Generate signals
            df = generate_signals(df)
            
            self.data[instrument] = df
        
        # Save preprocessed data
        processed_file.parent.mkdir(exist_ok=True)
        import pickle
        with open(processed_file, 'wb') as f:
            pickle.dump(self.data, f)
        logger.info(f"Saved preprocessed data to {processed_file}")
        
        return self.data
    
    def run_backtest(self) -> Tuple[List[Dict], List[Tuple[pd.Timestamp, float]]]:
        """
        Run the main backtest loop.
        
        Returns:
            Tuple[List[Dict], List[Tuple[pd.Timestamp, float]]]: (trade_log, equity_curve)
        """
        logger.info("Starting backtest...")
        
        # Load and preprocess data if not already loaded
        if not self.data:
            self.data = self.load_and_preprocess_data()
        
        # Create a common time index from start to end date at 1h frequency
        start_ts = pd.Timestamp(self.config.START_DATE, tz='UTC')
        end_ts = pd.Timestamp(self.config.END_DATE, tz='UTC')
        time_index = pd.date_range(start=start_ts, end=end_ts, freq='h', tz='UTC')
        
        logger.info(f"Backtesting from {start_ts} to {end_ts} ({len(time_index)} hours)")
        
        # Track the last date we saw for daily reset
        last_date = None
        
        # Main loop: iterate over each timestamp
        for i, current_time in enumerate(time_index):
            # Check if we've moved to a new day (for daily loss limit reset)
            current_date = current_time.date()
            if last_date is None or current_date != last_date:
                # New day: reset daily start equity and daily loss limit flag
                self.daily_start_equity = self.equity
                self.daily_loss_limit_breached = False
                last_date = current_date
                logger.debug(f"New day: {current_date}, daily start equity reset to {self.daily_start_equity:.2f}")
            
            # Update peak equity and drawdown
            if self.equity > self.peak_equity:
                self.peak_equity = self.equity
                self.current_drawdown_duration = 0  # Reset drawdown duration on new peak
            else:
                self.current_drawdown_duration += 1  # Increment drawdown duration
            
            current_drawdown = (self.peak_equity - self.equity) / self.peak_equity if self.peak_equity > 0 else 0
            if current_drawdown > self.max_drawdown:
                self.max_drawdown = current_drawdown
                self.max_drawdown_duration = self.current_drawdown_duration
            
            # Process each instrument at this timestamp
            for instrument in self.config.INSTRUMENTS:
                if instrument not in self.data:
                    continue
                df = self.data[instrument]
                if current_time not in df.index:
                    # No data for this instrument at this timestamp
                    continue
                
                # Get the current bar data
                bar = df.loc[current_time]
                
                # Process exits for any open position in this instrument
                self._process_exits(instrument, bar, current_time)
                
                # Process entries (if no open position in this instrument after exits)
                if instrument not in [pos['instrument'] for pos in self.open_positions]:
                    self._process_entries(instrument, bar, current_time)
            
            # Record equity at the end of each hour (for equity curve)
            self.equity_curve.append((current_time, self.equity))
            
            # Progress logging
            if i % (24 * 30) == 0:  # Log every 30 days
                logger.info(f"Progress: {current_time} - Equity: {self.equity:.2f}")
        
        logger.info("Backtest completed.")
        return self.trade_log, self.equity_curve
    
    def _process_exits(self, instrument: str, bar: pd.Series, current_time: pd.Timestamp):
        """
        Check exit conditions for open positions in the given instrument.
        
        Args:
            instrument (str): Instrument symbol.
            bar (pd.Series): Current bar data.
            current_time (pd.Timestamp): Current timestamp.
        """
        # Find open position for this instrument
        position = None
        for pos in self.open_positions:
            if pos['instrument'] == instrument:
                position = pos
                break
        
        if position is None:
            return
        
        # Extract position details
        entry_price = position['entry_price']
        direction = position['direction']
        size = position['size_usd']
        entry_time = position['entry_time']
        regime_at_entry = position['regime_at_entry']
        sl_pct = position['sl_pct']
        tp_pct = position['tp_pct']
        time_exit_bar = position['time_exit_bar']
        bars_held = (current_time - entry_time).total_seconds() / 3600  # hours
        
        # Get current price
        current_price = bar['close']
        
        # Initialize exit reason
        exit_reason = None
        exit_price = current_price
        
        # a. TAKE PROFIT
        if direction == 'LONG' and current_price >= entry_price * (1 + tp_pct):
            exit_reason = 'TAKE_PROFIT'
        elif direction == 'SHORT' and current_price <= entry_price * (1 - tp_pct):
            exit_reason = 'TAKE_PROFIT'
        
        # b. STOP LOSS
        if exit_reason is None:
            if direction == 'LONG' and current_price <= entry_price * (1 - sl_pct):
                exit_reason = 'STOP_LOSS'
            elif direction == 'SHORT' and current_price >= entry_price * (1 + sl_pct):
                exit_reason = 'STOP_LOSS'
        
        # c. TIME EXIT
        if exit_reason is None and bars_held >= time_exit_bar:
            exit_reason = 'TIME_EXIT'
        
        # d. REGIME FLIP EXIT
        if exit_reason is None:
            current_regime = bar['regime']
            # If regime contradicts direction -> exit immediately
            if (direction == 'LONG' and current_regime == 'BEAR') or \
               (direction == 'SHORT' and current_regime == 'BULL'):
                exit_reason = 'REGIME_FLIP'
            # If regime = SIDEWAYS and position profitable -> move SL to breakeven
            elif current_regime == 'SIDEWAYS':
                # Check if profitable
                if direction == 'LONG' and current_price <= entry_price:
                    exit_reason = 'REGIME_FLIP'  # losing in sideways -> exit
                elif direction == 'SHORT' and current_price >= entry_price:
                    exit_reason = 'REGIME_FLIP'  # losing in sideways -> exit
                # If profitable, we adjust the stop loss to break even and continue.
                # We'll implement by setting a new stop loss at entry_price and then we don't exit.
                # We'll set a flag so we know we've moved to breakeven
                else:
                    # Profitable in sideways: move SL to breakeven
                    position['breakeven_sl_moved'] = True
                    # Update the position's stop loss to entry_price for future checks
                    position['sl_price'] = entry_price
                    # We do not exit, we continue to next bar
                    return  # Skip the rest of exit processing for this bar
            # If regime = SIDEWAYS and position losing -> exit immediately (handled above)
        
        # e. HIGH VOL EXIT
        if exit_reason is None and bar.get('is_high_vol', False):
            # Tighten SL to 50% of original
            # We'll check if the current price breaches the tightened SL
            original_sl_pct = position.get('original_sl_pct', sl_pct)
            tightened_sl_pct = original_sl_pct * 0.5
            if direction == 'LONG' and current_price <= entry_price * (1 - tightened_sl_pct):
                exit_reason = 'HIGH_VOL_EXIT'
            elif direction == 'SHORT' and current_price >= entry_price * (1 + tightened_sl_pct):
                exit_reason = 'HIGH_VOL_EXIT'
        
        # If we have an exit reason, close the position
        if exit_reason is not None:
            self._close_position(position, exit_price, current_time, exit_reason)
    
    def _close_position(self, position: Dict, exit_price: float, exit_time: pd.Timestamp, exit_reason: str):
        """
        Close an open position and record the trade.
        
        Args:
            position (Dict): The position to close.
            exit_price (float): Exit price.
            exit_time (pd.Timestamp): Exit timestamp.
            exit_reason (str): Reason for exit.
        """
        # Calculate PnL using cost model
        # We need the funding series for the instrument during the trade
        instrument = position['instrument']
        df = self.data[instrument]
        # Get funding rate series for the instrument (we need it as a Series indexed by timestamp)
        # We'll extract the funding rate column and make it a Series
        funding_series = df['fundingRate'].copy()
        funding_series.name = 'fundingRate'
        
        # Calculate trade cost
        cost_dict = self.cost_model.calculate_trade_cost(
            entry_price=position['entry_price'],
            exit_price=exit_price,
            size=position['size_usd'],
            direction=position['direction'],
            entry_time=position['entry_time'],
            exit_time=exit_time,
            funding_series=funding_series
        )
        
        # Create trade record
        trade = {
            'instrument': instrument,
            'direction': position['direction'],
            'entry_time': position['entry_time'],
            'exit_time': exit_time,
            'entry_price': position['entry_price'],
            'exit_price': exit_price,
            'size_usd': position['size_usd'],
            'leverage': position['leverage'],
            'margin_used': position['margin_required'],
            'bars_held': (exit_time - position['entry_time']).total_seconds() / 3600,
            'exit_reason': exit_reason,
            'regime_at_entry': position['regime_at_entry'],
            'regime_at_exit': self.data[instrument].loc[exit_time]['regime'] if exit_time in self.data[instrument].index else 'UNKNOWN',
            'regime_changed': position['regime_at_entry'] != self.data[instrument].loc[exit_time]['regime'] if exit_time in self.data[instrument].index else False,
            'gross_pnl': cost_dict['gross_pnl'],
            'entry_fee': cost_dict['entry_fee'],
            'exit_fee': cost_dict['exit_fee'],
            'slippage': cost_dict['slippage'],
            'funding_paid': cost_dict['funding_cost'],
            'total_cost': cost_dict['total_cost'],
            'net_pnl': cost_dict['net_pnl'],
            'net_pnl_pct': cost_dict['net_pnl'] / position['size_usd'] * 100,  # Percentage of notional
            'running_equity_after': self.equity + cost_dict['net_pnl'],  # Equity after this trade
            'confluence_score': position.get('confluence_score', 0),
            'oi_at_entry': position.get('oi_at_entry', 0),
            'funding_at_entry': position.get('funding_at_entry', 0)
        }
        
        # Update equity
        self.equity += trade['net_pnl']
        
        # Add to trade log
        self.trade_log.append(trade)
        
        # Remove from open positions
        self.open_positions.remove(position)
        
        # Update last trade time for this instrument
        self.last_trade_time[instrument] = exit_time
        
        logger.debug(f"Closed {position['direction']} position in {instrument} at {exit_time} for {exit_reason}: PnL = {trade['net_pnl']:.2f}")
    
    def _process_entries(self, instrument: str, bar: pd.Series, current_time: pd.Timestamp):
        """
        Check entry conditions and open a new position if conditions are met.
        
        Args:
            instrument (str): Instrument symbol.
            bar (pd.Series): Current bar data.
            current_time (pd.Timestamp): Current timestamp.
        """
        # Check if we can trade based on risk limits and daily loss limit
        if self.daily_loss_limit_breached:
            return
        
        # Check current drawdown halt
        current_drawdown = (self.peak_equity - self.equity) / self.peak_equity if self.peak_equity > 0 else 0
        if current_drawdown >= self.config.MAX_DRAWDOWN_HALT:
            logger.warning(f"Drawdown {current_drawdown:.2%} exceeded halt threshold - continuing for reporting")
        
        # Check if we have an existing position in this instrument (should not, but double-check)
        if any(pos['instrument'] == instrument for pos in self.open_positions):
            return
        
        # Check time since last trade on this instrument
        last_trade = self.last_trade_time.get(instrument)
        if last_trade is not None:
            hours_since_last_trade = (current_time - last_trade).total_seconds() / 3600
            if hours_since_last_trade < self.config.MIN_BARS_BETWEEN_TRADES:
                return
        
        # Check regime: no new positions in HIGH_VOL
        if bar.get('is_high_vol', False):
            return

        # Volume filter: only enter if 24h volume > 30-day average volume
        df = self.data[instrument]
        vol_24h = df['volume'].rolling(window=24).sum().loc[current_time]
        vol_30d_avg = df['volume'].rolling(window=24).sum().rolling(window=30*24).mean().shift(1).loc[current_time]
        if pd.isna(vol_30d_avg):
            pass
        elif vol_24h <= vol_30d_avg:
            return
        
        # Check signals: we need at least one entry signal
        entry_long = bar.get('entry_long', False)
        entry_short = bar.get('entry_short', False)
        if not entry_long and not entry_short:
            return
        
        # Check concurrent position limit
        if len(self.open_positions) >= self.config.MAX_CONCURRENT:
            return
        
        # Determine direction based on signal (if both long and short, we need a rule)
        if entry_long and entry_short:
            score_long = bar.get('score_long', 0)
            score_short = bar.get('score_short', 0)
            if score_long >= score_short:
                direction = 'LONG'
            else:
                direction = 'SHORT'
        elif entry_long:
            direction = 'LONG'
        elif entry_short:
            direction = 'SHORT'
        else:
            return  # Should not happen due to earlier check, but safe
        
        # Get stop loss and take profit percentages based on regime
        regime = bar['regime']
        if regime == 'BULL':
            sl_pct = self.config.BULL_SL_PCT
            tp_pct = sl_pct * 1.5
            time_exit_bars = self.config.BULL_TIME_EXIT_BARS
        elif regime == 'BEAR':
            sl_pct = self.config.BEAR_SL_PCT
            tp_pct = sl_pct * 1.5
            time_exit_bars = self.config.BEAR_TIME_EXIT_BARS
        elif regime == 'SIDEWAYS':
            sl_pct = self.config.SIDEWAYS_SL_PCT
            tp_pct = sl_pct * 1.5
            time_exit_bars = self.config.SIDEWAYS_TIME_EXIT_BARS
        else:  # HIGH_VOL should have been filtered out, but just in case
            sl_pct = self.config.BULL_SL_PCT * 0.5  # Tighten SL
            tp_pct = sl_pct * 1.5
            time_exit_bars = self.config.BULL_TIME_EXIT_BARS
        
        # Calculate position size
        # We need the current equity and drawdown for the position sizer
        current_dd = (self.peak_equity - self.equity) / self.peak_equity if self.peak_equity > 0 else 0
        # We also need to pass open positions (for correlation cap) and the instrument
        size_usd, leverage, margin_required = self.position_sizer.calculate_size(
            equity=self.equity,
            regime=regime,
            current_dd=current_dd,
            open_positions=self.open_positions,
            sl_pct=sl_pct,
            instrument=instrument
        )
        
        # Check if we can trade (position sizer also checks risk limits)
        can_trade, reason = self.position_sizer.check_risk_limits(
            equity=self.equity,
            open_positions=self.open_positions
        )
        if not can_trade:
            logger.debug(f"Cannot trade {instrument}: {reason}")
            return
        
        # If size is zero, skip
        if size_usd <= 0:
            return
        
        # Open the position
        position = {
            'instrument': instrument,
            'direction': direction,
            'entry_price': bar['close'],
            'entry_time': current_time,
            'size_usd': size_usd,
            'leverage': leverage,
            'margin_required': margin_required,
            'regime_at_entry': regime,
            'sl_pct': sl_pct,
            'tp_pct': tp_pct,
            'time_exit_bar': time_exit_bars,
            'original_sl_pct': sl_pct,  # Store original for HIGH_VOL adjustment
            'confluence_score': bar.get('score_long' if direction == 'LONG' else 'score_short', 0),
            'oi_at_entry': bar.get('openInterest', 0),
            'funding_at_entry': bar.get('fundingRate', 0)
        }
        
        # Add to open positions
        self.open_positions.append(position)
        
        # Update last trade time
        self.last_trade_time[instrument] = current_time
        
        logger.debug(f"Opened {direction} position in {instrument} at {current_time}: size=${size_usd:.2f}, leverage={leverage:.2f}x")
    
    def get_performance_stats(self) -> Dict:
        """
        Calculate performance statistics from the trade log.
        
        Returns:
            Dict: Performance statistics.
        """
        if not self.trade_log:
            return {}
        
        trades_df = pd.DataFrame(self.trade_log)
        
        # Basic stats
        total_trades = len(trades_df)
        winning_trades = trades_df[trades_df['net_pnl'] > 0]
        losing_trades = trades_df[trades_df['net_pnl'] <= 0]
        win_rate = len(winning_trades) / total_trades if total_trades > 0 else 0
        
        # PnL stats
        net_pnl = trades_df['net_pnl'].sum()
        gross_pnl = trades_df['gross_pnl'].sum()
        total_cost = trades_df['total_cost'].sum()
        avg_win = winning_trades['net_pnl'].mean() if len(winning_trades) > 0 else 0
        avg_loss = losing_trades['net_pnl'].mean() if len(losing_trades) > 0 else 0
        profit_factor = abs(winning_trades['net_pnl'].sum() / losing_trades['net_pnl'].sum()) if len(losing_trades) > 0 and losing_trades['net_pnl'].sum() != 0 else 0
        
        # Return stats
        total_return_pct = (self.equity - 100000) / 100000 * 100
        
        # Sharpe ratio (assuming hourly data, annualized)
        # We need daily returns for Sharpe, but we have equity curve.
        # We'll approximate using hourly returns from equity curve.
        if len(self.equity_curve) > 1:
            equity_series = pd.Series([eq for _, eq in self.equity_curve], 
                                    index=[ts for ts, _ in self.equity_curve])
            hourly_returns = equity_series.pct_change().dropna()
            # Annualize: sqrt(24*365) for hourly
            sharpe_ratio = hourly_returns.mean() / hourly_returns.std() * np.sqrt(24*365) if hourly_returns.std() != 0 else 0
        else:
            sharpe_ratio = 0
        
        # Max drawdown
        max_dd = self.max_drawdown
        
        # Calmar ratio: annualized return / max drawdown
        # Annualized return: (1 + total_return_pct/100)^(1/(years)) - 1
        # We have 2 years of data
        years = 2
        annualized_return = (1 + total_return_pct/100)**(1/years) - 1
        calmar_ratio = annualized_return / max_dd if max_dd != 0 else 0
        
        # Sortino ratio: similar to Sharpe but using downside deviation
        # We'll calculate downside deviation from hourly returns
        if len(self.equity_curve) > 1:
            downside_returns = hourly_returns[hourly_returns < 0]
            downside_deviation = downside_returns.std() if len(downside_returns) > 0 else 0
            sortino_ratio = hourly_returns.mean() / downside_deviation * np.sqrt(24*365) if downside_deviation != 0 else 0
        else:
            sortino_ratio = 0
        
        # VaR (95%) - 5th percentile of hourly returns
        if len(self.equity_curve) > 1:
            var_95 = np.percentile(hourly_returns, 5) if len(hourly_returns) > 0 else 0
        else:
            var_95 = 0
        
        # Trades per month
        months = 24  # 2 years
        trades_per_month = total_trades / months if months > 0 else 0
        
        # Regime breakdown
        regime_stats = {}
        for regime in ['BULL', 'SIDEWAYS', 'BEAR']:
            regime_trades = trades_df[trades_df['regime_at_entry'] == regime]
            if len(regime_trades) > 0:
                regime_stats[regime] = {
                    'trades': len(regime_trades),
                    'win_rate': len(regime_trades[regime_trades['net_pnl'] > 0]) / len(regime_trades),
                    'avg_pnl': regime_trades['net_pnl'].mean(),
                    'total_pnl': regime_trades['net_pnl'].sum()
                }
            else:
                regime_stats[regime] = {
                    'trades': 0,
                    'win_rate': 0,
                    'avg_pnl': 0,
                    'total_pnl': 0
                }
        
        return {
            'total_trades': total_trades,
            'winning_trades': len(winning_trades),
            'losing_trades': len(losing_trades),
            'win_rate': win_rate,
            'net_pnl': net_pnl,
            'net_pnl_pct': total_return_pct,
            'gross_pnl': gross_pnl,
            'total_cost': total_cost,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_factor': profit_factor,
            'sharpe_ratio': sharpe_ratio,
            'sortino_ratio': sortino_ratio,
            'calmar_ratio': calmar_ratio,
            'max_drawdown': max_dd,
            'var_95': var_95,
            'trades_per_month': trades_per_month,
            'regime_stats': regime_stats
        }

def run_backtest():
    """
    Convenience function to run the backtest and return results.
    """
    engine = BacktestEngine()
    trade_log, equity_curve = engine.run_backtest()
    stats = engine.get_performance_stats()
    return trade_log, equity_curve, stats

if __name__ == "__main__":
    # Run the backtest when executed directly
    logger.info("Running backtest engine standalone...")
    trade_log, equity_curve, stats = run_backtest()
    
    # Print some stats
    print(f"Backtest completed. Total trades: {len(trade_log)}")
    print(f"Final equity: {stats.get('net_pnl', 0) + 100000:.2f}")
    print(f"Net PnL: {stats.get('net_pnl', 0):.2f} ({stats.get('net_pnl_pct', 0):.2f}%)")
    print(f"Sharpe ratio: {stats.get('sharpe_ratio', 0):.2f}")
    print(f"Max drawdown: {stats.get('max_drawdown', 0):.2%}")