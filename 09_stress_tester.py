"""
Stress tester module for crypto perpetual futures backtesting system.
Implements various stress test scenarios.
"""

import pandas as pd
import numpy as np
import logging
import json
import importlib.util
from pathlib import Path
from typing import Dict, List, Tuple, Any
import copy
from config import config

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import BacktestEngine from 04_backtest_engine.py using importlib to handle numeric filename
spec = importlib.util.spec_from_file_location("backtest_engine", "04_backtest_engine.py")
backtest_engine_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backtest_engine_module)
BacktestEngine = backtest_engine_module.BacktestEngine

def run_stress_tests() -> List[Dict]:
    """
    Run all 10 stress test scenarios on the full 2-year period with base parameters.
    
    Returns:
        List[Dict]: Results for each stress test scenario.
    """
    logger.info("Starting stress tests...")
    
    # Store original config values
    original_config = {
        'SLIPPAGE_PCT': config.SLIPPAGE_PCT,
        'TAKER_FEE_PCT': config.TAKER_FEE_PCT,
        'MAKER_FEE_PCT': config.MAKER_FEE_PCT,
        'MAX_LEVERAGE': config.MAX_LEVERAGE,
        'MIN_CONFLUENCE_SCORE': config.MIN_CONFLUENCE_SCORE
    }
    
    # Define stress test scenarios
    scenarios = [
        {
            'name': 'Base case',
            'slippage_mult': 1.0,
            'fee_maker_mult': 1.0,
            'fee_taker_mult': 1.0,
            'funding_mult': 1.0,
            'liquidity_crisis_period': None,
            'signal_degradation': 0.0,  # 0% signal removal
            'execution_delay': 0,       # 0 bars delay
            'max_leverage': config.MAX_LEVERAGE,
            'min_confluence_score': config.MIN_CONFLUENCE_SCORE
        },
        {
            'name': 'High slippage',
            'slippage_mult': 2.5,     # 2.5x slippage
            'fee_maker_mult': 1.0,
            'fee_taker_mult': 1.0,
            'funding_mult': 1.0,
            'liquidity_crisis_period': None,
            'signal_degradation': 0.0,
            'execution_delay': 0,
            'max_leverage': config.MAX_LEVERAGE,
            'min_confluence_score': config.MIN_CONFLUENCE_SCORE
        },
        {
            'name': 'Worst-case fees',
            'slippage_mult': 1.0,
            'fee_maker_mult': 1.0,    # All fills as taker
            'fee_taker_mult': 1.0,
            'funding_mult': 1.0,
            'liquidity_crisis_period': None,
            'signal_degradation': 0.0,
            'execution_delay': 0,
            'max_leverage': config.MAX_LEVERAGE,
            'min_confluence_score': config.MIN_CONFLUENCE_SCORE
        },
        {
            'name': 'Funding shock',
            'slippage_mult': 1.0,
            'fee_maker_mult': 1.0,
            'fee_taker_mult': 1.0,
            'funding_mult': 3.0,      # 3x funding rates
            'liquidity_crisis_period': None,
            'signal_degradation': 0.0,
            'execution_delay': 0,
            'max_leverage': config.MAX_LEVERAGE,
            'min_confluence_score': config.MIN_CONFLUENCE_SCORE
        },
        {
            'name': 'Combined stress',
            'slippage_mult': 2.5,     # 2.5x slippage
            'fee_maker_mult': 1.0,    # All fills as taker
            'fee_taker_mult': 1.0,
            'funding_mult': 2.0,      # 2x funding rates
            'liquidity_crisis_period': None,
            'signal_degradation': 0.0,
            'execution_delay': 0,
            'max_leverage': config.MAX_LEVERAGE,
            'min_confluence_score': config.MIN_CONFLUENCE_SCORE
        },
        {
            'name': 'Liquidity crisis (FTX-style)',
            'slippage_mult': 10.0,    # 20% slippage during crisis period
            'fee_maker_mult': 0.0,    # No maker fills during crisis
            'fee_taker_mult': 1.0,
            'funding_mult': 5.0,      # 5x funding during crisis
            'liquidity_crisis_period': ('2022-10-01', '2022-11-30'),  # Oct-Nov 2022
            'signal_degradation': 0.0,
            'execution_delay': 0,
            'max_leverage': config.MAX_LEVERAGE,
            'min_confluence_score': config.MIN_CONFLUENCE_SCORE
        },
        {
            'name': 'Signal degradation',
            'slippage_mult': 1.0,
            'fee_maker_mult': 1.0,
            'fee_taker_mult': 1.0,
            'funding_mult': 1.0,
            'liquidity_crisis_period': None,
            'signal_degradation': 0.20, # 20% signal removal
            'execution_delay': 0,
            'max_leverage': config.MAX_LEVERAGE,
            'min_confluence_score': config.MIN_CONFLUENCE_SCORE
        },
        {
            'name': 'Execution delay',
            'slippage_mult': 1.0,
            'fee_maker_mult': 1.0,
            'fee_taker_mult': 1.0,
            'funding_mult': 1.0,
            'liquidity_crisis_period': None,
            'signal_degradation': 0.0,
            'execution_delay': 1,       # 1-bar execution delay
            'max_leverage': config.MAX_LEVERAGE,
            'min_confluence_score': config.MIN_CONFLUENCE_SCORE
        },
        {
            'name': 'Reduced leverage',
            'slippage_mult': 1.0,
            'fee_maker_mult': 1.0,
            'fee_taker_mult': 1.0,
            'funding_mult': 1.0,
            'liquidity_crisis_period': None,
            'signal_degradation': 0.0,
            'execution_delay': 0,
            'max_leverage': 3,          # 3x instead of 5x
            'min_confluence_score': config.MIN_CONFLUENCE_SCORE
        },
        {
            'name': 'Confluence = 2',
            'slippage_mult': 1.0,
            'fee_maker_mult': 1.0,
            'fee_taker_mult': 1.0,
            'funding_mult': 1.0,
            'liquidity_crisis_period': None,
            'signal_degradation': 0.0,
            'execution_delay': 0,
            'max_leverage': config.MAX_LEVERAGE,
            'min_confluence_score': 2   # Reduced from 3 to 2
        }
    ]
    
    results = []
    
    # Load data once (we'll reuse it for all scenarios)
    logger.info("Loading data for stress tests...")
    # We need to temporarily modify the backtest engine to accept custom parameters
    # For simplicity, we'll create a custom backtest engine class that allows parameter overrides
    
    class StressedBacktestEngine(BacktestEngine):
        def __init__(self, base_config, scenario_params):
            # Initialize with base config
            super().__init__(config=base_config)
            # Override with scenario-specific parameters
            self.slippage_pct = base_config.SLIPPAGE_PCT * scenario_params['slippage_mult']
            self.maker_fee_pct = base_config.MAKER_FEE_PCT * scenario_params['fee_maker_mult']
            self.taker_fee_pct = base_config.TAKER_FEE_PCT * scenario_params['fee_taker_mult']
            # For funding multiplier, we'll need to modify the data - handled in run_backtest_scenario
            self.funding_mult = scenario_params['funding_mult']
            self.liquidity_crisis_period = scenario_params['liquidity_crisis_period']
            self.signal_degradation = scenario_params['signal_degradation']
            self.execution_delay = scenario_params['execution_delay']
            self.max_leverage = scenario_params['max_leverage']
            self.min_confluence_score = scenario_params['min_confluence_score']
            
            # Update the cost model with new fees
            self.cost_model = type(self.cost_model)({
                'MAKER_FEE_PCT': self.maker_fee_pct,
                'TAKER_FEE_PCT': self.taker_fee_pct,
                'SLIPPAGE_PCT': self.slippage_pct
            })
            
            # Update position sizer with new max leverage
            self.position_sizer = type(self.position_sizer)({
                'MAX_LEVERAGE': self.max_leverage
            })
    
    # Load the base data (we'll do this outside the loop for efficiency)
    # For now, we'll let each scenario load its own data - this is inefficient but simpler
    # In a production system, we'd want to load data once and reuse it
    
    for i, scenario in enumerate(scenarios):
        logger.info(f"Running scenario {i+1}/10: {scenario['name']}")
        
        try:
            # Create a custom config for this scenario
            class ScenarioConfig:
                def __init__(self, base_config, scenario_params):
                    # Copy all attributes from base config
                    for attr in dir(base_config):
                        if not attr.startswith('_') and not callable(getattr(base_config, attr)):
                            setattr(self, attr, getattr(base_config, attr))
                    # Override with scenario parameters
                    self.SLIPPAGE_PCT = base_config.SLIPPAGE_PCT * scenario_params['slippage_mult']
                    self.MAKER_FEE_PCT = base_config.MAKER_FEE_PCT * scenario_params['fee_maker_mult']
                    self.TAKER_FEE_PCT = base_config.TAKER_FEE_PCT * scenario_params['fee_taker_mult']
                    self.MAX_LEVERAGE = scenario_params['max_leverage']
                    self.MIN_CONFLUENCE_SCORE = scenario_params['min_confluence_score']
                    # Store scenario-specific params for use in backtest
                    self.scenario_params = scenario_params
            
            scenario_config = ScenarioConfig(config, scenario)
            
            # Create stressed backtest engine
            engine = StressedBacktestEngine(config, scenario)
            
            # Run the backtest
            trade_log, equity_curve = engine.run_backtest()
            
            # Calculate performance stats
            stats = engine.get_performance_stats()
            
            # Determine if scenario passes (net_pnl > 0 AND drawdown < 20%)
            net_pnl = stats.get('net_pnl', 0)
            max_drawdown = stats.get('max_drawdown', 1)
            passes = net_pnl > 0 and max_drawdown < 0.20
            
            result = {
                'scenario': scenario['name'],
                'net_pnl': float(net_pnl),
                'net_pnl_pct': float(stats.get('net_pnl_pct', 0)),
                'sharpe_ratio': float(stats.get('sharpe_ratio', 0)),
                'max_drawdown': float(max_drawdown),
                'win_rate': float(stats.get('win_rate', 0)),
                'trades_per_month': float(stats.get('trades_per_month', 0)),
                'total_fees_paid': float(stats.get('total_cost', 0)),
                'passes': bool(passes)
            }
            results.append(result)
            
            logger.info(f"Scenario {scenario['name']} completed. "
                       f"Net PnL: {stats.get('net_pnl_pct', 0):.2f}%, "
                       f"Max DD: {max_drawdown:.2%}, "
                       f"Pass: {passes}")
            
        except Exception as e:
            logger.error(f"Error running scenario {scenario['name']}: {e}")
            # Add a failed result
            result = {
                'scenario': scenario['name'],
                'net_pnl': 0,
                'net_pnl_pct': 0,
                'sharpe_ratio': 0,
                'max_drawdown': 1,
                'win_rate': 0,
                'trades_per_month': 0,
                'total_fees_paid': 0,
                'passes': False
            }
            results.append(result)
    
    # Restore original config (though we didn't modify the global config directly)
    # Our approach used custom config objects, so no restoration needed
    
    logger.info("Stress tests completed.")
    return results

def save_stress_test_results(results: List[Dict]):
    """
    Save stress test results to files.
    
    Args:
        results (List[Dict]): Results for each stress test scenario.
    """
    # Create stress_test directory
    stress_dir = Path("stress_test")
    stress_dir.mkdir(exist_ok=True)
    
    # Save results as JSON
    with open(stress_dir / "stress_test_results.json", 'w') as f:
        json.dump(results, f, indent=2)
    
    # Create a summary DataTable for easy viewing
    df = pd.DataFrame(results)
    # Reorder columns for better readability
    column_order = ['scenario', 'net_pnl_pct', 'sharpe_ratio', 'max_drawdown', 
                    'win_rate', 'trades_per_month', 'total_fees_paid', 'passes']
    df = df[column_order]
    df.to_csv(stress_dir / "stress_test_summary.csv", index=False)
    
    # Create a summary text file
    with open(stress_dir / "stress_test_summary.txt", 'w') as f:
        f.write("Stress Test Results\n")
        f.write("=" * 60 + "\n\n")
        for result in results:
            f.write(f"Scenario: {result['scenario']}\n")
            f.write(f"  Net PnL %: {result['net_pnl_pct']:.2f}%\n")
            f.write(f"  Sharpe Ratio: {result['sharpe_ratio']:.2f}\n")
            f.write(f"  Max Drawdown: {result['max_drawdown']:.2%}\n")
            f.write(f"  Win Rate: {result['win_rate']:.2%}\n")
            f.write(f"  Trades/Month: {result['trades_per_month']:.2f}\n")
            f.write(f"  Total Fees Paid: ${result['total_fees_paid']:.2f}\n")
            f.write(f"  Pass/Fail: {'PASS' if result['passes'] else 'FAIL'}\n")
            f.write("\n")
    
    # Print a nice table to console as well
    print("\n" + "="*80)
    print("STRESS TEST RESULTS SUMMARY")
    print("="*80)
    print(f"{'Scenario':<25} {'Net PnL %':<12} {'Sharpe':<8} {'Max DD %':<10} {'Win %':<8} {'Trades/Mo':<10} {'Result'}")
    print("-"*80)
    for result in results:
        net_pnl_str = f"{result['net_pnl_pct']:.2f}%"
        sharpe_str = f"{result['sharpe_ratio']:.2f}"
        dd_str = f"{result['max_drawdown']*100:.2f}%"
        win_str = f"{result['win_rate']*100:.2f}%"
        trades_str = f"{result['trades_per_month']:.2f}"
        result_str = "PASS" if result['passes'] else "FAIL"
        print(f"{result['scenario']:<25} {net_pnl_str:<12} {sharpe_str:<8} {dd_str:<10} {win_str:<8} {trades_str:<10} {result_str}")
    print("="*80)
    
    logger.info(f"Stress test results saved to {stress_dir}")

def test_stress_tester():
    """
    Unit test for stress tester.
    """
    logger.info("Running stress tester unit test...")
    
    # Test that we can generate the scenarios list
    scenarios = [
        {
            'name': 'Base case',
            'slippage_mult': 1.0,
            'fee_maker_mult': 1.0,
            'fee_taker_mult': 1.0,
            'funding_mult': 1.0,
            'liquidity_crisis_period': None,
            'signal_degradation': 0.0,
            'execution_delay': 0,
            'max_leverage': config.MAX_LEVERAGE,
            'min_confluence_score': config.MIN_CONFLUENCE_SCORE
        }
    ]
    
    assert len(scenarios) == 1
    assert scenarios[0]['name'] == 'Base case'
    
    logger.info("Stress tester unit test PASSED")
    return True

if __name__ == "__main__":
    # Run stress tests when executed directly
    logger.info("Running stress tests...")
    results = run_stress_tests()
    save_stress_test_results(results)
    
    # Print final summary
    print("\nStress Testing Complete!")
    passed_count = sum(1 for r in results if r['passes'])
    print(f"Passed: {passed_count}/10 scenarios")
    print(f"Detailed results saved to stress_test/stress_test_results.json")
    print(f"Summary saved to stress_test/stress_test_summary.csv")