#!/usr/bin/env python3
"""
Elliott Wave Cloud Run Service
- /scan:    Run full scanner, update watchlist + results in Google Sheets
- /monitor: Check watchlist for Fib entries, send Telegram alerts, log trades
- /eod:     End-of-day P&L summary (unrealized + realized vs yesterday) to Telegram
- /health:  Health check
"""

import json
import os
import sys
import time
import traceback
from datetime import datetime, timedelta

import gspread
import pandas as pd
import requests as _requests
import yfinance as yf
from flask import Flask, jsonify
from google.oauth2.service_account import Credentials

import ew_scanner_v2 as scanner
import ew_monitor as monitor

app = Flask(__name__)

SHEET_ID = os.environ.get('GOOGLE_SHEET_ID', '')
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')
MIN_SCORE = int(os.environ.get('MIN_SCORE', '95'))
SETUP_FILTERS = os.environ.get('SETUP_FILTERS', 'WAVE_3,WAVE_5,CORRECTION').split(',')
REGIME_FILTER_ENABLED = os.environ.get('REGIME_FILTER', 'true').lower() == 'true'
POSITION_PCT = float(os.environ.get('POSITION_PCT', '0.05'))   # notional % of account per trade
ACCOUNT_SIZE = float(os.environ.get('ACCOUNT_SIZE', '0'))       # 0 = show % only (no share count)
EOD_ALLOC_USD = float(os.environ.get('EOD_ALLOC_USD', '10000'))  # flat $ per position for EOD P&L

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive',
]

WATCHLIST_HEADERS = ['ticker', 'setup_type', 'score', 'entry', 'stop', 't1', 't2',
                     'current_price', 'rr_t1', 'weekly_trend', 'scan_date']
TRADE_LOG_HEADERS = ['timestamp', 'type', 'ticker', 'entry', 'stop', 'target',
                     'price', 'pnl_pct', 'notes']
OPEN_TRADES_HEADERS = ['ticker', 'setup_type', 'entry', 'initial_stop', 'current_stop',
                       't1', 't2', 'max_price', 't1_reached', 'stage', 'status',
                       'entry_date', 'bars_since_entry']
ALERT_HISTORY_HEADERS = ['timestamp', 'ticker', 'type']
DAILY_PNL_HEADERS = ['date', 'unrealized', 'realized', 'net', 'open_count', 'closed_count']


# ═══════════════════════════════════════════════════════════════════════
# GOOGLE SHEETS
# ═══════════════════════════════════════════════════════════════════════

def get_sheets_client():
    creds_json = os.environ.get('GOOGLE_CREDENTIALS')
    if creds_json:
        creds_dict = json.loads(creds_json)
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    else:
        creds = Credentials.from_service_account_file('/app/service_account.json', scopes=SCOPES)
    return gspread.authorize(creds)


def get_or_create_tab(spreadsheet, title, headers):
    try:
        ws = spreadsheet.worksheet(title)
    except gspread.exceptions.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=title, rows=1000, cols=len(headers))
        ws.update(values=[headers], range_name='A1')
    return ws


def _safe_float(val, default=0.0):
    try:
        return float(val) if val != '' else default
    except (ValueError, TypeError):
        return default


# ═══════════════════════════════════════════════════════════════════════
# SHEETS STATE OPS
# ═══════════════════════════════════════════════════════════════════════

def read_watchlist(sh):
    ws = get_or_create_tab(sh, 'Watchlist', WATCHLIST_HEADERS)
    records = ws.get_all_records()
    for r in records:
        for k in ('score', 'entry', 'stop', 't1', 't2', 'current_price', 'rr_t1'):
            r[k] = _safe_float(r.get(k))
    return records


def write_watchlist(sh, candidates):
    ws = get_or_create_tab(sh, 'Watchlist', WATCHLIST_HEADERS)
    ws.clear()
    ws.update(values=[WATCHLIST_HEADERS], range_name='A1')
    if not candidates:
        return
    rows = []
    for c in candidates:
        rows.append([
            c.get('ticker', ''),
            c.get('setup_type', ''),
            round(_safe_float(c.get('score')), 1),
            round(_safe_float(c.get('entry', c.get('current_price'))), 2),
            round(_safe_float(c.get('stop')), 2),
            round(_safe_float(c.get('t1')), 2),
            round(_safe_float(c.get('t2')), 2),
            round(_safe_float(c.get('current_price')), 2),
            round(_safe_float(c.get('rr_t1')), 1),
            c.get('weekly_trend', ''),
            datetime.now().strftime('%Y-%m-%d'),
        ])
    ws.update(values=rows, range_name=f'A2:K{len(rows) + 1}')


def write_scanner_results(sh, candidates):
    headers = ['ticker', 'setup_type', 'score', 'tier', 'entry', 'stop',
               't1', 't2', 'rr_t1', 'weekly_trend']
    ws = get_or_create_tab(sh, 'Scanner Results', headers)
    ws.clear()
    ws.update(values=[headers], range_name='A1')
    if not candidates:
        return
    rows = []
    for c in candidates[:500]:
        rows.append([
            c.get('ticker', ''), c.get('setup_type', ''),
            round(_safe_float(c.get('score')), 1), c.get('tier', ''),
            round(_safe_float(c.get('current_price')), 2),
            round(_safe_float(c.get('stop')), 2),
            round(_safe_float(c.get('t1')), 2),
            round(_safe_float(c.get('t2')), 2),
            round(_safe_float(c.get('rr_t1')), 1),
            c.get('weekly_trend', ''),
        ])
    ws.update(values=rows, range_name=f'A2:J{len(rows) + 1}')


def log_trade_event(sh, event_type, ticker, **kwargs):
    try:
        ws = get_or_create_tab(sh, 'Trade Log', TRADE_LOG_HEADERS)
        ws.append_row([
            datetime.now().strftime('%Y-%m-%d %H:%M'),
            event_type, ticker,
            kwargs.get('entry', ''),
            kwargs.get('stop', ''),
            kwargs.get('target', ''),
            kwargs.get('price', ''),
            kwargs.get('pnl_pct', ''),
            kwargs.get('notes', ''),
        ])
    except Exception as e:
        print(f"  [SHEETS ERR] log_trade_event: {e}")


def read_open_trades(sh):
    ws = get_or_create_tab(sh, 'Open Trades', OPEN_TRADES_HEADERS)
    records = ws.get_all_records()
    for r in records:
        for k in ('entry', 'initial_stop', 'current_stop', 't1', 't2', 'max_price'):
            r[k] = _safe_float(r.get(k))
        # Backward compatible with the old 'partial_taken' column name.
        r['t1_reached'] = str(r.get('t1_reached', r.get('partial_taken', ''))).lower() == 'true'
        r['stage'] = int(_safe_float(r.get('stage'), 1))
        r['bars_since_entry'] = int(_safe_float(r.get('bars_since_entry'), 0))
    return records


def write_open_trades(sh, trades):
    ws = get_or_create_tab(sh, 'Open Trades', OPEN_TRADES_HEADERS)
    ws.clear()
    ws.update(values=[OPEN_TRADES_HEADERS], range_name='A1')
    if not trades:
        return
    rows = []
    for t in trades:
        rows.append([
            t.get('ticker', ''), t.get('setup_type', ''),
            t.get('entry', 0), t.get('initial_stop', 0), t.get('current_stop', 0),
            t.get('t1', 0), t.get('t2', 0), t.get('max_price', 0),
            str(t.get('t1_reached', False)),
            t.get('stage', 1), t.get('status', 'OPEN'),
            t.get('entry_date', ''), t.get('bars_since_entry', 0),
        ])
    ws.update(values=rows, range_name=f'A2:M{len(rows) + 1}')


def read_alert_history(sh):
    ws = get_or_create_tab(sh, 'Alert History', ALERT_HISTORY_HEADERS)
    return ws.get_all_records()


def record_alert_sheets(sh, ticker, alert_type):
    try:
        ws = get_or_create_tab(sh, 'Alert History', ALERT_HISTORY_HEADERS)
        ws.append_row([datetime.now().isoformat(), ticker, alert_type])
    except Exception as e:
        print(f"  [SHEETS ERR] record_alert: {e}")


def should_alert(ticker, alert_type, history, cooldown_hours=4):
    cutoff = datetime.now() - timedelta(hours=cooldown_hours)
    for h in history:
        try:
            ts = datetime.fromisoformat(str(h.get('timestamp', '')))
            if h.get('ticker') == ticker and h.get('type') == alert_type and ts > cutoff:
                return False
        except (ValueError, TypeError):
            pass
    return True


# ═══════════════════════════════════════════════════════════════════════
# TELEGRAM
# ═══════════════════════════════════════════════════════════════════════

def send_telegram(message, parse_mode=None):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"  [NO TG] {message[:80]}...")
        return False
    try:
        payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': message,
                   'disable_web_page_preview': True}
        if parse_mode:
            payload['parse_mode'] = parse_mode
        resp = _requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json=payload, timeout=10)
        return resp.status_code == 200
    except Exception as e:
        print(f"  [TG ERR] {e}")
        return False


# ═══════════════════════════════════════════════════════════════════════
# CLEAN CANDIDATE FOR SERIALIZATION
# ═══════════════════════════════════════════════════════════════════════

def _clean_candidate(c):
    d = {}
    for k, v in c.items():
        if isinstance(v, dict) and 'date' in v:
            d[k] = {'price': v['price'], 'date': str(v['date'])[:10]}
        elif hasattr(v, 'item'):
            d[k] = float(v)
        elif isinstance(v, pd.Timestamp):
            d[k] = str(v)[:10]
        else:
            d[k] = v
    return d


# ═══════════════════════════════════════════════════════════════════════
# /scan — FULL SCANNER
# ═══════════════════════════════════════════════════════════════════════

@app.route('/scan')
def scan_endpoint():
    t0 = time.time()
    try:
        print(f"\n{'=' * 60}")
        print(f"  SCAN — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print(f"{'=' * 60}")

        # Build universe
        sp500 = scanner.get_sp500_tickers()
        smallmid = scanner.get_smallmid_tickers()
        try:
            all_traded = scanner.get_all_traded_tickers()
        except Exception:
            all_traded = []
        universe = list(set(sp500 + smallmid + all_traded))
        print(f"  Universe: {len(universe)} tickers")

        # Quick screen (1 month)
        end_dt = datetime.now().strftime('%Y-%m-%d')
        screen_start = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        screen_data = scanner.download_batch(universe, screen_start, end_dt,
                                             interval='1d', min_bars=10)

        viable = []
        for ticker, df in screen_data.items():
            try:
                price = float(df['Close'].iloc[-1])
                if price < scanner.MIN_PRICE or price > scanner.MAX_PRICE:
                    continue
                avg_vol = float(df['Volume'].tail(20).mean())
                if price * avg_vol < 1_000_000:
                    continue
                viable.append(ticker)
            except Exception:
                pass
        print(f"  Quick screen: {len(viable)} viable")

        # Full download
        daily_start = (datetime.now() - timedelta(days=730)).strftime('%Y-%m-%d')
        weekly_start = (datetime.now() - timedelta(days=1825)).strftime('%Y-%m-%d')
        daily_data = scanner.download_batch(viable, daily_start, end_dt, interval='1d')
        weekly_data = scanner.download_batch(viable, weekly_start, end_dt, interval='1wk')

        # Filter
        filtered = scanner.apply_universe_filters(daily_data)
        print(f"  Filtered: {len(filtered)} tickers")

        # Scan for setups
        all_candidates = []
        for i, ticker in enumerate(filtered):
            try:
                daily_df = filtered[ticker]
                weekly_df = weekly_data.get(ticker)
                candidates = scanner.analyze_ticker(ticker, daily_df, weekly_df)
                all_candidates.extend(candidates)
            except Exception:
                pass
            if (i + 1) % 200 == 0:
                print(f"  Scanned {i + 1}/{len(filtered)}, {len(all_candidates)} candidates")

        # Deduplicate, sort by score
        all_candidates.sort(key=lambda x: x.get('score', 0), reverse=True)
        seen = set()
        deduped = []
        for c in all_candidates:
            if c['ticker'] not in seen:
                seen.add(c['ticker'])
                deduped.append(c)
        all_candidates = deduped

        # Clean for serialization
        clean_all = [_clean_candidate(c) for c in all_candidates]

        # Build watchlist (WAVE_3 + score >= MIN_SCORE)
        watchlist = [c for c in clean_all
                     if c.get('score', 0) >= MIN_SCORE
                     and c.get('setup_type') in SETUP_FILTERS][:30]

        # Write to Sheets
        try:
            gc = get_sheets_client()
            sh = gc.open_by_key(SHEET_ID)
            write_watchlist(sh, watchlist)
            write_scanner_results(sh, clean_all)
            log_trade_event(sh, 'SCAN', 'ALL',
                            notes=f"{len(clean_all)} total, {len(watchlist)} watchlist, "
                                  f"{len(filtered)} scanned")
        except Exception as e:
            print(f"  [SHEETS ERR] {e}")

        elapsed = time.time() - t0
        summary = (f"Scan done: {len(clean_all)} candidates, "
                   f"{len(watchlist)} watchlist ({'+'.join(SETUP_FILTERS)} >= {MIN_SCORE}), "
                   f"{elapsed:.0f}s")
        print(f"  {summary}")
        send_telegram(f"Scanner Update\n{summary}")

        return jsonify({
            'status': 'ok',
            'total_candidates': len(clean_all),
            'watchlist_size': len(watchlist),
            'universe_scanned': len(filtered),
            'elapsed_seconds': round(elapsed),
        })

    except Exception as e:
        traceback.print_exc()
        send_telegram(f"Scanner Error: {str(e)[:200]}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


# ═══════════════════════════════════════════════════════════════════════
# /monitor — ENTRY CHECKER
# ═══════════════════════════════════════════════════════════════════════

def check_regime():
    if not REGIME_FILTER_ENABLED:
        return True, "disabled"
    try:
        spy = yf.download('SPY', period='6mo', interval='1d', progress=False)
        if spy.empty:
            return True, "no SPY data"
        if isinstance(spy.columns, pd.MultiIndex):
            spy.columns = spy.columns.droplevel(1)
        close = spy['Close']
        sma20 = float(close.rolling(20).mean().iloc[-1])
        sma50 = float(close.rolling(50).mean().iloc[-1])
        bullish = sma20 > sma50
        status = f"SMA20={sma20:.2f} {'>' if bullish else '<'} SMA50={sma50:.2f}"
        return bullish, status
    except Exception as e:
        return True, f"error: {e}"

@app.route('/monitor')
def monitor_endpoint():
    t0 = time.time()
    try:
        print(f"\n{'=' * 60}")
        print(f"  MONITOR — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print(f"{'=' * 60}")

        regime_bullish, regime_status = check_regime()
        print(f"  Regime: {'BULLISH' if regime_bullish else 'BEARISH'} ({regime_status})")

        gc = get_sheets_client()
        sh = gc.open_by_key(SHEET_ID)

        watchlist = read_watchlist(sh)
        open_trades = read_open_trades(sh)
        alert_history = read_alert_history(sh)

        # The scanner no longer emits ETFs, but a watchlist written by an older
        # scan can still hold them until the next scan overwrites it — drop them
        # here so a stale row can never open a position we would not take.
        try:
            etfs = scanner.get_etf_symbols()
            stale = [c for c in watchlist if str(c.get('ticker', '')).strip() in etfs]
            if stale:
                print(f"  Skipping {len(stale)} stale ETF candidate(s): "
                      f"{', '.join(c['ticker'] for c in stale)}")
                watchlist = [c for c in watchlist if c not in stale]
        except Exception as e:
            print(f"  [MONITOR WARN] ETF list unavailable ({e}) — watchlist unfiltered")

        if not watchlist:
            return jsonify({'status': 'ok', 'alerts': 0, 'message': 'empty watchlist'})

        config = {'entry_zone_pct': 0.03, 'approach_pct': 0.05, 'alert_cooldown_hours': 4}
        alerts_sent = 0
        open_tickers = {t['ticker'] for t in open_trades if t.get('status') == 'OPEN'}
        market_open = monitor.is_market_hours()

        print(f"  Checking {len(watchlist)} tickers ({len(open_tickers)} open trades)"
              f" [market {'OPEN' if market_open else 'CLOSED'}]"
              f" [regime {'BULLISH' if regime_bullish else 'BEARISH'}]")

        if not market_open:
            print("  Market closed — skipping new-entry scan, managing open trades only")

        # New-entry scan only runs during market hours; open-trade management below
        # always runs (end-of-day stop updates use the settled daily bar).
        for c in (watchlist if market_open else []):
            ticker = c.get('ticker', '')
            if not ticker:
                continue
            try:
                data = monitor.download_ticker(ticker)
                daily_df = data.get('daily')
                weekly_df = data.get('weekly')
                if daily_df is None:
                    continue

                daily = monitor.check_daily(c, daily_df, config)
                if daily is None:
                    continue

                cur = daily['current']
                print(f"  {ticker:<6} ${cur:>8.2f}", end='')

                if daily['status'] == 'INVALIDATED':
                    print(f"  [INVALID]")
                    continue

                entry_found = False
                if ticker in open_tickers:
                    print(f"  [IN TRADE]", end='')
                elif not regime_bullish:
                    print(f"  [REGIME OFF]", end='')
                else:
                    for tf, tf_df in [('DAILY', daily_df), ('WEEKLY', weekly_df)]:
                        analysis = monitor.analyze_fib_entry(tf_df, tf, c)
                        alert_key = f'{tf}_ENTRY'
                        if (analysis and analysis.get('entry_signal')
                                and should_alert(ticker, alert_key, alert_history)):
                            sig = analysis['entry_signal']
                            entry_price = sig.get('entry', cur)
                            stop_price = daily['stop']
                            risk_pct = (entry_price - stop_price) / entry_price if entry_price > 0 else 0

                            if risk_pct < 0.025:
                                print(f"  [{tf} SKIP risk {risk_pct:.1%}]", end='')
                                continue

                            msg = monitor.fmt_entry(ticker, c, analysis, daily, POSITION_PCT, ACCOUNT_SIZE)
                            send_telegram(msg)
                            record_alert_sheets(sh, ticker, alert_key)
                            log_trade_event(sh, 'ENTRY', ticker,
                                            entry=entry_price, stop=stop_price,
                                            target=f"${daily['t1']:.2f}",
                                            notes=f"{tf} {sig.get('candle', '')} @ fib {sig.get('fib', '')} risk {risk_pct:.1%}")
                            alerts_sent += 1
                            print(f"  [{tf} ENTER]", end='')
                            entry_found = True

                            entry_price = sig.get('entry', cur)
                            trade = {
                                'ticker': ticker,
                                'setup_type': c.get('setup_type', 'WAVE_3'),
                                'entry': entry_price,
                                'initial_stop': daily['stop'],
                                'current_stop': daily['stop'],
                                't1': daily['t1'],
                                't2': daily.get('t2', 0),
                                'max_price': entry_price,
                                't1_reached': False,
                                'stage': 1,
                                'status': 'OPEN',
                                'entry_date': datetime.now().strftime('%Y-%m-%d'),
                                'bars_since_entry': 0,
                            }
                            open_trades.append(trade)
                            open_tickers.add(ticker)
                            print(f" [TRADE OPENED]", end='')
                            break  # one entry per ticker per cycle (don't also open on WEEKLY)

                if not entry_found and daily['status'] == 'APPROACHING':
                    print(f"  [APPROACHING]", end='')

                print()
            except Exception as e:
                print(f"  {ticker:<6} error: {e}")
                time.sleep(0.3)

        # Update open trades
        for trade in open_trades:
            if trade.get('status') != 'OPEN':
                continue
            ticker = trade['ticker']
            try:
                df = yf.download(ticker, period='5d', interval='1d', progress=False)
                if df.empty:
                    continue
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.droplevel(1)
                bar = df.iloc[-1]
                atr = monitor.calculate_atr(df)
                atr_val = (float(atr.iloc[-1]) if len(atr.dropna()) > 0
                           else float(bar['High'] - bar['Low']))
                msg = monitor.update_trade(trade, float(bar['High']), float(bar['Low']),
                                           float(bar['Close']), atr_val)
                if msg:
                    send_telegram(msg)
                    if trade.get('status') == 'CLOSED':
                        exit_price = trade.get('exit_price', trade['current_stop'])
                        pnl = (exit_price - trade['entry']) / trade['entry'] * 100
                        log_trade_event(sh, 'EXIT', ticker,
                                        entry=trade['entry'], price=exit_price,
                                        pnl_pct=f"{pnl:.1f}")
                    elif trade.pop('partial_event', False):
                        pnl = (trade['t1'] - trade['entry']) / trade['entry'] * 100
                        log_trade_event(sh, 'PARTIAL', ticker,
                                        entry=trade['entry'], price=trade['t1'],
                                        pnl_pct=f"{pnl:.1f}",
                                        notes="Booked 75% at T1, riding 25% to T2")
                    else:
                        log_trade_event(sh, 'STOP_UPDATE', ticker,
                                        stop=trade['current_stop'],
                                        notes=f"Stage {trade.get('stage', 1)}")
                    alerts_sent += 1
            except Exception:
                pass

        active_trades = [t for t in open_trades if t.get('status') == 'OPEN']
        try:
            write_open_trades(sh, active_trades)
        except Exception as e:
            print(f"  [SHEETS ERR] write_open_trades: {e}")

        # Clean old alert history (keep last 48h)
        try:
            ws = sh.worksheet('Alert History')
            all_alerts = ws.get_all_records()
            cutoff = datetime.now() - timedelta(hours=48)
            fresh = [a for a in all_alerts
                     if datetime.fromisoformat(str(a.get('timestamp', ''))) > cutoff]
            if len(fresh) < len(all_alerts):
                ws.clear()
                ws.update(values=[ALERT_HISTORY_HEADERS], range_name='A1')
                if fresh:
                    rows = [[a['timestamp'], a['ticker'], a['type']] for a in fresh]
                    ws.update(values=rows, range_name=f'A2:C{len(rows) + 1}')
        except Exception:
            pass

        elapsed = time.time() - t0
        print(f"  Monitor done: {alerts_sent} alerts, {elapsed:.0f}s")

        return jsonify({
            'status': 'ok',
            'tickers_checked': len(watchlist),
            'alerts_sent': alerts_sent,
            'open_trades': len(active_trades),
            'elapsed_seconds': round(elapsed),
        })

    except Exception as e:
        traceback.print_exc()
        send_telegram(f"Monitor Error: {str(e)[:200]}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


# ═══════════════════════════════════════════════════════════════════════
# /eod — END-OF-DAY P&L SUMMARY
# ═══════════════════════════════════════════════════════════════════════

def read_trade_log(sh):
    ws = get_or_create_tab(sh, 'Trade Log', TRADE_LOG_HEADERS)
    return ws.get_all_records()


def _settled_closes(tickers):
    """Most recent settled daily close for each ticker (the end-of-day mark)."""
    prices = {}
    if not tickers:
        return prices
    try:
        data = yf.download(tickers, period='5d', interval='1d',
                           progress=False, group_by='ticker')
    except Exception:
        data = None
    for t in tickers:
        px = None
        try:
            s = data[t]['Close'].dropna()
            if len(s):
                px = float(s.iloc[-1])
        except Exception:
            px = None
        if px is None:  # per-ticker fallback (handles single-ticker / odd frames)
            try:
                df = yf.download(t, period='5d', interval='1d', progress=False)
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.droplevel(1)
                px = float(df['Close'].dropna().iloc[-1])
            except Exception:
                px = None
        prices[t] = px
    return prices


def compute_eod_pnl(sh):
    """Mark open positions to the settled close and tally realized exits.
    Every position is sized at a flat EOD_ALLOC_USD; exit model is 100%@T1
    (see ew_monitor.update_trade), so each trade is fully open or fully closed."""
    alloc = EOD_ALLOC_USD
    # ETFs are reported as if never traded (they won 14% vs 43% for stocks and
    # drove 60% of realized losses). The scanner no longer emits them; this skips
    # any legacy rows so historical and future totals stay on the same basis.
    try:
        etfs = scanner.get_etf_symbols()
    except Exception as e:
        print(f"  [EOD WARN] ETF list unavailable ({e}) — totals include ETFs")
        etfs = set()
    open_recs = [r for r in read_open_trades(sh)
                 if str(r.get('status', '')).upper() == 'OPEN'
                 and str(r.get('ticker', '')).strip() not in etfs]
    exits = [r for r in read_trade_log(sh)
             if str(r.get('type', '')).upper() == 'EXIT'
             and str(r.get('ticker', '')).strip() not in etfs]

    open_tickers = [str(r['ticker']) for r in open_recs]
    prices = _settled_closes(open_tickers)

    unrealized = 0.0
    missing = []
    for r in open_recs:
        t = str(r['ticker'])
        try:
            entry = float(r['entry'])
        except (TypeError, ValueError):
            continue
        px = prices.get(t)
        if px is None or entry <= 0:
            missing.append(t)
            continue
        unrealized += alloc * (px / entry - 1)

    realized = 0.0
    for r in exits:
        try:
            entry = float(r['entry'])
            exit_px = float(r['price'])
        except (TypeError, ValueError):
            continue
        if entry > 0:
            realized += alloc * (exit_px / entry - 1)

    open_count = len(open_tickers) - len(missing)
    return {
        'unrealized': unrealized,
        'realized': realized,
        'net': unrealized + realized,
        'open_count': open_count,
        'closed_count': len(exits),
        'deployed': alloc * open_count,
        'missing': missing,
    }


def read_prior_pnl(sh, today_str):
    """Most recent stored snapshot from a prior day (the 'Yesterday' baseline)."""
    ws = get_or_create_tab(sh, 'Daily PnL', DAILY_PNL_HEADERS)
    recs = ws.get_all_records()
    prior = [r for r in recs
             if str(r.get('date', '')).strip() and str(r.get('date')) != today_str]
    return prior[-1] if prior else None


def save_pnl_snapshot(sh, today_str, summary):
    """Upsert today's snapshot (idempotent if /eod runs more than once)."""
    ws = get_or_create_tab(sh, 'Daily PnL', DAILY_PNL_HEADERS)
    recs = ws.get_all_records()
    values = [today_str, round(summary['unrealized']), round(summary['realized']),
              round(summary['net']), summary['open_count'], summary['closed_count']]
    for i, r in enumerate(recs):
        if str(r.get('date')) == today_str:
            ws.update(values=[values], range_name=f'A{i + 2}:F{i + 2}')
            return
    ws.append_row(values)


def _money(x):
    x = round(x)
    return f"{'+' if x >= 0 else '-'}${abs(x):,}"


def format_eod_message(today_str, summary, prior):
    LW, NW = 22, 9  # label width, number-column width

    def yval(key):
        try:
            return _money(float(prior.get(key, 0))) if prior else '—'
        except (TypeError, ValueError):
            return '—'

    def dval(key, now):
        if not prior:
            return '—'
        try:
            d = round(now) - round(float(prior.get(key, 0)))
        except (TypeError, ValueError):
            return '—'
        return '—' if d == 0 else _money(d)

    oc, cc = summary['open_count'], summary['closed_count']
    body = [
        (f"Unrealized ({oc} open)", summary['unrealized'], 'unrealized'),
        (f"Realized ({cc} closed)", summary['realized'], 'realized'),
    ]
    rule = '-' * (LW + NW * 3)
    lines = [f"{'':<{LW}}{'Now':>{NW}}{'Yest':>{NW}}{'Δ':>{NW}}", rule]
    for label, now, key in body:
        lines.append(f"{label:<{LW}}{_money(now):>{NW}}{yval(key):>{NW}}{dval(key, now):>{NW}}")
    lines.append(rule)
    lines.append(f"{'Net total':<{LW}}{_money(summary['net']):>{NW}}"
                 f"{yval('net'):>{NW}}{dval('net', summary['net']):>{NW}}")

    deployed = summary['deployed']
    ret = (summary['unrealized'] / deployed * 100) if deployed else 0.0
    footer = f"{oc} open · ${deployed / 1000:.0f}k deployed · {ret:+.2f}% on open"
    note = "" if not summary['missing'] else f"\n⚠️ no price: {', '.join(summary['missing'])}"
    table = "\n".join(lines)
    return (f"📊 <b>End-of-Day P&amp;L</b> — {today_str}\n"
            f"<pre>{table}</pre>\n{footer}{note}")


@app.route('/eod')
def eod_endpoint():
    t0 = time.time()
    try:
        today_str = datetime.now().strftime('%Y-%m-%d')
        print(f"\n{'=' * 60}\n  EOD P&L — {today_str}\n{'=' * 60}")

        gc = get_sheets_client()
        sh = gc.open_by_key(SHEET_ID)

        summary = compute_eod_pnl(sh)
        prior = read_prior_pnl(sh, today_str)
        send_telegram(format_eod_message(today_str, summary, prior), parse_mode='HTML')
        save_pnl_snapshot(sh, today_str, summary)

        print(f"  unrealized={summary['unrealized']:.0f} realized={summary['realized']:.0f} "
              f"net={summary['net']:.0f} open={summary['open_count']} "
              f"closed={summary['closed_count']} ({time.time() - t0:.0f}s)")
        if summary['missing']:
            print(f"  missing prices: {summary['missing']}")

        return jsonify({
            'status': 'ok',
            'date': today_str,
            'unrealized': round(summary['unrealized']),
            'realized': round(summary['realized']),
            'net': round(summary['net']),
            'open_count': summary['open_count'],
            'closed_count': summary['closed_count'],
            'missing': summary['missing'],
            'elapsed_seconds': round(time.time() - t0),
        })

    except Exception as e:
        traceback.print_exc()
        send_telegram(f"EOD Summary Error: {str(e)[:200]}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


# ═══════════════════════════════════════════════════════════════════════
# HEALTH
# ═══════════════════════════════════════════════════════════════════════

@app.route('/')
def health():
    return jsonify({
        'status': 'healthy',
        'service': 'elliott-wave',
        'timestamp': datetime.now().isoformat(),
    })


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
