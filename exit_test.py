#!/usr/bin/env python3
"""Controlled A/B/C test of EXIT MODELS only — everything else held fixed.
Answers: 100%@T1 vs 75/25 vs 50/50 vs 100%@T2 vs trail-only, across train,
test, and 6 rolling folds (so we see which wins *consistently*, not in one window)."""
import pandas as pd
import optimize as opt

opt._init(opt.CACHE)
daily, raw, ref = opt._G['daily'], opt._G['raw'], opt._G['ref']

# Base config = the candidate that emerged from the sweep (dist-200 filter is the edge);
# we change ONLY the exit model below.
BASE = {'types': ('WAVE_3', 'WAVE_5'), 'min_score': 0, 'w2_band': (0.382, 0.887),
        'stop_buffer': 0.03, 'min_rr': 1.5, 'trail_atr': 2.5, 'max_hold': 180,
        'regime': 'spy_sma20_50', 'ind_filter': 'dist200_15'}

EXITS = [
    ('100% @ T1',       dict(partial_at_t1=1.0, t2_exit=False)),
    ('75% T1 / 25% T2', dict(partial_at_t1=0.75, t2_exit=True)),
    ('50% T1 / 50% T2', dict(partial_at_t1=0.50, t2_exit=True)),
    ('100% @ T2',       dict(partial_at_t1=0.0, t2_exit=True)),
    ('trail only (no tgt)', dict(partial_at_t1=0.0, t2_exit=False)),
]
TARGETSETS = [('T1=1.0x  T2=1.618x', (1.0, 1.618, 2.0)),
              ('T1=0.618x T2=1.0x', (0.618, 1.0, 1.618)),
              ('T1=1.0x  T2=2.618x', (1.0, 2.618, 3.618))]

FS, FE, SP = opt.FULL_START, opt.FULL_END, opt.SPLIT
edges = pd.date_range(FS, FE, periods=7)
folds = [(edges[i], edges[i + 1]) for i in range(6)]


def g(x):
    return f"{x['ann']:+6.1f}% {x['sharpe']:5.2f} {x['win']:3.0f}% n{x['n']:<4}" if x else "      n/a         "


print(f"\nBase: W3+W5, no score filter, W2 0.382-0.887, stop 3%, minRR 1.5, "
      f"regime SPY>SMA, dist200<15% filter, hold 180d")
print(f"In-sample {FS.date()}→{SP.date()} | Out-of-sample {SP.date()}→{FE.date()} | 6 rolling 6-mo folds\n")

for tname, tgt in TARGETSETS:
    print("=" * 104)
    print(f"  TARGETS: {tname}")
    print("=" * 104)
    print(f"  {'Exit model':<20} {'TRAIN  ann/Sh/win':<22} {'TEST(OOS) ann/Sh/win':<22} "
          f"{'folds + / valid':<16} {'mean fold Sharpe':<16} {'median fold ann'}")
    print("  " + "-" * 102)
    for ename, ex in EXITS:
        cfg = {**BASE, **ex, 'targets': tgt}
        tr = opt.simulate(daily, raw, cfg, FS, SP, ref)
        te = opt.simulate(daily, raw, cfg, SP, FE, ref)
        fstats = [opt.simulate(daily, raw, cfg, a, b, ref) for a, b in folds]
        fs = [f for f in fstats if f]
        pos = sum(1 for f in fs if f['total'] > 0)
        msh = sum(f['sharpe'] for f in fs) / len(fs) if fs else 0.0
        mann = sorted(f['ann'] for f in fs)[len(fs) // 2] if fs else 0.0
        print(f"  {ename:<20} {g(tr):<22} {g(te):<22} "
              f"{f'{pos}/{len(fs)} pos':<16} {msh:<16.2f} {mann:+.1f}%")
    print()
