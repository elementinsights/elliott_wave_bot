# Aleks Elliott Wave Trading Framework
## Systematic Long-Only Strategy for S&P 500 + Russell 2000

---

## 1. Executive Summary

This document reverse-engineers Aleks's discretionary Elliott Wave trading approach into a systematic, rules-based long-only framework. The strategy is derived from two primary sources:

1. **Aleks's EWT Presentation** — covering impulse waves, diagonals (expanding/contracting, leading/ending), and all corrective patterns (zigzag, flat variants, double/triple combos, double/triple zigzags, contracting triangles), with complete Fibonacci ratio tables and structural rules for each.
2. **Sample Trade Alerts** — five real trades (NFLX, ARM, EVTC, RR, DELL) showing the full lifecycle: entry, stop management, partial profit-taking, and various exit scenarios (target hit, wave count invalidation, stop-out, stall-at-breakeven close).

**Core philosophy**: Enter at the start of motive waves (primarily Wave 3 after Wave 2 completion), use Fibonacci extensions for targets, place stops at structural invalidation levels, and actively manage trades with trailing stops and partial exits.

**Key finding from the trades**: Aleks uses a 75/25 partial profit model (book 75% near first target, trail 25% for extended moves), moves stops to breakeven after initial favorable movement, and exits immediately when the wave count is no longer supported by price action — even at a small profit.

---

## 2. Key Observations from the PDFs

### 2.1 Pattern Universe (from Presentation)

**Motive Patterns:**
- Impulse (5-3-5-3-5 structure)
- Leading Diagonal (can be 5-3-5-3-5 or 3-3-3-3-3; appears in Wave 1 or Wave A position)
- Ending Diagonal (always 3-3-3-3-3; appears in Wave 5 or Wave C position)
- Diagonal variants: Contracting and Expanding for both leading and ending

**Corrective Patterns:**
- Zigzag (5-3-5): sharp correction, Wave B retraces 38.2-88.7% of A, Wave C = 61.8-127.2% of A
- Flat - Regular (3-3-5): B retraces >90% of A, C ≈ 61.8-127.2% of A
- Flat - Expanded (3-3-5): B exceeds 100% of A (127.2-161.8%), C = 127.2-161.8% of A
- Flat - Running (3-3-5): B exceeds 100% of A, C does NOT go beyond end of A
- Double Combo WXY (3-3-3): sideways correction, Y can go past beginning of W
- Triple Combo WXYXZ (3-3-3-3-3): sideways correction
- Double Zigzag WXY (3-3-3): sharp correction, X cannot go past beginning of W
- Triple Zigzag WXYXZ (3-3-3-3-3): sharp correction
- Triangle - Contracting (3-3-3-3-3): at least 4 of 5 waves must be simple zigzags

### 2.2 Complete Fibonacci Ratio Tables (Directly from Presentation)

**IMPULSE WAVE:**
| Wave | Fibonacci Ratios (of reference wave) |
|------|--------------------------------------|
| Wave 2 | 50%, 61.8%, 78.6%, or 88.7% of Wave 1 |
| Wave 3 | 161.8%, 175%, 227.2%, or 361.8% of Wave 1 |
| Wave 4 | 23.6%, 38.2%, 50%, or 61.8% of Wave 3 |
| Wave 5 | Inverse 123.6%-161.8% retracement of Wave 4; Equal to Wave 1; 61.8% of Waves 1-3 |

**DIAGONAL (Contracting & Expanding):**
| Wave | Fibonacci Ratios |
|------|-----------------|
| Wave 2 | 61.8% or 78.6% of Wave 1 |
| Wave 4 | 61.8% or 78.6% of Wave 3 |

**ZIGZAG:**
| Wave | Fibonacci Ratios |
|------|-----------------|
| Wave B | 38.2%, 50%, 61.8%, 76.6%, or 88.7% of Wave A |
| Wave C | 61.8%, 100%, or 127.2% of Wave A |

**FLAT - REGULAR:**
| Wave | Fibonacci Ratios |
|------|-----------------|
| Wave B | >90% of Wave A |
| Wave C | 61.8%, 100%, or 127.2% of Wave A |

**FLAT - EXPANDED:**
| Wave | Fibonacci Ratios |
|------|-----------------|
| Wave B | 127.2% or 161.8% of Wave A |
| Wave C | 127.2% or 161.8% of Wave A |

**FLAT - RUNNING:**
| Wave | Fibonacci Ratios |
|------|-----------------|
| Wave B | 127.2% or 161.8% of Wave A |
| Wave C | 61.8% or 100% of Wave A |

**DOUBLE COMBO (WXY):**
| Wave | Fibonacci Ratios |
|------|-----------------|
| Wave X | 61.8%, 78.6%, or 88.7% of Wave W |
| Wave Y | 61.8%, 100%, 127.2%, or 161.8% of Wave W |

**TRIPLE COMBO (WXYXZ):**
| Wave | Fibonacci Ratios |
|------|-----------------|
| Wave X | 61.8%, 78.6%, or 88.7% of Wave W |
| Wave Y | 61.8%, 100%, 127.2%, or 161.8% of Wave W |
| Wave X₂ | 61.8%, 78.6%, or 88.7% of Wave Y |
| Wave Z | 61.8%, 127.2%, or 161.8% of Wave Y |

**DOUBLE ZIGZAG (WXY):**
| Wave | Fibonacci Ratios |
|------|-----------------|
| Wave X | 38.2% or 50% of Wave W |
| Wave Y | 61.8%, 100%, 127.2%, or 161.8% of Wave W |

**TRIPLE ZIGZAG (WXYXZ):**
| Wave | Fibonacci Ratios |
|------|-----------------|
| Wave X | 38.2% or 50% of Wave W |
| Wave Y | 61.8%, 100%, 127.2%, or 161.8% of Wave W |
| Wave X₂ | 38.2% or 50% of Wave Y |
| Wave Z | 61.8%, 100%, 127.2%, or 161.8% of Wave Y |

**TRIANGLE - CONTRACTING:**
| Wave | Fibonacci Ratios |
|------|-----------------|
| Wave B | 61.8% or 161.8% of Wave A |
| Wave C | 61.8% or 78.6% of Wave A |
| Wave D | 61.8% or 78.6% of Wave B |

### 2.3 Inviolable Rules (Directly from Presentation)

**Three Cardinal Rules:**
1. **Wave 2 cannot retrace more than 100% of Wave 1** (i.e., cannot go below Wave 1 origin)
2. **Wave 3 cannot be the shortest impulse wave** (among Waves 1, 3, and 5)
3. **Wave 4 cannot enter the price territory of Wave 1** (cannot overlap Wave 1's high)

**Diagonal-Specific Rules:**

*Contracting Diagonal:*
- Wave 3 shorter than Wave 1
- Wave 5 shorter than Wave 3
- Wave 4 shorter than Wave 2
- Wave 4 cannot go past the end of Wave 2
- Wave 5 can overshoot or undershoot the trendline
- Leading Diagonal 5th CANNOT be truncated
- Ending Diagonal 5th CAN be truncated

*Expanding Diagonal:*
- Wave 1 shortest wave
- Wave 3 cannot be the shortest wave
- Wave 3 longer than Wave 1 & shorter than Wave 5
- Wave 4 longer than Wave 2
- Wave 4 cannot go past the end of Wave 2
- Wave 5 longest wave (larger than Wave 3)
- Wave 5 cannot be truncated

*Leading Diagonal:*
- Wave 2 is always a ZigZag Family
- Wave 2 cannot go beyond the start of Wave 1
- Wave 3 always goes beyond end of Wave 1
- Wave 4 cannot go past end of Wave 2
- Wave 4 is always a ZigZag Family
- Wave 5 cannot truncate

*Ending Diagonal:*
- Wave 2 is always a ZigZag Family
- Wave 2 cannot go beyond start of Wave 1
- Wave 3 always goes beyond end of Wave 1
- Wave 4 cannot go past end of Wave 2
- Wave 3 is always a ZigZag Family
- Wave 4 is always a ZigZag Family
- Wave 4 can only appear in contracting diagonal
- Wave 5 is always a ZigZag Family

**Corrective Pattern Rules:**
- Zigzag: Wave B cannot retrace more than 100% of Wave A; Wave C almost always ends beyond A; Wave C can be truncated
- Flat-Regular: Wave B retraces at least 90% of Wave A; Wave C usually ends beyond end of Wave A
- Flat-Expanded: Wave B retraces MORE than 100% the start of Wave A; Wave C goes beyond end of Wave A
- Flat-Running: Wave B retraces more than 100% the start of Wave A; Wave C does NOT go beyond end of Wave A
- Double Combo: Must be sideways correction; only one actionary wave can be a simple ZigZag
- Triple Combo: Must be sideways correction; only two actionary waves can be simple ZigZags
- Double Zigzag: Must be sharp correction; Wave W & Y must be simple ZigZags; Wave X cannot go past beginning of Wave W
- Triple Zigzag: Must be sharp correction; Wave W, Y & Z must be simple ZigZags
- Triangle: Wave C cannot go past end of Wave A; Wave D cannot go past end of Wave B; Wave E cannot go past end of Wave C; at least 4 of the waves must be simple ZigZags

### 2.4 Guidelines (Soft Rules)

- **Proportionality**: Corrective moves should be proportional in size
- **Alternation**: Wave 2 and Wave 4 should alternate in form — if Wave 2 is a sharp zigzag, Wave 4 should be a sideways flat/triangle, and vice versa
- **W2/W4 Duration Similarity**: If Wave 2 lasts 3 months, Wave 4 should be approximately 4-6 months, not a year. The pullback magnitude should also be similar
- **Wave 3 characteristics**: Usually the most vertical and longest wave in the sequence
- **Top-down approach**: Always start analysis from the largest timeframe to understand the macro wave context

### 2.5 Supporting Indicators

Aleks uses (from presentation):
- **RSI** (Relative Strength Index)
- **MACD** (Moving Average Convergence Divergence)
- **Stochastic**
- Fibonacci retracements, extensions, and projections

### 2.6 Case Studies from Presentation

**NVDA (Monthly Chart):**
- Shows complete multi-decade impulse wave from ~1992 to present
- Waves (1) through (5)/(8) labeled on monthly timeframe
- Channel lines drawn connecting wave peaks
- Demonstrates the fractal nature of waves and the importance of starting from the largest timeframe

**HOOD (Daily/Weekly Chart on TradingView):**
- Waves (1), (2), (3), (4) labeled
- RSI and MACD displayed below price
- Wave (4) finding support, with projected Wave (5) move higher
- Channel line connecting Waves (1)-(3) with parallel from (2)
- Demonstrates channel-based Wave 5 target projection

---

## 3. Reverse-Engineered Interpretation of Each Sample Trade

### 3.1 NFLX

**Alert Sequence:**
1. LONG Entry: $81.77 | Stop: $75 | Targets: $124, $150
2. Stop update: Stop moved to $81.77 (breakeven) | Targets unchanged: $124, $150

**Risk/Reward Analysis:**
- Initial risk: $6.77 (8.3%)
- R:R to T1: $42.23 / $6.77 = **6.2:1**
- R:R to T2: $68.23 / $6.77 = **10.1:1**
- Notable: T2/T1 price move ratio = $68.23 / $42.23 = **1.616 ≈ 1.618** (Fibonacci golden ratio)

**Inferred Wave Count:**
- *Likely setup*: **Early Wave 3 entry** after completion of large-degree Wave 2
- Stop at $75 represents the Wave 2 invalidation level (below Wave 1 origin or Wave 2 low)
- Entry at $81.77 is near the Wave 2 bottom
- The large R:R ratios (6:1, 10:1) are consistent with Wave 3 being the longest/strongest wave

**Target Derivation (inference):**
- T1 $124 and T2 $150 are in 1.618 proportion to each other (measured from entry), suggesting Fibonacci extension levels of Wave 1 projected from Wave 2 bottom
- T1 likely represents a 100% or 161.8% extension of a reference wave
- T2 likely represents a higher extension level (161.8% or 227.2%)

**Stop Management:**
- Stop moved to breakeven ($81.77) after price moved favorably, eliminating risk
- *Rule derived*: Move to breakeven once trade is comfortably in profit (approximately 1-2R of favorable movement)

**What went right:** High-conviction Wave 3 setup with excellent R:R. Breakeven stop protected capital.

---

### 3.2 ARM

**Alert Sequence:**
1. LONG Entry: $103.79 | Stop: $90 | Targets: $140, $184
2. Stop update: $90 → $105 | Targets: $140, $184
3. Stop update: $105 → $124 | Targets: $184, $184 (T1 removed — likely already passed $140)
4. Stop update: $124 → $130 | Targets: $184, $184
5. Partial profit: "Book 0.75 of position" — closed 75% at $175.37; remaining 25% stop raised to $150
6. Stop update on remainder: $150 → $170
7. Final close: Remaining 25% closed at $194.44

**Risk/Reward Analysis:**
- Initial risk: $13.79 (13.3%)
- R:R to T1 ($140): $36.21 / $13.79 = **2.6:1**
- R:R to T2 ($184): $80.21 / $13.79 = **5.8:1**
- Actual result: 75% @ $175.37 (+68.9%), 25% @ $194.44 (+87.3%)
- Blended return: 0.75 × 68.9% + 0.25 × 87.3% = **73.5% gain**

**Inferred Wave Count (confirmed from prior analysis):**
- Peak: $188.75 (Jul 2024) → Correction to Origin: $80.00 (Apr 2025) = 57.6% decline
- **Wave (1)**: $80.00 → $183.16 (+129%), 203 days
- **Wave (2)**: $183.16 → $100.02 (80.6% retrace, landing at .786 Fib)
- Entry at $103.79 = near Wave 2 bottom
- *Setup*: **Wave 3 entry after deep Wave 2 retrace**

**Target Derivation (computed):**
- Wave 1 move: $183.16 - $80.00 = $103.16
- From Wave 2 bottom ($100.02):
  - 0.382 × $103.16 = $39.41 → **$100.02 + $39.41 = $139.43 ≈ T1 of $140** ✓
  - Wave 1 high retest: **$183.16 ≈ T2 of $184** ✓
- **T1 = 38.2% Fibonacci extension of Wave 1 from Wave 2 bottom**
- **T2 = Wave 1 high (prior resistance / 0.786 extension)**

**Stop Placement (computed):**
- Initial stop $90: This is $10.02 below Wave 2 low ($100.02), representing ~10% below the corrective bottom
- *NOT* below Wave 1 origin ($80) — the stop provides a buffer below W2 but doesn't require price to retrace all of W1
- *Rule derived*: Place stop 8-13% below Wave 2 low, or below the nearest significant structural level

**Stop Management Progression:**
| Stage | Stop | Distance from Entry | Event |
|-------|------|-------------------|-------|
| Entry | $90 | -13.3% | Initial invalidation level |
| Update 1 | $105 | +1.2% | Small profit lock (~1R favorable) |
| Update 2 | $124 | +19.5% | Significant swing support |
| Update 3 | $130 | +25.2% | Tighter trail as momentum builds |
| Partial exit | $150 (on 25%) | +44.5% | 75% booked at $175.37, trail remainder |
| Update 4 | $170 (on 25%) | +63.8% | Trail below partial exit price |
| Final close | Market | +87.3% | Full exit at $194.44 |

**Critical Observations:**
- Stop moved to above entry ($105) after ~1R of favorable movement
- Each subsequent stop was raised to the most recent significant swing low
- Partial profit taken near T2 (75% at $175.37 vs T2 of $184)
- Remaining position given room to run with trailing stop
- Final exit was discretionary (close at market open when pre-market showed $194.44)

---

### 3.3 EVTC

**Alert Sequence:**
1. LONG Entry: $29.17 | Stop: $25.70 | Targets: $42, $52
2. Close: "We are closing EVTC trade at $29.30. Stock is not behaving as wave count proposes"

**Risk/Reward Analysis:**
- Initial risk: $3.47 (11.9%)
- R:R to T1: $12.83 / $3.47 = **3.7:1**
- R:R to T2: $22.83 / $3.47 = **6.6:1**
- Actual result: **+$0.13 (+0.4%) — closed at near breakeven**

**Inferred Wave Count:**
- *Likely setup*: Wave 3 or C-wave continuation entry
- Stop at $25.70 represents the invalidation level for the wave count
- Targets suggest a strong motive wave was expected

**Why Closed Early:**
- Price did not decline to stop ($25.70), but Aleks closed at $29.30 because the **wave count was not being confirmed by price action**
- This is the most important discretionary rule: **exit when the wave structure is wrong, regardless of whether the stop is hit**
- Possible reasons: price was chopping sideways instead of impulsing, sub-wave structure didn't match expectations, or a higher-timeframe count shifted

**Rules Derived:**
1. **Wave count invalidation exit**: If price action does not follow the expected wave structure within a reasonable time window, close the trade — do not wait for stop loss
2. **Time-based invalidation**: If the expected motive wave doesn't begin within X bars of entry, the setup may be wrong
3. **Preserve capital**: Small profit/breakeven exit > holding and hoping

---

### 3.4 RR

**Alert Sequence:**
1. LONG Entry: $2.52 | Stop: $2.30 | Targets: $4.70, $7.30
2. Status update: "RR stopped out — depend on the broker since it traded around SL. If you are stopped out, we will look for new entry after we see more upside"

**Risk/Reward Analysis:**
- Initial risk: $0.22 (8.7%)
- R:R to T1: $2.18 / $0.22 = **9.9:1**
- R:R to T2: $4.78 / $0.22 = **21.7:1**
- Actual result: **-$0.22 (-8.7%) — stopped out**

**Inferred Wave Count:**
- *Likely setup*: Low-priced stock with large Wave 3 potential
- Very high R:R ratios suggest deep Wave 2 retrace with massive Wave 3 extension targets
- T1 at $4.70 = 86.5% move, T2 at $7.30 = 189.7% move
- Stop at $2.30 represents the invalidation level (below Wave 2 low)

**Target Derivation (inference):**
- T1 $4.70 / T2 $7.30: The ratio $7.30 / $4.70 = 1.553 ≈ close to 1.618
- These appear to be Fibonacci extensions of Wave 1

**Rules Derived:**
1. **Clean stop-out**: When stopped out, the wave count is invalidated — do not re-enter immediately
2. **Re-entry condition**: "Look for new entry after we see more upside" — requires fresh confirmation that the wave structure is valid before re-entering
3. **Accept losses**: Not every setup works; a clean stop-out at -8.7% is acceptable with 10:1+ R:R setups

---

### 3.5 DELL

**Alert Sequence:**
1. LONG Entry: $126 | Stop: $119 | Target: $150 (chart shows wave count with "BUY 123.45" and "SL 119")
2. Stop update: $119 → $124
3. Stop update: $124 → $126 (breakeven)
4. Close: "We are closing DELL at market $127.81"

**Risk/Reward Analysis:**
- Initial risk: $7 (5.6%)
- R:R to T1: $24 / $7 = **3.4:1**
- Actual result: **+$1.81 (+1.4%) — closed near breakeven**

**Inferred Wave Count (from chart):**
- The embedded chart shows a 5-wave impulse count labeled on DELL
- Entry appears to be near the end of a corrective wave (Wave 4 or Wave 2)
- The chart shows the wave count with diagonal/channel lines
- RSI and MACD visible below the price chart
- *Likely setup*: **Wave 5 continuation** or **Wave 3 entry** on the daily chart

**Why Closed Near Breakeven:**
- Price reached only $127.81 after entry at $126 — very little movement toward the $150 target
- Stop was methodically moved: $119 → $124 → $126 (breakeven)
- Closed at market once stop was at breakeven — trade was not working as expected
- Similar to EVTC: discretionary exit when the wave count isn't producing the expected impulse

**Rules Derived:**
1. **Stall-at-breakeven exit**: If price stalls near the entry zone and doesn't produce expected momentum, close when stop reaches breakeven
2. **Timeframe discipline**: The trade was given time to work (multiple stop updates), but ultimately closed when it became clear the expected wave wasn't materializing
3. **Capital preservation priority**: Close non-performing trades to redeploy capital into better setups

---

### 3.6 Cross-Trade Summary Table

| Trade | Setup Type | Entry | Stop | Risk% | T1 | T2 | R:R (T1) | Result | Exit Reason |
|-------|-----------|-------|------|-------|----|----|----------|--------|-------------|
| NFLX | Wave 3 | $81.77 | $75 | 8.3% | $124 | $150 | 6.2:1 | In profit | Trail to BE+ |
| ARM | Wave 3 | $103.79 | $90 | 13.3% | $140 | $184 | 2.6:1 | **+73.5%** | Targets hit |
| EVTC | Wave 3/C | $29.17 | $25.70 | 11.9% | $42 | $52 | 3.7:1 | **+0.4%** | Count invalid |
| RR | Wave 3 | $2.52 | $2.30 | 8.7% | $4.70 | $7.30 | 9.9:1 | **-8.7%** | Stopped out |
| DELL | Wave 5/3 | $126 | $119 | 5.6% | $150 | — | 3.4:1 | **+1.4%** | Stall at BE |

**Derived statistics:**
- Average initial risk: **9.6%**
- Minimum R:R to first target: **2.6:1**
- Win rate (profitable): 3/5 = 60% (counting EVTC and DELL as small wins)
- Clear wins: 2/5 = 40% (NFLX, ARM)
- Losses: 1/5 = 20% (RR)
- Breakeven/small: 2/5 = 40% (EVTC, DELL)

---

## 4. Systematic Strategy Rules

### 4.1 Cardinal Rules (Never Violate)

These are the three inviolable Elliott Wave rules that must pass before ANY setup is considered:

```
RULE 1: Wave 2 cannot retrace more than 100% of Wave 1
  → If current price is below Wave 1 origin, the count is WRONG. No trade.

RULE 2: Wave 3 cannot be the shortest impulse wave (among W1, W3, W5)
  → When projecting Wave 3 targets, ensure W3 will be at minimum longer than W1
  → If W1 was large, W3 must be even larger OR W5 must be shorter than both

RULE 3: Wave 4 cannot enter Wave 1 price territory
  → The low of Wave 4 must remain above the high of Wave 1
  → If Wave 4 breaks below Wave 1 high, the impulse count is INVALID
```

### 4.2 Structural Validation Rules

Before identifying a trade setup, validate the wave structure:

```
VALIDATE_IMPULSE(W1_start, W1_end, W2_end, W3_end=None, W4_end=None, W5_end=None):
  1. W2_end > W1_start                        (Rule 1: W2 holds above W1 origin)
  2. W2_end < W1_end                           (W2 must retrace — not exceed W1)
  3. W2_retrace = (W1_end - W2_end) / (W1_end - W1_start)
     → Must be in {0.50, 0.618, 0.786, 0.887} zone (±5% tolerance)
  4. If W3_end known:
     → W3_end > W1_end                        (W3 must exceed W1 high)
     → W3_move ≥ W1_move                      (W3 not shortest — at minimum)
  5. If W4_end known:
     → W4_end > W1_end                        (Rule 3: W4 above W1 territory)
     → W4_retrace of W3 in {0.236, 0.382, 0.50, 0.618}
  6. If W5_end known:
     → W5_move: check not shortest among {W1, W3, W5}
```

### 4.3 Fibonacci Validation Tolerances

For programmatic detection, apply these tolerances to Fib levels:

```
RETRACE_TOLERANCE = 0.05  (±5% of the ratio)

Example: 61.8% retrace level
  → Valid range: 56.8% to 66.8%

FIB_RETRACE_ZONES (for Wave 2 of impulse):
  Zone A (deep):  0.786 ± 0.05 → 0.736 to 0.836
  Zone B (mid):   0.618 ± 0.05 → 0.568 to 0.668
  Zone C (mid):   0.500 ± 0.05 → 0.450 to 0.550
  Zone D (ultra): 0.887 ± 0.05 → 0.837 to 0.937

FIB_EXTENSION_TARGETS (for Wave 3 from Wave 2 bottom):
  1.618x, 1.75x, 2.272x, 3.618x of Wave 1 move

FIB_EXTENSION_TARGETS (for Wave 5 from Wave 4 bottom):
  1.0x of Wave 1, 0.618x of Waves 1-3, inverse 1.236-1.618 retrace of Wave 4
```

### 4.4 Risk Management Rules

```
MAX_RISK_PER_TRADE = 10-13% of entry price (derived from ARM/EVTC)
MIN_RR_TO_T1 = 2.5:1 (ARM was lowest at 2.6:1)
PREFERRED_RR_TO_T1 = 4:1 or higher

POSITION_SIZING:
  Risk per trade = 1-2% of portfolio
  Position size = (Portfolio × Risk%) / (Entry - Stop)

PARTIAL_PROFIT_SPLIT:
  75% of position closed at or near T1
  25% of position trails with stop for extended move toward T2+
```

---

## 5. Setup Archetypes

### 5.1 Setup A: Early Wave 3 Long (Primary Setup)

This is Aleks's primary trade — entering at the start of Wave 3 after a completed Wave 2.

**Required Market Structure:**
- Identifiable Wave 1 impulse (5-wave subdivision up from a significant low)
- Completed Wave 2 corrective structure (zigzag, flat, or combo pattern)
- Wave 2 has NOT broken below Wave 1 origin (Cardinal Rule 1)
- Price is near or at a valid Fibonacci retrace level of Wave 1

**Required Swing Points:**
- Wave 1 origin (start of impulse)
- Wave 1 peak (end of first impulse up)
- Wave 2 bottom (end of correction — must be above Wave 1 origin)

**Valid Fibonacci Retracement Zones:**
- Primary zone: 61.8%-78.6% retrace of Wave 1 (highest conviction)
- Secondary zone: 50%-61.8% retrace of Wave 1
- Deep zone: 78.6%-88.7% retrace of Wave 1 (valid but higher risk)

**Valid Entry Triggers:**
1. Price closes above the most recent corrective swing high (break of Wave 2 downtrend)
2. Price reclaims a key moving average (e.g., 20 EMA) on the entry timeframe after testing the Fib zone
3. Higher low forms within the Fib zone + momentum confirmation (RSI crossing above 50, MACD bullish crossover, or Stochastic turning up from oversold)
4. Break of the corrective channel (if Wave 2 forms a clear descending channel, a breakout above the upper trendline)

**Stop-Loss Placement:**
- Below the Wave 2 low by 3-5% (tight) to 8-13% (wide, as in ARM)
- OR below the Wave 1 origin if Wave 2 retraced deeply (e.g., >78.6%)
- The stop must be at a price where, if hit, the wave count is definitively WRONG

**Target Calculation:**
- **T1 (conservative)**: 38.2% Fibonacci extension of Wave 1 from Wave 2 bottom
  - Formula: `T1 = W2_bottom + (0.382 × W1_move)`
  - This is where ARM's T1 of $140 was derived
- **T2 (standard)**: Wave 1 high retest / 78.6% extension of Wave 1
  - Formula: `T2 = W1_peak` or `T2 = W2_bottom + (0.786 × W1_move)`
  - ARM's T2 of $184 ≈ Wave 1 peak ($183.16)
- **T3 (aggressive)**: 161.8% Fibonacci extension of Wave 1
  - Formula: `T3 = W2_bottom + (1.618 × W1_move)`
  - This is the standard Wave 3 target from textbook EWT
- **T4 (extended)**: 227.2% or 361.8% extension (for strong Wave 3 moves)

**Trade Invalidation:**
- Price breaks below Wave 2 low → stop loss hit → count invalid
- Price breaks below Wave 1 origin → Cardinal Rule violation → definitely invalid
- Price does not produce impulsive movement within reasonable time → EVTC-style exit
- Sub-wave structure of the expected Wave 3 does not show 5-wave impulse character

**Indicator Confirmation (Optional but Preferred):**
- RSI: Crossing above 50 from below, or bullish divergence at Wave 2 bottom
- MACD: Bullish crossover (signal line cross) or histogram turning positive
- Stochastic: Turning up from oversold (<20) zone

**Example Trades from Aleks:** NFLX, ARM, RR, possibly EVTC

---

### 5.2 Setup B: Wave 5 Continuation Long

Enter at the start of Wave 5 after a completed Wave 4.

**Required Market Structure:**
- Identifiable completed Waves 1, 2, 3 (impulse up)
- Completed Wave 4 corrective structure
- Wave 4 has NOT broken below Wave 1 high (Cardinal Rule 3)
- Waves 2 and 4 show alternation (different corrective types and/or proportional duration)

**Required Swing Points:**
- Wave 1 origin, Wave 1 peak, Wave 2 bottom, Wave 3 peak, Wave 4 bottom

**Valid Fibonacci Retracement Zones (Wave 4 of Wave 3):**
- Primary zone: 38.2% retrace of Wave 3
- Secondary zone: 23.6% or 50% retrace of Wave 3
- Deep zone: 61.8% retrace of Wave 3 (maximum — if deeper, count may be wrong)

**Valid Entry Triggers:**
- Same as Setup A, but applied to Wave 4 structure
- Break of Wave 4 corrective channel
- Price reclaiming the Wave 3 → Wave 4 decline's 38.2% retrace from below

**Stop-Loss Placement:**
- Below Wave 4 low by 3-5%
- Must be above Wave 1 high (otherwise Wave 4 overlap violates Rule 3)

**Target Calculation:**
- **T1**: Equal to Wave 1 move, measured from Wave 4 bottom
  - Formula: `T1 = W4_bottom + W1_move`
- **T2**: 61.8% of the Wave 1-to-Wave 3 move, measured from Wave 4 bottom
  - Formula: `T2 = W4_bottom + 0.618 × (W3_peak - W1_origin)`
- **T3**: 123.6%-161.8% inverse retracement of Wave 4
  - Formula: `T3 = W3_peak + (1.236 to 1.618) × W4_move`
- **Prior resistance**: Wave 3 peak (if Wave 5 just needs to retest)

**Trade Invalidation:**
- Wave 4 breaks below Wave 1 high → Cardinal Rule 3 violation
- Wave 5 fails to exceed Wave 3 peak (truncation) → exit at first sign of reversal
- No impulse character after entry → EVTC-style discretionary exit

**W2/W4 Alternation Check:**
- If Wave 2 was a deep sharp zigzag → Wave 4 should be a shallow sideways flat/triangle
- If Wave 2 was a shallow flat → Wave 4 should be a deeper zigzag
- Duration should be in same ballpark (if W2 = 3 months, W4 should be ~2-6 months)

**Example Trades from Aleks:** DELL (likely), HOOD case study from presentation

---

### 5.3 Setup C: C-Wave Continuation Long

Enter at the beginning of a bullish C-wave that completes a corrective pattern before the next motive wave resumes.

**Context:** This setup is used when a stock is in a larger uptrend and completes an ABC corrective pattern down — the C-wave down finishes, and the entry is placed for the resumption of the larger uptrend.

**Required Market Structure:**
- Identifiable larger-degree uptrend (at least one complete impulse wave up on a higher timeframe)
- ABC corrective structure forming within that uptrend
- Wave C appears to be completing or has completed (checking Fibonacci ratios of C relative to A)

**Valid Fibonacci Levels for C-Wave Completion:**
- C = 61.8% of Wave A (regular flat)
- C = 100% of Wave A (standard zigzag/flat)
- C = 127.2% of Wave A (expanded flat)
- C ≤ 161.8% of Wave A (maximum for expanded flat)

**Entry Trigger:**
- Price reaches a C-wave completion zone (Fibonacci level + structural support)
- Reversal candle pattern at the completion zone
- Momentum divergence (RSI/MACD bullish divergence at C-wave low)
- Break above the most recent corrective swing high

**Stop-Loss Placement:**
- Below the projected C-wave completion zone by 3-5%
- For a zigzag: below 127.2% extension of Wave A (from Wave B)
- Must validate that the stop level doesn't violate any higher-degree rules

**Target Calculation:**
- T1: Retest of the prior impulse high (before the correction began)
- T2: Next Fibonacci extension of the larger-degree wave structure

**Trade Invalidation:**
- C-wave extends significantly beyond 161.8% of Wave A
- Price action breaks critical structural levels on the higher timeframe
- The correction morphs into something more complex (double zigzag, triple combo)

---

### 5.4 Setup D: Diagonal Breakout Long

Enter after a confirmed breakout from a leading diagonal (Wave 1) or at the completion of a contraction within a larger impulse.

**Required Market Structure (Leading Diagonal in Wave 1 position):**
- 5-wave overlapping structure with converging or expanding trendlines
- Waves 1-3-5 are progressively shorter (contracting) or longer (expanding)
- All corrective waves (2, 4) are ZigZag family patterns
- Wave 4 overlap with Wave 1 is permitted (diagonals allow this)

**Entry Trigger:**
- Breakout above Wave 5 of the diagonal (for a leading diagonal in Wave 1 position, this signals the start of Wave 2 correction — NOT the entry point)
- The entry comes after the diagonal completes AND the subsequent Wave 2 correction finishes
- OR: Entry on breakout from an ending diagonal in Wave C position (signals end of correction)

**Stop-Loss Placement:**
- Below the Wave 2 correction low that follows the leading diagonal
- For ending diagonal completion: below the Wave 5 low of the diagonal

**Target Calculation:**
- Typically large targets because diagonals often precede strong moves
- Use standard Wave 3 extension targets from the diagonal-based Wave 1

**Trade Invalidation:**
- Leading diagonal rules are violated (e.g., Wave 5 truncated in a leading diagonal — not allowed)
- The subsequent correction exceeds 100% of the diagonal (Wave 2 breaks below Wave 1 origin)

---

### 5.5 Setup E: Larger Timeframe Bullish Impulse Continuation

Enter on a lower-timeframe setup when the higher-timeframe wave count is clearly bullish.

**Required Market Structure:**
- Weekly chart shows clear impulse wave structure in progress (e.g., in Wave 3 or starting Wave 5)
- Daily chart shows a pullback that represents a sub-wave correction within the larger motive wave
- 4H chart provides the precise entry timing

**Entry Logic:**
- Weekly: Confirm bullish wave count (e.g., price in Weekly Wave 3 up)
- Daily: Identify sub-wave correction (e.g., Daily Wave 2 or Wave 4 pullback)
- 4H: Enter when 4H shows reversal pattern at Daily support level

This is the multi-timeframe convergence setup — see Section 6 for full workflow.

---

## 6. Multi-Timeframe Workflow

### 6.1 Top-Down Process (from Aleks's Notes)

> "Start at largest timeframe to see where you are"

```
STEP 1: WEEKLY CHART — Determine Macro Wave Context
  - Identify the current position within the larger-degree wave count
  - Is the stock in a motive phase (Waves 1, 3, or 5 up) or corrective phase (Waves 2 or 4)?
  - If bearish (in a corrective structure down, or Wave 5 up appears complete): SKIP — no longs
  - If bullish (in Waves 1, 3, or early 5 up): PROCEED to Daily

STEP 2: DAILY CHART — Identify Actionable Wave Structure
  - Within the weekly bullish context, identify the sub-wave structure
  - Look for:
    a) Completed Wave 2 correction → potential Wave 3 setup (Setup A)
    b) Completed Wave 4 correction → potential Wave 5 setup (Setup B)
    c) Completed ABC correction → potential resumption setup (Setup C)
    d) Diagonal pattern → potential diagonal breakout setup (Setup D)
  - Measure Fibonacci retracements and validate against the ratio tables
  - Check W2/W4 alternation and proportionality guidelines
  - Confirm with RSI/MACD/Stochastic on the daily chart

STEP 3: 4-HOUR CHART — Refine Entry, Stop, and Confirmation
  - Use the 4H chart to pinpoint the exact entry level
  - Look for:
    a) Higher low formation within the daily Fibonacci zone
    b) Break of the corrective channel on 4H
    c) Momentum confirmation (RSI > 50, MACD bullish cross, Stoch turning up)
    d) Volume expansion on the breakout candle
  - Set precise stop just below the 4H swing low within the correction
  - This provides tighter risk compared to the daily-chart stop level
```

### 6.2 Active Trading Timeframe Selection

```
USE WEEKLY as active TF when:
  - Trading large-degree waves (Wave 1 lasted > 1 year)
  - Entry signals appear on the weekly chart
  - Hold time expected: months to quarters

USE DAILY as active TF when:
  - Trading intermediate-degree waves (Wave 1 lasted weeks to months)
  - Most common for S&P 500 / Russell 2000 stocks
  - Hold time expected: weeks to months
  - ARM, NFLX, DELL trades were likely on daily timeframe

USE 4-HOUR as active TF when:
  - Trading minor-degree waves (Wave 1 lasted days to weeks)
  - Used for entry refinement even when daily is the primary chart
  - Hold time expected: days to weeks
  - Can be used for faster-moving stocks or shorter-term sub-wave setups
```

### 6.3 Higher-Timeframe Conflict Resolution

```
RULE: Never take a lower-TF long when the higher-TF count is bearish

IF Weekly count is BEARISH (in corrective wave down or Wave 5 up complete):
  → SKIP all daily and 4H long setups on this stock

IF Weekly count is UNCLEAR (ambiguous structure):
  → Reduce position size to 50%
  → Use tighter stop
  → Only take highest-confidence daily setups (Setup A with .618-.786 retrace)

IF Weekly count is BULLISH but Daily is in correction:
  → Wait for daily correction to complete
  → Enter on 4H confirmation once daily correction hits Fib support zone

IF Weekly count is BULLISH and Daily count is BULLISH:
  → Full confidence — standard position size
  → Can use wider stops anchored to daily structure
```

---

## 7. Screening and Ranking Model

### 7.1 Universe Filters

```
LIQUIDITY_FILTER:
  Average daily volume (20-day) ≥ 500,000 shares
  Average daily dollar volume ≥ $5M

PRICE_FILTER:
  Stock price ≥ $5.00 (avoid penny stocks)
  Stock price ≤ $2,000 (practical position sizing)

TREND_FILTER:
  Price above 200-day SMA (confirms long-term uptrend context)
  OR: Price had a significant decline (40-75%) and is now forming Wave 1 off the bottom

VOLATILITY_FILTER:
  ATR(14) / Price × 100 ≥ 1.5% (enough movement for meaningful trades)
  ATR(14) / Price × 100 ≤ 8.0% (not too volatile for stop management)

RELATIVE_STRENGTH_FILTER:
  Stock's 3-month return > sector median (prefer relative strength)
  OR: Stock is bouncing off a deep correction (relative weakness turning to strength)
```

### 7.2 Swing Detection Logic

```
SWING_DETECTION(price_data, timeframe):
  Use scipy.signal.argrelextrema with order parameter:
    Weekly: order = 5 (5-week lookback on each side)
    Daily:  order = 8-15 (adaptive based on wave degree)
    4H:     order = 10-20 (more granular swings)

  For each timeframe, detect:
    swing_highs: local maxima in High prices
    swing_lows:  local minima in Low prices

  Filter swings:
    - Alternate high-low-high-low (no consecutive same-type swings)
    - Minimum swing size: ATR(14) × 1.5 (filter out noise)
    - Minimum 3 swings required to identify a wave

  Multi-order robustness:
    Run detection with orders [8, 10, 12, 15, 20]
    A swing that appears in 3+ order settings is "confirmed"
    Use confirmed swings for wave labeling
```

### 7.3 Fibonacci Zone Detection

```
FIB_ZONE_DETECT(wave1_start, wave1_end, current_price):
  wave1_move = wave1_end - wave1_start

  retrace_levels = {
    0.382: wave1_end - 0.382 * wave1_move,
    0.500: wave1_end - 0.500 * wave1_move,
    0.618: wave1_end - 0.618 * wave1_move,
    0.786: wave1_end - 0.786 * wave1_move,
    0.887: wave1_end - 0.887 * wave1_move,
  }

  # Check if current price is within tolerance of any Fib level
  for ratio, level in retrace_levels:
    if abs(current_price - level) / level < 0.03:  # 3% tolerance
      return {ratio: level, 'distance_pct': (current_price - level) / level}

  # Check if price is in a Fib zone (between two levels)
  for i, (r1, l1) in enumerate(sorted_levels):
    if i + 1 < len(sorted_levels):
      r2, l2 = sorted_levels[i + 1]
      if l2 <= current_price <= l1:
        return {'zone': f'{r1}-{r2}', 'upper': l1, 'lower': l2}
```

### 7.4 Breakout Detection

```
BREAKOUT_DETECT(price_data, swing_highs, swing_lows, lookback=20):
  recent_high = max(swing_highs in last lookback bars)
  corrective_channel_upper = regression_line through recent lower highs

  breakout_conditions = []

  # Condition 1: Close above recent corrective swing high
  if today_close > recent_corrective_swing_high:
    breakout_conditions.append('SWING_BREAK')

  # Condition 2: Close above corrective channel
  if today_close > corrective_channel_upper:
    breakout_conditions.append('CHANNEL_BREAK')

  # Condition 3: Higher low + momentum
  if recent_low > prior_low AND rsi > 50:
    breakout_conditions.append('HIGHER_LOW_MOMENTUM')

  return breakout_conditions
```

### 7.5 Momentum Confirmation

```
MOMENTUM_CONFIRM(price_data):
  rsi_14 = calculate_RSI(price_data, 14)
  macd_line, signal_line, histogram = calculate_MACD(price_data, 12, 26, 9)
  stoch_k, stoch_d = calculate_Stochastic(price_data, 14, 3)

  confirmations = 0

  # RSI confirmation
  if rsi_14 > 50 and rsi_14_prev <= 50:      # crossing above 50
    confirmations += 1
  if rsi_14 > 30 and rsi_14 made higher low while price made lower low:  # bullish divergence
    confirmations += 2  # divergence is stronger signal

  # MACD confirmation
  if macd_line > signal_line and macd_line_prev <= signal_line_prev:  # bullish crossover
    confirmations += 1
  if histogram > 0 and histogram_prev <= 0:  # histogram turning positive
    confirmations += 1

  # Stochastic confirmation
  if stoch_k < 20 and stoch_k > stoch_d:  # turning up from oversold
    confirmations += 1
  if stoch_k > 20 and stoch_k_prev < 20:  # crossing above oversold
    confirmations += 1

  return confirmations  # 0 = no confirmation, 1-2 = weak, 3-4 = moderate, 5+ = strong
```

### 7.6 Candidate Ranking System

```
SCORE_CANDIDATE(stock):
  score = 0

  # 1. Wave Structure Quality (0-30 pts)
  if wave2_retrace in 0.618 ± 0.05:    score += 30  # ideal retrace
  elif wave2_retrace in 0.786 ± 0.05:  score += 25  # deep but valid
  elif wave2_retrace in 0.500 ± 0.05:  score += 20  # moderate retrace
  elif wave2_retrace in 0.887 ± 0.05:  score += 10  # very deep, risky
  else:                                 score += 0   # not at Fib level

  # 2. Cardinal Rule Compliance (0-20 pts, pass/fail)
  if all_cardinal_rules_pass:           score += 20
  else:                                 return 0  # disqualified

  # 3. Multi-Timeframe Alignment (0-20 pts)
  if weekly_bullish AND daily_bullish:  score += 20
  elif weekly_bullish AND daily_neutral: score += 10
  elif weekly_neutral:                   score += 5
  if weekly_bearish:                     return 0  # disqualified

  # 4. Momentum Confirmation (0-15 pts)
  momentum_score = MOMENTUM_CONFIRM(price_data)
  score += min(momentum_score * 3, 15)

  # 5. Risk/Reward Quality (0-15 pts)
  rr_to_t1 = (t1 - entry) / (entry - stop)
  if rr_to_t1 >= 5.0:    score += 15
  elif rr_to_t1 >= 3.0:  score += 10
  elif rr_to_t1 >= 2.5:  score += 5
  else:                   return 0  # disqualified

  # 6. W2/W4 Alternation (0-5 pts, bonus)
  if w2_w4_alternate_in_form:  score += 3
  if w2_w4_similar_duration:   score += 2

  # 7. Volume Confirmation (0-5 pts, bonus)
  if volume_expanding_on_breakout:  score += 3
  if volume_contracting_in_correction:  score += 2

  # 8. Timing Freshness (0-10 pts, bonus)
  if days_since_w2_bottom <= 5:   score += 10
  elif days_since_w2_bottom <= 14: score += 7
  elif days_since_w2_bottom <= 30: score += 3

  return score  # Max theoretical: ~120 pts
```

**Output: Prioritized Watchlist**
- Rank stocks by score descending
- Group into tiers: A (score > 80), B (60-80), C (40-60)
- For each candidate, output: ticker, score, setup type, entry level, stop, T1, T2, R:R, timeframe, momentum status

---

## 8. Entry/Exit/Stop/Target Rules

### 8.1 Entry Rules (No Subjective Interpretation Required)

**Entry Rule 1: Wave 2 Fib Zone Breakout (Setup A)**
```
SETUP:      Completed Wave 1 + Wave 2 retrace to 50%-88.7% Fib zone
TIMEFRAME:  Daily (primary) or 4H (refinement)
TRIGGER:    Close above the highest high of the last 5 bars within the Wave 2 correction
ENTRY:      Next bar open after trigger candle closes
STOP:       Below Wave 2 low × (1 - 0.03 to 0.05) — i.e., 3-5% below W2 bottom
TARGET 1:   W2_bottom + 0.382 × W1_move (38.2% extension)
TARGET 2:   W1_peak (Wave 1 high retest) or W2_bottom + 0.786 × W1_move
TARGET 3:   W2_bottom + 1.618 × W1_move (standard W3 target)
RR_REQ:     R:R to T1 ≥ 2.5:1
```

**Entry Rule 2: Corrective Channel Breakout (Setup A/B)**
```
SETUP:      Wave 2 or Wave 4 forming a descending channel (≥3 touches)
TIMEFRAME:  Daily or 4H
TRIGGER:    Close above the upper trendline of the corrective channel
ENTRY:      Next bar open after breakout candle
STOP:       Below the most recent swing low within the channel × 0.97
TARGET 1:   Channel width projected from breakout point
TARGET 2:   Fibonacci extension targets as calculated in Setup A or B
RR_REQ:     R:R to T1 ≥ 2.5:1
```

**Entry Rule 3: Higher Low + Momentum Confirmation (Setup A/B/C)**
```
SETUP:      Price has made a higher low within the Fib retracement zone
TIMEFRAME:  4H (entry), Daily (context)
TRIGGER:    RSI(14) crosses above 50 AND MACD histogram turns positive
            AND price is above the higher low
ENTRY:      Close of the confirmation candle
STOP:       Below the higher low × 0.97
TARGET 1:   38.2% extension of reference wave
TARGET 2:   100% extension or prior high retest
RR_REQ:     R:R to T1 ≥ 3.0:1 (higher threshold due to less structural confirmation)
```

**Entry Rule 4: Wave 1 High Reclaim (Setup A — aggressive)**
```
SETUP:      After Wave 2 correction, price breaks back above Wave 1 peak
TIMEFRAME:  Daily
TRIGGER:    Close above W1_peak
ENTRY:      Next bar open
STOP:       Below the most recent swing low (which should be above W2 bottom)
TARGET 1:   W1_peak + 0.618 × W1_move (61.8% extension above W1 high)
TARGET 2:   W1_peak + 1.0 × W1_move (100% extension)
RR_REQ:     R:R to T1 ≥ 2.0:1
NOTE:       This is a later entry with more confirmation but worse R:R
```

### 8.2 Stop-Loss Rules

**Initial Stop Placement:**
```
FOR SETUP A (Wave 3 entry):
  stop = W2_low × (1 - buffer)
  buffer = 0.03 (tight) to 0.10 (wide)
  Choose buffer based on:
    - ATR(14): if ATR is large, use wider buffer
    - Wave 2 depth: if W2 retrace >78.6%, use wider buffer (more room for noise)
    - Stock price: higher-priced stocks may need % buffer; lower-priced need absolute $ buffer

FOR SETUP B (Wave 5 entry):
  stop = W4_low × (1 - buffer)
  buffer = 0.03 to 0.05
  CONSTRAINT: stop MUST be above W1_high (Cardinal Rule 3)

FOR SETUP C (C-wave completion):
  stop = C_wave_low × (1 - buffer)
  buffer = 0.03 to 0.05
  OR: stop below 127.2% extension of Wave A (beyond which the corrective structure changes)
```

### 8.3 Stop Management Rules (Trailing)

Based on ARM's stop progression:

```
STAGE 1 — Initial: Stop at invalidation level
  Trigger: Trade entry
  Action: Set stop at calculated initial level

STAGE 2 — Risk Reduction: Move stop to reduce risk by ~50%
  Trigger: Price moves favorably by ≥ 1R (one unit of initial risk)
  Action: Move stop to midpoint between entry and initial stop
  ARM example: Entry $103.79, Stop $90 (risk $13.79) → Price moved +$13.79 to ~$117
               → Stop moved to $105 (from $90)

STAGE 3 — Breakeven: Move stop to entry level
  Trigger: Price moves favorably by ≥ 2R OR reaches 50% of distance to T1
  Action: Move stop to entry price (breakeven)
  ARM example: Stop moved from $105 to breakeven was skipped; went to $124

STAGE 4 — Profit Protection: Trail stop to significant swing lows
  Trigger: Price makes new higher highs, forming identifiable swing lows
  Action: Move stop to below the most recent significant swing low
  ARM example: Stop → $124 → $130 (trailing below swing lows)

STAGE 5 — Partial Exit: Book majority of position at/near T1
  Trigger: Price reaches T1 or comes within 5% of T1
  Action: Close 75% of position at market; move stop on remaining 25% to below T1 or below the partial exit price
  ARM example: 75% closed at $175.37 (near T2 of $184), stop on 25% set at $150

STAGE 6 — Trail Remainder: Aggressive trail on remaining position
  Trigger: Price continues beyond T1
  Action: Trail stop on remaining 25% at 1-2 ATR below price or below each new swing low
  ARM example: Stop moved from $150 → $170; finally closed at $194.44

SPECIAL CASE — Wave Count Invalidation Exit:
  Trigger: Price action does not match expected wave structure
  Action: Close ENTIRE position immediately, regardless of P&L
  EVTC example: Closed at $29.30 (+0.4%) because wave count wasn't playing out
  Conditions that trigger:
    - Price chops sideways for > 2× the expected wave duration
    - Sub-wave structure shows corrective (3-wave) instead of impulsive (5-wave)
    - Key Fibonacci levels fail to act as support/resistance as expected
    - Higher-timeframe count changes due to new price action

SPECIAL CASE — Stall at Breakeven Exit:
  Trigger: Stop has been moved to breakeven + price is not progressing toward T1
  Action: Close position at market to free capital
  DELL example: Stop at breakeven $126, closed at $127.81 after insufficient progress
  Conditions that trigger:
    - Price has been between entry and +5% for more than 15 bars on entry timeframe
    - No momentum confirmation developing (RSI flat, MACD flat/declining)
```

### 8.4 Target Rules

**Target Hierarchy (from most conservative to most aggressive):**

```
FOR WAVE 3 SETUPS:
  T1_conservative = W2_bottom + 0.382 × W1_move     (38.2% extension)
  T1_standard     = W1_peak                          (Wave 1 high retest)
  T2_standard     = W2_bottom + 1.618 × W1_move     (161.8% extension)
  T2_aggressive   = W2_bottom + 2.272 × W1_move     (227.2% extension)
  T3_extended     = W2_bottom + 3.618 × W1_move     (361.8% extension)

FOR WAVE 5 SETUPS:
  T1 = W4_bottom + W1_move                           (Wave 5 = Wave 1)
  T2 = W4_bottom + 0.618 × (W3_peak - W1_origin)   (61.8% of W1-3)
  T3 = W3_peak + 1.618 × W4_move                    (161.8% inverse retrace)
  T_channel = Intersection with the 1-3 channel line projected from Wave 2

FOR C-WAVE SETUPS:
  T1 = correction_start (retest of the high before the correction)
  T2 = correction_start + 0.382 × prior_impulse_move (Fib extension beyond)

PRIOR RESISTANCE TARGETS:
  Always check: prior all-time high, prior significant swing high, round numbers
  If a Fib target coincides with prior resistance → higher confidence level
```

**Target Selection Logic:**
```
USE T1_conservative when:
  - R:R to T1 is already > 3:1
  - Wave structure is ambiguous or lower-confidence
  - Higher timeframe is neutral (not strongly bullish)

USE T1_standard + T2_standard when:
  - Clear wave count with high confidence
  - Multiple timeframes aligned bullish
  - This is the default setup (like ARM: T1=$140, T2=$184)

USE T2_aggressive or T3_extended when:
  - Wave 3 is clearly extending (5-wave sub-structure visible within Wave 3)
  - Strong momentum (RSI > 70, volume surge)
  - Only for the trailing 25% position after 75% is booked
```

---

## 9. Backtest Design

### 9.1 Required Historical Data

```
DATA REQUIREMENTS:
  - OHLCV (Open, High, Low, Close, Volume) data
  - Timeframes needed:
    - Weekly: minimum 5 years (to identify large-degree waves)
    - Daily: minimum 2 years (to identify intermediate waves and corrections)
    - 4-Hour: minimum 6 months (for entry refinement — optional for backtest V1)
  - Data source: yfinance (free), Alpha Vantage, or Polygon.io
  - Adjust for splits and dividends

DATA STORAGE:
  - Cache downloaded data locally to avoid repeated API calls
  - Store as parquet or feather format for fast reads
  - Update daily with incremental downloads
```

### 9.2 Swing Detection Without Lookahead Bias

```
CRITICAL: Use only data available AT THE TIME of each bar

CAUSAL_SWING_DETECTION(prices, order, current_bar_index):
  # Only use bars from [0, current_bar_index]
  # A swing high at bar i is confirmed only after 'order' bars have passed
  # i.e., swing at bar i is confirmed at bar i + order

  confirmed_highs = []
  confirmed_lows = []

  for i in range(order, current_bar_index - order):
    # Check if bar i is a local max using only bars [i-order, i+order]
    window = prices[i-order : i+order+1]
    if prices[i] == max(window):
      # This swing is confirmed at bar i + order
      confirmed_highs.append({
        'bar': i,
        'confirmation_bar': i + order,
        'price': prices[i]
      })

  # Similarly for lows
  # ...

  # Filter: only return swings whose confirmation_bar <= current_bar_index
  return [s for s in confirmed_highs if s['confirmation_bar'] <= current_bar_index]
```

### 9.3 Entry Simulation

```
SIMULATE_ENTRIES(stock_data, date_range):
  for each bar in date_range:
    # Get all confirmed swings up to this bar (no lookahead)
    swings = CAUSAL_SWING_DETECTION(stock_data, order, current_bar=bar)

    # Attempt wave labeling using only confirmed swings
    waves = LABEL_WAVES(swings)

    # Check each setup archetype
    for setup in [SETUP_A, SETUP_B, SETUP_C, SETUP_D]:
      if setup.conditions_met(waves, stock_data[:bar]):
        entry_price = stock_data[bar+1].Open  # next bar open (no same-bar entry)
        stop = setup.calculate_stop(waves)
        t1, t2 = setup.calculate_targets(waves)
        rr = (t1 - entry_price) / (entry_price - stop)

        if rr >= 2.5:
          open_trade = Trade(
            ticker=stock,
            entry_bar=bar+1,
            entry_price=entry_price,
            stop=stop,
            t1=t1,
            t2=t2,
            setup_type=setup.name
          )
```

### 9.4 Stop Update Simulation

```
SIMULATE_STOP_MANAGEMENT(trade, subsequent_bars):
  initial_risk = trade.entry_price - trade.stop
  max_price_seen = trade.entry_price
  current_stop = trade.stop

  for bar in subsequent_bars:
    price = bar.Close
    high = bar.High
    low = bar.Low

    # Check stop hit (use Low, not Close, for intrabar stop-outs)
    if low <= current_stop:
      trade.exit(price=current_stop, bar=bar, reason='STOP_HIT')
      return trade

    # Track max price
    max_price_seen = max(max_price_seen, high)
    favorable_move = max_price_seen - trade.entry_price

    # Stage 2: Move stop after 1R favorable
    if favorable_move >= initial_risk and current_stop < trade.entry_price - initial_risk * 0.5:
      new_stop = trade.entry_price - initial_risk * 0.5  # reduce risk by 50%
      current_stop = max(current_stop, new_stop)

    # Stage 3: Move to breakeven after 2R favorable
    if favorable_move >= 2 * initial_risk and current_stop < trade.entry_price:
      current_stop = trade.entry_price

    # Stage 5: Partial exit at T1
    if high >= trade.t1 and not trade.partial_taken:
      trade.partial_exit(price=trade.t1, pct=0.75, bar=bar)
      current_stop = max(current_stop, trade.t1 - initial_risk * 0.5)

    # Stage 6: Trail remainder
    if trade.partial_taken:
      trail_stop = max_price_seen - 2 * ATR(14, bar)
      current_stop = max(current_stop, trail_stop)

    # Check T2 hit
    if high >= trade.t2 and trade.partial_taken:
      trade.exit(price=trade.t2, bar=bar, reason='T2_HIT')
      return trade

  # If still open at end of backtest period
  trade.exit(price=bar.Close, bar=bar, reason='END_OF_DATA')
  return trade
```

### 9.5 Partial Exit Simulation

```
PARTIAL_EXIT_MODEL:
  When price reaches T1:
    - Close 75% of position at T1
    - Record partial P&L: 0.75 × (T1 - entry)
    - Remaining 25% continues with trailing stop
    - Total trade P&L = partial_pnl + remaining_pnl

  Remaining position outcome scenarios:
    a) Hits T2: remaining_pnl = 0.25 × (T2 - entry)
    b) Stopped out above entry: remaining_pnl = 0.25 × (stop - entry) where stop > entry
    c) Stopped out at/below entry: remaining_pnl = 0.25 × (stop - entry) ≈ 0

  Total P&L = partial_pnl + remaining_pnl
  Total P&L in R-multiples = total_pnl / initial_risk_dollars
```

### 9.6 Handling Special Cases

```
GAPS:
  - If price gaps below stop on open → exit at open price (slippage model)
  - If price gaps above T1 on open → partial exit at open price (favorable gap)
  - Track gap frequency and average slippage for risk metrics

EARNINGS:
  Option A (conservative): Close all positions 2 days before earnings
  Option B (moderate): Reduce position to 50% before earnings, trail tight stop on remainder
  Option C (aggressive): Hold through earnings if wave count is strong
  Recommendation: Start with Option A for backtest, then test B/C as variants

POSITION OVERLAP:
  - Maximum 5-6 concurrent positions (based on Aleks's update mentioning "4 positions" + RR)
  - If a new setup triggers but max positions reached → skip or replace lowest-scoring position
```

### 9.7 Metrics to Evaluate

```
PRIMARY METRICS:
  - Win Rate: % of trades that are profitable (target: > 40%)
  - Average R-Multiple: average P&L in units of initial risk (target: > 1.5R)
  - Profit Factor: gross_profit / gross_loss (target: > 1.5)
  - Expectancy: (win_rate × avg_win) - (loss_rate × avg_loss) (target: > 0)
  - Max Drawdown: largest peak-to-trough decline in equity curve (target: < 20%)

SECONDARY METRICS:
  - Average Hold Time: days from entry to exit
  - % of trades reaching T1: measures target accuracy
  - % of trades reaching T2: measures extension capture
  - Average MAE (Maximum Adverse Excursion): how far trades go against you before working
  - Average MFE (Maximum Favorable Excursion): how far trades go in your favor

SEGMENTED METRICS (analyze each separately):
  - By setup type (A, B, C, D, E)
  - By timeframe (4H, Daily, Weekly)
  - By Fibonacci retrace zone (50%, 61.8%, 78.6%, 88.7%)
  - By market regime (bull, bear, choppy — use SPY trend as proxy)
  - By sector
  - By market cap (large cap vs small cap from S&P 500 vs Russell 2000)
```

---

## 10. Pseudocode

### 10.1 Universe Scan

```python
def scan_universe():
    sp500 = fetch_sp500_tickers()      # ~500 tickers
    russell2000 = fetch_russell2000_tickers()  # ~2000 tickers (use S&P 600 + S&P 400 as proxy)
    universe = list(set(sp500 + russell2000))

    # Apply pre-filters
    filtered = []
    for ticker in universe:
        info = get_stock_info(ticker)
        if info.avg_volume_20d < 500_000: continue
        if info.price < 5.0 or info.price > 2000: continue
        if info.avg_dollar_volume < 5_000_000: continue
        filtered.append(ticker)

    # Download price data in batches
    data = {}
    for batch in chunk(filtered, 50):
        batch_data = yf.download(batch, period='2y', interval='1d')
        data.update(parse_batch(batch_data))

    return data
```

### 10.2 Swing Detection

```python
from scipy.signal import argrelextrema
import numpy as np

def detect_swings(df, orders=[8, 10, 12, 15, 20], min_swing_pct=0.03):
    """
    Detect swing highs and lows using multiple order parameters for robustness.
    Returns only swings confirmed by majority of order settings.
    """
    all_highs = {}  # bar_index -> count
    all_lows = {}

    for order in orders:
        high_idx = argrelextrema(df['High'].values, np.greater_equal, order=order)[0]
        low_idx = argrelextrema(df['Low'].values, np.less_equal, order=order)[0]

        for idx in high_idx:
            all_highs[idx] = all_highs.get(idx, 0) + 1
        for idx in low_idx:
            all_lows[idx] = all_lows.get(idx, 0) + 1

    # Keep swings confirmed by at least 3 order settings
    min_confirmations = 3
    confirmed_highs = [
        {'idx': idx, 'date': df.index[idx], 'price': df['High'].iloc[idx], 'type': 'high'}
        for idx, count in all_highs.items() if count >= min_confirmations
    ]
    confirmed_lows = [
        {'idx': idx, 'date': df.index[idx], 'price': df['Low'].iloc[idx], 'type': 'low'}
        for idx, count in all_lows.items() if count >= min_confirmations
    ]

    # Merge and sort
    swings = confirmed_highs + confirmed_lows
    swings.sort(key=lambda x: x['idx'])

    # Enforce alternation (no consecutive same-type swings)
    alternating = []
    for s in swings:
        if not alternating or alternating[-1]['type'] != s['type']:
            alternating.append(s)
        else:
            # Keep the more extreme one
            if s['type'] == 'high' and s['price'] > alternating[-1]['price']:
                alternating[-1] = s
            elif s['type'] == 'low' and s['price'] < alternating[-1]['price']:
                alternating[-1] = s

    # Filter minimum swing size
    filtered = [alternating[0]] if alternating else []
    for i in range(1, len(alternating)):
        move = abs(alternating[i]['price'] - alternating[i-1]['price'])
        pct_move = move / alternating[i-1]['price']
        if pct_move >= min_swing_pct:
            filtered.append(alternating[i])

    return filtered
```

### 10.3 Elliott Wave Candidate Detection

```python
def find_wave_candidates(swings, current_price, current_date):
    """
    Search through swing sequences to find valid Elliott Wave patterns.
    Returns list of candidate wave counts with quality scores.
    """
    candidates = []

    for i in range(len(swings) - 2):
        # Look for Wave 1 origin (low) -> Wave 1 peak (high) -> Wave 2 bottom (low)
        if swings[i]['type'] != 'low': continue
        if i + 1 >= len(swings) or swings[i+1]['type'] != 'high': continue
        if i + 2 >= len(swings) or swings[i+2]['type'] != 'low': continue

        w1_origin = swings[i]
        w1_peak = swings[i+1]
        w2_bottom = swings[i+2]

        # === CARDINAL RULE 1: W2 cannot retrace >100% of W1 ===
        if w2_bottom['price'] <= w1_origin['price']:
            continue

        w1_move = w1_peak['price'] - w1_origin['price']
        if w1_move <= 0: continue

        w2_retrace = (w1_peak['price'] - w2_bottom['price']) / w1_move

        # Check if W2 retrace is at a valid Fibonacci level
        fib_levels = [0.382, 0.500, 0.618, 0.786, 0.887]
        closest_fib = min(fib_levels, key=lambda f: abs(f - w2_retrace))
        fib_distance = abs(w2_retrace - closest_fib)

        if fib_distance > 0.08:  # not near any Fib level
            continue

        # Calculate entry, stop, targets
        entry = current_price  # or w2_bottom['price'] + small buffer
        stop = w2_bottom['price'] * 0.97  # 3% below W2 low

        # Targets
        t1 = w2_bottom['price'] + 0.382 * w1_move   # conservative
        t2 = w1_peak['price']                         # W1 high retest
        t3 = w2_bottom['price'] + 1.618 * w1_move   # standard W3

        # Risk/Reward
        risk = entry - stop
        if risk <= 0: continue
        rr_t1 = (t1 - entry) / risk
        rr_t2 = (t2 - entry) / risk

        if rr_t1 < 2.5: continue  # minimum R:R

        # === Check if this is an actionable setup ===
        days_since_w2 = (current_date - w2_bottom['date']).days

        candidate = {
            'setup_type': 'WAVE_3_ENTRY',
            'w1_origin': w1_origin,
            'w1_peak': w1_peak,
            'w2_bottom': w2_bottom,
            'w1_move': w1_move,
            'w2_retrace': w2_retrace,
            'closest_fib': closest_fib,
            'fib_distance': fib_distance,
            'entry': entry,
            'stop': stop,
            't1': t1,
            't2': t2,
            't3': t3,
            'risk_pct': risk / entry * 100,
            'rr_t1': rr_t1,
            'rr_t2': rr_t2,
            'days_since_w2': days_since_w2,
        }
        candidates.append(candidate)

    # Also search for Wave 5 setups (need 5 swing points)
    for i in range(len(swings) - 4):
        if swings[i]['type'] != 'low': continue
        seq_types = [s['type'] for s in swings[i:i+5]]
        if seq_types != ['low', 'high', 'low', 'high', 'low']:
            continue

        w1_origin = swings[i]
        w1_peak = swings[i+1]
        w2_bottom = swings[i+2]
        w3_peak = swings[i+3]
        w4_bottom = swings[i+4]

        # Validate impulse structure
        w1_move = w1_peak['price'] - w1_origin['price']
        w3_move = w3_peak['price'] - w2_bottom['price']

        # Cardinal Rule 1
        if w2_bottom['price'] <= w1_origin['price']: continue
        # Cardinal Rule 3
        if w4_bottom['price'] <= w1_peak['price']: continue
        # Cardinal Rule 2 (partial check)
        if w3_move < w1_move: continue  # W3 cannot be shortest

        w4_retrace = (w3_peak['price'] - w4_bottom['price']) / w3_move
        fib_levels_w4 = [0.236, 0.382, 0.500, 0.618]
        closest_fib_w4 = min(fib_levels_w4, key=lambda f: abs(f - w4_retrace))

        if abs(w4_retrace - closest_fib_w4) > 0.08: continue

        # Wave 5 targets
        entry = current_price
        stop = w4_bottom['price'] * 0.97

        t1 = w4_bottom['price'] + w1_move                    # W5 = W1
        t2 = w4_bottom['price'] + 0.618 * (w3_peak['price'] - w1_origin['price'])  # 61.8% of W1-3
        # Ensure W3 remains not the shortest
        max_w5 = w3_move - 0.01  # W5 cannot make W3 the shortest if W1 < W3
        # But W3 just needs to not be shortest among W1, W3, W5
        # So W5 CAN be larger than W3 as long as W3 > W1

        risk = entry - stop
        if risk <= 0: continue
        rr_t1 = (t1 - entry) / risk

        if rr_t1 < 2.0: continue

        days_since_w4 = (current_date - w4_bottom['date']).days

        candidate = {
            'setup_type': 'WAVE_5_ENTRY',
            'w1_origin': w1_origin,
            'w1_peak': w1_peak,
            'w2_bottom': w2_bottom,
            'w3_peak': w3_peak,
            'w4_bottom': w4_bottom,
            'w1_move': w1_move,
            'w3_move': w3_move,
            'w4_retrace': w4_retrace,
            'closest_fib': closest_fib_w4,
            'entry': entry,
            'stop': stop,
            't1': t1,
            't2': t2,
            'risk_pct': risk / entry * 100,
            'rr_t1': rr_t1,
            'days_since_w4': days_since_w4,
        }
        candidates.append(candidate)

    return candidates
```

### 10.4 Fibonacci Level Calculation

```python
def calculate_fib_levels(start_price, end_price, direction='retrace'):
    """
    Calculate Fibonacci retracement or extension levels.

    For retracements: measured from end_price back toward start_price
    For extensions: measured from a base price using the move distance
    """
    move = end_price - start_price

    if direction == 'retrace':
        # Retracement levels (Wave 2 of Wave 1, Wave 4 of Wave 3)
        ratios = [0.236, 0.382, 0.500, 0.618, 0.786, 0.887]
        levels = {}
        for r in ratios:
            levels[r] = end_price - r * move
        return levels

    elif direction == 'extend':
        # Extension levels (Wave 3 targets from Wave 2, Wave 5 targets from Wave 4)
        ratios = [0.382, 0.618, 0.786, 1.000, 1.236, 1.618, 1.750, 2.000, 2.272, 2.618, 3.618]
        levels = {}
        for r in ratios:
            levels[r] = start_price + r * abs(move)
        return levels


def calculate_wave3_targets(w1_origin, w1_peak, w2_bottom):
    """Calculate Wave 3 price targets using Fibonacci extensions."""
    w1_move = w1_peak - w1_origin

    targets = {
        'T1_conservative':  w2_bottom + 0.382 * w1_move,
        'T1_W1_retest':     w1_peak,
        'T2_standard':      w2_bottom + 1.618 * w1_move,
        'T2_alt':           w2_bottom + 1.750 * w1_move,
        'T3_aggressive':    w2_bottom + 2.272 * w1_move,
        'T4_extended':      w2_bottom + 3.618 * w1_move,
    }
    return targets


def calculate_wave5_targets(w1_origin, w1_peak, w3_peak, w4_bottom):
    """Calculate Wave 5 price targets."""
    w1_move = w1_peak - w1_origin
    w13_move = w3_peak - w1_origin
    w4_move = w3_peak - w4_bottom

    targets = {
        'T1_equal_w1':       w4_bottom + w1_move,
        'T2_618_w13':        w4_bottom + 0.618 * w13_move,
        'T3_inv_1236_w4':    w3_peak + 0.236 * w4_move,  # inverse 123.6% retrace
        'T3_inv_1618_w4':    w3_peak + 0.618 * w4_move,  # inverse 161.8% retrace
    }
    return targets
```

### 10.5 Entry Signal Generation

```python
def generate_entry_signals(df, candidates, indicators):
    """
    For each wave candidate, check if an entry signal is triggered today.
    Returns list of actionable trade signals.
    """
    signals = []

    for c in candidates:
        # Skip if too old (Wave 2/4 bottom was more than 60 days ago)
        if c.get('days_since_w2', c.get('days_since_w4', 999)) > 60:
            continue

        current_price = df['Close'].iloc[-1]
        current_bar = df.iloc[-1]
        prev_bar = df.iloc[-2]

        # Entry Rule 1: Break above recent corrective swing high
        recent_highs_in_correction = get_highs_since(df, c.get('w2_bottom', c.get('w4_bottom')))
        if recent_highs_in_correction:
            correction_swing_high = max(h['price'] for h in recent_highs_in_correction)
            if current_bar['Close'] > correction_swing_high and prev_bar['Close'] <= correction_swing_high:
                signal = create_signal(c, trigger='SWING_BREAK', entry=df['Open'].iloc[-1] if real_time else current_price)
                signals.append(signal)

        # Entry Rule 3: Higher low + momentum
        rsi = indicators['rsi'][-1]
        rsi_prev = indicators['rsi'][-2]
        macd_hist = indicators['macd_hist'][-1]
        macd_hist_prev = indicators['macd_hist'][-2]

        if rsi > 50 and rsi_prev <= 50 and macd_hist > 0:
            # Check for higher low
            recent_lows = get_lows_since(df, c.get('w2_bottom', c.get('w4_bottom')))
            if len(recent_lows) >= 2:
                if recent_lows[-1]['price'] > recent_lows[-2]['price']:
                    signal = create_signal(c, trigger='HIGHER_LOW_MOMENTUM', entry=current_price)
                    signals.append(signal)

    return signals


def create_signal(candidate, trigger, entry):
    """Create a trade signal from a candidate and trigger."""
    return {
        'ticker': candidate.get('ticker'),
        'setup_type': candidate['setup_type'],
        'trigger': trigger,
        'entry': entry,
        'stop': candidate['stop'],
        't1': candidate['t1'],
        't2': candidate['t2'],
        'rr_t1': (candidate['t1'] - entry) / (entry - candidate['stop']),
        'risk_pct': (entry - candidate['stop']) / entry * 100,
        'wave_data': candidate,
    }
```

### 10.6 Trade Management

```python
class TradeManager:
    def __init__(self, trade):
        self.trade = trade
        self.initial_risk = trade['entry'] - trade['stop']
        self.current_stop = trade['stop']
        self.max_price = trade['entry']
        self.partial_taken = False
        self.position_pct = 1.0  # 100%
        self.pnl = 0.0
        self.stage = 1  # current stop management stage

    def update(self, bar, atr):
        """Process one bar of price data. Returns exit signal or None."""
        high, low, close = bar['High'], bar['Low'], bar['Close']

        # Check stop hit first
        if low <= self.current_stop:
            exit_pnl = self.position_pct * (self.current_stop - self.trade['entry'])
            self.pnl += exit_pnl
            return {'action': 'STOP_HIT', 'price': self.current_stop, 'pnl': self.pnl}

        # Update max price
        self.max_price = max(self.max_price, high)
        favorable_move = self.max_price - self.trade['entry']

        # Stage 2: Risk reduction after 1R
        if favorable_move >= self.initial_risk and self.stage < 2:
            new_stop = self.trade['entry'] - self.initial_risk * 0.5
            self.current_stop = max(self.current_stop, new_stop)
            self.stage = 2

        # Stage 3: Breakeven after 2R
        if favorable_move >= 2 * self.initial_risk and self.stage < 3:
            self.current_stop = max(self.current_stop, self.trade['entry'])
            self.stage = 3

        # Stage 5: Partial exit at T1
        if high >= self.trade['t1'] and not self.partial_taken:
            partial_pnl = 0.75 * (self.trade['t1'] - self.trade['entry'])
            self.pnl += partial_pnl
            self.position_pct = 0.25
            self.partial_taken = True
            self.current_stop = max(self.current_stop, self.trade['t1'] - self.initial_risk)
            self.stage = 5

        # Stage 6: Trail remainder with ATR
        if self.partial_taken and self.stage >= 5:
            trail = self.max_price - 2.0 * atr
            self.current_stop = max(self.current_stop, trail)

        # Check T2 hit for remaining position
        if high >= self.trade['t2'] and self.partial_taken:
            remaining_pnl = self.position_pct * (self.trade['t2'] - self.trade['entry'])
            self.pnl += remaining_pnl
            return {'action': 'T2_HIT', 'price': self.trade['t2'], 'pnl': self.pnl}

        return None  # trade still open
```

### 10.7 Candidate Ranking

```python
def rank_candidates(candidates, price_data_dict, weekly_data_dict):
    """
    Score and rank all candidates. Returns sorted list with scores.
    """
    scored = []

    for c in candidates:
        ticker = c['ticker']
        score = 0

        # 1. Wave Structure Quality (0-30)
        fib_dist = c['fib_distance']
        if fib_dist < 0.02:     score += 30  # very close to Fib level
        elif fib_dist < 0.04:   score += 25
        elif fib_dist < 0.06:   score += 15
        elif fib_dist < 0.08:   score += 5

        # 2. Cardinal Rules (pass/fail — already filtered, so +20)
        score += 20

        # 3. Multi-TF Alignment (0-20)
        weekly_trend = assess_weekly_trend(weekly_data_dict.get(ticker))
        if weekly_trend == 'BULLISH':       score += 20
        elif weekly_trend == 'NEUTRAL':     score += 10
        elif weekly_trend == 'BEARISH':     continue  # skip entirely

        # 4. Momentum (0-15)
        df = price_data_dict[ticker]
        rsi = calculate_rsi(df, 14)
        macd_line, signal_line, hist = calculate_macd(df)
        stoch_k, stoch_d = calculate_stochastic(df)

        mom_score = 0
        if rsi.iloc[-1] > 50:              mom_score += 3
        if hist.iloc[-1] > 0:              mom_score += 3
        if hist.iloc[-1] > hist.iloc[-2]:  mom_score += 2
        if stoch_k.iloc[-1] > stoch_d.iloc[-1] and stoch_k.iloc[-1] < 80:
            mom_score += 3
        # Bullish divergence check
        if check_bullish_divergence(df, rsi):
            mom_score += 4
        score += min(mom_score, 15)

        # 5. R:R Quality (0-15)
        rr = c['rr_t1']
        if rr >= 5.0:    score += 15
        elif rr >= 4.0:  score += 12
        elif rr >= 3.0:  score += 8
        elif rr >= 2.5:  score += 5

        # 6. W2/W4 Alternation bonus (0-5)
        if c['setup_type'] == 'WAVE_5_ENTRY':
            w2_type = classify_correction(c.get('w2_data'))
            w4_type = classify_correction(c.get('w4_data'))
            if w2_type != w4_type:  score += 3  # different corrective forms
            w2_duration = c.get('w2_duration', 0)
            w4_duration = c.get('w4_duration', 0)
            if w2_duration > 0 and w4_duration > 0:
                ratio = max(w2_duration, w4_duration) / min(w2_duration, w4_duration)
                if ratio <= 2.0:    score += 2  # similar duration

        # 7. Volume (0-5)
        vol_20 = df['Volume'].rolling(20).mean().iloc[-1]
        vol_5 = df['Volume'].rolling(5).mean().iloc[-1]
        if vol_5 > vol_20 * 1.2:  score += 3  # volume expanding
        vol_in_correction = df['Volume'].iloc[-20:].mean()
        vol_before = df['Volume'].iloc[-40:-20].mean()
        if vol_in_correction < vol_before * 0.8:  score += 2  # volume dried up in correction

        # 8. Freshness (0-10)
        days = c.get('days_since_w2', c.get('days_since_w4', 999))
        if days <= 5:     score += 10
        elif days <= 14:  score += 7
        elif days <= 30:  score += 3

        c['score'] = score
        scored.append(c)

    # Sort by score descending
    scored.sort(key=lambda x: x['score'], reverse=True)

    # Assign tiers
    for c in scored:
        if c['score'] >= 80:    c['tier'] = 'A'
        elif c['score'] >= 60:  c['tier'] = 'B'
        elif c['score'] >= 40:  c['tier'] = 'C'
        else:                   c['tier'] = 'D'

    return scored
```

---

## 11. Open Questions and Assumptions

### 11.1 Assumptions Made (Not Directly Confirmed by PDFs)

1. **T1 = 38.2% extension**: This is reverse-engineered from ARM ($140 target matched 38.2% extension of W1 from W2 bottom). It's possible Aleks uses a different method for some trades. Other possibilities include sub-wave extensions or prior resistance levels.

2. **75/25 partial profit split**: This is directly from the ARM trade alerts. It's possible Aleks uses different ratios for different setups. The 75/25 split is used as the default until more data suggests otherwise.

3. **Stop buffer of 3-13%**: ARM's initial stop was ~10% below W2 low, but some trades might use tighter or wider buffers depending on the stock's volatility and wave degree.

4. **Wave count invalidation timeframe**: The EVTC exit ("not behaving as wave count proposes") is subjective. The system approximates this with time-based and structure-based rules, but the exact criteria Aleks uses are discretionary.

5. **Minimum R:R of 2.5:1**: The lowest R:R in the sample trades was ARM at 2.6:1 to T1. It's possible Aleks takes trades with lower R:R in high-confidence setups.

6. **Weekly trend as prerequisite**: The PDFs show "start at largest timeframe" but don't explicitly state that a bearish weekly count disqualifies daily longs. This is inferred as a logical systematic rule.

7. **Max concurrent positions**: Aleks mentioned holding "4 positions" at one point, plus RR was stopped out. The system assumes 5-6 max concurrent positions, but this may vary.

### 11.2 Open Questions

1. **Sub-wave counting**: How does Aleks validate that Wave 1 is a genuine 5-wave impulse (and not just a 3-wave corrective move)? The system currently counts swings but doesn't fully validate sub-wave structure.

2. **Corrective pattern identification**: The system detects retrace depth but doesn't classify whether Wave 2 is a zigzag vs flat vs combo. This affects alternation analysis and target precision.

3. **Leading/ending diagonal detection**: These patterns have overlapping waves and different rules — the system doesn't yet systematically scan for diagonals.

4. **Indicator weighting**: How much weight does Aleks give to RSI/MACD/Stochastic vs pure wave structure? The system treats them as confirmation (secondary) but Aleks may use them as filters.

5. **Market regime awareness**: Does Aleks reduce position size or stop trading entirely in bear markets? The system uses the weekly trend filter but doesn't explicitly handle market regime.

6. **Entry method precision**: Does Aleks enter at market on trigger candle close, or next bar open, or with limit orders? The system assumes next bar open.

7. **Triangle handling**: Triangles are common in Wave 4 position — does Aleks trade breakouts from triangles differently than standard Wave 4 completions?

8. **Time proportionality enforcement**: The guideline that W2 and W4 should be similar in duration — what tolerance does Aleks use? The system currently uses 2:1 max ratio.

9. **Truncated Wave 5**: How does Aleks handle scenarios where Wave 5 fails to exceed Wave 3 (truncation)? Does this affect position sizing or stop placement?

10. **Currency / international stocks**: The system currently targets US stocks (S&P 500 + Russell 2000). Does Aleks trade other markets where the same framework could apply?

### 11.3 What Is Directly Supported by PDFs vs. Inference

| Element | Source | Confidence |
|---------|--------|------------|
| Three cardinal rules | Directly stated in presentation | ✅ Certain |
| All Fibonacci ratios | Directly from presentation ratio tables | ✅ Certain |
| Pattern types and structures | Directly from presentation | ✅ Certain |
| RSI/MACD/Stochastic as tools | Directly stated in presentation | ✅ Certain |
| Top-down approach | Directly stated in notes | ✅ Certain |
| W2/W4 proportionality guideline | Directly stated in notes | ✅ Certain |
| Entry prices, stops, targets for 5 trades | Directly from trade alerts | ✅ Certain |
| 75/25 partial profit model | Directly from ARM alerts | ✅ Certain |
| Wave count invalidation exit | Directly from EVTC alert | ✅ Certain |
| Re-entry after stop-out needs confirmation | Directly from RR alert | ✅ Certain |
| T1 = 38.2% extension of W1 | Reverse-engineered from ARM data | ⚠️ High inference |
| T2 = W1 high retest | Reverse-engineered from ARM data | ⚠️ High inference |
| Stop = 3-13% below W2 low | Derived from trade stop levels | ⚠️ Moderate inference |
| Multi-TF conflict resolution rules | Logical inference from top-down approach | ⚠️ Moderate inference |
| Scoring/ranking weights | System design, not from Aleks | ⚠️ System assumption |
| Stall-at-breakeven exit rule | Derived from DELL trade | ⚠️ Moderate inference |
| Time-based invalidation | Logical inference from EVTC | ⚠️ Moderate inference |
| Max concurrent positions (5-6) | Derived from RR status update | ⚠️ Moderate inference |

---

*Framework version 1.0 — Derived from Aleks EWT Presentation + 5 Sample Trades*
*Generated 2026-05-27*
