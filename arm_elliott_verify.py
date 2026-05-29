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
print("Fetching ARM data...")
ticker = yf.Ticker("ARM")

end_date = datetime(2026, 5, 27)
start_date = end_date - timedelta(days=730)

df_1d = ticker.history(start=start_date, end=end_date, interval="1d")
df_1wk = ticker.history(start=start_date, end=end_date, interval="1wk")

print(f"Daily candles: {len(df_1d)}")
print(f"Weekly candles: {len(df_1wk)}")

# ── Trade parameters ───────────────────────────────────────────────────
ENTRY = 103.79
SL_INITIAL = 124.00
SL_ADJUSTED = 130.00
TARGET_1 = 176.00      # 1.618 extension (chart)
TARGET_ALERT = 184.00   # from trade alert
TARGET_2 = 200.00       # 2.0 extension (chart) / approximate exit

# ── Swing Detection ────────────────────────────────────────────────────
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

# ── Identify the four key points ───────────────────────────────────────
# From swing data + TradingView chart:
#   Pre-correction peak → Correction bottom → Wave (1) top → Wave (2) bottom

tz = df_1d.index.tz

# Pre-correction peak: highest high before the Apr 2025 crash
pre_crash = df_1d.loc[:pd.Timestamp('2025-03-01', tz=tz)]
peak_idx = pre_crash['High'].idxmax()
peak_price = pre_crash['High'].max()

# Correction bottom: lowest after peak, before mid-2025
correction_window = df_1d.loc[peak_idx:pd.Timestamp('2025-06-01', tz=tz)]
origin_idx = correction_window['Low'].idxmin()
origin_price = correction_window['Low'].min()

# Wave (1) top: highest between correction bottom and Nov 2025
w1_window = df_1d.loc[origin_idx:pd.Timestamp('2025-11-15', tz=tz)]
w1_idx = w1_window['High'].idxmax()
w1_price = w1_window['High'].max()

# Wave (2) bottom: lowest between Wave (1) top and Mar 2026
w2_window = df_1d.loc[w1_idx:pd.Timestamp('2026-03-15', tz=tz)]
w2_idx = w2_window['Low'].idxmin()
w2_price = w2_window['Low'].min()

print("\n" + "="*80)
print("WAVE STRUCTURE")
print("="*80)
print(f"  Pre-correction peak : ${peak_price:.2f}  ({peak_idx.strftime('%Y-%m-%d')})")
print(f"  Wave origin (bottom): ${origin_price:.2f}  ({origin_idx.strftime('%Y-%m-%d')})")
print(f"  Wave (1) top        : ${w1_price:.2f}  ({w1_idx.strftime('%Y-%m-%d')})")
print(f"  Wave (2) bottom     : ${w2_price:.2f}  ({w2_idx.strftime('%Y-%m-%d')})")
print(f"  Entry               : ${ENTRY:.2f}")

# ── Bearish correction sub-waves ───────────────────────────────────────
print("\n" + "="*80)
print("BEARISH CORRECTION: PEAK → BOTTOM")
print("="*80)

correction_df = df_1d.loc[peak_idx:origin_idx]
correction_range = peak_price - origin_price
correction_pct = (correction_range / peak_price) * 100
correction_days = (origin_idx - peak_idx).days
print(f"  ${peak_price:.2f} → ${origin_price:.2f}  ({correction_pct:.1f}% decline over {correction_days} days)")

for order in [8, 10, 15]:
    swings = find_swings(correction_df, order=order)
    print(f"\n  Sub-waves (swing_order={order}): {len(swings)} points")
    for s in swings:
        print(f"    {s['date'].strftime('%Y-%m-%d')}  ${s['price']:.2f}  {s['type']}")

# ── Wave (1) analysis ──────────────────────────────────────────────────
print("\n" + "="*80)
print("WAVE (1) IMPULSE: ORIGIN → TOP")
print("="*80)

wave1_move = w1_price - origin_price
wave1_pct = (wave1_move / origin_price) * 100
wave1_days = (w1_idx - origin_idx).days
print(f"  ${origin_price:.2f} → ${w1_price:.2f}  (+${wave1_move:.2f}, +{wave1_pct:.1f}%, {wave1_days} days)")

# Sub-waves within Wave (1)
w1_df = df_1d.loc[origin_idx:w1_idx]
for order in [5, 8, 10]:
    swings = find_swings(w1_df, order=order)
    print(f"\n  Wave (1) sub-waves (swing_order={order}): {len(swings)} points")
    for s in swings:
        print(f"    {s['date'].strftime('%Y-%m-%d')}  ${s['price']:.2f}  {s['type']}")

# ── Wave (2) retracement analysis ──────────────────────────────────────
print("\n" + "="*80)
print("WAVE (2) RETRACEMENT ANALYSIS")
print("="*80)

wave2_retrace = w1_price - w2_price
retrace_pct = (wave2_retrace / wave1_move) * 100

fib_236 = w1_price - (0.236 * wave1_move)
fib_382 = w1_price - (0.382 * wave1_move)
fib_500 = w1_price - (0.500 * wave1_move)
fib_618 = w1_price - (0.618 * wave1_move)
fib_786 = w1_price - (0.786 * wave1_move)

print(f"  Wave (1) move: ${wave1_move:.2f}")
print(f"  Wave (2) retrace: ${wave2_retrace:.2f}")
print(f"  Retracement: {retrace_pct:.1f}%")
print(f"\n  Fibonacci levels:")
print(f"    23.6%: ${fib_236:.2f}")
print(f"    38.2%: ${fib_382:.2f}")
print(f"    50.0%: ${fib_500:.2f}")
print(f"    61.8%: ${fib_618:.2f}")
print(f"    78.6%: ${fib_786:.2f}")
print(f"    Actual Wave (2): ${w2_price:.2f}")
print(f"    Entry: ${ENTRY:.2f}")

# Closest Fibonacci level
fibs = {'23.6%': fib_236, '38.2%': fib_382, '50.0%': fib_500, '61.8%': fib_618, '78.6%': fib_786}
closest = min(fibs.items(), key=lambda x: abs(x[1] - w2_price))
print(f"\n  → Closest Fib to Wave (2): {closest[0]} (${closest[1]:.2f}), diff: ${abs(closest[1] - w2_price):.2f}")

# Elliott rule: Wave (2) must hold above wave origin
print(f"\n  Wave (2) ${w2_price:.2f} > Origin ${origin_price:.2f}? {'YES' if w2_price > origin_price else 'NO'}")

# ── Extension targets ──────────────────────────────────────────────────
print("\n" + "="*80)
print("WAVE (3) EXTENSION TARGETS")
print("="*80)

# INTERPRETATION A: Full Wave (1) = $80 → $183
print(f"\n  ── A) Full Wave (1): ${origin_price:.2f} → ${w1_price:.2f} (${wave1_move:.2f}) ──")
for ratio, label in [(1.0, '1.000x'), (1.272, '1.272x'), (1.618, '1.618x'), (2.0, '2.000x'), (2.618, '2.618x')]:
    target = w2_price + (ratio * wave1_move)
    print(f"    {label}: ${target:.2f}")

# INTERPRETATION B: Chart's Wave (1) — reverse-engineered from targets
# Chart shows: 1.618 = $176.14, 2.0 = $196.36
# Working backward: if 1.618 ext from entry $103.79 = $176.14
# then wave(1) move = ($176.14 - $103.79) / 1.618 = $44.71
# This matches origin ~$93.88 (.786 fib) → ~$138.59 (first strong high)
chart_w1_move = (176.14 - ENTRY) / 1.618
chart_origin = 93.88   # .786 retracement level marked on chart
chart_w1_top = chart_origin + chart_w1_move

print(f"\n  ── B) Chart's Wave (1): ~${chart_origin:.2f} → ~${chart_w1_top:.2f} (${chart_w1_move:.2f}) ──")
print(f"     (origin at .786 Fib of bearish correction, first strong high after bottom)")
for ratio, label in [(1.0, '1.000x'), (1.272, '1.272x'), (1.618, '1.618x'), (2.0, '2.000x'), (2.618, '2.618x')]:
    target = ENTRY + (ratio * chart_w1_move)
    print(f"    {label}: ${target:.2f}{'  ← chart T1 ($176)' if abs(target - 176) < 2 else '  ← chart T2 ($196)' if abs(target - 196) < 4 else ''}")

print(f"\n  Chart used a SMALLER Wave (1) (~$45 move vs ~$103 full move).")
print(f"  The chart's origin is the .786 Fib level of the bearish correction,")
print(f"  NOT the absolute bottom at ${origin_price:.2f}.")
print(f"  This produced practical targets that matched the actual trade exit.")

# ── Trade outcome ──────────────────────────────────────────────────────
print("\n" + "="*80)
print("TRADE OUTCOME")
print("="*80)

after_entry = df_1d.loc[w2_idx:]
max_price = after_entry['High'].max()
max_date = after_entry['High'].idxmax()

print(f"  Entry: ${ENTRY:.2f} on ~{w2_idx.strftime('%Y-%m-%d')}")
print(f"  Max price after entry: ${max_price:.2f} on {max_date.strftime('%Y-%m-%d')}")

hit_176 = after_entry[after_entry['High'] >= TARGET_1]
hit_184 = after_entry[after_entry['High'] >= TARGET_ALERT]
hit_200 = after_entry[after_entry['High'] >= TARGET_2]

print(f"  Target $176 (1.618x) hit? {'YES — ' + hit_176.index[0].strftime('%Y-%m-%d') if len(hit_176) > 0 else 'NO'}")
print(f"  Target $184 (alert)  hit? {'YES — ' + hit_184.index[0].strftime('%Y-%m-%d') if len(hit_184) > 0 else 'NO'}")
print(f"  Target $200 (2.0x)   hit? {'YES — ' + hit_200.index[0].strftime('%Y-%m-%d') if len(hit_200) > 0 else 'NO'}")

if len(hit_200) > 0:
    exit_price = 200.00
    gain_pct = ((exit_price - ENTRY) / ENTRY) * 100
    print(f"\n  Approximate exit ~$200: +{gain_pct:.1f}% gain")

# Note: SL $124→$130 was a TRAILING stop set after price rallied.
# Original stop would have been below Wave (2) ~$100.
# Check drawdown from entry before Wave (3) launched
post_entry = df_1d.loc[w2_idx:pd.Timestamp('2026-04-20', tz=tz)]
min_low_after_entry = post_entry['Low'].min()
min_low_date = post_entry['Low'].idxmin()
max_drawdown = ((ENTRY - min_low_after_entry) / ENTRY) * 100 if min_low_after_entry < ENTRY else 0
print(f"\n  Lowest price after entry (before targets): ${min_low_after_entry:.2f} on {min_low_date.strftime('%Y-%m-%d')}")
print(f"  Max drawdown from entry: {max_drawdown:.1f}%")
print(f"  (SL $124→$130 were trailing stops set after price rallied above entry)")

# ── Daily prices: entry area and target hits ───────────────────────────
print("\n" + "="*80)
print("DAILY PRICES — ENTRY AREA")
print("="*80)
entry_area = df_1d.loc[pd.Timestamp('2026-01-05', tz=tz):pd.Timestamp('2026-03-15', tz=tz)]
for date, row in entry_area.iterrows():
    marker = ""
    if abs(row['Low'] - ENTRY) < 5:
        marker = " ← NEAR ENTRY"
    if row['Low'] <= w2_price + 1:
        marker = " ← WAVE (2) LOW"
    print(f"  {date.strftime('%Y-%m-%d')}  O:{row['Open']:.2f}  H:{row['High']:.2f}  L:{row['Low']:.2f}  C:{row['Close']:.2f}{marker}")

print("\n── TARGET HIT AREA ──")
target_area = df_1d.loc[pd.Timestamp('2026-04-20', tz=tz):pd.Timestamp('2026-05-15', tz=tz)]
for date, row in target_area.iterrows():
    marker = ""
    if row['High'] >= 200:
        marker = " ← $200 TARGET HIT"
    elif row['High'] >= 184:
        marker = " ← $184 TARGET HIT"
    elif row['High'] >= 176:
        marker = " ← $176 TARGET HIT"
    print(f"  {date.strftime('%Y-%m-%d')}  O:{row['Open']:.2f}  H:{row['High']:.2f}  L:{row['Low']:.2f}  C:{row['Close']:.2f}{marker}")

# ── Pattern comparison ─────────────────────────────────────────────────
print("\n" + "="*80)
print("PATTERN VALIDATION — ARM vs STM/ZETA FRAMEWORK")
print("="*80)
print(f"""
  CHECKLIST:
  ──────────────────────────────────────────────────────────────────────
  1. Completed correction / bear wave
     Peak ${peak_price:.2f} → Bottom ${origin_price:.2f} ({correction_pct:.1f}% decline)
     {'PASS' if correction_pct > 30 else 'WEAK'}: Deep correction completed

  2. Confirmed Wave (1) impulse up
     ${origin_price:.2f} → ${w1_price:.2f} (+{wave1_pct:.1f}%)
     {'PASS' if wave1_pct > 50 else 'CHECK'}: Strong impulse off the bottom

  3. Wave (2) retraces to deep Fibonacci (61.8%–78.6%)
     Retracement: {retrace_pct:.1f}% — closest fib: {closest[0]}
     {'PASS' if 55 <= retrace_pct <= 85 else 'FAIL'}: {'In the 61.8-78.6 golden zone' if 61.8 <= retrace_pct <= 78.6 else 'Near the zone' if 55 <= retrace_pct <= 85 else 'Outside zone'}

  4. Wave (2) holds above wave origin
     Wave (2) ${w2_price:.2f} > Origin ${origin_price:.2f}
     {'PASS' if w2_price > origin_price else 'FAIL'}

  5. Entry near Wave (2) bottom
     Entry ${ENTRY:.2f} vs Wave (2) low ${w2_price:.2f}
     {'PASS' if abs(ENTRY - w2_price) < 10 else 'CLOSE' if abs(ENTRY - w2_price) < 20 else 'FAR'}

  6. Stop below structure
     SL ${SL_INITIAL:.2f} → adjusted to ${SL_ADJUSTED:.2f}
     (trailing stop moved up to lock profits)

  7. Targets at Fibonacci extensions
     Chart's 1.618x = $176.14 — {'HIT' if len(hit_176) > 0 else 'NOT HIT'}
     Alert target $184 — {'HIT' if len(hit_184) > 0 else 'NOT HIT'}
     Chart's 2.000x = $196.36 / exit ~$200 — {'HIT' if len(hit_200) > 0 else 'NOT HIT'}
     (Chart used smaller-degree Wave(1) from .786 fib origin)
  ──────────────────────────────────────────────────────────────────────
""")

# ── Chart ──────────────────────────────────────────────────────────────
print("Generating chart...")

fig, axes = plt.subplots(2, 1, figsize=(22, 16))
fig.suptitle('ARM — Elliott Wave Trade Verification (Completed Trade)', fontsize=16, fontweight='bold', y=0.98)

# Limit chart to the trade period (not the $325 blowoff)
chart_end = pd.Timestamp('2026-05-15', tz=tz)

# ── Top: Full view with wave structure ──
ax = axes[0]
plot_df = df_1d.loc[:chart_end]
ax.plot(plot_df.index, plot_df['Close'], color='#555555', linewidth=0.8, alpha=0.8)
ax.fill_between(plot_df.index, plot_df['Low'], plot_df['High'], alpha=0.08, color='gray')

# Trade levels
for price, color, style, label in [
    (ENTRY, 'green', '--', f'Entry ${ENTRY}'),
    (SL_ADJUSTED, 'red', '--', f'SL ${SL_ADJUSTED}'),
    (TARGET_1, '#1565C0', '--', f'T1: $176 (1.618x)'),
    (TARGET_ALERT, '#1565C0', ':', f'Alert: $184'),
    (TARGET_2, '#1565C0', '--', f'T2: $200 (2.0x)'),
]:
    ax.axhline(y=price, color=color, linestyle=style, alpha=0.4, linewidth=1)

# Fibonacci retracement levels
for fib_val, fib_label in [(fib_382, '38.2%'), (fib_500, '50%'), (fib_618, '61.8%'), (fib_786, '78.6%')]:
    ax.axhline(y=fib_val, color='orange', linestyle=':', alpha=0.25, linewidth=0.8)
    ax.annotate(f'Fib {fib_label}: ${fib_val:.2f}', (plot_df.index[3], fib_val),
               fontsize=7, color='orange', alpha=0.6, va='bottom')

# Draw wave structure: Origin → (1) → (2) and projected (3)
wave_dates = [origin_idx, w1_idx, w2_idx]
wave_prices = [origin_price, w1_price, w2_price]
wave_labels = ['Origin', '(1)', '(2)']

ax.plot(wave_dates, wave_prices, color='#E65100', linewidth=2.5, alpha=0.85, zorder=5)
for d, p, lbl in zip(wave_dates, wave_prices, wave_labels):
    offset = 14 if 'high' in lbl or lbl == '(1)' else -16
    ax.annotate(lbl, (d, p), textcoords="offset points",
               xytext=(0, offset), fontsize=11, fontweight='bold',
               color='#E65100', ha='center', zorder=6,
               bbox=dict(boxstyle='round,pad=0.3', facecolor='white',
                        edgecolor='#E65100', alpha=0.9))

# Projected Wave (3) line to target area
if len(hit_200) > 0:
    w3_date = hit_200.index[0]
    ax.plot([w2_idx, w3_date], [w2_price, TARGET_2], color='#2E7D32',
            linewidth=2, linestyle='--', alpha=0.6, zorder=4)
    ax.annotate('(3) exit\n~$200', (w3_date, TARGET_2), textcoords="offset points",
               xytext=(10, 10), fontsize=10, fontweight='bold', color='#2E7D32',
               bbox=dict(boxstyle='round,pad=0.3', facecolor='#E8F5E9',
                        edgecolor='#2E7D32', alpha=0.8))

# Labels on right side
rightside = plot_df.index[-10] if len(plot_df) > 10 else plot_df.index[-1]
ax.annotate(f'Entry ${ENTRY}', (rightside, ENTRY), fontsize=8, color='green', fontweight='bold',
           textcoords="offset points", xytext=(10, 5))
ax.annotate(f'SL ${SL_ADJUSTED}', (rightside, SL_ADJUSTED), fontsize=8, color='red',
           textcoords="offset points", xytext=(10, -10))

# Swings
swings_d = find_swings(plot_df, order=10)
for s in swings_d:
    color = '#2196F3' if s['type'] == 'high' else '#FF9800'
    marker = 'v' if s['type'] == 'high' else '^'
    ax.scatter(s['date'], s['price'], color=color, marker=marker, s=25, zorder=3, alpha=0.4)

ax.set_title('ARM — Daily (Full View, capped at trade exit)', fontsize=12, fontweight='bold')
ax.set_ylabel('Price (USD)')
ax.grid(True, alpha=0.2)
ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha='right')

# ── Bottom: Zoomed to Wave (2) entry → exit ──
ax2 = axes[1]
zoom_start = w1_idx - timedelta(days=30)
zoom_df = df_1d.loc[zoom_start:chart_end]
ax2.plot(zoom_df.index, zoom_df['Close'], color='#555555', linewidth=1, alpha=0.8)
ax2.fill_between(zoom_df.index, zoom_df['Low'], zoom_df['High'], alpha=0.08, color='gray')

for price, color, style in [
    (ENTRY, 'green', '--'), (SL_ADJUSTED, 'red', '--'),
    (TARGET_1, '#1565C0', '--'), (TARGET_ALERT, '#1565C0', ':'), (TARGET_2, '#1565C0', '--'),
]:
    ax2.axhline(y=price, color=color, linestyle=style, alpha=0.4, linewidth=1.2)

for fib_val, fib_label in [(fib_382, '38.2%'), (fib_500, '50%'), (fib_618, '61.8%'), (fib_786, '78.6%')]:
    ax2.axhline(y=fib_val, color='orange', linestyle=':', alpha=0.3, linewidth=0.8)
    ax2.annotate(f'{fib_label}: ${fib_val:.2f}', (zoom_df.index[1], fib_val),
               fontsize=8, color='orange', alpha=0.7, va='bottom')

# Wave labels on zoomed
ax2.plot([w1_idx, w2_idx], [w1_price, w2_price], color='#E65100', linewidth=2.5, alpha=0.85, zorder=5)
for d, p, lbl in [(w1_idx, w1_price, '(1)'), (w2_idx, w2_price, '(2)')]:
    offset = 14 if lbl == '(1)' else -16
    ax2.annotate(lbl, (d, p), textcoords="offset points",
                xytext=(0, offset), fontsize=12, fontweight='bold',
                color='#E65100', ha='center', zorder=6,
                bbox=dict(boxstyle='round,pad=0.3', facecolor='white',
                         edgecolor='#E65100', alpha=0.9))

if len(hit_200) > 0:
    w3_date = hit_200.index[0]
    ax2.plot([w2_idx, w3_date], [w2_price, TARGET_2], color='#2E7D32',
            linewidth=2, linestyle='--', alpha=0.6, zorder=4)
    ax2.annotate('Exit ~$200', (w3_date, TARGET_2), textcoords="offset points",
               xytext=(10, 10), fontsize=10, fontweight='bold', color='#2E7D32')

# Entry marker
ax2.axvline(x=w2_idx, color='green', linestyle=':', alpha=0.4)
ax2.annotate(f'ENTRY ${ENTRY}', (w2_idx, ENTRY), textcoords="offset points",
            xytext=(15, -20), fontsize=10, color='green', fontweight='bold',
            arrowprops=dict(arrowstyle='->', color='green', alpha=0.6))

# Target annotations
right = zoom_df.index[-3] if len(zoom_df) > 3 else zoom_df.index[-1]
ax2.annotate(f'T1: $176 (1.618x)', (right, TARGET_1), fontsize=8, color='#1565C0',
            textcoords="offset points", xytext=(10, 5))
ax2.annotate(f'T2: $200 (2.0x)', (right, TARGET_2), fontsize=8, color='#1565C0',
            textcoords="offset points", xytext=(10, 5))
ax2.annotate(f'SL ${SL_ADJUSTED}', (right, SL_ADJUSTED), fontsize=8, color='red',
            textcoords="offset points", xytext=(10, -10))

swings_zoom = find_swings(zoom_df, order=5)
for s in swings_zoom:
    color = '#2196F3' if s['type'] == 'high' else '#FF9800'
    marker = 'v' if s['type'] == 'high' else '^'
    ax2.scatter(s['date'], s['price'], color=color, marker=marker, s=30, zorder=3, alpha=0.5)

ax2.set_title('ARM — Daily (Wave 2 Entry → Exit)', fontsize=12, fontweight='bold')
ax2.set_ylabel('Price (USD)')
ax2.grid(True, alpha=0.2)
ax2.xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))
plt.setp(ax2.xaxis.get_majorticklabels(), rotation=30, ha='right')

plt.tight_layout(rect=[0, 0, 1, 0.97])
output_path = '/Users/home/Desktop/Projects/elliot_wave/arm_elliott_analysis.png'
plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
print(f"\nChart saved to: {output_path}")
