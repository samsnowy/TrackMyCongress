# Research Findings

Results from running the congress trade analysis. Updated as new analysis is run.

---

## Dataset (as of 2026-05-06)

| Source | Stocks | Options | Members | Date Range |
|---|---|---|---|---|
| House (clerk PDFs) | 7,095 | 156 | 125 reps | 2022–2025 |
| Senate (efdsearch) | 4,080 | 306 | 47 senators | 2022–2026 |
| **Combined** | **~10,000** | **462** | **~170** | **2022–2026** |

Options breakdown: House 141 calls / 12 puts (call-heavy). Senate 73 calls / 169 puts (put-heavy — Tuberville straddles explain this entirely).
Only 9 House reps and ~15 senators traded options at all. Options trading is highly concentrated.

**Coverage caveat:** Neither source includes option exercise events — only the original purchase/sale of the contract. Exercise events also do not appear as stock purchases in any data source (confirmed by auditing all transaction types). No false signal risk from exercises.

---

## Follow-Disclosure Backtest (Step 2)

**Setup:** Buy at close on `ReportDate` (first day you realistically know about the trade). Hold N days. Compare return vs SPY over same window. Excess = trade return minus SPY return over the identical window.

**Dataset:** 4,570 purchases, 114 politicians, 2022–2026.

### Holding Period Sensitivity — Reliable Group

Reliable = avg excess >2% AND ≥20 trades. The reliable group is recomputed at each hold period, so the politician composition (and trade count) varies slightly — politicians who outperform at short holds differ from those who outperform at long holds.

> **Note on the old 2.4% number:** earlier versions of this analysis used a loose filter (>0% excess, ≥5 trades), which included noise traders with tiny sample sizes. Tightening to >2%/≥20 trades removed those and raised the measured excess to 4.8% at 90d on the same dataset. The 2.4% was diluted by chance winners, not a different strategy.

| Hold | Trades | Avg Excess | Win% | Avg Ret | SPY |
|------|--------|-----------|------|---------|-----|
| 10d  | 164    | +2.6%     | 68%  | +3.6%   | +1.0% |
| 20d  | 95     | +4.9%     | 70%  | +6.1%   | +1.2% |
| 30d  | 158    | +5.4%     | 66%  | +7.0%   | +1.6% |
| 60d  | 476    | +4.8%     | 61%  | +7.8%   | +3.0% |
| 90d  | 672    | +4.8%     | 55%  | +9.2%   | +4.3% |

**Key observation:** alpha peaks in the 20–30d range (+5.4%) and remains strong at 90d (+4.8%). Win rate is notably higher at short holds (68–70%) then compresses toward 55% at 90d — the short-hold signal may be detecting fast-moving accumulation events. The edge at 90d comes from magnitude (big winners), not win frequency.

### Full Reliable Group at 90d (congress_rankings.csv, generated 2026-05-06)

12 politicians with avg excess >2% and ≥20 trades on the combined House + Senate dataset.

| Politician | Trades | Avg Excess | Win% |
|---|---|---|---|
| Daniel S Sullivan | 40 | +14.8% | 87.5% |
| Tim Moore | 41 | +12.9% | 65.9% |
| David H McCormick | 24 | +8.9% | 83.3% |
| Byron Donalds | 29 | +6.4% | 44.8% |
| Cleo Fields | 81 | +6.3% | 61.7% |
| Greg Landsman | 22 | +5.8% | 63.6% |
| Thomas Suozzi | 30 | +4.9% | 56.7% |
| Julie Johnson | 42 | +3.7% | 64.3% |
| Shelley M Capito | 34 | +3.0% | 58.8% |
| Richard Dean Dr McCormick | 24 | +2.5% | 58.3% |
| Sheldon Whitehouse | 20 | +2.1% | 50.0% |
| Thomas H Tuberville | 285 | +2.1% | 42.8% |

Most statistically meaningful (high trade count + excess): **Cleo Fields (81 trades, +6.3%), Tim Moore (41, +12.9%), Daniel Sullivan (40, +14.8%), Julie Johnson (42, +3.7%)**. Tuberville (285 trades) has the largest sample but lowest excess — primarily an options straddle trader whose stock picks are incidental.

### Interpretation

- 672 trades in the 12-pol reliable group at 90d is the all-trades baseline
- The edge peaks at 20–30d and remains meaningful at 90d — consistent with an informational signal that plays out over months
- Short-hold win rates (68–70%) are unusually high — worth investigating whether this is data noise or a real fast-signal effect
- Best trade: IREN held by Cleo Fields (+256.7% excess). Worst: CNC held by Gilbert Cisneros (-69.4% excess)

### In-sample caveat

The 12 "reliable" politicians were selected using the same 2022–2026 dataset the backtest runs on — there is no out-of-sample validation. Under the null hypothesis, roughly half of 114 tested politicians would show positive excess by chance alone. The >2%/≥20 trades filter is stricter than before but still in-sample. Regenerate `congress_rankings.csv` periodically as new data accumulates to track whether these politicians remain consistent.

---

## High-Conviction Strategy (Step 5)

**Setup:** Same as Follow-Disclosure, but restricted to trades filed with amounts >$15k (excludes the `$1,001–$15,000` bracket). 78% of all filings are in that low-conviction bracket. The hypothesis: when a politician puts meaningful money down, the signal is stronger.

**HC reliable group:** 4 politicians with avg excess >2% and ≥20 high-conviction (>$15k) trades.

| Politician | HC Trades | Avg Excess | Win% |
|---|---|---|---|
| Tim Moore | 38 | +12.2% | — |
| David McCormick | 24 | +8.9% | — |
| Cleo Fields | 64 | +7.1% | — |
| Virginia Foxx | 28 | +2.8% | — |

### HC Holding Period Sensitivity

| Hold | Trades | Avg Excess | Win% | Avg Ret | SPY |
|------|--------|-----------|------|---------|-----|
| 10d  | 38     | +2.5%     | 71%  | +3.3%   | +0.8% |
| 20d  | 62     | +5.9%     | 77%  | +6.5%   | +0.6% |
| 30d  | 90     | +5.9%     | 69%  | +6.6%   | +0.8% |
| 60d  | 154    | +7.7%     | 60%  | +11.5%  | +3.7% |
| 90d  | 154    | **+7.9%** | 64%  | +13.0%  | +5.1% |

**Key finding:** restricting to meaningful-size trades (+7.9% at 90d) nearly doubles the excess vs all-trades (+4.8%). The HC group also has better win rates across all hold periods (64% at 90d vs 55% for all-trades). This is the live strategy.

**Why Strategy 2 (sell-filing exit) doesn't work for HC:** only 30 matched buy/sell pairs exist for the 4 HC politicians — too small a sample for a stable signal.

### HC group composition audit (2025 OOS data)

Per-politician breakdown of what they are actually trading and where the alpha comes from:

**David McCormick (+8.9% excess) — pure Bitcoin DCA, not stock-picking.**
All 24 HC trades are BITB (a Bitcoin spot ETF). He is systematically dollar-cost-averaging into BTC, not making individual stock calls. The +8.9% excess means Bitcoin outperformed SPY over those holding windows — it is crypto exposure, not informational edge. This number will be positive when BTC beats SPY and negative when it does not. McCormick should not be in a stock-signal strategy.

**Cleo Fields (+7.1% excess) — one outlier + mixed Mag-7.**
IREN (a Bitcoin mining stock) returned +256.7% excess on a single trade and is doing heavy lifting on his average. His actual Mag-7 buys are noisy: GOOG/TSM/AAPL are positive, but MSFT (-7.7%), META (-20.4%), AMZN (-3.3%), and NFLX (-13.8%) are all negative. Strip IREN and his edge is much weaker. A bull-market tech concentration bias is a real concern, though his Mag-7 results are not uniformly positive.

**Tim Moore (+12.2% excess) — contrarian industrials, most defensible.**
Not a tech-bull story at all: HOG, Ford (F), AAL, HY (Hyster-Yale), INTC, VZ. INTC carries the result (+78.8% excess across 3 trades) — a beaten-down semiconductor turnaround play, not momentum tech. His other names (AAL, VZ, CNC) are also value/cyclical picks. If the INTC calls reflect genuine informational advantage, this is the strongest case for real signal in the HC group.

**Virginia Foxx (+2.8% excess) — retired January 2025, 1 OOS trade.**
No longer in Congress. Her 28 HC trades that built the training-period ranking are gone.

### Conclusion

The HC group's +7.9% headline figure is significantly biased:
- McCormick's contribution is purely a Bitcoin allocation decision.
- Fields' contribution is dominated by one outlier (IREN) and is otherwise weak on Mag-7 names.
- Moore is the one politician with a plausible informational edge, but his sample is 38 trades across contrarian names in a single year.
- Foxx has retired.

Following the HC group as a basket is questionable. A cleaner approach would be to monitor Moore alone (contrarian industrials) and exclude McCormick entirely. Fields could stay with the caveat that IREN-type outliers are low-frequency and hard to count on repeating.

---

## Sell-Lag Pair Analysis (Step 3)

**Setup:** Match each politician's buy + sell on the same ticker. Measure price at four points: `buy_tx`, `buy_filed`, `sell_tx`, `sell_filed`. 1,424 matched pairs across 164 politicians, 598 tickers.

### Holding Behaviour

- Median hold: **128 days** (4+ months) before selling
- Mean hold: 146 days
- Median sell disclosure lag: **27 days** (mean 46 days — some very late filers skew it)

### The Sell-Lag Drift is Positive

| Scenario | Avg Return | Win% |
|---|---|---|
| Exit when they sell (`sell_tx`) | +3.9% | 50% |
| Exit when sell is filed (`sell_filed`) | +5.6% | 50% |
| 30d after sell filing | +7.4% | — |

**Price drift during sell lag window: +1.7%** — price rises on average while they're sitting on an undisclosed sell. 44% of pairs do drop, but the average is positive.

**Hypothesis disproved:** the sell filing is NOT a warning sign to exit early. Waiting for the filing captures an extra +1.7%. Holding even longer (30d after filing) adds another +1.7%.

### Sell Lag Effect by Disclosure Speed

| Lag Bucket | Pairs | Avg Move During Lag | % Negative |
|---|---|---|---|
| <=15d | 203 | +1.3% | 56% |
| 16-30d | 662 | +1.3% | 41% |
| 31-45d | 481 | +1.3% | 44% |
| 46-60d | 6 | +3.2% | 33% |
| >60d | 63 | +15.9% | 37% |

The >60d outlier group (+15.9%) is worth investigating — these late filers held through large moves.

---

## Options Analysis (Step 4)

**Dataset:** 462 total options trades. House: 141 calls / 12 puts across 9 reps. Senate: 73 calls / 169 puts across ~15 senators.

### Senate "Put-Heavy" Mystery — Resolved

Entirely explained by **Tommy Tuberville trading straddles** (buying both calls and puts on the same ticker/expiry). Senate is not hedging or making bearish bets — it's one senator running a volatility strategy.

### Tuberville Straddle Analysis

- **Straddle pairs identified:** 5 (same ticker + expiry month, both C+P with matching strike data)
- **Avg absolute move to expiry: 20.3%**
- **% moved >10%: 75%** / **% moved >20%: 50%**

At a typical straddle cost of ~10–15% of stock price, the majority moved enough to be profitable. Note: Senate options data has 0/306 strikes recorded — straddle matching is limited to the subset with parseable expiry data.

### House Call Purchase Analysis

| Hold | n | Avg Stock Return | SPY | Excess | Win% |
|------|---|-----------------|-----|--------|------|
| 30d  | 47 | +3.8% | +0.0% | **+3.8%** | 57% |
| 60d  | 47 | +0.6% | -0.3% | **+0.9%** | 53% |
| 90d  | 47 | +0.4% | -0.4% | **+0.8%** | 55% |

**Key finding:** signal is strongest at 30d (+3.8% excess) and collapses sharply by 60d (+0.9%) — much faster fade than previously estimated. Options signals use a 30-day hold in the live strategy. n=47 is 47 call *purchases* from 59 total House option purchases (the rest are puts).

### Deep ITM Call Analysis

Audited all 41 House call purchases with known strike data against stock price on filing date:

| Moneyness | Count |
|---|---|
| Deep ITM (>20% ITM, strike/price < 0.80) | 29 |
| Moderately ITM (10-20%, 0.80-0.90) | 1 |
| Near/At the money (0-10%) | 0 |
| OTM | 8 |

**29/38 (76%) of known-strike calls are deeply ITM.** This is deliberate — Gottheimer and Pelosi are buying synthetic long positions with leverage, not speculative bets. Key examples:
- Gottheimer MSFT: consistently 40-60% ITM across all purchases (2022–2026)
- Pelosi NVDA $80 (filed Jan 2025): 41.9% ITM vs price of $137.7
- Pelosi AMZN $150 (filed Jan 2025): 33.6% ITM vs price of $225.9
- Pelosi PANW $200 (filed Feb 2024): OTM at filing but PANW subsequently rallied — excluded by ITM filter

**Signal for live strategy:** call purchase + known politician + strike/current_price < 0.85 → buy the underlying stock.

### Options Data Source

Live options detection uses the official scraped options CSVs (`congress_options.csv` and `senate_options.csv`). The Quiver cache path in `fetcher.py` is retained for legacy exploratory commands, but Quiver access is no longer required for live detection.

Exercise events are absent from all data sources — they do not appear as stock purchases and create no false signals.

---

## Strategy 2: Hold Through the Sell Filing

**Setup:** Buy at close on `buy_filed` (same entry as Strategy 1). Exit at close on `sell_filed + N days` — i.e., hold until the *same politician* publicly files their sell, then hold N more days. Filtered to the 12 reliable politicians (excess >2%, ≥20 trades). 334 matched buy/sell pairs.

| Hold after sell filing | Pairs | Avg Ret | SPY | Excess | Win% |
|---|---|---|---|---|---|
| sell_filed +0d  | 334 | +11.1% | +7.5%  | +3.7% | 43% |
| **sell_filed +10d** | **334** | **+11.8%** | **+7.8%** | **+4.0%** | **49%** |
| sell_filed +20d | 334 | +12.4% | +8.7%  | +3.7% | 52% |
| sell_filed +30d | 334 | +13.2% | +9.6%  | +3.6% | 50% |
| sell_filed +60d | 334 | +15.1% | +11.4% | +3.6% | 47% |
| sell_filed +90d | 334 | +17.4% | +13.6% | +3.8% | 43% |

**Strategy 1 benchmark:** fixed 90d hold → +4.8% excess (12-pol strict filter), 55% win rate.

**Key findings:**
- +10d after sell filing is the sweet spot at +4.0% excess — beats Strategy 1 by +1.6% with 49% win rate
- Win rate peaks at 52% at +20d then fades — the +10d point balances excess and win rate best
- The pattern is no longer monotonic: excess peaks at +10d then plateaus rather than climbing to +90d
- The implication: hold about 10 days past the sell filing, then exit. Holding longer doesn't add return with the tighter politician group.

**The bull market caveat:** The entire 2022–2026 dataset is a mostly bullish regime. Politicians — particularly reliable ones — skew heavily toward large-cap tech (NVDA, MSFT, AAPL, GOOGL). In a bull market, buying large-cap tech and holding longer almost always beats SPY on a rolling basis. It is difficult to distinguish between genuine informational edge and a tech-heavy portfolio running in a tech bull market. The excess return vs SPY controls for market direction but does not control for sector or factor exposure. A beta/factor-adjusted analysis would isolate whether the edge survives after accounting for tech concentration.

---

## Live Strategy (Step 6)

**First dry run: 2026-04-25**

---

## Walk-Forward Validation (Step 7)

**Setup:** Train reliable-group selection on 2022–2023 data only. Then run backtest on 2024–2026 using only the pre-selected politicians — no re-ranking allowed. Run via: `python main.py walkforward`.

Split date: `2024-01-01`. Hold: 90d. Filter: >2% excess, ≥20 trades.

### All-trades result

| Metric | Training (IS) | Test (OOS) |
|---|---|---|
| Trades | 176 | 186 |
| Avg Excess | +5.7% | +0.8% |
| Win Rate | 64% | 49% |

**Training reliable group (3 politicians):** Daniel S Sullivan (+14.8% IS), Thomas Suozzi (+4.9% IS), Markwayne Mullin (+2.5% IS).

OOS breakdown:
- Sullivan: no OOS trades (retired / left Congress after 2024 election)
- Suozzi: no OOS trades (lost re-election Nov 2024)
- Mullin: +0.8% OOS, 186 trades, 49% win rate

**Alpha retention: 14%.** Verdict: edge mostly decayed OOS — mostly driven by politician turnover (2/3 left Congress), not strategy failure.

### High-conviction result (>$15k trades)

| Metric | Training (IS) | Test (OOS) |
|---|---|---|
| Trades | 83 | 126 |
| Avg Excess | +2.2% | +1.4% |
| Win Rate | 57% | 48% |

**Training reliable group (2 politicians):** Virginia Foxx (+2.5% IS), Markwayne Mullin (+2.0% IS).

OOS breakdown:
- Foxx: +9.6% OOS — but only 1 trade, not statistically meaningful
- Mullin: +1.4% OOS, 125 trades, 48% win rate

**Alpha retention: 66%.** Verdict: edge substantially survived OOS for the HC variant.

### Key caveat — live strategy politicians absent from training

The live HC strategy's best performers (Tim Moore, McCormick, Cleo Fields) cannot appear in the training set:

- Tim Moore and David McCormick won their races in November 2024 and took office January 2025 — all trades post-2024.
- Cleo Fields was elected to the 119th Congress November 2024 — all 64 HC trades are post-2024.

The walk-forward therefore tests a different, weaker politician set than the live strategy uses. The HC test (66% retention on Foxx/Mullin) is a floor estimate; whether Moore, McCormick, and Fields would retain their edge OOS remains untested because there is no pre-2024 data for them to train on.

**Implication:** as the 119th Congress accumulates more trade data (2025–2026), a meaningful out-of-sample test for Moore/McCormick/Fields will become possible. Re-run `walkforward` after mid-2026 when these politicians have 18+ months of OOS data.

---

## Known Limitations

Issues identified during code review that are documented here rather than patched, because fixing them would require meaningful rework with uncertain payoff.

### Methodology

**In-sample ranking bias (backtest.py + strategy.py)**
The "reliable politician" list is built from the same 2022–2026 data the backtest runs on. Politicians are selected ex-post by performance, then credited with performance on the data that selected them. Under the null hypothesis, roughly half of any tested group shows positive excess by chance — which is close to the observed 37/73. The list is a starting hypothesis, not an out-of-sample validated edge. Mitigation: regenerate `congress_rankings.csv` periodically as new data accumulates so the list tracks fresh signal, not just historical noise survivors.

**Entry price timing (backtest.py)**
Backtest entry uses the close on `ReportDate` (or first trading day after). In practice, STOCK Act filings often post after market close, meaning the realistic earliest entry is next-day open. Same-day close slightly overstates entry price precision. Effect size is small (open vs close is typically <0.5%), but excess return numbers are optimistic by roughly this margin.

**Options ITM filter uses today's price (strategy.py)**
The live strategy checks whether a call is deep-ITM against the *current* stock price, not the price on the filing date. A signal filed 20 days ago is re-evaluated against today's level. This is a current-state filter, not a replay of the original condition — if the stock ran up since filing, the filter approves a signal where you're chasing a move that already happened. Documented in `strategy.py` inline. The alternative (fetching historical price at filing date for each signal check) adds complexity for a marginal accuracy gain on 30-day-lookback signals.

**Live hold period vs backtest (live.py)**
`planned_exit` is anchored to `sig["report_date"]` (the disclosure date), but the actual order fills on `today`. If a signal is 5 days old within the 7-day lookback, the live hold period is 85 days, not 90. The live strategy entry price also differs from the backtest entry (today's price vs ReportDate close). The backtest numbers are not directly comparable to live performance.

### Code / Operational

**Legacy Quiver cache staleness (fetcher.py)**
`main.py congress` and other legacy Quiver helpers can still serve `congress_trades.csv` when the API is unavailable. The live strategy no longer depends on this cache; it reads the scraped official CSVs produced by `python -m congress.scrape_all`.

**Phantom positions on broker failure (live.py)**
If Alpaca is unreachable in live (non-dry-run) mode, `_place_order` is `None`, the order block is skipped, but the position is still appended to `strategy_state.json` with `order_id = "dry-run"`. The state will show an open position that Alpaca doesn't hold. Guard: always run `python main.py account` first to confirm Alpaca connectivity before a live run.

**First dry run: 2026-04-25**

- Stock signals: none in the 7-day window
- Options signals: Gottheimer's two MSFT call purchases filed 2026-04-08 (strikes $320 and $325, both >15% ITM). Deduped to one signal.
- Would buy: 117 shares MSFT at $424.62 (~$50k, 5% of $1M equity), exit 2026-05-08
- Paper account: $1,000,000 equity, Alpaca paper trading
