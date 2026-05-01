# TrackMyCongress

Backtesting congressional stock trade disclosures (STOCK Act filings) for alpha signals. Includes a live paper trading strategy running on Alpaca.

---

## What This Is

Members of Congress must publicly disclose stock trades within 45 days of the transaction. This project scrapes those filings from the House clerk and Senate EFDS, runs backtests against SPY to find statistically meaningful edges, and executes a live paper trading strategy on an Alpaca paper account.

**Dataset:** ~10,000 stock trades + 462 options across ~170 members (House 2022–2025, Senate 2022–2026).

---

## Key Findings

### 1. Follow-Disclosure Alpha Exists and Grows With Time

Buy at close on the day a trade is publicly filed. Hold N days. Compare to SPY over the same window.

| Hold | Reliable politicians | Trades | Avg Excess | Win% |
|------|---------------------|--------|------------|------|
| 10d  | 45/73               | 2,753  | +0.6%      | 53%  |
| 30d  | 39/72               | 2,697  | +1.1%      | 51%  |
| 60d  | 35/72               | 2,371  | +1.8%      | 52%  |
| 90d  | 37/71               | 2,225  | **+2.3%**  | 50%  |

"Reliable" = politicians with positive average excess return and ≥5 trades in the dataset.

The edge isn't in win rate (hovers ~50–53% regardless of hold period) — it's in the asymmetric return distribution. Alpha grows consistently with time, consistent with an informational edge that plays out over months.

### 2. Top Performers at 90-Day Hold

| Politician | Trades | Avg Excess | Win% |
|---|---|---|---|
| Daniel Sullivan (R-AK, Senate) | 40 | **+14.8%** | 87.5% |
| Mark Green (R-TN, House) | 9 | **+13.8%** | 100.0% |
| Tim Moore (R-NC, House) | 41 | **+12.9%** | 65.9% |
| David McCormick (R-PA, Senate) | 24 | **+8.9%** | 83.3% |
| Cleo Fields (D-LA, House) | 81 | **+6.3%** | 61.7% |
| Josh Gottheimer (D-NJ, House) | 362 | +1.7% | 48.3% |
| Thomas Tuberville (R-AL, Senate) | 285 | +2.1% | 42.8% |

Statistically strongest (high trade count + excess): Cleo Fields (81 trades, +6.3%), Daniel Sullivan (40, +14.8%), Tim Moore (41, +12.9%).

### 3. The Sell-Lag Signal Is a Myth

Hypothesis: politicians sell weeks before filing. Does price drop during that lag? Should you exit early when you see a sell filing?

**Result: no.** Analyzing 1,425 matched buy/sell pairs across 164 politicians and 598 tickers:

- Median hold before selling: **128 days**
- Median sell disclosure lag: **27 days**
- Price drift during the undisclosed sell lag: **+1.7%** on average

Waiting for the sell filing captures an extra +1.7% vs exiting at the actual sell date. Holding 30 days past the sell filing adds another +1.7%. The sell filing is not a reliable exit trigger.

One notable exception: pairs with >60-day disclosure lag show +15.9% avg move during the lag. Possible late-filer effect, not yet acted on.

### 4. Options: Pelosi and Gottheimer Buy Synthetic Longs

462 total options trades. Senate is "put-heavy" entirely due to one senator (Tommy Tuberville) running volatility straddles — not directional bearish bets.

**House call backtest** (buying underlying stock on filing date):

| Hold | Avg Excess | Win% |
|------|------------|------|
| 30d  | **+3.8%**  | ~55% |
| 60d  | +2.9%      | ~53% |
| 90d  | +0.8%      | ~51% |

Signal peaks at 30 days and fades — opposite of the stock signal.

**Deep ITM calls:** 29 of 38 House call purchases with known strikes are >20% ITM. Gottheimer and Pelosi are consistently buying calls 40–60% in-the-money — leveraged stock positions, not speculative bets. Examples:

- Gottheimer MSFT: 40–60% ITM across all purchases (2022–2026)
- Pelosi NVDA $80 strike (filed Jan 2025): 41.9% ITM vs $137.70 spot
- Pelosi AMZN $150 strike (filed Jan 2025): 33.6% ITM vs $225.90 spot

**Live strategy signal:** call purchase from a known politician with `strike/spot < 0.85` → buy the underlying stock, 30-day hold.

---

## Live Paper Trading Strategy

Two signal types, one execution path. State persisted in `strategy_state.json`. Running on Alpaca paper account ($1,000,000 simulated equity).

| Signal | Source | Filter | Hold |
|--------|--------|--------|------|
| Stock purchase | Quiver live feed (7-day lookback) | Reliable group (37 pols, positive excess + ≥5 trades) + exclude $1k–$15k filings | 90 days |
| Deep ITM call | Quiver `TickerType==OP` (30-day lookback) | Gottheimer / Pelosi / Ross / Bresnahan + `strike/price < 0.85` | 30 days |

**Sizing:** 5% of equity per position, max 15 simultaneous positions.

Multiple politicians buying the same ticker within the lookback window are deduplicated into one `[ACCUMULATION]` signal.

---

## Setup

```bash
git clone https://github.com/samsnowy/TrackMyCongress
cd TrackMyCongress
pip install -r requirements.txt
cp .env.example .env
# Add your Alpaca paper trading keys to .env (see .env.example)
```

Requires **Python 3.10+**.

**Data sources:**
- [Quiver Quant API](https://www.quiverquant.com/) — congressional trade live feed; the live strategy uses their free public endpoint (no API key required). If the endpoint is rate-limited or restricted, a local cache (`congress_trades.csv`) is used as fallback.
- [Alpaca](https://alpaca.markets/) — paper trading account (free, requires API keys in `.env`)

The scrapers (`congress/scraper.py`, `congress/senate_scraper.py`) pull directly from public government sources and don't require API keys.

---

## Usage

```bash
# Research
python main.py congress                 # latest trades from Quiver Quant live feed
python main.py followcongress           # follow-disclosure backtest (configurable hold periods)
python main.py paircongress             # buy/sell pair analysis — sell-lag drift
python main.py congressoptions          # options analysis

# Live strategy
python main.py live --dry-run           # simulate strategy without placing orders
python main.py live                     # run strategy and place paper orders
python main.py account                  # Alpaca paper account status + open positions

# Scraping (one-time, resumable)
python -m congress.scrape_all           # House + Senate PTRs
python -m congress.scraper              # House only
python -m congress.senate_scraper       # Senate only
```

**Refresh the reliable politician list periodically** as new data accumulates:
```bash
python main.py followcongress           # hold=90, min_trades=5 → save rankings
```

---

## Architecture

```
congress/
  scraper.py          — House PTR scraper (disclosures-clerk.house.gov, PDF-based)
  senate_scraper.py   — Senate PTR scraper (efdsearch.senate.gov, HTML + CSRF session)
  scrape_all.py       — runs both scrapers in sequence (resumable)
  loader.py           — unified data loader; normalises scraped CSVs for backtest
  fetcher.py          — Quiver Quant API client (live feed, cached); parses options rows
  backtest.py         — follow-disclosure backtest engine (yfinance daily prices)
  trade_pairs.py      — buy/sell pair matching + sell-lag drift analysis
  options_analysis.py — options overview, straddle analysis, House call backtest
  strategy.py         — pure strategy logic (signal detection, dedup, exit rules)
  live.py             — live strategy orchestrator (Alpaca execution, state management)
broker/
  alpaca_paper.py     — Alpaca paper trading (orders, positions, account)
data/
  fetcher.py          — yfinance OHLCV helpers
config.py             — loads .env
main.py               — CLI entry point
```

---

## Data

Scraped from public government sources:

| Source | URL | Format | Coverage |
|--------|-----|--------|----------|
| House PTRs | disclosures-clerk.house.gov | PDF | 2022–present |
| Senate eFDS | efdsearch.senate.gov | HTML/JSON | 2022–present |

Quiver Quant API provides a pre-parsed live feed (~10 months rolling) used for the live strategy.

**What's missing from all data sources:** option exercise events. Exercises do not appear as stock purchases anywhere. Confirmed by auditing all transaction types — no false signal risk.

---

## Limitations

- **Disclosure lag:** The backtest entry is the close on the day a trade is publicly filed — 30–45 days after the actual transaction. Real-time edge (if any) is unknowable from this data.
- **Backtesting assumptions:** Results assume buying at the closing price on filing day with no slippage or liquidity constraints. In practice, some tickers are illiquid and execution costs will reduce returns.
- **Sample size:** Top individual performers (Sullivan, Moore) have 9–41 trades each. High excess returns may reflect a specific time period or sector concentration rather than a persistent edge. The dataset covers 2022–2026 — a strong bull market for US equities.
- **Data accuracy:** Congressional disclosures are self-reported with known errors and omissions. Quiver Quant (used for the live feed) notes their data "may be inaccurate or incomplete." Options strike/expiry data is parsed from free-text `Description` fields and can misparse.
- **Past performance:** The backtest covers one market regime. Excess returns vs SPY may not persist in different rate or volatility environments.
- **Not financial advice.** This is a research and education project. Congressional disclosure patterns are one input signal, not a trading strategy guarantee. Do your own analysis before making any investment decisions.
