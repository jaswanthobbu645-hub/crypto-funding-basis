import ccxt
import pandas as pd
import time
import os

SYMBOLS = [
    'BTC/USDT:USDT', 'ETH/USDT:USDT', 'BNB/USDT:USDT', 'XRP/USDT:USDT', 
    'ADA/USDT:USDT', 'MATIC/USDT:USDT', 'DOT/USDT:USDT', 'LTC/USDT:USDT', 
    'TRX/USDT:USDT', 'ATOM/USDT:USDT', 'ETC/USDT:USDT', 'BCH/USDT:USDT',
    'ICP/USDT:USDT', 'HBAR/USDT:USDT', 'VET/USDT:USDT', 'ALGO/USDT:USDT',
    'FTM/USDT:USDT', 'GRT/USDT:USDT', 'SAND/USDT:USDT', 'MANA/USDT:USDT',
    'AXS/USDT:USDT', 'EGLD/USDT:USDT', 'THETA/USDT:USDT', 'RUNE/USDT:USDT',
    'AAVE/USDT:USDT', 'UNI/USDT:USDT'
]

DATA_DIR = 'data/expanded'
os.makedirs(DATA_DIR, exist_ok=True)

exchange = ccxt.binanceusdm()

def fetch_asset(symbol, days=730):
    print(f'Fetching {symbol}...')
    try:
        since = exchange.milliseconds() - (days * 24 * 60 * 60 * 1000)
        all_ohlcv = []
        while since < exchange.milliseconds():
            batch = exchange.fetch_ohlcv(symbol, timeframe='1h', since=since, limit=1500)
            if not batch: break
            all_ohlcv.extend(batch)
            since = batch[-1][0] + 1
            time.sleep(exchange.rateLimit / 1000)
        
        df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df = df.drop_duplicates(subset=['timestamp']).sort_values('timestamp').reset_index(drop=True)
        
        # Fetch funding history
        funding_since = exchange.milliseconds() - (days * 24 * 60 * 60 * 1000)
        all_funding = []
        while funding_since < exchange.milliseconds():
            try:
                fb = exchange.fetch_funding_rate_history(symbol, since=funding_since, limit=1000)
                if not fb: break
                all_funding.extend(fb)
                funding_since = fb[-1]['timestamp'] + 1
                time.sleep(exchange.rateLimit / 1000)
            except Exception as e:
                print(f'  Funding error: {e}')
                break
        
        if all_funding:
            fdf = pd.DataFrame(all_funding)
            fdf['timestamp'] = pd.to_datetime(fdf['timestamp'], unit='ms')
            fdf = fdf[['timestamp', 'fundingRate']].drop_duplicates(subset=['timestamp'])
            df = df.merge(fdf, on='timestamp', how='left')
        else:
            df['fundingRate'] = 0
        
        df['fundingRate'] = df['fundingRate'].ffill().fillna(0)
        
        clean_name = symbol.replace('/', '_').replace(':', '_')
        out = os.path.join(DATA_DIR, f'{clean_name}.parquet')
        df.to_parquet(out)
        print(f'  Saved {len(df)} rows to {out}')
        return df
    except Exception as e:
        print(f'  FAILED {symbol}: {e}')
        return None

if __name__ == '__main__':
    for sym in SYMBOLS:
        fetch_asset(sym)
        time.sleep(1)