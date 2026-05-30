#!/usr/bin/env python3
"""
Strategy optimizer — overfitting-resistant parameter/indicator search.

Approach:
  1. Download universe + detect every RAW setup once (causal/walk-forward),
     storing wave structure + per-stock indicator snapshot + market-regime
     snapshot at each entry bar. Cached to opt_cache.pkl.
  2. Sweep thousands of *simulation* configs (targets, exit model, stop, R:R,
     MIN_SCORE, W2 band, regime filter, entry-indicator filter, hold time,
     setup types) in-memory — each sim is milliseconds.
  3. TRAIN on the first ~2 years, then VALIDATE survivors on a held-out final
     window they never saw. Rank by out-of-sample risk-adjusted return and
     require train/test consistency, so we find an edge that holds up rather
     than an in-sample fluke.

Usage:
  python optimize.py build         # build/refresh the cache only
  python optimize.py sweep 50000   # run N random configs (default 40000)
  python optimize.py               # build if needed, then sweep
"""
import sys, os, time, pickle, warnings, random, math
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

import ew_scanner_v2 as scanner
import backtest as bt

warnings.filterwarnings('ignore')

CACHE = 'opt_cache.pkl'
FULL_START = bt.BACKTEST_START
FULL_END = bt.BACKTEST_END
# in-sample / out-of-sample split (~60/40)
SPLIT = FULL_START + (FULL_END - FULL_START) * 0.6
START_CAPITAL = 1_000_000
POSITION_PCT = 0.01
SWING_CONFIRM_BARS = 12
MIN_TRADES_TRAIN = 30          # ignore configs too sparse to trust
TOPK_VALIDATE = 400            # top in-sample configs to examine OOS

# ─────────────────────────────────────────────────────────────────────
# Indicators not already in the scanner
# ─────────────────────────────────────────────────────────────────────

def adx(df, period=14):
    high, low, close = df['High'], df['Low'], df['Close']
    up = high.diff()
    dn = -low.diff()
    plus_dm = ((up > dn) & (up > 0)) * up
    minus_dm = ((dn > up) & (dn > 0)) * dn
    tr = pd.concat([high - low, (high - close.shift()).abs(),
                    (low - close.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/period, min_periods=period).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1/period, min_periods=period).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=1/period, min_periods=period).mean() / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=1/period, min_periods=period).mean()


def compute_regime_series():
    """SPY/VIX-based market-regime indicators, indexed by date."""
    import yfinance as yf
    start = (FULL_START - pd.Timedelta(days=400)).strftime('%Y-%m-%d')
    end = FULL_END.strftime('%Y-%m-%d')
    out = {}
    spy = yf.download('SPY', start=start, end=end, interval='1d', progress=False)
    if isinstance(spy.columns, pd.MultiIndex):
        lv1 = spy.columns.get_level_values(1)
        spy.columns = lv1 if 'Close' in lv1 else spy.columns.get_level_values(0)
    c = spy['Close']
    out['spy_sma20'] = c.rolling(20).mean()
    out['spy_sma50'] = c.rolling(50).mean()
    out['spy_sma200'] = c.rolling(200).mean()
    out['spy_close'] = c
    out['spy_adx'] = adx(spy)
    out['spy_dist200'] = (c - c.rolling(200).mean()) / c.rolling(200).mean() * 100
    try:
        vix = yf.download('^VIX', start=start, end=end, interval='1d', progress=False)
        if isinstance(vix.columns, pd.MultiIndex):
            lv1 = vix.columns.get_level_values(1)
            vix.columns = lv1 if 'Close' in lv1 else vix.columns.get_level_values(0)
        out['vix'] = vix['Close']
    except Exception:
        out['vix'] = pd.Series(dtype=float)
    df = pd.DataFrame(out)
    return df


def _regime_snapshot(regime_df, date):
    """Values of each regime indicator as of the last bar <= date."""
    sub = regime_df[regime_df.index <= date]
    if len(sub) == 0:
        return {}
    r = sub.iloc[-1]
    return {
        'spy_bull': bool(r['spy_sma20'] > r['spy_sma50']) if pd.notna(r['spy_sma20']) and pd.notna(r['spy_sma50']) else True,
        'spy_above200': bool(r['spy_close'] > r['spy_sma200']) if pd.notna(r['spy_sma200']) else True,
        'spy_adx': float(r['spy_adx']) if pd.notna(r['spy_adx']) else 0.0,
        'spy_dist200': float(r['spy_dist200']) if pd.notna(r['spy_dist200']) else 0.0,
        'vix': float(r['vix']) if 'vix' in r and pd.notna(r['vix']) else 20.0,
    }


# ─────────────────────────────────────────────────────────────────────
# Raw setup detection (causal) — store structure, defer all filtering
# ─────────────────────────────────────────────────────────────────────

def detect_raw_setups(ticker, daily_df, weekly_df, regime_df):
    setups = []
    full = scanner.detect_swings(daily_df)
    if len(full) < 3:
        return setups
    ind = scanner.calculate_indicators(daily_df)
    adx_s = adx(daily_df)
    sma200 = daily_df['Close'].rolling(200).mean()
    vol20 = daily_df['Volume'].rolling(20).mean()
    vol5 = daily_df['Volume'].rolling(5).mean()

    def snapshot(bi):
        def sv(s):
            try:
                v = s.iloc[bi]
                return float(v) if pd.notna(v) else None
            except Exception:
                return None
        price = float(daily_df['Close'].iloc[bi])
        d200 = sv(sma200)
        return {
            'rsi': sv(ind['rsi']),
            'macd_hist': sv(ind['macd_hist']),
            'stoch_k': sv(ind['stoch_k']),
            'adx': sv(adx_s),
            'atr_pct': (sv(ind['atr']) / price * 100) if sv(ind['atr']) else None,
            'vol_ratio': (sv(vol5) / sv(vol20)) if sv(vol5) and sv(vol20) else None,
            'dist200': ((price - d200) / d200 * 100) if d200 else None,
        }

    # ---- Wave 3 (low-high-low) ----
    for i in range(len(full) - 2):
        if full[i]['type'] != 'low' or full[i+1]['type'] != 'high' or full[i+2]['type'] != 'low':
            continue
        w2_idx_full = full[i+2]['idx']
        sig_idx = w2_idx_full + SWING_CONFIRM_BARS
        if sig_idx >= len(daily_df):
            continue
        for bi in range(sig_idx, min(sig_idx + 90, len(daily_df))):
            bd = daily_df.index[bi]
            if bd < FULL_START or bd > FULL_END:
                continue
            cs = scanner.detect_swings(daily_df.iloc[:bi+1])
            if len(cs) < 3 or cs[-1]['type'] != 'low' or cs[-2]['type'] != 'high' or cs[-3]['type'] != 'low':
                break
            w1o, w1p, w2b = cs[-3], cs[-2], cs[-1]
            if abs(w2b['idx'] - w2_idx_full) > SWING_CONFIRM_BARS:
                break
            w1_move = w1p['price'] - w1o['price']
            if w1_move <= 0 or w1_move / w1o['price'] < 0.10:
                break
            ok, _ = scanner.validate_cardinal_rules(w1o['price'], w1p['price'], w2b['price'])
            if not ok:
                break
            w2_ret = (w1p['price'] - w2b['price']) / w1_move
            ep = float(daily_df['Close'].iloc[bi])
            rec = (ep - w2b['price']) / w2b['price'] * 100
            if rec < -5 or rec > 80:
                break
            wk = weekly_df[weekly_df.index <= bd] if weekly_df is not None else None
            winfo = scanner.count_weekly_waves(wk)
            cand = {'fib_distance': scanner.fib_distance(w2_ret, scanner.FIB_W2_IMPULSE),
                    'rr_t1': 3.0, 'weekly_trend': winfo['trend'], 'weekly_info': winfo,
                    'setup_type': 'WAVE_3', 'channel': None, 'channel_position': None,
                    'days_since_w2': (bd - w2b['date']).days}
            ind_at = {k: v.iloc[:bi+1] for k, v in ind.items()}
            score = scanner.score_candidate(cand, ind_at, winfo['trend'], daily_df.iloc[:bi+1])
            setups.append({
                'ticker': ticker, 'setup_type': 'WAVE_3',
                'signal_date': bd, 'signal_idx': bi,
                'entry': ep, 'w_low': w2b['price'], 'move': w1_move,
                'w2_ret': w2_ret, 'score': score,
                'weekly_bull': winfo['trend'] == 'BULLISH',
                'weekly_bear': winfo['trend'] == 'BEARISH',
                'ind': snapshot(bi), 'regime': _regime_snapshot(regime_df, bd),
            })
            break

    # ---- Wave 5 (low-high-low-high-low) ----
    for i in range(len(full) - 4):
        t = [s['type'] for s in full[i:i+5]]
        if t != ['low', 'high', 'low', 'high', 'low']:
            continue
        w4_idx_full = full[i+4]['idx']
        sig_idx = w4_idx_full + SWING_CONFIRM_BARS
        if sig_idx >= len(daily_df):
            continue
        for bi in range(sig_idx, min(sig_idx + 90, len(daily_df))):
            bd = daily_df.index[bi]
            if bd < FULL_START or bd > FULL_END:
                continue
            cs = scanner.detect_swings(daily_df.iloc[:bi+1])
            if len(cs) < 5:
                break
            w1o, w1p, w2b, w3p, w4b = cs[-5], cs[-4], cs[-3], cs[-2], cs[-1]
            if [w1o['type'], w1p['type'], w2b['type'], w3p['type'], w4b['type']] != \
               ['low', 'high', 'low', 'high', 'low']:
                break
            if abs(w4b['idx'] - w4_idx_full) > SWING_CONFIRM_BARS:
                break
            w1_move = w1p['price'] - w1o['price']
            w3_move = w3p['price'] - w2b['price']
            if w1_move <= 0 or w3_move <= 0:
                break
            ok, _ = scanner.validate_cardinal_rules(w1o['price'], w1p['price'], w2b['price'],
                                                    w3p['price'], w4b['price'])
            if not ok:
                break
            w4_ret = (w3p['price'] - w4b['price']) / w3_move
            if scanner.fib_distance(w4_ret, scanner.FIB_W4_IMPULSE) > scanner.FIB_TOLERANCE + 0.03:
                break
            ep = float(daily_df['Close'].iloc[bi])
            rec = (ep - w4b['price']) / w4b['price'] * 100
            if rec < -5 or rec > 60:
                break
            wk = weekly_df[weekly_df.index <= bd] if weekly_df is not None else None
            winfo = scanner.count_weekly_waves(wk)
            cand = {'fib_distance': scanner.fib_distance(w4_ret, scanner.FIB_W4_IMPULSE),
                    'rr_t1': 3.0, 'weekly_trend': winfo['trend'], 'weekly_info': winfo,
                    'setup_type': 'WAVE_5', 'channel': None, 'channel_position': None,
                    'days_since_w4': (bd - w4b['date']).days}
            ind_at = {k: v.iloc[:bi+1] for k, v in ind.items()}
            score = scanner.score_candidate(cand, ind_at, winfo['trend'], daily_df.iloc[:bi+1])
            setups.append({
                'ticker': ticker, 'setup_type': 'WAVE_5',
                'signal_date': bd, 'signal_idx': bi,
                'entry': ep, 'w_low': w4b['price'], 'move': w1_move,
                'w2_ret': w4_ret, 'score': score,
                'weekly_bull': winfo['trend'] == 'BULLISH',
                'weekly_bear': winfo['trend'] == 'BEARISH',
                'ind': snapshot(bi), 'regime': _regime_snapshot(regime_df, bd),
            })
            break

    return setups


def build_cache():
    print("Building cache (download + causal raw-setup detection)...")
    daily, weekly = bt.download_all_data()
    print("  Computing regime series (SPY/VIX)...")
    regime = compute_regime_series()
    print(f"  Detecting raw setups across {len(daily)} tickers...")
    raw, done = [], 0
    for tk in daily:
        try:
            raw += detect_raw_setups(tk, daily[tk], weekly.get(tk), regime)
        except Exception:
            pass
        done += 1
        if done % 200 == 0:
            print(f"\r  {done}/{len(daily)} ({len(raw)} raw setups)", end='', flush=True)
    print(f"\r  {done}/{len(daily)} — {len(raw)} raw setups")
    # keep only price frames we need (slim the cache)
    tickers = {s['ticker'] for s in raw} | {'SPY'}
    daily_slim = {t: daily[t] for t in tickers if t in daily}
    with open(CACHE, 'wb') as f:
        pickle.dump({'daily': daily_slim, 'raw': raw, 'ref_index': list(regime.index)}, f, protocol=4)
    print(f"  Cached {len(daily_slim)} price frames + {len(raw)} setups -> {CACHE}")
    return daily_slim, raw


# ─────────────────────────────────────────────────────────────────────
# Filtering + simulation (fast; swept per config)
# ─────────────────────────────────────────────────────────────────────

def passes(s, cfg):
    if s['setup_type'] not in cfg['types']:
        return False
    if s['weekly_bear']:
        return False
    if s['score'] < cfg['min_score']:
        return False
    lo, hi = cfg['w2_band']
    if not (lo - 0.08 <= s['w2_ret'] <= hi + 0.08):
        return False
    rg = cfg['regime']
    r = s['regime']
    if rg == 'spy_sma20_50' and not r.get('spy_bull', True): return False
    if rg == 'spy_above200' and not r.get('spy_above200', True): return False
    if rg == 'spy_adx20' and r.get('spy_adx', 0) < 20: return False
    if rg == 'vix_below20' and r.get('vix', 20) > 20: return False
    if rg == 'spy_dist200_10' and abs(r.get('spy_dist200', 0)) > 10: return False
    fl = cfg['ind_filter']
    ind = s['ind']
    if fl == 'rsi_40_70' and not (ind.get('rsi') and 40 <= ind['rsi'] <= 70): return False
    if fl == 'macd_pos' and not (ind.get('macd_hist') and ind['macd_hist'] > 0): return False
    if fl == 'adx_20' and not (ind.get('adx') and ind['adx'] > 20): return False
    if fl == 'vol_surge' and not (ind.get('vol_ratio') and ind['vol_ratio'] > 1.2): return False
    if fl == 'dist200_15' and not (ind.get('dist200') is not None and ind['dist200'] < 15): return False
    return True


def simulate(daily, raw, cfg, start, end, ref_index):
    m1, m2, m3 = cfg['targets']
    sb = cfg['stop_buffer']
    partial = cfg['partial_at_t1']
    t2_exit = cfg['t2_exit']
    trail = cfg['trail_atr']
    max_hold = cfg['max_hold']

    # build candidate trades from setups in window that pass filters
    cands = []
    for s in raw:
        if not (start <= s['signal_date'] <= end):
            continue
        if not passes(s, cfg):
            continue
        wl, mv, ep = s['w_low'], s['move'], s['entry']
        stop = wl * (1 - sb)
        risk = ep - stop
        if risk <= 0:
            continue
        rp = risk / ep * 100
        if rp < 1.0 or rp > 20.0:
            continue
        t1 = wl + m1 * mv
        t2 = wl + m2 * mv
        if t1 <= ep:
            t1 = max(t1, ep * 1.01)
        if t2 <= t1:
            t2 = t1 * 1.05
        if (t1 - ep) / risk < cfg['min_rr']:
            continue
        atr_e = (s['ind'].get('atr_pct') or 0) / 100 * ep
        cands.append({'ticker': s['ticker'], 'setup_type': s['setup_type'],
                      'signal_date': s['signal_date'], 'entry': ep, 'stop': stop,
                      't1': t1, 't2': t2, 'risk': risk,
                      'atr': atr_e if atr_e > 0 else risk})
    cands.sort(key=lambda x: x['signal_date'])

    bt_dates = [d for d in ref_index if start <= d <= end]
    if not bt_dates:
        return None

    trades, open_tr, eq = [], {}, []
    ptr, max_conc = 0, 0
    for date in bt_dates:
        closed = []
        for tk, tr in open_tr.items():
            df = daily.get(tk)
            if df is None or date not in df.index:
                continue
            loc = df.index.get_loc(date)
            hi = float(df['High'].iloc[loc]); lo = float(df['Low'].iloc[loc]); cl = float(df['Close'].iloc[loc])
            atrv = tr['atr']
            tr['max_price'] = max(tr['max_price'], hi)
            e, r = tr['entry'], tr['risk']
            mx = tr['max_price']
            if tr['stage'] < 2 and mx >= e + 0.5 * r:
                tr['cstop'] = max(tr['cstop'], e - 0.5 * r); tr['stage'] = 2
            if tr['stage'] < 3 and mx >= e + r:
                tr['cstop'] = max(tr['cstop'], e); tr['stage'] = 3
            if tr['stage'] < 4 and mx >= e + 1.5 * r:
                tr['cstop'] = max(tr['cstop'], e + 0.5 * r); tr['stage'] = 4
            if tr['pos'] < 1.0 or partial >= 1.0:
                tr['cstop'] = max(tr['cstop'], mx - trail * atrv)
            hd = (date - tr['edate']).days

            if lo <= tr['cstop']:
                pnl = tr['realized'] + tr['pos'] * (tr['cstop'] - e) * tr['sh']
                tr.update(pnl=pnl, pnl_pct=pnl / tr['ts'] * 100, hold=hd, reason='STOP')
                trades.append(dict(tr)); closed.append(tk); continue
            if tr['pos'] == 1.0 and partial > 0 and hi >= tr['t1']:
                tr['realized'] += partial * (tr['t1'] - e) * tr['sh']
                tr['pos'] = 1.0 - partial
                tr['cstop'] = max(tr['cstop'], tr['t1'] - r)
                tr['stage'] = max(tr['stage'], 5)
                if tr['pos'] <= 0:
                    pnl = tr['realized']
                    tr.update(pnl=pnl, pnl_pct=pnl / tr['ts'] * 100, hold=hd, reason='T1')
                    trades.append(dict(tr)); closed.append(tk); continue
            if t2_exit and tr['pos'] < 1.0 and hi >= tr['t2']:
                pnl = tr['realized'] + tr['pos'] * (tr['t2'] - e) * tr['sh']
                tr.update(pnl=pnl, pnl_pct=pnl / tr['ts'] * 100, hold=hd, reason='T2')
                trades.append(dict(tr)); closed.append(tk); continue
            if t2_exit and partial == 0 and hi >= tr['t2']:
                pnl = tr['realized'] + tr['pos'] * (tr['t2'] - e) * tr['sh']
                tr.update(pnl=pnl, pnl_pct=pnl / tr['ts'] * 100, hold=hd, reason='T2')
                trades.append(dict(tr)); closed.append(tk); continue
            if hd >= max_hold:
                pnl = tr['realized'] + tr['pos'] * (cl - e) * tr['sh']
                tr.update(pnl=pnl, pnl_pct=pnl / tr['ts'] * 100, hold=hd, reason='HOLD')
                trades.append(dict(tr)); closed.append(tk); continue
        for tk in closed:
            del open_tr[tk]

        realized = sum(t['pnl'] for t in trades)
        ts = (START_CAPITAL + realized) * POSITION_PCT
        while ptr < len(cands) and cands[ptr]['signal_date'] <= date:
            c = cands[ptr]; ptr += 1
            tk = c['ticker']
            if tk in open_tr:
                continue
            open_tr[tk] = {'ticker': tk, 'setup_type': c['setup_type'], 'edate': c['signal_date'],
                           'entry': c['entry'], 'risk': c['risk'], 't1': c['t1'], 't2': c['t2'],
                           'ts': ts, 'sh': ts / c['entry'], 'pos': 1.0, 'realized': 0.0,
                           'cstop': c['stop'], 'max_price': c['entry'], 'stage': 1,
                           'atr': c['atr']}
        max_conc = max(max_conc, len(open_tr))

        realized = sum(t['pnl'] for t in trades)
        unreal = 0.0
        for tk, tr in open_tr.items():
            df = daily.get(tk)
            if df is None or date not in df.index:
                continue
            cl = float(df.loc[date, 'Close'])
            unreal += tr['realized'] + tr['pos'] * (cl - tr['entry']) * tr['sh']
        eq.append((date, START_CAPITAL + realized + unreal))

    for tk, tr in list(open_tr.items()):
        df = daily.get(tk)
        if df is None:
            continue
        cl = float(df['Close'].iloc[-1])
        pnl = tr['realized'] + tr['pos'] * (cl - tr['entry']) * tr['sh']
        tr.update(pnl=pnl, pnl_pct=pnl / tr['ts'] * 100, hold=0, reason='END')
        trades.append(dict(tr))

    return _stats(trades, eq)


def _stats(trades, eq):
    if len(trades) < 3 or len(eq) < 5:
        return None
    s = pd.Series([e[1] for e in eq], index=[e[0] for e in eq])
    ret = s.pct_change().dropna()
    sharpe = float(ret.mean() / ret.std() * math.sqrt(252)) if ret.std() > 0 else 0.0
    dd = float(((s - s.cummax()) / s.cummax()).min()) * 100
    total = (s.iloc[-1] - START_CAPITAL) / START_CAPITAL * 100
    days = (eq[-1][0] - eq[0][0]).days or 1
    ann = ((1 + total / 100) ** (365 / days) - 1) * 100
    pnls = [t['pnl'] for t in trades]
    wins = [p for p in pnls if p > 0]; losses = [p for p in pnls if p <= 0]
    pf = abs(sum(wins) / sum(losses)) if losses and sum(losses) != 0 else float('inf')
    return {'total': total, 'ann': ann, 'sharpe': sharpe, 'max_dd': dd,
            'win': len(wins) / len(trades) * 100, 'pf': pf, 'n': len(trades)}


# ─────────────────────────────────────────────────────────────────────
# Parameter space + random search
# ─────────────────────────────────────────────────────────────────────

SPACE = {
    'types': [('WAVE_3',), ('WAVE_3', 'WAVE_5')],
    'min_score': [0, 85, 95, 105, 115],
    'w2_band': [(0.382, 0.887), (0.5, 0.887), (0.5, 0.786), (0.618, 0.887)],
    'stop_buffer': [0.01, 0.03, 0.05],
    'min_rr': [1.0, 1.5, 2.0, 2.5, 3.0],
    'targets': [(1.0, 1.618, 2.0), (1.0, 2.0, 2.618), (1.272, 2.0, 3.618),
                (0.618, 1.0, 1.618), (1.0, 1.0, 1.618), (1.618, 2.618, 3.618)],
    'partial_at_t1': [0.0, 0.5, 0.75, 1.0],
    't2_exit': [True, False],
    'trail_atr': [2.0, 2.5, 3.0],
    'max_hold': [90, 180, 270, 365],
    'regime': ['none', 'spy_sma20_50', 'spy_above200', 'spy_adx20', 'vix_below20', 'spy_dist200_10'],
    'ind_filter': ['none', 'rsi_40_70', 'macd_pos', 'adx_20', 'vol_surge', 'dist200_15'],
}

BASELINE = {'types': ('WAVE_3', 'WAVE_5'), 'min_score': 95, 'w2_band': (0.5, 0.887),
            'stop_buffer': 0.03, 'min_rr': 2.0, 'targets': (1.0, 1.618, 2.0),
            'partial_at_t1': 0.75, 't2_exit': True, 'trail_atr': 2.0, 'max_hold': 180,
            'regime': 'spy_sma20_50', 'ind_filter': 'none'}


def sample_cfg(rng):
    return {k: rng.choice(v) for k, v in SPACE.items()}


_G = {}

def _init(cache_path):
    with open(cache_path, 'rb') as f:
        c = pickle.load(f)
    _G['daily'] = c['daily']; _G['raw'] = c['raw']
    ri = c.get('ref_index')
    if ri is not None:
        _G['ref'] = pd.DatetimeIndex(ri)
    elif c['daily']:
        _G['ref'] = pd.DatetimeIndex(sorted(set().union(*[df.index for df in c['daily'].values()])))
    else:
        _G['ref'] = pd.DatetimeIndex([])


def _eval(cfg):
    tr = simulate(_G['daily'], _G['raw'], cfg, FULL_START, SPLIT, _G['ref'])
    te = simulate(_G['daily'], _G['raw'], cfg, SPLIT, FULL_END, _G['ref'])
    return {'cfg': cfg, 'train': tr, 'test': te}


def sweep(n):
    if not os.path.exists(CACHE):
        build_cache()
    _init(CACHE)
    print(f"\nIn-sample {FULL_START.date()}→{SPLIT.date()} | Out-of-sample {SPLIT.date()}→{FULL_END.date()}")
    base = _eval(BASELINE)
    def fmt(s): return "n/a" if not s else f"ret {s['total']:+.1f}% ann {s['ann']:+.1f}% Sharpe {s['sharpe']:.2f} DD {s['max_dd']:.1f}% win {s['win']:.0f}% n={s['n']}"
    print(f"\nBASELINE (current live config):\n  TRAIN: {fmt(base['train'])}\n  TEST:  {fmt(base['test'])}")

    rng = random.Random(12345)
    seen, configs = set(), []
    while len(configs) < n:
        cfg = sample_cfg(rng)
        key = tuple(sorted((k, str(v)) for k, v in cfg.items()))
        if key in seen:
            continue
        seen.add(key); configs.append(cfg)
    print(f"\nEvaluating {len(configs)} unique configs on {os.cpu_count()} cores...")

    t0 = time.time()
    results = []
    with ProcessPoolExecutor(max_workers=max(2, (os.cpu_count() or 4) - 2),
                             initializer=_init, initargs=(CACHE,)) as ex:
        for i, r in enumerate(ex.map(_eval, configs, chunksize=50)):
            results.append(r)
            if (i + 1) % 2000 == 0:
                print(f"\r  {i+1}/{len(configs)} ({time.time()-t0:.0f}s)", end='', flush=True)
    print(f"\r  {len(configs)} done in {time.time()-t0:.0f}s")

    # rank in-sample, then validate out-of-sample
    valid = [r for r in results if r['train'] and r['train']['n'] >= MIN_TRADES_TRAIN]
    valid.sort(key=lambda r: r['train']['sharpe'], reverse=True)
    top = valid[:TOPK_VALIDATE]
    # robust = good in-sample AND holds out-of-sample
    robust = [r for r in top if r['test'] and r['test']['n'] >= 15
              and r['test']['sharpe'] > 0.5 and r['test']['total'] > 0
              and r['test']['ann'] >= 0.5 * r['train']['ann']]
    robust.sort(key=lambda r: (r['test']['sharpe'] + r['train']['sharpe']) / 2
                + min(r['test']['ann'], r['train']['ann']) / 100, reverse=True)

    _report(base, valid, robust)
    return base, valid, robust


def _line(r):
    tr, te = r['train'], r['test']
    c = r['cfg']
    tag = f"{'+'.join(t[-1] for t in c['types'])} sc>={c['min_score']} w2{c['w2_band']} sb{c['stop_buffer']} rr{c['min_rr']} tgt{c['targets']} p{c['partial_at_t1']:.2f}/t2={int(c['t2_exit'])} trail{c['trail_atr']} hold{c['max_hold']} reg:{c['regime']} ind:{c['ind_filter']}"
    return (f"  TRAIN ann {tr['ann']:+6.1f}% Sh {tr['sharpe']:.2f} DD {tr['max_dd']:5.1f}% n{tr['n']:>3} | "
            f"TEST ann {te['ann']:+6.1f}% Sh {te['sharpe']:.2f} DD {te['max_dd']:5.1f}% n{te['n']:>3}\n    {tag}")


def _report(base, valid, robust):
    print("\n" + "=" * 100)
    print(f"  RESULTS — {len(valid)} configs with >= {MIN_TRADES_TRAIN} train trades; "
          f"{len(robust)} survived out-of-sample validation")
    print("=" * 100)
    print("\n  Top 20 by in-sample Sharpe (NOT validated — shown to see overfitting):")
    for r in valid[:20]:
        print(_line(r))
    print("\n" + "─" * 100)
    print("  TOP ROBUST CONFIGS (good in-sample AND held up out-of-sample) — these are the real candidates:")
    print("─" * 100)
    if not robust:
        print("  None passed OOS validation. The edge does not generalize with these parameters.")
    for r in robust[:25]:
        print(_line(r))
    try:
        import json
        with open('optimize_results.json', 'w') as f:
            json.dump({'baseline': base, 'robust': robust[:50],
                       'top_insample': valid[:50]}, f, default=str, indent=2)
        print("\n  Full results -> optimize_results.json")
    except Exception as e:
        print(f"  [json err] {e}")


if __name__ == '__main__':
    arg = sys.argv[1] if len(sys.argv) > 1 else ''
    if arg == 'build':
        build_cache()
    else:
        n = int(sys.argv[2]) if arg == 'sweep' and len(sys.argv) > 2 else 40000
        sweep(n)
