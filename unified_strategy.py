import yfinance as yf
import pandas as pd
import numpy as np
from scipy.signal import argrelextrema
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

# ═══════════════════════════════════════════════════════════════════════
# UNIFIED ELLIOTT WAVE STRATEGY
# Built from: ARM (completed), STM (completed), ZETA (active)
# ═══════════════════════════════════════════════════════════════════════

def find_swings(df, order=5):
    prices_high = df['High'].values
    prices_low = df['Low'].values
    swing_high_idx = argrelextrema(prices_high, np.greater_equal, order=order)[0]
    swing_low_idx = argrelextrema(prices_low, np.less_equal, order=order)[0]
    swings = []
    for idx in swing_high_idx:
        swings.append({'idx': idx, 'date': df.index[idx], 'price': prices_high[idx], 'type': 'high'})
    for idx in swing_low_idx:
        swings.append({'idx': idx, 'date': df.index[idx], 'price': prices_low[idx], 'type': 'low'})
    swings.sort(key=lambda x: x['idx'])
    filtered = []
    for s in swings:
        if not filtered or filtered[-1]['type'] != s['type']:
            filtered.append(s)
        else:
            if s['type'] == 'high' and s['price'] > filtered[-1]['price']:
                filtered[-1] = s
            elif s['type'] == 'low' and s['price'] < filtered[-1]['price']:
                filtered[-1] = s
    return filtered


def find_sub_wave1(df, origin_idx, w1_top_idx, origin_price):
    """Find the first clean sub-impulse within Wave (1).
    This is the smaller-degree Wave (1) used for practical targets."""
    w1_df = df.loc[origin_idx:w1_top_idx]
    candidates = []

    for order in [5, 8, 10, 12]:
        swings = find_swings(w1_df, order=order)
        # Find first strong high after origin, then first pullback
        highs = [s for s in swings if s['type'] == 'high']
        lows = [s for s in swings if s['type'] == 'low']

        if len(highs) >= 1 and len(lows) >= 1:
            first_high = highs[0]
            # First pullback after that high
            pullbacks = [s for s in lows if s['date'] > first_high['date']]
            if pullbacks:
                first_pull = pullbacks[0]
                move = first_high['price'] - origin_price
                retrace = first_high['price'] - first_pull['price']
                retrace_pct = (retrace / move * 100) if move > 0 else 0

                candidates.append({
                    'order': order,
                    'sub_w1_high': first_high['price'],
                    'sub_w1_high_date': first_high['date'],
                    'sub_w1_pullback': first_pull['price'],
                    'sub_w1_pullback_date': first_pull['date'],
                    'sub_w1_move': move,
                    'sub_w1_retrace_pct': retrace_pct,
                })

    return candidates


def analyze_correction_subwaves(df, peak_idx, origin_idx):
    """Analyze the bearish correction for 5-wave structure."""
    correction_df = df.loc[peak_idx:origin_idx]
    results = []

    for order in [8, 10, 12, 15]:
        swings = find_swings(correction_df, order=order)
        highs = [s for s in swings if s['type'] == 'high']
        lows = [s for s in swings if s['type'] == 'low']

        # Count alternating waves
        n_swings = len(swings)
        if n_swings >= 4:
            results.append({
                'order': order,
                'n_swings': n_swings,
                'swings': swings,
                'n_highs': len(highs),
                'n_lows': len(lows),
            })

    return results


# ═══════════════════════════════════════════════════════════════════════
# FETCH ALL DATA
# ═══════════════════════════════════════════════════════════════════════
print("Fetching data for all tickers...")

trades = {}

# ── ARM ────────────────────────────────────────────────────────────────
arm_1d = yf.Ticker("ARM").history(start='2024-04-01', end='2026-05-27', interval="1d")
arm_1wk = yf.Ticker("ARM").history(start='2024-01-01', end='2026-05-27', interval="1wk")
tz_arm = arm_1d.index.tz

trades['ARM'] = {
    'df_1d': arm_1d,
    'df_1wk': arm_1wk,
    'entry': 103.79,
    'stop': 93.00,       # estimated original stop below Wave (2)
    'sl_trail': [124.0, 130.0],
    'targets_alert': [184.0, 184.0],
    'targets_chart': [176.0, 200.0],
    'exit_price': 200.0,
    'status': 'completed',
    'timeframe': '1d',
    # Key structure points (from our analysis)
    'peak_date': '2024-07-09',
    'peak_price': 188.75,
    'origin_date': '2025-04-07',
    'origin_price': 80.00,
    'w1_top_date': '2025-10-27',
    'w1_top_price': 183.16,
    'w2_low_date': '2026-02-05',
    'w2_low_price': 100.02,
    # Chart's smaller wave (1) — .786 fib origin
    'chart_sub_origin': 93.88,
    'chart_sub_w1_top': 138.59,
}

# ── STM ────────────────────────────────────────────────────────────────
stm_1d = yf.Ticker("STM").history(start='2024-04-01', end='2026-05-27', interval="1d")
stm_1wk = yf.Ticker("STM").history(start='2024-01-01', end='2026-05-27', interval="1wk")
tz_stm = stm_1d.index.tz

trades['STM'] = {
    'df_1d': stm_1d,
    'df_1wk': stm_1wk,
    'entry': None,  # will detect from data
    'status': 'completed',
    'timeframe': '1d',
}

# Detect STM structure from data
stm_swings_wk = find_swings(stm_1wk, order=3)
# Find the peak before the correction
stm_pre = stm_1d.loc[:pd.Timestamp('2025-01-01', tz=tz_stm)]
if len(stm_pre) > 0:
    stm_peak_idx = stm_pre['High'].idxmax()
    stm_peak = stm_pre['High'].max()
else:
    stm_peak_idx = stm_1d['High'].idxmax()
    stm_peak = stm_1d['High'].max()

# Find STM correction bottom
stm_corr = stm_1d.loc[stm_peak_idx:pd.Timestamp('2025-12-01', tz=tz_stm)]
stm_origin_idx = stm_corr['Low'].idxmin()
stm_origin = stm_corr['Low'].min()

# Find STM Wave (1) top
stm_w1_window = stm_1d.loc[stm_origin_idx:pd.Timestamp('2026-03-01', tz=tz_stm)]
if len(stm_w1_window) > 0:
    stm_w1_idx = stm_w1_window['High'].idxmax()
    stm_w1 = stm_w1_window['High'].max()
else:
    stm_w1_idx = stm_origin_idx
    stm_w1 = stm_origin

# Find STM Wave (2) low
stm_w2_window = stm_1d.loc[stm_w1_idx:pd.Timestamp('2026-05-27', tz=tz_stm)]
if len(stm_w2_window) > 0:
    stm_w2_idx = stm_w2_window['Low'].idxmin()
    stm_w2 = stm_w2_window['Low'].min()
else:
    stm_w2_idx = stm_w1_idx
    stm_w2 = stm_w1

trades['STM'].update({
    'peak_date': stm_peak_idx.strftime('%Y-%m-%d'),
    'peak_price': stm_peak,
    'origin_date': stm_origin_idx.strftime('%Y-%m-%d'),
    'origin_price': stm_origin,
    'w1_top_date': stm_w1_idx.strftime('%Y-%m-%d'),
    'w1_top_price': stm_w1,
    'w2_low_date': stm_w2_idx.strftime('%Y-%m-%d'),
    'w2_low_price': stm_w2,
})

# ── ZETA ───────────────────────────────────────────────────────────────
zeta_1d = yf.Ticker("ZETA").history(start='2023-06-01', end='2026-05-27', interval="1d")
zeta_1wk = yf.Ticker("ZETA").history(start='2023-01-01', end='2026-05-27', interval="1wk")
tz_zeta = zeta_1d.index.tz

trades['ZETA'] = {
    'df_1d': zeta_1d,
    'df_1wk': zeta_1wk,
    'entry': 18.08,
    'stop': 15.00,
    'targets_alert': [25.0, 40.0],
    'status': 'active',
    'timeframe': '1d',
}

# Detect ZETA structure
zeta_pre = zeta_1d.loc[:pd.Timestamp('2025-01-01', tz=tz_zeta)]
if len(zeta_pre) > 0:
    zeta_peak_idx = zeta_pre['High'].idxmax()
    zeta_peak = zeta_pre['High'].max()
else:
    zeta_peak_idx = zeta_1d['High'].idxmax()
    zeta_peak = zeta_1d['High'].max()

# ZETA correction bottom
zeta_corr = zeta_1d.loc[zeta_peak_idx:pd.Timestamp('2026-02-01', tz=tz_zeta)]
zeta_origin_idx = zeta_corr['Low'].idxmin()
zeta_origin = zeta_corr['Low'].min()

# ZETA Wave (1) top — highest between origin and the pullback to entry
zeta_w1_window = zeta_1d.loc[zeta_origin_idx:pd.Timestamp('2026-05-01', tz=tz_zeta)]
if len(zeta_w1_window) > 0:
    zeta_w1_idx = zeta_w1_window['High'].idxmax()
    zeta_w1 = zeta_w1_window['High'].max()
else:
    zeta_w1_idx = zeta_origin_idx
    zeta_w1 = zeta_origin

# ZETA Wave (2) low — near entry at $18.08
zeta_w2_window = zeta_1d.loc[zeta_w1_idx:]
if len(zeta_w2_window) > 0:
    zeta_w2_idx = zeta_w2_window['Low'].idxmin()
    zeta_w2 = zeta_w2_window['Low'].min()
else:
    zeta_w2_idx = zeta_w1_idx
    zeta_w2 = zeta_w1

trades['ZETA'].update({
    'peak_date': zeta_peak_idx.strftime('%Y-%m-%d'),
    'peak_price': zeta_peak,
    'origin_date': zeta_origin_idx.strftime('%Y-%m-%d'),
    'origin_price': zeta_origin,
    'w1_top_date': zeta_w1_idx.strftime('%Y-%m-%d'),
    'w1_top_price': zeta_w1,
    'w2_low_date': zeta_w2_idx.strftime('%Y-%m-%d'),
    'w2_low_price': zeta_w2,
})

print(f"ARM daily: {len(arm_1d)}, STM daily: {len(stm_1d)}, ZETA daily: {len(zeta_1d)}")


# ═══════════════════════════════════════════════════════════════════════
# ANALYZE EACH TRADE
# ═══════════════════════════════════════════════════════════════════════

print("\n" + "="*90)
print("INDIVIDUAL TRADE ANALYSIS")
print("="*90)

analysis = {}

for name, t in trades.items():
    print(f"\n{'─'*90}")
    print(f"  {name}")
    print(f"{'─'*90}")

    peak = t['peak_price']
    origin = t['origin_price']
    w1_top = t['w1_top_price']
    w2_low = t['w2_low_price']
    entry = t.get('entry', w2_low)

    correction_depth = ((peak - origin) / peak) * 100
    wave1_move = w1_top - origin
    wave1_pct = (wave1_move / origin) * 100
    wave2_retrace = w1_top - w2_low
    wave2_retrace_pct = (wave2_retrace / wave1_move * 100) if wave1_move > 0 else 0

    # Fibonacci levels
    fib_levels = {
        '23.6%': w1_top - (0.236 * wave1_move),
        '38.2%': w1_top - (0.382 * wave1_move),
        '50.0%': w1_top - (0.500 * wave1_move),
        '61.8%': w1_top - (0.618 * wave1_move),
        '78.6%': w1_top - (0.786 * wave1_move),
    }
    closest_fib = min(fib_levels.items(), key=lambda x: abs(x[1] - w2_low))

    # Extension targets (full Wave 1)
    ext_full = {}
    for ratio in [1.0, 1.272, 1.618, 2.0, 2.618]:
        ext_full[ratio] = w2_low + (ratio * wave1_move)

    # Sub-wave (1) analysis — find smaller degree wave
    df_1d = t['df_1d']
    tz = df_1d.index.tz
    origin_ts = pd.Timestamp(t['origin_date'], tz=tz)
    w1_ts = pd.Timestamp(t['w1_top_date'], tz=tz)

    sub_candidates = find_sub_wave1(df_1d, origin_ts, w1_ts, origin)
    best_sub = None
    if sub_candidates:
        # Pick the sub-wave with retrace closest to 38.2-50% (cleanest sub-impulse)
        scored = []
        for sc in sub_candidates:
            # Score: prefer sub-waves where the first pullback is 30-60% retrace
            ret = sc['sub_w1_retrace_pct']
            if 25 <= ret <= 65:
                score = 100 - abs(ret - 45)  # prefer ~45% retrace
            else:
                score = 50 - abs(ret - 45)
            # Also prefer meaningful size (at least 20% of full Wave 1)
            size_ratio = sc['sub_w1_move'] / wave1_move if wave1_move > 0 else 0
            if 0.3 <= size_ratio <= 0.7:
                score += 30
            scored.append((score, sc))
        scored.sort(key=lambda x: x[0], reverse=True)
        best_sub = scored[0][1]

    ext_sub = {}
    sub_w1_move = None
    if best_sub:
        sub_w1_move = best_sub['sub_w1_move']
        for ratio in [1.0, 1.272, 1.618, 2.0, 2.618]:
            ext_sub[ratio] = (entry or w2_low) + (ratio * sub_w1_move)

    # For ARM, also compute from chart's known sub-wave
    ext_chart = {}
    if 'chart_sub_origin' in t:
        chart_move = t['chart_sub_w1_top'] - t['chart_sub_origin']
        for ratio in [1.0, 1.272, 1.618, 2.0, 2.618]:
            ext_chart[ratio] = (entry or w2_low) + (ratio * chart_move)

    # Correction duration
    peak_ts = pd.Timestamp(t['peak_date'], tz=tz)
    origin_ts_dt = pd.Timestamp(t['origin_date'], tz=tz)
    correction_days = (origin_ts_dt - peak_ts).days

    # Wave (1) duration
    w1_days = (w1_ts - origin_ts_dt).days

    # Trade outcome (if completed)
    trade_result = None
    if t.get('exit_price') and entry:
        trade_result = ((t['exit_price'] - entry) / entry) * 100

    # Print
    print(f"  Peak:           ${peak:.2f} ({t['peak_date']})")
    print(f"  Origin:         ${origin:.2f} ({t['origin_date']})")
    print(f"  Wave (1) top:   ${w1_top:.2f} ({t['w1_top_date']})")
    print(f"  Wave (2) low:   ${w2_low:.2f} ({t['w2_low_date']})")
    if entry:
        print(f"  Entry:          ${entry:.2f}")
    print()
    print(f"  Correction:     {correction_depth:.1f}% decline, {correction_days} days")
    print(f"  Wave (1):       +${wave1_move:.2f} (+{wave1_pct:.1f}%), {w1_days} days")
    print(f"  Wave (2) retrace: {wave2_retrace_pct:.1f}% → closest fib: {closest_fib[0]} (${closest_fib[1]:.2f})")
    print(f"  W2 holds > origin: {'YES' if w2_low > origin else 'NO'}")

    print(f"\n  Full W1 extensions from W2 (${w2_low:.2f}):")
    for ratio, val in ext_full.items():
        print(f"    {ratio:.3f}x: ${val:.2f}")

    if best_sub:
        print(f"\n  Sub-Wave (1) detected: ${origin:.2f} → ${best_sub['sub_w1_high']:.2f} (${best_sub['sub_w1_move']:.2f})")
        print(f"    First pullback: ${best_sub['sub_w1_pullback']:.2f} ({best_sub['sub_w1_retrace_pct']:.1f}% retrace)")
        print(f"  Sub-W1 extensions from entry (${entry or w2_low:.2f}):")
        for ratio, val in ext_sub.items():
            print(f"    {ratio:.3f}x: ${val:.2f}")

    if ext_chart:
        chart_mv = t['chart_sub_w1_top'] - t['chart_sub_origin']
        print(f"\n  Chart's sub-W1: ${t['chart_sub_origin']:.2f} → ${t['chart_sub_w1_top']:.2f} (${chart_mv:.2f})")
        print(f"  Chart extensions from entry (${entry:.2f}):")
        for ratio, val in ext_chart.items():
            print(f"    {ratio:.3f}x: ${val:.2f}")

    if trade_result is not None:
        print(f"\n  RESULT: +{trade_result:.1f}% (exited ~${t['exit_price']:.2f})")

    analysis[name] = {
        'peak': peak,
        'origin': origin,
        'w1_top': w1_top,
        'w2_low': w2_low,
        'entry': entry,
        'correction_depth': correction_depth,
        'wave1_move': wave1_move,
        'wave1_pct': wave1_pct,
        'wave1_days': w1_days,
        'correction_days': correction_days,
        'wave2_retrace_pct': wave2_retrace_pct,
        'closest_fib': closest_fib,
        'ext_full': ext_full,
        'ext_sub': ext_sub,
        'ext_chart': ext_chart,
        'sub_w1_move': sub_w1_move,
        'best_sub': best_sub,
        'trade_result': trade_result,
    }


# ═══════════════════════════════════════════════════════════════════════
# CROSS-TRADE STATISTICS
# ═══════════════════════════════════════════════════════════════════════

print("\n" + "="*90)
print("CROSS-TRADE STATISTICS")
print("="*90)

all_names = list(analysis.keys())

# Table header
print(f"\n  {'Metric':<35} ", end='')
for n in all_names:
    print(f"{'  ' + n:<15}", end='')
print()
print(f"  {'─'*35} ", end='')
for _ in all_names:
    print(f"  {'─'*13}", end='')
print()

metrics = [
    ('Correction depth (%)', 'correction_depth', '.1f'),
    ('Correction duration (days)', 'correction_days', 'd'),
    ('Wave (1) gain (%)', 'wave1_pct', '.1f'),
    ('Wave (1) duration (days)', 'wave1_days', 'd'),
    ('Wave (2) retrace (%)', 'wave2_retrace_pct', '.1f'),
    ('W2 closest Fib', None, None),  # special
]

for label, key, fmt in metrics:
    print(f"  {label:<35} ", end='')
    for n in all_names:
        if key:
            val = analysis[n][key]
            print(f"  {val:>13{fmt}}", end='')
        else:
            fib = analysis[n]['closest_fib']
            print(f"  {fib[0]:>13}", end='')
    print()

# Averages/ranges
print(f"\n  {'─'*70}")
vals = {key: [analysis[n][key] for n in all_names] for key in ['correction_depth', 'wave1_pct', 'wave2_retrace_pct', 'correction_days', 'wave1_days']}

print(f"\n  Averages across all trades:")
print(f"    Correction depth:   {np.mean(vals['correction_depth']):.1f}% (range: {min(vals['correction_depth']):.1f}–{max(vals['correction_depth']):.1f}%)")
print(f"    Wave (1) gain:      {np.mean(vals['wave1_pct']):.1f}% (range: {min(vals['wave1_pct']):.1f}–{max(vals['wave1_pct']):.1f}%)")
print(f"    Wave (2) retrace:   {np.mean(vals['wave2_retrace_pct']):.1f}% (range: {min(vals['wave2_retrace_pct']):.1f}–{max(vals['wave2_retrace_pct']):.1f}%)")
print(f"    Correction days:    {np.mean(vals['correction_days']):.0f} (range: {min(vals['correction_days'])}–{max(vals['correction_days'])})")
print(f"    Wave (1) days:      {np.mean(vals['wave1_days']):.0f} (range: {min(vals['wave1_days'])}–{max(vals['wave1_days'])})")

# ═══════════════════════════════════════════════════════════════════════
# EXTENSION TARGET ANALYSIS — Which ratio hits actual targets?
# ═══════════════════════════════════════════════════════════════════════

print("\n" + "="*90)
print("EXTENSION TARGET CALIBRATION")
print("="*90)

# ARM: actual targets were $176, $184, $200
# The chart used a sub-wave (1) of ~$44.72
# Full Wave (1) of $103.16
arm_a = analysis['ARM']
print(f"\n  ARM — Actual trade targets: $176, $184, $200")
print(f"    Full W1 (${arm_a['wave1_move']:.2f}):")
for ratio, val in arm_a['ext_full'].items():
    marker = ""
    if abs(val - 176) < 5: marker = " ← ~$176"
    if abs(val - 200) < 5: marker = " ← ~$200"
    print(f"      {ratio:.3f}x = ${val:.2f}{marker}")

if arm_a['ext_chart']:
    print(f"    Chart sub-W1:")
    for ratio, val in arm_a['ext_chart'].items():
        marker = ""
        if abs(val - 176) < 3: marker = " ← $176 TARGET"
        if abs(val - 184) < 3: marker = " ← $184 TARGET"
        if abs(val - 200) < 5: marker = " ← ~$200 TARGET"
        print(f"      {ratio:.3f}x = ${val:.2f}{marker}")

if arm_a['ext_sub']:
    print(f"    Auto-detected sub-W1 (${arm_a['sub_w1_move']:.2f}):")
    for ratio, val in arm_a['ext_sub'].items():
        marker = ""
        if abs(val - 176) < 5: marker = " ← ~$176"
        if abs(val - 200) < 8: marker = " ← ~$200"
        print(f"      {ratio:.3f}x = ${val:.2f}{marker}")

# For ARM, reverse-engineer: what extension ratio of full W1 gives the actual targets?
print(f"\n  ARM — Reverse-engineered ratios from entry ${arm_a['entry']:.2f}:")
for target in [176, 184, 200]:
    ratio_full = (target - arm_a['w2_low']) / arm_a['wave1_move'] if arm_a['wave1_move'] > 0 else 0
    print(f"    ${target} = {ratio_full:.3f}x full W1")

# ═══════════════════════════════════════════════════════════════════════
# STOP LOSS ANALYSIS
# ═══════════════════════════════════════════════════════════════════════

print("\n" + "="*90)
print("STOP LOSS ANALYSIS")
print("="*90)

for name in all_names:
    a = analysis[name]
    t = trades[name]
    entry = a['entry']
    w2_low = a['w2_low']
    origin = a['origin']

    if entry is None:
        continue

    # Stop below Wave (2)
    stop_below_w2 = w2_low * 0.95  # 5% below Wave 2
    stop_at_origin = origin  # at wave origin (invalidation)

    # Distance from entry
    risk_to_w2 = ((entry - stop_below_w2) / entry) * 100
    risk_to_origin = ((entry - stop_at_origin) / entry) * 100

    print(f"\n  {name} (entry ${entry:.2f}, W2 low ${w2_low:.2f}, origin ${origin:.2f}):")
    print(f"    Stop 5% below W2:    ${stop_below_w2:.2f} (risk: {risk_to_w2:.1f}%)")
    print(f"    Stop at wave origin:  ${stop_at_origin:.2f} (risk: {risk_to_origin:.1f}%)")

    if t.get('stop'):
        actual_stop = t['stop']
        actual_risk = ((entry - actual_stop) / entry) * 100
        print(f"    Actual trade stop:    ${actual_stop:.2f} (risk: {actual_risk:.1f}%)")

        # Where does actual stop sit relative to structure?
        if actual_stop > origin:
            pct_between = ((actual_stop - origin) / (w2_low - origin)) * 100 if (w2_low - origin) > 0 else 0
            print(f"    Stop is {pct_between:.0f}% of the way from origin to W2 low")

# ═══════════════════════════════════════════════════════════════════════
# RISK/REWARD ANALYSIS
# ═══════════════════════════════════════════════════════════════════════

print("\n" + "="*90)
print("RISK/REWARD RATIOS")
print("="*90)

for name in all_names:
    a = analysis[name]
    t = trades[name]
    entry = a['entry']
    if entry is None:
        continue

    stop = t.get('stop')
    if stop is None:
        stop = a['w2_low'] * 0.95

    risk = entry - stop
    if risk <= 0:
        continue

    print(f"\n  {name} (entry ${entry:.2f}, stop ${stop:.2f}, risk ${risk:.2f}):")

    # Full W1 extensions
    print(f"    Full W1 targets:")
    for ratio, target in a['ext_full'].items():
        reward = target - entry
        rr = reward / risk if risk > 0 else 0
        print(f"      {ratio:.3f}x = ${target:.2f}  →  R:R = 1:{rr:.1f}")

    # Sub-W1 extensions
    if a['ext_sub']:
        print(f"    Sub-W1 targets:")
        for ratio, target in a['ext_sub'].items():
            reward = target - entry
            rr = reward / risk if risk > 0 else 0
            print(f"      {ratio:.3f}x = ${target:.2f}  →  R:R = 1:{rr:.1f}")

    # Alert targets
    if t.get('targets_alert'):
        print(f"    Alert targets:")
        for target in t['targets_alert']:
            reward = target - entry
            rr = reward / risk if risk > 0 else 0
            print(f"      ${target:.2f}  →  R:R = 1:{rr:.1f}")


# ═══════════════════════════════════════════════════════════════════════
# UNIFIED STRATEGY
# ═══════════════════════════════════════════════════════════════════════

print("\n" + "="*90)
print("═══════════════════════════════════════════════════════════════════")
print("  UNIFIED ELLIOTT WAVE ENTRY STRATEGY")
print("  Based on ARM (completed +93%), STM, ZETA (active)")
print("═══════════════════════════════════════════════════════════════════")
print("="*90)

avg_corr = np.mean(vals['correction_depth'])
avg_w1 = np.mean(vals['wave1_pct'])
avg_w2_ret = np.mean(vals['wave2_retrace_pct'])
min_w2_ret = min(vals['wave2_retrace_pct'])
max_w2_ret = max(vals['wave2_retrace_pct'])

print(f"""
  ┌─────────────────────────────────────────────────────────────────┐
  │  STEP 1: IDENTIFY COMPLETED CORRECTION                         │
  ├─────────────────────────────────────────────────────────────────┤
  │  • Stock must have declined >{min(vals['correction_depth']):.0f}% from a major high        │
  │  • Observed range: {min(vals['correction_depth']):.0f}–{max(vals['correction_depth']):.0f}%, average {avg_corr:.0f}%                       │
  │  • Correction should last 100+ days (avg: {np.mean(vals['correction_days']):.0f})             │
  │  • Ideally shows a 5-wave (or A-B-C) bearish structure          │
  └─────────────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────────────┐
  │  STEP 2: CONFIRM WAVE (1) IMPULSE UP                           │
  ├─────────────────────────────────────────────────────────────────┤
  │  • Strong rally off the correction bottom                       │
  │  • Observed gains: {min(vals['wave1_pct']):.0f}–{max(vals['wave1_pct']):.0f}%, average {avg_w1:.0f}%                        │
  │  • Duration: {min(vals['wave1_days'])}–{max(vals['wave1_days'])} days (avg: {np.mean(vals['wave1_days']):.0f})                          │
  │  • Should show internal 5-wave sub-structure                    │
  │  • NOTE: Also identify the first sub-impulse within Wave (1)   │
  │    for practical target calculation (see Step 6)                │
  └─────────────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────────────┐
  │  STEP 3: WAIT FOR WAVE (2) RETRACEMENT                        │
  ├─────────────────────────────────────────────────────────────────┤
  │  • Wave (2) must retrace deeply into Wave (1)                  │
  │  • Target zone: 61.8%–78.6% Fibonacci retracement              │
  │  • Observed range: {min_w2_ret:.1f}–{max_w2_ret:.1f}%, average {avg_w2_ret:.1f}%                   │
  │  • CRITICAL: Wave (2) must HOLD ABOVE Wave (1) origin          │
  │  • If it breaks below origin, the count is invalidated          │
  └─────────────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────────────┐
  │  STEP 4: ENTRY                                                  │
  ├─────────────────────────────────────────────────────────────────┤
  │  • Enter near Wave (2) bottom (within ~5% of the low)           │
  │  • Look for reversal confirmation (bullish candle, volume)      │
  │  • ARM entered $3.77 above W2 low (3.8% above)                 │
  │  • ZETA entered $18.08 near W2 low                              │
  └─────────────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────────────┐
  │  STEP 5: STOP LOSS                                              │
  ├─────────────────────────────────────────────────────────────────┤
  │  • Initial stop: Below Wave (2) low (5-10% cushion)             │
  │  • Invalidation stop: At Wave (1) origin (full loss if broken) │
  │  • Trail stop up as price advances:                             │
  │    - Move to breakeven after +15-20%                            │
  │    - Move to below Wave (3) sub-wave (ii) after +30%           │
  │    - ARM trailed: $124 → $130 as price advanced                │
  └─────────────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────────────┐
  │  STEP 6: TARGETS (dual-extension method)                        │
  ├─────────────────────────────────────────────────────────────────┤
  │                                                                 │
  │  Calculate BOTH and use as a target range:                      │
  │                                                                 │
  │  A) Sub-Wave (1) extensions (conservative / practical):         │
  │     • Measure the FIRST clean impulse within Wave (1)           │
  │     • Or use origin at .786 Fib of bearish correction           │
  │     • Target 1: 1.618x extension from entry    (partial exit)  │
  │     • Target 2: 2.000x extension from entry    (full exit)     │
  │     ARM result: T1=$176, T2=$196 → both hit                    │
  │                                                                 │
  │  B) Full Wave (1) extensions (aggressive / maximum):            │
  │     • Use the full Wave (1) move                                │
  │     • Target 1: 0.786x extension from W2                        │
  │     • Target 2: 1.000x extension from W2                        │
  │     ARM result: 1.0x = $203 (≈ actual exit at $200)             │
  │                                                                 │
  │  In practice: exit 50% at sub-W1 1.618x, rest at full-W1 1.0x │
  └─────────────────────────────────────────────────────────────────┘
""")

# ═══════════════════════════════════════════════════════════════════════
# APPLY STRATEGY TO ZETA (active trade)
# ═══════════════════════════════════════════════════════════════════════

print("="*90)
print("APPLYING STRATEGY TO ZETA (ACTIVE TRADE)")
print("="*90)

za = analysis['ZETA']
zt = trades['ZETA']

print(f"""
  Structure:
    Peak:     ${za['peak']:.2f} ({zt['peak_date']})
    Origin:   ${za['origin']:.2f} ({zt['origin_date']})
    W1 top:   ${za['w1_top']:.2f} ({zt['w1_top_date']})
    W2 low:   ${za['w2_low']:.2f} ({zt['w2_low_date']})
    Entry:    ${zt['entry']:.2f}
    Stop:     ${zt['stop']:.2f}

  Checklist:
    1. Correction: {za['correction_depth']:.1f}% decline {'✓ PASS' if za['correction_depth'] > 30 else '? WEAK'}
    2. Wave (1):   +{za['wave1_pct']:.1f}% gain {'✓ PASS' if za['wave1_pct'] > 30 else '? CHECK'}
    3. W2 retrace: {za['wave2_retrace_pct']:.1f}% (closest: {za['closest_fib'][0]}) {'✓ PASS' if 55 <= za['wave2_retrace_pct'] <= 90 else '? CHECK'}
    4. W2 > origin: ${za['w2_low']:.2f} > ${za['origin']:.2f}? {'✓ PASS' if za['w2_low'] > za['origin'] else '✗ FAIL'}
    5. Entry near W2: ${zt['entry']:.2f} vs ${za['w2_low']:.2f} {'✓ PASS' if abs(zt['entry'] - za['w2_low']) / za['w2_low'] < 0.1 else '? CHECK'}
    6. Stop below structure: ${zt['stop']:.2f}
""")

# ZETA targets using dual method
print(f"  Full W1 targets (W1 = ${za['wave1_move']:.2f}):")
for ratio, val in za['ext_full'].items():
    reward = val - zt['entry']
    risk = zt['entry'] - zt['stop']
    rr = reward / risk if risk > 0 else 0
    alert_match = ""
    if abs(val - 25) < 2: alert_match = " ← near alert T1 ($25)"
    if abs(val - 40) < 3: alert_match = " ← near alert T2 ($40)"
    print(f"    {ratio:.3f}x: ${val:.2f}  (R:R 1:{rr:.1f}){alert_match}")

if za['ext_sub']:
    print(f"\n  Sub-W1 targets (sub-W1 = ${za['sub_w1_move']:.2f}):")
    for ratio, val in za['ext_sub'].items():
        reward = val - zt['entry']
        risk = zt['entry'] - zt['stop']
        rr = reward / risk if risk > 0 else 0
        alert_match = ""
        if abs(val - 25) < 2: alert_match = " ← near alert T1 ($25)"
        if abs(val - 40) < 3: alert_match = " ← near alert T2 ($40)"
        print(f"    {ratio:.3f}x: ${val:.2f}  (R:R 1:{rr:.1f}){alert_match}")

# Recommended ZETA plan
risk = zt['entry'] - zt['stop']
print(f"""
  ── ZETA TRADE PLAN ──
  Entry:        ${zt['entry']:.2f}
  Stop:         ${zt['stop']:.2f} (risk: ${risk:.2f}, {risk/zt['entry']*100:.1f}%)
""")

# Get current ZETA price
current_zeta = zeta_1d['Close'].iloc[-1]
current_pnl = ((current_zeta - zt['entry']) / zt['entry']) * 100
print(f"  Current:      ${current_zeta:.2f} ({current_pnl:+.1f}% from entry)")

# ═══════════════════════════════════════════════════════════════════════
# CHART — All three trades side by side (normalized)
# ═══════════════════════════════════════════════════════════════════════

print("\nGenerating unified chart...")

fig, axes = plt.subplots(3, 1, figsize=(24, 24))
fig.suptitle('Unified Elliott Wave Strategy — ARM / STM / ZETA', fontsize=18, fontweight='bold', y=0.98)

for ax_i, name in enumerate(['ARM', 'STM', 'ZETA']):
    ax = axes[ax_i]
    a = analysis[name]
    t = trades[name]
    df = t['df_1d']
    tz = df.index.tz

    # For ARM, cap at $210 to focus on the trade period
    if name == 'ARM':
        plot_end = pd.Timestamp('2026-05-01', tz=tz)
        plot_df = df.loc[:plot_end]
    else:
        plot_df = df

    ax.plot(plot_df.index, plot_df['Close'], color='#555555', linewidth=0.8, alpha=0.8)
    ax.fill_between(plot_df.index, plot_df['Low'], plot_df['High'], alpha=0.06, color='gray')

    # Wave structure line
    origin_ts = pd.Timestamp(t['origin_date'], tz=tz)
    w1_ts = pd.Timestamp(t['w1_top_date'], tz=tz)
    w2_ts = pd.Timestamp(t['w2_low_date'], tz=tz)

    wave_dates = [origin_ts, w1_ts, w2_ts]
    wave_prices = [a['origin'], a['w1_top'], a['w2_low']]
    wave_labels = ['Origin', '(1)', '(2)']

    ax.plot(wave_dates, wave_prices, color='#E65100', linewidth=2.5, alpha=0.85, zorder=5)
    for d, p, lbl in zip(wave_dates, wave_prices, wave_labels):
        offset = 14 if lbl == '(1)' else -16
        ax.annotate(lbl, (d, p), textcoords="offset points",
                   xytext=(0, offset), fontsize=11, fontweight='bold',
                   color='#E65100', ha='center', zorder=6,
                   bbox=dict(boxstyle='round,pad=0.3', facecolor='white',
                            edgecolor='#E65100', alpha=0.9))

    # Fibonacci levels
    for fib_pct, fib_val in [(0.382, a['w1_top'] - 0.382 * a['wave1_move']),
                              (0.618, a['w1_top'] - 0.618 * a['wave1_move']),
                              (0.786, a['w1_top'] - 0.786 * a['wave1_move'])]:
        ax.axhline(y=fib_val, color='orange', linestyle=':', alpha=0.25, linewidth=0.8)
        ax.annotate(f'{fib_pct:.1%}: ${fib_val:.2f}', (plot_df.index[3], fib_val),
                   fontsize=7, color='orange', alpha=0.6, va='bottom')

    # Entry / stop / targets
    entry = a['entry'] or a['w2_low']
    if t.get('entry'):
        ax.axhline(y=t['entry'], color='green', linestyle='--', alpha=0.5, linewidth=1.2)
    if t.get('stop'):
        ax.axhline(y=t['stop'], color='red', linestyle='--', alpha=0.4, linewidth=1)

    # Extension target lines
    if a['ext_sub']:
        for ratio in [1.618, 2.0]:
            if ratio in a['ext_sub']:
                val = a['ext_sub'][ratio]
                if val < plot_df['High'].max() * 1.5:
                    ax.axhline(y=val, color='#1565C0', linestyle='--', alpha=0.3, linewidth=1)
                    ax.annotate(f'Sub {ratio:.3f}x: ${val:.2f}', (plot_df.index[-1], val),
                               fontsize=7, color='#1565C0', alpha=0.7,
                               textcoords="offset points", xytext=(5, 3))

    for ratio in [1.0]:
        val = a['ext_full'][ratio]
        if val < plot_df['High'].max() * 1.5:
            ax.axhline(y=val, color='#2E7D32', linestyle=':', alpha=0.3, linewidth=1)
            ax.annotate(f'Full {ratio:.3f}x: ${val:.2f}', (plot_df.index[-1], val),
                       fontsize=7, color='#2E7D32', alpha=0.7,
                       textcoords="offset points", xytext=(5, 3))

    # Swings
    swings = find_swings(plot_df, order=10)
    for s in swings:
        color = '#2196F3' if s['type'] == 'high' else '#FF9800'
        marker = 'v' if s['type'] == 'high' else '^'
        ax.scatter(s['date'], s['price'], color=color, marker=marker, s=20, zorder=3, alpha=0.35)

    status = f"(COMPLETED +{a['trade_result']:.0f}%)" if a['trade_result'] else "(ACTIVE)" if t['status'] == 'active' else ""
    retrace_info = f"W2 retrace: {a['wave2_retrace_pct']:.1f}% ({a['closest_fib'][0]})"
    ax.set_title(f"{name} — Daily  |  {retrace_info}  |  {status}",
                fontsize=12, fontweight='bold', pad=10)
    ax.set_ylabel('Price (USD)')
    ax.grid(True, alpha=0.2)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha='right')

plt.tight_layout(rect=[0, 0, 1, 0.97])
output_path = '/Users/home/Desktop/Projects/elliot_wave/unified_strategy.png'
plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
print(f"Chart saved to: {output_path}")

print("\n" + "="*90)
print("DONE")
print("="*90)
