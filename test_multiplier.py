import sys
sys.path.insert(0, r'C:\Users\Avinash\crypto_backtest')
from backtest_engine import BacktestEngine
from config import config
import pandas as pd

# Monkey patch _process_entries to use a variable multiplier
original_process_entries = BacktestEngine._process_entries

def patched_process_entries(self, instrument, bar, current_time):
    # Check if we can trade based on risk limits and daily loss limit
    if self.daily_loss_limit_breached:
        return

    # Check current drawdown halt
    current_drawdown = (self.peak_equity - self.equity) / self.peak_equity if self.peak_equity > 0 else 0
    if current_drawdown >= self.config.MAX_DRAWDOWN_HALT:
        return

    # Check if we have an existing position in this instrument (should not, but double-check)
    if any(pos['instrument'] == instrument for pos in self.open_positions):
        return

    # Check time since last trade on this instrument
    last_trade = self.last_trade_time.get(instrument)
    if last_trade is not None:
        hours_since_last_trade = (current_time - last_trade).total_seconds() / 3600
        if hours_since_last_trade < self.config.MIN_BARS_BETWEEN_TRADES:
            return

    # Check regime: no new positions in HIGH_VOL
    df = self.data[instrument]
    if bar.get('is_high_vol', False):
        return

    # Volume filter: only enter if 24h volume > 30-day average volume
    vol_24h = bar['volume']
    # Calculate 30-day average volume (720 hours for hourly data), shifted to avoid lookahead
    vol_30d_avg = df['volume'].rolling(window=720, min_periods=1).mean().shift(1).loc[current_time]
    # If not enough data for average, allow the trade
    if pd.isna(vol_30d_avg):
        pass
    elif vol_24h <= vol_30d_avg:
        return

    # Check signals: we need at least one entry signal
    entry_long = bar.get('entry_long', False)
    entry_short = bar.get('entry_short', False)
    if not entry_long and not entry_short:
        return

    # Check concurrent position limit
    if len(self.open_positions) >= self.config.MAX_CONCURRENT:
        return

    # Determine direction based on signal (if both long and short, we need a rule)
    if entry_long and entry_short:
        score_long = bar.get('score_long', 0)
        score_short = bar.get('score_short', 0)
        if score_long >= score_short:
            direction = 'LONG'
        else:
            direction = 'SHORT'
    elif entry_long:
        direction = 'LONG'
    elif entry_short:
        direction = 'SHORT'
    else:
        return  # Should not happen due to earlier check, but safe

    # Get stop loss and take profit percentages based on regime
    regime = bar['regime']
    if regime == 'BULL':
        sl_pct = self.config.BULL_SL_PCT
        tp_pct = sl_pct * 2.0  # multiplier = 2.0
        time_exit_bars = self.config.BULL_TIME_EXIT_BARS
    elif regime == 'BEAR':
        sl_pct = self.config.BEAR_SL_PCT
        tp_pct = sl_pct * 2.0  # multiplier = 2.0
        time_exit_bars = self.config.BEAR_TIME_EXIT_BARS
    elif regime == 'SIDEWAYS':
        sl_pct = self.config.SIDEWAYS_SL_PCT
        tp_pct = sl_pct * 2.0  # multiplier = 2.0
        time_exit_bars = self.config.SIDEWAYS_TIME_EXIT_BARS
    else:  # HIGH_VOL should have been filtered out, but just in case
        sl_pct = self.config.BULL_SL_PCT * 0.5  # Tighten SL
        tp_pct = sl_pct * 2.0  # multiplier = 2.0
        time_exit_bars = self.config.BULL_TIME_EXIT_BARS

    # Calculate position size
    # We need the current equity and drawdown for the position sizer
    current_dd = (self.peak_equity - self.equity) / self.peak_equity if self.peak_equity > 0 else 0
    # We also need to pass open positions (for correlation cap) and the instrument
    size_usd, leverage, margin_required = self.position_sizer.calculate_size(
        equity=self.equity,
        regime=regime,
        current_dd=current_dd,
        open_positions=self.open_positions,
        sl_pct=sl_pct,
        instrument=instrument
    )

    # Check if we can trade (position sizer also checks risk limits)
    can_trade, reason = self.position_sizer.check_risk_limits(
        equity=self.equity,
        open_positions=self.open_positions
    )
    if not can_trade:
        logger.debug(f"Cannot trade {instrument}: {reason}")
        return

    # If size is zero, skip
    if size_usd <= 0:
        return

    # Open the position
    position = {
        'instrument': instrument,
        'direction': direction,
        'entry_price': bar['close'],
        'entry_time': current_time,
        'size_usd': size_usd,
        'leverage': leverage,
        'margin_required': margin_required,
        'regime_at_entry': regime,
        'sl_pct': sl_pct,
        'tp_pct': tp_pct,
        'time_exit_bar': time_exit_bars,
        'original_sl_pct': sl_pct,  # Store original for HIGH_VOL adjustment
        'confluence_score': bar.get('score_long' if direction == 'LONG' else 'score_short', 0),
        'oi_at_entry': bar.get('openInterest', 0),
        'funding_at_entry': bar.get('fundingRate', 0)
    }

    # Add to open positions
    self.open_positions.append(position)

# Apply monkey patch
BacktestEngine._process_entries = patched_process_entries

# Import logger
import logging
logger = logging.getLogger(__name__)

# Run backtest
engine = BacktestEngine()
trade_log, equity_curve = engine.run_backtest()

if len(trade_log) == 0:
    print("No trades")
else:
    df = pd.DataFrame(trade_log)
    df['net_pnl_pct'] = df['net_pnl'] / df['size_usd'] * 100
    winners = df[df['net_pnl'] > 0]
    losers = df[df['net_pnl'] <= 0]
    avg_win = winners['net_pnl_pct'].mean() if len(winners) > 0 else 0
    avg_loss = losers['net_pnl_pct'].mean() if len(losers) > 0 else 0
    rr = avg_win / abs(avg_loss) if avg_loss != 0 else 0
    months = 24
    tpm = len(df) / months
    wr = len(winners) / len(df) * 100
    roll_max = df['running_equity_after'].cummax()
    max_dd = ((roll_max - df['running_equity_after']) / roll_max).max() * 100
    net_pct = (df['running_equity_after'].iloc[-1] - 100000) / 100000 * 100
    print(f"Multiplier 2.0:")
    print(f"  Trades/month: {tpm:.1f}")
    print(f"  Win rate: {wr:.1f}%")
    print(f"  R:R: {rr:.2f}")
    print(f"  Net PnL: {net_pct:.1f}%")
    print(f"  Max DD: {max_dd:.1f}%")