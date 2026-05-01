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
| `congress_rankings.csv` | 37 politicians | Generated from 90d backtest |

Combined: ~10,000 stock trades, 462 options, ~170 members across both chambers.

---

## ✅ Step 1 — Data loading refactor

Done. `congress/loader.py` normalises scraped CSVs to backtest schema.
`followcongress` and `paircongress` now use full House + Senate dataset.

---

## ✅ Step 2 — Follow-disclosure backtest

Done. See [FINDINGS.md](FINDINGS.md) for full results.

**Summary:** Clear alpha signal, grows with hold period (+0.6% excess at 10d → +2.3% at 90d).
Best politicians at 90d: Daniel Sullivan (+14.8%), Mark Green (+13.8%), Tim Moore (+12.9%), David McCormick (+8.9%), Cleo Fields (+6.3%).

---

## ✅ Step 3 — Sell-lag drift analysis

Done. See [FINDINGS.md](FINDINGS.md) for full results.

**Summary:** Hypothesis disproved. Price rises +1.7% on average during the sell lag window — waiting for the sell filing is *better* than exiting early. The sell filing is not a useful exit trigger on average. 44% of pairs do drop, so a conditional rule (exit early if lag >30d + already up >X%) may still have value but needs more work.

---

## ✅ Step 4 — Options analysis

Done. See [FINDINGS.md](FINDINGS.md) for full results.

**Summary:** Senate "put-heavy" explained — it's Tommy Tuberville running straddles, not directional bets. House calls show +3.8% excess at 30d fading to +0.8% at 90d. Deep ITM call purchases by Gottheimer and Pelosi are the actionable signal — 29/38 known-strike calls are >20% ITM, functioning as leveraged stock positions.

---

## ✅ Step 5 — Accumulation momentum signal

Incorporated directly into the live strategy as a filter rather than a standalone backtest. When multiple reliable politicians file the same ticker within the 7-day lookback window, signals are deduplicated into one `[ACCUMULATION]` entry. No separate backtest run — the follow-disclosure backtest already captures the return; accumulation is treated as a conviction booster.

---

## ✅ Step 6 — Full paper trading strategy

Done. Running on Alpaca paper account ($1,000,000 simulated equity).

**Two signal types:**

| Signal | Source | Filter | Hold |
|---|---|---|---|
| Stock purchase | Quiver live feed (7d lookback) | Reliable group (37 pols, positive excess + ≥5 trades) + exclude $1k-$15k | 90 days |
| Deep ITM call | Quiver `TickerType==OP` (30d lookback) | Gottheimer / Pelosi / Ross / Bresnahan + strike/price < 0.85 | 30 days |

**Sizing:** 5% of equity per position, max 15 simultaneous positions.  
**State:** `strategy_state.json` — open positions, closed positions, seen signal keys.  
**Run:** `python main.py live` (daily) or `python main.py live --dry-run` to simulate.

**First dry run result (2026-04-25):** No stock signals in the 7-day window. One MSFT options signal from Gottheimer's April 8 call purchases (two contracts, same ticker → deduped to one entry). Would buy 117 shares at $424.62, exit May 8.

---

## Validation TODOs

Steps needed to confirm the edge is real and not an in-sample artifact:

- **Walk-forward test** — rank politicians on 2022–2023 data only, then run the backtest on 2024–2026 without touching the training split. If the same names outperform out-of-sample, that's genuine signal.
- **Permutation test** — randomly shuffle politician→ticker assignments and rerun the backtest 1,000 times to build a null distribution. Check where the observed +2.3% excess sits. If it's in the top 5%, the result is unlikely to be noise.
- **Transaction cost sensitivity** — rerun the backtest at 0.25%, 0.5%, and 1.0% round-trip friction. Identify the break-even cost where the edge disappears.
- **Risk-adjusted returns** — compute beta of the follow-congress portfolio vs SPY and derive alpha. If excess returns vanish after beta adjustment, the strategy is just holding higher-volatility stocks, not exploiting an informational edge.

---

## Open Questions

- **Refresh cadence** — `congress_rankings.csv` should be regenerated periodically as new trades accumulate. Current list is from the 2022–2026 dataset.
- **Party data missing** — all scraped politicians marked `"?"`. Add lookup if party-level breakdown matters.
- **Sample concentration** — top performers (Sullivan, Moore, Fields) have many trades in a narrow range. Check if results are driven by a specific time period or sector.
- **Options-active politicians on stock trades** — do Gottheimer/Pelosi also outperform on their stock purchases? (Gottheimer: +1.68% at 90d across 362 trades — yes, modestly. Already in reliable group.)
- **>60d late filers** — the >60d sell-lag bucket shows +15.9% avg move during lag. Are these the same politicians who outperform on purchases?
- **Conditional sell-lag exit** — 44% of pairs drop during the sell lag. A rule like "exit early if lag >30d and already up >15%" has not been tested.
