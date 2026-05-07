# Congress Trades Research Plan

## Goal

Find exploitable patterns in congressional stock trade disclosures. Three hypotheses:

1. **Follow-disclosure** — buy when a politician files a purchase, hold N days. Alpha vs SPY?
2. **Sell-lag exit** — politicians sell weeks before filing. Does price drop during that lag? Use filing date as exit trigger.
3. **Accumulation momentum** — stocks with multiple politicians buying in a short window as a momentum signal.

---

## Data Status

| File | Rows | Status |
|---|---|---|
| `congress_historical.csv` | ~7,000 stock trades | Complete (House, 2022–2025) |
| `congress_options.csv` | 156 trades, 9 reps | Complete (House, deduplicated) |
| `senate_historical.csv` | ~4,000 stock trades | Complete (Senate, 2022–2026) |
| `senate_options.csv` | 306 trades | Complete (Senate) |
| `congress_trades.csv` | ~1,000 trades | Quiver API cache (separate, live) |
| `congress_rankings.csv` | 12 politicians | Generated from 90d backtest (excess >2%, ≥20 trades) — all-trades |
| `congress_rankings_hc.csv` | 4 politicians | HC backtest (>$15k trades, excess >2%, ≥20 HC trades) — live strategy |

Combined: ~10,000 stock trades, 462 options, ~170 members across both chambers.

---

## ✅ Step 1 — Data loading refactor

Done. `congress/loader.py` normalises scraped CSVs to backtest schema.
`followcongress` and `paircongress` now use full House + Senate dataset.

---

## ✅ Step 2 — Follow-disclosure backtest

Done. See [FINDINGS.md](FINDINGS.md) for full results.

**Summary:** Clear alpha signal. Strict filter (>2% excess, ≥20 trades) gives 12 reliable politicians at 4.8% excess at 90d. Short-hold win rates are unusually high (68–70% at 10–20d). Best politicians at 90d: Daniel Sullivan (+14.8%), Tim Moore (+12.9%), David McCormick (+8.9%), Cleo Fields (+6.3%).

Note: an earlier loose filter (>0%, ≥5 trades) produced +2.4% at 90d — the lower number was diluted by noise traders with 5-trade sample sizes, not a different strategy.

---

## ✅ Step 3 — Sell-lag drift analysis

Done. See [FINDINGS.md](FINDINGS.md) for full results.

**Summary:** Hypothesis disproved. Price rises +1.7% on average during the sell lag window — waiting for the sell filing is *better* than exiting early. The sell filing is not a useful exit trigger on average. 44% of pairs do drop, so a conditional rule (exit early if lag >30d + already up >X%) may still have value but needs more work.

---

## ✅ Step 4 — Options analysis

Done. See [FINDINGS.md](FINDINGS.md) for full results.

**Summary:** Senate "put-heavy" explained — it's Tommy Tuberville running straddles, not directional bets. House calls show +3.8% excess at 30d fading to +0.8% at 90d. Deep ITM call purchases by Gottheimer and Pelosi are the actionable signal — 29/38 known-strike calls are >20% ITM, functioning as leveraged stock positions.

---

## ✅ Step 5 — High-conviction strategy

Done. See [FINDINGS.md](FINDINGS.md) for full results.

**Summary:** Filtering to trades >$15k (excludes the low-conviction $1k–$15k bracket) reveals 4 HC politicians (Tim Moore, McCormick, Cleo Fields, Virginia Foxx) with +7.9% excess at 90d — nearly double the 12-pol all-trades figure. This is the live strategy. Rankings saved to `congress_rankings_hc.csv`.

Accumulation momentum is incorporated as a signal modifier: multiple politicians filing the same ticker within the lookback window are deduplicated into one `[ACCUMULATION]` entry.

---

## ✅ Step 6 — Full paper trading strategy

Done. Running on Alpaca paper account ($1,000,000 simulated equity).

**Two signal types:**

| Signal | Source | Filter | Hold |
|---|---|---|---|
| Stock purchase | Quiver live feed (7d lookback) | HC group (4 pols, >$15k trades, avg excess >2% + ≥20 HC trades) | 90 days |
| Deep ITM call | Quiver `TickerType==OP` (30d lookback) | Gottheimer / Pelosi / Ross / Bresnahan + strike/price < 0.85 | 30 days |

**Sizing:** 5% of equity per position, max 15 simultaneous positions.  
**State:** `strategy_state.json` — open positions, closed positions, seen signal keys.  
**Run:** `python main.py live` (daily) or `python main.py live --dry-run` to simulate.

**Rankings refresh:** `python main.py highconv` regenerates `congress_rankings_hc.csv` (HC strategy) and `congress_rankings.csv` (all-trades, for site findings). Run periodically as new data accumulates.

**First dry run result (2026-04-25):** No stock signals in the 7-day window. One MSFT options signal from Gottheimer's April 8 call purchases (two contracts, same ticker → deduped to one entry). Would buy 117 shares at $424.62, exit May 8.

---

## Validation TODOs

Steps needed to confirm the edge is real and not an in-sample artifact:

- ~~**Walk-forward test**~~ — **Done.** All-trades: 14% alpha retention (Sullivan/Suozzi left Congress; Mullin +0.8% OOS). HC: 66% retention (Foxx/Mullin). Live strategy's best politicians (Moore, McCormick, Fields) all joined post-2024 and cannot be tested — re-run after mid-2026.
- **Permutation test** — randomly shuffle politician→ticker assignments and rerun the backtest 1,000 times to build a null distribution. Check where the observed +7.9% excess (HC) sits. If it's in the top 5%, the result is unlikely to be noise.
- **Transaction cost sensitivity** — rerun the backtest at 0.25%, 0.5%, and 1.0% round-trip friction. Identify the break-even cost where the edge disappears.
- **Risk-adjusted returns** — compute beta of the follow-congress portfolio vs SPY and derive alpha. If excess returns vanish after beta adjustment, the strategy is just holding higher-volatility stocks, not exploiting an informational edge.

---

## Strategy Architecture TODOs

Known design gaps in the live strategy worth addressing:

- **Per-politician position tracking** — currently positions are keyed by ticker, so a second reliable politician buying the same stock is silently skipped. A better model keys positions on `(ticker, politician)`, allowing multiple tranches in the same stock. Each tranche would be sized independently at 5% and exit on its own timeline. Requires Alpaca position math to be managed manually in state.
- **Sell signal monitoring** — the live strategy has no awareness of sell filings. Currently exits are purely time-based (90 days from filing). With per-politician tracking, the natural exit rule becomes: close a tranche when the *same politician who triggered entry* files a sell on that ticker, OR after 90 days — whichever comes first. The sell-lag research showed sells average +1.7% drift during the lag, so exiting 30 days *after* the sell filing may outperform exiting on the filing date itself.

---

## Open Questions

- **Refresh cadence** — `congress_rankings.csv` should be regenerated periodically as new trades accumulate. Current list is from the 2022–2026 dataset.
- **Party data missing** — all scraped politicians marked `"?"`. Add lookup if party-level breakdown matters.
- **Sample concentration** — top performers (Sullivan, Moore, Fields) have many trades in a narrow range. Check if results are driven by a specific time period or sector.
- **Options-active politicians on stock trades** — do Gottheimer/Pelosi also outperform on their stock purchases? (Gottheimer: +1.68% at 90d across 362 trades — yes, modestly. Already in reliable group.)
- **>60d late filers** — the >60d sell-lag bucket shows +15.9% avg move during lag. Are these the same politicians who outperform on purchases?
- **Conditional sell-lag exit** — 44% of pairs drop during the sell lag. A rule like "exit early if lag >30d and already up >15%" has not been tested.
