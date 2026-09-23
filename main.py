"""
Main pipeline for crypto perpetual futures backtesting system.
Runs the full pipeline end to end.
"""

import pandas as pd
import numpy as np
import logging
import json
import os
import importlib.util
from pathlib import Path
from datetime import datetime
import sys
from config import config

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def import_module_from_file(module_name, file_path):
    """
    Import a module from a file path.
    
    Args:
        module_name (str): Name to assign to the module.
        file_path (str or Path): Path to the file.
        
    Returns:
        module: The imported module.
    """
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def run_step(step_name, step_func, *args, **kwargs):
    """
    Run a step of the pipeline with error handling and logging.
    
    Args:
        step_name (str): Name of the step for logging.
        step_func (callable): Function to execute for this step.
        *args, **kwargs: Arguments to pass to the step function.
        
    Returns:
        Result of the step function, or None if failed.
    """
    logger.info(f"=== Starting {step_name} ===")
    try:
        result = step_func(*args, **kwargs)
        logger.info(f"=== Completed {step_name} ===")
        return result
    except Exception as e:
        logger.error(f"=== Failed {step_name}: {e} ===", exc_info=True)
        return None

def main():
    """Run the full backtesting pipeline."""
    logger.info("Starting crypto perpetual futures backtesting pipeline...")
    
    # Step 1: Download / load data
    logger.info("Step 1: Download / load data")
    data_download_module = import_module_from_file("data_download", "01_data_download.py")
    download_main = data_download_module.main
    data_dict = run_step("Data Download", download_main)
    if data_dict is None:
        logger.error("Data download failed. Exiting.")
        return False
    
    # Step 2: Validate data quality
    logger.info("Step 2: Validate data quality")
    # We'll do a simple validation
    if data_dict:
        total_rows = sum(len(df) for df in data_dict.values())
        logger.info(f"Total data points across all instruments: {total_rows}")
        for instrument, df in data_dict.items():
            if df.empty:
                logger.warning(f"No data for {instrument}")
            else:
                date_range = f"{df['timestamp'].min()} to {df['timestamp'].max()}"
                null_count = df.isnull().sum().sum()
                logger.info(f"{instrument}: {len(df)} rows, {date_range}, nulls: {null_count}")
    else:
        logger.warning("No data dictionary returned from download step")
    
    # Step 3: Generate signals on all instruments
    logger.info("Step 3: Generate signals on all instruments")
    signals_module = import_module_from_file("signals", "03_signals.py")
    regime_detector_module = import_module_from_file("regime_detector", "02_regime_detector.py")
    generate_signals = signals_module.generate_signals
    RegimeDetector = regime_detector_module.RegimeDetector
    
    regime_detector = RegimeDetector(confirmation_bars=config.REGIME_CONFIRM_BARS)
    signaled_data = {}
    
    for instrument, df in data_dict.items():
        if df.empty:
            signaled_data[instrument] = df
            continue
        # Make a copy to avoid modifying original
        df_copy = df.copy()
        # Detect regime
        df_copy = regime_detector.detect_regime(df_copy)
        # Generate signals
        df_copy = generate_signals(df_copy)
        signaled_data[instrument] = df_copy
    
    logger.info("Signal generation completed.")
    
    # Step 4: Run base backtest (default params, full 2 years)
    logger.info("Step 4: Run base backtest (default params, full 2 years)")
    backtest_engine_module = import_module_from_file("backtest_engine", "04_backtest_engine.py")
    BacktestEngine = backtest_engine_module.BacktestEngine
    
    base_engine = BacktestEngine(config=config)
    base_trade_log, base_equity_curve = run_step("Base Backtest", base_engine.run_backtest)
    
    if base_trade_log is None:
        logger.error("Base backtest failed. Exiting.")
        return False
    
    base_stats = base_engine.get_performance_stats()
    
    # Print acceptance criteria check immediately
    logger.info("Printing base backtest acceptance criteria...")
    # We'll use the ReportGenerator to print the console report
    report_generator_module = import_module_from_file("report_generator", "10_report_generator.py")
    ReportGenerator = report_generator_module.ReportGenerator
    report_gen = ReportGenerator(base_trade_log, base_equity_curve, base_stats)
    report_gen.print_console_report()
    
    # Step 5: Run parameter optimization (500 random samples, IS only)
    logger.info("Step 5: Run parameter optimization (500 random samples, IS only)")
    param_optimizer_module = import_module_from_file("parameter_optimizer", "07_parameter_optimizer.py")
    run_parameter_optimization = param_optimizer_module.run_parameter_optimization
    save_optimization_results = param_optimizer_module.save_optimization_results
    
    # We need to set the end date to in-sample only for optimization
    original_end_date = config.END_DATE
    config.END_DATE = '2024-01-01'  # 16 months from start
    
    try:
        top_10_params, results_df = run_parameter_optimization()
        save_optimization_results(top_10_params, results_df)
        logger.info("Parameter optimization completed.")
    except Exception as e:
        logger.error(f"Parameter optimization failed: {e}")
        top_10_params = []
        results_df = None
    finally:
        config.END_DATE = original_end_date
    
    # Step 6: Run walk-forward validation (4 windows, best IS params)
    logger.info("Step 6: Run walk-forward validation (4 windows, best IS params)")
    walk_forward_module = import_module_from_file("walk_forward", "08_walk_forward.py")
    run_walk_forward = walk_forward_module.run_walk_forward
    save_walk_forward_results = walk_forward_module.save_walk_forward_results
    
    try:
        window_results, summary_df = run_walk_forward()
        save_walk_forward_results(window_results, summary_df)
        logger.info("Walk-forward validation completed.")
    except Exception as e:
        logger.error(f"Walk-forward validation failed: {e}")
        window_results = []
        summary_df = None
    
    # Step 7: Run all 10 stress tests
    logger.info("Step 7: Run all 10 stress tests")
    stress_tester_module = import_module_from_file("stress_tester", "09_stress_tester.py")
    run_stress_tests = stress_tester_module.run_stress_tests
    save_stress_test_results = stress_tester_module.save_stress_test_results
    
    try:
        stress_results = run_stress_tests()
        save_stress_test_results(stress_results)
        logger.info("Stress tests completed.")
    except Exception as e:
        logger.error(f"Stress tests failed: {e}")
        stress_results = []
    
    # Step 8: Generate all 10 charts
    logger.info("Step 8: Generate all 10 charts")
    # We already imported ReportGenerator above, but we need the generate_reports function
    generate_reports = report_generator_module.generate_reports
    
    try:
        # We need regime data for the reports - we can use the signaled data (which has regime)
        generate_reports(base_trade_log, base_equity_curve, base_stats, signaled_data)
        logger.info("Report generation completed.")
    except Exception as e:
        logger.error(f"Report generation failed: {e}")
    
    # Step 9: Print full console report (already done in step 4, but we can do a more detailed one)
    logger.info("Step 9: Print full console report (already done in base backtest)")
    # The base backtest already printed the console report via ReportGenerator
    
    # Step 10: Save all results
    logger.info("Step 10: Save all results")
    try:
        # Save trade log
        if base_trade_log:
            trades_df = pd.DataFrame(base_trade_log)
            trades_df.to_csv("trades_log.csv", index=False)
            logger.info("Saved trades_log.csv")
        
        # Save equity curve
        if base_equity_curve:
            equity_df = pd.DataFrame(base_equity_curve, columns=['timestamp', 'equity'])
            equity_df.to_csv("equity_curve.csv", index=False)
            logger.info("Saved equity_curve.csv")
        
        # Save monthly summary (we'll generate from trade log)
        if base_trade_log:
            trades_df = pd.DataFrame(base_trade_log)
            if 'exit_time' in trades_df.columns:
                trades_df['exit_time'] = pd.to_datetime(trades_df['exit_time'])
                trades_df.set_index('exit_time', inplace=True)
                monthly_summary = trades_df['net_pnl'].resample('M').agg(['sum', 'count'])
                monthly_summary.columns = ['net_pnl', 'trade_count']
                monthly_summary.to_csv("monthly_summary.csv")
                logger.info("Saved monthly_summary.csv")
        
        # Save regime log (we'll create from signaled data)
        regime_logs = []
        for instrument, df in signaled_data.items():
            if not df.empty and 'regime' in df.columns:
                df_copy = df[['regime']].copy()
                df_copy['instrument'] = instrument
                regime_logs.append(df_copy.reset_index())
        if regime_logs:
            regime_log_df = pd.concat(regime_logs, ignore_index=True)
            regime_log_df.to_csv("regime_log.csv", index=False)
            logger.info("Saved regime_log.csv")
        
        # Save optimization results (already saved by optimization step)
        # Save stress test results (already saved by stress test step)
        # Save walk-forward results (already saved by walk-forward step)
        
        # Save best parameters
        if 'top_10_params' in locals() and top_10_params:
            best_params = top_10_params[0]  # First is best
            with open("best_params.json", 'w') as f:
                json.dump(best_params, f, indent=2)
            logger.info("Saved best_params.json")
        
        logger.info("All results saved.")
    except Exception as e:
        logger.error(f"Error saving results: {e}")
    
    logger.info("Backtest complete. Check reports/ folder for all charts.")
    print("Backtest complete. Check reports/ folder for all charts.")
    print(f"Best parameter set saved to best_params.json")
    print(f"All trades saved to trades_log.csv")
    
    return True

if __name__ == "__main__":
    success = main()
    if success:
        logger.info("Pipeline completed successfully.")
        sys.exit(0)
    else:
        logger.error("Pipeline completed with errors.")
        sys.exit(1)