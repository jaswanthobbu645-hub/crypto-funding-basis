"""
Data download module for crypto perpetual futures backtesting system.
Fetches historical data from Bybit API or generates synthetic data as fallback.
"""

import pandas as pd
import numpy as np
import requests
import time
import logging
from pathlib import Path
from datetime import datetime, timedelta
import json
import os

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Import config
from config import config

# Constants
BASE_URL = "https://api.bybit.com/v5/market"
DATA_DIR = Path("data")
COMBINED_FILE = DATA_DIR / "combined_all.pkl"

# Instruments mapping (Bybit uses without hyphens for spot, but for linear perp we use the symbol without hyphens)
# Bybit linear symbols: SOLUSDT, DOGEUSDT, etc.
INSTRUMENT_MAP = {
    'SOL-USDT-PERP': 'SOLUSDT',
    'DOGE-USDT-PERP': 'DOGEUSDT',
    'ARB-USDT-PERP': 'ARBUSDT',
    'SUI-USDT-PERP': 'SUIUSDT'
}

def fetch_ohlcv(symbol: str, start_ts: int, end_ts: int, max_retries: int = 3) -> pd.DataFrame:
    """
    Fetch OHLCV data from Bybit for given symbol and time range.
    """
    endpoint = f"{BASE_URL}/kline"
    params = {
        "category": "linear",
        "symbol": symbol,
        "interval": "60",  # 1 hour
        "start": start_ts,
        "end": end_ts,
        "limit": 200
    }
    
    for attempt in range(max_retries):
        try:
            response = requests.get(endpoint, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data["retCode"] != 0:
                logger.error(f"Bybit API error: {data['retMsg']}")
                if attempt < max_retries - 1:
                    time.sleep(5)
                    continue
                else:
                    return pd.DataFrame()
            
            klines = data["result"]["list"]
            if not klines:
                return pd.DataFrame()
            
            df = pd.DataFrame(klines, columns=[
                "timestamp", "open", "high", "low", "close", "volume", "turnover"
            ])
            # Convert timestamp to datetime (in milliseconds)
            df["timestamp"] = pd.to_datetime(df["timestamp"].astype(int), unit='ms', utc=True)
            # Convert numeric columns
            for col in ["open", "high", "low", "close", "volume", "turnover"]:
                df[col] = pd.to_numeric(df[col])
            
            logger.info(f"Fetched {len(df)} OHLCV candles for {symbol} from {df['timestamp'].min()} to {df['timestamp'].max()}")
            return df
            
        except Exception as e:
            logger.error(f"Error fetching OHLCV for {symbol} (attempt {attempt+1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(5)
            else:
                return pd.DataFrame()

def fetch_open_interest(symbol: str, start_ts: int, end_ts: int, max_retries: int = 3) -> pd.DataFrame:
    """
    Fetch Open Interest data from Bybit for given symbol and time range.
    """
    endpoint = f"{BASE_URL}/open-interest"
    params = {
        "category": "linear",
        "symbol": symbol,
        "intervalTime": "1h",  # 1 hour
        "startTime": start_ts,
        "endTime": end_ts,
        "limit": 200
    }
    
    for attempt in range(max_retries):
        try:
            response = requests.get(endpoint, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data["retCode"] != 0:
                logger.error(f"Bybit API error: {data['retMsg']}")
                if attempt < max_retries - 1:
                    time.sleep(5)
                    continue
                else:
                    return pd.DataFrame()
            
            oi_data = data["result"]["list"]
            if not oi_data:
                return pd.DataFrame()
            
            df = pd.DataFrame(oi_data, columns=["timestamp", "openInterest"])
            df["timestamp"] = pd.to_datetime(df["timestamp"].astype(int), unit='ms', utc=True)
            df["openInterest"] = pd.to_numeric(df["openInterest"])
            
            logger.info(f"Fetched {len(df)} OI candles for {symbol} from {df['timestamp'].min()} to {df['timestamp'].max()}")
            return df
            
        except Exception as e:
            logger.error(f"Error fetching OI for {symbol} (attempt {attempt+1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(5)
            else:
                return pd.DataFrame()

def fetch_funding_rate(symbol: str, start_ts: int, end_ts: int, max_retries: int = 3) -> pd.DataFrame:
    """
    Fetch Funding Rate history from Bybit for given symbol and time range.
    Funding rate is every 8 hours.
    """
    endpoint = f"{BASE_URL}/funding/history"
    params = {
        "category": "linear",
        "symbol": symbol,
        "startTime": start_ts,
        "endTime": end_ts,
        "limit": 200
    }
    
    for attempt in range(max_retries):
        try:
            response = requests.get(endpoint, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data["retCode"] != 0:
                logger.error(f"Bybit API error: {data['retMsg']}")
                if attempt < max_retries - 1:
                    time.sleep(5)
                    continue
                else:
                    return pd.DataFrame()
            
            funding_data = data["result"]["list"]
            if not funding_data:
                return pd.DataFrame()
            
            df = pd.DataFrame(funding_data, columns=["fundingRateTimestamp", "fundingRate"])
            df["timestamp"] = pd.to_datetime(df["fundingRateTimestamp"].astype(int), unit='ms', utc=True)
            df["fundingRate"] = pd.to_numeric(df["fundingRate"])
            df = df[["timestamp", "fundingRate"]]
            
            logger.info(f"Fetched {len(df)} funding rate records for {symbol} from {df['timestamp'].min()} to {df['timestamp'].max()}")
            return df
            
        except Exception as e:
            logger.error(f"Error fetching funding rate for {symbol} (attempt {attempt+1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(5)
            else:
                return pd.DataFrame()

def merge_data_for_instrument(symbol: str, ohlcv_df: pd.DataFrame, oi_df: pd.DataFrame, funding_df: pd.DataFrame) -> pd.DataFrame:
    """
    Merge OHLCV, OI, and funding data for a single instrument.
    """
    if ohlcv_df.empty:
        logger.warning(f"No OHLCV data for {symbol}, skipping merge")
        return pd.DataFrame()
    
    # Start with OHLCV as base
    df = ohlcv_df.copy()
    
    # Merge OI (left join on timestamp)
    if not oi_df.empty:
        df = df.merge(oi_df, on="timestamp", how="left")
    else:
        df["openInterest"] = np.nan
    
    # Merge funding (left join on timestamp)
    if not funding_df.empty:
        df = df.merge(funding_df, on="timestamp", how="left")
    else:
        df["fundingRate"] = np.nan
    
    # Forward fill funding rate (since it's 8h, we want to fill for each hour)
    df["fundingRate"] = df["fundingRate"].ffill()
    
    # Sort by timestamp
    df = df.sort_values("timestamp").reset_index(drop=True)
    
    logger.info(f"Merged data for {symbol}: {len(df)} rows")
    return df

def generate_synthetic_data(symbol: str) -> pd.DataFrame:
    """
    Generate realistic synthetic data for backtesting when API is unavailable.
    """
    logger.warning(f"USING SYNTHETIC DATA for {symbol} — replace with real data before live trading")
    
    # Define time range
    start_date = pd.Timestamp(config.START_DATE, tz='UTC')
    end_date = pd.Timestamp(config.END_DATE, tz='UTC')
    # Generate hourly timestamps
    timestamps = pd.date_range(start=start_date, end=end_date, freq='h', tz='UTC')
    
    n = len(timestamps)
    logger.info(f"Generating {n} hourly bars for {symbol}")
    
    # Base price process (random walk with drift and volatility clustering)
    np.random.seed(42)  # For reproducibility
    
    # Daily returns parameters
    daily_mean = 0.001
    daily_std = 0.035
    # Convert to hourly (assuming 24 hours in a day)
    hourly_mean = daily_mean / 24
    hourly_std = daily_std / np.sqrt(24)
    
    # Generate returns with volatility clustering (GARCH-like)
    returns = np.zeros(n)
    volatility = np.zeros(n)
    volatility[0] = hourly_std
    
    for i in range(1, n):
        # GARCH(1,1) style volatility update
        volatility[i] = np.sqrt(0.000001 + 0.06 * returns[i-1]**2 + 0.92 * volatility[i-1]**2)
        returns[i] = np.random.normal(hourly_mean, volatility[i])
    
    # Generate price series
    log_returns = returns
    log_prices = np.cumsum(log_returns)
    # Start at a reasonable price for each instrument
    base_prices = {
        'SOLUSDT': 20.0,
        'DOGEUSDT': 0.08,
        'ARBUSDT': 1.0,
        'SUIUSDT': 0.5
    }
    base_price = base_prices.get(symbol, 10.0)
    close_prices = base_price * np.exp(log_prices)
    
    # Generate OHLC from close prices with some randomness
    high_prices = close_prices * (1 + np.abs(np.random.normal(0, 0.01, n)))
    low_prices = close_prices * (1 - np.abs(np.random.normal(0, 0.01, n)))
    open_prices = np.roll(close_prices, 1)
    open_prices[0] = close_prices[0]
    
    # Ensure high >= low and high >= open,close and low <= open,close
    high_prices = np.maximum(high_prices, np.maximum(open_prices, close_prices))
    low_prices = np.minimum(low_prices, np.minimum(open_prices, close_prices))
    
    # Generate volume (correlated with volatility and returns magnitude)
    volume_base = np.random.lognormal(mean=10, sigma=0.5, size=n)
    volume = volume_base * (1 + 5 * np.abs(returns))  # Higher volume on big moves
    
    # Generate Open Interest (random walk with drift and bounds)
    oi = np.zeros(n)
    oi[0] = 500_000_000  # Start at 500M
    for i in range(1, n):
        drift = 0.0001  # Slight upward drift
        shock = np.random.normal(0, 0.02)
        oi[i] = oi[i-1] * (1 + drift + shock)
        # Apply bounds: 100M to 2B
        oi[i] = np.clip(oi[i], 100_000_000, 2_000_000_000)
    
    # Generate funding rate (mean-reverting process with bounds)
    funding = np.zeros(n)
    funding[0] = 0.0001  # Start at 0.01%
    for i in range(1, n):
        # Mean reversion to 0.01% with half-life of ~80 hours
        mean_reversion = 0.0001 * (1 - np.exp(-0.01))  # Adjust for hourly
        shock = np.random.normal(0, 0.00005)  # Std 0.005%
        funding[i] = funding[i-1] + mean_reversion * (0.0001 - funding[i-1]) + shock
        # Apply bounds: -0.15% to +0.15%
        funding[i] = np.clip(funding[i], -0.0015, 0.0015)
    
    # Add correlation with BTC (simulate by adding common factor)
    # Generate a common BTC-like factor
    btc_factor = np.cumsum(np.random.normal(0, hourly_std/2, n))
    # Incorporate 75% correlation: 0.75 * btc_factor + 0.25 * instrument-specific
    close_prices = base_price * np.exp(0.75 * btc_factor + 0.25 * (log_prices - np.mean(log_prices)))
    # Adjust OHLC accordingly
    high_prices = close_prices * (1 + np.abs(np.random.normal(0, 0.01, n)))
    low_prices = close_prices * (1 - np.abs(np.random.normal(0, 0.01, n)))
    open_prices = np.roll(close_prices, 1)
    open_prices[0] = close_prices[0]
    high_prices = np.maximum(high_prices, np.maximum(open_prices, close_prices))
    low_prices = np.minimum(low_prices, np.minimum(open_prices, close_prices))
    
    # Add volatility clustering to returns (already done)
    
    # Add crash events (3 sudden -25% in 3 days)
    crash_starts = [int(0.2 * n), int(0.5 * n), int(0.8 * n)]
    for start_idx in crash_starts:
        end_idx = min(start_idx + 72, n)  # 3 days = 72 hours
        if end_idx > start_idx:
            crash_factor = np.linspace(0, -0.25, end_idx - start_idx)
            close_prices[start_idx:end_idx] *= (1 + crash_factor)
            # Adjust OHLC
            high_prices[start_idx:end_idx] *= (1 + crash_factor)
            low_prices[start_idx:end_idx] *= (1 + crash_factor)
            open_prices[start_idx:end_idx] *= (1 + crash_factor)
    
    # Add squeeze events (2 sudden +40% in 5 days)
    squeeze_starts = [int(0.3 * n), int(0.6 * n)]
    for start_idx in squeeze_starts:
        end_idx = min(start_idx + 120, n)  # 5 days = 120 hours
        if end_idx > start_idx:
            squeeze_factor = np.linspace(0, 0.40, end_idx - start_idx)
            close_prices[start_idx:end_idx] *= (1 + squeeze_factor)
            high_prices[start_idx:end_idx] *= (1 + squeeze_factor)
            low_prices[start_idx:end_idx] *= (1 + squeeze_factor)
            open_prices[start_idx:end_idx] *= (1 + squeeze_factor)
    
    # Recalculate returns after events
    log_returns = np.diff(np.log(close_prices), prepend=np.log(close_prices[0]))
    
    # Build DataFrame
    df = pd.DataFrame({
        'timestamp': timestamps,
        'open': open_prices,
        'high': high_prices,
        'low': low_prices,
        'close': close_prices,
        'volume': volume,
        'turnover': volume * close_prices,  # Approximate turnover
        'openInterest': oi,
        'fundingRate': funding
    })
    
    logger.info(f"Generated synthetic data for {symbol} with {len(df)} rows")
    return df

def download_instrument_data(instrument: str) -> pd.DataFrame:
    """
    Download and process data for a single instrument.
    """
    symbol = INSTRUMENT_MAP[instrument]
    logger.info(f"Processing instrument: {instrument} (Bybit symbol: {symbol})")
    
    # Convert date range to timestamps
    start_ts = int(pd.Timestamp(config.START_DATE, tz='UTC').timestamp() * 1000)
    end_ts = int(pd.Timestamp(config.END_DATE, tz='UTC').timestamp() * 1000)
    
    # We'll fetch data in chunks due to API limits
    chunk_size = 200  # max candles per request
    current_ts = start_ts
    all_ohlcv = []
    all_oi = []
    all_funding = []
    
    # Fetch OHLCV in chunks
    while current_ts < end_ts:
        chunk_end_ts = min(current_ts + (chunk_size * 60 * 60 * 1000), end_ts)  # chunk_size hours in ms
        ohlcv_df = fetch_ohlcv(symbol, current_ts, chunk_end_ts)
        if ohlcv_df.empty:
            logger.warning(f"No OHLCV data returned for chunk starting at {current_ts}")
            break
        all_ohlcv.append(ohlcv_df)
        # Move to next chunk (start from the last timestamp we got)
        if len(ohlcv_df) > 0:
            last_ts = ohlcv_df['timestamp'].max()
            current_ts = int(last_ts.timestamp() * 1000) + (60 * 60 * 1000)  # next hour
        else:
            break
        time.sleep(0.5)  # Rate limit safety
    
    # Fetch OI in chunks
    current_ts = start_ts
    while current_ts < end_ts:
        chunk_end_ts = min(current_ts + (chunk_size * 60 * 60 * 1000), end_ts)
        oi_df = fetch_open_interest(symbol, current_ts, chunk_end_ts)
        if oi_df.empty:
            logger.warning(f"No OI data returned for chunk starting at {current_ts}")
            break
        all_oi.append(oi_df)
        if len(oi_df) > 0:
            last_ts = oi_df['timestamp'].max()
            current_ts = int(last_ts.timestamp() * 1000) + (60 * 60 * 1000)
        else:
            break
        time.sleep(0.5)
    
    # Fetch funding in chunks (funding is 8h, but we can still chunk by time)
    current_ts = start_ts
    while current_ts < end_ts:
        chunk_end_ts = min(current_ts + (chunk_size * 60 * 60 * 1000), end_ts)
        funding_df = fetch_funding_rate(symbol, current_ts, chunk_end_ts)
        if funding_df.empty:
            logger.warning(f"No funding data returned for chunk starting at {current_ts}")
            break
        all_funding.append(funding_df)
        if len(funding_df) > 0:
            last_ts = funding_df['timestamp'].max()
            current_ts = int(last_ts.timestamp() * 1000) + (60 * 60 * 1000)
        else:
            break
        time.sleep(0.5)
    
    # Combine chunks
    ohlcv_combined = pd.concat(all_ohlcv, ignore_index=True) if all_ohlcv else pd.DataFrame()
    oi_combined = pd.concat(all_oi, ignore_index=True) if all_oi else pd.DataFrame()
    funding_combined = pd.concat(all_funding, ignore_index=True) if all_funding else pd.DataFrame()
    
    # Remove duplicates (just in case)
    if not ohlcv_combined.empty:
        ohlcv_combined = ohlcv_combined.drop_duplicates(subset=['timestamp']).sort_values('timestamp')
    if not oi_combined.empty:
        oi_combined = oi_combined.drop_duplicates(subset=['timestamp']).sort_values('timestamp')
    if not funding_combined.empty:
        funding_combined = funding_combined.drop_duplicates(subset=['timestamp']).sort_values('timestamp')
    
    # Merge data
    df = merge_data_for_instrument(instrument, ohlcv_combined, oi_combined, funding_combined)
    
    return df

def download_all_data() -> dict:
    """
    Download data for all instruments and return a dictionary of DataFrames.
    """
    all_data = {}
    
    for instrument in config.INSTRUMENTS:
        logger.info(f"=== Downloading data for {instrument} ===")
        df = download_instrument_data(instrument)
        
        if df.empty:
            logger.warning(f"Failed to download data for {instrument}, generating synthetic data")
            symbol = INSTRUMENT_MAP[instrument]
            df = generate_synthetic_data(symbol)
        
        # Save individual CSV
        csv_filename = DATA_DIR / f"{instrument.replace('-', '_')}_2y.csv"
        df.to_csv(csv_filename, index=False)
        logger.info(f"Saved data for {instrument} to {csv_filename}")
        
        all_data[instrument] = df
    
    # Save combined pickle
    with open(COMBINED_FILE, 'wb') as f:
        import pickle
        pickle.dump(all_data, f)
    logger.info(f"Saved combined data to {COMBINED_FILE}")
    
    # Print summary
    logger.info("\n=== DATA DOWNLOAD SUMMARY ===")
    for instrument, df in all_data.items():
        if df.empty:
            logger.info(f"{instrument}: No data")
            continue
        date_range = f"{df['timestamp'].min()} to {df['timestamp'].max()}"
        null_counts = df.isnull().sum().sum()
        logger.info(f"{instrument}: {len(df)} rows, {date_range}, nulls: {null_counts}")
    
    return all_data

def load_existing_data() -> dict:
    """
    Load existing data from pickle if available and fresh.
    """
    if COMBINED_FILE.exists():
        # Check if file is less than 1 day old
        file_age = datetime.now() - datetime.fromtimestamp(COMBINED_FILE.stat().st_mtime)
        if file_age.days < 1:
            logger.info(f"Loading existing data from {COMBINED_FILE}")
            with open(COMBINED_FILE, 'rb') as f:
                import pickle
                data = pickle.load(f)
            logger.info("Successfully loaded existing data")
            return data
        else:
            logger.info(f"Existing data is {file_age.days} days old, will re-download")
    return {}

def main():
    """
    Main function to run data download.
    """
    # Ensure data directory exists
    DATA_DIR.mkdir(exist_ok=True)
    
    # Try to load existing data
    all_data = load_existing_data()
    
    # If no existing data or outdated, download fresh data
    if not all_data:
        logger.info("No existing data found, downloading fresh data...")
        all_data = download_all_data()
    else:
        logger.info("Using existing data")
    
    logger.info("Data download process completed.")
    return all_data

if __name__ == "__main__":
    main()