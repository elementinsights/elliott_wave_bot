#!/usr/bin/env python3
"""
Aleks Elliott Wave Scanner v2
Systematic long-only EWT strategy for S&P 500 + Russell 2000.
Based on Aleks's framework: 5 setup types, 120-point scoring, multi-TF analysis.
"""

import json
import time
import warnings
from datetime import datetime, timedelta
from io import StringIO

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
import yfinance as yf
from scipy.signal import argrelextrema

warnings.filterwarnings('ignore')

# ═══════════════════════════════════════════════════════════════════════
# CONSTANTS — Fibonacci ratios from Aleks's presentation
# ═══════════════════════════════════════════════════════════════════════

# Per the EWT Notes, Wave 2 retraces 50/61.8/78.6/88.7% of Wave 1. Aleks enters deep
# retracements, so 38.2% (too shallow / off-style) is excluded.
FIB_W2_IMPULSE = [0.500, 0.618, 0.786, 0.887]
FIB_W3_TARGETS = [0.382, 0.618, 0.786, 1.000, 1.618, 1.750, 2.272, 3.618]
FIB_W4_IMPULSE = [0.236, 0.382, 0.500, 0.618]
FIB_W5_TARGETS_W1 = [1.000]  # W5 = W1
FIB_CORRECTION_RETRACE = [0.236, 0.382, 0.500, 0.618, 0.786]
FIB_TOLERANCE = 0.08

# Scoring weights
WEIGHT_STRUCTURE = 30
WEIGHT_RULES = 20
WEIGHT_WEEKLY = 20
WEIGHT_MOMENTUM = 15
WEIGHT_RR = 15
WEIGHT_ALTERNATION = 5
WEIGHT_VOLUME = 5
WEIGHT_FRESHNESS = 10

# Filters
MIN_PRICE = 2.0
MAX_PRICE = 2000.0
MIN_AVG_VOLUME = 500_000
MIN_RR_T1 = 2.0
MIN_RISK_PCT = 1.5
MAX_RISK_PCT = 18.0
STOP_BUFFER = 0.03
MAX_CONCURRENT_POSITIONS = 6

# ═══════════════════════════════════════════════════════════════════════
# TICKER SOURCING
# ═══════════════════════════════════════════════════════════════════════

HEADERS = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}

MIN_MARKET_CAP = 200_000_000  # $200M — Aleks's smallest trade (MVIS) is ~$216M

def get_sp500_tickers():
    url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
    resp = requests.get(url, headers=HEADERS)
    tables = pd.read_html(StringIO(resp.text))
    tickers = tables[0]['Symbol'].tolist()
    return [t.replace('.', '-') for t in tickers]

def get_smallmid_tickers():
    tickers = []
    for url in [
        'https://en.wikipedia.org/wiki/List_of_S%26P_600_companies',
        'https://en.wikipedia.org/wiki/List_of_S%26P_400_companies',
    ]:
        try:
            resp = requests.get(url, headers=HEADERS)
            tables = pd.read_html(StringIO(resp.text))
            for t in tables[0]:
                if 'ymbol' in str(t) or 'icker' in str(t):
                    tickers.extend(tables[0][t].tolist())
                    break
        except Exception:
            pass
    return list(set(t.replace('.', '-') for t in tickers if isinstance(t, str)))

def get_all_traded_tickers():
    """Pull all NASDAQ/NYSE/AMEX traded stocks + ETFs from NASDAQ trader file."""
    import csv
    url = 'https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqtraded.txt'
    resp = requests.get(url, headers=HEADERS, timeout=15)
    lines = resp.text.strip().split('\n')
    reader = csv.reader(lines, delimiter='|')
    next(reader)  # header
    tickers = []
    for row in reader:
        if len(row) < 8:
            continue
        sym = row[1].strip()
        name = row[2] if len(row) > 2 else ''
        test = row[7] if len(row) > 7 else ''
        if test == 'Y' or not sym or 'File Creation' in sym:
            continue
        if any(c in sym for c in [' ', '^', '.', '/', '$']):
            continue
        if len(sym) > 5:
            continue
        skip = ['Warrant', 'Rights', 'Preferred', 'Depositary', 'Unit', 'Notes', 'Debenture']
        if any(w.lower() in name.lower() for w in skip):
            continue
        tickers.append(sym)
    return list(set(tickers))

CURATED_ETFS = [
    'SPY', 'QQQ', 'IWM', 'DIA', 'VTI', 'VOO',
    'XLF', 'XLE', 'XLK', 'XLV', 'XLI', 'XLC', 'XLU', 'XLP', 'XLB', 'XLY', 'XLRE',
    'GLD', 'SLV', 'GDX', 'GDXJ', 'SIL',
    'USO', 'UNG', 'XOP', 'OIH',
    'ARKK', 'ARKG', 'ARKF', 'ARKW',
    'UVXY', 'VXX', 'VIXY',
    'SMH', 'SOXX', 'XBI', 'IBB', 'REMX',
    'TLT', 'HYG', 'LQD', 'JNK',
    'EEM', 'EFA', 'FXI', 'EWJ',
    'KWEB', 'MCHI',
    'BITX', 'BITO',
]

# ═══════════════════════════════════════════════════════════════════════
# DATA DOWNLOAD
# ═══════════════════════════════════════════════════════════════════════

def download_batch(tickers, start, end, interval='1d', batch_size=50, min_bars=50):
    all_data = {}
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i+batch_size]
        try:
            raw = yf.download(batch, start=start, end=end, interval=interval,
                              group_by='ticker', threads=True, progress=False)
            if raw.empty:
                continue
            for t in batch:
                try:
                    if len(batch) == 1:
                        df = raw.copy()
                    else:
                        df = raw[t].copy()
                    if isinstance(df.columns, pd.MultiIndex):
                        # Keep the OHLC field level, drop the ticker level
                        # (single-ticker downloads put the ticker on level 0).
                        lvl1 = df.columns.get_level_values(1)
                        df.columns = lvl1 if 'Close' in lvl1 else df.columns.get_level_values(0)
                    df = df.dropna(subset=['Close'])
                    if len(df) >= min_bars:
                        all_data[t] = df
                except Exception:
                    pass
        except Exception:
            pass
        if i + batch_size < len(tickers):
            time.sleep(0.5)
        pct = min(100, (i + batch_size) / len(tickers) * 100)
        print(f"\r  Downloading ({interval}): {pct:.0f}% ({len(all_data)} tickers loaded)", end='', flush=True)
    print()
    return all_data

# ═══════════════════════════════════════════════════════════════════════
# INDICATORS — RSI, MACD, Stochastic, ATR
# ═══════════════════════════════════════════════════════════════════════

def calculate_rsi(df, period=14):
    delta = df['Close'].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1/period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def calculate_macd(df, fast=12, slow=26, signal=9):
    ema_fast = df['Close'].ewm(span=fast, adjust=False).mean()
    ema_slow = df['Close'].ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram

def calculate_stochastic(df, k_period=14, d_period=3):
    low_min = df['Low'].rolling(k_period).min()
    high_max = df['High'].rolling(k_period).max()
    stoch_k = 100 * (df['Close'] - low_min) / (high_max - low_min + 1e-10)
    stoch_d = stoch_k.rolling(d_period).mean()
    return stoch_k, stoch_d

def calculate_atr(df, period=14):
    high_low = df['High'] - df['Low']
    high_close = abs(df['High'] - df['Close'].shift(1))
    low_close = abs(df['Low'] - df['Close'].shift(1))
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, min_periods=period).mean()

def calculate_indicators(df):
    macd_line, macd_signal, macd_hist = calculate_macd(df)
    stoch_k, stoch_d = calculate_stochastic(df)
    return {
        'rsi': calculate_rsi(df),
        'macd_line': macd_line,
        'macd_signal': macd_signal,
        'macd_hist': macd_hist,
        'stoch_k': stoch_k,
        'stoch_d': stoch_d,
        'atr': calculate_atr(df),
    }

# ═══════════════════════════════════════════════════════════════════════
# SWING DETECTION — multi-order with confirmation
# ═══════════════════════════════════════════════════════════════════════

def find_swings_single(df, order=10):
    highs = df['High'].values
    lows = df['Low'].values
    hi_idx = argrelextrema(highs, np.greater_equal, order=order)[0]
    lo_idx = argrelextrema(lows, np.less_equal, order=order)[0]
    swings = []
    for i in hi_idx:
        swings.append({'idx': i, 'date': df.index[i], 'price': float(highs[i]), 'type': 'high'})
    for i in lo_idx:
        swings.append({'idx': i, 'date': df.index[i], 'price': float(lows[i]), 'type': 'low'})
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

def detect_swings(df, orders=None, min_confirmations=2, min_swing_pct=None):
    if orders is None:
        orders = [8, 10, 12, 15, 20]
    if min_swing_pct is None:
        atr = calculate_atr(df)
        if len(atr.dropna()) > 0:
            min_swing_pct = 1.5 * atr.dropna().iloc[-1] / df['Close'].iloc[-1]
        else:
            min_swing_pct = 0.03

    all_points = {}
    for order in orders:
        swings = find_swings_single(df, order)
        for s in swings:
            key = s['idx']
            if key not in all_points:
                all_points[key] = {'idx': s['idx'], 'date': s['date'],
                                   'price': s['price'], 'type': s['type'], 'count': 0}
            all_points[key]['count'] += 1
            if s['type'] == 'high' and s['price'] > all_points[key]['price']:
                all_points[key]['price'] = s['price']
            elif s['type'] == 'low' and s['price'] < all_points[key]['price']:
                all_points[key]['price'] = s['price']

    confirmed = [v for v in all_points.values() if v['count'] >= min_confirmations]
    confirmed.sort(key=lambda x: x['idx'])

    alt = []
    for s in confirmed:
        if not alt or alt[-1]['type'] != s['type']:
            alt.append(s)
        else:
            if s['type'] == 'high' and s['price'] > alt[-1]['price']:
                alt[-1] = s
            elif s['type'] == 'low' and s['price'] < alt[-1]['price']:
                alt[-1] = s

    filtered = [alt[0]] if alt else []
    for i in range(1, len(alt)):
        move = abs(alt[i]['price'] - alt[i-1]['price'])
        pct_move = move / alt[i-1]['price']
        if pct_move >= min_swing_pct:
            filtered.append(alt[i])

    return filtered

# ═══════════════════════════════════════════════════════════════════════
# WEEKLY TREND ASSESSMENT
# ═══════════════════════════════════════════════════════════════════════

def assess_weekly_trend(weekly_df):
    if weekly_df is None or len(weekly_df) < 40:
        return 'NEUTRAL'

    sma40 = weekly_df['Close'].rolling(40).mean()
    current = weekly_df['Close'].iloc[-1]
    sma_val = sma40.iloc[-1]

    if pd.isna(sma_val):
        return 'NEUTRAL'

    swings = find_swings_single(weekly_df, order=5)
    recent_highs = [s for s in swings if s['type'] == 'high'][-3:]
    recent_lows = [s for s in swings if s['type'] == 'low'][-3:]

    above_sma = current > sma_val
    higher_highs = len(recent_highs) >= 2 and recent_highs[-1]['price'] > recent_highs[-2]['price']
    higher_lows = len(recent_lows) >= 2 and recent_lows[-1]['price'] > recent_lows[-2]['price']
    lower_highs = len(recent_highs) >= 2 and recent_highs[-1]['price'] < recent_highs[-2]['price']
    lower_lows = len(recent_lows) >= 2 and recent_lows[-1]['price'] < recent_lows[-2]['price']

    if above_sma and (higher_highs or higher_lows):
        return 'BULLISH'
    elif not above_sma and (lower_highs or lower_lows):
        return 'BEARISH'
    return 'NEUTRAL'


def count_weekly_waves(weekly_df):
    """Identify macro-degree wave position on the weekly timeframe."""
    result = {
        'trend': 'NEUTRAL',
        'wave_position': None,
        'macro_phase': None,
        'wave_points': [],
    }

    if weekly_df is None or len(weekly_df) < 40:
        return result

    result['trend'] = assess_weekly_trend(weekly_df)

    swings = find_swings_single(weekly_df, order=8)
    if len(swings) < 3:
        return result

    current_price = float(weekly_df['Close'].iloc[-1])
    lows = [s for s in swings if s['type'] == 'low']

    if not lows:
        return result

    best = None

    for origin in lows[-6:]:
        after = [s for s in swings if s['date'] > origin['date']]
        if not after:
            continue

        waves = [origin]
        for s in after:
            expected = 'high' if len(waves) % 2 == 1 else 'low'
            if s['type'] != expected:
                continue
            # W1 peak must exceed origin
            if len(waves) == 1 and s['price'] <= origin['price']:
                break
            # W2 must hold above origin
            if len(waves) == 2 and s['price'] <= origin['price']:
                break
            # W3 must exceed W1 peak
            if len(waves) == 3 and s['price'] <= waves[1]['price']:
                break
            # W4 must hold above W1 peak territory
            if len(waves) == 4 and s['price'] <= waves[1]['price']:
                break

            waves.append(s)
            if len(waves) >= 6:
                break

        if len(waves) >= 3 and (best is None or len(waves) > len(best)):
            best = waves

    if best is None:
        return result

    n = len(best)
    result['wave_points'] = best

    if n >= 6:
        if current_price < best[5]['price'] * 0.95:
            result['wave_position'] = 'CORRECTION'
            result['macro_phase'] = 'CORRECTING'
        else:
            result['wave_position'] = 'W5'
            result['macro_phase'] = 'IMPULSE_LATE'
    elif n == 5:
        if current_price > best[3]['price']:
            result['wave_position'] = 'W5'
            result['macro_phase'] = 'IMPULSE_LATE'
        else:
            result['wave_position'] = 'W4'
            result['macro_phase'] = 'IMPULSE_MID'
    elif n == 4:
        if current_price < best[3]['price'] * 0.92:
            result['wave_position'] = 'W4'
            result['macro_phase'] = 'IMPULSE_MID'
        else:
            result['wave_position'] = 'W3'
            result['macro_phase'] = 'IMPULSE_EARLY'
    elif n == 3:
        if current_price > best[1]['price']:
            result['wave_position'] = 'W3'
            result['macro_phase'] = 'IMPULSE_EARLY'
        else:
            result['wave_position'] = 'W2'
            result['macro_phase'] = 'BUILDING'
    elif n == 2:
        result['wave_position'] = 'W1' if current_price >= best[1]['price'] * 0.95 else 'W2'
        result['macro_phase'] = 'BUILDING'

    return result


# ═══════════════════════════════════════════════════════════════════════
# CARDINAL RULE VALIDATION
# ═══════════════════════════════════════════════════════════════════════

def validate_cardinal_rules(w1_origin, w1_peak, w2_bottom,
                            w3_peak=None, w4_bottom=None, w5_peak=None):
    if w2_bottom <= w1_origin:
        return False, "Rule 1: W2 broke below W1 origin"
    if w3_peak is not None and w4_bottom is not None:
        if w4_bottom <= w1_peak:
            return False, "Rule 3: W4 entered W1 territory"
    if w3_peak is not None:
        w1_move = w1_peak - w1_origin
        w3_move = w3_peak - w2_bottom
        if w5_peak is not None:
            w5_move = w5_peak - w4_bottom
            moves = [w1_move, w3_move, w5_move]
            if w3_move == min(moves):
                return False, "Rule 2: W3 is shortest impulse wave"
        elif w3_move < w1_move:
            return False, "Rule 2: W3 shorter than W1"
    return True, "All rules pass"

# ═══════════════════════════════════════════════════════════════════════
# FIBONACCI HELPERS
# ═══════════════════════════════════════════════════════════════════════

def closest_fib(retrace_pct, fib_levels):
    return min(fib_levels, key=lambda f: abs(f - retrace_pct))

def fib_distance(retrace_pct, fib_levels):
    return min(abs(retrace_pct - f) for f in fib_levels)

def calc_extensions(base_price, wave_move, ratios=None):
    if ratios is None:
        ratios = FIB_W3_TARGETS
    return {r: base_price + r * wave_move for r in ratios}


def calculate_channel(p1, p2, p_parallel, df_len):
    """
    Parallel channel from two base-line points and one parallel reference.
    p1, p2: (idx, price) defining the base trendline.
    p_parallel: (idx, price) for the parallel line.
    Returns channel dict or None.
    """
    x1, y1 = p1
    x2, y2 = p2
    if x2 == x1:
        return None

    slope = (y2 - y1) / (x2 - x1)
    base_intercept = y1 - slope * x1

    xp, yp = p_parallel
    parallel_intercept = yp - slope * xp

    if parallel_intercept > base_intercept:
        lower_intercept = base_intercept
        upper_intercept = parallel_intercept
    else:
        lower_intercept = parallel_intercept
        upper_intercept = base_intercept

    width = upper_intercept - lower_intercept
    if width <= 0:
        return None

    current_idx = df_len - 1
    lower_at_current = slope * current_idx + lower_intercept
    upper_at_current = slope * current_idx + upper_intercept

    if upper_at_current <= lower_at_current:
        return None

    return {
        'slope': slope,
        'lower_intercept': lower_intercept,
        'upper_intercept': upper_intercept,
        'lower_at_current': lower_at_current,
        'upper_at_current': upper_at_current,
        'is_rising': slope > 0,
    }


# ═══════════════════════════════════════════════════════════════════════
# SETUP A: WAVE 3 ENTRY (after Wave 2 completion)
# ═══════════════════════════════════════════════════════════════════════

def find_wave3_setups(swings, df, current_price, current_date, ticker=''):
    candidates = []
    for i in range(len(swings) - 2):
        if swings[i]['type'] != 'low':
            continue
        if i + 1 >= len(swings) or swings[i+1]['type'] != 'high':
            continue
        if i + 2 >= len(swings) or swings[i+2]['type'] != 'low':
            continue

        w1_origin = swings[i]
        w1_peak = swings[i+1]
        w2_bottom = swings[i+2]

        w1_move = w1_peak['price'] - w1_origin['price']
        if w1_move <= 0:
            continue
        w1_pct = w1_move / w1_origin['price'] * 100
        if w1_pct < 10:
            continue

        valid, _ = validate_cardinal_rules(w1_origin['price'], w1_peak['price'], w2_bottom['price'])
        if not valid:
            continue

        w2_retrace = (w1_peak['price'] - w2_bottom['price']) / w1_move
        fib_dist = fib_distance(w2_retrace, FIB_W2_IMPULSE)
        if fib_dist > FIB_TOLERANCE:
            continue

        days_since = (current_date - w2_bottom['date']).days
        if days_since > 90 or days_since < 0:
            continue

        recovery_pct = (current_price - w2_bottom['price']) / w2_bottom['price'] * 100
        if recovery_pct < -5 or recovery_pct > 80:
            continue

        stop = w2_bottom['price'] * (1 - STOP_BUFFER)
        risk = current_price - stop
        if risk <= 0:
            continue
        risk_pct = risk / current_price * 100
        if risk_pct < MIN_RISK_PCT or risk_pct > MAX_RISK_PCT:
            continue

        # Wave-3 targets are Fibonacci extensions of W1 projected from the W2 low.
        # Aleks marks 1.0 / 1.618 / 2.0+ extensions as targets (e.g. STM 1.618=$62.48,
        # 2.0=$80.95); the old "T2 = W1 peak" capped exits ~0.6x too early.
        t1 = w2_bottom['price'] + 1.000 * w1_move   # ~Wave-1 peak retest (first scale)
        t2 = w2_bottom['price'] + 1.618 * w1_move   # classic Wave-3 extension (main target)
        t3 = w2_bottom['price'] + 2.000 * w1_move   # extension runner

        # If price already ran past a target, roll each up to the next level
        if t1 <= current_price:
            t1 = t2
        if t2 <= current_price:
            t2 = t3
        if t2 <= t1:
            t2 = t1 * 1.05

        rr_t1 = (t1 - current_price) / risk
        if rr_t1 < MIN_RR_T1:
            continue

        channel = calculate_channel(
            (w1_origin['idx'], w1_origin['price']),
            (w2_bottom['idx'], w2_bottom['price']),
            (w1_peak['idx'], w1_peak['price']),
            len(df)
        )
        channel_pos = None
        if channel:
            span = channel['upper_at_current'] - channel['lower_at_current']
            if span > 0:
                channel_pos = (current_price - channel['lower_at_current']) / span

        candidates.append({
            'ticker': ticker,
            'setup_type': 'WAVE_3',
            'w1_origin': w1_origin,
            'w1_peak': w1_peak,
            'w2_bottom': w2_bottom,
            'w1_move': w1_move,
            'w1_pct': w1_pct,
            'w2_retrace': w2_retrace,
            'closest_fib': closest_fib(w2_retrace, FIB_W2_IMPULSE),
            'fib_distance': fib_dist,
            'current_price': current_price,
            'entry': current_price,
            'stop': stop,
            't1': t1,
            't2': t2,
            't3': t3,
            'risk_pct': risk_pct,
            'rr_t1': rr_t1,
            'rr_t2': (t2 - current_price) / risk if t2 > current_price else 0,
            'days_since_w2': days_since,
            'recovery_pct': recovery_pct,
            'channel': channel,
            'channel_position': channel_pos,
        })

    candidates.sort(key=lambda x: x['rr_t1'], reverse=True)
    return candidates[:3]

# ═══════════════════════════════════════════════════════════════════════
# SETUP B: WAVE 5 ENTRY (after Wave 4 completion)
# ═══════════════════════════════════════════════════════════════════════

def find_wave5_setups(swings, df, current_price, current_date, ticker=''):
    candidates = []
    for i in range(len(swings) - 4):
        types = [s['type'] for s in swings[i:i+5]]
        if types != ['low', 'high', 'low', 'high', 'low']:
            continue

        w1_o = swings[i]
        w1_p = swings[i+1]
        w2_b = swings[i+2]
        w3_p = swings[i+3]
        w4_b = swings[i+4]

        w1_move = w1_p['price'] - w1_o['price']
        w3_move = w3_p['price'] - w2_b['price']
        if w1_move <= 0 or w3_move <= 0:
            continue

        valid, reason = validate_cardinal_rules(
            w1_o['price'], w1_p['price'], w2_b['price'],
            w3_p['price'], w4_b['price'])
        if not valid:
            continue

        w2_ret = (w1_p['price'] - w2_b['price']) / w1_move
        w4_ret = (w3_p['price'] - w4_b['price']) / w3_move
        if fib_distance(w4_ret, FIB_W4_IMPULSE) > FIB_TOLERANCE + 0.03:
            continue

        days_since = (current_date - w4_b['date']).days
        if days_since > 90 or days_since < 0:
            continue

        recovery = (current_price - w4_b['price']) / w4_b['price'] * 100
        if recovery < -5 or recovery > 60:
            continue

        stop = w4_b['price'] * (1 - STOP_BUFFER)
        risk = current_price - stop
        if risk <= 0:
            continue
        risk_pct = risk / current_price * 100
        if risk_pct < MIN_RISK_PCT or risk_pct > MAX_RISK_PCT:
            continue

        t1 = w4_b['price'] + w1_move
        w13_move = w3_p['price'] - w1_o['price']
        t2 = w4_b['price'] + 0.618 * w13_move

        if t2 < t1:
            t2 = t1 + 0.382 * w1_move
        if t1 <= current_price:
            t1 = t2
        rr_t1 = (t1 - current_price) / risk
        if rr_t1 < MIN_RR_T1:
            continue

        w2_type = 'deep' if w2_ret > 0.55 else 'shallow'
        w4_type = 'deep' if w4_ret > 0.40 else 'shallow'
        alternates = w2_type != w4_type

        channel = calculate_channel(
            (w2_b['idx'], w2_b['price']),
            (w4_b['idx'], w4_b['price']),
            (w3_p['idx'], w3_p['price']),
            len(df)
        )
        channel_pos = None
        if channel:
            span = channel['upper_at_current'] - channel['lower_at_current']
            if span > 0:
                channel_pos = (current_price - channel['lower_at_current']) / span

        candidates.append({
            'ticker': ticker,
            'setup_type': 'WAVE_5',
            'w1_origin': w1_o,
            'w1_peak': w1_p,
            'w2_bottom': w2_b,
            'w3_peak': w3_p,
            'w4_bottom': w4_b,
            'w1_move': w1_move,
            'w3_move': w3_move,
            'w2_retrace': w2_ret,
            'w4_retrace': w4_ret,
            'closest_fib': closest_fib(w4_ret, FIB_W4_IMPULSE),
            'fib_distance': fib_distance(w4_ret, FIB_W4_IMPULSE),
            'alternation': alternates,
            'current_price': current_price,
            'entry': current_price,
            'stop': stop,
            't1': t1,
            't2': t2,
            'risk_pct': risk_pct,
            'rr_t1': rr_t1,
            'rr_t2': (t2 - current_price) / risk if t2 > current_price else 0,
            'days_since_w4': days_since,
            'recovery_pct': recovery,
            'channel': channel,
            'channel_position': channel_pos,
        })

    candidates.sort(key=lambda x: x['rr_t1'], reverse=True)
    return candidates[:3]

# ═══════════════════════════════════════════════════════════════════════
# SETUP C: CORRECTION COMPLETION (WXY/ABC at Fib of prior impulse)
# Like UUUU: completed impulse → large correction → entry at .382 Fib
# ═══════════════════════════════════════════════════════════════════════

def find_correction_setups(swings, df, current_price, current_date, ticker=''):
    candidates = []

    all_highs = [s for s in swings if s['type'] == 'high']
    all_lows = [s for s in swings if s['type'] == 'low']
    if not all_highs or not all_lows:
        return candidates

    for peak in all_highs:
        lows_after = [s for s in all_lows if s['date'] > peak['date']]
        if not lows_after:
            continue

        for trough in lows_after:
            decline = (peak['price'] - trough['price']) / peak['price']
            if decline < 0.30 or decline > 0.90:
                continue

            correction_days = (trough['date'] - peak['date']).days
            if correction_days < 30:
                continue

            full_range = peak['price'] - trough['price']

            days_since = (current_date - trough['date']).days
            if days_since > 90 or days_since < 0:
                continue

            recovery = (current_price - trough['price']) / trough['price'] * 100
            if recovery < -5 or recovery > 50:
                continue

            retrace_of_decline = (peak['price'] - current_price) / full_range if full_range > 0 else 0
            fib_dist = fib_distance(1 - retrace_of_decline, FIB_CORRECTION_RETRACE)
            current_fib = 1 - retrace_of_decline
            if current_fib < 0 or current_fib > 1:
                continue

            closest_fib_level = closest_fib(current_fib, FIB_CORRECTION_RETRACE)
            if abs(current_fib - closest_fib_level) > 0.10:
                continue

            stop = trough['price'] * (1 - STOP_BUFFER)
            risk = current_price - stop
            if risk <= 0:
                continue
            risk_pct = risk / current_price * 100
            if risk_pct < MIN_RISK_PCT or risk_pct > MAX_RISK_PCT:
                continue

            t1 = peak['price']
            t2 = peak['price'] + 0.382 * full_range

            rr_t1 = (t1 - current_price) / risk
            if rr_t1 < MIN_RR_T1:
                continue

            swings_in_correction = [s for s in swings
                                     if peak['date'] < s['date'] <= trough['date']]
            correction_waves = len(swings_in_correction)
            likely_wxy = correction_waves >= 4

            candidates.append({
                'ticker': ticker,
                'setup_type': 'CORRECTION',
                'peak': peak,
                'trough': trough,
                'decline_pct': decline * 100,
                'correction_days': correction_days,
                'correction_waves': correction_waves,
                'likely_wxy': likely_wxy,
                'current_fib_of_decline': current_fib,
                'closest_fib': closest_fib_level,
                'fib_distance': abs(current_fib - closest_fib_level),
                'current_price': current_price,
                'entry': current_price,
                'stop': stop,
                't1': t1,
                't2': t2,
                'risk_pct': risk_pct,
                'rr_t1': rr_t1,
                'rr_t2': (t2 - current_price) / risk if t2 > current_price else 0,
                'days_since_trough': days_since,
                'recovery_pct': recovery,
            })

    candidates.sort(key=lambda x: x['rr_t1'], reverse=True)
    seen_peaks = set()
    deduped = []
    for c in candidates:
        pk = c['peak']['date']
        if pk not in seen_peaks:
            seen_peaks.add(pk)
            deduped.append(c)
    return deduped[:3]

# ═══════════════════════════════════════════════════════════════════════
# MOMENTUM CONFIRMATION
# ═══════════════════════════════════════════════════════════════════════

def check_momentum(indicators):
    score = 0
    confirmations = []

    rsi = indicators['rsi']
    if len(rsi.dropna()) < 3:
        return 0, []

    rsi_now = rsi.iloc[-1]
    rsi_prev = rsi.iloc[-2]

    if rsi_now > 50 and rsi_prev <= 50:
        score += 3
        confirmations.append('RSI_CROSS_50')
    elif rsi_now > 40:
        score += 1

    if 25 < rsi_now < 45:
        score += 2
        confirmations.append('RSI_OVERSOLD_BOUNCE')

    hist = indicators['macd_hist']
    if len(hist.dropna()) >= 2:
        if hist.iloc[-1] > 0 and hist.iloc[-2] <= 0:
            score += 3
            confirmations.append('MACD_CROSS')
        elif hist.iloc[-1] > hist.iloc[-2]:
            score += 1
            confirmations.append('MACD_IMPROVING')

    stk = indicators['stoch_k']
    std = indicators['stoch_d']
    if len(stk.dropna()) >= 2:
        if stk.iloc[-1] > std.iloc[-1] and stk.iloc[-1] < 80:
            score += 2
            confirmations.append('STOCH_BULLISH')
        if stk.iloc[-2] < 20 and stk.iloc[-1] > 20:
            score += 2
            confirmations.append('STOCH_OVERSOLD_EXIT')

    return min(score, 7), confirmations

def check_bullish_divergence(df, rsi, lookback=40):
    if len(df) < lookback or len(rsi.dropna()) < lookback:
        return False
    recent = df.tail(lookback)
    recent_rsi = rsi.tail(lookback)
    lows_idx = argrelextrema(recent['Low'].values, np.less_equal, order=5)[0]
    if len(lows_idx) < 2:
        return False
    l1, l2 = lows_idx[-2], lows_idx[-1]
    price_lower = recent['Low'].iloc[l2] < recent['Low'].iloc[l1]
    rsi_higher = recent_rsi.iloc[l2] > recent_rsi.iloc[l1]
    return price_lower and rsi_higher

# ═══════════════════════════════════════════════════════════════════════
# SCORING SYSTEM — 140 points max
# ═══════════════════════════════════════════════════════════════════════

def score_candidate(candidate, indicators, weekly_trend, df):
    score = 0

    # 1. Wave Structure Quality (0-30)
    fd = candidate.get('fib_distance', 0.1)
    if fd < 0.02:   score += 30
    elif fd < 0.04: score += 25
    elif fd < 0.06: score += 18
    elif fd < 0.08: score += 10
    else:            score += 5

    # 2. Cardinal Rules (0-20) — already filtered, so all pass
    score += 20

    # 3. Multi-TF Alignment (0-20) + Degree alignment bonus (0-5)
    if weekly_trend == 'BULLISH':   score += 20
    elif weekly_trend == 'NEUTRAL': score += 10
    else:                           score += 0

    weekly_info = candidate.get('weekly_info', {})
    wave_pos = weekly_info.get('wave_position')
    setup_type = candidate.get('setup_type')
    if wave_pos and setup_type:
        if setup_type == 'WAVE_3' and wave_pos in ('W2', 'W3'):
            score += 5
        elif setup_type == 'WAVE_5' and wave_pos in ('W4', 'W5'):
            score += 3
        elif setup_type == 'CORRECTION' and wave_pos == 'CORRECTION':
            score += 5
    candidate['weekly_wave_position'] = wave_pos
    candidate['weekly_macro_phase'] = weekly_info.get('macro_phase')

    # 4. Momentum (0-15)
    mom_score, mom_confirms = check_momentum(indicators)
    score += min(mom_score * 2, 15)

    if check_bullish_divergence(df, indicators['rsi']):
        score += 5
        mom_confirms.append('BULLISH_DIVERGENCE')
    candidate['momentum_confirms'] = mom_confirms

    # 5. R:R Quality (0-15)
    rr = candidate.get('rr_t1', 0)
    if rr >= 6.0:   score += 15
    elif rr >= 4.0:  score += 12
    elif rr >= 3.0:  score += 8
    elif rr >= 2.5:  score += 5

    # 6. Alternation (0-5) — Wave 5 setups only
    if candidate.get('alternation'):
        score += 5

    # 7. Volume (0-5)
    if len(df) > 25:
        vol_20 = df['Volume'].tail(20).mean()
        vol_5 = df['Volume'].tail(5).mean()
        if vol_5 > vol_20 * 1.3:
            score += 3
        vol_prior = df['Volume'].iloc[-40:-20].mean() if len(df) > 40 else vol_20
        if vol_20 < vol_prior * 0.7:
            score += 2

    # 8. Freshness (0-10)
    days = candidate.get('days_since_w2',
           candidate.get('days_since_w4',
           candidate.get('days_since_trough', 999)))
    if days <= 5:    score += 10
    elif days <= 14: score += 7
    elif days <= 30: score += 4
    elif days <= 60: score += 1

    # 9. Channel Quality (0-10) — Aleks uses channels as confluence
    channel = candidate.get('channel')
    channel_pos = candidate.get('channel_position')
    if channel and channel_pos is not None:
        if channel['is_rising']:
            score += 3
        if 0 <= channel_pos <= 0.4:
            score += 4
        elif 0.4 < channel_pos <= 0.7:
            score += 2
        if 0 <= channel_pos <= 0.4 and fd < 0.05:
            score += 3

    candidate['score'] = score
    if score >= 100:  candidate['tier'] = 'A'
    elif score >= 80: candidate['tier'] = 'B'
    elif score >= 60: candidate['tier'] = 'C'
    else:             candidate['tier'] = 'D'

    # RSI at current bar
    rsi_val = indicators['rsi'].iloc[-1] if len(indicators['rsi'].dropna()) > 0 else None
    candidate['rsi'] = float(rsi_val) if rsi_val and not pd.isna(rsi_val) else None

    return score

# ═══════════════════════════════════════════════════════════════════════
# TRADE MANAGER — 6-stage stop management
# ═══════════════════════════════════════════════════════════════════════

class TradeManager:
    def __init__(self, signal):
        self.ticker = signal['ticker']
        self.setup_type = signal['setup_type']
        self.entry = signal['entry']
        self.initial_stop = signal['stop']
        self.current_stop = signal['stop']
        self.t1 = signal['t1']
        self.t2 = signal.get('t2', signal['t1'] * 1.2)
        self.initial_risk = self.entry - self.initial_stop
        self.max_price = self.entry
        self.t1_reached = False
        self.position_pct = 1.0
        self.realized_pnl = 0.0
        self.stage = 1
        self.status = 'OPEN'
        self.exit_price = None
        self.entry_date = signal.get('entry_date', datetime.now().strftime('%Y-%m-%d'))
        self.bars_since_entry = 0
        self.bars_at_breakeven = 0
        self.history = [{'date': self.entry_date, 'action': 'ENTRY',
                         'price': self.entry, 'stop': self.current_stop}]

    def update(self, date, high, low, close, atr):
        self.bars_since_entry += 1

        if low <= self.current_stop:
            pnl = self.position_pct * (self.current_stop - self.entry)
            self.realized_pnl += pnl
            self.status = 'STOPPED'
            self.exit_price = self.current_stop
            self.history.append({'date': str(date), 'action': 'STOP_HIT',
                                 'price': self.current_stop, 'pnl': self.realized_pnl})
            return {'action': 'STOP_HIT', 'price': self.current_stop, 'pnl': self.realized_pnl}

        self.max_price = max(self.max_price, high)
        fav = self.max_price - self.entry
        old_stop = self.current_stop

        # Stage 2: risk reduction after 1R
        if fav >= self.initial_risk and self.stage < 2:
            new_stop = self.entry - self.initial_risk * 0.5
            self.current_stop = max(self.current_stop, new_stop)
            self.stage = 2

        # Stage 3: breakeven after 2R
        if fav >= 2 * self.initial_risk and self.stage < 3:
            self.current_stop = max(self.current_stop, self.entry)
            self.stage = 3

        # Stage 4: trail with ATR after 3R
        if fav >= 3 * self.initial_risk and self.stage < 4:
            trail = self.max_price - 2.5 * atr
            self.current_stop = max(self.current_stop, trail)
            self.stage = 4

        # Stage 5: book 75% at T1, ride the remaining 25% to T2 (Aleks's two-stage exit)
        if self.t1 > 0 and high >= self.t1 and not self.t1_reached:
            self.realized_pnl += 0.75 * (self.t1 - self.entry)
            self.position_pct = 0.25
            self.t1_reached = True
            self.current_stop = max(self.current_stop, self.t1 - self.initial_risk)
            self.stage = max(self.stage, 5)
            self.history.append({'date': str(date), 'action': 'PARTIAL_EXIT_75%',
                                 'price': self.t1, 'stop': self.current_stop})

        # Stage 6: tighter ATR trail on the 25% runner
        if self.t1_reached:
            trail = self.max_price - 2.0 * atr
            self.current_stop = max(self.current_stop, trail)
            self.stage = max(self.stage, 6)

        # T2 — exit the remaining 25%
        if self.t2 > 0 and high >= self.t2 and self.t1_reached:
            self.realized_pnl += self.position_pct * (self.t2 - self.entry)
            self.status = 'T2_HIT'
            self.exit_price = self.t2
            self.history.append({'date': str(date), 'action': 'T2_HIT',
                                 'price': self.t2, 'pnl': self.realized_pnl})
            return {'action': 'T2_HIT', 'price': self.t2, 'pnl': self.realized_pnl}

        # Wave count invalidation: no progress after 30 bars
        if self.bars_since_entry >= 30 and fav < self.initial_risk and self.stage <= 1:
            pnl = self.position_pct * (close - self.entry)
            self.realized_pnl += pnl
            self.status = 'INVALIDATED'
            self.exit_price = close
            self.history.append({'date': str(date), 'action': 'WAVE_INVALID',
                                 'price': close, 'pnl': self.realized_pnl})
            return {'action': 'WAVE_INVALID', 'price': close, 'pnl': self.realized_pnl}

        # Stall at breakeven
        if self.current_stop >= self.entry:
            if abs(close - self.entry) / self.entry < 0.05:
                self.bars_at_breakeven += 1
            else:
                self.bars_at_breakeven = 0
            if self.bars_at_breakeven >= 15:
                pnl = self.position_pct * (close - self.entry)
                self.realized_pnl += pnl
                self.status = 'STALL_EXIT'
                self.exit_price = close
                self.history.append({'date': str(date), 'action': 'STALL_EXIT',
                                     'price': close, 'pnl': self.realized_pnl})
                return {'action': 'STALL_EXIT', 'price': close, 'pnl': self.realized_pnl}

        if self.current_stop != old_stop:
            self.history.append({'date': str(date), 'action': f'STOP_UPDATE_S{self.stage}',
                                 'stop': self.current_stop})

        return None

    def to_dict(self):
        return {
            'ticker': self.ticker, 'setup_type': self.setup_type,
            'entry': self.entry, 'initial_stop': self.initial_stop,
            'current_stop': self.current_stop, 't1': self.t1, 't2': self.t2,
            'initial_risk': self.initial_risk, 'max_price': self.max_price,
            't1_reached': self.t1_reached, 'position_pct': self.position_pct,
            'realized_pnl': self.realized_pnl, 'stage': self.stage,
            'status': self.status, 'entry_date': self.entry_date,
            'bars_since_entry': self.bars_since_entry,
            'bars_at_breakeven': self.bars_at_breakeven,
            'exit_price': self.exit_price,
            'history': self.history,
        }

    @classmethod
    def from_dict(cls, d):
        dummy = {'ticker': d['ticker'], 'setup_type': d['setup_type'],
                 'entry': d['entry'], 'stop': d['initial_stop'],
                 't1': d['t1'], 't2': d['t2'], 'entry_date': d['entry_date']}
        tm = cls(dummy)
        tm.current_stop = d['current_stop']
        tm.initial_risk = d['initial_risk']
        tm.max_price = d['max_price']
        tm.t1_reached = d.get('t1_reached', d.get('partial_taken', False))
        tm.position_pct = d['position_pct']
        tm.realized_pnl = d['realized_pnl']
        tm.stage = d['stage']
        tm.status = d['status']
        tm.bars_since_entry = d['bars_since_entry']
        tm.bars_at_breakeven = d['bars_at_breakeven']
        tm.exit_price = d.get('exit_price')
        tm.history = d['history']
        return tm

# ═══════════════════════════════════════════════════════════════════════
# TRADE TRACKER PERSISTENCE
# ═══════════════════════════════════════════════════════════════════════

TRADE_TRACKER_PATH = 'open_trades.json'

def load_trade_tracker():
    try:
        with open(TRADE_TRACKER_PATH) as f:
            data = json.load(f)
        return [TradeManager.from_dict(d) for d in data]
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def save_trade_tracker(trades):
    with open(TRADE_TRACKER_PATH, 'w') as f:
        json.dump([t.to_dict() for t in trades], f, indent=2, default=str)

def update_open_trades(open_trades, daily_data):
    events = []
    still_open = []
    for trade in open_trades:
        if trade.status != 'OPEN':
            continue
        df = daily_data.get(trade.ticker)
        if df is None or len(df) < 2:
            still_open.append(trade)
            continue
        bar = df.iloc[-1]
        atr = calculate_atr(df)
        atr_val = atr.iloc[-1] if len(atr.dropna()) > 0 else (bar['High'] - bar['Low'])
        result = trade.update(
            date=df.index[-1].strftime('%Y-%m-%d'),
            high=float(bar['High']),
            low=float(bar['Low']),
            close=float(bar['Close']),
            atr=float(atr_val),
        )
        if result:
            events.append({'ticker': trade.ticker, **result})
        else:
            still_open.append(trade)
    return events, still_open

# ═══════════════════════════════════════════════════════════════════════
# OUTPUT — Console + JSON + Charts
# ═══════════════════════════════════════════════════════════════════════

def print_results(candidates, title="SCAN RESULTS"):
    if not candidates:
        print(f"\n  No candidates found.")
        return

    for tier_label, tier_code in [('TIER A (Score >= 90)', 'A'),
                                   ('TIER B (Score 70-89)', 'B'),
                                   ('TIER C (Score 50-69)', 'C')]:
        tier_cands = [c for c in candidates if c.get('tier') == tier_code]
        if not tier_cands:
            continue
        print(f"\n  ═══ {tier_label}: {len(tier_cands)} candidates ═══")
        print(f"  {'Ticker':<8} {'Score':>5} {'Setup':<11} {'Price':>8} {'Stop':>8} {'T1':>8}"
              f" {'T2':>8} {'R:R':>5} {'Fib':>6} {'Days':>5} {'RSI':>5} {'Weekly':<8} {'Momentum'}")
        print(f"  {'─'*120}")
        for c in tier_cands[:20]:
            fib_str = f"{c.get('closest_fib', 0):.1%}" if c.get('closest_fib') else "N/A"
            days = c.get('days_since_w2', c.get('days_since_w4', c.get('days_since_trough', 0)))
            rsi_str = f"{c['rsi']:.0f}" if c.get('rsi') else "N/A"
            weekly = c.get('weekly_trend', 'N/A')
            mom = ','.join(c.get('momentum_confirms', [])[:2])
            print(f"  {c['ticker']:<8} {c['score']:>5.0f} {c['setup_type']:<11} "
                  f"${c['current_price']:>7.2f} ${c['stop']:>7.2f} ${c['t1']:>7.2f} "
                  f"${c.get('t2', 0):>7.2f} {c['rr_t1']:>5.1f} {fib_str:>6} {days:>5} "
                  f"{rsi_str:>5} {weekly:<8} {mom}")

def print_detailed(candidates, top_n=10):
    for c in candidates[:top_n]:
        print(f"\n  ┌{'─'*70}┐")
        print(f"  │ {c['ticker']:<8} │ {c['setup_type']:<11} │ Score: {c['score']:>3.0f} │ Tier: {c.get('tier', '?')} │")
        print(f"  ├{'─'*70}┤")
        print(f"  │ Price: ${c['current_price']:.2f}  Stop: ${c['stop']:.2f}  "
              f"T1: ${c['t1']:.2f}  T2: ${c.get('t2', 0):.2f}")
        print(f"  │ Risk: {c['risk_pct']:.1f}%  R:R(T1): {c['rr_t1']:.1f}x  "
              f"R:R(T2): {c.get('rr_t2', 0):.1f}x")
        if c['setup_type'] == 'WAVE_3':
            print(f"  │ W1: ${c['w1_origin']['price']:.2f} → ${c['w1_peak']['price']:.2f} "
                  f"(+{c['w1_pct']:.0f}%)")
            print(f"  │ W2: ${c['w1_peak']['price']:.2f} → ${c['w2_bottom']['price']:.2f} "
                  f"(retrace {c['w2_retrace']:.1%} at {c['closest_fib']:.1%} Fib)")
        elif c['setup_type'] == 'WAVE_5':
            print(f"  │ W4 retrace: {c['w4_retrace']:.1%} at {c['closest_fib']:.1%} Fib")
            print(f"  │ Alternation: {'Yes' if c.get('alternation') else 'No'}")
        elif c['setup_type'] == 'CORRECTION':
            print(f"  │ Peak: ${c['peak']['price']:.2f} → Trough: ${c['trough']['price']:.2f} "
                  f"({c['decline_pct']:.0f}% decline)")
            print(f"  │ Correction waves: {c['correction_waves']}  "
                  f"WXY likely: {'Yes' if c.get('likely_wxy') else 'No'}")
        rsi_detail = f"{c['rsi']:.1f}" if c.get('rsi') else 'N/A'
        wave_pos = c.get('weekly_wave_position', '')
        macro = c.get('weekly_macro_phase', '')
        macro_str = f"  Macro: {wave_pos} ({macro})" if wave_pos else ""
        ch_str = ""
        if c.get('channel_position') is not None:
            ch_str = f"  Channel: {c['channel_position']:.0%}"
        print(f"  │ RSI: {rsi_detail}  Weekly: {c.get('weekly_trend', 'N/A')}{macro_str}{ch_str}")
        print(f"  │ Momentum: {', '.join(c.get('momentum_confirms', []))}")
        print(f"  └{'─'*70}┘")

def generate_charts(candidates, daily_data, filename='ew_scanner_v2_charts.png'):
    top = [c for c in candidates if c.get('tier') in ('A', 'B')][:12]
    if not top:
        top = candidates[:8]
    if not top:
        return

    n = len(top)
    cols = 2
    rows = (n + 1) // 2
    fig, axes = plt.subplots(rows, cols, figsize=(18, 5 * rows))
    if rows == 1 and cols == 1:
        axes = np.array([axes])
    axes = axes.flatten()

    for idx, c in enumerate(top):
        ax = axes[idx]
        ticker = c['ticker']
        df = daily_data.get(ticker)
        if df is None:
            continue

        plot_df = df.tail(250)
        ax.plot(plot_df.index, plot_df['Close'], color='white', linewidth=1)
        ax.fill_between(plot_df.index, plot_df['Low'], plot_df['High'], alpha=0.15, color='cyan')

        # Mark wave points
        if c['setup_type'] == 'WAVE_3':
            for label, pt, color in [('W1o', c['w1_origin'], 'lime'),
                                      ('W1', c['w1_peak'], 'yellow'),
                                      ('W2', c['w2_bottom'], 'red')]:
                ax.annotate(label, (pt['date'], pt['price']),
                           fontsize=8, color=color, fontweight='bold',
                           ha='center', va='bottom' if 'o' in label or '2' in label else 'top')
                ax.scatter([pt['date']], [pt['price']], color=color, s=40, zorder=5)
        elif c['setup_type'] == 'WAVE_5':
            for label, pt, color in [('0', c['w1_origin'], 'lime'),
                                      ('1', c['w1_peak'], 'yellow'),
                                      ('2', c['w2_bottom'], 'red'),
                                      ('3', c['w3_peak'], 'yellow'),
                                      ('4', c['w4_bottom'], 'red')]:
                ax.annotate(label, (pt['date'], pt['price']),
                           fontsize=8, color=color, fontweight='bold',
                           ha='center', va='bottom' if label in ('0', '2', '4') else 'top')
                ax.scatter([pt['date']], [pt['price']], color=color, s=40, zorder=5)
        elif c['setup_type'] == 'CORRECTION':
            for label, pt, color in [('Peak', c['peak'], 'yellow'),
                                      ('Trough', c['trough'], 'red')]:
                ax.annotate(label, (pt['date'], pt['price']),
                           fontsize=8, color=color, fontweight='bold',
                           ha='center', va='top' if label == 'Peak' else 'bottom')
                ax.scatter([pt['date']], [pt['price']], color=color, s=40, zorder=5)

        # Target lines
        for tgt, lbl, clr in [(c['t1'], 'T1', '#00ff88'), (c.get('t2', 0), 'T2', '#00ccff')]:
            if tgt and tgt > 0:
                ax.axhline(y=tgt, color=clr, linestyle='--', alpha=0.5, linewidth=0.8)
                ax.text(plot_df.index[-1], tgt, f' {lbl}=${tgt:.0f}', color=clr,
                        fontsize=7, va='bottom')

        # Stop line
        ax.axhline(y=c['stop'], color='red', linestyle='--', alpha=0.5, linewidth=0.8)
        ax.text(plot_df.index[-1], c['stop'], f' SL=${c["stop"]:.0f}', color='red',
                fontsize=7, va='top')

        # Channel trendlines
        ch = c.get('channel')
        if ch and df is not None:
            n_bars = len(df)
            plot_start = n_bars - len(plot_df)
            ch_dates = []
            ch_lower = []
            ch_upper = []
            for j in range(len(plot_df)):
                gi = plot_start + j
                ch_dates.append(plot_df.index[j])
                ch_lower.append(ch['slope'] * gi + ch['lower_intercept'])
                ch_upper.append(ch['slope'] * gi + ch['upper_intercept'])
            ax.plot(ch_dates, ch_lower, color='#ff9900', linestyle='--', alpha=0.6, linewidth=0.8)
            ax.plot(ch_dates, ch_upper, color='#ff9900', linestyle='--', alpha=0.6, linewidth=0.8)
            ax.fill_between(ch_dates, ch_lower, ch_upper, alpha=0.04, color='orange')

        fib_str = f"{c.get('closest_fib', 0):.0%}" if c.get('closest_fib') else ""
        macro_str = f" | Wkly:{c.get('weekly_wave_position', '')}" if c.get('weekly_wave_position') else ""
        ax.set_title(f"{ticker} | {c['setup_type']} | Score:{c['score']:.0f} | "
                     f"R:R:{c['rr_t1']:.1f} | {fib_str}{macro_str}",
                     fontsize=10, color='white')
        ax.set_facecolor('#1a1a2e')
        ax.tick_params(colors='gray', labelsize=7)
        ax.grid(alpha=0.1)

    for i in range(len(top), len(axes)):
        axes[i].set_visible(False)

    fig.patch.set_facecolor('#0f0f23')
    fig.suptitle(f'Aleks EWT Scanner v2 — {datetime.now().strftime("%Y-%m-%d")}',
                 color='white', fontsize=14)
    plt.tight_layout()
    plt.savefig(filename, dpi=150, bbox_inches='tight', facecolor='#0f0f23')
    plt.close()
    print(f"\n  Charts saved to {filename}")

def save_json(candidates, filename='ew_scanner_v2_results.json'):
    output = []
    skip_keys = {'weekly_info'}
    for c in candidates:
        d = {}
        for k, v in c.items():
            if k in skip_keys:
                continue
            if isinstance(v, dict) and 'date' in v:
                d[k] = {'price': v['price'],
                         'date': str(v['date'])[:10]}
            elif isinstance(v, (np.floating, np.integer)):
                d[k] = float(v)
            elif isinstance(v, pd.Timestamp):
                d[k] = str(v)[:10]
            else:
                d[k] = v
        output.append(d)
    with open(filename, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"  Results saved to {filename}")

# ═══════════════════════════════════════════════════════════════════════
# UNIVERSE FILTERS
# ═══════════════════════════════════════════════════════════════════════

def apply_universe_filters(daily_data):
    filtered = {}
    for ticker, df in daily_data.items():
        try:
            price = float(df['Close'].iloc[-1])
            if price < MIN_PRICE or price > MAX_PRICE:
                continue
            avg_vol = float(df['Volume'].tail(20).mean())
            if avg_vol < MIN_AVG_VOLUME:
                continue
            atr = calculate_atr(df)
            if len(atr.dropna()) == 0:
                continue
            atr_pct = float(atr.iloc[-1]) / price * 100
            if atr_pct < 1.0 or atr_pct > 10.0:
                continue
            filtered[ticker] = df
        except Exception:
            pass
    return filtered

# ═══════════════════════════════════════════════════════════════════════
# MAIN SCAN LOOP
# ═══════════════════════════════════════════════════════════════════════

def analyze_ticker(ticker, daily_df, weekly_df):
    current_price = float(daily_df['Close'].iloc[-1])
    current_date = daily_df.index[-1]

    weekly_info = count_weekly_waves(weekly_df)
    if weekly_info['trend'] == 'BEARISH':
        return []

    swings = detect_swings(daily_df)
    if len(swings) < 3:
        return []

    candidates = []

    # Setup A: Wave 3
    w3_setups = find_wave3_setups(swings, daily_df, current_price, current_date, ticker)
    candidates.extend(w3_setups)

    # Setup B: Wave 5
    w5_setups = find_wave5_setups(swings, daily_df, current_price, current_date, ticker)
    candidates.extend(w5_setups)

    # Setup C: Correction completion
    corr_setups = find_correction_setups(swings, daily_df, current_price, current_date, ticker)
    candidates.extend(corr_setups)

    # Calculate indicators + score
    indicators = calculate_indicators(daily_df)
    for c in candidates:
        c['weekly_trend'] = weekly_info['trend']
        c['weekly_info'] = weekly_info
        score_candidate(c, indicators, weekly_info['trend'], daily_df)

    return candidates


def main():
    print("=" * 80)
    print("  ALEKS ELLIOTT WAVE SCANNER v2")
    print(f"  Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  Strategy: Long-only | Setups: Wave 3, Wave 5, Correction Completion")
    print("=" * 80)

    # Phase 1: Get tickers
    print("\n  Phase 1: Building universe...")
    sp500 = get_sp500_tickers()
    smallmid = get_smallmid_tickers()
    try:
        all_traded = get_all_traded_tickers()
        print(f"  Sources: {len(sp500)} S&P 500 + {len(smallmid)} Small/Mid + {len(all_traded)} NASDAQ/NYSE traded + {len(CURATED_ETFS)} ETFs")
    except Exception as e:
        all_traded = []
        print(f"  NASDAQ traded fetch failed ({e}), using index-only universe")
    universe = list(set(sp500 + smallmid + all_traded + CURATED_ETFS))
    print(f"  Universe: {len(universe)} unique tickers (will filter by ${MIN_MARKET_CAP/1e6:.0f}M+ market cap)")

    # Phase 2A: Quick screen — download 1 month to filter by dollar volume
    end_date = datetime.now().strftime('%Y-%m-%d')
    screen_start = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')

    print("\n  Phase 2A: Quick screen (1 month data)...")
    screen_data = download_batch(universe, screen_start, end_date, interval='1d', min_bars=10)
    print()

    viable = []
    for ticker, df in screen_data.items():
        try:
            price = float(df['Close'].iloc[-1])
            if price < MIN_PRICE or price > MAX_PRICE:
                continue
            avg_vol = float(df['Volume'].tail(20).mean())
            avg_dollar_vol = price * avg_vol
            if avg_dollar_vol < 1_000_000:
                continue
            viable.append(ticker)
        except Exception:
            pass
    print(f"  Quick screen: {len(viable)} tickers pass (price + $1M+ avg daily dollar volume)")

    # Phase 2B: Full download for viable tickers only
    daily_start = (datetime.now() - timedelta(days=730)).strftime('%Y-%m-%d')
    weekly_start = (datetime.now() - timedelta(days=1825)).strftime('%Y-%m-%d')

    print("\n  Phase 2B: Downloading full history for viable tickers...")
    daily_data = download_batch(viable, daily_start, end_date, interval='1d')
    weekly_data = download_batch(viable, weekly_start, end_date, interval='1wk')

    # Phase 3: Universe filters
    print("\n\n  Phase 3: Applying universe filters...")
    filtered = apply_universe_filters(daily_data)
    print(f"  After filters: {len(filtered)} tickers (from {len(daily_data)})")

    # Phase 4: Scan for setups
    print("\n  Phase 4: Scanning for Elliott Wave setups...")
    all_candidates = []
    scanned = 0
    for ticker in filtered:
        try:
            daily_df = filtered[ticker]
            weekly_df = weekly_data.get(ticker)
            candidates = analyze_ticker(ticker, daily_df, weekly_df)
            all_candidates.extend(candidates)
        except Exception:
            pass
        scanned += 1
        if scanned % 100 == 0:
            print(f"\r  Scanned: {scanned}/{len(filtered)} tickers, "
                  f"{len(all_candidates)} candidates found", end='', flush=True)
    print(f"\r  Scanned: {scanned}/{len(filtered)} tickers, "
          f"{len(all_candidates)} candidates found")

    # Sort and deduplicate
    all_candidates.sort(key=lambda x: x.get('score', 0), reverse=True)
    seen = set()
    deduped = []
    for c in all_candidates:
        if c['ticker'] not in seen:
            seen.add(c['ticker'])
            deduped.append(c)
    all_candidates = deduped

    # Phase 5: Results
    print("\n  Phase 5: Results")
    print(f"\n  Total candidates: {len(all_candidates)}")
    by_type = {}
    for c in all_candidates:
        t = c['setup_type']
        by_type[t] = by_type.get(t, 0) + 1
    for t, n in sorted(by_type.items()):
        print(f"    {t}: {n}")

    print_results(all_candidates)
    print_detailed(all_candidates, top_n=15)

    # Phase 6: Output
    print("\n  Phase 6: Saving output...")
    save_json(all_candidates)
    if all_candidates:
        generate_charts(all_candidates, daily_data)

    # Phase 7: Update trade tracker
    print("\n  Phase 7: Trade tracker...")
    open_trades = load_trade_tracker()
    if open_trades:
        print(f"  Open trades: {len(open_trades)}")
        events, still_open = update_open_trades(open_trades, daily_data)
        for e in events:
            print(f"    {e['ticker']}: {e['action']} at ${e['price']:.2f} "
                  f"(P&L: ${e.get('pnl', 0):.2f})")
        save_trade_tracker(still_open)
    else:
        print("  No open trades to manage.")

    # Summary
    tier_a = [c for c in all_candidates if c.get('tier') == 'A']
    tier_b = [c for c in all_candidates if c.get('tier') == 'B']
    print(f"\n  ═══ SUMMARY ═══")
    print(f"  Tier A candidates: {len(tier_a)}")
    print(f"  Tier B candidates: {len(tier_b)}")
    print(f"  Total actionable:  {len(tier_a) + len(tier_b)}")
    if tier_a:
        print(f"\n  Top Tier A picks:")
        for c in tier_a[:5]:
            print(f"    {c['ticker']:<8} {c['setup_type']:<11} Score:{c['score']:.0f} "
                  f"R:R:{c['rr_t1']:.1f} Entry:${c['current_price']:.2f} "
                  f"Stop:${c['stop']:.2f} T1:${c['t1']:.2f}")

    print(f"\n{'='*80}")
    print(f"  Scan complete. {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'='*80}")


if __name__ == '__main__':
    main()
