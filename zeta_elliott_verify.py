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
print("Fetching ZETA data...")
ticker = yf.Ticker("ZETA")

# Pull 3 years of weekly data for full cycle context
end_date = datetime.now()
start_date = end_date - timedelta(days=1095)

df_1wk = ticker.history(start=start_date, end=end_date, interval="1wk")
df_1d = ticker.history(start=start_date, end=end_date, interval="1d")

# Also get more recent 1h data for finer detail around entry
start_1h = datetime(2025, 10, 1)
df_1h = ticker.history(start=start_1h, end=end_date, interval="1h")

print(f"Weekly candles: {len(df_1wk)}")
print(f"Daily candles: {len(df_1d)}")
print(f"1h candles (from Oct 2025): {len(df_1h)}")

# ── Print key price levels ──────────────────────────────────────────────
print("\n" + "="*80)
print("ZETA PRICE HISTORY — KEY LEVELS")
print("="*80)

# Find the all-time high and major lows
print(f"\nAll-time high in dataset: ${df_1wk['High'].max():.2f} on {df_1wk['High'].idxmax().strftime('%Y-%m-%d')}")
print(f"All-time low in dataset:  ${df_1wk['Low'].min():.2f} on {df_1wk['Low'].idxmin().strftime('%Y-%m-%d')}")
print(f"Current price:            ${df_1wk['Close'].iloc[-1]:.2f}")

# ── Weekly swing analysis ───────────────────────────────────────────────
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

print("\n── Weekly Swing Points (various orders) ──")
for order in [2, 3, 4, 5, 6, 8]:
    swings = find_swings(df_1wk, order=order)
    print(f"\n  Swing order={order}: {len(swings)} points")
    for s in swings:
        print(f"    {s['date'].strftime('%Y-%m-%d')}  ${s['price']:.2f}  {s['type']}")

# ── Daily data around May 5, 2026 entry ────────────────────────────────
print("\n── Daily prices around May 5, 2026 ──")
may_area = df_1d.loc['2026-04-20':'2026-05-15']
for date, row in may_area.iterrows():
    print(f"  {date.strftime('%Y-%m-%d')}  O:{row['Open']:.2f}  H:{row['High']:.2f}  L:{row['Low']:.2f}  C:{row['Close']:.2f}")

# ── Fibonacci Analysis ──────────────────────────────────────────────────
print("\n" + "="*80)
print("FIBONACCI RETRACEMENT ANALYSIS")
print("="*80)

# We need to identify:
# 1. The major low (potential wave origin or wave (4) of larger degree)
# 2. Wave (1) high
# 3. Wave (2) low — should be near $18.08 entry on May 5

# Let's look at the data from the last 2 years to find the structure
print("\n── Weekly prices (last 2 years summary) ──")
recent = df_1wk.loc['2024-01-01':]
for date, row in recent.iterrows():
    print(f"  {date.strftime('%Y-%m-%d')}  O:{row['Open']:.2f}  H:{row['High']:.2f}  L:{row['Low']:.2f}  C:{row['Close']:.2f}")

# Find potential wave structure
# Look for major swing low before the entry
daily_recent = df_1d.loc['2024-06-01':]
swings_daily = find_swings(daily_recent, order=15)
print("\n── Major Daily Swings (order=15) from Jun 2024 ──")
for s in swings_daily:
    print(f"  {s['date'].strftime('%Y-%m-%d')}  ${s['price']:.2f}  {s['type']}")

swings_daily_10 = find_swings(daily_recent, order=10)
print("\n── Major Daily Swings (order=10) from Jun 2024 ──")
for s in swings_daily_10:
    print(f"  {s['date'].strftime('%Y-%m-%d')}  ${s['price']:.2f}  {s['type']}")

# Now let's try to identify the Elliott Wave structure
print("\n" + "="*80)
print("ELLIOTT WAVE STRUCTURE ANALYSIS")
print("="*80)

# From the swings, try to identify the wave (1) and wave (2)
# The entry at $18.08 on May 5 should be near a Wave (2) bottom

# Let's check multiple interpretations
for order in [3, 4, 5]:
    swings_wk = find_swings(df_1wk, order=order)

    # Find the swing low closest to $18 and May 2026
    for i, s in enumerate(swings_wk):
        if s['type'] == 'low' and s['price'] < 20 and s['date'] > pd.Timestamp('2026-03-01', tz=s['date'].tz if s['date'].tz else None):
            # This could be wave (2)
            # Look backward for wave (1) high and wave origin
            preceding = swings_wk[:i+1]

            # Find the nearest high before this low = wave (1) candidate
            for j in range(len(preceding)-1, -1, -1):
                if preceding[j]['type'] == 'high':
                    wave1_high = preceding[j]
                    # Find the low before that = wave origin
                    for k in range(j-1, -1, -1):
                        if preceding[k]['type'] == 'low':
                            wave_origin = preceding[k]

                            wave1_move = wave1_high['price'] - wave_origin['price']
                            wave2_retrace = wave1_high['price'] - s['price']
                            retrace_pct = (wave2_retrace / wave1_move * 100) if wave1_move > 0 else 0

                            # Check Fibonacci levels
                            fib_382 = wave1_high['price'] - (0.382 * wave1_move)
                            fib_500 = wave1_high['price'] - (0.500 * wave1_move)
                            fib_618 = wave1_high['price'] - (0.618 * wave1_move)
                            fib_786 = wave1_high['price'] - (0.786 * wave1_move)

                            # Wave (3) targets
                            w3_1618 = s['price'] + (1.618 * wave1_move)
                            w3_2618 = s['price'] + (2.618 * wave1_move)

                            print(f"\n  [Weekly order={order}] Candidate wave structure:")
                            print(f"    Wave origin: {wave_origin['date'].strftime('%Y-%m-%d')} ${wave_origin['price']:.2f}")
                            print(f"    Wave (1) top: {wave1_high['date'].strftime('%Y-%m-%d')} ${wave1_high['price']:.2f}")
                            print(f"    Wave (2) low: {s['date'].strftime('%Y-%m-%d')} ${s['price']:.2f}")
                            print(f"    Wave (1) size: ${wave1_move:.2f}")
                            print(f"    Wave (2) retracement: {retrace_pct:.1f}%")
                            print(f"    Fib levels: 38.2%=${fib_382:.2f}  50%=${fib_500:.2f}  61.8%=${fib_618:.2f}  78.6%=${fib_786:.2f}")
                            print(f"    Wave (2) holds above origin? {'YES' if s['price'] > wave_origin['price'] else 'NO'}")
                            print(f"    Entry $18.08 vs Wave (2) low ${s['price']:.2f}")
                            print(f"    Stop $15.00 vs Wave origin ${wave_origin['price']:.2f}")
                            print(f"    Wave (3) target 1.618x: ${w3_1618:.2f}")
                            print(f"    Wave (3) target 2.618x: ${w3_2618:.2f}")

                            # Check if targets match the trade alert ($25, $40)
                            print(f"    Trade targets: $25, $40")
                            print(f"    $25 target ≈ {((25 - s['price']) / wave1_move):.3f}x Wave(1) from Wave(2)")
                            print(f"    $40 target ≈ {((40 - s['price']) / wave1_move):.3f}x Wave(1) from Wave(2)")

                            break
                    break

# ── Check the stop at $15 ───────────────────────────────────────────────
print("\n" + "="*80)
print("STOP LOSS ANALYSIS — $15.00")
print("="*80)

# Find what $15 corresponds to structurally
lows_below_18 = df_1d[df_1d['Low'] < 18].sort_values('Low')
print("\nDays with lows below $18:")
for date, row in lows_below_18.head(20).iterrows():
    print(f"  {date.strftime('%Y-%m-%d')}  Low: ${row['Low']:.2f}")

# What's at $15?
lows_near_15 = df_1d[(df_1d['Low'] >= 14) & (df_1d['Low'] <= 16)].sort_values('Low')
print(f"\nDays with lows near $15:")
for date, row in lows_near_15.head(10).iterrows():
    print(f"  {date.strftime('%Y-%m-%d')}  Low: ${row['Low']:.2f}")

# ── Chart ───────────────────────────────────────────────────────────────
print("\nGenerating chart...")

fig, axes = plt.subplots(2, 1, figsize=(22, 16))
fig.suptitle('ZETA — Elliott Wave Entry Analysis (May 5, 2026)', fontsize=16, fontweight='bold', y=0.98)

# Weekly chart
ax = axes[0]
ax.plot(df_1wk.index, df_1wk['Close'], color='#555555', linewidth=1, alpha=0.8)
ax.fill_between(df_1wk.index, df_1wk['Low'], df_1wk['High'], alpha=0.1, color='gray')

# Mark entry point
entry_date = pd.Timestamp('2026-05-05', tz=df_1wk.index.tz)
ax.axhline(y=18.08, color='green', linestyle='--', alpha=0.5, linewidth=1)
ax.axhline(y=15.00, color='red', linestyle='--', alpha=0.5, linewidth=1)
ax.axhline(y=25.00, color='blue', linestyle='--', alpha=0.3, linewidth=1)
ax.axhline(y=40.00, color='blue', linestyle='--', alpha=0.3, linewidth=1)

ax.annotate('Entry $18.08', (entry_date, 18.08), textcoords="offset points",
           xytext=(10, 10), fontsize=9, color='green', fontweight='bold')
ax.annotate('Stop $15.00', (entry_date, 15.00), textcoords="offset points",
           xytext=(10, -15), fontsize=9, color='red', fontweight='bold')
ax.annotate('Target 1: $25', (entry_date, 25.00), textcoords="offset points",
           xytext=(10, 5), fontsize=8, color='blue')
ax.annotate('Target 2: $40', (entry_date, 40.00), textcoords="offset points",
           xytext=(10, 5), fontsize=8, color='blue')

# Plot swings
swings_wk = find_swings(df_1wk, order=3)
for s in swings_wk:
    color = '#2196F3' if s['type'] == 'high' else '#FF9800'
    marker = 'v' if s['type'] == 'high' else '^'
    ax.scatter(s['date'], s['price'], color=color, marker=marker, s=40, zorder=3, alpha=0.6)

ax.set_title('ZETA — Weekly', fontsize=12, fontweight='bold')
ax.set_ylabel('Price (USD)')
ax.grid(True, alpha=0.2)
ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha='right')

# Daily chart — zoomed to last 12 months
ax2 = axes[1]
df_1d_recent = df_1d.loc['2025-06-01':]
ax2.plot(df_1d_recent.index, df_1d_recent['Close'], color='#555555', linewidth=0.8, alpha=0.8)

ax2.axhline(y=18.08, color='green', linestyle='--', alpha=0.5, linewidth=1)
ax2.axhline(y=15.00, color='red', linestyle='--', alpha=0.5, linewidth=1)
ax2.axhline(y=25.00, color='blue', linestyle='--', alpha=0.3, linewidth=1)
ax2.axhline(y=40.00, color='blue', linestyle='--', alpha=0.3, linewidth=1)

entry_date_d = pd.Timestamp('2026-05-05', tz=df_1d_recent.index.tz)
ax2.axvline(x=entry_date_d, color='green', linestyle=':', alpha=0.5)
ax2.annotate('Entry May 5', (entry_date_d, 18.08), textcoords="offset points",
            xytext=(10, 10), fontsize=9, color='green', fontweight='bold')

swings_d = find_swings(df_1d_recent, order=8)
for s in swings_d:
    color = '#2196F3' if s['type'] == 'high' else '#FF9800'
    marker = 'v' if s['type'] == 'high' else '^'
    ax2.scatter(s['date'], s['price'], color=color, marker=marker, s=30, zorder=3, alpha=0.5)

ax2.set_title('ZETA — Daily (Last 12 Months)', fontsize=12, fontweight='bold')
ax2.set_ylabel('Price (USD)')
ax2.grid(True, alpha=0.2)
ax2.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
plt.setp(ax2.xaxis.get_majorticklabels(), rotation=30, ha='right')

plt.tight_layout(rect=[0, 0, 1, 0.97])
output_path = '/Users/home/Desktop/Projects/zeta_elliott_analysis.png'
plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
print(f"Chart saved to: {output_path}")

# ── Final Summary ───────────────────────────────────────────────────────
print("\n" + "="*80)
print("COMPARISON TO STM TRADE LOGIC")
print("="*80)
print("""
STM Entry Logic:
  1. Completed bear market / corrective wave done           → Check ZETA
  2. Confirmed Wave (1) impulse up                          → Check ZETA
  3. Wave (2) retraces to deep Fibonacci (61.8%-78.6%)      → Check ZETA
  4. Wave (2) holds above Wave (1) origin                   → Check ZETA
  5. Entry near Wave (2) bottom                             → $18.08
  6. Stop below Wave (2) with structure-based level          → $15.00
  7. Targets at Wave (3) and Wave (5) Fibonacci extensions  → $25, $40
""")
