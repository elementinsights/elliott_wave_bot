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

# ── Fetch Data ──────────────────────────────────────────────────────────
print("Fetching STM data...")
ticker = yf.Ticker("STM")

end_date = datetime.now()
start_date = end_date - timedelta(days=365)

# 1h data (yfinance supports up to 730 days for 1h)
df_1h = ticker.history(start=start_date, end=end_date, interval="1h")
print(f"1h candles: {len(df_1h)}")

# Daily data
df_1d = ticker.history(start=start_date, end=end_date, interval="1d")
print(f"1d candles: {len(df_1d)}")

# Resample 1h to 4h and 12h
def resample_ohlcv(df, rule):
    resampled = df.resample(rule).agg({
        'Open': 'first',
        'High': 'max',
        'Low': 'min',
        'Close': 'last',
        'Volume': 'sum'
    }).dropna()
    return resampled

df_4h = resample_ohlcv(df_1h, '4h')
df_12h = resample_ohlcv(df_1h, '12h')
print(f"4h candles: {len(df_4h)}")
print(f"12h candles: {len(df_12h)}")

# ── Swing Detection ─────────────────────────────────────────────────────
def find_swings(df, order=5):
    """Find swing highs and lows using local extrema detection."""
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

    # Remove consecutive same-type swings (keep the most extreme)
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

# ── Elliott Wave Detection ──────────────────────────────────────────────
def validate_impulse_up(waves):
    """Check if 5 points form a valid bullish impulse wave (5-wave up)."""
    # waves = [w0(low), w1(high), w2(low), w3(high), w4(low), w5(high)]
    if len(waves) != 6:
        return False
    w0, w1, w2, w3, w4, w5 = [w['price'] for w in waves]

    # Basic structure: alternating low-high-low-high-low-high
    expected_types = ['low', 'high', 'low', 'high', 'low', 'high']
    if [w['type'] for w in waves] != expected_types:
        return False

    # Rule 1: Wave 2 never retraces beyond start of Wave 1
    if w2 <= w0:
        return False

    # Rule 2: Wave 3 is never the shortest impulse wave
    wave1_len = w1 - w0
    wave3_len = w3 - w2
    wave5_len = w5 - w4
    if wave3_len < wave1_len and wave3_len < wave5_len:
        return False

    # Rule 3: Wave 4 does not overlap Wave 1 territory
    if w4 <= w1:
        return False

    # Overall uptrend
    if w5 <= w0:
        return False

    # Waves should make progress
    if w3 <= w1:
        return False

    return True

def validate_impulse_down(waves):
    """Check if 5 points form a valid bearish impulse wave (5-wave down)."""
    if len(waves) != 6:
        return False
    w0, w1, w2, w3, w4, w5 = [w['price'] for w in waves]

    expected_types = ['high', 'low', 'high', 'low', 'high', 'low']
    if [w['type'] for w in waves] != expected_types:
        return False

    if w2 >= w0:
        return False

    wave1_len = w0 - w1
    wave3_len = w2 - w3
    wave5_len = w4 - w5
    if wave3_len < wave1_len and wave3_len < wave5_len:
        return False

    if w4 >= w1:
        return False

    if w5 >= w0:
        return False

    if w3 >= w1:
        return False

    return True

def score_wave(waves, direction='up'):
    """Score a wave pattern — higher is better. Considers Fibonacci ratios and proportionality."""
    if direction == 'up':
        w0, w1, w2, w3, w4, w5 = [w['price'] for w in waves]
        wave1 = w1 - w0
        wave2_retrace = (w1 - w2) / wave1 if wave1 != 0 else 999
        wave3 = w3 - w2
        wave4_retrace = (w3 - w4) / wave3 if wave3 != 0 else 999
        wave5 = w5 - w4
    else:
        w0, w1, w2, w3, w4, w5 = [w['price'] for w in waves]
        wave1 = w0 - w1
        wave2_retrace = (w2 - w1) / wave1 if wave1 != 0 else 999
        wave3 = w2 - w3
        wave4_retrace = (w4 - w3) / wave3 if wave3 != 0 else 999
        wave5 = w4 - w5

    score = 0.0

    # Fibonacci scoring for Wave 2 retracement (ideal: 0.382-0.618)
    if 0.382 <= wave2_retrace <= 0.618:
        score += 30
    elif 0.236 <= wave2_retrace <= 0.786:
        score += 15

    # Fibonacci scoring for Wave 4 retracement (ideal: 0.236-0.5)
    if 0.236 <= wave4_retrace <= 0.5:
        score += 25
    elif 0.15 <= wave4_retrace <= 0.618:
        score += 12

    # Wave 3 should ideally be 1.618x Wave 1
    if wave1 > 0:
        w3_ratio = wave3 / wave1
        if 1.2 <= w3_ratio <= 2.0:
            score += 25
        elif 0.8 <= w3_ratio <= 2.618:
            score += 10

    # Wave 5 relationship to Wave 1 (often equal or 0.618x)
    if wave1 > 0:
        w5_ratio = wave5 / wave1
        if 0.5 <= w5_ratio <= 1.2:
            score += 20
        elif 0.382 <= w5_ratio <= 1.618:
            score += 10

    # Time span — prefer waves that cover meaningful price action
    total_move = abs(waves[-1]['price'] - waves[0]['price'])
    avg_price = np.mean([w['price'] for w in waves])
    pct_move = total_move / avg_price * 100 if avg_price > 0 else 0
    score += min(pct_move * 2, 20)

    return score

def detect_elliott_waves(swings, min_waves=6):
    """Scan swings for valid Elliott Wave impulse patterns."""
    patterns = []

    for i in range(len(swings) - 5):
        candidate = swings[i:i+6]

        if validate_impulse_up(candidate):
            s = score_wave(candidate, 'up')
            patterns.append({'waves': candidate, 'direction': 'up', 'score': s})

        if validate_impulse_down(candidate):
            s = score_wave(candidate, 'down')
            patterns.append({'waves': candidate, 'direction': 'down', 'score': s})

    # Remove heavily overlapping patterns, keep highest scored
    patterns.sort(key=lambda x: x['score'], reverse=True)
    filtered = []
    used_indices = set()
    for p in patterns:
        indices = set(w['idx'] for w in p['waves'])
        overlap = indices & used_indices
        if len(overlap) <= 1:
            filtered.append(p)
            used_indices |= indices

    return filtered

# ── Charting ────────────────────────────────────────────────────────────
def plot_timeframe(df, timeframe_label, swings, patterns, ax):
    """Plot price data with Elliott Wave overlays."""
    ax.plot(df.index, df['Close'], color='#555555', linewidth=0.8, alpha=0.7, label='Close')

    # Plot swing points
    for s in swings:
        color = '#2196F3' if s['type'] == 'high' else '#FF9800'
        marker = 'v' if s['type'] == 'high' else '^'
        ax.scatter(s['date'], s['price'], color=color, marker=marker, s=30, zorder=3, alpha=0.5)

    colors_up = ['#4CAF50', '#66BB6A', '#81C784', '#A5D6A7', '#C8E6C9']
    colors_down = ['#F44336', '#EF5350', '#E57373', '#EF9A9A', '#FFCDD2']

    pattern_count = {'up': 0, 'down': 0}

    for pi, p in enumerate(patterns):
        waves = p['waves']
        direction = p['direction']
        score = p['score']

        dates = [w['date'] for w in waves]
        prices = [w['price'] for w in waves]

        color = '#2E7D32' if direction == 'up' else '#C62828'
        ax.plot(dates, prices, color=color, linewidth=2.5, alpha=0.85, zorder=5)

        labels = ['0', '1', '2', '3', '4', '5']
        for j, (d, pr) in enumerate(zip(dates, prices)):
            offset = 8 if waves[j]['type'] == 'high' else -12
            ax.annotate(labels[j], (d, pr), textcoords="offset points",
                       xytext=(0, offset), fontsize=9, fontweight='bold',
                       color=color, ha='center', zorder=6,
                       bbox=dict(boxstyle='round,pad=0.2', facecolor='white',
                                edgecolor=color, alpha=0.85))

        pattern_count[direction] += 1

        # Annotation with score
        mid_idx = 3
        dir_label = "▲ Bull" if direction == 'up' else "▼ Bear"
        ax.annotate(f"{dir_label} (score: {score:.0f})",
                   (dates[mid_idx], prices[mid_idx]),
                   textcoords="offset points", xytext=(40, 20 if direction == 'up' else -25),
                   fontsize=7.5, color=color, alpha=0.9,
                   arrowprops=dict(arrowstyle='->', color=color, alpha=0.5))

    ax.set_title(f"STM — {timeframe_label}   |   Found: {pattern_count['up']} bullish, {pattern_count['down']} bearish impulse waves",
                fontsize=11, fontweight='bold', pad=10)
    ax.set_ylabel('Price (USD)', fontsize=9)
    ax.grid(True, alpha=0.2)
    ax.tick_params(axis='both', labelsize=8)

    if len(df) > 100:
        ax.xaxis.set_major_locator(mdates.MonthLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
    else:
        ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))

    plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha='right')

# ── Run Analysis ────────────────────────────────────────────────────────
timeframes = {
    '1h': (df_1h, 8),
    '4h': (df_4h, 6),
    '12h': (df_12h, 4),
    '1d': (df_1d, 4),
}

fig, axes = plt.subplots(4, 1, figsize=(20, 28))
fig.suptitle('STM — Elliott Wave Detection (Past 12 Months)', fontsize=16, fontweight='bold', y=0.98)

results_summary = []

for i, (tf_label, (df_tf, swing_order)) in enumerate(timeframes.items()):
    print(f"\n{'='*60}")
    print(f"Analyzing {tf_label} timeframe ({len(df_tf)} candles, swing order={swing_order})...")

    swings = find_swings(df_tf, order=swing_order)
    print(f"  Swing points found: {len(swings)}")

    patterns = detect_elliott_waves(swings)
    print(f"  Elliott Wave patterns found: {len(patterns)}")

    for pi, p in enumerate(patterns):
        waves = p['waves']
        direction = p['direction']
        score = p['score']
        start_date = waves[0]['date'].strftime('%Y-%m-%d')
        end_date = waves[-1]['date'].strftime('%Y-%m-%d')
        start_price = waves[0]['price']
        end_price = waves[-1]['price']
        pct_change = ((end_price - start_price) / start_price) * 100

        w_prices = [w['price'] for w in waves]
        wave1 = abs(w_prices[1] - w_prices[0])
        wave3 = abs(w_prices[3] - w_prices[2])
        wave5 = abs(w_prices[5] - w_prices[4])
        w2_retrace = abs(w_prices[1] - w_prices[2]) / wave1 * 100 if wave1 > 0 else 0
        w4_retrace = abs(w_prices[3] - w_prices[4]) / wave3 * 100 if wave3 > 0 else 0
        w3_ratio = wave3 / wave1 if wave1 > 0 else 0

        print(f"\n  Pattern {pi+1}: {'BULLISH' if direction == 'up' else 'BEARISH'} impulse (score: {score:.1f})")
        print(f"    Period: {start_date} → {end_date}")
        print(f"    Price: ${start_price:.2f} → ${end_price:.2f} ({pct_change:+.1f}%)")
        print(f"    Wave 2 retracement: {w2_retrace:.1f}%")
        print(f"    Wave 3/Wave 1 ratio: {w3_ratio:.2f}x")
        print(f"    Wave 4 retracement: {w4_retrace:.1f}%")

        results_summary.append({
            'timeframe': tf_label,
            'direction': direction,
            'score': score,
            'start': start_date,
            'end': end_date,
            'pct_change': pct_change,
            'w2_retrace': w2_retrace,
            'w3_w1_ratio': w3_ratio,
            'w4_retrace': w4_retrace,
        })

    plot_timeframe(df_tf, tf_label, swings, patterns, axes[i])

plt.tight_layout(rect=[0, 0, 1, 0.97])
output_path = '/Users/home/Desktop/Projects/stm_elliott_waves.png'
plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
print(f"\n\nChart saved to: {output_path}")

# Summary table
print(f"\n{'='*80}")
print(f"SUMMARY: {len(results_summary)} total Elliott Wave impulse patterns detected across all timeframes")
print(f"{'='*80}")
print(f"{'TF':<6} {'Dir':<8} {'Score':<8} {'Period':<25} {'Move':<10} {'W2 Ret':<10} {'W3/W1':<8} {'W4 Ret':<10}")
print(f"{'-'*85}")
for r in sorted(results_summary, key=lambda x: x['score'], reverse=True):
    print(f"{r['timeframe']:<6} {r['direction']:<8} {r['score']:<8.1f} {r['start']} → {r['end']}  {r['pct_change']:>+6.1f}%   {r['w2_retrace']:>5.1f}%    {r['w3_w1_ratio']:>5.2f}x   {r['w4_retrace']:>5.1f}%")
