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
import time
import json
import requests
from io import StringIO
warnings.filterwarnings('ignore')

# ═══════════════════════════════════════════════════════════════════════
# POINT 0 SCANNER — Stocks at the start of a new wave
# Just completed a deep correction, beginning to reverse
# ═══════════════════════════════════════════════════════════════════════

# Parameters derived from ARM/STM/ZETA corrections
MIN_CORRECTION_PCT = 40.0
MAX_CORRECTION_PCT = 85.0
MIN_CORRECTION_DAYS = 60
MAX_DAYS_SINCE_BOTTOM = 45      # bottom must be recent
MAX_RECOVERY_PCT = 30.0          # not too far off the bottom yet
MIN_PRICE = 3.0
MIN_AVG_VOLUME = 300_000

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


def analyze_point0(df, ticker):
    """Find stocks that just bottomed from a deep correction."""
    if len(df) < 100:
        return None

    tz = df.index.tz
    current_price = df['Close'].iloc[-1]
    avg_vol = df['Volume'].tail(30).mean()

    if current_price < MIN_PRICE or avg_vol < MIN_AVG_VOLUME:
        return None

    results = []

    for swing_order in [10, 15, 20]:
        swings = find_swings(df, order=swing_order)
        if len(swings) < 3:
            continue

        highs = [s for s in swings if s['type'] == 'high']
        lows = [s for s in swings if s['type'] == 'low']

        if not highs or not lows:
            continue

        # For each major high, check if there's a recent deep low after it
        for peak in highs:
            peak_price = peak['price']
            peak_date = peak['date']

            # Need enough time for a proper correction
            days_since_peak = (df.index[-1] - peak_date).days
            if days_since_peak < MIN_CORRECTION_DAYS:
                continue

            # Find lows after this peak
            later_lows = [s for s in lows if s['date'] > peak_date]
            if not later_lows:
                continue

            for bottom in later_lows:
                bottom_price = bottom['price']
                bottom_date = bottom['date']

                correction_pct = ((peak_price - bottom_price) / peak_price) * 100
                if correction_pct < MIN_CORRECTION_PCT or correction_pct > MAX_CORRECTION_PCT:
                    continue

                correction_days = (bottom_date - peak_date).days
                if correction_days < MIN_CORRECTION_DAYS:
                    continue

                days_since_bottom = (df.index[-1] - bottom_date).days
                if days_since_bottom > MAX_DAYS_SINCE_BOTTOM:
                    continue

                # Check that this is actually the lowest point (no lower low after)
                after_bottom = df.loc[bottom_date:]
                if len(after_bottom) > 1 and after_bottom['Low'].min() < bottom_price * 0.98:
                    actual_min = after_bottom['Low'].min()
                    actual_min_date = after_bottom['Low'].idxmin()
                    # Use the actual lowest point instead
                    bottom_price = actual_min
                    bottom_date = actual_min_date
                    days_since_bottom = (df.index[-1] - bottom_date).days
                    if days_since_bottom > MAX_DAYS_SINCE_BOTTOM:
                        continue
                    correction_pct = ((peak_price - bottom_price) / peak_price) * 100
                    if correction_pct < MIN_CORRECTION_PCT:
                        continue

                # How much has it recovered from the bottom?
                recovery_pct = ((current_price - bottom_price) / bottom_price) * 100
                if recovery_pct > MAX_RECOVERY_PCT:
                    continue
                if recovery_pct < -5:
                    continue  # still falling

                # Check if the bottom is the lowest in the correction period
                corr_window = df.loc[peak_date:bottom_date]
                if len(corr_window) > 0:
                    actual_low = corr_window['Low'].min()
                    if bottom_price > actual_low * 1.05:
                        continue  # not the actual bottom

                # Check for bearish sub-wave count in correction
                corr_df = df.loc[peak_date:bottom_date]
                corr_swings = find_swings(corr_df, order=max(5, swing_order // 2))
                n_corr_swings = len(corr_swings)

                # Volume analysis — is volume increasing off the bottom?
                if days_since_bottom >= 5:
                    recent_vol = df['Volume'].tail(5).mean()
                    prior_vol = df['Volume'].iloc[-20:-5].mean() if len(df) > 20 else avg_vol
                    vol_ratio = recent_vol / prior_vol if prior_vol > 0 else 1.0
                else:
                    vol_ratio = 1.0

                # Price momentum — is it turning up?
                if len(df) >= 10:
                    last_5_close = df['Close'].tail(5).values
                    momentum = (last_5_close[-1] - last_5_close[0]) / last_5_close[0] * 100 if last_5_close[0] > 0 else 0
                else:
                    momentum = 0

                # Projected targets based on ARM/ZETA pattern averages
                # Average Wave (1) gain was 122%, so:
                projected_w1_top = bottom_price * 2.22  # +122%
                projected_w2_low = projected_w1_top - (0.75 * (projected_w1_top - bottom_price))  # 75% retrace
                projected_w3_target = projected_w2_low + 1.618 * (projected_w1_top - bottom_price)

                # Score the setup
                score = 0.0

                # Correction depth (prefer 50-75%, matching our data)
                if 55 <= correction_pct <= 75:
                    score += 25
                elif 45 <= correction_pct <= 80:
                    score += 15
                else:
                    score += 5

                # Correction duration (prefer 150-300 days)
                if 120 <= correction_days <= 350:
                    score += 15
                elif 60 <= correction_days <= 400:
                    score += 8

                # Freshness (prefer very recent bottoms)
                if days_since_bottom <= 10:
                    score += 25
                elif days_since_bottom <= 21:
                    score += 18
                elif days_since_bottom <= 35:
                    score += 10
                else:
                    score += 5

                # Recovery — slight bounce is good (confirms bottom)
                if 2 <= recovery_pct <= 15:
                    score += 20
                elif 0 <= recovery_pct < 2:
                    score += 10  # barely moved, could still be falling
                elif 15 < recovery_pct <= 30:
                    score += 8

                # Volume confirmation
                if vol_ratio > 1.5:
                    score += 10
                elif vol_ratio > 1.2:
                    score += 5

                # Momentum (price turning up)
                if momentum > 3:
                    score += 10
                elif momentum > 0:
                    score += 5

                # Correction sub-wave count (5+ swings suggests complete structure)
                if n_corr_swings >= 8:
                    score += 10
                elif n_corr_swings >= 5:
                    score += 5

                # Liquidity bonus
                if avg_vol > 5_000_000:
                    score += 5
                elif avg_vol > 1_000_000:
                    score += 3

                results.append({
                    'ticker': ticker,
                    'current_price': current_price,
                    'avg_volume': avg_vol,
                    'peak_price': peak_price,
                    'peak_date': peak_date,
                    'bottom_price': bottom_price,
                    'bottom_date': bottom_date,
                    'correction_pct': correction_pct,
                    'correction_days': correction_days,
                    'days_since_bottom': days_since_bottom,
                    'recovery_pct': recovery_pct,
                    'vol_ratio': vol_ratio,
                    'momentum_5d': momentum,
                    'n_corr_swings': n_corr_swings,
                    'projected_w1_top': projected_w1_top,
                    'projected_w2_entry': projected_w2_low,
                    'projected_w3_target': projected_w3_target,
                    'score': score,
                    'swing_order': swing_order,
                })

    if not results:
        return None

    results.sort(key=lambda x: x['score'], reverse=True)
    seen = set()
    best = []
    for r in results:
        key = r['bottom_date'].strftime('%Y-%m')
        if key not in seen:
            best.append(r)
            seen.add(key)
        if len(best) >= 2:
            break
    return best


# ── Get tickers ───────────────────────────────────────────────────────
print("="*90)
print("POINT 0 SCANNER — Stocks just completing a deep correction")
print(f"Looking for: >{MIN_CORRECTION_PCT}% decline, bottom within last {MAX_DAYS_SINCE_BOTTOM} days,")
print(f"             recovery <{MAX_RECOVERY_PCT}%, starting to reverse")
print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print("="*90)

headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'}
all_tickers = []

for name, url in [
    ('S&P 500', 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'),
    ('S&P 600', 'https://en.wikipedia.org/wiki/List_of_S%26P_600_companies'),
    ('S&P 400', 'https://en.wikipedia.org/wiki/List_of_S%26P_400_companies'),
]:
    try:
        resp = requests.get(url, headers=headers)
        tables = pd.read_html(StringIO(resp.text))
        df = tables[0]
        col = 'Symbol' if 'Symbol' in df.columns else 'Ticker symbol' if 'Ticker symbol' in df.columns else df.columns[0]
        batch = [t.replace('.', '-') for t in df[col].tolist()]
        all_tickers.extend(batch)
        print(f"  {name}: {len(batch)}")
    except Exception as e:
        print(f"  {name}: failed ({e})")

all_tickers = sorted(set(all_tickers))
print(f"  Total: {len(all_tickers)}")

# ── Download ──────────────────────────────────────────────────────────
print(f"\nDownloading data...")
end_date = datetime.now()
start_date = end_date - timedelta(days=730)

all_data = {}
total = len(all_tickers)
for i in range(0, total, 50):
    batch = all_tickers[i:i+50]
    try:
        data = yf.download(' '.join(batch), start=start_date, end=end_date,
                          interval='1d', group_by='ticker', progress=False, threads=True)
        if len(batch) == 1:
            if len(data) > 50:
                all_data[batch[0]] = data
        else:
            for t in batch:
                try:
                    td = data[t].dropna(how='all')
                    if len(td) > 50:
                        all_data[t] = td
                except (KeyError, TypeError):
                    pass
    except:
        pass

    done = min(i + 50, total)
    print(f"\r  {done}/{total} ({done/total*100:.0f}%) — {len(all_data)} valid", end='', flush=True)
    if i + 50 < total:
        time.sleep(0.5)

print()

# ── Scan ──────────────────────────────────────────────────────────────
print(f"\nScanning for Point 0 setups...")
candidates = []
scanned = 0

for ticker, df in all_data.items():
    scanned += 1
    if scanned % 200 == 0:
        print(f"\r  {scanned}/{len(all_data)} — {len(candidates)} found", end='', flush=True)
    try:
        results = analyze_point0(df, ticker)
        if results:
            candidates.extend(results)
    except:
        pass

print(f"\r  {scanned}/{len(all_data)} — {len(candidates)} found")

# Deduplicate
candidates.sort(key=lambda x: x['score'], reverse=True)
seen = set()
unique = []
for c in candidates:
    if c['ticker'] not in seen:
        unique.append(c)
        seen.add(c['ticker'])

# Split by timing
just_bottomed = [c for c in unique if c['days_since_bottom'] <= 10]
early_reversal = [c for c in unique if 10 < c['days_since_bottom'] <= 25]
confirming = [c for c in unique if 25 < c['days_since_bottom'] <= 45]

# ── Results ───────────────────────────────────────────────────────────
print(f"\n{'='*90}")
print(f"RESULTS")
print(f"{'='*90}")
print(f"  Total Point 0 candidates: {len(unique)}")
print(f"  Just bottomed (0-10 days):     {len(just_bottomed)}")
print(f"  Early reversal (11-25 days):   {len(early_reversal)}")
print(f"  Confirming bounce (26-45 days): {len(confirming)}")

def print_table(items, header, limit=30):
    if not items:
        print(f"\n  No candidates.")
        return
    print(f"\n{'─'*90}")
    print(f"  {header}")
    print(f"{'─'*90}")
    print(f"  {'Ticker':<8} {'Score':>5} {'Price':>8} {'Corr%':>6} {'CorrDays':>8} {'DaysBot':>7} {'Recov%':>7} {'Vol↑':>5} {'Mom5d':>6} {'ProjW1':>8} {'ProjW2E':>8} {'ProjW3':>8}")
    print(f"  {'─'*8} {'─'*5} {'─'*8} {'─'*6} {'─'*8} {'─'*7} {'─'*7} {'─'*5} {'─'*6} {'─'*8} {'─'*8} {'─'*8}")

    for c in items[:limit]:
        print(f"  {c['ticker']:<8} {c['score']:>5.0f} {c['current_price']:>8.2f} {c['correction_pct']:>5.1f}% {c['correction_days']:>7}d {c['days_since_bottom']:>5}d  {c['recovery_pct']:>5.1f}% {c['vol_ratio']:>4.1f}x {c['momentum_5d']:>+5.1f}% {c['projected_w1_top']:>8.2f} {c['projected_w2_entry']:>8.2f} {c['projected_w3_target']:>8.2f}")

    if len(items) > limit:
        print(f"\n  ... and {len(items) - limit} more")

print_table(just_bottomed, "JUST BOTTOMED — Point 0 in the last 10 days")
print_table(early_reversal, "EARLY REVERSAL — Bouncing off bottom (11-25 days)")
print_table(confirming, "CONFIRMING — Sustained bounce (26-45 days)")

# ── Detailed top candidates ───────────────────────────────────────────
top_n = min(20, len(unique))
if top_n > 0:
    print(f"\n{'='*90}")
    print(f"DETAILED — Top {top_n}")
    print(f"{'='*90}")

    for i, c in enumerate(unique[:top_n]):
        print(f"\n  {'─'*80}")
        print(f"  #{i+1}  {c['ticker']}  |  Score: {c['score']:.0f}  |  ${c['current_price']:.2f}  |  Bottom {c['days_since_bottom']}d ago")
        print(f"  {'─'*80}")
        print(f"    Peak:       ${c['peak_price']:.2f} ({c['peak_date'].strftime('%Y-%m-%d')})")
        print(f"    Bottom:     ${c['bottom_price']:.2f} ({c['bottom_date'].strftime('%Y-%m-%d')})")
        print(f"    Correction: {c['correction_pct']:.1f}% over {c['correction_days']} days")
        print(f"    Recovery:   {c['recovery_pct']:.1f}% from bottom  |  5d momentum: {c['momentum_5d']:+.1f}%")
        print(f"    Volume:     {c['avg_volume']:,.0f} avg  |  recent/prior: {c['vol_ratio']:.1f}x")
        print(f"    Corr swings: {c['n_corr_swings']} (more = more complete structure)")
        print(f"    ── Projected path (based on avg ARM/STM/ZETA pattern) ──")
        print(f"    Wave (1) top:    ${c['projected_w1_top']:.2f} (+{((c['projected_w1_top']-c['current_price'])/c['current_price']*100):.0f}% from current)")
        print(f"    Wave (2) entry:  ${c['projected_w2_entry']:.2f} (projected pullback for W2 entry)")
        print(f"    Wave (3) target: ${c['projected_w3_target']:.2f} (+{((c['projected_w3_target']-c['current_price'])/c['current_price']*100):.0f}% from current)")

# ── Chart ─────────────────────────────────────────────────────────────
chart_n = min(8, len(unique))
if chart_n > 0:
    print(f"\nGenerating charts...")
    rows = (chart_n + 1) // 2
    fig, axes = plt.subplots(rows, 2, figsize=(24, 6 * rows))
    fig.suptitle(f'Point 0 Scanner — Stocks at Correction Bottom ({datetime.now().strftime("%Y-%m-%d")})',
                fontsize=16, fontweight='bold', y=0.98)
    if rows == 1:
        axes = [axes]

    for i, c in enumerate(unique[:chart_n]):
        ax = axes[i // 2][i % 2]
        ticker = c['ticker']
        if ticker not in all_data:
            continue

        df = all_data[ticker]
        ax.plot(df.index, df['Close'], color='#555555', linewidth=0.8, alpha=0.8)
        ax.fill_between(df.index, df['Low'], df['High'], alpha=0.06, color='gray')

        # Mark peak and bottom
        ax.scatter(c['peak_date'], c['peak_price'], color='red', marker='v', s=100, zorder=5)
        ax.annotate('Peak', (c['peak_date'], c['peak_price']), textcoords="offset points",
                   xytext=(0, 12), fontsize=9, fontweight='bold', color='red', ha='center',
                   bbox=dict(boxstyle='round,pad=0.2', facecolor='white', edgecolor='red', alpha=0.9))

        ax.scatter(c['bottom_date'], c['bottom_price'], color='#2E7D32', marker='^', s=100, zorder=5)
        ax.annotate('Point 0', (c['bottom_date'], c['bottom_price']), textcoords="offset points",
                   xytext=(0, -16), fontsize=9, fontweight='bold', color='#2E7D32', ha='center',
                   bbox=dict(boxstyle='round,pad=0.2', facecolor='white', edgecolor='#2E7D32', alpha=0.9))

        # Correction line
        ax.plot([c['peak_date'], c['bottom_date']], [c['peak_price'], c['bottom_price']],
               color='red', linewidth=1.5, linestyle='--', alpha=0.5)

        # Projected Wave (1) path
        future_date = df.index[-1] + timedelta(days=200)
        ax.plot([c['bottom_date'], future_date], [c['bottom_price'], c['projected_w1_top']],
               color='#2E7D32', linewidth=1.5, linestyle='--', alpha=0.4)
        ax.annotate(f'Proj W1: ${c["projected_w1_top"]:.0f}', (future_date, c['projected_w1_top']),
                   fontsize=7, color='#2E7D32', alpha=0.7)

        # Current price
        ax.axhline(y=c['current_price'], color='blue', linestyle=':', alpha=0.3)

        # Swings
        swings = find_swings(df, order=c['swing_order'])
        for s in swings:
            clr = '#2196F3' if s['type'] == 'high' else '#FF9800'
            mkr = 'v' if s['type'] == 'high' else '^'
            ax.scatter(s['date'], s['price'], color=clr, marker=mkr, s=15, zorder=3, alpha=0.35)

        ax.set_title(f"{ticker} | Score:{c['score']:.0f} | Corr:{c['correction_pct']:.0f}% | Bot:{c['days_since_bottom']}d ago | Recov:{c['recovery_pct']:.1f}% | ${c['current_price']:.2f}",
                    fontsize=9, fontweight='bold')
        ax.set_ylabel('Price')
        ax.grid(True, alpha=0.2)
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %y'))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha='right', fontsize=8)

    for i in range(chart_n, rows * 2):
        axes[i // 2][i % 2].set_visible(False)

    plt.tight_layout(rect=[0, 0, 1, 0.97])
    out = '/Users/home/Desktop/Projects/elliot_wave/scanner_point0.png'
    plt.savefig(out, dpi=150, bbox_inches='tight', facecolor='white')
    print(f"Chart saved to: {out}")

# Save JSON
out_json = '/Users/home/Desktop/Projects/elliot_wave/scanner_point0.json'
json_out = []
for c in unique[:50]:
    json_out.append({
        'ticker': c['ticker'],
        'score': c['score'],
        'current_price': float(c['current_price']),
        'peak_price': float(c['peak_price']),
        'peak_date': c['peak_date'].strftime('%Y-%m-%d'),
        'bottom_price': float(c['bottom_price']),
        'bottom_date': c['bottom_date'].strftime('%Y-%m-%d'),
        'correction_pct': float(c['correction_pct']),
        'correction_days': c['correction_days'],
        'days_since_bottom': c['days_since_bottom'],
        'recovery_pct': float(c['recovery_pct']),
        'projected_w1_top': float(c['projected_w1_top']),
        'projected_w2_entry': float(c['projected_w2_entry']),
        'projected_w3_target': float(c['projected_w3_target']),
    })
with open(out_json, 'w') as f:
    json.dump(json_out, f, indent=2)
print(f"Results saved to: {out_json}")

print(f"\n{'='*90}")
print("SCAN COMPLETE")
print(f"{'='*90}")
