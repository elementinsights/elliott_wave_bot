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
import sys
import json
warnings.filterwarnings('ignore')

# ═══════════════════════════════════════════════════════════════════════
# ELLIOTT WAVE SCANNER
# Scans S&P 500 + Russell 2000 for Wave (2) entry setups
# Based on unified strategy from ARM (+93%), STM, ZETA
# ═══════════════════════════════════════════════════════════════════════

# ── Strategy parameters (derived from ARM/ZETA data) ──────────────────
MIN_CORRECTION_PCT = 40.0       # minimum peak-to-trough decline
MAX_CORRECTION_PCT = 85.0       # maximum (avoid penny stocks / dying companies)
MIN_WAVE1_GAIN_PCT = 50.0       # minimum Wave (1) rally
MIN_WAVE2_RETRACE_PCT = 45.0    # minimum Wave (2) retrace of Wave (1)
MAX_WAVE2_RETRACE_PCT = 90.0    # maximum (beyond .786 + buffer)
ENTRY_WINDOW_DAYS = 21          # how recently Wave (2) bottom must have formed
MIN_PRICE = 5.0                 # minimum stock price
MIN_AVG_VOLUME = 200_000        # minimum average daily volume

# ── Swing detection ───────────────────────────────────────────────────
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
    """Find the first sub-impulse within Wave (1) for target calculation."""
    w1_df = df.loc[origin_idx:w1_top_idx]
    if len(w1_df) < 10:
        return None

    for order in [5, 8, 10, 12]:
        swings = find_swings(w1_df, order=order)
        highs = [s for s in swings if s['type'] == 'high']
        lows = [s for s in swings if s['type'] == 'low']
        if len(highs) >= 1 and len(lows) >= 1:
            first_high = highs[0]
            pullbacks = [s for s in lows if s['date'] > first_high['date']]
            if pullbacks:
                move = first_high['price'] - origin_price
                retrace_pct = (first_high['price'] - pullbacks[0]['price']) / move * 100 if move > 0 else 0
                if 25 <= retrace_pct <= 70 and move > 0:
                    return {
                        'move': move,
                        'high': first_high['price'],
                        'high_date': first_high['date'],
                        'pullback': pullbacks[0]['price'],
                        'retrace_pct': retrace_pct,
                    }
    return None


# ── Full wave analysis for a single ticker ────────────────────────────
def analyze_ticker(df, ticker):
    """Run full Elliott Wave analysis. Returns candidate dict or None."""
    if len(df) < 100:
        return None

    tz = df.index.tz
    current_price = df['Close'].iloc[-1]
    avg_vol = df['Volume'].tail(30).mean()

    if current_price < MIN_PRICE or avg_vol < MIN_AVG_VOLUME:
        return None

    results = []

    # Try multiple swing orders for robustness
    for swing_order in [10, 12, 15, 20]:
        swings = find_swings(df, order=swing_order)
        if len(swings) < 6:
            continue

        highs = [s for s in swings if s['type'] == 'high']
        lows = [s for s in swings if s['type'] == 'low']

        if len(highs) < 2 or len(lows) < 3:
            continue

        # Try each major high as a potential peak
        for hi, peak_swing in enumerate(highs):
            peak_price = peak_swing['price']
            peak_date = peak_swing['date']

            # Skip if peak is too recent (need time for correction + W1 + W2)
            if (df.index[-1] - peak_date).days < 180:
                continue

            # Find the deepest low AFTER this peak (correction bottom / wave origin)
            later_lows = [s for s in lows if s['date'] > peak_date]
            if not later_lows:
                continue

            for origin_swing in later_lows:
                origin_price = origin_swing['price']
                origin_date = origin_swing['date']

                correction_pct = ((peak_price - origin_price) / peak_price) * 100
                if correction_pct < MIN_CORRECTION_PCT or correction_pct > MAX_CORRECTION_PCT:
                    continue

                correction_days = (origin_date - peak_date).days
                if correction_days < 30:
                    continue

                # Find Wave (1) top: highest high after origin
                later_highs = [s for s in highs if s['date'] > origin_date]
                if not later_highs:
                    continue

                for w1_swing in later_highs:
                    w1_price = w1_swing['price']
                    w1_date = w1_swing['date']

                    wave1_move = w1_price - origin_price
                    wave1_pct = (wave1_move / origin_price) * 100 if origin_price > 0 else 0

                    if wave1_pct < MIN_WAVE1_GAIN_PCT:
                        continue

                    wave1_days = (w1_date - origin_date).days
                    if wave1_days < 30:
                        continue

                    # Find Wave (2) low: lowest low after Wave (1) top
                    w2_candidates = [s for s in lows if s['date'] > w1_date]
                    if not w2_candidates:
                        continue

                    for w2_swing in w2_candidates:
                        w2_price = w2_swing['price']
                        w2_date = w2_swing['date']

                        # Wave (2) must hold above origin
                        if w2_price <= origin_price:
                            continue

                        wave2_retrace = w1_price - w2_price
                        wave2_retrace_pct = (wave2_retrace / wave1_move) * 100 if wave1_move > 0 else 0

                        if wave2_retrace_pct < MIN_WAVE2_RETRACE_PCT or wave2_retrace_pct > MAX_WAVE2_RETRACE_PCT:
                            continue

                        # Check timing — Wave (2) bottom should be recent
                        days_since_w2 = (df.index[-1] - w2_date).days

                        # Current price should be above Wave (2) low (recovery started)
                        if current_price < w2_price:
                            continue

                        # Classify the setup
                        if days_since_w2 <= ENTRY_WINDOW_DAYS:
                            stage = "AT_ENTRY"  # right at Wave (2) bottom now
                        elif days_since_w2 <= 60:
                            stage = "EARLY_W3"  # recently launched from W2
                        elif days_since_w2 <= 120:
                            stage = "MID_W3"    # wave 3 in progress
                        else:
                            continue  # too old

                        # Fibonacci analysis
                        fib_levels = {
                            0.382: w1_price - (0.382 * wave1_move),
                            0.500: w1_price - (0.500 * wave1_move),
                            0.618: w1_price - (0.618 * wave1_move),
                            0.786: w1_price - (0.786 * wave1_move),
                        }
                        closest_fib = min(fib_levels.items(), key=lambda x: abs(x[1] - w2_price))

                        # Extension targets
                        ext_full = {r: w2_price + (r * wave1_move) for r in [1.0, 1.618, 2.0]}

                        # Sub-wave (1) for conservative targets
                        sub_w1 = find_sub_wave1(df, origin_date, w1_date, origin_price)
                        ext_sub = {}
                        if sub_w1:
                            ext_sub = {r: w2_price + (r * sub_w1['move']) for r in [1.0, 1.618, 2.0, 2.618]}

                        # Score the setup
                        score = 0.0

                        # Retrace quality (prefer 61.8-78.6%)
                        if 61.8 <= wave2_retrace_pct <= 78.6:
                            score += 35
                        elif 55 <= wave2_retrace_pct <= 85:
                            score += 20
                        else:
                            score += 5

                        # Correction depth (prefer 50-75%)
                        if 50 <= correction_pct <= 75:
                            score += 15
                        elif 40 <= correction_pct <= 85:
                            score += 8

                        # Wave (1) strength
                        if wave1_pct >= 100:
                            score += 15
                        elif wave1_pct >= 70:
                            score += 10

                        # Timing freshness
                        if stage == "AT_ENTRY":
                            score += 25
                        elif stage == "EARLY_W3":
                            score += 15
                        elif stage == "MID_W3":
                            score += 5

                        # Recovery confirmation (price has bounced from W2)
                        recovery_pct = ((current_price - w2_price) / w2_price) * 100 if w2_price > 0 else 0
                        if 0 < recovery_pct < 15:
                            score += 10  # just starting to recover
                        elif 15 <= recovery_pct < 40:
                            score += 5

                        # Risk/reward
                        risk = w2_price * 0.05  # 5% below W2
                        reward_t1 = ext_full.get(1.0, 0) - current_price
                        rr = reward_t1 / risk if risk > 0 else 0
                        if rr >= 3:
                            score += 10

                        results.append({
                            'ticker': ticker,
                            'current_price': current_price,
                            'avg_volume': avg_vol,
                            'peak_price': peak_price,
                            'peak_date': peak_date,
                            'origin_price': origin_price,
                            'origin_date': origin_date,
                            'w1_price': w1_price,
                            'w1_date': w1_date,
                            'w2_price': w2_price,
                            'w2_date': w2_date,
                            'correction_pct': correction_pct,
                            'correction_days': correction_days,
                            'wave1_pct': wave1_pct,
                            'wave1_move': wave1_move,
                            'wave1_days': wave1_days,
                            'wave2_retrace_pct': wave2_retrace_pct,
                            'closest_fib': closest_fib,
                            'days_since_w2': days_since_w2,
                            'stage': stage,
                            'recovery_pct': recovery_pct,
                            'ext_full': ext_full,
                            'ext_sub': ext_sub,
                            'sub_w1': sub_w1,
                            'score': score,
                            'swing_order': swing_order,
                        })

    if not results:
        return None

    # Deduplicate — keep highest-scored, non-overlapping setups
    results.sort(key=lambda x: x['score'], reverse=True)
    best = []
    used_dates = set()
    for r in results:
        key = r['w2_date'].strftime('%Y-%m')
        if key not in used_dates:
            best.append(r)
            used_dates.add(key)
        if len(best) >= 2:
            break

    return best


# ── Get ticker lists ──────────────────────────────────────────────────
def get_sp500_tickers():
    """Get S&P 500 tickers from Wikipedia."""
    import requests
    from io import StringIO
    headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'}
    try:
        resp = requests.get('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies', headers=headers)
        tables = pd.read_html(StringIO(resp.text))
        df = tables[0]
        tickers = df['Symbol'].tolist()
        tickers = [t.replace('.', '-') for t in tickers]
        return tickers
    except Exception as e:
        print(f"  Error fetching S&P 500 list: {e}")
        return []


def get_smallmid_tickers():
    """Get S&P 400 (mid) + S&P 600 (small) as Russell proxy."""
    import requests
    from io import StringIO
    headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'}
    tickers = []

    for name, url in [
        ('S&P 600', 'https://en.wikipedia.org/wiki/List_of_S%26P_600_companies'),
        ('S&P 400', 'https://en.wikipedia.org/wiki/List_of_S%26P_400_companies'),
    ]:
        try:
            resp = requests.get(url, headers=headers)
            tables = pd.read_html(StringIO(resp.text))
            df = tables[0]
            col = 'Symbol' if 'Symbol' in df.columns else 'Ticker symbol' if 'Ticker symbol' in df.columns else df.columns[0]
            batch = df[col].tolist()
            batch = [t.replace('.', '-') for t in batch]
            tickers.extend(batch)
            print(f"    {name}: {len(batch)} tickers")
        except Exception as e:
            print(f"    {name}: failed ({e})")

    return tickers


# ── Batch download helper ─────────────────────────────────────────────
def download_batch(tickers, start, end, batch_size=50):
    """Download daily data for a list of tickers in batches."""
    all_data = {}
    total = len(tickers)

    for i in range(0, total, batch_size):
        batch = tickers[i:i+batch_size]
        batch_str = ' '.join(batch)
        try:
            data = yf.download(batch_str, start=start, end=end, interval='1d',
                             group_by='ticker', progress=False, threads=True)

            if len(batch) == 1:
                # Single ticker with group_by='ticker' returns a MultiIndex
                # (ticker on level 0, OHLC field on level 1). Flatten to the
                # level that actually holds 'Close' so df['Close'] etc. work.
                t = batch[0]
                if isinstance(data.columns, pd.MultiIndex):
                    lvl1 = data.columns.get_level_values(1)
                    data.columns = lvl1 if 'Close' in lvl1 else data.columns.get_level_values(0)
                data = data.dropna(how='all')
                if len(data) > 50:
                    all_data[t] = data
            else:
                for t in batch:
                    try:
                        ticker_data = data[t].dropna(how='all')
                        if len(ticker_data) > 50:
                            all_data[t] = ticker_data
                    except (KeyError, TypeError):
                        pass

        except Exception as e:
            pass

        # Progress
        done = min(i + batch_size, total)
        pct = done / total * 100
        print(f"\r  Downloaded {done}/{total} ({pct:.0f}%) — {len(all_data)} valid", end='', flush=True)

        if i + batch_size < total:
            time.sleep(0.5)

    print()
    return all_data


# ═══════════════════════════════════════════════════════════════════════
# MAIN SCAN
# ═══════════════════════════════════════════════════════════════════════

print("="*90)
print("ELLIOTT WAVE SCANNER — S&P 500 + Small/Mid Caps")
print("Strategy: Wave (2) deep-retrace entry (from ARM/ZETA framework)")
print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print("="*90)

# Get ticker lists
print("\nFetching ticker lists...")
sp500 = get_sp500_tickers()
print(f"  S&P 500: {len(sp500)} tickers")

smallcap = get_smallmid_tickers()
print(f"  Small/Mid caps: {len(smallcap)} tickers")

# Combine and deduplicate
all_tickers = list(set(sp500 + smallcap))
all_tickers.sort()
print(f"  Total unique tickers: {len(all_tickers)}")

# Download data (2 years for full wave detection)
print(f"\nDownloading daily data (2 years)...")
end_date = datetime.now()
start_date = end_date - timedelta(days=730)

all_data = download_batch(all_tickers, start_date, end_date, batch_size=50)
print(f"  Successfully downloaded: {len(all_data)} tickers")

# Scan each ticker
print(f"\nScanning for Wave (2) setups...")
all_candidates = []
errors = 0
scanned = 0

for ticker, df in all_data.items():
    scanned += 1
    if scanned % 100 == 0:
        print(f"\r  Scanned {scanned}/{len(all_data)} — {len(all_candidates)} candidates found", end='', flush=True)

    try:
        results = analyze_ticker(df, ticker)
        if results:
            all_candidates.extend(results)
    except Exception as e:
        errors += 1

print(f"\r  Scanned {scanned}/{len(all_data)} — {len(all_candidates)} candidates found")
print(f"  Errors: {errors}")

# Sort all candidates by score
all_candidates.sort(key=lambda x: x['score'], reverse=True)

# Deduplicate by ticker (keep best per ticker)
seen_tickers = set()
unique_candidates = []
for c in all_candidates:
    if c['ticker'] not in seen_tickers:
        unique_candidates.append(c)
        seen_tickers.add(c['ticker'])

# ═══════════════════════════════════════════════════════════════════════
# RESULTS
# ═══════════════════════════════════════════════════════════════════════

# Split by stage
at_entry = [c for c in unique_candidates if c['stage'] == 'AT_ENTRY']
early_w3 = [c for c in unique_candidates if c['stage'] == 'EARLY_W3']
mid_w3 = [c for c in unique_candidates if c['stage'] == 'MID_W3']

print(f"\n{'='*90}")
print(f"RESULTS SUMMARY")
print(f"{'='*90}")
print(f"  Total candidates: {len(unique_candidates)}")
print(f"  AT ENTRY (W2 bottom in last {ENTRY_WINDOW_DAYS} days): {len(at_entry)}")
print(f"  EARLY WAVE 3 (W2 bottom 22-60 days ago): {len(early_w3)}")
print(f"  MID WAVE 3 (W2 bottom 61-120 days ago): {len(mid_w3)}")

def print_candidates(candidates, header, limit=30):
    if not candidates:
        print(f"\n  No candidates in this category.")
        return

    print(f"\n{'─'*90}")
    print(f"  {header}")
    print(f"{'─'*90}")
    print(f"  {'Ticker':<8} {'Score':>5} {'Price':>8} {'Corr%':>6} {'W1%':>7} {'W2ret%':>7} {'Fib':>6} {'DaysW2':>7} {'T1(sub)':>9} {'T1(full)':>9} {'R:R':>6}")
    print(f"  {'─'*8} {'─'*5} {'─'*8} {'─'*6} {'─'*7} {'─'*7} {'─'*6} {'─'*7} {'─'*9} {'─'*9} {'─'*6}")

    for c in candidates[:limit]:
        # T1 targets
        t1_sub = c['ext_sub'].get(1.618, 0) if c['ext_sub'] else 0
        t1_full = c['ext_full'].get(1.0, 0)

        # R:R (risk = 5% below W2)
        risk = c['w2_price'] * 0.05
        reward = t1_full - c['current_price']
        rr = reward / risk if risk > 0 and reward > 0 else 0

        fib_label = f"{c['closest_fib'][0]:.0%}"

        print(f"  {c['ticker']:<8} {c['score']:>5.0f} {c['current_price']:>8.2f} {c['correction_pct']:>5.1f}% {c['wave1_pct']:>6.1f}% {c['wave2_retrace_pct']:>6.1f}% {fib_label:>6} {c['days_since_w2']:>5}d  {t1_sub:>9.2f} {t1_full:>9.2f} {rr:>5.1f}x")

    if len(candidates) > limit:
        print(f"\n  ... and {len(candidates) - limit} more")

print_candidates(at_entry, f"AT ENTRY — Wave (2) bottom within last {ENTRY_WINDOW_DAYS} days")
print_candidates(early_w3, "EARLY WAVE 3 — Recently entered (W2 bottom 22-60 days ago)")
print_candidates(mid_w3, "MID WAVE 3 — In progress (W2 bottom 61-120 days ago)")

# ═══════════════════════════════════════════════════════════════════════
# DETAILED VIEW — Top candidates
# ═══════════════════════════════════════════════════════════════════════

top_n = min(20, len(unique_candidates))
if top_n > 0:
    print(f"\n{'='*90}")
    print(f"DETAILED VIEW — Top {top_n} Candidates")
    print(f"{'='*90}")

    for i, c in enumerate(unique_candidates[:top_n]):
        risk = c['current_price'] - (c['w2_price'] * 0.95)
        stop = c['w2_price'] * 0.95

        print(f"\n  {'─'*80}")
        print(f"  #{i+1}  {c['ticker']}  |  Score: {c['score']:.0f}  |  Stage: {c['stage']}  |  ${c['current_price']:.2f}")
        print(f"  {'─'*80}")
        print(f"    Peak:     ${c['peak_price']:.2f} ({c['peak_date'].strftime('%Y-%m-%d')})")
        print(f"    Origin:   ${c['origin_price']:.2f} ({c['origin_date'].strftime('%Y-%m-%d')})")
        print(f"    Wave (1): ${c['w1_price']:.2f} ({c['w1_date'].strftime('%Y-%m-%d')})  +{c['wave1_pct']:.1f}%")
        print(f"    Wave (2): ${c['w2_price']:.2f} ({c['w2_date'].strftime('%Y-%m-%d')})  retrace: {c['wave2_retrace_pct']:.1f}% ({c['closest_fib'][0]:.1%} fib)")
        print(f"    Correction: {c['correction_pct']:.1f}% over {c['correction_days']} days")
        print(f"    Current:  ${c['current_price']:.2f} ({c['recovery_pct']:.1f}% above W2)  |  {c['days_since_w2']} days since W2")

        print(f"    Stop (5% below W2): ${stop:.2f}  |  Risk from current: ${risk:.2f} ({risk/c['current_price']*100:.1f}%)")

        if c['ext_sub']:
            sub_move = c['sub_w1']['move'] if c['sub_w1'] else 0
            print(f"    Sub-W1 targets (move=${sub_move:.2f}):")
            for ratio in [1.618, 2.0, 2.618]:
                if ratio in c['ext_sub']:
                    val = c['ext_sub'][ratio]
                    gain = ((val - c['current_price']) / c['current_price']) * 100
                    rr = (val - c['current_price']) / risk if risk > 0 else 0
                    print(f"      {ratio:.3f}x: ${val:.2f} (+{gain:.1f}%, R:R 1:{rr:.1f})")

        print(f"    Full-W1 targets (move=${c['wave1_move']:.2f}):")
        for ratio in [1.0, 1.618, 2.0]:
            val = c['ext_full'][ratio]
            gain = ((val - c['current_price']) / c['current_price']) * 100
            rr = (val - c['current_price']) / risk if risk > 0 else 0
            print(f"      {ratio:.3f}x: ${val:.2f} (+{gain:.1f}%, R:R 1:{rr:.1f})")

        print(f"    Avg Volume: {c['avg_volume']:,.0f}")

# ═══════════════════════════════════════════════════════════════════════
# CHART — Top candidates
# ═══════════════════════════════════════════════════════════════════════

chart_n = min(8, len(unique_candidates))
if chart_n > 0:
    print(f"\nGenerating chart for top {chart_n} candidates...")

    rows = (chart_n + 1) // 2
    fig, axes = plt.subplots(rows, 2, figsize=(24, 6 * rows))
    fig.suptitle(f'Elliott Wave Scanner — Top {chart_n} Candidates ({datetime.now().strftime("%Y-%m-%d")})',
                fontsize=16, fontweight='bold', y=0.98)

    if rows == 1:
        axes = [axes]

    for i, c in enumerate(unique_candidates[:chart_n]):
        ax = axes[i // 2][i % 2] if rows > 1 else axes[0][i % 2]
        ticker = c['ticker']

        if ticker in all_data:
            df = all_data[ticker]
            ax.plot(df.index, df['Close'], color='#555555', linewidth=0.8, alpha=0.8)
            ax.fill_between(df.index, df['Low'], df['High'], alpha=0.06, color='gray')

            # Wave structure
            wave_dates = [c['origin_date'], c['w1_date'], c['w2_date']]
            wave_prices = [c['origin_price'], c['w1_price'], c['w2_price']]
            wave_labels = ['Origin', '(1)', '(2)']

            ax.plot(wave_dates, wave_prices, color='#E65100', linewidth=2.5, alpha=0.85, zorder=5)
            for d, p, lbl in zip(wave_dates, wave_prices, wave_labels):
                offset = 12 if lbl == '(1)' else -14
                ax.annotate(lbl, (d, p), textcoords="offset points",
                           xytext=(0, offset), fontsize=10, fontweight='bold',
                           color='#E65100', ha='center', zorder=6,
                           bbox=dict(boxstyle='round,pad=0.2', facecolor='white',
                                    edgecolor='#E65100', alpha=0.9))

            # Fibonacci levels
            for fib_pct in [0.618, 0.786]:
                fib_val = c['w1_price'] - (fib_pct * c['wave1_move'])
                ax.axhline(y=fib_val, color='orange', linestyle=':', alpha=0.3, linewidth=0.8)

            # Extension targets
            for ratio in [1.0, 1.618]:
                val = c['ext_full'][ratio]
                ax.axhline(y=val, color='#1565C0', linestyle='--', alpha=0.3, linewidth=0.8)

            # Current price marker
            ax.axhline(y=c['current_price'], color='green', linestyle='-', alpha=0.3, linewidth=0.8)

            # Swings
            swings = find_swings(df, order=c['swing_order'])
            for s in swings:
                clr = '#2196F3' if s['type'] == 'high' else '#FF9800'
                mkr = 'v' if s['type'] == 'high' else '^'
                ax.scatter(s['date'], s['price'], color=clr, marker=mkr, s=15, zorder=3, alpha=0.35)

        fib_str = f"{c['closest_fib'][0]:.0%}"
        ax.set_title(f"{ticker} | Score:{c['score']:.0f} | {c['stage']} | W2ret:{c['wave2_retrace_pct']:.0f}%({fib_str}) | ${c['current_price']:.2f}",
                    fontsize=10, fontweight='bold')
        ax.set_ylabel('Price')
        ax.grid(True, alpha=0.2)
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %y'))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha='right', fontsize=8)

    # Hide empty subplots
    total_slots = rows * 2
    for i in range(chart_n, total_slots):
        axes[i // 2][i % 2].set_visible(False)

    plt.tight_layout(rect=[0, 0, 1, 0.97])
    output_path = '/Users/home/Desktop/Projects/elliot_wave/scanner_results.png'
    plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
    print(f"Chart saved to: {output_path}")

# Save results to JSON for further analysis
results_file = '/Users/home/Desktop/Projects/elliot_wave/scanner_results.json'
json_results = []
for c in unique_candidates[:50]:
    json_results.append({
        'ticker': c['ticker'],
        'score': c['score'],
        'stage': c['stage'],
        'current_price': float(c['current_price']),
        'peak_price': float(c['peak_price']),
        'peak_date': c['peak_date'].strftime('%Y-%m-%d'),
        'origin_price': float(c['origin_price']),
        'origin_date': c['origin_date'].strftime('%Y-%m-%d'),
        'w1_price': float(c['w1_price']),
        'w1_date': c['w1_date'].strftime('%Y-%m-%d'),
        'w2_price': float(c['w2_price']),
        'w2_date': c['w2_date'].strftime('%Y-%m-%d'),
        'correction_pct': float(c['correction_pct']),
        'wave1_pct': float(c['wave1_pct']),
        'wave2_retrace_pct': float(c['wave2_retrace_pct']),
        'closest_fib': f"{c['closest_fib'][0]:.0%}",
        'days_since_w2': c['days_since_w2'],
        'recovery_pct': float(c['recovery_pct']),
    })

with open(results_file, 'w') as f:
    json.dump(json_results, f, indent=2)
print(f"\nResults saved to: {results_file}")

print(f"\n{'='*90}")
print("SCAN COMPLETE")
print(f"{'='*90}")
