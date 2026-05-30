#!/usr/bin/env python3
"""Show that 'highest return' = highest-Sharpe exit sized up, not the highest
raw-return exit. For each exit model, scale position size and record return + DD.
Sharpe stays ~constant with size (return and risk scale together), so at MATCHED
risk the higher-Sharpe model returns more."""
import optimize as opt

opt._init(opt.CACHE)
daily, raw, ref = opt._G['daily'], opt._G['raw'], opt._G['ref']
FS, FE = opt.FULL_START, opt.FULL_END

BASE = {'types': ('WAVE_3', 'WAVE_5'), 'min_score': 0, 'w2_band': (0.382, 0.887),
        'stop_buffer': 0.03, 'min_rr': 1.5, 'trail_atr': 2.5, 'max_hold': 180,
        'regime': 'spy_sma20_50', 'ind_filter': 'dist200_15', 'targets': (1.0, 1.618, 2.0)}

EXITS = [('100% @ T1 (Sharpe~3.3)', dict(partial_at_t1=1.0, t2_exit=False)),
         ('100% @ T2 (Sharpe~2.9)', dict(partial_at_t1=0.0, t2_exit=True)),
         ('trail only (Sharpe~2.1)', dict(partial_at_t1=0.0, t2_exit=False))]
SIZES = [0.01, 0.02, 0.03, 0.05, 0.08, 0.12]

print(f"\nFull period {FS.date()}→{FE.date()}.  For each exit: scale position size, "
      f"record 3-yr return / max-DD / Sharpe.\n")
print(f"  {'Exit model':<24} {'size/trade':>10} {'3yr return':>12} {'max DD':>9} {'Sharpe':>8} {'ret per 1% DD':>14}")
print("  " + "-" * 84)
results = {}
for ename, ex in EXITS:
    rows = []
    for sz in SIZES:
        opt.POSITION_PCT = sz
        st = opt.simulate(daily, raw, {**BASE, **ex}, FS, FE, ref)
        if st:
            rpd = st['total'] / abs(st['max_dd']) if st['max_dd'] != 0 else float('inf')
            rows.append((sz, st['total'], st['max_dd'], st['sharpe'], rpd))
    results[ename] = rows
    for sz, tot, dd, sh, rpd in rows:
        print(f"  {ename:<24} {sz*100:>9.0f}% {tot:>11.1f}% {dd:>8.1f}% {sh:>8.2f} {rpd:>13.1f}x")
    print()

print("  " + "=" * 84)
print("  Return at MATCHED RISK (size each exit so its max DD ≈ -10%, compare returns):")
for ename, rows in results.items():
    # find size whose |DD| is closest to 10, scale linearly from nearest sample
    best = min(rows, key=lambda r: abs(abs(r[2]) - 10))
    sz, tot, dd, sh, rpd = best
    scaled_ret = tot * (10.0 / abs(dd)) if dd != 0 else 0
    print(f"    {ename:<24} ~{scaled_ret:6.0f}% return at -10% DD   (from {tot:.0f}% @ {dd:.1f}% DD, size {sz*100:.0f}%)")
opt.POSITION_PCT = 0.01
