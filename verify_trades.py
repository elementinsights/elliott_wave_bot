#!/usr/bin/env python3
"""
Verify Aleks's 6 sample trades against actual price data.
For each trade: find entry date, map wave count, verify stops/targets against Fibonacci levels.
"""

import yfinance as yf
import pandas as pd
import numpy as np
from scipy.signal import argrelextrema
from datetime import timedelta

def find_swings(df, order=10):
    highs = df['High'].values
    lows = df['Low'].values
    hi_idx = argrelextrema(highs, np.greater_equal, order=order)[0]
    lo_idx = argrelextrema(lows, np.less_equal, order=order)[0]
    swings = []
    for i in hi_idx:
        swings.append({'idx': i, 'date': df.index[i], 'price': highs[i], 'type': 'high'})
    for i in lo_idx:
        swings.append({'idx': i, 'date': df.index[i], 'price': lows[i], 'type': 'low'})
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

def fib_retrace(high, low, ratio):
    return high - ratio * (high - low)

def fib_extend(base, move, ratio):
    return base + ratio * move

def calculate_rsi(df, period=14):
    delta = df['Close'].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.ewm(alpha=1/period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def analyze_trade(ticker, entry_price, stop, t1, t2, approx_entry_date=None,
                  data_start='2018-01-01', data_end='2026-12-31', notes=''):
    print(f"\n{'='*80}")
    print(f"  {ticker} — Entry: ${entry_price}, Stop: ${stop}, T1: ${t1}, T2: ${t2 or 'N/A'}")
    if notes:
        print(f"  Notes: {notes}")
    print(f"{'='*80}")

    df = yf.download(ticker, start=data_start, end=data_end, interval='1d', progress=False)
    if df.empty:
        print(f"  ERROR: No data for {ticker}")
        return
    if isinstance(df.columns, pd.MultiIndex):
        # Robustly keep the OHLC field level (the one containing 'Close'),
        # whether the ticker is on level 0 (group_by='ticker') or level 1.
        lvl1 = df.columns.get_level_values(1)
        df.columns = lvl1 if 'Close' in lvl1 else df.columns.get_level_values(0)

    # Find the entry date (when price was near entry_price)
    if approx_entry_date:
        window_start = pd.Timestamp(approx_entry_date) - timedelta(days=30)
        window_end = pd.Timestamp(approx_entry_date) + timedelta(days=30)
        window = df.loc[window_start:window_end]
    else:
        window = df

    # Find dates where close was within 2% of entry price
    close_matches = window[abs(window['Close'] - entry_price) / entry_price < 0.02]
    if close_matches.empty:
        close_matches = window[abs(window['Close'] - entry_price) / entry_price < 0.05]

    if not close_matches.empty:
        entry_date = close_matches.index[0]
        print(f"\n  Entry date (closest match): {entry_date.strftime('%Y-%m-%d')}")
        print(f"  Actual close on that date: ${df.loc[entry_date, 'Close']:.2f}")
    else:
        print(f"\n  WARNING: Could not find entry date near ${entry_price}")
        entry_date = None

    # Analyze wave structure using data BEFORE entry
    if entry_date:
        pre_entry = df.loc[:entry_date]
    else:
        pre_entry = df

    risk = entry_price - stop
    risk_pct = risk / entry_price * 100
    rr_t1 = (t1 - entry_price) / risk if risk > 0 else 0
    rr_t2 = (t2 - entry_price) / risk if t2 and risk > 0 else 0

    print(f"\n  Risk: ${risk:.2f} ({risk_pct:.1f}%)")
    print(f"  R:R to T1: {rr_t1:.1f}:1")
    if t2:
        print(f"  R:R to T2: {rr_t2:.1f}:1")

    # Swing analysis on pre-entry data (use 2+ years before entry)
    if entry_date:
        analysis_start = entry_date - timedelta(days=900)
        analysis_data = df.loc[analysis_start:entry_date]
    else:
        analysis_data = pre_entry.tail(500)

    print(f"\n  Analysis window: {analysis_data.index[0].strftime('%Y-%m-%d')} to {analysis_data.index[-1].strftime('%Y-%m-%d')}")
    print(f"  Bars: {len(analysis_data)}")

    # Detect swings at multiple orders
    for order in [8, 12, 15, 20]:
        swings = find_swings(analysis_data, order=order)
        if len(swings) < 3:
            continue

        print(f"\n  --- Swings (order={order}): {len(swings)} points ---")

        # Find major highs and lows
        all_highs = [s for s in swings if s['type'] == 'high']
        all_lows = [s for s in swings if s['type'] == 'low']

        if all_highs and all_lows:
            peak = max(all_highs, key=lambda x: x['price'])
            trough = min(all_lows, key=lambda x: x['price'])

            print(f"  Major Peak: ${peak['price']:.2f} on {peak['date'].strftime('%Y-%m-%d')}")
            print(f"  Major Trough: ${trough['price']:.2f} on {trough['date'].strftime('%Y-%m-%d')}")

            if peak['date'] < trough['date']:
                decline = (peak['price'] - trough['price']) / peak['price'] * 100
                print(f"  Decline: {decline:.1f}%")

            # Fibonacci retracement from peak to trough
            move = peak['price'] - trough['price']
            print(f"\n  Fibonacci Retracements (Peak ${peak['price']:.2f} to Trough ${trough['price']:.2f}):")
            for ratio in [0.236, 0.382, 0.500, 0.618, 0.786, 0.887]:
                level = trough['price'] + ratio * move
                dist_to_entry = abs(level - entry_price) / entry_price * 100
                marker = " <-- ENTRY" if dist_to_entry < 3 else ""
                marker2 = " <-- STOP" if abs(level - stop) / stop * 100 < 5 else ""
                marker3 = " <-- T1" if abs(level - t1) / t1 * 100 < 3 else ""
                marker4 = " <-- T2" if t2 and abs(level - t2) / t2 * 100 < 3 else ""
                print(f"    {ratio:.3f}: ${level:.2f}{marker}{marker2}{marker3}{marker4}")

            # Also check Fib from trough (as new impulse origin)
            # Look for waves after trough
            post_trough = [s for s in swings if s['date'] > trough['date']]
            if post_trough:
                first_high_after = next((s for s in post_trough if s['type'] == 'high'), None)
                first_low_after_high = None
                if first_high_after:
                    first_low_after_high = next(
                        (s for s in post_trough if s['type'] == 'low' and s['date'] > first_high_after['date']),
                        None
                    )

                if first_high_after:
                    w1_move = first_high_after['price'] - trough['price']
                    w1_pct = w1_move / trough['price'] * 100
                    print(f"\n  Potential Wave 1: ${trough['price']:.2f} → ${first_high_after['price']:.2f} (+{w1_pct:.1f}%)")
                    print(f"    Date: {trough['date'].strftime('%Y-%m-%d')} → {first_high_after['date'].strftime('%Y-%m-%d')}")

                    if first_low_after_high:
                        w2_retrace = (first_high_after['price'] - first_low_after_high['price']) / w1_move
                        print(f"  Potential Wave 2: ${first_high_after['price']:.2f} → ${first_low_after_high['price']:.2f}")
                        print(f"    Retrace: {w2_retrace*100:.1f}%")
                        print(f"    Date: {first_low_after_high['date'].strftime('%Y-%m-%d')}")

                        # Extension targets from W2 bottom
                        print(f"\n  Fibonacci Extensions from W2 bottom (${first_low_after_high['price']:.2f}):")
                        for ratio in [0.382, 0.618, 0.786, 1.000, 1.618, 2.000, 2.272, 3.618]:
                            ext = first_low_after_high['price'] + ratio * w1_move
                            marker = ""
                            if abs(ext - t1) / t1 * 100 < 3: marker = " <-- T1"
                            if t2 and abs(ext - t2) / t2 * 100 < 3: marker = " <-- T2"
                            if abs(ext - entry_price) / entry_price * 100 < 3: marker = " <-- ENTRY"
                            print(f"    {ratio:.3f}x: ${ext:.2f}{marker}")

    # Post-entry price action
    if entry_date:
        post_entry = df.loc[entry_date:]
        if len(post_entry) > 1:
            max_price = post_entry['High'].max()
            max_date = post_entry['High'].idxmax()
            min_price = post_entry['Low'].min()
            min_date = post_entry['Low'].idxmin()

            print(f"\n  POST-ENTRY PRICE ACTION:")
            print(f"    Max price: ${max_price:.2f} on {max_date.strftime('%Y-%m-%d')}")
            print(f"    Min price: ${min_price:.2f} on {min_date.strftime('%Y-%m-%d')}")
            print(f"    Max gain: +{(max_price - entry_price) / entry_price * 100:.1f}%")
            print(f"    Max drawdown: {(min_price - entry_price) / entry_price * 100:.1f}%")
            print(f"    Hit T1 (${t1}): {'YES' if max_price >= t1 else 'NO'}")
            if t2:
                print(f"    Hit T2 (${t2}): {'YES' if max_price >= t2 else 'NO'}")
            print(f"    Hit Stop (${stop}): {'YES' if min_price <= stop else 'NO'}")

            # Find when stop was hit or target was hit
            for i, row in post_entry.iterrows():
                if row['Low'] <= stop:
                    print(f"    Stop hit on: {i.strftime('%Y-%m-%d')} (Low=${row['Low']:.2f})")
                    break
                if row['High'] >= t1:
                    print(f"    T1 hit on: {i.strftime('%Y-%m-%d')} (High=${row['High']:.2f})")
                    break

    # RSI at entry
    rsi = calculate_rsi(df)
    if entry_date and entry_date in rsi.index:
        print(f"\n  RSI(14) at entry: {rsi.loc[entry_date]:.1f}")


print("=" * 80)
print("  ALEKS TRADE VERIFICATION — 6 Sample Trades vs Real Price Data")
print("=" * 80)

# NFLX: Entry $81.77, Stop $75, T1 $124, T2 $150
# NFLX was around $81 in early 2023 (after the 2022 crash from ~$700 to ~$165)
# Actually NFLX went from ~$700 to ~$165 in 2022... $81.77 doesn't match recent history
# Let me check if NFLX had a split. Yes, NFLX had a stock split... no, NFLX has never split (10:1 rumored but didn't happen)
# Wait — NFLX was around $81 in late 2012 / early 2013. But that seems too old for these alerts.
# OR this could be adjusted for a split. Let me just pull data and look.
analyze_trade('NFLX', 81.77, 75, 124, 150,
              approx_entry_date='2012-10-01',
              data_start='2010-01-01', data_end='2026-12-31',
              notes='Need to find when NFLX was near $81.77')

# ARM: Entry $103.79, Stop $90, T1 $140, T2 $184 (already verified)
analyze_trade('ARM', 103.79, 90, 140, 184,
              approx_entry_date='2026-02-05',
              data_start='2023-01-01', data_end='2026-12-31',
              notes='Wave 3 entry after deep W2 retrace — previously verified')

# EVTC: Entry $29.17, Stop $25.70, T1 $42, T2 $52
analyze_trade('EVTC', 29.17, 25.70, 42, 52,
              approx_entry_date=None,
              data_start='2020-01-01', data_end='2026-12-31',
              notes='Closed at $29.30 — wave count invalidation')

# RR: Entry $2.52, Stop $2.30, T1 $4.70, T2 $7.30
analyze_trade('RR', 2.52, 2.30, 4.70, 7.30,
              approx_entry_date=None,
              data_start='2020-01-01', data_end='2026-12-31',
              notes='Stopped out — low-priced stock with large R:R')

# DELL: Entry $126, Stop $119, T1 $150, T2 None
analyze_trade('DELL', 126, 119, 150, None,
              approx_entry_date=None,
              data_start='2020-01-01', data_end='2026-12-31',
              notes='Stall at breakeven — closed at $127.81')

# UUUU: Entry $4.21, Stop $3.50, T1 $11, T2 None
# From alerts: Aug 26, 2025 stop moved to $8.23; Aug 28, 2025 stop moved to $11.30
# Chart shows WXY correction after completed 5-wave impulse
analyze_trade('UUUU', 4.21, 3.50, 11.00, None,
              approx_entry_date='2025-03-01',
              data_start='2018-01-01', data_end='2026-12-31',
              notes='WXY correction completion — .382 Fib entry. Stop updates Aug 2025.')

print("\n\nDone.")
