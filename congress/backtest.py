"""
Congress follow-strategy backtest.

For every purchase disclosure from a politician:
  - Entry: closing price on ReportDate (when we first know about it)
  - Exit:  closing price on ReportDate + hold_days
  - Excess return: trade return minus SPY return over same window

Aggregates results per politician and per group so you can decide
who (or which combination) is worth following.
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from datetime import timedelta

from data.fetcher import fetch_daily_closes


@dataclass
class CongressTrade:
    politician: str
    party: str
    ticker: str
    report_date: pd.Timestamp
    transaction_date: pd.Timestamp
    disclosure_lag: int
    entry_price: float
    exit_price: float
    hold_days: int
    trade_return_pct: float
    spy_return_pct: float
    excess_return_pct: float


@dataclass
class PoliticianResult:
    name: str
    party: str
    trades: list[CongressTrade] = field(default_factory=list)

    @property
    def n(self) -> int:
        return len(self.trades)

    @property
    def avg_excess(self) -> float:
        if not self.trades:
            return 0.0
        return np.mean([t.excess_return_pct for t in self.trades])

    @property
    def win_rate(self) -> float:
        if not self.trades:
            return 0.0
        return sum(1 for t in self.trades if t.excess_return_pct > 0) / self.n

    @property
    def avg_trade_return(self) -> float:
        return np.mean([t.trade_return_pct for t in self.trades]) if self.trades else 0.0

    @property
    def avg_spy_return(self) -> float:
        return np.mean([t.spy_return_pct for t in self.trades]) if self.trades else 0.0

    @property
    def total_excess(self) -> float:
        return sum(t.excess_return_pct for t in self.trades)



def _next_trading_day_price(closes: pd.DataFrame, ticker: str, date: pd.Timestamp) -> float | None:
    """Return closing price on or after date for ticker."""
    if ticker not in closes.columns:
        return None
    future = closes[ticker][closes.index >= date].dropna()
    if future.empty:
        return None
    return float(future.iloc[0])


def _exit_price(closes: pd.DataFrame, ticker: str, entry_date: pd.Timestamp, hold_days: int) -> tuple[float | None, pd.Timestamp | None]:
    """Return (price, actual_exit_date) hold_days after entry."""
    if ticker not in closes.columns:
        return None, None
    target = entry_date + timedelta(days=hold_days)
    future = closes[ticker][closes.index >= target].dropna()
    if future.empty:
        return None, None
    return float(future.iloc[0]), future.index[0]


def prefetch_prices(df: pd.DataFrame, max_hold_days: int = 90) -> pd.DataFrame:
    """
    Fetch prices once for the full date range needed across all hold periods.
    Pass the result into run_politician_backtest() as `closes` to avoid
    re-downloading on every call.
    """
    clean = df.dropna(subset=["Ticker", "ReportDate"]).copy()
    clean = clean[clean["Ticker"].str.len() <= 5]
    start = clean["ReportDate"].min()
    end   = clean["ReportDate"].max() + timedelta(days=max_hold_days + 10)
    print(f"  Fetching price history for {clean['Ticker'].nunique()} tickers + SPY...")
    return fetch_daily_closes(clean["Ticker"].unique().tolist(), start, end)


def run_politician_backtest(
    df: pd.DataFrame,
    hold_days: int = 30,
    min_trades: int = 2,
    purchases_only: bool = True,
    closes: pd.DataFrame | None = None,
) -> dict[str, PoliticianResult]:
    """
    Backtest following each politician's disclosures.

    df: congress trades DataFrame (from loader.load_for_backtest())
    hold_days: how many calendar days to hold each position
    min_trades: minimum trades required to include a politician in results
    closes: pre-fetched price DataFrame from prefetch_prices() — pass this
            when running multiple hold periods to avoid re-downloading prices.
    """
    if purchases_only:
        df = df[df["Transaction"] == "Purchase"].copy()

    df = df.dropna(subset=["Ticker", "ReportDate"]).copy()
    df = df[df["Ticker"].str.len() <= 5]  # filter out options/bonds

    if closes is None:
        start = df["ReportDate"].min()
        end   = df["ReportDate"].max() + timedelta(days=hold_days + 10)
        print(f"  Fetching price history for {df['Ticker'].nunique()} tickers + SPY...")
        closes = fetch_daily_closes(df["Ticker"].unique().tolist(), start, end)

    results: dict[str, PoliticianResult] = {}

    for _, row in df.iterrows():
        politician = row["Representative"]
        ticker     = row["Ticker"]
        report_dt  = row["ReportDate"]
        tx_dt      = row["TransactionDate"]
        party      = row["Party"]

        # NOTE: entry is the close ON ReportDate (or the next trading day). If the disclosure
        # hits after market close — common for STOCK Act filings — the realistic entry would
        # be next-day open, not same-day close. This overstates entry price precision slightly.
        entry = _next_trading_day_price(closes, ticker, report_dt)
        spy_entry = _next_trading_day_price(closes, "SPY", report_dt)
        if entry is None or spy_entry is None:
            continue

        exit_p, exit_dt = _exit_price(closes, ticker, report_dt, hold_days)
        spy_exit_p, _   = _exit_price(closes, "SPY",    report_dt, hold_days)
        if exit_p is None or spy_exit_p is None:
            continue

        trade_ret = (exit_p    - entry)     / entry     * 100
        spy_ret   = (spy_exit_p - spy_entry) / spy_entry * 100
        excess    = trade_ret - spy_ret

        trade = CongressTrade(
            politician=politician,
            party=party,
            ticker=ticker,
            report_date=report_dt,
            transaction_date=tx_dt,
            disclosure_lag=int(row["disclosure_lag_days"]) if pd.notna(row["disclosure_lag_days"]) else 0,
            entry_price=round(entry, 2),
            exit_price=round(exit_p, 2),
            hold_days=hold_days,
            trade_return_pct=round(trade_ret, 2),
            spy_return_pct=round(spy_ret, 2),
            excess_return_pct=round(excess, 2),
        )

        if politician not in results:
            results[politician] = PoliticianResult(name=politician, party=party)
        results[politician].trades.append(trade)

    # Filter to min_trades
    return {k: v for k, v in results.items() if v.n >= min_trades}


def rank_politicians(results: dict[str, PoliticianResult]) -> pd.DataFrame:
    if not results:
        return pd.DataFrame(columns=["politician","party","trades","avg_excess","win_rate","avg_trade_ret","avg_spy_ret","total_excess"])
    rows = []
    for name, r in results.items():
        rows.append({
            "politician":       name,
            "party":            r.party,
            "trades":           r.n,
            "avg_excess":       round(r.avg_excess, 2),
            "win_rate":         round(r.win_rate * 100, 1),
            "avg_trade_ret":    round(r.avg_trade_return, 2),
            "avg_spy_ret":      round(r.avg_spy_return, 2),
            "total_excess":     round(r.total_excess, 2),
        })
    return pd.DataFrame(rows).sort_values("avg_excess", ascending=False).reset_index(drop=True)


def simulate_group(
    results: dict[str, PoliticianResult],
    politicians: list[str],
) -> dict:
    """
    Simulate following a group of politicians — treat all their trades as one portfolio.
    Returns aggregate stats.
    """
    all_trades = []
    for name in politicians:
        if name in results:
            all_trades.extend(results[name].trades)

    if not all_trades:
        return {}

    excess  = [t.excess_return_pct for t in all_trades]
    returns = [t.trade_return_pct   for t in all_trades]
    spy     = [t.spy_return_pct     for t in all_trades]

    return {
        "politicians":    politicians,
        "total_trades":   len(all_trades),
        "avg_excess":     round(np.mean(excess), 2),
        "win_rate":       round(sum(1 for e in excess if e > 0) / len(excess) * 100, 1),
        "avg_trade_ret":  round(np.mean(returns), 2),
        "avg_spy_ret":    round(np.mean(spy), 2),
        "total_excess":   round(sum(excess), 2),
        "best_trade":     max(all_trades, key=lambda t: t.excess_return_pct),
        "worst_trade":    min(all_trades, key=lambda t: t.excess_return_pct),
    }


def print_rankings(rankings: pd.DataFrame, hold_days: int) -> None:
    print(f"\n  {'Politician':<30} {'P':<2} {'Trades':>6}  {'Avg Excess':>10}  {'Win%':>5}  {'Avg Ret':>8}  {'vs SPY':>7}")
    print("  " + "-" * 78)
    for _, row in rankings.iterrows():
        marker = " *" if row["avg_excess"] > 0 and row["trades"] >= 5 else "  "
        print(
            f"{marker}{row['politician']:<30} {row['party']:<2} "
            f"{int(row['trades']):>6}  "
            f"{row['avg_excess']:>+9.1f}%  "
            f"{row['win_rate']:>4.0f}%  "
            f"{row['avg_trade_ret']:>+7.1f}%  "
            f"{row['avg_spy_ret']:>+6.1f}%"
        )
    print(f"\n  * = positive excess + 5+ trades (reliable signal) | hold_days={hold_days}")


def print_group_result(g: dict) -> None:
    if not g:
        print("  No trades found for this group.")
        return
    print(f"  Trades:         {g['total_trades']}")
    print(f"  Avg Excess Ret: {g['avg_excess']:>+.1f}%")
    print(f"  Win Rate:       {g['win_rate']:.0f}%")
    print(f"  Avg Trade Ret:  {g['avg_trade_ret']:>+.1f}%  (SPY: {g['avg_spy_ret']:>+.1f}%)")
    best = g["best_trade"]
    worst = g["worst_trade"]
    print(f"  Best trade:     {best.ticker} ({best.politician}) {best.excess_return_pct:>+.1f}% excess")
    print(f"  Worst trade:    {worst.ticker} ({worst.politician}) {worst.excess_return_pct:>+.1f}% excess")
