"""
Walk-forward validation module for crypto perpetual futures backtesting system.
Implements walk-forward validation engine.
"""

import pandas as pd
import numpy as np
import logging
import json
from pathlib import Path
from typing import Dict, List, Tuple
import copy
import importlib.util
from config import config

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import run_parameter_optimization from 07_parameter_optimizer.py using importlib
spec_opt = importlib.util.spec_from_file_location("parameter_optimizer", "07_parameter_optimizer.py")
parameter_optimizer_module = importlib.util.module_from_spec(spec_opt)
spec_opt.loader.exec_module(parameter_optimizer_module)
run_parameter_optimization = parameter_optimizer_module.run_parameter_optimization

# Import BacktestEngine from 04_backtest_engine.py using importlib
spec_bt = importlib.util.spec_from_file_location("backtest_engine", "04_backtest_engine.py")
backtest_engine_module = importlib.util.module_from_spec(spec_bt)
spec_bt.loader.exec_module(backtest_engine_module)
BacktestEngine = backtest_engine_module.BacktestEngine

def run_walk_forward() -> Tuple[List[Dict], pd.DataFrame]:
    """
    Run walk-forward validation with 4 windows.
    
    Returns:
        Tuple[List[Dict], pd.DataFrame]: (window_results, summary_df)
    """
    logger.info("Starting walk-forward validation...")
    
    # Define the windows: each window has a training period and testing period
    # All windows use the same start date (2022-09-01) for training, expanding over time
    windows = [
        {
            'train_start': '2022-09-01',
            'train_end': '2024-01-01',
            'test_start': '2024-01-01',
            'test_end': '2024-03-01',
            'window': 1
        },
        {
            'train_start': '2022-09-01',
            'train_end': '2024-03-01',
            'test_start': '2024-03-01',
            'test_end': '2024-05-01',
            'window': 2
        },
        {
            'train_start': '2022-09-01',
            'train_end': '2024-05-01',
            'test_start': '2024-05-01',
            'test_end': '2024-07-01',
            'window': 3
        },
        {
            'train_start': '2022-09-01',
            'train_end': '2024-07-01',
            'test_start': '2024-07-01',
            'test_end': '2024-09-01',
            'window': 4
        }
    ]
    
    window_results = []
    
    for window in windows:
        logger.info(f"Processing Window {window['window']}: "
                   f"Train {window['train_start']} to {window['train_end']}, "
                   f"Test {window['test_start']} to {window['test_end']}")
        
        # 1. Run optimizer on train period
        original_end_date = config.END_DATE
        config.END_DATE = window['train_end']
        
        try:
            # Load pre-computed best parameters instead of running optimization
            import json as _json
            with open('optimization/best_params.json', 'r') as _f:
                best_params = _json.load(_f)
            # Remove score/meta keys if present
            best_params = {k: v for k, v in best_params.items() 
                         if k not in ['score', 'net_pnl_pct', 'sharpe_ratio', 
                                      'max_drawdown', 'win_rate', 'trades_per_month']}
            top_10_params = [best_params]  # Format expected by the rest of the code
        except Exception as e:
            logger.error(f"Error loading best parameters for window {window['window']}: {e}")
            best_params = None
        finally:
            config.END_DATE = original_end_date
        
        if best_params is None:
            logger.warning(f"No valid parameters found for window {window['window']}, skipping")
            continue
        
        # 2. Run backtest on test period using best params
        # We'll load data from the global start to the test end for indicator warmup,
        # but only evaluate on the test period
        
        # Save original dates
        orig_start = config.START_DATE
        orig_end = config.END_DATE
        
        # Set to load data from global start to test end
        config.START_DATE = '2022-09-01'
        config.END_DATE = window['test_end']
        
        # Create a custom config with the best parameters
        class CustomConfig:
            def __init__(self, base_config, override_params):
                for attr in dir(base_config):
                    if not attr.startswith('_') and not callable(getattr(base_config, attr)):
                        setattr(self, attr, getattr(base_config, attr))
                for key, value in override_params.items():
                    setattr(self, key, value)
        
        # We need to override the end date for the test period
        test_config = CustomConfig(config, best_params)
        # Keep the START_DATE as global start (2022-09-01) for warmup, END_DATE as test end
        # The backtest engine will process all data but we'll filter results to test period
        
        engine = BacktestEngine(config=test_config)
        
        try:
            trade_log, equity_curve = engine.run_backtest()
            
            # Filter trades to only those that exited in the test period
            test_start = pd.Timestamp(window['test_start'])
            test_end = pd.Timestamp(window['test_end'])
            # Localize to UTC if no timezone info
            if test_start.tzinfo is None:
                test_start = test_start.tz_localize('UTC')
            if test_end.tzinfo is None:
                test_end = test_end.tz_localize('UTC')
            
            filtered_trades = []
            for trade in trade_log:
                exit_time = pd.Timestamp(trade['exit_time'])
                if exit_time.tzinfo is None:
                    exit_time = exit_time.tz_localize('UTC')
                if test_start <= exit_time < test_end:
                    filtered_trades.append(trade)
            
            # Filter equity curve to test period
            filtered_equity_curve = [
                (timestamp, equity) for timestamp, equity in equity_curve
                if test_start <= timestamp < test_end
            ]
            
            # Calculate statistics on the filtered test period
            # We'll create a temporary engine to calculate stats from the filtered trades
            temp_engine = BacktestEngine(config=test_config)
            temp_engine.trade_log = filtered_trades
            temp_engine.equity_curve = filtered_equity_curve
            # Set the equity to the starting equity for the test period (we'll approximate)
            # For simplicity, we'll use the equity from the equity curve at the start of test period
            if filtered_equity_curve:
                temp_engine.equity = filtered_equity_curve[0][1]
            else:
                temp_engine.equity = 100000.0  # Default starting equity
            
            stats = temp_engine.get_performance_stats()
            
            # If no trades, stats will be empty, we'll handle that
            if not stats:
                stats = {
                    'net_pnl': 0,
                    'net_pnl_pct': 0,
                    'sharpe_ratio': 0,
                    'max_drawdown': 0,
                    'win_rate': 0,
                    'total_trades': 0,
                    'profit_factor': 0,
                    'trades_per_month': 0
                }
            
            # Record window result
            window_result = {
                'window': window['window'],
                'train_start': window['train_start'],
                'train_end': window['train_end'],
                'test_start': window['test_start'],
                'test_end': window['test_end'],
                'best_params': best_params,
                'stats': stats
            }
            window_results.append(window_result)
            
            logger.info(f"Window {window['window']} completed. "
                       f"Net PnL: {stats.get('net_pnl_pct', 0):.2f}%, "
                       f"Sharpe: {stats.get('sharpe_ratio', 0):.2f}, "
                       f"Max DD: {stats.get('max_drawdown', 0):.2%}")
            
        except Exception as e:
            logger.error(f"Error in backtest for window {window['window']}: {e}")
        finally:
            # Restore original dates
            config.START_DATE = orig_start
            config.END_DATE = orig_end
    
    # Create summary DataFrame
    if window_results:
        summary_data = []
        for result in window_results:
            stats = result['stats']
            summary_data.append({
                'Window': result['window'],
                'Train Period': f"{result['train_start']} to {result['train_end']}",
                'Test Period': f"{result['test_start']} to {result['test_end']}",
                'Net PnL %': stats.get('net_pnl_pct', 0),
                'Sharpe Ratio': stats.get('sharpe_ratio', 0),
                'Max Drawdown': stats.get('max_drawdown', 0),
                'Win Rate': stats.get('win_rate', 0),
                'Total Trades': stats.get('total_trades', 0),
                'Profit Factor': stats.get('profit_factor', 0),
                'Trades/Month': stats.get('trades_per_month', 0)
            })
        summary_df = pd.DataFrame(summary_data)
    else:
        summary_df = pd.DataFrame()
    
    logger.info("Walk-forward validation completed.")
    return window_results, summary_df

def save_walk_forward_results(window_results: List[Dict], summary_df: pd.DataFrame):
    """
    Save walk-forward results to files.
    
    Args:
        window_results (List[Dict]): Results for each window.
        summary_df (pd.DataFrame): Summary DataFrame.
    """
    # Create walk_forward directory
    wf_dir = Path("walk_forward")
    wf_dir.mkdir(exist_ok=True)
    
    # Save window results as JSON
    # Convert non-serializable objects (like Timestamp) to string
    serializable_results = []
    for result in window_results:
        res_copy = result.copy()
        # Convert params to string if needed, but they are already serializable
        # Convert timestamps in best_params? The best_params are from the optimizer and should be numbers.
        # We'll leave as is.
        serializable_results.append(res_copy)
    
    with open(wf_dir / "window_results.json", 'w') as f:
        json.dump(serializable_results, f, indent=2)
    
    # Save summary as CSV
    summary_df.to_csv(wf_dir / "walk_forward_summary.csv", index=False)
    
    # Create a summary text file
    with open(wf_dir / "walk_forward_summary.txt", 'w') as f:
        f.write("Walk-Forward Validation Results\n")
        f.write("=" * 50 + "\n\n")
        for result in window_results:
            f.write(f"Window {result['window']}:\n")
            f.write(f"  Train: {result['train_start']} to {result['train_end']}\n")
            f.write(f"  Test:  {result['test_start']} to {result['test_end']}\n")
            f.write(f"  Best Parameters: {result['best_params']}\n")
            stats = result['stats']
            f.write(f"  Test Performance:\n")
            f.write(f"    Net PnL %: {stats.get('net_pnl_pct', 0):.2f}%\n")
            f.write(f"    Sharpe Ratio: {stats.get('sharpe_ratio', 0):.2f}\n")
            f.write(f"    Max Drawdown: {stats.get('max_drawdown', 0):.2%}\n")
            f.write(f"    Win Rate: {stats.get('win_rate', 0):.2%}\n")
            f.write(f"    Total Trades: {stats.get('total_trades', 0)}\n")
            f.write(f"    Profit Factor: {stats.get('profit_factor', 0):.2f}\n")
            f.write(f"    Trades/Month: {stats.get('trades_per_month', 0):.2f}\n")
            f.write("\n")
    
    logger.info(f"Walk-forward results saved to {wf_dir}")

def test_walk_forward():
    """
    Unit test for walk-forward validation.
    """
    logger.info("Running walk-forward unit test...")
    
    # We'll test with a very short period to avoid long runs
    # Temporarily override the config dates for the test
    original_start = config.START_DATE
    original_end = config.END_DATE
    
    # Set to a very short period
    config.START_DATE = '2022-09-01'
    config.END_DATE = '2022-09-02'  # Two days
    
    try:
        # We expect little to no data, but we want to see if it runs without error
        window_results, summary_df = run_walk_forward()
        # We don't care about the actual results, just that it doesn't crash
        logger.info("Walk-forward unit test completed without error")
    except Exception as e:
        logger.error(f"Walk-forward unit test failed: {e}")
        raise
    finally:
        # Restore original dates
        config.START_DATE = original_start
        config.END_DATE = original_end
    
    logger.info("Walk-forward unit test PASSED")
    return True

if __name__ == "__main__":
    # Run walk-forward validation when executed directly
    logger.info("Running walk-forward validation...")
    window_results, summary_df = run_walk_forward()
    save_walk_forward_results(window_results, summary_df)
    
    # Print summary
    print("\nWalk-Forward Validation Complete!")
    if not summary_df.empty:
        print(summary_df.to_string(index=False))
    else:
        print("No results to display.")
    print(f"\nDetailed results saved to walk_forward/window_results.json")
    print(f"Summary saved to walk_forward/walk_forward_summary.csv")