"""
Options trade analysis for House and Senate congress members.

Key questions:
  - Who trades options and what pattern (directional vs straddle)?
  - Are options purchases predictive of underlying stock moves?
  - Tuberville straddle analysis: does the stock move enough to profit?
  - House call purchases: do they beat SPY?
"""

import pandas as pd
import numpy as np
from datetime import timedelta

from data.fetcher import fetch_daily_closes

_HOUSE_FILE  = "congress_options.csv"
_SENATE_FILE = "senate_options.csv"
_HOLD_DAYS   = [30, 60, 90]


def load_options(chamber: str = "both") -> pd.DataFrame:
    import os
    frames = []
    if chamber in ("house", "both") and os.path.exists(_HOUSE_FILE):
        df = pd.read_csv(_HOUSE_FILE)
        df["chamber"] = "House"
        frames.append(df)
    if chamber in ("senate", "both") and os.path.exists(_SENATE_FILE):
        df = pd.read_csv(_SENATE_FILE)
        df["chamber"] = "Senate"
        frames.append(df)
    if not frames:
        return pd.DataFrame(columns=[
            "name", "chamber", "filing_date", "transaction_date", "expiration",
            "ticker", "transaction", "option_type", "strike", "amount_range",
        ])
    combined = pd.concat(frames, ignore_index=True)
    combined["filing_date"]      = pd.to_datetime(combined["filing_date"], errors="coerce")
    combined["transaction_date"] = pd.to_datetime(combined["transaction_date"], format="%m/%d/%Y", errors="coerce")
    combined["expiration"]       = pd.to_datetime(combined["expiration"], format="mixed", errors="coerce")
    return combined



def _price_on_or_after(closes: pd.DataFrame, ticker: str, date: pd.Timestamp) -> float | None:
    if ticker not in closes.columns:
        return None
    s = closes[ticker][closes.index >= date].dropna()
    return float(s.iloc[0]) if not s.empty else None


def print_overview(df: pd.DataFrame) -> None:
    print(f"\n{'='*60}")
    print(f"  Congress Options Overview  ({len(df)} total trades)")
    print(f"{'='*60}")

    for chamber in ["House", "Senate"]:
        sub = df[df["chamber"] == chamber]
        if sub.empty:
            continue
        purchases = sub[sub["transaction"] == "Purchase"]
        print(f"\n  {chamber}: {len(sub)} trades | {sub['name'].nunique()} politicians | {sub['ticker'].nunique()} tickers")
        print(f"    Purchases: {len(purchases)}  |  Sales: {len(sub)-len(purchases)}")
        print(f"    Calls: {(sub['option_type']=='Call').sum()}  |  Puts: {(sub['option_type']=='Put').sum()}  |  Unknown: {sub['option_type'].isna().sum()}")
        print(f"    Strike known: {sub['strike'].notna().sum()}/{len(sub)}")
        print(f"    Top traders:")
        for name, count in sub["name"].value_counts().head(5).items():
            calls = ((sub["name"]==name) & (sub["option_type"]=="Call")).sum()
            puts  = ((sub["name"]==name) & (sub["option_type"]=="Put")).sum()
            print(f"      {name:<32} {count:>3} trades  ({calls}C / {puts}P)")


def analyse_tuberville(df: pd.DataFrame) -> None:
    """
    Tuberville trades straddles — buying calls AND puts on the same ticker/expiry.
    Key question: does the underlying move enough to profit from the straddle?
    We proxy with |underlying move| vs typical straddle cost (~10-15% of stock price).
    """
    tub = df[(df["name"].str.contains("Tuberville", na=False, regex=False)) & (df["transaction"] == "Purchase")].copy()
    if tub.empty:
        return

    print(f"\n{'='*60}")
    print(f"  Tuberville Straddle Analysis  ({len(tub)} purchases)")
    print(f"{'='*60}")

    # Identify straddle pairs: same ticker + same expiry + both call and put
    tub["exp_month"] = tub["expiration"].dt.to_period("M")
    pairs = tub.groupby(["ticker", "exp_month"]).agg(
        types=("option_type", lambda x: set(x.dropna())),
        count=("option_type", "count"),
        filing_date=("filing_date", "min"),
    ).reset_index()
    straddles = pairs[pairs["types"].apply(lambda x: "Call" in x and "Put" in x)]
    print(f"\n  Straddle pairs identified: {len(straddles)} (same ticker + expiry month, both C+P)")
    print(f"  Single-direction trades: {len(pairs) - len(straddles)}")

    # Fetch prices and measure actual move at expiry
    tickers = straddles["ticker"].unique().tolist()
    if not tickers:
        return
    start = tub["filing_date"].min()
    end   = tub["expiration"].max()
    if pd.isna(end):
        end = start + timedelta(days=365)

    print(f"\n  Fetching prices for {len(tickers)} tickers...")
    closes = fetch_daily_closes(tickers, start, end)

    results = []
    for _, row in straddles.iterrows():
        ticker = row["ticker"]
        entry_date  = row["filing_date"]
        expiry_date = tub[(tub["ticker"]==ticker) & (tub["exp_month"]==row["exp_month"])]["expiration"].min()

        entry = _price_on_or_after(closes, ticker, entry_date)
        if pd.isna(expiry_date) or entry is None:
            continue
        exit_p = _price_on_or_after(closes, ticker, expiry_date)
        if exit_p is None:
            continue

        move_pct = abs(exit_p - entry) / entry * 100
        direction = "up" if exit_p > entry else "down"
        results.append({
            "ticker": ticker,
            "expiry": str(row["exp_month"]),
            "entry": round(entry, 2),
            "exit": round(exit_p, 2),
            "abs_move_pct": round(move_pct, 1),
            "direction": direction,
        })

    if results:
        rdf = pd.DataFrame(results).sort_values("abs_move_pct", ascending=False)
        avg_move = rdf["abs_move_pct"].mean()
        print(f"\n  Avg absolute move to expiry: {avg_move:.1f}%")
        print(f"  % moved >10%: {(rdf['abs_move_pct']>10).mean()*100:.0f}%")
        print(f"  % moved >20%: {(rdf['abs_move_pct']>20).mean()*100:.0f}%")
        print(f"\n  {'Ticker':<8} {'Expiry':<10} {'Entry':>8} {'Exit':>8} {'|Move|':>8} {'Dir'}")
        print("  " + "-"*50)
        for _, r in rdf.head(15).iterrows():
            print(f"  {r['ticker']:<8} {r['expiry']:<10} ${r['entry']:>7.2f} ${r['exit']:>7.2f} {r['abs_move_pct']:>7.1f}%  {r['direction']}")


def analyse_house_calls(df: pd.DataFrame) -> None:
    """
    For House call purchases: is the underlying stock return positive at 30/60/90d?
    Compare to SPY over same window.
    """
    calls = df[
        (df["chamber"] == "House") &
        (df["transaction"] == "Purchase") &
        (df["option_type"] == "Call")
    ].copy().dropna(subset=["filing_date", "ticker"])

    if calls.empty:
        return

    print(f"\n{'='*60}")
    print(f"  House Call Purchase Analysis  ({len(calls)} calls)")
    print(f"{'='*60}")

    tickers = calls["ticker"].unique().tolist()
    start   = calls["filing_date"].min()
    end     = calls["filing_date"].max() + timedelta(days=100)

    print(f"\n  Fetching prices for {len(tickers)} tickers...")
    closes = fetch_daily_closes(tickers, start, end)

    for hold in _HOLD_DAYS:
        returns = []
        spy_returns = []
        for _, row in calls.iterrows():
            entry = _price_on_or_after(closes, row["ticker"], row["filing_date"])
            spy_e = _price_on_or_after(closes, "SPY",         row["filing_date"])
            if entry is None or spy_e is None:
                continue
            target = row["filing_date"] + timedelta(days=hold)
            exit_p = _price_on_or_after(closes, row["ticker"], target)
            spy_x  = _price_on_or_after(closes, "SPY",         target)
            if exit_p is None or spy_x is None:
                continue
            returns.append((exit_p - entry) / entry * 100)
            spy_returns.append((spy_x - spy_e) / spy_e * 100)

        if returns:
            avg_ret    = np.mean(returns)
            avg_spy    = np.mean(spy_returns)
            avg_excess = avg_ret - avg_spy
            win_pct    = sum(1 for r in returns if r > 0) / len(returns) * 100
            print(f"\n  Hold {hold:>2}d | n={len(returns):>3} | "
                  f"avg={avg_ret:>+5.1f}%  spy={avg_spy:>+5.1f}%  "
                  f"excess={avg_excess:>+5.1f}%  win={win_pct:.0f}%")

    # Top tickers by frequency
    print(f"\n  Most traded tickers (call purchases):")
    for ticker, cnt in calls["ticker"].value_counts().head(10).items():
        traders = calls[calls["ticker"]==ticker]["name"].unique()
        print(f"    {ticker:<8} {cnt:>3}x  {', '.join(traders)}")


def backtest_options_signals(
    df: pd.DataFrame,
    hold_days_list: list[int] | None = None,
    calls_only: bool = True,
    deep_itm_only: bool = False,
    itm_threshold: float = 0.85,
    min_trades: int = 2,
) -> dict[int, pd.DataFrame]:
    """
    For each call purchase filing, buy the underlying stock on filing_date
    and hold N days. Rank politicians by excess return vs SPY.

    Returns a dict keyed by hold_days, each value is a rankings DataFrame with
    columns: politician, chamber, trades, avg_excess, win_rate, avg_ret, avg_spy.

    deep_itm_only: only include rows where strike / stock_price_at_filing < itm_threshold.
                   Rows with unknown strike are excluded when this filter is active.
    """
    if hold_days_list is None:
        hold_days_list = [30, 60, 90]

    signals = df[df["transaction"] == "Purchase"].copy()
    if calls_only:
        signals = signals[signals["option_type"] == "Call"]
    signals = signals.dropna(subset=["filing_date", "ticker"])

    if signals.empty:
        return {}

    tickers = signals["ticker"].unique().tolist()
    start   = signals["filing_date"].min()
    end     = signals["filing_date"].max() + timedelta(days=max(hold_days_list) + 10)

    print(f"  Fetching prices for {len(tickers)} tickers...")
    closes = fetch_daily_closes(tickers, start, end)

    results_by_hold: dict[int, list[dict]] = {h: [] for h in hold_days_list}

    for _, row in signals.iterrows():
        ticker      = row["ticker"]
        filing_date = row["filing_date"]
        politician  = row["name"]
        chamber     = row.get("chamber", "Unknown")
        strike      = row.get("strike")

        entry   = _price_on_or_after(closes, ticker,  filing_date)
        spy_e   = _price_on_or_after(closes, "SPY",   filing_date)
        if entry is None or spy_e is None:
            continue

        if deep_itm_only:
            if pd.isna(strike):
                continue
            try:
                if float(strike) / entry >= itm_threshold:
                    continue
            except (TypeError, ValueError):
                continue

        for hold in hold_days_list:
            exit_date = filing_date + timedelta(days=hold)
            exit_p    = _price_on_or_after(closes, ticker, exit_date)
            spy_x     = _price_on_or_after(closes, "SPY",  exit_date)
            if exit_p is None or spy_x is None:
                continue
            ret     = (exit_p - entry)   / entry   * 100
            spy_ret = (spy_x  - spy_e)   / spy_e   * 100
            results_by_hold[hold].append({
                "politician": politician,
                "chamber":    chamber,
                "ticker":     ticker,
                "ret":        ret,
                "spy_ret":    spy_ret,
                "excess":     ret - spy_ret,
            })

    out = {}
    for hold, rows in results_by_hold.items():
        if not rows:
            out[hold] = pd.DataFrame()
            continue
        rdf = pd.DataFrame(rows)
        grp = rdf.groupby(["politician", "chamber"]).agg(
            trades    = ("ret", "count"),
            avg_ret   = ("ret",    "mean"),
            avg_spy   = ("spy_ret","mean"),
            avg_excess= ("excess", "mean"),
            win_rate  = ("excess", lambda x: (x > 0).mean() * 100),
        ).reset_index()
        grp = grp[grp["trades"] >= min_trades].sort_values("avg_excess", ascending=False)
        for col in ("avg_ret", "avg_spy", "avg_excess", "win_rate"):
            grp[col] = grp[col].round(2)
        out[hold] = grp.reset_index(drop=True)
    return out


def print_options_rankings(rankings_by_hold: dict[int, pd.DataFrame], deep_itm: bool = False) -> None:
    label = "Deep ITM calls" if deep_itm else "All call purchases"
    print(f"\n{'='*70}")
    print(f"  Options Signal Backtest -- {label}")
    print(f"  Strategy: buy underlying stock on filing date, hold N days vs SPY")
    print(f"{'='*70}")

    for hold, df in sorted(rankings_by_hold.items()):
        if df.empty:
            print(f"\n  Hold {hold}d -- no data")
            continue
        reliable = df[(df["avg_excess"] > 0) & (df["trades"] >= 2)]
        print(f"\n  Hold {hold}d  ({len(df)} politicians, {int(df['trades'].sum())} signals, "
              f"{len(reliable)} with positive excess)")
        print(f"  {'Politician':<32} {'Ch':<3} {'Trades':>6}  {'Avg Excess':>10}  {'Win%':>5}  {'Avg Ret':>8}  {'vs SPY':>7}")
        print("  " + "-" * 74)
        for _, row in df.head(20).iterrows():
            marker = " *" if row["avg_excess"] > 0 else "  "
            print(
                f"{marker}{row['politician']:<32} {row['chamber'][:1]:<3}"
                f"{int(row['trades']):>6}  "
                f"{row['avg_excess']:>+9.1f}%  "
                f"{row['win_rate']:>4.0f}%  "
                f"{row['avg_ret']:>+7.1f}%  "
                f"{row['avg_spy']:>+6.1f}%"
            )


def run_options_analysis() -> None:
    df = load_options()
    print_overview(df)
    analyse_tuberville(df)
    analyse_house_calls(df)
