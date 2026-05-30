#!/usr/bin/env python3
"""
EWT Entry Monitor
Watches scanner candidates for Fib-based entry signals on 4H/1D/1W.
Sends alerts to Telegram.

Usage:
  python ew_monitor.py --daemon     # run 24/7 (30 min market hours, 2 hr after)
  python ew_monitor.py              # run a single check cycle
  python ew_monitor.py --force-scan # single cycle + refresh watchlist
  python ew_monitor.py --scan       # refresh watchlist only
  python ew_monitor.py --status     # show watchlist and open trades
  python ew_monitor.py --add TICKER # add ticker to watchlist
  python ew_monitor.py --enter TICKER # record a trade entry
"""

import json
import os
import sys
import time
import warnings
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import yfinance as yf
from scipy.signal import argrelextrema

warnings.filterwarnings('ignore')

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / 'monitor_config.json'
STATE_PATH = BASE_DIR / 'monitor_state.json'
SCANNER_RESULTS = BASE_DIR / 'ew_scanner_v2_results.json'

# ═══════════════════════════════════════════════════════════════════════
# CONFIG & STATE
# ═══════════════════════════════════════════════════════════════════════

# Aligned with the Cloud Run deployment via env vars (defaults match live config).
MIN_SCORE = int(os.environ.get('MIN_SCORE', '95'))
SETUP_FILTERS = os.environ.get('SETUP_FILTERS', 'WAVE_3').split(',')
REGIME_FILTER_ENABLED = os.environ.get('REGIME_FILTER', 'true').lower() == 'true'

DEFAULT_CONFIG = {
    'telegram_bot_token': '',
    'telegram_chat_id': '',
    'entry_zone_pct': 0.03,
    'approach_pct': 0.05,
    'alert_cooldown_hours': 4,
    'max_watchlist': 30,
}

def load_config():
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return {**DEFAULT_CONFIG, **json.load(f)}
    with open(CONFIG_PATH, 'w') as f:
        json.dump(DEFAULT_CONFIG, f, indent=2)
    return DEFAULT_CONFIG

def load_state():
    if STATE_PATH.exists():
        with open(STATE_PATH) as f:
            return json.load(f)
    return {'watchlist': [], 'open_trades': [], 'alert_history': [], 'last_scan': None}

def save_state(state):
    with open(STATE_PATH, 'w') as f:
        json.dump(state, f, indent=2, default=str)

# ═══════════════════════════════════════════════════════════════════════
# TELEGRAM
# ═══════════════════════════════════════════════════════════════════════

def send_telegram(message, config):
    token = config.get('telegram_bot_token', '')
    chat_id = config.get('telegram_chat_id', '')
    if not token or not chat_id:
        print(f"  [NO TG] {message[:80]}...")
        return False
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={'chat_id': chat_id, 'text': message,
                  'disable_web_page_preview': True},
            timeout=10)
        return resp.status_code == 200
    except Exception as e:
        print(f"  [TG ERR] {e}")
        return False

def should_alert(ticker, alert_type, state, config):
    cooldown = config.get('alert_cooldown_hours', 4)
    cutoff = datetime.now() - timedelta(hours=cooldown)
    for h in state.get('alert_history', []):
        if (h['ticker'] == ticker and h['type'] == alert_type and
            datetime.fromisoformat(h['timestamp']) > cutoff):
            return False
    return True

def record_alert(ticker, alert_type, state):
    state.setdefault('alert_history', []).append({
        'ticker': ticker, 'type': alert_type,
        'timestamp': datetime.now().isoformat(),
    })
    cutoff = datetime.now() - timedelta(hours=48)
    state['alert_history'] = [
        h for h in state['alert_history']
        if datetime.fromisoformat(h['timestamp']) > cutoff
    ]

# ═══════════════════════════════════════════════════════════════════════
# REGIME FILTER — SPY SMA(20) > SMA(50)
# ═══════════════════════════════════════════════════════════════════════

def check_regime():
    if not REGIME_FILTER_ENABLED:
        return True, "disabled"
    try:
        spy = yf.download('SPY', period='6mo', interval='1d', progress=False)
        if spy.empty:
            return True, "no SPY data"
        if isinstance(spy.columns, pd.MultiIndex):
            spy.columns = spy.columns.droplevel(1)
        close = spy['Close']
        sma20 = float(close.rolling(20).mean().iloc[-1])
        sma50 = float(close.rolling(50).mean().iloc[-1])
        bullish = sma20 > sma50
        status = f"SMA20={sma20:.2f} {'>' if bullish else '<'} SMA50={sma50:.2f}"
        return bullish, status
    except Exception as e:
        return True, f"error: {e}"

# ═══════════════════════════════════════════════════════════════════════
# DATA
# ═══════════════════════════════════════════════════════════════════════

def download_ticker(ticker):
    data = {}
    try:
        df = yf.download(ticker, period='2y', interval='1d', progress=False)
        if not df.empty:
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.droplevel(1)
            data['daily'] = df
    except Exception:
        pass
    try:
        df = yf.download(ticker, period='5y', interval='1wk', progress=False)
        if not df.empty:
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.droplevel(1)
            data['weekly'] = df
    except Exception:
        pass
    return data

# ═══════════════════════════════════════════════════════════════════════
# INDICATORS & SWINGS
# ═══════════════════════════════════════════════════════════════════════

def calculate_atr(df, period=14):
    high_low = df['High'] - df['Low']
    high_close = abs(df['High'] - df['Close'].shift(1))
    low_close = abs(df['Low'] - df['Close'].shift(1))
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, min_periods=period).mean()

def find_swings(df, order=5):
    highs = df['High'].values
    lows = df['Low'].values
    hi_idx = argrelextrema(highs, np.greater_equal, order=order)[0]
    lo_idx = argrelextrema(lows, np.less_equal, order=order)[0]
    swings = []
    for i in hi_idx:
        swings.append({'idx': i, 'date': str(df.index[i])[:16], 'price': float(highs[i]), 'type': 'high'})
    for i in lo_idx:
        swings.append({'idx': i, 'date': str(df.index[i])[:16], 'price': float(lows[i]), 'type': 'low'})
    swings.sort(key=lambda x: x['idx'])
    filt = []
    for s in swings:
        if not filt or filt[-1]['type'] != s['type']:
            filt.append(s)
        else:
            if s['type'] == 'high' and s['price'] > filt[-1]['price']:
                filt[-1] = s
            elif s['type'] == 'low' and s['price'] < filt[-1]['price']:
                filt[-1] = s
    return filt

FIB_LEVELS = [0.236, 0.382, 0.500, 0.618, 0.786, 0.887]

# ═══════════════════════════════════════════════════════════════════════
# FIB ENTRY ANALYSIS (all timeframes)
# ═══════════════════════════════════════════════════════════════════════

# Swing detection order and proximity thresholds per timeframe
TF_PARAMS = {
    'DAILY':  {'swing_order': 5, 'fib_dist': 0.02,  'low_dist': 0.03, 'lookback': 5, 'min_bars': 30},
    'WEEKLY': {'swing_order': 4, 'fib_dist': 0.03,  'low_dist': 0.04, 'lookback': 3, 'min_bars': 20},
}

def _is_reversal_candle(candle, prev_candle):
    """Detect hammer, bullish engulfing, or strong rejection candle."""
    o, h, l, c = float(candle['Open']), float(candle['High']), float(candle['Low']), float(candle['Close'])
    body = abs(c - o)
    full_range = h - l
    if full_range <= 0:
        return False, ''
    lower_wick = min(o, c) - l
    upper_wick = h - max(o, c)
    bullish = c > o

    if bullish and lower_wick >= 2 * body and upper_wick < body * 0.5:
        return True, 'HAMMER'

    if prev_candle is not None and bullish:
        po, pc = float(prev_candle['Open']), float(prev_candle['Close'])
        if pc < po and c > po and o <= pc:
            return True, 'ENGULFING'

    if bullish and body / full_range > 0.6 and (c - l) / full_range > 0.7:
        return True, 'STRONG_BULL'

    return False, ''


def _fib_zone_tested(df, fib_price, lookback=5):
    """Check if price touched or wicked through a Fib zone in recent candles."""
    tolerance = fib_price * 0.01
    recent = df.iloc[-lookback:]
    for _, bar in recent.iterrows():
        if float(bar['Low']) <= fib_price + tolerance:
            return True
    return False


def analyze_fib_entry(df, timeframe, candidate):
    """Check any timeframe for Fib-based entry signals.
    Requires: reversal candle pattern + Fib zone tested in recent bars."""
    params = TF_PARAMS.get(timeframe, TF_PARAMS['DAILY'])
    if df is None or len(df) < params['min_bars']:
        return None

    current = float(df['Close'].iloc[-1])
    swings = find_swings(df, order=params['swing_order'])
    if len(swings) < 3:
        return None

    highs = [s for s in swings if s['type'] == 'high']
    lows = [s for s in swings if s['type'] == 'low']
    if not highs or not lows:
        return None

    result = {'current': current, 'fib_zones': [], 'entry_signal': None, 'timeframe': timeframe}

    last_candle = df.iloc[-1]
    prev_candle = df.iloc[-2] if len(df) >= 2 else None
    is_reversal, candle_type = _is_reversal_candle(last_candle, prev_candle)

    last_high = highs[-1]
    last_low = lows[-1]
    fib_dist = params['fib_dist']
    lookback = params['lookback']

    if last_high['idx'] > last_low['idx']:
        impulse = last_high['price'] - last_low['price']
        if impulse <= 0:
            return result
        best_signal = None
        for fib in FIB_LEVELS:
            fib_price = last_high['price'] - fib * impulse
            dist = abs(current - fib_price) / fib_price
            result['fib_zones'].append({'ratio': fib, 'price': round(fib_price, 2), 'dist_pct': round(dist * 100, 2)})

            if dist < fib_dist and is_reversal and _fib_zone_tested(df, fib_price, lookback):
                quality = 3 if fib in (0.382, 0.500, 0.618) else 2 if fib == 0.786 else 1
                if best_signal is None or quality > best_signal['_q']:
                    best_signal = {
                        'type': 'FIB_PULLBACK',
                        'fib': fib, 'price': round(fib_price, 2),
                        'entry': round(current, 2),
                        'candle': candle_type, '_q': quality,
                    }
        if best_signal and best_signal['_q'] >= 2:
            best_signal.pop('_q')
            result['entry_signal'] = best_signal
    else:
        decline = last_high['price'] - last_low['price']
        if decline <= 0:
            return result
        for fib in FIB_LEVELS:
            fib_price = last_low['price'] + fib * decline
            dist = abs(current - fib_price) / fib_price
            result['fib_zones'].append({'ratio': fib, 'price': round(fib_price, 2), 'dist_pct': round(dist * 100, 2)})

        dist_to_low = abs(current - last_low['price']) / last_low['price']
        if dist_to_low < params['low_dist'] and is_reversal:
            nearest = min(result['fib_zones'], key=lambda z: z['dist_pct'])
            result['entry_signal'] = {
                'type': 'REVERSAL_AT_LOW',
                'fib': nearest['ratio'],
                'price': round(last_low['price'], 2),
                'entry': round(current, 2),
                'candle': candle_type,
            }

    return result

# ═══════════════════════════════════════════════════════════════════════
# DAILY STATUS CHECK
# ═══════════════════════════════════════════════════════════════════════

def check_daily(candidate, daily_df, config):
    """Check where price is relative to the candidate's setup."""
    if daily_df is None or len(daily_df) < 10:
        return None

    current = float(daily_df['Close'].iloc[-1])
    setup = candidate.get('setup_type', '')
    entry = candidate.get('entry', current)

    stop = candidate.get('stop', 0)
    t1 = candidate.get('t1', 0)
    t2 = candidate.get('t2', 0)

    if stop <= 0:
        return None

    risk = current - stop
    risk_pct = risk / current * 100 if current > 0 else 0
    rr = (t1 - current) / risk if risk > 0 and t1 > current else 0

    approach_pct = config.get('approach_pct', 0.05)
    dist_to_entry = (current - entry) / entry if entry > 0 else 999
    approaching = 0 < dist_to_entry < approach_pct

    status = 'WATCHING'
    if current <= stop:
        status = 'INVALIDATED'
    elif current >= t1:
        status = 'PAST_T1'
    elif approaching:
        status = 'APPROACHING'

    return {
        'status': status, 'current': current, 'entry': entry,
        'stop': stop, 't1': t1, 't2': t2,
        'risk_pct': round(risk_pct, 1), 'rr': round(rr, 1),
        'dist_to_entry_pct': round(dist_to_entry * 100, 1),
    }

# ═══════════════════════════════════════════════════════════════════════
# ALERT FORMATTING
# ═══════════════════════════════════════════════════════════════════════

def fmt_approaching(ticker, c, daily, dist_pct):
    score = c.get('score', 0)
    msg = f"Approaching Entry • {ticker} • Score: {score:.0f}\n"
    msg += f"Price: ${daily['current']:.2f} ({dist_pct:.1f}% from zone)\n"
    msg += f"Entry: ${daily['entry']:.2f}\n"
    msg += f"Stop: ${daily['stop']:.2f}\n"
    targets = f"${daily['t1']:.2f}"
    if daily['t2']:
        targets += f", ${daily['t2']:.2f}"
    msg += f"Target(s): {targets}"
    return msg

def fmt_entry(ticker, c, analysis, daily):
    sig = analysis['entry_signal']
    tf = analysis['timeframe']
    score = c.get('score', 0)
    setup = c.get('setup_type', '')
    wave_labels = {'WAVE_3': 'Wave 3', 'WAVE_5': 'Wave 5', 'CORRECTION': 'Wave 1'}
    wave = wave_labels.get(setup, setup)
    msg = f"Trade Alert • {ticker} • Score: {score:.0f}\n"
    msg += f"LONG (BUY) — {tf} — {wave} Entry\n"
    msg += f"Regime: BULLISH (SPY SMA20>SMA50)\n"
    msg += f"Entry: ${sig['entry']:.2f}\n"
    if daily:
        msg += f"Stop: ${daily['stop']:.2f}\n"
        targets = f"${daily['t1']:.2f}"
        if daily['t2']:
            targets += f", ${daily['t2']:.2f}"
        msg += f"Target(s): {targets}"
    return msg

def fmt_stop_update(ticker, old, new, stage, price):
    stages = {1: 'Initial', 2: 'Risk Reduced', 3: 'Breakeven',
              4: 'Trailing', 5: 'Post-T1 (75% booked)', 6: 'Runner Trail'}
    msg = f"Stop Update • {ticker}\n"
    msg += f"Stop: ${old:.2f} → ${new:.2f}\n"
    msg += f"Price: ${price:.2f}\n"
    msg += f"Stage: {stages.get(stage, stage)}"
    return msg

def fmt_exit(ticker, action, price, pnl):
    msg = f"Trade Exit • {ticker}\n"
    msg += f"{action} at ${price:.2f}\n"
    msg += f"P&L: {pnl:+.1f}%"
    return msg

def fmt_t1_hit(ticker, t1, entry, new_stop):
    pnl = (t1 - entry) / entry * 100
    msg = f"Target 1 Hit • {ticker}\n"
    msg += f"T1: ${t1:.2f} reached (+{pnl:.1f}%)\n"
    msg += f"Sell 75%, ride 25% to T2 — stop raised to ${new_stop:.2f}"
    return msg

# ═══════════════════════════════════════════════════════════════════════
# WATCHLIST
# ═══════════════════════════════════════════════════════════════════════

def refresh_watchlist(state, config):
    if not SCANNER_RESULTS.exists():
        print("  No scanner results. Run ew_scanner_v2.py first.")
        return
    with open(SCANNER_RESULTS) as f:
        candidates = json.load(f)
    candidates = [c for c in candidates
                  if c.get('score', 0) >= MIN_SCORE and c.get('setup_type') in SETUP_FILTERS]
    candidates.sort(key=lambda x: x.get('score', 0), reverse=True)
    max_w = config.get('max_watchlist', 30)
    existing = {w['ticker'] for w in state.get('watchlist', [])}
    new_tickers = []
    for c in candidates[:max_w]:
        if c['ticker'] not in existing:
            new_tickers.append(c['ticker'])
    state['watchlist'] = candidates[:max_w]
    state['last_scan'] = datetime.now().isoformat()
    print(f"  Watchlist: {len(state['watchlist'])} tickers ({len(new_tickers)} new) "
          f"[{','.join(SETUP_FILTERS)}, score >= {MIN_SCORE}]")
    return new_tickers

# ═══════════════════════════════════════════════════════════════════════
# TRADE MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════

def update_trade(trade, bar_high, bar_low, bar_close, atr_val):
    """Update an open trade. Returns alert message or None."""
    old_stop = trade['current_stop']
    old_stage = trade.get('stage', 1)
    entry = trade['entry']
    initial_risk = entry - trade['initial_stop']
    if initial_risk <= 0:
        return None

    trade['bars_since_entry'] = trade.get('bars_since_entry', 0) + 1

    # Stop hit — full exit
    if bar_low <= trade['current_stop']:
        pnl = (trade['current_stop'] - entry) / entry * 100
        trade['status'] = 'CLOSED'
        trade['exit_price'] = trade['current_stop']
        return fmt_exit(trade['ticker'], 'STOP HIT', trade['current_stop'], pnl)

    trade['max_price'] = max(trade.get('max_price', entry), bar_high)
    fav = trade['max_price'] - entry

    if fav >= initial_risk and trade.get('stage', 1) < 2:
        trade['current_stop'] = max(trade['current_stop'], entry - initial_risk * 0.5)
        trade['stage'] = 2
    if fav >= 2 * initial_risk and trade.get('stage', 1) < 3:
        trade['current_stop'] = max(trade['current_stop'], entry)
        trade['stage'] = 3
    if fav >= 3 * initial_risk and trade.get('stage', 1) < 4:
        trade['current_stop'] = max(trade['current_stop'], trade['max_price'] - 2.5 * atr_val)
        trade['stage'] = 4

    # T1 — book 75%, ride the remaining 25% to T2 (Aleks's two-stage exit)
    if trade['t1'] > 0 and bar_high >= trade['t1'] and not trade.get('t1_reached'):
        trade['t1_reached'] = True
        trade['position_pct'] = 0.25
        trade['current_stop'] = max(trade['current_stop'], trade['t1'] - initial_risk)
        trade['stage'] = max(trade.get('stage', 1), 5)
        trade['partial_event'] = True   # signals the caller to log a 75% partial fill
        return fmt_t1_hit(trade['ticker'], trade['t1'], entry, trade['current_stop'])

    # Past T1: tighter trail on the 25% runner
    if trade.get('t1_reached'):
        trade['current_stop'] = max(trade['current_stop'], trade['max_price'] - 2.0 * atr_val)
        trade['stage'] = max(trade.get('stage', 1), 6)

    # T2 — exit the remaining 25%
    if trade['t2'] > 0 and bar_high >= trade['t2'] and trade.get('t1_reached'):
        pnl = (trade['t2'] - entry) / entry * 100
        trade['status'] = 'CLOSED'
        trade['exit_price'] = trade['t2']
        return fmt_exit(trade['ticker'], 'T2 HIT', trade['t2'], pnl)

    if trade['current_stop'] != old_stop:
        return fmt_stop_update(trade['ticker'], old_stop, trade['current_stop'],
                               trade.get('stage', 1), bar_close)
    return None

# ═══════════════════════════════════════════════════════════════════════
# MAIN MONITOR CYCLE
# ═══════════════════════════════════════════════════════════════════════

def run_monitor(state, config, force_scan=False):
    now = datetime.now()
    print(f"\n{'='*60}")
    print(f"  EWT MONITOR — {now.strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}")

    regime_bullish, regime_status = check_regime()
    print(f"\n  Regime: {'BULLISH' if regime_bullish else 'BEARISH'} ({regime_status})")
    if not regime_bullish:
        print("  Skipping new entries — SPY SMA(20) < SMA(50)")

    last_scan = state.get('last_scan')
    new_tickers = []
    if force_scan or not last_scan or (now - datetime.fromisoformat(last_scan)).days >= 1:
        print("\n  Refreshing watchlist...")
        new_tickers = refresh_watchlist(state, config) or []

    watchlist = state.get('watchlist', [])
    if not watchlist:
        print("  Empty watchlist.")
        return

    alerts = []
    print(f"\n  Checking {len(watchlist)} tickers...")

    for c in watchlist:
        ticker = c['ticker']
        try:
            data = download_ticker(ticker)
            daily_df = data.get('daily')
            weekly_df = data.get('weekly')
            if daily_df is None:
                continue

            daily = check_daily(c, daily_df, config)
            if daily is None:
                continue

            cur = daily['current']
            print(f"  {ticker:<6} ${cur:>8.2f}", end='')

            # Invalidation
            if daily['status'] == 'INVALIDATED':
                if should_alert(ticker, 'INVALIDATED', state, config):
                    msg = f"Setup Invalidated • {ticker}\nPrice ${cur:.2f} broke below stop ${daily['stop']:.2f}"
                    alerts.append((ticker, 'INVALIDATED', msg))
                print(f"  [INVALID]", end='')
                print()
                continue

            # Skip new entries if regime is bearish
            if not regime_bullish:
                print(f"  [REGIME OFF]")
                continue

            # Check daily and weekly for Fib entry signals
            entry_found = False
            for tf, tf_df in [('DAILY', daily_df), ('WEEKLY', weekly_df)]:
                analysis = analyze_fib_entry(tf_df, tf, c)
                alert_key = f'{tf}_ENTRY'
                if analysis and analysis.get('entry_signal') and should_alert(ticker, alert_key, state, config):
                    msg = fmt_entry(ticker, c, analysis, daily)
                    alerts.append((ticker, alert_key, msg))
                    print(f"  [{tf} ENTER]", end='')
                    entry_found = True

            # Approaching entry zone (only if no entry signal fired)
            if not entry_found and daily['status'] == 'APPROACHING' and should_alert(ticker, 'APPROACHING', state, config):
                msg = fmt_approaching(ticker, c, daily, daily['dist_to_entry_pct'])
                alerts.append((ticker, 'APPROACHING', msg))
                print(f"  [APPROACHING]", end='')

            print()

        except Exception as e:
            print(f"  {ticker:<6} error: {e}")
            time.sleep(0.5)

    # Open trades
    for trade in state.get('open_trades', []):
        if trade.get('status') != 'OPEN':
            continue
        ticker = trade['ticker']
        try:
            df = yf.download(ticker, period='5d', interval='1d', progress=False)
            if df.empty:
                continue
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.droplevel(1)
            bar = df.iloc[-1]
            atr = calculate_atr(df)
            atr_val = float(atr.iloc[-1]) if len(atr.dropna()) > 0 else float(bar['High'] - bar['Low'])
            msg = update_trade(trade, float(bar['High']), float(bar['Low']),
                               float(bar['Close']), atr_val)
            if msg:
                alerts.append((ticker, 'TRADE_UPDATE', msg))
        except Exception:
            pass

    state['open_trades'] = [t for t in state.get('open_trades', []) if t.get('status') == 'OPEN']

    # Send alerts
    if alerts:
        print(f"\n  Sending {len(alerts)} alerts...")
        for ticker, atype, msg in alerts:
            send_telegram(msg, config)
            record_alert(ticker, atype, state)
            time.sleep(0.3)
    else:
        print(f"\n  No alerts.")

    save_state(state)
    print(f"  Done. {datetime.now().strftime('%H:%M:%S')}")

def show_status(state):
    print(f"\n{'='*60}")
    print(f"  EWT MONITOR STATUS")
    print(f"{'='*60}")
    wl = state.get('watchlist', [])
    print(f"\n  Watchlist: {len(wl)} tickers")
    if wl:
        print(f"  {'Ticker':<8} {'Setup':<12} {'Score':>5} {'Entry':>8} {'Stop':>8} {'T1':>8}")
        print(f"  {'─'*54}")
        for w in wl[:20]:
            print(f"  {w.get('ticker','?'):<8} {w.get('setup_type','?'):<12} "
                  f"{w.get('score',0):>5.0f} ${w.get('entry',0):>7.2f} "
                  f"${w.get('stop',0):>7.2f} ${w.get('t1',0):>7.2f}")
    trades = [t for t in state.get('open_trades', []) if t.get('status') == 'OPEN']
    print(f"\n  Open trades: {len(trades)}")
    for t in trades:
        print(f"    {t['ticker']}: entry ${t['entry']:.2f} stop ${t['current_stop']:.2f} stage {t.get('stage', 1)}")
    recent = [h for h in state.get('alert_history', [])
              if datetime.fromisoformat(h['timestamp']) > datetime.now() - timedelta(hours=24)]
    print(f"\n  Alerts (24h): {len(recent)}")
    for h in recent[-5:]:
        print(f"    {h['timestamp'][:16]} {h['ticker']} {h['type']}")

def is_market_hours():
    """Check if US market is open (9:30 AM - 4:00 PM ET, Mon-Fri)."""
    try:
        from zoneinfo import ZoneInfo
        et = datetime.now(ZoneInfo('America/New_York'))
    except ImportError:
        import pytz
        et = datetime.now(pytz.timezone('US/Eastern'))
    if et.weekday() >= 5:
        return False
    market_open = et.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = et.replace(hour=16, minute=0, second=0, microsecond=0)
    return market_open <= et <= market_close


def run_daemon(config):
    """Run continuously. Checks every 30 min during market hours, every 2 hours after."""
    print(f"\n  EWT Monitor daemon started.")
    print(f"  Market hours: every 30 min | After hours: every 2 hours")
    print(f"  Press Ctrl+C to stop.\n")
    send_telegram("Monitor started — running 24/7", config)

    cycle = 0
    while True:
        try:
            state = load_state()
            force = (cycle == 0) or (cycle % 48 == 0)
            run_monitor(state, config, force_scan=force)
            cycle += 1

            if is_market_hours():
                sleep_min = 30
            else:
                sleep_min = 120

            print(f"\n  Sleeping {sleep_min} min (next check ~{(datetime.now() + timedelta(minutes=sleep_min)).strftime('%H:%M')})")
            time.sleep(sleep_min * 60)

        except KeyboardInterrupt:
            print("\n  Daemon stopped.")
            send_telegram("Monitor stopped", config)
            break
        except Exception as e:
            print(f"\n  Error in cycle: {e}")
            time.sleep(300)


def main():
    config = load_config()
    state = load_state()
    args = sys.argv[1:]

    if '--status' in args:
        show_status(state)
    elif '--scan' in args:
        refresh_watchlist(state, config)
        save_state(state)
    elif '--daemon' in args:
        run_daemon(config)
    elif '--add' in args:
        idx = args.index('--add')
        if idx + 1 < len(args):
            ticker = args[idx + 1].upper()
            if not any(w['ticker'] == ticker for w in state.get('watchlist', [])):
                state.setdefault('watchlist', []).append({
                    'ticker': ticker, 'setup_type': 'MANUAL', 'entry': 0,
                    'stop': 0, 't1': 0, 't2': 0, 'score': 0,
                })
                save_state(state)
                print(f"  Added {ticker}")
            else:
                print(f"  {ticker} already on watchlist")
    elif '--enter' in args:
        idx = args.index('--enter')
        if idx + 1 < len(args):
            ticker = args[idx + 1].upper()
            c = next((w for w in state.get('watchlist', []) if w['ticker'] == ticker), None)
            if c:
                trade = {
                    'ticker': ticker, 'setup_type': c.get('setup_type', 'MANUAL'),
                    'entry': c.get('entry', 0), 'initial_stop': c.get('stop', 0),
                    'current_stop': c.get('stop', 0), 't1': c.get('t1', 0),
                    't2': c.get('t2', 0), 'max_price': c.get('entry', 0),
                    't1_reached': False, 'stage': 1, 'status': 'OPEN',
                    'entry_date': datetime.now().strftime('%Y-%m-%d'),
                    'bars_since_entry': 0,
                }
                state.setdefault('open_trades', []).append(trade)
                save_state(state)
                targets = f"${trade['t1']:.2f}"
                if trade['t2']:
                    targets += f", ${trade['t2']:.2f}"
                msg = f"Trade Entered • {ticker}\n"
                msg += f"LONG (BUY)\n"
                msg += f"Entry: ${trade['entry']:.2f}\n"
                msg += f"Stop: ${trade['current_stop']:.2f}\n"
                msg += f"Target(s): {targets}"
                send_telegram(msg, config)
                print(f"  Entered {ticker} at ${trade['entry']:.2f}")
            else:
                print(f"  {ticker} not on watchlist")
    else:
        run_monitor(state, config, force_scan=('--force-scan' in args))

if __name__ == '__main__':
    main()
