#!/usr/bin/env python3
"""
Regime Filter Sweep v2 — Layer additional indicators on top of SMA(20)>SMA(50) winner.
Caches setups/data to disk so filter sweeps run in seconds.
"""

import sys, os, time, webbrowser, warnings, pickle
from datetime import datetime, timedelta
from collections import defaultdict

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

CACHE_FILE = 'regime_cache.pkl'


def download_regime_data():
    end = BACKTEST_END.strftime('%Y-%m-%d')
    start = (BACKTEST_START - timedelta(days=400)).strftime('%Y-%m-%d')
    tickers = {
        'SPY': 'SPY', 'VIX': '^VIX', 'QQQ': 'QQQ', 'IWM': 'IWM',
        'TLT': 'TLT', 'HYG': 'HYG', 'SMH': 'SMH', 'XLF': 'XLF',
        'XLE': 'XLE', 'XLU': 'XLU', 'XLK': 'XLK', 'UUP': 'UUP',
        'GLD': 'GLD', 'SHY': 'SHY', 'EEM': 'EEM', 'RSP': 'RSP',
        'COPPER': 'CPER', 'VIX3M': '^VIX3M',
    }
    data = {}
    for name, sym in tickers.items():
        try:
            df = yf.Ticker(sym).history(start=start, end=end, interval='1d')
            data[name] = df
        except Exception:
            data[name] = pd.DataFrame()
    return data


def compute_regime_indicators(data):
    spy = data.get('SPY', pd.DataFrame())
    vix = data.get('VIX', pd.DataFrame())
    qqq = data.get('QQQ', pd.DataFrame())
    iwm = data.get('IWM', pd.DataFrame())
    tlt = data.get('TLT', pd.DataFrame())
    hyg = data.get('HYG', pd.DataFrame())
    for df in [spy, vix, qqq, iwm, tlt, hyg]:
        if not df.empty and df.index.tz is not None:
            df.index = df.index.tz_localize(None)

    ind = pd.DataFrame(index=spy.index)

    # SPY moving averages
    for p in [10, 20, 50, 100, 150, 200]:
        ind[f'sma_{p}'] = spy['Close'].rolling(p).mean()
        ind[f'ema_{p}'] = spy['Close'].ewm(span=p).mean()
    ind['spy_close'] = spy['Close']

    # SPY RSI
    delta = spy['Close'].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1/14, min_periods=14).mean()
    avg_loss = loss.ewm(alpha=1/14, min_periods=14).mean()
    ind['rsi'] = 100 - (100 / (1 + avg_gain / avg_loss))

    # SPY MACD
    ema12 = spy['Close'].ewm(span=12).mean()
    ema26 = spy['Close'].ewm(span=26).mean()
    ind['macd'] = ema12 - ema26
    ind['macd_signal'] = ind['macd'].ewm(span=9).mean()
    ind['macd_hist'] = ind['macd'] - ind['macd_signal']

    # SPY Rate of Change
    for p in [5, 10, 20, 50]:
        ind[f'roc_{p}'] = spy['Close'].pct_change(p) * 100

    # SPY Bollinger Bands
    bb_sma = spy['Close'].rolling(20).mean()
    bb_std = spy['Close'].rolling(20).std()
    ind['bb_upper'] = bb_sma + 2 * bb_std
    ind['bb_lower'] = bb_sma - 2 * bb_std
    ind['bb_pct'] = (spy['Close'] - ind['bb_lower']) / (ind['bb_upper'] - ind['bb_lower'])

    # SPY distance from 200 SMA (%)
    ind['dist_sma200'] = (spy['Close'] - ind['sma_200']) / ind['sma_200'] * 100

    # SPY drawdown from 50-day high
    ind['spy_dd_50'] = (spy['Close'] - spy['Close'].rolling(50).max()) / spy['Close'].rolling(50).max() * 100

    # SPY volatility (20-day realized)
    ind['realized_vol'] = spy['Close'].pct_change().rolling(20).std() * np.sqrt(252) * 100

    # SMA cross states
    ind['sma20_above_50'] = (ind['sma_20'] > ind['sma_50']).astype(int)
    ind['sma10_above_20'] = (ind['sma_10'] > ind['sma_20']).astype(int)
    ind['sma50_above_200'] = (ind['sma_50'] > ind['sma_200']).astype(int)

    # SPY above key levels
    ind['spy_above_ema20'] = (spy['Close'] > ind['ema_20']).astype(int)

    # VIX
    if not vix.empty:
        ind['vix'] = vix['Close'].reindex(ind.index, method='ffill')
        ind['vix_sma10'] = ind['vix'].rolling(10).mean()
        ind['vix_above_sma10'] = (ind['vix'] > ind['vix_sma10']).astype(int)
    else:
        ind['vix'] = 20
        ind['vix_sma10'] = 20
        ind['vix_above_sma10'] = 0

    # QQQ momentum (tech leadership)
    if not qqq.empty:
        qqq_aligned = qqq['Close'].reindex(ind.index, method='ffill')
        ind['qqq_sma20'] = qqq_aligned.rolling(20).mean()
        ind['qqq_sma50'] = qqq_aligned.rolling(50).mean()
        ind['qqq_20_above_50'] = (ind['qqq_sma20'] > ind['qqq_sma50']).astype(int)
        ind['qqq_roc10'] = qqq_aligned.pct_change(10) * 100
    else:
        ind['qqq_20_above_50'] = 1
        ind['qqq_roc10'] = 0

    # IWM (small cap health)
    if not iwm.empty:
        iwm_aligned = iwm['Close'].reindex(ind.index, method='ffill')
        ind['iwm_sma20'] = iwm_aligned.rolling(20).mean()
        ind['iwm_sma50'] = iwm_aligned.rolling(50).mean()
        ind['iwm_20_above_50'] = (ind['iwm_sma20'] > ind['iwm_sma50']).astype(int)
    else:
        ind['iwm_20_above_50'] = 1

    # TLT (bonds — risk-on when bonds falling)
    if not tlt.empty:
        tlt_aligned = tlt['Close'].reindex(ind.index, method='ffill')
        ind['tlt_roc20'] = tlt_aligned.pct_change(20) * 100
    else:
        ind['tlt_roc20'] = 0

    # HYG (credit spreads proxy — risk-on when HYG rising)
    if not hyg.empty:
        hyg_aligned = hyg['Close'].reindex(ind.index, method='ffill')
        ind['hyg_sma20'] = hyg_aligned.rolling(20).mean()
        ind['hyg_above_sma20'] = (hyg_aligned > ind['hyg_sma20']).astype(int)
        ind['hyg_roc10'] = hyg_aligned.pct_change(10) * 100
    else:
        ind['hyg_above_sma20'] = 1
        ind['hyg_roc10'] = 0

    # --- RSI crossovers & derivatives ---
    ind['rsi_prev'] = ind['rsi'].shift(1)
    ind['rsi_crossed_50'] = ((ind['rsi'] > 50) & (ind['rsi_prev'] <= 50)).astype(int)
    ind['rsi_crossed_30'] = ((ind['rsi'] > 30) & (ind['rsi_prev'] <= 30)).astype(int)
    ind['rsi_crossed_40'] = ((ind['rsi'] > 40) & (ind['rsi_prev'] <= 40)).astype(int)
    ind['rsi_crossed_60'] = ((ind['rsi'] > 60) & (ind['rsi_prev'] <= 60)).astype(int)
    for w in [3, 5, 10]:
        ind[f'rsi_crossed_50_{w}d'] = ind['rsi_crossed_50'].rolling(w).max()
        ind[f'rsi_crossed_30_{w}d'] = ind['rsi_crossed_30'].rolling(w).max()
        ind[f'rsi_crossed_40_{w}d'] = ind['rsi_crossed_40'].rolling(w).max()
    ind['rsi_slope'] = ind['rsi'] - ind['rsi'].shift(5)
    ind['rsi_sma'] = ind['rsi'].rolling(10).mean()
    ind['rsi_above_sma'] = (ind['rsi'] > ind['rsi_sma']).astype(int)

    # --- MACD crossovers ---
    ind['macd_prev'] = ind['macd'].shift(1)
    ind['macd_signal_prev'] = ind['macd_signal'].shift(1)
    ind['macd_crossed_zero'] = ((ind['macd'] > 0) & (ind['macd_prev'] <= 0)).astype(int)
    ind['macd_crossed_signal'] = ((ind['macd'] > ind['macd_signal']) & (ind['macd_prev'] <= ind['macd_signal_prev'])).astype(int)
    ind['macd_hist_prev'] = ind['macd_hist'].shift(1)
    ind['macd_hist_rising'] = (ind['macd_hist'] > ind['macd_hist_prev']).astype(int)
    for w in [3, 5, 10]:
        ind[f'macd_crossed_zero_{w}d'] = ind['macd_crossed_zero'].rolling(w).max()
        ind[f'macd_crossed_signal_{w}d'] = ind['macd_crossed_signal'].rolling(w).max()

    # --- Stochastic %K %D ---
    low14 = spy['Low'].rolling(14).min()
    high14 = spy['High'].rolling(14).max()
    ind['stoch_k'] = (spy['Close'] - low14) / (high14 - low14) * 100
    ind['stoch_d'] = ind['stoch_k'].rolling(3).mean()
    ind['stoch_k_prev'] = ind['stoch_k'].shift(1)
    ind['stoch_d_prev'] = ind['stoch_d'].shift(1)
    ind['stoch_bullish_cross'] = ((ind['stoch_k'] > ind['stoch_d']) & (ind['stoch_k_prev'] <= ind['stoch_d_prev'])).astype(int)
    for w in [3, 5, 10]:
        ind[f'stoch_bullish_{w}d'] = ind['stoch_bullish_cross'].rolling(w).max()

    # --- ADX / DMI ---
    tr1 = spy['High'] - spy['Low']
    tr2 = (spy['High'] - spy['Close'].shift(1)).abs()
    tr3 = (spy['Low'] - spy['Close'].shift(1)).abs()
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr14 = true_range.ewm(span=14).mean()
    up_move = spy['High'] - spy['High'].shift(1)
    down_move = spy['Low'].shift(1) - spy['Low']
    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0), index=spy.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0), index=spy.index)
    plus_di = 100 * plus_dm.ewm(span=14).mean() / atr14
    minus_di = 100 * minus_dm.ewm(span=14).mean() / atr14
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    ind['adx'] = dx.ewm(span=14).mean()
    ind['plus_di'] = plus_di
    ind['minus_di'] = minus_di

    # --- CCI (Commodity Channel Index) ---
    tp = (spy['High'] + spy['Low'] + spy['Close']) / 3
    cci_sma = tp.rolling(20).mean()
    cci_mad = tp.rolling(20).apply(lambda x: np.mean(np.abs(x - x.mean())), raw=True)
    ind['cci'] = (tp - cci_sma) / (0.015 * cci_mad)

    # --- Williams %R ---
    high14w = spy['High'].rolling(14).max()
    low14w = spy['Low'].rolling(14).min()
    ind['willr'] = -100 * (high14w - spy['Close']) / (high14w - low14w)

    # --- OBV (On Balance Volume) ---
    obv = pd.Series(0, index=spy.index, dtype=float)
    close_diff = spy['Close'].diff()
    obv = spy['Volume'].where(close_diff > 0, -spy['Volume']).where(close_diff != 0, 0).cumsum()
    ind['obv'] = obv
    ind['obv_sma20'] = obv.rolling(20).mean()
    ind['obv_above_sma'] = (obv > ind['obv_sma20']).astype(int)
    ind['obv_slope'] = obv - obv.shift(10)

    # --- Volume ---
    ind['vol_ratio'] = spy['Volume'] / spy['Volume'].rolling(20).mean()

    # --- ATR (normalized) ---
    ind['atr_pct'] = (atr14 / spy['Close']) * 100

    # --- Consecutive up/down days ---
    up_day = (spy['Close'] > spy['Close'].shift(1)).astype(int)
    consec = up_day.copy()
    for i in range(1, len(consec)):
        if consec.iloc[i] == 1:
            consec.iloc[i] = consec.iloc[i-1] + 1
        else:
            consec.iloc[i] = 0
    ind['consec_up'] = consec

    # --- Price vs previous week high/low ---
    ind['prev_5d_high'] = spy['High'].rolling(5).max().shift(1)
    ind['above_prev_week_high'] = (spy['Close'] > ind['prev_5d_high']).astype(int)

    # --- Keltner Channel ---
    kc_mid = spy['Close'].ewm(span=20).mean()
    kc_atr = true_range.ewm(span=20).mean()
    ind['kc_upper'] = kc_mid + 2 * kc_atr
    ind['kc_lower'] = kc_mid - 2 * kc_atr
    ind['kc_pct'] = (spy['Close'] - ind['kc_lower']) / (ind['kc_upper'] - ind['kc_lower'])

    # --- MFI (Money Flow Index) ---
    mfi_tp = (spy['High'] + spy['Low'] + spy['Close']) / 3
    mfi_mf = mfi_tp * spy['Volume']
    mfi_pos = pd.Series(np.where(mfi_tp > mfi_tp.shift(1), mfi_mf, 0), index=spy.index)
    mfi_neg = pd.Series(np.where(mfi_tp < mfi_tp.shift(1), mfi_mf, 0), index=spy.index)
    mfi_ratio = mfi_pos.rolling(14).sum() / mfi_neg.rolling(14).sum()
    ind['mfi'] = 100 - (100 / (1 + mfi_ratio))

    # --- SMH (Semiconductors) ---
    smh = data.get('SMH', pd.DataFrame())
    if not smh.empty:
        if smh.index.tz is not None: smh.index = smh.index.tz_localize(None)
        smh_c = smh['Close'].reindex(ind.index, method='ffill')
        ind['smh_sma20'] = smh_c.rolling(20).mean()
        ind['smh_sma50'] = smh_c.rolling(50).mean()
        ind['smh_20_above_50'] = (ind['smh_sma20'] > ind['smh_sma50']).astype(int)
        ind['smh_roc10'] = smh_c.pct_change(10) * 100
        ind['smh_roc20'] = smh_c.pct_change(20) * 100
    else:
        ind['smh_20_above_50'] = 1; ind['smh_roc10'] = 0; ind['smh_roc20'] = 0

    # --- XLF (Financials) ---
    xlf = data.get('XLF', pd.DataFrame())
    if not xlf.empty:
        if xlf.index.tz is not None: xlf.index = xlf.index.tz_localize(None)
        xlf_c = xlf['Close'].reindex(ind.index, method='ffill')
        ind['xlf_sma20'] = xlf_c.rolling(20).mean()
        ind['xlf_sma50'] = xlf_c.rolling(50).mean()
        ind['xlf_20_above_50'] = (ind['xlf_sma20'] > ind['xlf_sma50']).astype(int)
    else:
        ind['xlf_20_above_50'] = 1

    # --- XLE (Energy) ---
    xle = data.get('XLE', pd.DataFrame())
    if not xle.empty:
        if xle.index.tz is not None: xle.index = xle.index.tz_localize(None)
        xle_c = xle['Close'].reindex(ind.index, method='ffill')
        ind['xle_roc20'] = xle_c.pct_change(20) * 100
    else:
        ind['xle_roc20'] = 0

    # --- XLU vs XLK (Utilities vs Tech = risk-off/risk-on) ---
    xlu = data.get('XLU', pd.DataFrame())
    xlk = data.get('XLK', pd.DataFrame())
    if not xlu.empty and not xlk.empty:
        if xlu.index.tz is not None: xlu.index = xlu.index.tz_localize(None)
        if xlk.index.tz is not None: xlk.index = xlk.index.tz_localize(None)
        xlu_c = xlu['Close'].reindex(ind.index, method='ffill')
        xlk_c = xlk['Close'].reindex(ind.index, method='ffill')
        ratio = xlk_c / xlu_c
        ind['xlk_xlu_ratio_rising'] = (ratio > ratio.rolling(20).mean()).astype(int)
    else:
        ind['xlk_xlu_ratio_rising'] = 1

    # --- UUP (Dollar Index) ---
    uup = data.get('UUP', pd.DataFrame())
    if not uup.empty:
        if uup.index.tz is not None: uup.index = uup.index.tz_localize(None)
        uup_c = uup['Close'].reindex(ind.index, method='ffill')
        ind['uup_sma20'] = uup_c.rolling(20).mean()
        ind['dollar_weak'] = (uup_c < ind['uup_sma20']).astype(int)
        ind['uup_roc20'] = uup_c.pct_change(20) * 100
    else:
        ind['dollar_weak'] = 0; ind['uup_roc20'] = 0

    # --- GLD (Gold) ---
    gld = data.get('GLD', pd.DataFrame())
    if not gld.empty:
        if gld.index.tz is not None: gld.index = gld.index.tz_localize(None)
        gld_c = gld['Close'].reindex(ind.index, method='ffill')
        ind['gld_roc20'] = gld_c.pct_change(20) * 100
    else:
        ind['gld_roc20'] = 0

    # --- CPER (Copper) ---
    copper = data.get('COPPER', pd.DataFrame())
    if not copper.empty:
        if copper.index.tz is not None: copper.index = copper.index.tz_localize(None)
        cu_c = copper['Close'].reindex(ind.index, method='ffill')
        ind['copper_roc20'] = cu_c.pct_change(20) * 100
        ind['copper_sma50'] = cu_c.rolling(50).mean()
        ind['copper_above_50'] = (cu_c > ind['copper_sma50']).astype(int)
    else:
        ind['copper_roc20'] = 0; ind['copper_above_50'] = 1

    # --- EEM (Emerging Markets) ---
    eem = data.get('EEM', pd.DataFrame())
    if not eem.empty:
        if eem.index.tz is not None: eem.index = eem.index.tz_localize(None)
        eem_c = eem['Close'].reindex(ind.index, method='ffill')
        ind['eem_roc20'] = eem_c.pct_change(20) * 100
        ind['eem_sma50'] = eem_c.rolling(50).mean()
        ind['eem_above_50'] = (eem_c > ind['eem_sma50']).astype(int)
    else:
        ind['eem_roc20'] = 0; ind['eem_above_50'] = 1

    # --- RSP/SPY (Equal weight vs cap weight = breadth) ---
    rsp = data.get('RSP', pd.DataFrame())
    if not rsp.empty:
        if rsp.index.tz is not None: rsp.index = rsp.index.tz_localize(None)
        rsp_c = rsp['Close'].reindex(ind.index, method='ffill')
        rsp_spy = rsp_c / spy['Close']
        ind['breadth_improving'] = (rsp_spy > rsp_spy.rolling(20).mean()).astype(int)
        ind['rsp_roc10'] = rsp_c.pct_change(10) * 100
    else:
        ind['breadth_improving'] = 1; ind['rsp_roc10'] = 0

    # --- Yield curve proxy: TLT/SHY ---
    shy = data.get('SHY', pd.DataFrame())
    if not shy.empty and not tlt.empty:
        if shy.index.tz is not None: shy.index = shy.index.tz_localize(None)
        shy_c = shy['Close'].reindex(ind.index, method='ffill')
        tlt_c = tlt['Close'].reindex(ind.index, method='ffill')
        yc = tlt_c / shy_c
        ind['yield_curve_rising'] = (yc > yc.rolling(20).mean()).astype(int)
    else:
        ind['yield_curve_rising'] = 1

    # --- VIX term structure: VIX / VIX3M ---
    vix3m = data.get('VIX3M', pd.DataFrame())
    if not vix3m.empty and not vix.empty:
        if vix3m.index.tz is not None: vix3m.index = vix3m.index.tz_localize(None)
        v3m = vix3m['Close'].reindex(ind.index, method='ffill')
        v1 = ind['vix']
        ind['vix_contango'] = (v1 < v3m).astype(int)  # normal = bullish
        ind['vix_ratio'] = v1 / v3m
    else:
        ind['vix_contango'] = 1; ind['vix_ratio'] = 0.85

    # --- HYG/IEF (Credit spread proxy) ---
    if not hyg.empty:
        hyg_c = hyg['Close'].reindex(ind.index, method='ffill') if hyg.index.tz is None else hyg['Close'].reindex(ind.index, method='ffill')
        shy_safe = shy['Close'].reindex(ind.index, method='ffill') if not shy.empty else pd.Series(1, index=ind.index)
        if not shy.empty:
            credit = hyg_c / shy_safe
            ind['credit_improving'] = (credit > credit.rolling(20).mean()).astype(int)
        else:
            ind['credit_improving'] = 1
    else:
        ind['credit_improving'] = 1

    # --- Seasonality ---
    ind['month'] = ind.index.month
    ind['day_of_week'] = ind.index.dayofweek

    # --- SPY weekly RSI (approximated from daily) ---
    spy_weekly_close = spy['Close'].resample('W-FRI').last().dropna()
    wk_delta = spy_weekly_close.diff()
    wk_gain = wk_delta.where(wk_delta > 0, 0.0)
    wk_loss = -wk_delta.where(wk_delta < 0, 0.0)
    wk_avg_gain = wk_gain.ewm(alpha=1/14, min_periods=14).mean()
    wk_avg_loss = wk_loss.ewm(alpha=1/14, min_periods=14).mean()
    wk_rsi = 100 - (100 / (1 + wk_avg_gain / wk_avg_loss))
    ind['weekly_rsi'] = wk_rsi.reindex(ind.index, method='ffill')

    # --- Distance from 52-week high ---
    ind['dist_52w_high'] = (spy['Close'] - spy['Close'].rolling(252).max()) / spy['Close'].rolling(252).max() * 100

    # --- Up days ratio ---
    up = (spy['Close'] > spy['Close'].shift(1)).astype(int)
    ind['up_days_10'] = up.rolling(10).sum()
    ind['up_days_20'] = up.rolling(20).sum()

    return ind


def base_filter(ind, d):
    return ind.loc[d, 'sma20_above_50'] == 1


def build_filter_combos():
    combos = []

    combos.append(('BASELINE (no filter)', lambda ind, d: True))
    combos.append(('SMA(20)>SMA(50) ONLY [prev winner]', base_filter))

    # ═══ RSI LEVEL ═══
    for t in [30, 40, 45, 50, 55]:
        combos.append((f'BASE + RSI>{t}', lambda ind, d, t=t: base_filter(ind, d) and ind.loc[d, 'rsi'] > t))

    # ═══ RSI CROSSOVERS ═══
    for w in [3, 5, 10]:
        combos.append((f'BASE + RSI crossed 50 in {w}d', lambda ind, d, w=w: base_filter(ind, d) and ind.loc[d, f'rsi_crossed_50_{w}d'] == 1))
        combos.append((f'BASE + RSI crossed 30 in {w}d', lambda ind, d, w=w: base_filter(ind, d) and ind.loc[d, f'rsi_crossed_30_{w}d'] == 1))
        combos.append((f'BASE + RSI crossed 40 in {w}d', lambda ind, d, w=w: base_filter(ind, d) and ind.loc[d, f'rsi_crossed_40_{w}d'] == 1))

    combos.append(('BASE + RSI slope>0 (5d)', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'rsi_slope'] > 0))
    combos.append(('BASE + RSI slope>5 (5d)', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'rsi_slope'] > 5))
    combos.append(('BASE + RSI>own SMA(10)', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'rsi_above_sma'] == 1))

    # ═══ MACD LEVEL ═══
    combos.append(('BASE + MACD>0', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'macd'] > 0))
    combos.append(('BASE + MACD hist>0', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'macd_hist'] > 0))
    combos.append(('BASE + MACD>signal', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'macd'] > ind.loc[d, 'macd_signal']))
    combos.append(('BASE + MACD hist rising', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'macd_hist_rising'] == 1))

    # ═══ MACD CROSSOVERS ═══
    for w in [3, 5, 10]:
        combos.append((f'BASE + MACD crossed 0 in {w}d', lambda ind, d, w=w: base_filter(ind, d) and ind.loc[d, f'macd_crossed_zero_{w}d'] == 1))
        combos.append((f'BASE + MACD crossed signal in {w}d', lambda ind, d, w=w: base_filter(ind, d) and ind.loc[d, f'macd_crossed_signal_{w}d'] == 1))

    # ═══ STOCHASTIC ═══
    combos.append(('BASE + Stoch %K>50', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'stoch_k'] > 50))
    combos.append(('BASE + Stoch %K>20', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'stoch_k'] > 20))
    combos.append(('BASE + Stoch %K>%D', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'stoch_k'] > ind.loc[d, 'stoch_d']))
    combos.append(('BASE + Stoch %K<80', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'stoch_k'] < 80))
    combos.append(('BASE + 20<Stoch<80', lambda ind, d: base_filter(ind, d) and 20 < ind.loc[d, 'stoch_k'] < 80))
    for w in [3, 5, 10]:
        combos.append((f'BASE + Stoch bullish cross in {w}d', lambda ind, d, w=w: base_filter(ind, d) and ind.loc[d, f'stoch_bullish_{w}d'] == 1))

    # ═══ ADX / DMI ═══
    combos.append(('BASE + ADX>20', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'adx'] > 20))
    combos.append(('BASE + ADX>25', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'adx'] > 25))
    combos.append(('BASE + ADX>30', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'adx'] > 30))
    combos.append(('BASE + ADX<25 (range)', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'adx'] < 25))
    combos.append(('BASE + +DI>-DI', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'plus_di'] > ind.loc[d, 'minus_di']))

    # ═══ CCI ═══
    combos.append(('BASE + CCI>0', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'cci'] > 0))
    combos.append(('BASE + CCI>100', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'cci'] > 100))
    combos.append(('BASE + CCI>-100', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'cci'] > -100))
    combos.append(('BASE + 0<CCI<200', lambda ind, d: base_filter(ind, d) and 0 < ind.loc[d, 'cci'] < 200))

    # ═══ WILLIAMS %R ═══
    combos.append(('BASE + WillR>-50', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'willr'] > -50))
    combos.append(('BASE + WillR>-20', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'willr'] > -20))
    combos.append(('BASE + WillR>-80', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'willr'] > -80))
    combos.append(('BASE + -80<WillR<-20', lambda ind, d: base_filter(ind, d) and -80 < ind.loc[d, 'willr'] < -20))

    # ═══ MFI (Money Flow Index) ═══
    combos.append(('BASE + MFI>50', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'mfi'] > 50))
    combos.append(('BASE + MFI>40', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'mfi'] > 40))
    combos.append(('BASE + MFI>60', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'mfi'] > 60))
    combos.append(('BASE + MFI<80', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'mfi'] < 80))

    # ═══ OBV ═══
    combos.append(('BASE + OBV>SMA(20)', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'obv_above_sma'] == 1))
    combos.append(('BASE + OBV slope>0 (10d)', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'obv_slope'] > 0))

    # ═══ VOLUME ═══
    combos.append(('BASE + Vol>1.0x avg', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'vol_ratio'] > 1.0))
    combos.append(('BASE + Vol>1.5x avg', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'vol_ratio'] > 1.5))
    combos.append(('BASE + Vol<2.0x avg', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'vol_ratio'] < 2.0))

    # ═══ ATR ═══
    combos.append(('BASE + ATR%<1.0', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'atr_pct'] < 1.0))
    combos.append(('BASE + ATR%<1.5', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'atr_pct'] < 1.5))
    combos.append(('BASE + ATR%<2.0', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'atr_pct'] < 2.0))

    # ═══ KELTNER CHANNEL ═══
    combos.append(('BASE + KC%>0.3', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'kc_pct'] > 0.3))
    combos.append(('BASE + KC%>0.5', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'kc_pct'] > 0.5))
    combos.append(('BASE + KC%<0.8', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'kc_pct'] < 0.8))

    # ═══ CONSECUTIVE UP DAYS ═══
    combos.append(('BASE + >=2 consec up days', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'consec_up'] >= 2))
    combos.append(('BASE + >=3 consec up days', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'consec_up'] >= 3))

    # ═══ PRICE VS PREV WEEK ═══
    combos.append(('BASE + above prev week high', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'above_prev_week_high'] == 1))

    # ═══ VIX ═══
    for v in [18, 20, 22, 25, 30]:
        combos.append((f'BASE + VIX<{v}', lambda ind, d, v=v: base_filter(ind, d) and ind.loc[d, 'vix'] < v))
    combos.append(('BASE + VIX<SMA10(VIX)', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'vix_above_sma10'] == 0))
    combos.append(('BASE + VIX>SMA10(VIX)', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'vix_above_sma10'] == 1))

    # ═══ RATE OF CHANGE ═══
    for p in [5, 10, 20]:
        combos.append((f'BASE + ROC({p})>0', lambda ind, d, p=p: base_filter(ind, d) and ind.loc[d, f'roc_{p}'] > 0))
    combos.append(('BASE + ROC(10)>1%', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'roc_10'] > 1))
    combos.append(('BASE + ROC(20)>2%', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'roc_20'] > 2))

    # ═══ BOLLINGER / DISTANCE / VOL / DD ═══
    combos.append(('BASE + BB%>0.3', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'bb_pct'] > 0.3))
    combos.append(('BASE + BB%>0.5', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'bb_pct'] > 0.5))
    combos.append(('BASE + BB%<0.8', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'bb_pct'] < 0.8))
    combos.append(('BASE + dist(200)>0%', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'dist_sma200'] > 0))
    combos.append(('BASE + dist(200)<10%', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'dist_sma200'] < 10))
    combos.append(('BASE + dist(200)<5%', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'dist_sma200'] < 5))
    combos.append(('BASE + dist(200)<15%', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'dist_sma200'] < 15))
    combos.append(('BASE + vol<15%', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'realized_vol'] < 15))
    combos.append(('BASE + vol<20%', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'realized_vol'] < 20))
    combos.append(('BASE + DD(50d)>-3%', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'spy_dd_50'] > -3))
    combos.append(('BASE + DD(50d)>-5%', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'spy_dd_50'] > -5))

    # ═══ MA CROSSES ═══
    combos.append(('BASE + SMA(10)>SMA(20)', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'sma10_above_20'] == 1))
    combos.append(('BASE + SMA(50)>SMA(200)', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'sma50_above_200'] == 1))
    combos.append(('BASE + SPY>EMA(20)', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'spy_above_ema20'] == 1))

    # ═══ INTERMARKET ═══
    combos.append(('BASE + QQQ(20)>QQQ(50)', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'qqq_20_above_50'] == 1))
    combos.append(('BASE + IWM(20)>IWM(50)', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'iwm_20_above_50'] == 1))
    combos.append(('BASE + HYG>HYG SMA(20)', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'hyg_above_sma20'] == 1))
    combos.append(('BASE + QQQ ROC(10)>0', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'qqq_roc10'] > 0))
    combos.append(('BASE + HYG ROC(10)>0', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'hyg_roc10'] > 0))
    combos.append(('BASE + TLT ROC(20)<0', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'tlt_roc20'] < 0))

    # ═══ SEMICONDUCTORS ═══
    combos.append(('BASE + SMH(20)>SMH(50)', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'smh_20_above_50'] == 1))
    combos.append(('BASE + SMH ROC(10)>0', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'smh_roc10'] > 0))
    combos.append(('BASE + SMH ROC(20)>0', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'smh_roc20'] > 0))

    # ═══ FINANCIALS ═══
    combos.append(('BASE + XLF(20)>XLF(50)', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'xlf_20_above_50'] == 1))

    # ═══ ENERGY ═══
    combos.append(('BASE + XLE ROC(20)>0', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'xle_roc20'] > 0))

    # ═══ RISK-ON/OFF (Tech vs Utilities) ═══
    combos.append(('BASE + XLK/XLU rising (risk-on)', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'xlk_xlu_ratio_rising'] == 1))

    # ═══ DOLLAR ═══
    combos.append(('BASE + weak dollar (UUP<SMA20)', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'dollar_weak'] == 1))
    combos.append(('BASE + UUP ROC(20)<0', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'uup_roc20'] < 0))

    # ═══ GOLD ═══
    combos.append(('BASE + GLD ROC(20)<0 (risk-on)', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'gld_roc20'] < 0))
    combos.append(('BASE + GLD ROC(20)>0', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'gld_roc20'] > 0))

    # ═══ COPPER (economic growth) ═══
    combos.append(('BASE + copper ROC(20)>0', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'copper_roc20'] > 0))
    combos.append(('BASE + copper>SMA(50)', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'copper_above_50'] == 1))

    # ═══ EMERGING MARKETS ═══
    combos.append(('BASE + EEM ROC(20)>0', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'eem_roc20'] > 0))
    combos.append(('BASE + EEM>SMA(50)', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'eem_above_50'] == 1))

    # ═══ BREADTH (RSP/SPY equal weight) ═══
    combos.append(('BASE + breadth improving (RSP/SPY)', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'breadth_improving'] == 1))
    combos.append(('BASE + RSP ROC(10)>0', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'rsp_roc10'] > 0))

    # ═══ YIELD CURVE ═══
    combos.append(('BASE + yield curve rising', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'yield_curve_rising'] == 1))

    # ═══ VIX TERM STRUCTURE ═══
    combos.append(('BASE + VIX contango (normal)', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'vix_contango'] == 1))
    combos.append(('BASE + VIX ratio<0.9', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'vix_ratio'] < 0.9))
    combos.append(('BASE + VIX ratio<0.85', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'vix_ratio'] < 0.85))

    # ═══ CREDIT SPREADS ═══
    combos.append(('BASE + credit improving (HYG/SHY)', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'credit_improving'] == 1))

    # ═══ WEEKLY RSI ═══
    combos.append(('BASE + weekly RSI>40', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'weekly_rsi'] > 40))
    combos.append(('BASE + weekly RSI>50', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'weekly_rsi'] > 50))
    combos.append(('BASE + weekly RSI>60', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'weekly_rsi'] > 60))

    # ═══ DISTANCE FROM 52-WEEK HIGH ═══
    combos.append(('BASE + within 5% of 52w high', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'dist_52w_high'] > -5))
    combos.append(('BASE + within 10% of 52w high', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'dist_52w_high'] > -10))
    combos.append(('BASE + >5% from 52w high', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'dist_52w_high'] < -5))

    # ═══ UP DAYS RATIO ═══
    combos.append(('BASE + 6+ up days in 10', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'up_days_10'] >= 6))
    combos.append(('BASE + 5+ up days in 10', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'up_days_10'] >= 5))
    combos.append(('BASE + 11+ up days in 20', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'up_days_20'] >= 11))
    combos.append(('BASE + 12+ up days in 20', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'up_days_20'] >= 12))

    # ═══ SEASONALITY ═══
    combos.append(('BASE + Nov-Apr (best 6 months)', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'month'] in [11, 12, 1, 2, 3, 4]))
    combos.append(('BASE + not Sep (worst month)', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'month'] != 9))
    combos.append(('BASE + Q1 (Jan-Mar)', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'month'] in [1, 2, 3]))
    combos.append(('BASE + Q4 (Oct-Dec)', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'month'] in [10, 11, 12]))
    combos.append(('BASE + Mon/Tue/Wed', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'day_of_week'] <= 2))
    combos.append(('BASE + not Mon (weak open)', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'day_of_week'] != 0))
    combos.append(('BASE + Fri (week-end strength)', lambda ind, d: base_filter(ind, d) and ind.loc[d, 'day_of_week'] == 4))

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
            except Exception:
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
        'total_return': total_return, 'ann_return': ann_return,
        'sharpe': sharpe, 'max_dd': max_dd,
        'win_rate': len(wins)/len(trades)*100, 'profit_factor': pf,
        'trades': len(trades), 'max_concurrent': max(e['open'] for e in equity_curve),
        'avg_hold': avg_hold, 'roi_deployed': roi_deployed,
    }


def generate_results_html(results, filename='regime_results_v2.html'):
    results.sort(key=lambda x: x['stats']['sharpe'] if x['stats'] else -999, reverse=True)

    rows = ''
    for i, r in enumerate(results):
        s = r['stats']
        if s is None: continue
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
        bl_note = f"Baseline (no filter): {bs['total_return']:.1f}% return, {bs['sharpe']:.2f} Sharpe, {bs['max_dd']:.1f}% max DD"

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Regime Filter Sweep v2</title>
<style>
body {{ background:#1a1a2e; color:#e0e0e0; font-family:'Segoe UI',system-ui,sans-serif; padding:20px; }}
h1 {{ color:#00d4ff; text-align:center; }}
.subtitle {{ color:#888; text-align:center; margin-bottom:10px; }}
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
<h1>Regime Filter Sweep v2 — Layering on SMA(20)>SMA(50)</h1>
<p class="subtitle">{BACKTEST_START.strftime('%b %Y')} — {BACKTEST_END.strftime('%b %Y')} · $1M · 1%/trade · 100% exit at T2 · Sorted by Sharpe</p>
<p class="subtitle">{bl_note}</p>
<p class="subtitle">BASE = SMA(20)>SMA(50) on SPY daily. All combos layer on top of BASE.</p>
<table>
<tr><th>#</th><th>Filter</th><th>Trades</th><th>Skipped</th><th>Return</th><th>Ann.</th><th>Sharpe</th><th>MaxDD</th><th>Win%</th><th>PF</th><th>ROI Deployed</th><th>MaxConc</th><th>AvgHold</th></tr>
{rows}
</table>
<p class="note">Top 3 highlighted green · Top 10 highlighted blue · BASE = SMA(20)>SMA(50) on SPY daily · Intermarket: QQQ (tech), IWM (small caps), TLT (bonds), HYG (credit)</p>
</body></html>"""

    with open(filename, 'w') as f:
        f.write(html)
    return filename


def main():
    t0 = time.time()
    print("=" * 70)
    print("  REGIME FILTER SWEEP v2 — Layering on SMA(20)>SMA(50)")
    print(f"  Period: {BACKTEST_START.strftime('%Y-%m-%d')} to {BACKTEST_END.strftime('%Y-%m-%d')}")
    print("=" * 70)

    # Check for cached data
    if os.path.exists(CACHE_FILE):
        print("\n  Loading cached data/setups...")
        with open(CACHE_FILE, 'rb') as f:
            cache = pickle.load(f)
        daily_data = cache['daily_data']
        all_setups = cache['all_setups']
        print(f"  {len(daily_data)} tickers, {len(all_setups)} setups loaded from cache")
    else:
        print("\nPhase 1: Downloading ticker data...")
        daily_data, weekly_data = download_all_data()

        print(f"\nPhase 2: Finding setups across {len(daily_data)} tickers...")
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

        print("  Saving cache...")
        with open(CACHE_FILE, 'wb') as f:
            pickle.dump({'daily_data': daily_data, 'all_setups': all_setups}, f, protocol=4)
        print(f"  Cache saved ({os.path.getsize(CACHE_FILE) / 1e9:.1f} GB)")

    print("\nPhase 3: Downloading regime data (18 tickers)...")
    regime_data = download_regime_data()
    regime_ind = compute_regime_indicators(regime_data)
    print(f"  {len(regime_ind)} bars, {len(regime_ind.columns)} indicators")

    combos = build_filter_combos()
    print(f"\nPhase 4: Testing {len(combos)} filter combinations...")

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
