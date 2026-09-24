import re

with open('src/data/download_expanded_v2.py', 'r') as f:
    content = f.read()

# Define the new SYMBOLS list
new_symbols = [
    'SOL/USDT:USDT', 'DOGE/USDT:USDT', 'ARB/USDT:USDT', 'SUI/USDT:USDT',
    'MATIC/USDT:USDT', 'AVAX/USDT:USDT', 'LINK/USDT:USDT', 'OP/USDT:USDT',
    'INJ/USDT:USDT', 'APT/USDT:USDT', 'NEAR/USDT:USDT', 'FIL/USDT:USDT',
    'TIA/USDT:USDT', 'SEI/USDT:USDT', 'WIF/USDT:USDT',
    'BTC/USDT:USDT', 'ETH/USDT:USDT', 'BNB/USDT:USDT', 'XRP/USDT:USDT',
    'ADA/USDT:USDT', 'DOT/USDT:USDT', 'LTC/USDT:USDT', 'TRX/USDT:USDT',
    'ATOM/USDT:USDT', 'ETC/USDT:USDT', 'BCH/USDT:USDT',
    'ICP/USDT:USDT', 'HBAR/USDT:USDT', 'VET/USDT:USDT', 'ALGO/USDT:USDT',
    'FTM/USDT:USDT', 'GRT/USDT:USDT', 'SAND/USDT:USDT', 'MANA/USDT:USDT',
    'AXS/USDT:USDT', 'EGLD/USDT:USDT', 'THETA/USDT:USDT',
    'RUNE/USDT:USDT', 'AAVE/USDT:USDT', 'UNI/USDT:USDT'
]

# Remove duplicates while preserving order
seen = set()
unique_symbols = []
for s in new_symbols:
    base = s.split('/')[0]
    if base not in seen:
        seen.add(base)
        unique_symbols.append(s)

# Build the new list string
new_list_str = '[\n    ' + ',\n    '.join([f"'{s}'" for s in unique_symbols]) + '\n]'

# Replace the old SYMBOLS list
new_content = re.sub(r'SYMBOLS = \[.*?\]', f'SYMBOLS = {new_list_str}', content, flags=re.DOTALL)

with open('src/data/download_expanded_v2.py', 'w') as f:
    f.write(new_content)

print(f'Total unique symbols: {len(unique_symbols)}')
print('First few:', unique_symbols[:5])
