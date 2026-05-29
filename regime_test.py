#!/usr/bin/env python3
"""
Regime Filter Sweep — test dozens of market regime filters on the same setups.
Downloads data and finds setups once, then rapidly simulates each filter combo.
"""

import sys, os, time, webbrowser, warnings
from datetime import datetime, timedelta
from collections import defaultdict
from itertools import product

import numpy as np
import pandas as pd
import yfinance as yf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ew_scanner_v2 as scanner
from backtest import (
    download_all_data, find_setups_for_ticker,
    BACKTEST_START, BACKTEST_END, START_CAPITAL, POSITION_PCT, MAX_HOLD_DAYS
)

warnings.filterwarnings('ignore')


def download_regime_data():
    end = BACKTEST_END.strftime('%Y-%m-%d')
    start = (BACKTEST_START - timedelta(days=400)).strftime('%Y-%m-%d')

    spy = yf.Ticker('SPY').history(start=start, end=end, interval='1d')
    vix = yf.Ticker('^VIX').history(start=start, end=end, interval='1d')
    return spy, vix


def compute_regime_indicators(spy, vix):
    if spy.index.tz is not None:
        spy.index = spy.index.tz_localize(None)
    if not vix.empty and vix.index.tz is not None:
        vix.index = vix.index.tz_localize(None)
    ind = pd.DataFrame(index=spy.index)

    for p in [20, 50, 100, 150, 200]:
        ind[f'sma_{p}'] = spy['Close'].rolling(p).mean()
        ind[f'ema_{p}'] = spy['Close'].ewm(span=p).mean()
    ind['spy_close'] = spy['Close']

    delta = spy['Close'].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1/14, min_periods=14).mean()
    avg_loss = loss.ewm(alpha=1/14, min_periods=14).mean()
    ind['rsi'] = 100 - (100 / (1 + avg_gain / avg_loss))

    ema12 = spy['Close'].ewm(span=12).mean()
    ema26 = spy['Close'].ewm(span=26).mean()
    ind['macd'] = ema12 - ema26
    ind['macd_signal'] = ind['macd'].ewm(span=9).mean()
    ind['macd_hist'] = ind['macd'] - ind['macd_signal']

    ind['sma50_above_200'] = (ind['sma_50'] > ind['sma_200']).astype(int)
    ind['sma20_above_50'] = (ind['sma_20'] > ind['sma_50']).astype(int)

    ind['spy_above_sma50'] = (ind['spy_close'] > ind['sma_50']).astype(int)
    ind['spy_above_sma100'] = (ind['spy_close'] > ind['sma_100']).astype(int)
    ind['spy_above_sma150'] = (ind['spy_close'] > ind['sma_150']).astype(int)
    ind['spy_above_sma200'] = (ind['spy_close'] > ind['sma_200']).astype(int)
    ind['spy_above_ema20'] = (ind['spy_close'] > ind['ema_20']).astype(int)
    ind['spy_above_ema50'] = (ind['spy_close'] > ind['ema_50']).astype(int)

    dd_window = spy['Close'].rolling(50).max()
    ind['spy_dd_pct'] = (spy['Close'] - dd_window) / dd_window * 100

    if not vix.empty:
        vix_aligned = vix['Close'].reindex(ind.index, method='ffill')
        ind['vix'] = vix_aligned
    else:
        ind['vix'] = 20

    return ind


def build_filter_combos():
    combos = []

    combos.append(('BASELINE (no filter)', lambda ind, d: True))

    for p in [50, 100, 150, 200]:
        combos.append((f'SPY > SMA({p})', lambda ind, d, p=p: ind.loc[d, f'spy_close'] > ind.loc[d, f'sma_{p}']))

    for p in [20, 50]:
        combos.append((f'SPY > EMA({p})', lambda ind, d, p=p: ind.loc[d, f'spy_close'] > ind.loc[d, f'ema_{p}']))

    combos.append(('SMA(50) > SMA(200)', lambda ind, d: ind.loc[d, 'sma50_above_200'] == 1))
    combos.append(('SMA(20) > SMA(50)', lambda ind, d: ind.loc[d, 'sma20_above_50'] == 1))

    combos.append(('SMA(50)>SMA(200) + SPY>SMA(50)', lambda ind, d: ind.loc[d, 'sma50_above_200'] == 1 and ind.loc[d, 'spy_close'] > ind.loc[d, 'sma_50']))
    combos.append(('SMA(50)>SMA(200) + SPY>SMA(200)', lambda ind, d: ind.loc[d, 'sma50_above_200'] == 1 and ind.loc[d, 'spy_close'] > ind.loc[d, 'sma_200']))

    for thresh in [30, 40, 50]:
        combos.append((f'SPY RSI > {thresh}', lambda ind, d, t=thresh: ind.loc[d, 'rsi'] > t))

    combos.append(('MACD > 0', lambda ind, d: ind.loc[d, 'macd'] > 0))
    combos.append(('MACD hist > 0', lambda ind, d: ind.loc[d, 'macd_hist'] > 0))

    for v in [20, 25, 30, 35]:
        combos.append((f'VIX < {v}', lambda ind, d, v=v: ind.loc[d, 'vix'] < v))

    combos.append(('SPY>SMA(200) + RSI>40', lambda ind, d: ind.loc[d, 'spy_close'] > ind.loc[d, 'sma_200'] and ind.loc[d, 'rsi'] > 40))
    combos.append(('SPY>SMA(200) + RSI>50', lambda ind, d: ind.loc[d, 'spy_close'] > ind.loc[d, 'sma_200'] and ind.loc[d, 'rsi'] > 50))
    combos.append(('SPY>SMA(200) + MACD>0', lambda ind, d: ind.loc[d, 'spy_close'] > ind.loc[d, 'sma_200'] and ind.loc[d, 'macd'] > 0))
    combos.append(('SPY>SMA(200) + VIX<25', lambda ind, d: ind.loc[d, 'spy_close'] > ind.loc[d, 'sma_200'] and ind.loc[d, 'vix'] < 25))
    combos.append(('SPY>SMA(200) + VIX<30', lambda ind, d: ind.loc[d, 'spy_close'] > ind.loc[d, 'sma_200'] and ind.loc[d, 'vix'] < 30))

    combos.append(('SPY>SMA(50) + RSI>40', lambda ind, d: ind.loc[d, 'spy_close'] > ind.loc[d, 'sma_50'] and ind.loc[d, 'rsi'] > 40))
    combos.append(('SPY>SMA(50) + RSI>50', lambda ind, d: ind.loc[d, 'spy_close'] > ind.loc[d, 'sma_50'] and ind.loc[d, 'rsi'] > 50))
    combos.append(('SPY>SMA(50) + MACD>0', lambda ind, d: ind.loc[d, 'spy_close'] > ind.loc[d, 'sma_50'] and ind.loc[d, 'macd'] > 0))
    combos.append(('SPY>SMA(50) + VIX<25', lambda ind, d: ind.loc[d, 'spy_close'] > ind.loc[d, 'sma_50'] and ind.loc[d, 'vix'] < 25))

    combos.append(('SPY>EMA(20) + MACD hist>0', lambda ind, d: ind.loc[d, 'spy_close'] > ind.loc[d, 'ema_20'] and ind.loc[d, 'macd_hist'] > 0))
    combos.append(('SPY>SMA(200) + MACD hist>0', lambda ind, d: ind.loc[d, 'spy_close'] > ind.loc[d, 'sma_200'] and ind.loc[d, 'macd_hist'] > 0))

    combos.append(('Golden Cross + RSI>40', lambda ind, d: ind.loc[d, 'sma50_above_200'] == 1 and ind.loc[d, 'rsi'] > 40))
    combos.append(('Golden Cross + VIX<25', lambda ind, d: ind.loc[d, 'sma50_above_200'] == 1 and ind.loc[d, 'vix'] < 25))
    combos.append(('Golden Cross + MACD>0', lambda ind, d: ind.loc[d, 'sma50_above_200'] == 1 and ind.loc[d, 'macd'] > 0))
    combos.append(('Golden Cross + RSI>40 + VIX<30', lambda ind, d: ind.loc[d, 'sma50_above_200'] == 1 and ind.loc[d, 'rsi'] > 40 and ind.loc[d, 'vix'] < 30))

    combos.append(('SPY>SMA(200) + RSI>40 + VIX<30', lambda ind, d: ind.loc[d, 'spy_close'] > ind.loc[d, 'sma_200'] and ind.loc[d, 'rsi'] > 40 and ind.loc[d, 'vix'] < 30))
    combos.append(('SPY>SMA(200) + RSI>40 + MACD>0', lambda ind, d: ind.loc[d, 'spy_close'] > ind.loc[d, 'sma_200'] and ind.loc[d, 'rsi'] > 40 and ind.loc[d, 'macd'] > 0))
    combos.append(('SPY>SMA(200) + MACD>0 + VIX<25', lambda ind, d: ind.loc[d, 'spy_close'] > ind.loc[d, 'sma_200'] and ind.loc[d, 'macd'] > 0 and ind.loc[d, 'vix'] < 25))
    combos.append(('SPY>SMA(50) + RSI>40 + VIX<25', lambda ind, d: ind.loc[d, 'spy_close'] > ind.loc[d, 'sma_50'] and ind.loc[d, 'rsi'] > 40 and ind.loc[d, 'vix'] < 25))
    combos.append(('SPY>SMA(50) + RSI>50 + MACD>0', lambda ind, d: ind.loc[d, 'spy_close'] > ind.loc[d, 'sma_50'] and ind.loc[d, 'rsi'] > 50 and ind.loc[d, 'macd'] > 0))

    combos.append(('SPY drawdown < 5%', lambda ind, d: ind.loc[d, 'spy_dd_pct'] > -5))
    combos.append(('SPY drawdown < 10%', lambda ind, d: ind.loc[d, 'spy_dd_pct'] > -10))
    combos.append(('SPY>SMA(200) + DD<5%', lambda ind, d: ind.loc[d, 'spy_close'] > ind.loc[d, 'sma_200'] and ind.loc[d, 'spy_dd_pct'] > -5))

    combos.append(('SPY>SMA(150) + RSI>40', lambda ind, d: ind.loc[d, 'spy_close'] > ind.loc[d, 'sma_150'] and ind.loc[d, 'rsi'] > 40))
    combos.append(('SPY>SMA(150) + VIX<25', lambda ind, d: ind.loc[d, 'spy_close'] > ind.loc[d, 'sma_150'] and ind.loc[d, 'vix'] < 25))
    combos.append(('SPY>SMA(100) + RSI>40 + VIX<30', lambda ind, d: ind.loc[d, 'spy_close'] > ind.loc[d, 'sma_100'] and ind.loc[d, 'rsi'] > 40 and ind.loc[d, 'vix'] < 30))

    return combos


def run_sim_with_filter(all_setups, daily_data, regime_ind, regime_fn):
    setups = all_setups.copy()
    setups.sort(key=lambda x: x['signal_date'])

    ref_ticker = 'SPY' if 'SPY' in daily_data else next(iter(daily_data))
    ref_dates = daily_data[ref_ticker].index
    bt_dates = sorted([d for d in ref_dates if BACKTEST_START <= d <= BACKTEST_END])

    trades = []
    open_trades = {}
    equity_curve = []
    setup_ptr = 0
    max_concurrent = 0
    skipped = 0

    for date in bt_dates:
        closed = []
        for tk, tr in open_trades.items():
            df = daily_data.get(tk)
            if df is None or date not in df.index:
                continue
            loc = df.index.get_loc(date)
            hi = float(df['High'].iloc[loc])
            lo = float(df['Low'].iloc[loc])
            cl = float(df['Close'].iloc[loc])
            if hi > tr['max_price']:
                tr['max_price'] = hi

            e, r = tr['entry_price'], tr['risk']
            if tr['stage'] < 2 and tr['max_price'] >= e + 0.5 * r:
                tr['current_stop'] = max(tr['current_stop'], e - 0.5 * r); tr['stage'] = 2
            if tr['stage'] < 3 and tr['max_price'] >= e + r:
                tr['current_stop'] = max(tr['current_stop'], e); tr['stage'] = 3
            if tr['stage'] < 4 and tr['max_price'] >= e + 1.5 * r:
                tr['current_stop'] = max(tr['current_stop'], e + 0.5 * r); tr['stage'] = 4

            hd = (date - tr['entry_date']).days

            if lo <= tr['current_stop']:
                pnl = (tr['current_stop'] - e) * tr['shares']
                tr.update(exit_date=date, exit_price=tr['current_stop'], reason='STOP',
                          pnl=pnl, pnl_pct=pnl/tr['trade_size']*100, hold_days=hd)
                trades.append(dict(tr)); closed.append(tk); continue

            if hi >= tr['t2'] and tr['pos'] == 1.0:
                pnl = (tr['t2'] - e) * tr['shares']
                tr.update(exit_date=date, exit_price=tr['t2'], reason='T2',
                          pnl=pnl, pnl_pct=pnl/tr['trade_size']*100, hold_days=hd)
                trades.append(dict(tr)); closed.append(tk); continue

            if hd >= MAX_HOLD_DAYS:
                pnl = (cl - e) * tr['shares']
                tr.update(exit_date=date, exit_price=cl, reason='MAX_HOLD',
                          pnl=pnl, pnl_pct=pnl/tr['trade_size']*100, hold_days=hd)
                trades.append(dict(tr)); closed.append(tk); continue

        for tk in closed:
            del open_trades[tk]

        realized_so_far = sum(t['pnl'] for t in trades)
        portfolio_value = START_CAPITAL + realized_so_far
        trade_size = portfolio_value * POSITION_PCT

        while setup_ptr < len(setups) and setups[setup_ptr]['signal_date'] <= date:
            s = setups[setup_ptr]; setup_ptr += 1
            tk = s['ticker']
            if tk in open_trades:
                continue

            # REGIME FILTER — skip entry if market conditions don't pass
            try:
                lookup = date
                if date not in regime_ind.index:
                    idx = regime_ind.index.get_indexer([date], method='ffill')[0]
                    if idx < 0:
                        skipped += 1; continue
                    lookup = regime_ind.index[idx]
                if not regime_fn(regime_ind, lookup):
                    skipped += 1
                    continue
            except Exception as ex:
                skipped += 1
                continue

            open_trades[tk] = {
                'ticker': tk, 'setup_type': s['setup_type'],
                'entry_date': s['signal_date'], 'entry_price': s['entry'],
                'stop': s['stop'], 't1': s['t1'], 't2': s['t2'],
                'risk': s['risk'], 'score': s['score'],
                'trade_size': trade_size,
                'shares': trade_size / s['entry'], 'pos': 1.0,
                'realized': 0.0, 'current_stop': s['stop'],
                'max_price': s['entry'], 'stage': 1,
            }

        if len(open_trades) > max_concurrent:
            max_concurrent = len(open_trades)

        realized_total = sum(t['pnl'] for t in trades)
        unrealized = 0
        for tk, tr in open_trades.items():
            df = daily_data.get(tk)
            if df is None or date not in df.index:
                continue
            cl = float(df.loc[date, 'Close'])
            unrealized += (cl - tr['entry_price']) * tr['shares']

        equity_curve.append({
            'date': date, 'equity': START_CAPITAL + realized_total + unrealized,
            'open': len(open_trades),
        })

    for tk, tr in list(open_trades.items()):
        df = daily_data.get(tk)
        if df is None: continue
        cl = float(df['Close'].iloc[-1])
        hd = (bt_dates[-1] - tr['entry_date']).days
        pnl = (cl - tr['entry_price']) * tr['shares']
        tr.update(exit_date=bt_dates[-1], exit_price=cl, reason='BT_END',
                  pnl=pnl, pnl_pct=pnl/tr['trade_size']*100, hold_days=hd)
        trades.append(dict(tr))

    return trades, equity_curve, max_concurrent, skipped


def quick_stats(trades, equity_curve):
    if not trades or len(trades) < 5:
        return None
    pnls = [t['pnl'] for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]

    eq = pd.Series([e['equity'] for e in equity_curve], index=[e['date'] for e in equity_curve])
    daily_ret = eq.pct_change().dropna()
    sharpe = float(daily_ret.mean() / daily_ret.std() * np.sqrt(252)) if daily_ret.std() > 0 else 0

    running_max = eq.cummax()
    drawdown = (eq - running_max) / running_max
    max_dd = float(drawdown.min()) * 100

    total_return = (eq.iloc[-1] - START_CAPITAL) / START_CAPITAL * 100
    days = (equity_curve[-1]['date'] - equity_curve[0]['date']).days
    ann_return = ((1 + total_return/100) ** (365/days) - 1) * 100 if days > 0 else 0

    pf = abs(sum(wins)/sum(losses)) if losses and sum(losses) != 0 else float('inf')

    avg_hold = np.mean([t['hold_days'] for t in trades])
    avg_capital = len(trades) * (START_CAPITAL * POSITION_PCT) * avg_hold / max(days, 1)
    roi_deployed = (sum(pnls) / avg_capital * 100) if avg_capital > 0 else 0

    return {
        'total_return': total_return,
        'ann_return': ann_return,
        'sharpe': sharpe,
        'max_dd': max_dd,
        'win_rate': len(wins)/len(trades)*100,
        'profit_factor': pf,
        'trades': len(trades),
        'max_concurrent': max(e['open'] for e in equity_curve),
        'avg_hold': avg_hold,
        'roi_deployed': roi_deployed,
    }


def generate_results_html(results, filename='regime_results.html'):
    results.sort(key=lambda x: x['stats']['sharpe'] if x['stats'] else -999, reverse=True)

    rows = ''
    for i, r in enumerate(results):
        s = r['stats']
        if s is None:
            continue
        rank_class = ''
        if i < 3: rank_class = 'top3'
        elif i < 10: rank_class = 'top10'

        rows += f"""<tr class="{rank_class}">
<td>{i+1}</td><td>{r['name']}</td>
<td>{s['trades']}</td><td>{r['skipped']}</td>
<td>{s['total_return']:.1f}%</td><td>{s['ann_return']:.1f}%</td>
<td>{s['sharpe']:.2f}</td><td>{s['max_dd']:.1f}%</td>
<td>{s['win_rate']:.1f}%</td><td>{s['profit_factor']:.2f}</td>
<td>{s['roi_deployed']:.1f}%</td><td>{s['max_concurrent']}</td>
<td>{s['avg_hold']:.0f}d</td>
</tr>\n"""

    baseline = next((r for r in results if 'BASELINE' in r['name']), None)
    bl_note = ''
    if baseline and baseline['stats']:
        bs = baseline['stats']
        bl_note = f"Baseline: {bs['total_return']:.1f}% return, {bs['sharpe']:.2f} Sharpe, {bs['max_dd']:.1f}% max DD, {bs['trades']} trades"

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Regime Filter Sweep</title>
<style>
body {{ background:#1a1a2e; color:#e0e0e0; font-family:'Segoe UI',system-ui,sans-serif; padding:20px; }}
h1 {{ color:#00d4ff; text-align:center; }}
.subtitle {{ color:#888; text-align:center; margin-bottom:30px; }}
table {{ border-collapse:collapse; width:100%; margin:20px auto; }}
th {{ background:#16213e; color:#00d4ff; padding:10px 8px; text-align:right; border-bottom:2px solid #0f3460; position:sticky; top:0; }}
th:nth-child(1), th:nth-child(2) {{ text-align:left; }}
td {{ padding:8px; text-align:right; border-bottom:1px solid #1a1a3e; }}
td:nth-child(1), td:nth-child(2) {{ text-align:left; }}
tr:hover {{ background:#16213e; }}
tr.top3 {{ background:#0a2a1a; }}
tr.top3:hover {{ background:#0d3520; }}
tr.top10 {{ background:#1a1a3e; }}
.note {{ color:#888; text-align:center; font-size:0.9em; margin-top:20px; }}
</style></head>
<body>
<h1>Regime Filter Sweep — {len(results)} Combinations</h1>
<p class="subtitle">{BACKTEST_START.strftime('%b %Y')} — {BACKTEST_END.strftime('%b %Y')} · $1M · 1%/trade · 100% exit at T2 · Sorted by Sharpe</p>
<p class="subtitle">{bl_note}</p>
<table>
<tr><th>#</th><th>Filter</th><th>Trades</th><th>Skipped</th><th>Return</th><th>Ann.</th><th>Sharpe</th><th>MaxDD</th><th>Win%</th><th>PF</th><th>ROI Deployed</th><th>MaxConc</th><th>AvgHold</th></tr>
{rows}
</table>
<p class="note">Top 3 highlighted green · Top 10 highlighted blue · ROI Deployed = return on average capital actually at risk</p>
</body></html>"""

    with open(filename, 'w') as f:
        f.write(html)
    return filename


def main():
    t0 = time.time()
    print("=" * 70)
    print("  REGIME FILTER SWEEP")
    print(f"  Period: {BACKTEST_START.strftime('%Y-%m-%d')} to {BACKTEST_END.strftime('%Y-%m-%d')}")
    print("=" * 70)

    print("\nPhase 1: Downloading regime data (SPY, VIX)...")
    spy, vix = download_regime_data()
    regime_ind = compute_regime_indicators(spy, vix)
    print(f"  SPY: {len(spy)} bars, VIX: {len(vix)} bars")

    print("\nPhase 2: Downloading ticker data...")
    daily_data, weekly_data = download_all_data()

    print(f"\nPhase 3: Finding setups across {len(daily_data)} tickers...")
    all_setups = []
    done = 0
    for ticker in daily_data:
        wdf = weekly_data.get(ticker)
        try:
            setups = find_setups_for_ticker(ticker, daily_data[ticker], wdf)
            all_setups.extend(setups)
        except Exception:
            pass
        done += 1
        if done % 200 == 0:
            print(f"\r  Scanned {done}/{len(daily_data)} tickers ({len(all_setups)} setups found)", end='', flush=True)
    print(f"\r  Scanned {done}/{len(daily_data)} tickers — {len(all_setups)} total setups")

    combos = build_filter_combos()
    print(f"\nPhase 4: Testing {len(combos)} regime filter combinations...")

    results = []
    for i, (name, fn) in enumerate(combos):
        trades, eq, max_conc, skipped = run_sim_with_filter(all_setups, daily_data, regime_ind, fn)
        stats = quick_stats(trades, eq) if eq else None
        results.append({'name': name, 'stats': stats, 'skipped': skipped})
        ret = f"{stats['total_return']:.1f}%" if stats else "N/A"
        sh = f"{stats['sharpe']:.2f}" if stats else "N/A"
        print(f"\r  [{i+1}/{len(combos)}] {name:50s} → {ret:>8s}  Sharpe={sh}", flush=True)

    print(f"\nPhase 5: Generating report...")
    fname = generate_results_html(results)
    print(f"  Saved to {fname}")

    elapsed = time.time() - t0
    print(f"\n  Done in {elapsed/60:.1f} minutes")
    webbrowser.open('file://' + os.path.abspath(fname))


if __name__ == '__main__':
    main()
