#!/usr/bin/env python3
"""
Elliott Wave Cloud Run Service
- /scan:    Run full scanner, update watchlist + results in Google Sheets
- /monitor: Check watchlist for Fib entries, send Telegram alerts, log trades
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

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive',
]

WATCHLIST_HEADERS = ['ticker', 'setup_type', 'score', 'entry', 'stop', 't1', 't2',
                     'current_price', 'rr_t1', 'weekly_trend', 'scan_date']
TRADE_LOG_HEADERS = ['timestamp', 'type', 'ticker', 'entry', 'stop', 'target',
                     'price', 'pnl_pct', 'notes']
OPEN_TRADES_HEADERS = ['ticker', 'setup_type', 'entry', 'initial_stop', 'current_stop',
                       't1', 't2', 'max_price', 'partial_taken', 'stage', 'status',
                       'entry_date', 'bars_since_entry']
ALERT_HISTORY_HEADERS = ['timestamp', 'ticker', 'type']


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
        r['partial_taken'] = str(r.get('partial_taken', '')).lower() == 'true'
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
            str(t.get('partial_taken', False)),
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

def send_telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"  [NO TG] {message[:80]}...")
        return False
    try:
        resp = _requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={'chat_id': TELEGRAM_CHAT_ID, 'text': message,
                  'disable_web_page_preview': True},
            timeout=10)
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
        universe = list(set(sp500 + smallmid + all_traded + scanner.CURATED_ETFS))
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

        if not watchlist:
            return jsonify({'status': 'ok', 'alerts': 0, 'message': 'empty watchlist'})

        config = {'entry_zone_pct': 0.03, 'approach_pct': 0.05, 'alert_cooldown_hours': 4}
        alerts_sent = 0
        open_tickers = {t['ticker'] for t in open_trades if t.get('status') == 'OPEN'}
        market_open = monitor.is_market_hours()

        print(f"  Checking {len(watchlist)} tickers ({len(open_tickers)} open trades)"
              f" [market {'OPEN' if market_open else 'CLOSED'}]"
              f" [regime {'BULLISH' if regime_bullish else 'BEARISH'}]")

        for c in watchlist:
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

                if ticker in open_tickers:
                    print(f"  [IN TRADE]", end='')
                elif not regime_bullish:
                    print(f"  [REGIME OFF]", end='')
                else:
                    entry_found = False
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

                            msg = monitor.fmt_entry(ticker, c, analysis, daily)
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
                                'partial_taken': False,
                                'stage': 1,
                                'status': 'OPEN',
                                'entry_date': datetime.now().strftime('%Y-%m-%d'),
                                'bars_since_entry': 0,
                            }
                            open_trades.append(trade)
                            open_tickers.add(ticker)
                            print(f" [TRADE OPENED]", end='')

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
                        pnl = (trade['current_stop'] - trade['entry']) / trade['entry'] * 100
                        log_trade_event(sh, 'EXIT', ticker,
                                        entry=trade['entry'], price=trade['current_stop'],
                                        pnl_pct=f"{pnl:.1f}")
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
