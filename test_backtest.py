import sys
import importlib.util
from pathlib import Path

def import_module_from_file(module_name, file_path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

config_module = import_module_from_file('config', 'config.py')
config = config_module.config
BacktestEngine = import_module_from_file('04_backtest_engine', '04_backtest_engine.py').BacktestEngine

print('Testing BacktestEngine with processed data...')
engine = BacktestEngine(config=config)
# Check if processed data exists
processed_file = Path('data/processed_all.pkl')
if processed_file.exists():
    print('Processed data found, loading...')
    import pickle
    with open(processed_file, 'rb') as f:
        data = pickle.load(f)
    print('Loaded processed data for instruments:', list(data.keys()))
    # Manually set the data to avoid re-downloading
    engine.data = data
    print('Engine data set manually.')
else:
    print('No processed data found, will attempt to load and preprocess...')
    
# Now run a small backtest test (just a few steps)
print('Running backtest for a small subset...')
# We'll monkey-patch the time_index to only have a few points for testing
original_run_backtest = engine.run_backtest
def test_run_backtest():
    logger = engine.__class__.__dict__.get('logger', None)
    if logger is None:
        import logging
        logger = logging.getLogger(__name__)
    logger.info('Starting test backtest...')
    
    # Load and preprocess data if not already loaded
    if not engine.data:
        engine.data = engine.load_and_preprocess_data()
    
    # Create a common time index from start to end date at 1H frequency
    # But for testing, let's just use the first 100 hours from the data
    start_ts = pd.Timestamp(config.START_DATE, tz='UTC')
    end_ts = pd.Timestamp(config.END_DATE, tz='UTC')
    full_time_index = pd.date_range(start=start_ts, end=end_ts, freq='H', tz='UTC')
    # Take only first 100 hours for testing
    time_index = full_time_index[:100]
    
    logger.info(f'Testing from {time_index[0]} to {time_index[-1]} ({len(time_index)} hours)')
    
    # Track the last date we saw for daily reset
    last_date = None
    
    # Main loop: iterate over each timestamp
    for i, current_time in enumerate(time_index):
        # Check if we've moved to a new day (for daily loss limit reset)
        current_date = current_time.date()
        if last_date is None or current_date != last_date:
            # New day: reset daily start equity and daily loss limit flag
            engine.daily_start_equity = engine.equity
            engine.daily_loss_limit_breached = False
            last_date = current_date
            logger.debug(f'New day: {current_date}, daily start equity reset to {engine.daily_start_equity:.2f}')
        
        # Update peak equity and drawdown
        if engine.equity > engine.peak_equity:
            engine.peak_equity = engine.equity
            engine.current_drawdown_duration = 0  # Reset drawdown duration on new peak
        else:
            engine.current_drawdown_duration += 1  # Increment drawdown duration
        
        current_drawdown = (engine.peak_equity - engine.equity) / engine.peak_equity if engine.peak_equity > 0 else 0
        if current_drawdown > engine.max_drawdown:
            engine.max_drawdown = current_drawdown
            engine.max_drawdown_duration = engine.current_drawdown_duration
        
        # Process each instrument at this timestamp
        for instrument in config.INSTRUMENTS:
            if instrument not in engine.data:
                continue
            df = engine.data[instrument]
            if current_time not in df.index:
                # No data for this instrument at this timestamp
                continue
            
            # Get the current bar data
            bar = df.loc[current_time]
            
            # Process exits for any open position in this instrument
            engine._process_exits(instrument, bar, current_time)
            
            # Process entries (if no open position in this instrument after exits)
            if instrument not in [pos['instrument'] for pos in engine.open_positions]:
                engine._process_entries(instrument, bar, current_time)
        
        # Record equity at the end of each hour (for equity curve)
        engine.equity_curve.append((current_time, engine.equity))
        
        # Progress logging
        if i % 20 == 0:  # Log every 20 hours for test
            logger.info(f'Progress: {current_time} - Equity: {engine.equity:.2f}')
    
    logger.info('Backtest completed.')
    return engine.trade_log, engine.equity_curve

# Temporarily replace the run_backtest method
engine.run_backtest = test_run_backtest

# Import pandas for the timestamp creation
import pandas as pd

# Run the test
trade_log, equity_curve = engine.run_backtest()
print(f'Test completed. Trades: {len(trade_log)}, Equity points: {len(equity_curve)}')
if trade_log:
    print('First trade:', trade_log[0])
if equity_curve:
    print('First equity point:', equity_curve[0])
    print('Last equity point:', equity_curve[-1])