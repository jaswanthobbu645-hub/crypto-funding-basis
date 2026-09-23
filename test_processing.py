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
load_existing_data = import_module_from_file('01_data_download', '01_data_download.py').load_existing_data
RegimeDetector = import_module_from_file('02_regime_detector', '02_regime_detector.py').RegimeDetector
generate_signals = import_module_from_file('03_signals', '03_signals.py').generate_signals

print('Loading existing data...')
data = load_existing_data()
if data is None:
    print('No data')
    sys.exit(1)
print('Instruments:', list(data.keys()))
regime_detector = RegimeDetector(confirmation_bars=config.REGIME_CONFIRM_BARS)
processed = {}
for inst, df in data.items():
    print(f'Processing {inst}...')
    df = df.copy()
    df.set_index('timestamp', inplace=True)
    df.sort_index(inplace=True)
    df = regime_detector.detect_regime(df)
    df = generate_signals(df)
    processed[inst] = df
print('Saving processed data...')
import pickle
from pathlib import Path
processed_file = Path('data/processed_all.pkl')
processed_file.parent.mkdir(exist_ok=True)
with open(processed_file, 'wb') as f:
    pickle.dump(processed, f)
print('Saved to', processed_file)