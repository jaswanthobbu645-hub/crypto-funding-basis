import os
import subprocess
import sys

# Define the scripts to run
scripts = ['05_funding_basis.py', '05b_taker_test.py']
base_dir = r'C:\Users\Avinash\crypto_backtest'

all_good = True
for script in scripts:
    path = os.path.join(base_dir, script)
    print(f'Running {script}...')
    result = subprocess.run([sys.executable, path], capture_output=True, text=True)
    if result.returncode != 0:
        print(f'  FAILED: {result.stderr}')
        all_good = False
    else:
        print('  OK')
        # Check for expected content
        if script == '05_funding_basis.py' and 'PERFORMANCE SUMMARY' not in result.stdout:
            print('  WARNING: Missing expected output')
        if script == '05b_taker_test.py' and 'TAKER FEE RESULTS' not in result.stdout:
            print('  WARNING: Missing expected output')

if all_good:
    print('\nAll scripts executed successfully.')
else:
    print('\nSome scripts failed.')
    sys.exit(1)