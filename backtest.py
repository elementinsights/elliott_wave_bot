#!/usr/bin/env python3
"""
Aleks EWT Scanner v2 — 3-Year Walk-Forward Backtest
1% of portfolio per trade (compounding), no duplicate positions, 100% exit at T2.
Every entry decision is causal (no look-ahead): swing structure, weekly trend, and
indicators are all evaluated using only data available at/before the entry bar.
"""

import sys, os, time, webbrowser, base64, warnings
from datetime import datetime, timedelta
from io import BytesIO
from collections import defaultdict

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ew_scanner_v2 as scanner

warnings.filterwarnings('ignore')

# ─── CONFIG ──────────────────────────────────────────────────────────
POSITION_PCT = 0.01  # 1% of portfolio per trade
START_CAPITAL = 1_000_000
BACKTEST_END = pd.Timestamp(datetime.now().strftime('%Y-%m-%d'))
BACKTEST_START = BACKTEST_END - pd.DateOffset(years=3)
SWING_CONFIRM_BARS = 12
MAX_HOLD_DAYS = 180
MIN_SCORE_BT = 95


def download_all_data():
    print("Phase 1: Building universe...")
    sp500 = scanner.get_sp500_tickers()
    smallmid = scanner.get_smallmid_tickers()
    try:
        all_traded = scanner.get_all_traded_tickers()
    except Exception:
        all_traded = []
    universe = list(set(sp500 + smallmid + all_traded + scanner.CURATED_ETFS))
    print(f"  {len(universe)} unique tickers")

    end = BACKTEST_END.strftime('%Y-%m-%d')
    scr_start = (BACKTEST_END - timedelta(days=35)).strftime('%Y-%m-%d')
    print("\nPhase 2: Quick screen (1-month)...")
    scr = scanner.download_batch(universe, scr_start, end, interval='1d', min_bars=10)

    viable = []
    for t, df in scr.items():
        try:
            p = float(df['Close'].iloc[-1])
            if p < scanner.MIN_PRICE or p > scanner.MAX_PRICE:
                continue
            if p * float(df['Volume'].tail(20).mean()) < 1_000_000:
                continue
            viable.append(t)
        except Exception:
            pass
    print(f"  {len(viable)} viable tickers")

    daily_start = (BACKTEST_START - timedelta(days=365)).strftime('%Y-%m-%d')
    weekly_start = (BACKTEST_START - timedelta(days=1825)).strftime('%Y-%m-%d')
    print(f"\nPhase 3: Full history download ({daily_start} → {end})...")
    daily = scanner.download_batch(viable, daily_start, end, interval='1d', min_bars=100)
    weekly = scanner.download_batch(viable, weekly_start, end, interval='1wk', min_bars=40)

    missing = [t for t in viable if t not in daily]
    if missing:
        print(f"  Retrying {len(missing)} tickers individually (recent IPOs)...")
        import yfinance as yf
        for t in missing:
            try:
                tk = yf.Ticker(t)
                df = tk.history(period='max', interval='1d')
                if len(df) >= 100:
                    df.columns = [c if isinstance(c, str) else c[0] for c in df.columns]
                    daily[t] = df
                    wk = tk.history(period='max', interval='1wk')
                    if len(wk) >= 40:
                        wk.columns = [c if isinstance(c, str) else c[0] for c in wk.columns]
                        weekly[t] = wk
            except Exception:
                pass
        print(f"  Recovered {len([t for t in missing if t in daily])} tickers")

    print("\nPhase 4: Universe filters...")
    filtered = scanner.apply_universe_filters(daily)
    print(f"  {len(filtered)} tickers pass all filters")
    return filtered, weekly


def find_setups_for_ticker(ticker, daily_df, weekly_df):
    """Walk-forward setup search: every entry decision uses only data available
    at (or before) the entry bar — causal swing detection, causal weekly trend,
    and causal indicators — so there is no look-ahead bias.

    Full-history swings are used ONLY to cheaply enumerate candidate W2-bottom
    locations; each candidate is then re-derived and validated causally."""
    full_swings = scanner.detect_swings(daily_df)
    if len(full_swings) < 3:
        return []

    # RSI/MACD/Stoch/ATR are EWM/rolling (backward-looking), so slicing the
    # full-history series to [:bi+1] yields the same values a causal recompute would.
    indicators = scanner.calculate_indicators(daily_df)
    setups = []
    seen = set()

    # ── Wave 3 ──
    for i in range(len(full_swings) - 2):
        if (full_swings[i]['type'] != 'low' or full_swings[i+1]['type'] != 'high'
                or full_swings[i+2]['type'] != 'low'):
            continue
        w2b_idx_full = full_swings[i+2]['idx']
        sig_idx = w2b_idx_full + SWING_CONFIRM_BARS
        if sig_idx >= len(daily_df):
            continue

        for bi in range(sig_idx, min(sig_idx + 90, len(daily_df))):
            bd = daily_df.index[bi]
            if bd < BACKTEST_START or bd > BACKTEST_END:
                continue

            # ---- CAUSAL: re-detect the wave structure from data up to the entry bar ----
            cswings = scanner.detect_swings(daily_df.iloc[:bi+1])
            if len(cswings) < 3:
                break
            if (cswings[-1]['type'] != 'low' or cswings[-2]['type'] != 'high'
                    or cswings[-3]['type'] != 'low'):
                break  # no valid low-high-low established yet at this bar
            w1o, w1p, w2b = cswings[-3], cswings[-2], cswings[-1]
            # The causally-confirmed low must be the same W2 bottom we enumerated.
            if abs(w2b['idx'] - w2b_idx_full) > SWING_CONFIRM_BARS:
                break

            key = ('W3', w1o['idx'], w2b['idx'])
            if key in seen:
                break

            w1_move = w1p['price'] - w1o['price']
            if w1_move <= 0 or w1_move / w1o['price'] < 0.10:
                break
            ok, _ = scanner.validate_cardinal_rules(w1o['price'], w1p['price'], w2b['price'])
            if not ok:
                break
            w2_ret = (w1p['price'] - w2b['price']) / w1_move
            fd = scanner.fib_distance(w2_ret, scanner.FIB_W2_IMPULSE)
            if fd > scanner.FIB_TOLERANCE:
                break

            # Causal weekly trend — only weekly bars on or before the entry date.
            wk_hist = weekly_df[weekly_df.index <= bd] if weekly_df is not None else None
            weekly_info = scanner.count_weekly_waves(wk_hist)
            if weekly_info['trend'] == 'BEARISH':
                break

            ep = float(daily_df['Close'].iloc[bi])
            rec = (ep - w2b['price']) / w2b['price'] * 100
            if rec < -5 or rec > 80:
                break
            stop = w2b['price'] * (1 - scanner.STOP_BUFFER)
            risk = ep - stop
            if risk <= 0:
                break
            rp = risk / ep * 100
            if rp < scanner.MIN_RISK_PCT or rp > scanner.MAX_RISK_PCT:
                break
            t1 = w2b['price'] + w1_move
            t2 = w1p['price']
            t3 = w2b['price'] + 1.618 * w1_move
            if t1 <= ep: t1 = t2
            if t2 <= ep: t2 = t3
            if t2 < t1: t2 = t1 * 1.05
            rr = (t1 - ep) / risk
            if rr < scanner.MIN_RR_T1:
                break

            ch = scanner.calculate_channel(
                (w1o['idx'], w1o['price']), (w2b['idx'], w2b['price']),
                (w1p['idx'], w1p['price']), bi + 1)
            ch_pos = None
            if ch:
                sp = ch['upper_at_current'] - ch['lower_at_current']
                if sp > 0: ch_pos = (ep - ch['lower_at_current']) / sp

            cand = {
                'ticker': ticker, 'setup_type': 'WAVE_3',
                'fib_distance': fd, 'rr_t1': rr,
                'days_since_w2': (bd - w2b['date']).days,
                'weekly_trend': weekly_info['trend'], 'weekly_info': weekly_info,
                'channel': ch, 'channel_position': ch_pos,
            }
            ind_at = {k: v.iloc[:bi+1] for k, v in indicators.items()}
            sc = scanner.score_candidate(cand, ind_at, weekly_info['trend'], daily_df.iloc[:bi+1])
            if sc >= MIN_SCORE_BT:
                seen.add(key)
                setups.append({
                    'ticker': ticker, 'setup_type': 'WAVE_3',
                    'signal_date': bd, 'signal_idx': bi,
                    'entry': ep, 'stop': stop, 't1': t1, 't2': t2,
                    'risk': risk, 'risk_pct': rp, 'rr_t1': rr, 'score': sc,
                })
            break  # only evaluate the first in-range bar for this pattern

    return setups


def run_simulation(all_setups, daily_data):
    all_setups.sort(key=lambda x: x['signal_date'])

    ref_ticker = 'SPY' if 'SPY' in daily_data else next(iter(daily_data))
    ref_dates = daily_data[ref_ticker].index
    bt_dates = sorted([d for d in ref_dates if BACKTEST_START <= d <= BACKTEST_END])

    trades = []
    open_trades = {}
    equity_curve = []
    setup_ptr = 0
    max_concurrent = 0

    for date in bt_dates:
        # Close trades first
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

        # Enter new trades — 1% of realized portfolio value
        realized_so_far = sum(t['pnl'] for t in trades)
        portfolio_value = START_CAPITAL + realized_so_far
        trade_size = portfolio_value * POSITION_PCT

        while setup_ptr < len(all_setups) and all_setups[setup_ptr]['signal_date'] <= date:
            s = all_setups[setup_ptr]; setup_ptr += 1
            tk = s['ticker']
            if tk in open_trades:
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

        # Equity
        realized_total = sum(t['pnl'] for t in trades)
        unrealized = 0
        for tk, tr in open_trades.items():
            df = daily_data.get(tk)
            if df is None or date not in df.index:
                continue
            cl = float(df.loc[date, 'Close'])
            unrealized += (cl - tr['entry_price']) * tr['shares']

        equity_curve.append({
            'date': date,
            'equity': START_CAPITAL + realized_total + unrealized,
            'open': len(open_trades),
        })

    # Close remaining at end
    for tk, tr in list(open_trades.items()):
        df = daily_data.get(tk)
        if df is None: continue
        cl = float(df['Close'].iloc[-1])
        hd = (bt_dates[-1] - tr['entry_date']).days
        pnl = (cl - tr['entry_price']) * tr['shares']
        tr.update(exit_date=bt_dates[-1], exit_price=cl, reason='BT_END',
                  pnl=pnl, pnl_pct=pnl/tr['trade_size']*100, hold_days=hd)
        trades.append(dict(tr))

    return trades, equity_curve, max_concurrent


def compute_stats(trades, equity_curve):
    if not trades:
        return {}
    pnls = [t['pnl'] for t in trades]
    pnl_pcts = [t['pnl_pct'] for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]

    eq = pd.Series([e['equity'] for e in equity_curve],
                    index=[e['date'] for e in equity_curve])
    daily_ret = eq.pct_change().dropna()
    sharpe = float(daily_ret.mean() / daily_ret.std() * np.sqrt(252)) if daily_ret.std() > 0 else 0

    running_max = eq.cummax()
    drawdown = (eq - running_max) / running_max
    max_dd = float(drawdown.min()) * 100

    total_return = (eq.iloc[-1] - START_CAPITAL) / START_CAPITAL * 100
    days = (equity_curve[-1]['date'] - equity_curve[0]['date']).days
    ann_return = ((1 + total_return/100) ** (365/days) - 1) * 100 if days > 0 else 0

    hold_days = [t['hold_days'] for t in trades]

    by_type = defaultdict(list)
    for t in trades:
        by_type[t['setup_type']].append(t)

    type_stats = {}
    for st, tl in by_type.items():
        w = [t['pnl'] for t in tl if t['pnl'] > 0]
        l = [t['pnl'] for t in tl if t['pnl'] <= 0]
        type_stats[st] = {
            'count': len(tl),
            'win_rate': len(w)/len(tl)*100 if tl else 0,
            'avg_pnl': np.mean([t['pnl'] for t in tl]),
            'total_pnl': sum(t['pnl'] for t in tl),
        }

    # Monthly returns
    monthly = defaultdict(float)
    for t in trades:
        key = t['exit_date'].strftime('%Y-%m') if hasattr(t['exit_date'], 'strftime') else str(t['exit_date'])[:7]
        monthly[key] += t['pnl']

    return {
        'total_trades': len(trades),
        'total_pnl': sum(pnls),
        'total_return': total_return,
        'ann_return': ann_return,
        'sharpe': sharpe,
        'max_dd': max_dd,
        'win_rate': len(wins)/len(trades)*100,
        'avg_win': np.mean(wins) if wins else 0,
        'avg_loss': np.mean(losses) if losses else 0,
        'max_win': max(pnls),
        'max_loss': min(pnls),
        'profit_factor': abs(sum(wins)/sum(losses)) if losses and sum(losses) != 0 else float('inf'),
        'avg_hold': np.mean(hold_days),
        'median_hold': np.median(hold_days),
        'max_concurrent': max(e['open'] for e in equity_curve),
        'avg_pnl_pct': np.mean(pnl_pcts),
        'type_stats': type_stats,
        'monthly': dict(sorted(monthly.items())),
    }


def make_chart(equity_curve):
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 8), height_ratios=[3, 1],
                                     gridspec_kw={'hspace': 0.3})
    dates = [e['date'] for e in equity_curve]
    eq = [e['equity'] for e in equity_curve]

    ax1.plot(dates, eq, color='#00ff88', linewidth=1.2)
    ax1.fill_between(dates, START_CAPITAL, eq, alpha=0.1,
                      where=[e >= START_CAPITAL for e in eq], color='#00ff88')
    ax1.fill_between(dates, START_CAPITAL, eq, alpha=0.1,
                      where=[e < START_CAPITAL for e in eq], color='#ff4444')
    ax1.axhline(y=START_CAPITAL, color='gray', linestyle='--', alpha=0.3)
    ax1.set_title('Equity Curve', color='white', fontsize=14)
    ax1.set_ylabel('Portfolio Value ($)', color='gray')
    ax1.set_facecolor('#1a1a2e')
    ax1.tick_params(colors='gray')
    ax1.grid(alpha=0.1)

    opens = [e['open'] for e in equity_curve]
    ax2.fill_between(dates, 0, opens, color='#ff9900', alpha=0.5)
    ax2.set_title('Open Positions', color='white', fontsize=11)
    ax2.set_ylabel('Count', color='gray')
    ax2.set_facecolor('#1a1a2e')
    ax2.tick_params(colors='gray')
    ax2.grid(alpha=0.1)

    fig.patch.set_facecolor('#0f0f23')
    buf = BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor='#0f0f23')
    plt.close()
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()


def generate_html(trades, equity_curve, stats, filename='backtest_results.html'):
    chart_b64 = make_chart(equity_curve)

    pos = 'color:#00ff88'
    neg = 'color:#ff4444'
    def clr(v): return pos if v >= 0 else neg

    # Top trades
    best = sorted(trades, key=lambda t: t['pnl'], reverse=True)[:10]
    worst = sorted(trades, key=lambda t: t['pnl'])[:10]

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>EWT Scanner v2 — 3-Year Backtest</title>
<style>
body {{ font-family:-apple-system,Helvetica,Arial,sans-serif; background:#0f0f23; color:#e0e0e0; padding:30px 50px; }}
h1 {{ color:#ff9900; margin-bottom:5px; }}
h2 {{ color:#ff9900; margin-top:30px; border-bottom:1px solid #2a2a4e; padding-bottom:8px; }}
.subtitle {{ color:#888; margin-bottom:30px; }}
table {{ border-collapse:collapse; width:100%; margin:15px 0; }}
th {{ background:#1a1a3e; color:#ff9900; padding:10px 12px; text-align:left; font-size:13px; }}
td {{ padding:8px 12px; border-bottom:1px solid #1a1a3e; font-size:13px; }}
tr:hover {{ background:#1a1a2e; }}
.cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:15px; margin:20px 0; }}
.card {{ background:#1a1a2e; border-radius:8px; padding:18px; text-align:center; }}
.card .label {{ color:#888; font-size:12px; text-transform:uppercase; }}
.card .value {{ font-size:24px; font-weight:bold; margin-top:5px; }}
.pos {{ color:#00ff88; }} .neg {{ color:#ff4444; }} .neu {{ color:#ff9900; }}
img {{ width:100%; border-radius:8px; margin:15px 0; }}
</style></head><body>
<h1>Aleks EWT Scanner v2 — 3-Year Backtest</h1>
<p class="subtitle">{BACKTEST_START.strftime('%b %Y')} — {BACKTEST_END.strftime('%b %Y')} · 1% per trade (compounding) · 100% exit at T2 · ${START_CAPITAL:,.0f} start · {stats['total_trades']} trades</p>

<div class="cards">
<div class="card"><div class="label">Total Return</div><div class="value {'pos' if stats['total_return']>=0 else 'neg'}">{stats['total_return']:+.1f}%</div></div>
<div class="card"><div class="label">Annualized Return</div><div class="value {'pos' if stats['ann_return']>=0 else 'neg'}">{stats['ann_return']:+.1f}%</div></div>
<div class="card"><div class="label">Sharpe Ratio</div><div class="value neu">{stats['sharpe']:.2f}</div></div>
<div class="card"><div class="label">Max Drawdown</div><div class="value neg">{stats['max_dd']:.1f}%</div></div>
<div class="card"><div class="label">Win Rate</div><div class="value neu">{stats['win_rate']:.1f}%</div></div>
<div class="card"><div class="label">Profit Factor</div><div class="value neu">{stats['profit_factor']:.2f}</div></div>
<div class="card"><div class="label">Max Concurrent</div><div class="value neu">{stats['max_concurrent']}</div></div>
<div class="card"><div class="label">Avg Hold Time</div><div class="value neu">{stats['avg_hold']:.0f} days</div></div>
</div>

<img src="data:image/png;base64,{chart_b64}" alt="Equity Curve">

<h2>Key Statistics</h2>
<table>
<tr><th>Metric</th><th>Value</th></tr>
<tr><td>Starting Capital</td><td>${START_CAPITAL:,.0f}</td></tr>
<tr><td>Ending Equity</td><td>${START_CAPITAL + stats['total_pnl']:,.0f}</td></tr>
<tr><td>Total P&L</td><td style="{clr(stats['total_pnl'])}">${stats['total_pnl']:+,.0f}</td></tr>
<tr><td>Total Return</td><td style="{clr(stats['total_return'])}">{stats['total_return']:+.1f}%</td></tr>
<tr><td>Annualized Return</td><td style="{clr(stats['ann_return'])}">{stats['ann_return']:+.1f}%</td></tr>
<tr><td>Sharpe Ratio</td><td>{stats['sharpe']:.2f}</td></tr>
<tr><td>Max Drawdown</td><td style="{neg}">{stats['max_dd']:.1f}%</td></tr>
<tr><td>Total Trades</td><td>{stats['total_trades']}</td></tr>
<tr><td>Win Rate</td><td>{stats['win_rate']:.1f}%</td></tr>
<tr><td>Average Win</td><td style="{pos}">${stats['avg_win']:+,.0f}</td></tr>
<tr><td>Average Loss</td><td style="{neg}">${stats['avg_loss']:+,.0f}</td></tr>
<tr><td>Largest Win</td><td style="{pos}">${stats['max_win']:+,.0f}</td></tr>
<tr><td>Largest Loss</td><td style="{neg}">${stats['max_loss']:+,.0f}</td></tr>
<tr><td>Profit Factor</td><td>{stats['profit_factor']:.2f}</td></tr>
<tr><td>Avg P&L per Trade</td><td style="{clr(stats['avg_pnl_pct'])}">{stats['avg_pnl_pct']:+.1f}%</td></tr>
<tr><td>Avg Hold Time</td><td>{stats['avg_hold']:.0f} days</td></tr>
<tr><td>Median Hold Time</td><td>{stats['median_hold']:.0f} days</td></tr>
<tr><td>Max Concurrent Positions</td><td>{stats['max_concurrent']}</td></tr>
</table>

<h2>Setup Type Breakdown</h2>
<table>
<tr><th>Setup</th><th>Trades</th><th>Win Rate</th><th>Avg P&L</th><th>Total P&L</th></tr>"""

    for st, s in stats['type_stats'].items():
        label = {'WAVE_3': 'Wave 3', 'WAVE_5': 'Wave 5', 'CORRECTION': 'Wave 1 (Correction)'}.get(st, st)
        html += f"""
<tr><td>{label}</td><td>{s['count']}</td><td>{s['win_rate']:.1f}%</td>
<td style="{clr(s['avg_pnl'])}">${s['avg_pnl']:+,.0f}</td>
<td style="{clr(s['total_pnl'])}">${s['total_pnl']:+,.0f}</td></tr>"""

    html += """</table>

<h2>Monthly P&L</h2>
<table><tr><th>Month</th><th>P&L</th><th>Cumulative</th></tr>"""
    cum = 0
    for month, pnl in stats['monthly'].items():
        cum += pnl
        html += f'<tr><td>{month}</td><td style="{clr(pnl)}">${pnl:+,.0f}</td><td style="{clr(cum)}">${cum:+,.0f}</td></tr>'

    html += """</table>

<h2>Top 10 Winning Trades</h2>
<table><tr><th>Ticker</th><th>Type</th><th>Entry</th><th>Exit</th><th>Hold</th><th>P&L</th><th>P&L %</th><th>Exit Reason</th></tr>"""
    for t in best:
        ed = str(t.get('entry_date',''))[:10]
        xd = str(t.get('exit_date',''))[:10]
        st = {'WAVE_3':'W3','WAVE_5':'W5','CORRECTION':'Corr'}.get(t['setup_type'], t['setup_type'])
        html += f'<tr><td>{t["ticker"]}</td><td>{st}</td><td>{ed}</td><td>{xd}</td><td>{t["hold_days"]}d</td><td style="{clr(t["pnl"])}">${t["pnl"]:+,.0f}</td><td style="{clr(t["pnl_pct"])}">{t["pnl_pct"]:+.1f}%</td><td>{t.get("reason","")}</td></tr>'

    html += """</table>

<h2>Top 10 Losing Trades</h2>
<table><tr><th>Ticker</th><th>Type</th><th>Entry</th><th>Exit</th><th>Hold</th><th>P&L</th><th>P&L %</th><th>Exit Reason</th></tr>"""
    for t in worst:
        ed = str(t.get('entry_date',''))[:10]
        xd = str(t.get('exit_date',''))[:10]
        st = {'WAVE_3':'W3','WAVE_5':'W5','CORRECTION':'Corr'}.get(t['setup_type'], t['setup_type'])
        html += f'<tr><td>{t["ticker"]}</td><td>{st}</td><td>{ed}</td><td>{xd}</td><td>{t["hold_days"]}d</td><td style="{clr(t["pnl"])}">${t["pnl"]:+,.0f}</td><td style="{clr(t["pnl_pct"])}">{t["pnl_pct"]:+.1f}%</td><td>{t.get("reason","")}</td></tr>'

    html += f"""</table>
<p style="color:#555;margin-top:40px;font-size:11px;">
Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} · Backtest {BACKTEST_START.strftime('%Y-%m-%d')} to {BACKTEST_END.strftime('%Y-%m-%d')} · 1%/trade compounding · ${START_CAPITAL:,.0f} start · MIN_SCORE={MIN_SCORE_BT}
</p></body></html>"""

    with open(filename, 'w') as f:
        f.write(html)
    print(f"  Report saved to {filename}")
    return filename


def main():
    t0 = time.time()
    print("=" * 70)
    print("  ALEKS EWT SCANNER v2 — 3-YEAR BACKTEST")
    print(f"  Period: {BACKTEST_START.strftime('%Y-%m-%d')} to {BACKTEST_END.strftime('%Y-%m-%d')}")
    print(f"  Portfolio: ${START_CAPITAL:,} | Position: {POSITION_PCT:.0%} (compounding) | MIN_SCORE: {MIN_SCORE_BT}")
    print("=" * 70)

    daily_data, weekly_data = download_all_data()

    print(f"\nPhase 5: Finding historical setups across {len(daily_data)} tickers...")
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

    print(f"\nPhase 6: Simulating trades...")
    trades, equity_curve, max_conc = run_simulation(all_setups, daily_data)
    print(f"  {len(trades)} trades executed, max {max_conc} concurrent positions")

    print(f"\nPhase 7: Computing statistics...")
    stats = compute_stats(trades, equity_curve)
    for k in ['total_return', 'ann_return', 'sharpe', 'max_dd', 'win_rate', 'profit_factor']:
        print(f"  {k}: {stats[k]:.2f}")

    print(f"\nPhase 8: Generating report...")
    fname = generate_html(trades, equity_curve, stats)

    elapsed = time.time() - t0
    print(f"\n  Done in {elapsed/60:.1f} minutes")
    webbrowser.open('file://' + os.path.abspath(fname))


if __name__ == '__main__':
    main()
