#!/usr/bin/env python3
"""
EWT Strategy Backtester
Pre-computes swing patterns once, then sweeps parameter combinations.
Reports strategies ranked by Sharpe ratio.
"""

import json
import time
import warnings
from datetime import datetime, timedelta
from io import StringIO
from itertools import product

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
import yfinance as yf
from scipy.signal import argrelextrema

warnings.filterwarnings('ignore')

HEADERS = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}

# ═══════════════════════════════════════════════════════════════════════
# DATA
# ═══════════════════════════════════════════════════════════════════════

def get_sp500_tickers():
    url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
    resp = requests.get(url, headers=HEADERS)
    tables = pd.read_html(StringIO(resp.text))
    tickers = tables[0]['Symbol'].tolist()
    return [t.replace('.', '-') for t in tickers]

def download_batch(tickers, start, end, interval='1d', batch_size=50):
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
                        df.columns = df.columns.droplevel(1)
                    df = df.dropna(subset=['Close'])
                    if len(df) >= 100:
                        all_data[t] = df
                except Exception:
                    pass
        except Exception:
            pass
        if i + batch_size < len(tickers):
            time.sleep(0.3)
        pct = min(100, (i + batch_size) / len(tickers) * 100)
        print(f"\r  Downloading: {pct:.0f}% ({len(all_data)} tickers)", end='', flush=True)
    print()
    return all_data

# ═══════════════════════════════════════════════════════════════════════
# INDICATORS
# ═══════════════════════════════════════════════════════════════════════

def calculate_atr(df, period=14):
    high_low = df['High'] - df['Low']
    high_close = abs(df['High'] - df['Close'].shift(1))
    low_close = abs(df['Low'] - df['Close'].shift(1))
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, min_periods=period).mean()

# ═══════════════════════════════════════════════════════════════════════
# SWING DETECTION
# ═══════════════════════════════════════════════════════════════════════

def find_swings(df, order=10):
    highs = df['High'].values
    lows = df['Low'].values
    hi_idx = argrelextrema(highs, np.greater_equal, order=order)[0]
    lo_idx = argrelextrema(lows, np.less_equal, order=order)[0]
    swings = []
    for i in hi_idx:
        swings.append({'idx': int(i), 'price': float(highs[i]), 'type': 'high'})
    for i in lo_idx:
        swings.append({'idx': int(i), 'price': float(lows[i]), 'type': 'low'})
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

def detect_swings_multi(df, orders=(8, 10, 12, 15), min_confirms=2):
    all_points = {}
    for order in orders:
        swings = find_swings(df, order)
        for s in swings:
            key = s['idx']
            if key not in all_points:
                all_points[key] = {**s, 'count': 0}
            all_points[key]['count'] += 1
            if s['type'] == 'high' and s['price'] > all_points[key]['price']:
                all_points[key]['price'] = s['price']
            elif s['type'] == 'low' and s['price'] < all_points[key]['price']:
                all_points[key]['price'] = s['price']
    confirmed = sorted([v for v in all_points.values() if v['count'] >= min_confirms],
                       key=lambda x: x['idx'])
    alt = []
    for s in confirmed:
        if not alt or alt[-1]['type'] != s['type']:
            alt.append(s)
        else:
            if s['type'] == 'high' and s['price'] > alt[-1]['price']:
                alt[-1] = s
            elif s['type'] == 'low' and s['price'] < alt[-1]['price']:
                alt[-1] = s
    return alt

# ═══════════════════════════════════════════════════════════════════════
# WEEKLY TREND (pre-computed at each weekly bar)
# ═══════════════════════════════════════════════════════════════════════

def precompute_weekly_trends(weekly_df):
    """Returns a Series of weekly trends indexed by date."""
    if weekly_df is None or len(weekly_df) < 50:
        return None
    sma40 = weekly_df['Close'].rolling(40).mean()
    swings = find_swings(weekly_df, order=5)
    trends = pd.Series('NEUTRAL', index=weekly_df.index)
    for i in range(40, len(weekly_df)):
        current = float(weekly_df['Close'].iloc[i])
        sma_val = float(sma40.iloc[i])
        if pd.isna(sma_val):
            continue
        above = current > sma_val
        relevant = [s for s in swings if s['idx'] <= i]
        highs = [s for s in relevant if s['type'] == 'high'][-3:]
        lows = [s for s in relevant if s['type'] == 'low'][-3:]
        hh = len(highs) >= 2 and highs[-1]['price'] > highs[-2]['price']
        hl = len(lows) >= 2 and lows[-1]['price'] > lows[-2]['price']
        lh = len(highs) >= 2 and highs[-1]['price'] < highs[-2]['price']
        ll = len(lows) >= 2 and lows[-1]['price'] < lows[-2]['price']
        if above and (hh or hl):
            trends.iloc[i] = 'BULLISH'
        elif not above and (lh or ll):
            trends.iloc[i] = 'BEARISH'
    return trends

def get_weekly_trend_at(weekly_trends, weekly_df, daily_date):
    """Look up weekly trend for a given daily date."""
    if weekly_trends is None:
        return 'NEUTRAL'
    mask = weekly_df.index <= daily_date
    if not mask.any():
        return 'NEUTRAL'
    idx = weekly_df.index[mask][-1]
    return weekly_trends.loc[idx]

# ═══════════════════════════════════════════════════════════════════════
# PRE-COMPUTE ALL POTENTIAL PATTERNS (once per stock)
# ═══════════════════════════════════════════════════════════════════════

def precompute_patterns(swings, closes):
    """
    Extract all potential Wave 3, Wave 5, and Correction patterns from swings.
    These are parameter-independent — just the raw swing relationships.
    """
    patterns = {'WAVE_3': [], 'WAVE_5': [], 'CORRECTION': []}
    n_bars = len(closes)

    # Wave 3: L-H-L sequences
    for i in range(len(swings) - 2):
        s0, s1, s2 = swings[i], swings[i+1], swings[i+2]
        if s0['type'] != 'low' or s1['type'] != 'high' or s2['type'] != 'low':
            continue
        w1_move = s1['price'] - s0['price']
        if w1_move <= 0:
            continue
        if s2['price'] <= s0['price']:
            continue
        retrace = (s1['price'] - s2['price']) / w1_move
        w1_pct = w1_move / s0['price']
        patterns['WAVE_3'].append({
            'w1_origin': s0['price'], 'w1_peak': s1['price'],
            'w2_bottom': s2['price'], 'w1_move': w1_move,
            'w1_pct': w1_pct, 'w2_retrace': retrace,
            'setup_bar': s2['idx'],
        })

    # Wave 5: 5-swing sequences
    for i in range(len(swings) - 4):
        types = [s['type'] for s in swings[i:i+5]]
        if types != ['low', 'high', 'low', 'high', 'low']:
            continue
        s0, s1, s2, s3, s4 = swings[i:i+5]
        w1 = s1['price'] - s0['price']
        w3 = s3['price'] - s2['price']
        if w1 <= 0 or w3 <= 0:
            continue
        if s2['price'] <= s0['price']:
            continue
        if s4['price'] <= s1['price']:
            continue
        if w3 < w1 * 0.5:
            continue
        w4_ret = (s3['price'] - s4['price']) / w3
        patterns['WAVE_5'].append({
            'w1_origin': s0['price'], 'w1_peak': s1['price'],
            'w2_bottom': s2['price'], 'w3_peak': s3['price'],
            'w4_bottom': s4['price'],
            'w1_move': w1, 'w3_move': w3,
            'w13_move': s3['price'] - s0['price'],
            'w4_retrace': w4_ret,
            'setup_bar': s4['idx'],
        })

    # Correction: peak → trough (>30% decline)
    all_highs = [s for s in swings if s['type'] == 'high']
    all_lows = [s for s in swings if s['type'] == 'low']
    for peak in all_highs:
        for trough in [s for s in all_lows if s['idx'] > peak['idx']]:
            decline = (peak['price'] - trough['price']) / peak['price']
            if decline < 0.30 or decline > 0.90:
                continue
            corr_bars = trough['idx'] - peak['idx']
            if corr_bars < 15:
                continue
            patterns['CORRECTION'].append({
                'peak': peak['price'], 'trough': trough['price'],
                'decline': decline,
                'full_range': peak['price'] - trough['price'],
                'setup_bar': trough['idx'],
            })

    return patterns

# ═══════════════════════════════════════════════════════════════════════
# TRADE SIMULATION
# ═══════════════════════════════════════════════════════════════════════

def simulate_trade(entry_idx, entry_price, stop, t1, t2, setup_type,
                   highs, lows, closes, atr_vals, params):
    """Simulate a single trade. Returns result dict or None."""
    initial_risk = entry_price - stop
    if initial_risk <= 0:
        return None

    partial_pct = params['partial_at_t1']
    trail_atr = params['trail_atr']
    n_bars = len(closes)

    current_stop = stop
    max_price = entry_price
    partial_taken = False
    position_pct = 1.0
    realized_pnl = 0.0
    stage = 1
    bars_held = 0
    bars_at_be = 0

    for bar in range(entry_idx + 1, min(entry_idx + 201, n_bars)):
        bars_held += 1
        h, l, c = float(highs[bar]), float(lows[bar]), float(closes[bar])
        atr_val = float(atr_vals[bar]) if not np.isnan(atr_vals[bar]) else initial_risk

        if l <= current_stop:
            pnl = position_pct * (current_stop - entry_price) / entry_price
            realized_pnl += pnl
            return {'exit': 'STOP', 'pnl_pct': realized_pnl * 100,
                    'r_multiple': realized_pnl * entry_price / initial_risk,
                    'bars_held': bars_held, 'setup_type': setup_type}

        max_price = max(max_price, h)
        fav = max_price - entry_price

        if fav >= initial_risk and stage < 2:
            current_stop = max(current_stop, entry_price - initial_risk * 0.5)
            stage = 2
        if fav >= 2 * initial_risk and stage < 3:
            current_stop = max(current_stop, entry_price)
            stage = 3
        if fav >= 3 * initial_risk and stage < 4:
            current_stop = max(current_stop, max_price - trail_atr * atr_val)
            stage = 4

        if h >= t1 and not partial_taken:
            partial_pnl = partial_pct * (t1 - entry_price) / entry_price
            realized_pnl += partial_pnl
            position_pct = 1.0 - partial_pct
            partial_taken = True
            current_stop = max(current_stop, t1 - initial_risk)
            stage = 5
            if partial_pct >= 1.0:
                return {'exit': 'T1_FULL', 'pnl_pct': realized_pnl * 100,
                        'r_multiple': realized_pnl * entry_price / initial_risk,
                        'bars_held': bars_held, 'setup_type': setup_type}

        if partial_taken:
            current_stop = max(current_stop, max_price - max(1.5, trail_atr - 0.5) * atr_val)
            stage = 6

        if h >= t2 and partial_taken:
            remaining_pnl = position_pct * (t2 - entry_price) / entry_price
            realized_pnl += remaining_pnl
            return {'exit': 'T2', 'pnl_pct': realized_pnl * 100,
                    'r_multiple': realized_pnl * entry_price / initial_risk,
                    'bars_held': bars_held, 'setup_type': setup_type}

        if bars_held >= 30 and fav < initial_risk and stage <= 1:
            pnl = position_pct * (c - entry_price) / entry_price
            realized_pnl += pnl
            return {'exit': 'INVALIDATED', 'pnl_pct': realized_pnl * 100,
                    'r_multiple': realized_pnl * entry_price / initial_risk,
                    'bars_held': bars_held, 'setup_type': setup_type}

        if current_stop >= entry_price and abs(c - entry_price) / entry_price < 0.05:
            bars_at_be += 1
        else:
            bars_at_be = 0
        if bars_at_be >= 15:
            pnl = position_pct * (c - entry_price) / entry_price
            realized_pnl += pnl
            return {'exit': 'STALL', 'pnl_pct': realized_pnl * 100,
                    'r_multiple': realized_pnl * entry_price / initial_risk,
                    'bars_held': bars_held, 'setup_type': setup_type}

    c = float(closes[min(entry_idx + 200, n_bars - 1)])
    pnl = position_pct * (c - entry_price) / entry_price
    realized_pnl += pnl
    return {'exit': 'TIME_EXIT', 'pnl_pct': realized_pnl * 100,
            'r_multiple': realized_pnl * entry_price / initial_risk,
            'bars_held': min(bars_held, 200), 'setup_type': setup_type}

# ═══════════════════════════════════════════════════════════════════════
# BACKTEST ENGINE (fast — uses pre-computed data)
# ═══════════════════════════════════════════════════════════════════════

def run_backtest_for_params(stock_cache, params):
    """
    Run backtest for one parameter set across all pre-computed stocks.
    stock_cache = {ticker: {patterns, closes, highs, lows, atr_vals, weekly_trends, weekly_df, daily_df}}
    """
    all_trades = []
    w2_min = params['w2_fib_min']
    w2_max = params['w2_fib_max']
    w4_min = params.get('w4_fib_min', 0.236)
    w4_max = params.get('w4_fib_max', 0.618)
    stop_buf = params['stop_buffer']
    t1_ext = params['t1_ext']
    min_w1 = params['min_w1_pct'] / 100.0
    min_rr = params['min_rr']
    max_days = params.get('max_days_since', 60)
    weekly_filter = params.get('weekly_filter', 'BULLISH_NEUTRAL')
    scan_step = 10

    for ticker, cache in stock_cache.items():
        patterns = cache['patterns']
        closes = cache['closes']
        highs = cache['highs']
        lows = cache['lows']
        atr_vals = cache['atr_vals']
        weekly_trends = cache['weekly_trends']
        weekly_df = cache['weekly_df']
        daily_df = cache['daily_df']
        n_bars = len(closes)

        qualified = []

        # Filter Wave 3 patterns
        for p in patterns['WAVE_3']:
            if p['w2_retrace'] < w2_min or p['w2_retrace'] > w2_max:
                continue
            if p['w1_pct'] < min_w1:
                continue
            sb = p['setup_bar']
            for entry_bar in range(sb + 1, min(sb + max_days + 1, n_bars)):
                ep = float(closes[entry_bar])
                stop = p['w2_bottom'] * (1 - stop_buf)
                risk = ep - stop
                if risk <= 0 or risk / ep < 0.015 or risk / ep > 0.18:
                    continue
                t1 = p['w2_bottom'] + t1_ext * p['w1_move']
                t2 = p['w1_peak']
                if t1 <= ep:
                    t1 = t2
                if t2 < t1:
                    t2 = t1 * 1.05
                rr = (t1 - ep) / risk
                if rr < min_rr:
                    continue
                qualified.append((entry_bar, ep, stop, t1, t2, 'WAVE_3', rr))
                break

        # Filter Wave 5 patterns
        for p in patterns['WAVE_5']:
            if p['w4_retrace'] < w4_min or p['w4_retrace'] > w4_max + 0.06:
                continue
            sb = p['setup_bar']
            for entry_bar in range(sb + 1, min(sb + max_days + 1, n_bars)):
                ep = float(closes[entry_bar])
                stop = p['w4_bottom'] * (1 - stop_buf)
                risk = ep - stop
                if risk <= 0 or risk / ep < 0.015 or risk / ep > 0.18:
                    continue
                t1 = p['w4_bottom'] + p['w1_move']
                t2 = p['w4_bottom'] + 0.618 * p['w13_move']
                if t2 < t1:
                    t2 = t1 + 0.382 * p['w1_move']
                if t1 <= ep:
                    t1 = t2
                rr = (t1 - ep) / risk
                if rr < min_rr:
                    continue
                qualified.append((entry_bar, ep, stop, t1, t2, 'WAVE_5', rr))
                break

        # Filter Correction patterns
        for p in patterns['CORRECTION']:
            sb = p['setup_bar']
            for entry_bar in range(sb + 1, min(sb + max_days + 1, n_bars)):
                ep = float(closes[entry_bar])
                recovery = (ep - p['trough']) / p['trough']
                if recovery < -0.05 or recovery > 0.50:
                    continue
                stop = p['trough'] * (1 - stop_buf)
                risk = ep - stop
                if risk <= 0 or risk / ep < 0.015 or risk / ep > 0.18:
                    continue
                t1 = p['peak']
                t2 = p['peak'] + 0.382 * p['full_range']
                rr = (t1 - ep) / risk
                if rr < min_rr:
                    continue
                qualified.append((entry_bar, ep, stop, t1, t2, 'CORRECTION', rr))
                break

        # Sort by entry bar, simulate without overlapping trades
        qualified.sort(key=lambda x: x[0])
        active_end = 0

        for entry_bar, ep, stop, t1, t2, stype, rr in qualified:
            if entry_bar < active_end:
                continue

            # Weekly filter
            if weekly_trends is not None and weekly_df is not None:
                daily_date = daily_df.index[entry_bar]
                trend = get_weekly_trend_at(weekly_trends, weekly_df, daily_date)
                if weekly_filter == 'BULLISH' and trend != 'BULLISH':
                    continue
                elif weekly_filter == 'BULLISH_NEUTRAL' and trend == 'BEARISH':
                    continue

            result = simulate_trade(entry_bar, ep, stop, t1, t2, stype,
                                    highs, lows, closes, atr_vals, params)
            if result:
                result['ticker'] = ticker
                all_trades.append(result)
                active_end = entry_bar + result['bars_held'] + 1

    return all_trades

# ═══════════════════════════════════════════════════════════════════════
# METRICS
# ═══════════════════════════════════════════════════════════════════════

def compute_metrics(trades):
    if not trades:
        return {'total_trades': 0, 'win_rate': 0, 'avg_pnl': 0, 'avg_r': 0,
                'sharpe': -999, 'profit_factor': 0, 'max_dd_r': 0,
                'avg_bars': 0, 'median_r': 0, 'total_r': 0, 'std_r': 0,
                'exit_counts': {}, 'type_counts': {}}

    r_arr = np.array([t['r_multiple'] for t in trades])
    pnls = [t['pnl_pct'] for t in trades]
    bars = [t['bars_held'] for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    gross_profit = sum(wins) if wins else 0
    gross_loss = abs(sum(losses)) if losses else 0.001

    avg_r = float(np.mean(r_arr))
    std_r = float(np.std(r_arr)) if len(r_arr) > 1 else 1.0
    trades_per_year = max(1, len(trades) / 5)
    sharpe = (avg_r / std_r) * np.sqrt(trades_per_year) if std_r > 0 else 0

    cum_r = np.cumsum(r_arr)
    peak_r = np.maximum.accumulate(cum_r)
    max_dd_r = float(np.min(cum_r - peak_r)) if len(cum_r) > 0 else 0

    exit_counts = {}
    type_counts = {}
    for t in trades:
        exit_counts[t['exit']] = exit_counts.get(t['exit'], 0) + 1
        type_counts[t['setup_type']] = type_counts.get(t['setup_type'], 0) + 1

    return {
        'total_trades': len(trades),
        'win_rate': len(wins) / len(trades) * 100,
        'avg_pnl': float(np.mean(pnls)),
        'avg_r': avg_r,
        'median_r': float(np.median(r_arr)),
        'std_r': std_r,
        'sharpe': sharpe,
        'profit_factor': gross_profit / gross_loss,
        'max_dd_r': max_dd_r,
        'avg_bars': float(np.mean(bars)),
        'total_r': float(np.sum(r_arr)),
        'exit_counts': exit_counts,
        'type_counts': type_counts,
    }

# ═══════════════════════════════════════════════════════════════════════
# PARAMETER GRID
# ═══════════════════════════════════════════════════════════════════════

PHASE1_GRID = {
    'w2_fib_min':    [0.382, 0.500, 0.618],
    'w2_fib_max':    [0.786, 0.887],
    'stop_buffer':   [0.03, 0.05, 0.08],
    't1_ext':        [0.382, 0.618, 1.000],
    'partial_at_t1': [0.50, 0.75, 1.00],
    'min_w1_pct':    [15],
    'trail_atr':     [2.5],
    'min_rr':        [2.5],
    'weekly_filter': ['BULLISH_NEUTRAL'],
}

PHASE2_GRID = {
    'min_w1_pct':    [10, 15, 20],
    'trail_atr':     [2.0, 2.5, 3.0],
    'min_rr':        [2.0, 2.5, 3.0],
    'weekly_filter': ['BULLISH', 'BULLISH_NEUTRAL'],
}

PARAM_GRID = PHASE1_GRID

def generate_combos(grid):
    keys = list(grid.keys())
    values = list(grid.values())
    combos = []
    for vals in product(*values):
        combo = dict(zip(keys, vals))
        combo['w4_fib_min'] = 0.236
        combo['w4_fib_max'] = 0.618
        combo['max_days_since'] = 60
        combos.append(combo)
    return combos

# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════

def main():
    print("=" * 80)
    print("  EWT STRATEGY BACKTESTER")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 80)

    # Phase 1: Download data
    print("\n  Phase 1: Getting tickers...")
    tickers = get_sp500_tickers()
    print(f"  Universe: {len(tickers)} S&P 500 tickers")

    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=1825)).strftime('%Y-%m-%d')
    weekly_start = (datetime.now() - timedelta(days=3650)).strftime('%Y-%m-%d')

    print("\n  Phase 2: Downloading data...")
    daily_data = download_batch(tickers, start_date, end_date, interval='1d')
    print("  Downloading weekly data...")
    weekly_data = download_batch(tickers, weekly_start, end_date, interval='1wk')

    filtered = {}
    for t, df in daily_data.items():
        if len(df) >= 500:
            avg_vol = float(df['Volume'].tail(60).mean())
            price = float(df['Close'].iloc[-1])
            if avg_vol >= 500_000 and 5 <= price <= 2000:
                filtered[t] = df
    print(f"  Filtered: {len(filtered)} stocks")

    # Phase 3: Pre-compute (expensive, but only once)
    print("\n  Phase 3: Pre-computing swing patterns & indicators...")
    stock_cache = {}
    for i, (ticker, df) in enumerate(filtered.items()):
        swings = detect_swings_multi(df)
        if len(swings) < 3:
            continue
        atr = calculate_atr(df)
        weekly_df = weekly_data.get(ticker)
        weekly_trends = precompute_weekly_trends(weekly_df)
        patterns = precompute_patterns(swings, df['Close'].values)
        total_patterns = sum(len(v) for v in patterns.values())
        if total_patterns == 0:
            continue
        stock_cache[ticker] = {
            'patterns': patterns,
            'closes': df['Close'].values,
            'highs': df['High'].values,
            'lows': df['Low'].values,
            'atr_vals': atr.values,
            'weekly_trends': weekly_trends,
            'weekly_df': weekly_df,
            'daily_df': df,
        }
        if (i + 1) % 50 == 0:
            print(f"\r  Pre-computed: {i+1}/{len(filtered)} stocks, {len(stock_cache)} with patterns", end='', flush=True)
    print(f"\r  Pre-computed: {len(stock_cache)} stocks with viable patterns                    ")

    # Phase 4A: Coarse sweep (core parameters)
    combos = generate_combos(PHASE1_GRID)
    print(f"\n  Phase 4A: Coarse sweep — {len(combos)} combinations (core params)...")
    results = []
    start_time = time.time()

    for ci, params in enumerate(combos):
        trades = run_backtest_for_params(stock_cache, params)
        metrics = compute_metrics(trades)
        results.append({**{k: v for k, v in params.items()
                           if k not in ('w4_fib_min', 'w4_fib_max', 'max_days_since')},
                        **metrics})
        if (ci + 1) % 50 == 0 or ci == len(combos) - 1:
            elapsed = time.time() - start_time
            eta = elapsed / (ci + 1) * (len(combos) - ci - 1)
            print(f"\r  {ci+1}/{len(combos)} ({elapsed:.0f}s, ~{eta:.0f}s left)", end='', flush=True)

    elapsed_p1 = time.time() - start_time
    print(f"\n  Phase 4A done in {elapsed_p1:.0f}s")

    # Phase 4B: Fine sweep — take top 5 core configs, vary secondary params
    results_p1 = [r for r in results if r['total_trades'] >= 15]
    results_p1.sort(key=lambda x: x['sharpe'], reverse=True)
    top5_cores = results_p1[:5]

    phase2_combos = generate_combos(PHASE2_GRID)
    print(f"\n  Phase 4B: Fine sweep — top 5 cores × {len(phase2_combos)} secondary combos = {5 * len(phase2_combos)} runs...")

    start_time = time.time()
    phase2_results = []
    total_runs = len(top5_cores) * len(phase2_combos)
    run_count = 0

    for core in top5_cores:
        for p2 in phase2_combos:
            params = {**core}
            for k in ('total_trades', 'win_rate', 'avg_pnl', 'avg_r', 'median_r', 'std_r',
                       'sharpe', 'profit_factor', 'max_dd_r', 'avg_bars', 'total_r',
                       'exit_counts', 'type_counts'):
                params.pop(k, None)
            params.update(p2)
            params['w4_fib_min'] = 0.236
            params['w4_fib_max'] = 0.618
            params['max_days_since'] = 60

            trades = run_backtest_for_params(stock_cache, params)
            metrics = compute_metrics(trades)
            phase2_results.append({**{k: v for k, v in params.items()
                                       if k not in ('w4_fib_min', 'w4_fib_max', 'max_days_since')},
                                    **metrics})
            run_count += 1
            if run_count % 20 == 0 or run_count == total_runs:
                elapsed = time.time() - start_time
                eta = elapsed / run_count * (total_runs - run_count)
                print(f"\r  {run_count}/{total_runs} ({elapsed:.0f}s, ~{eta:.0f}s left)", end='', flush=True)

    elapsed_p2 = time.time() - start_time
    print(f"\n  Phase 4B done in {elapsed_p2:.0f}s")

    # Merge all results
    results = results + phase2_results
    print(f"\n  Total parameter sets evaluated: {len(results)}")

    # Filter out combos with too few trades
    results = [r for r in results if r['total_trades'] >= 15]
    results.sort(key=lambda x: x['sharpe'], reverse=True)

    # Phase 5: Results
    print(f"\n{'='*130}")
    print(f"  TOP 25 STRATEGIES BY SHARPE RATIO  (min 15 trades)")
    print(f"{'='*130}")
    print(f"  {'#':>3} {'Sharpe':>7} {'Trades':>6} {'Win%':>6} {'AvgR':>6} {'MedR':>6} "
          f"{'PF':>5} {'MaxDD':>6} {'TotR':>7} {'W2 Fib':>10} {'Stop':>5} {'T1ext':>5} "
          f"{'Part%':>5} {'W1min':>5} {'Trail':>5} {'RR':>4} {'Weekly':>10}")
    print(f"  {'─'*127}")

    for i, r in enumerate(results[:25]):
        print(f"  {i+1:>3} {r['sharpe']:>7.2f} {r['total_trades']:>6} "
              f"{r['win_rate']:>6.1f} {r['avg_r']:>6.2f} {r['median_r']:>6.2f} "
              f"{r['profit_factor']:>5.2f} {r['max_dd_r']:>6.1f} {r['total_r']:>7.1f} "
              f"{r['w2_fib_min']:.2f}-{r['w2_fib_max']:.2f} "
              f"{r['stop_buffer']:>5.0%} {r['t1_ext']:>5.2f} "
              f"{r['partial_at_t1']:>5.0%} {r['min_w1_pct']:>5}% "
              f"{r['trail_atr']:>5.1f} {r['min_rr']:>4.1f} "
              f"{r['weekly_filter']:>10}")

    # Detailed top 5
    print(f"\n{'='*80}")
    print(f"  DETAILED BREAKDOWN — TOP 5")
    print(f"{'='*80}")

    for i, r in enumerate(results[:5]):
        print(f"\n  === STRATEGY #{i+1} — Sharpe: {r['sharpe']:.2f} ===")
        print(f"  Parameters:")
        print(f"    W2 Fib Range: {r['w2_fib_min']:.3f} - {r['w2_fib_max']:.3f}")
        print(f"    Stop Buffer:  {r['stop_buffer']:.0%}    T1 Extension: {r['t1_ext']:.3f}x W1")
        print(f"    Partial @ T1: {r['partial_at_t1']:.0%}    Trail ATR:    {r['trail_atr']:.1f}x")
        print(f"    Min W1 Move:  {r['min_w1_pct']}%     Min R:R:      {r['min_rr']:.1f}")
        print(f"    Weekly:       {r['weekly_filter']}")
        print(f"  Performance:")
        print(f"    Trades: {r['total_trades']:>5}   Win Rate: {r['win_rate']:.1f}%")
        print(f"    Avg R:  {r['avg_r']:>+.3f}  Median R: {r['median_r']:>+.3f}")
        print(f"    PF:     {r['profit_factor']:.2f}    Total R:  {r['total_r']:>+.1f}")
        print(f"    Max DD: {r['max_dd_r']:.1f}R   Avg Bars: {r['avg_bars']:.0f}")
        ec = r.get('exit_counts', {})
        print(f"  Exits: ", end='')
        for k in ['T1_FULL', 'T2', 'STOP', 'INVALIDATED', 'STALL', 'TIME_EXIT', 'OPEN']:
            if ec.get(k, 0) > 0:
                print(f"{k}:{ec[k]} ", end='')
        print()
        tc = r.get('type_counts', {})
        print(f"  Types: ", end='')
        for k in ['WAVE_3', 'WAVE_5', 'CORRECTION']:
            if tc.get(k, 0) > 0:
                print(f"{k}:{tc[k]} ", end='')
        print()

    # Worst 5 (for comparison)
    bottom = [r for r in results if r['total_trades'] >= 15]
    bottom.sort(key=lambda x: x['sharpe'])
    print(f"\n  --- WORST 5 (for comparison) ---")
    for i, r in enumerate(bottom[:5]):
        print(f"  #{i+1} Sharpe:{r['sharpe']:>6.2f} Trades:{r['total_trades']:>4} Win%:{r['win_rate']:>5.1f} "
              f"W2:{r['w2_fib_min']:.2f}-{r['w2_fib_max']:.2f} Stop:{r['stop_buffer']:.0%} "
              f"T1:{r['t1_ext']:.2f} Part:{r['partial_at_t1']:.0%}")

    # Parameter sensitivity analysis
    print(f"\n{'='*80}")
    print(f"  PARAMETER SENSITIVITY (avg Sharpe per value)")
    print(f"{'='*80}")

    all_params = {**PHASE1_GRID, **PHASE2_GRID}
    for param_name in all_params:
        values_map = {}
        for r in results:
            v = r.get(param_name)
            if v not in values_map:
                values_map[v] = []
            values_map[v].append(r['sharpe'])
        print(f"\n  {param_name}:")
        for v in sorted(values_map.keys(), key=lambda x: str(x)):
            arr = values_map[v]
            print(f"    {str(v):>16}: avg Sharpe {np.mean(arr):>6.2f}  "
                  f"(best {np.max(arr):>6.2f}, n={len(arr)})")

    # Save results
    output = []
    for r in results[:100]:
        clean = {}
        for k, v in r.items():
            if isinstance(v, (np.floating, np.integer)):
                clean[k] = round(float(v), 4)
            elif isinstance(v, dict):
                clean[k] = {str(kk): int(vv) if isinstance(vv, (np.integer,)) else vv
                            for kk, vv in v.items()}
            else:
                clean[k] = v
        output.append(clean)
    with open('ew_backtest_results.json', 'w') as f:
        json.dump(output, f, indent=2, default=str)

    # Charts
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.patch.set_facecolor('#0f0f23')

    valid = [r for r in results if r['total_trades'] >= 15]
    sharpes = [r['sharpe'] for r in valid]
    wins_arr = [r['win_rate'] for r in valid]
    pfs = [r['profit_factor'] for r in valid]
    n_trades = [r['total_trades'] for r in valid]

    for ax in axes.flatten():
        ax.set_facecolor('#1a1a2e')
        ax.tick_params(colors='gray', labelsize=8)
        ax.grid(alpha=0.1)

    axes[0, 0].hist(sharpes, bins=40, color='cyan', alpha=0.7, edgecolor='white', linewidth=0.5)
    axes[0, 0].set_title('Sharpe Distribution', color='white', fontsize=10)
    if valid:
        axes[0, 0].axvline(x=valid[0]['sharpe'], color='lime', linestyle='--',
                           label=f"Best: {valid[0]['sharpe']:.2f}")
        axes[0, 0].legend(facecolor='#1a1a2e', edgecolor='gray', labelcolor='white')

    axes[0, 1].scatter(wins_arr, sharpes, alpha=0.3, c='cyan', s=8)
    axes[0, 1].set_title('Sharpe vs Win Rate', color='white', fontsize=10)
    axes[0, 1].set_xlabel('Win Rate %', color='gray')

    axes[1, 0].scatter(n_trades, sharpes, alpha=0.3, c='orange', s=8)
    axes[1, 0].set_title('Sharpe vs # Trades', color='white', fontsize=10)
    axes[1, 0].set_xlabel('Total Trades', color='gray')

    axes[1, 1].scatter(pfs, sharpes, alpha=0.3, c='lime', s=8)
    axes[1, 1].set_title('Sharpe vs Profit Factor', color='white', fontsize=10)
    axes[1, 1].set_xlabel('Profit Factor', color='gray')

    fig.suptitle(f'EWT Backtest — {len(results)} Combinations, {len(stock_cache)} Stocks, 5yr',
                 color='white', fontsize=13)
    plt.tight_layout()
    plt.savefig('ew_backtest_results.png', dpi=150, bbox_inches='tight', facecolor='#0f0f23')
    plt.close()
    print(f"\n  Results: ew_backtest_results.json")
    print(f"  Charts:  ew_backtest_results.png")
    print(f"\n{'='*80}")
    print(f"  Done. {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'='*80}")


if __name__ == '__main__':
    main()
