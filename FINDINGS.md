# Research Findings

Results from running the congress trade analysis. Updated as new analysis is run.

---

## Dataset (as of 2026-04-30)

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

**Dataset:** 4,568 purchases, 73 politicians with ≥5 trades, 2022–2026.

### Holding Period Sensitivity — Reliable Group

Reliable = politicians with positive avg excess return AND ≥5 trades.

| Hold | Reliable pols | Total trades | Avg Excess | Win% | Avg Ret | SPY |
|------|--------------|-------------|-----------|------|---------|-----|
| 10d  | 45/73        | 2,754       | +0.6%     | 53%  | +1.0%   | +0.4% |
| 20d  | 41/73        | 2,989       | +0.8%     | 53%  | +1.6%   | +0.9% |
| 30d  | 39/72        | 2,698       | +1.1%     | 51%  | +2.4%   | +1.3% |
| 60d  | 35/72        | 2,372       | +1.8%     | 52%  | +5.1%   | +3.2% |
| 90d  | 37/73        | 2,217       | +2.3%     | 51%  | +6.8%   | +4.5% |

**Key observation:** alpha grows consistently with hold period. Strongest signal at 90 days (+2.3% excess). Win rate hovers around 50–53% regardless of hold — the edge is in the magnitude of wins, not win frequency.

### Full Reliable Group at 90d (congress_rankings.csv, generated 2026-04-30)

37 politicians with positive avg excess and ≥5 trades on the combined House + Senate dataset.

| Politician | Trades | Avg Excess | Win% |
|---|---|---|---|
| Daniel S Sullivan | 40 | +14.8% | 87.5% |
| Mark Dr Green | 9 | +13.8% | 100.0% |
| Kelly Louise Morrison | 5 | +13.4% | 80.0% |
| Tim Moore | 41 | +12.9% | 65.9% |
| Tina Smith | 5 | +9.8% | 80.0% |
| David H McCormick | 24 | +8.9% | 83.3% |
| James R. Langevin | 7 | +8.8% | 57.1% |
| Byron Donalds | 29 | +6.4% | 44.8% |
| Cleo Fields | 81 | +6.3% | 61.7% |
| Greg Landsman | 22 | +5.8% | 63.6% |
| Dwight Evans | 8 | +5.0% | 62.5% |
| Thomas Suozzi | 30 | +4.9% | 56.7% |
| Jerry Moran | 19 | +3.7% | 47.4% |
| Julie Johnson | 42 | +3.7% | 64.3% |
| Shelley M Capito | 34 | +3.0% | 58.8% |
| Thomas H. Kean | 18 | +2.7% | 44.4% |
| Katie Britt | 16 | +2.6% | 69.0% |
| Richard Dean Dr McCormick | 24 | +2.5% | 58.3% |
| Alan S. Lowenthal | 10 | +2.4% | 70.0% |
| Sheldon Whitehouse | 20 | +2.1% | 50.0% |
| Thomas H Tuberville | 285 | +2.1% | 42.8% |
| Rick Larsen | 18 | +1.9% | 55.6% |
| John Rutherford | 5 | +1.7% | 60.0% |
| Josh Gottheimer | 362 | +1.7% | 48.3% |
| Virginia Foxx | 108 | +1.5% | 50.9% |
| Scott Franklin | 8 | +1.1% | 62.5% |
| A. Mitchell McConnell, Jr. | 17 | +1.1% | 47.1% |
| Earl Blumenauer | 16 | +1.0% | 50.0% |
| Jared Moskowitz | 114 | +1.0% | 51.8% |
| Marjorie Taylor Mrs Greene | 61 | +0.9% | 49.2% |
| Greg Stanton | 53 | +0.7% | 50.9% |
| David J. Taylor | 18 | +0.7% | 44.4% |
| Markwayne Mullin | 272 | +0.6% | 50.4% |
| John Boozman | 155 | +0.4% | 39.4% |
| Robert J. Wittman | 19 | +0.4% | 57.9% |
| William R. Keating | 18 | +0.1% | 50.0% |
| Gilbert Cisneros | 204 | +0.0% | 42.6% |

Changes from 2026-04-25: **Katie Britt entered** (16 trades, +2.6%, 69% win) replacing **Angus King** who dropped to -0.9% with 2 additional trades. All core metrics unchanged.

Most statistically meaningful (high trade count + excess): **Cleo Fields (81 trades, +6.3%), Daniel Sullivan (40, +14.8%), Tim Moore (41, +12.9%), Julie Johnson (42, +3.7%), Josh Gottheimer (362, +1.7%)**.

### Interpretation

- ~2,200 trades in the reliable group is a reasonable sample
- The signal strengthens with time — consistent with informational edge that plays out over months
- Win rate ~50% means pure coin-flip on direction; the edge comes from asymmetric return distribution
- Best trade: IREN held by Cleo Fields (+256.7% excess). Worst: CNC held by Gilbert Cisneros (-69.4% excess)

### In-sample caveat

The 37 "reliable" politicians were selected using the same 2022–2026 dataset the backtest runs on — there is no out-of-sample validation. Under the null hypothesis (all politicians are noise), roughly half of 73 tested politicians would show positive excess by chance alone, which is close to the observed 37. The filter threshold (positive excess + ≥5 trades) is also weak enough that some entries may be noise survivors rather than genuine signal sources. The live strategy treats this list as a starting hypothesis, not a validated edge. Regenerate `congress_rankings.csv` periodically as new data accumulates to update the list with fresher signal.

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

The Quiver Quant live feed (`congress_trades.csv`) includes options rows via `TickerType == "OP"`. The `Description` field contains `"CALL OPTIONS; STRIKE PRICE $X; EXPIRES MM/DD/YYYY"`. No separate scraping needed for live detection — `fetch_options()` in `fetcher.py` parses these rows automatically.

Exercise events are absent from all data sources — they do not appear as stock purchases and create no false signals.

---

## Live Strategy (Step 6)

**First dry run: 2026-04-25**

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

**401 falls silently to stale cache (fetcher.py)**
If the Quiver API returns 401 (key expired, plan downgraded) and `congress_trades.csv` is under 48 hours old, the error is suppressed and stale data is served with only a `[WARN]` log line. The live strategy continues on outdated signals. Check the log output after each run for the `[fetch]` vs `[cache]` line.

**Phantom positions on broker failure (live.py)**
If Alpaca is unreachable in live (non-dry-run) mode, `_place_order` is `None`, the order block is skipped, but the position is still appended to `strategy_state.json` with `order_id = "dry-run"`. The state will show an open position that Alpaca doesn't hold. Guard: always run `python main.py account` first to confirm Alpaca connectivity before a live run.

**First dry run: 2026-04-25**

- Stock signals: none in the 7-day window
- Options signals: Gottheimer's two MSFT call purchases filed 2026-04-08 (strikes $320 and $325, both >15% ITM). Deduped to one signal.
- Would buy: 117 shares MSFT at $424.62 (~$50k, 5% of $1M equity), exit 2026-05-08
- Paper account: $1,000,000 equity, Alpaca paper trading
