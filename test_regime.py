import sys
import importlib
import pickle
import pandas as pd

# Import the module using importlib because it starts with a number
module_name = '02_regime_detector'
regime_detector = importlib.import_module(module_name)
RegimeDetector = regime_detector.RegimeDetector

with open(r'data\combined_all.pkl', 'rb') as f:
    data = pickle.load(f)
# Take first instrument
instrument = 'SOL-USDT-PERP'
df = data[instrument].copy()
print(f'Testing {instrument} with {len(df)} rows')
detector = RegimeDetector(confirmation_bars=2)
result = detector.detect_regime(df)
print('Regime counts:')
print(result['regime'].value_counts())
print('Regime percentages:')
print(result['regime'].value_counts(normalize=True) * 100)
# Call print method if exists
detector.print_regime_distribution(result)