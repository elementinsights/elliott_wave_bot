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
# Go back 18 months for more context on the larger wave
start_date = end_date - timedelta(days=548)

df_1d = ticker.history(start=start_date, end=end_date, interval="1d")
df_1wk = ticker.history(start=start_date, end=end_date, interval="1wk")

# Also get 1h for finer resolution on the Nov 2025+ period
start_1h = datetime(2025, 10, 1)
df_1h = ticker.history(start=start_1h, end=end_date, interval="1h")

# Resample 1h to 4h
def resample_ohlcv(df, rule):
    resampled = df.resample(rule).agg({
        'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'
    }).dropna()
    return resampled

df_4h = resample_ohlcv(df_1h, '4h')

print(f"1h candles (from Oct 2025): {len(df_1h)}")
print(f"4h candles: {len(df_4h)}")
print(f"1d candles: {len(df_1d)}")
print(f"1wk candles: {len(df_1wk)}")

# ── Print price data around Nov 27, 2025 ────────────────────────────────
print("\n── Daily prices around Nov 27, 2025 ──")
nov_area = df_1d.loc['2025-11-20':'2025-12-10']
for date, row in nov_area.iterrows():
    print(f"  {date.strftime('%Y-%m-%d')}  O:{row['Open']:.2f}  H:{row['High']:.2f}  L:{row['Low']:.2f}  C:{row['Close']:.2f}")

print("\n── Weekly prices around Nov 27, 2025 ──")
nov_wk = df_1wk.loc['2025-11-01':'2025-12-31']
for date, row in nov_wk.iterrows():
    print(f"  {date.strftime('%Y-%m-%d')}  O:{row['Open']:.2f}  H:{row['High']:.2f}  L:{row['Low']:.2f}  C:{row['Close']:.2f}")

# ── Swing Detection with multiple sensitivities ─────────────────────────
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

# ── Wave Validation ─────────────────────────────────────────────────────
def validate_impulse_up(waves):
    if len(waves) < 4:
        return False
    prices = [w['price'] for w in waves]

    if len(waves) == 6:
        # Full 5-wave: low-high-low-high-low-high
        expected = ['low', 'high', 'low', 'high', 'low', 'high']
        if [w['type'] for w in waves] != expected:
            return False
        w0, w1, w2, w3, w4, w5 = prices
        if w2 <= w0: return False
        wave1, wave3, wave5 = w1-w0, w3-w2, w5-w4
        if wave3 < wave1 and wave3 < wave5: return False
        if w4 <= w1: return False
        if w5 <= w0: return False
        if w3 <= w1: return False
        return True

    elif len(waves) == 5:
        # 4 waves done (through wave 4): low-high-low-high-low
        expected = ['low', 'high', 'low', 'high', 'low']
        if [w['type'] for w in waves] != expected:
            return False
        w0, w1, w2, w3, w4 = prices
        if w2 <= w0: return False
        if w4 <= w1: return False
        if w3 <= w1: return False
        return True

    elif len(waves) == 4:
        # 3 waves done: low-high-low-high
        expected = ['low', 'high', 'low', 'high']
        if [w['type'] for w in waves] != expected:
            return False
        w0, w1, w2, w3 = prices
        if w2 <= w0: return False
        if w3 <= w1: return False
        return True

    return False

def score_wave(waves):
    prices = [w['price'] for w in waves]
    score = 0.0

    if len(waves) >= 4:
        w0, w1, w2 = prices[0], prices[1], prices[2]
        wave1 = w1 - w0
        w2_retrace = (w1 - w2) / wave1 if wave1 > 0 else 999
        if 0.382 <= w2_retrace <= 0.618: score += 30
        elif 0.236 <= w2_retrace <= 0.786: score += 15

    if len(waves) >= 4:
        wave1 = prices[1] - prices[0]
        wave3 = prices[3] - prices[2]
        if wave1 > 0:
            ratio = wave3 / wave1
            if 1.2 <= ratio <= 2.0: score += 25
            elif 0.8 <= ratio <= 2.618: score += 10
            if ratio >= 1.618: score += 10  # extended wave 3 bonus

    if len(waves) >= 6:
        wave3 = prices[3] - prices[2]
        w4_retrace = (prices[3] - prices[4]) / wave3 if wave3 > 0 else 999
        if 0.236 <= w4_retrace <= 0.5: score += 25
        elif 0.15 <= w4_retrace <= 0.618: score += 12

        wave1 = prices[1] - prices[0]
        wave5 = prices[5] - prices[4]
        if wave1 > 0:
            ratio = wave5 / wave1
            if 0.5 <= ratio <= 1.2: score += 20
            elif 0.382 <= ratio <= 1.618: score += 10

    total_move = abs(prices[-1] - prices[0])
    avg_price = np.mean(prices)
    pct_move = total_move / avg_price * 100 if avg_price > 0 else 0
    score += min(pct_move * 2, 30)

    # Bonus for completeness
    score += len(waves) * 5

    return score

# ── Search for waves starting near Nov 27, 2025 ─────────────────────────
def find_waves_from_date(df, tf_label, target_date, swing_orders, date_tolerance_days=10):
    """Search for Elliott Wave patterns starting near target_date."""
    results = []

    for order in swing_orders:
        swings = find_swings(df, order=order)

        # Find swings near the target date
        for i, s in enumerate(swings):
            days_diff = abs((s['date'] - pd.Timestamp(target_date, tz=s['date'].tz if s['date'].tz else None)).total_seconds()) / 86400
            if days_diff > date_tolerance_days:
                continue
            if s['type'] != 'low':
                continue

            # Try to build wave forward from this swing low
            remaining = swings[i:]

            # Check for 4, 5, or 6 point waves
            for wave_len in [6, 5, 4]:
                if len(remaining) < wave_len:
                    continue
                candidate = remaining[:wave_len]
                if validate_impulse_up(candidate):
                    sc = score_wave(candidate)
                    results.append({
                        'timeframe': tf_label,
                        'swing_order': order,
                        'waves': candidate,
                        'wave_count': wave_len - 1,
                        'score': sc,
                    })

            # Also try skipping some intermediate swings for larger-degree waves
            lows = [s for s in remaining if s['type'] == 'low']
            highs = [s for s in remaining if s['type'] == 'high']

            for n_low in range(min(4, len(lows))):
                for combo_h in range(min(len(highs), 5)):
                    for combo_h2 in range(combo_h+1, min(len(highs), 6)):
                        # Build: low[0], high[combo_h], low[n_low+1], high[combo_h2], ...
                        pass  # too combinatorial, stick with consecutive swings

    # Deduplicate
    seen = set()
    unique = []
    for r in results:
        key = (r['timeframe'], r['wave_count'], tuple(w['idx'] for w in r['waves']))
        if key not in seen:
            seen.add(key)
            unique.append(r)

    unique.sort(key=lambda x: x['score'], reverse=True)
    return unique

target = datetime(2025, 11, 27)

print("\n" + "="*80)
print(f"SEARCHING FOR ELLIOTT WAVE STARTING NEAR {target.strftime('%Y-%m-%d')}")
print("="*80)

all_results = []

configs = [
    ('1h', df_1h, [6, 8, 10, 12, 15, 20, 30, 40]),
    ('4h', df_4h, [4, 5, 6, 8, 10, 12, 15]),
    ('1d', df_1d, [3, 4, 5, 6, 8, 10, 12, 15, 20]),
    ('1wk', df_1wk, [2, 3, 4, 5, 6]),
]

for tf_label, df_tf, orders in configs:
    print(f"\n── {tf_label} timeframe ──")
    results = find_waves_from_date(df_tf, tf_label, target, orders, date_tolerance_days=14)
    all_results.extend(results)

    if not results:
        print("  No waves found starting near this date")
    else:
        for r in results[:5]:
            waves = r['waves']
            print(f"\n  Wave ({r['wave_count']} waves done, swing_order={r['swing_order']}, score={r['score']:.1f})")
            labels = ['0', '1', '2', '3', '4', '5']
            for j, w in enumerate(waves):
                print(f"    Wave {labels[j]}: {w['date'].strftime('%Y-%m-%d %H:%M')}  ${w['price']:.2f} ({w['type']})")
            w0 = waves[0]['price']
            wlast = waves[-1]['price']
            pct = (wlast - w0) / w0 * 100
            print(f"    Move so far: ${w0:.2f} → ${wlast:.2f} ({pct:+.1f}%)")

            if len(waves) >= 4:
                wave1 = waves[1]['price'] - waves[0]['price']
                w2_ret = (waves[1]['price'] - waves[2]['price']) / wave1 * 100 if wave1 > 0 else 0
                wave3 = waves[3]['price'] - waves[2]['price']
                w3_ratio = wave3 / wave1 if wave1 > 0 else 0
                print(f"    W2 retracement: {w2_ret:.1f}%  |  W3/W1 ratio: {w3_ratio:.2f}x")
            if len(waves) >= 6:
                w4_ret = (waves[3]['price'] - waves[4]['price']) / (waves[3]['price'] - waves[2]['price']) * 100
                wave5 = waves[5]['price'] - waves[4]['price']
                w5_ratio = wave5 / wave1 if wave1 > 0 else 0
                print(f"    W4 retracement: {w4_ret:.1f}%  |  W5/W1 ratio: {w5_ratio:.2f}x")

# ── Also just show all swing points from Nov 2025 onward for manual review ──
print("\n" + "="*80)
print("ALL SWING POINTS FROM NOV 2025 (for manual review)")
print("="*80)

for tf_label, df_tf, default_order in [('1d', df_1d, 5), ('1wk', df_1wk, 3)]:
    for order in [default_order, default_order + 2, default_order + 4]:
        swings = find_swings(df_tf, order=order)
        nov_swings = [s for s in swings if s['date'] >= pd.Timestamp('2025-11-01', tz=swings[0]['date'].tz if swings[0]['date'].tz else None)]
        print(f"\n  {tf_label} (swing_order={order}): {len(nov_swings)} swings from Nov 2025")
        for s in nov_swings:
            print(f"    {s['date'].strftime('%Y-%m-%d')}  ${s['price']:.2f}  {s['type']}")

# ── Chart the best candidates ───────────────────────────────────────────
print("\n\nGenerating charts...")

fig, axes = plt.subplots(4, 1, figsize=(22, 30))
fig.suptitle('STM — Elliott Wave Search from ~Nov 27, 2025', fontsize=16, fontweight='bold', y=0.98)

for ax_i, (tf_label, df_tf, orders) in enumerate(configs):
    ax = axes[ax_i]

    # Only show data from Oct 2025 onward for clarity
    if tf_label == '1wk':
        plot_df = df_tf.loc['2025-06-01':]
    else:
        plot_df = df_tf.loc['2025-10-01':]

    ax.plot(plot_df.index, plot_df['Close'], color='#555555', linewidth=0.8, alpha=0.7)

    # Plot all swings for this timeframe
    best_order = orders[len(orders)//2]
    swings = find_swings(df_tf, order=best_order)
    for s in swings:
        if s['date'] >= plot_df.index[0]:
            color = '#2196F3' if s['type'] == 'high' else '#FF9800'
            marker = 'v' if s['type'] == 'high' else '^'
            ax.scatter(s['date'], s['price'], color=color, marker=marker, s=25, zorder=3, alpha=0.4)

    # Mark Nov 27 with a vertical line
    target_ts = pd.Timestamp('2025-11-27', tz=plot_df.index.tz)
    ax.axvline(x=target_ts, color='purple', linestyle='--', alpha=0.5, linewidth=1.5)
    ax.annotate('Nov 27', (target_ts, ax.get_ylim()[1] if ax.get_ylim()[1] > 0 else 30),
               fontsize=8, color='purple', ha='center', va='bottom')

    # Overlay best wave patterns for this timeframe
    tf_results = [r for r in all_results if r['timeframe'] == tf_label]
    colors = ['#2E7D32', '#1565C0', '#E65100', '#6A1B9A']
    for pi, r in enumerate(tf_results[:4]):
        waves = r['waves']
        dates = [w['date'] for w in waves]
        prices = [w['price'] for w in waves]
        c = colors[pi % len(colors)]

        ax.plot(dates, prices, color=c, linewidth=2.5, alpha=0.85, zorder=5)
        labels = ['0', '1', '2', '3', '4', '5']
        for j, (d, p) in enumerate(zip(dates, prices)):
            offset = 10 if waves[j]['type'] == 'high' else -14
            ax.annotate(labels[j], (d, p), textcoords="offset points",
                       xytext=(0, offset), fontsize=10, fontweight='bold',
                       color=c, ha='center', zorder=6,
                       bbox=dict(boxstyle='round,pad=0.2', facecolor='white',
                                edgecolor=c, alpha=0.85))

        dir_label = f"score:{r['score']:.0f}, order:{r['swing_order']}"
        ax.annotate(dir_label, (dates[len(dates)//2], prices[len(prices)//2]),
                   textcoords="offset points", xytext=(50, 15),
                   fontsize=7, color=c, alpha=0.8,
                   arrowprops=dict(arrowstyle='->', color=c, alpha=0.4))

    n_found = len(tf_results)
    ax.set_title(f"STM — {tf_label}   |   {n_found} candidate wave(s) from ~Nov 27",
                fontsize=11, fontweight='bold', pad=10)
    ax.set_ylabel('Price (USD)', fontsize=9)
    ax.grid(True, alpha=0.2)
    ax.tick_params(axis='both', labelsize=8)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha='right')

plt.tight_layout(rect=[0, 0, 1, 0.97])
output_path = '/Users/home/Desktop/Projects/stm_elliott_nov27.png'
plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
print(f"Chart saved to: {output_path}")
