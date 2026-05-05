"""
Pairs buy/sell transactions for the same politician + ticker from the
historical scraper CSV, then analyses the price trajectory across four
key dates:

  buy_tx     — when they actually bought (transaction_date of the buy)
  buy_filed  — when the buy was disclosed (filing_date of the buy)
  sell_tx    — when they actually sold   (transaction_date of the sell)
  sell_filed — when the sell was disclosed (filing_date of the sell)

Key questions:
  1. How long do they hold before selling? (sell_tx - buy_tx)
  2. What is the price return at each date?
  3. Does price drop in the window between sell_tx and sell_filed?
     (i.e., if you're following them you're still holding during that drop)
  4. What's the optimal exit day after entry (buy_filed) to maximise return?
"""

import pandas as pd
import numpy as np
from datetime import timedelta
from dataclasses import dataclass

from data.fetcher import fetch_daily_closes


@dataclass
class TradePair:
    politician:     str
    ticker:         str
    buy_tx:         pd.Timestamp
    buy_filed:      pd.Timestamp
    sell_tx:        pd.Timestamp
    sell_filed:     pd.Timestamp
    hold_days:      int          # sell_tx - buy_tx (actual hold)
    lag_buy:        int          # buy_filed - buy_tx
    lag_sell:       int          # sell_filed - sell_tx

    # price returns (filled after price fetch)
    ret_at_sell_tx:    float | None = None   # return if you sold when they sold
    ret_at_sell_filed: float | None = None   # return if you waited for sell filing
    ret_30d_after_sell_filed: float | None = None  # aftermath — where price goes after public knows
    spy_ret_hold:      float | None = None   # SPY over same buy_filed → sell_filed window
    excess_ret:        float | None = None   # ret_at_sell_filed - spy_ret_hold


def build_pairs(df: pd.DataFrame, max_match_days: int = 365) -> list[TradePair]:
    """
    Match buys to sells for the same (politician, ticker).
    Uses transaction_date for matching and filing_date for both.
    Only pairs where sell comes after buy and within max_match_days.
    """
    buys  = df[df["transaction"].isin(["Purchase"])].copy()
    sells = df[df["transaction"].isin(["Sale", "Sale (Partial)"])].copy()

    buys["transaction_date"]  = pd.to_datetime(buys["transaction_date"],  errors="coerce")
    buys["filing_date"]       = pd.to_datetime(buys["filing_date"],       errors="coerce")
    sells["transaction_date"] = pd.to_datetime(sells["transaction_date"], errors="coerce")
    sells["filing_date"]      = pd.to_datetime(sells["filing_date"],      errors="coerce")

    pairs = []
    for (politician, ticker), bgroup in buys.groupby(["name", "ticker"]):
        sgroup = sells[(sells["name"] == politician) & (sells["ticker"] == ticker)]
        if sgroup.empty:
            continue

        for _, buy_row in bgroup.iterrows():
            buy_tx = buy_row["transaction_date"]
            if pd.isna(buy_tx):
                continue

            # Find earliest sell after this buy within max_match_days
            candidates = sgroup[
                (sgroup["transaction_date"] > buy_tx) &
                (sgroup["transaction_date"] <= buy_tx + timedelta(days=max_match_days))
            ].sort_values("transaction_date")

            if candidates.empty:
                continue

            sell_row = candidates.iloc[0]
            sell_tx  = sell_row["transaction_date"]

            buy_filed  = buy_row["filing_date"]
            sell_filed = sell_row["filing_date"]
            if pd.isna(buy_filed) or pd.isna(sell_filed):
                continue

            pairs.append(TradePair(
                politician  = politician,
                ticker      = ticker,
                buy_tx      = buy_tx,
                buy_filed   = buy_filed,
                sell_tx     = sell_tx,
                sell_filed  = sell_filed,
                hold_days   = (sell_tx - buy_tx).days,
                lag_buy     = (buy_filed - buy_tx).days,
                lag_sell    = (sell_filed - sell_tx).days,
            ))

    return pairs



def _price_on_or_after(closes: pd.DataFrame, ticker: str, date: pd.Timestamp) -> float | None:
    if ticker not in closes.columns:
        return None
    s = closes[ticker][closes.index >= date].dropna()
    return float(s.iloc[0]) if not s.empty else None


def enrich_pairs(pairs: list[TradePair]) -> list[TradePair]:
    """Fetch prices and fill return fields on each pair."""
    if not pairs:
        return pairs

    tickers = list({p.ticker for p in pairs})
    start   = min(p.buy_filed for p in pairs)
    end     = max(p.sell_filed for p in pairs)

    print(f"  Fetching prices for {len(tickers)} tickers...")
    closes = fetch_daily_closes(tickers, start, end, end_buffer_days=40)

    for p in pairs:
        entry = _price_on_or_after(closes, p.ticker, p.buy_filed)
        spy_e = _price_on_or_after(closes, "SPY",    p.buy_filed)
        if not entry or not spy_e:
            continue

        at_sell_tx    = _price_on_or_after(closes, p.ticker, p.sell_tx)
        at_sell_filed = _price_on_or_after(closes, p.ticker, p.sell_filed)
        after_30d     = _price_on_or_after(closes, p.ticker, p.sell_filed + timedelta(days=30))
        spy_exit      = _price_on_or_after(closes, "SPY",    p.sell_filed)

        if at_sell_tx:
            p.ret_at_sell_tx    = round((at_sell_tx    - entry) / entry * 100, 2)
        if at_sell_filed:
            p.ret_at_sell_filed = round((at_sell_filed - entry) / entry * 100, 2)
        if after_30d:
            p.ret_30d_after_sell_filed = round((after_30d - entry) / entry * 100, 2)
        if spy_exit and spy_e:
            p.spy_ret_hold  = round((spy_exit - spy_e) / spy_e * 100, 2)
            if p.ret_at_sell_filed is not None:
                p.excess_ret = round(p.ret_at_sell_filed - p.spy_ret_hold, 2)

    return pairs


def pairs_to_df(pairs: list[TradePair]) -> pd.DataFrame:
    return pd.DataFrame([p.__dict__ for p in pairs])


def analyse_sell_lag_effect(pairs_df: pd.DataFrame) -> pd.DataFrame:
    """
    Key question: does the price drop between sell_tx and sell_filed?
    Shows the average price movement during the sell lag window.
    If negative, following politicians means you hold through a drop you
    could avoid if you exited before the sell filing.
    """
    df = pairs_df.dropna(subset=["ret_at_sell_tx", "ret_at_sell_filed"])
    df = df.copy()
    df["move_during_sell_lag"] = df["ret_at_sell_filed"] - df["ret_at_sell_tx"]
    df["sell_lag_bucket"] = pd.cut(df["lag_sell"], bins=[0, 15, 30, 45, 60, 999],
                                   labels=["<=15d", "16-30d", "31-45d", "46-60d", ">60d"])
    return df.groupby("sell_lag_bucket", observed=True).agg(
        pairs           = ("politician", "count"),
        avg_move_during_lag = ("move_during_sell_lag", "mean"),
        pct_negative    = ("move_during_sell_lag", lambda x: (x < 0).mean() * 100),
        avg_ret_at_sell_tx    = ("ret_at_sell_tx",    "mean"),
        avg_ret_at_sell_filed = ("ret_at_sell_filed", "mean"),
    ).round(2).reset_index()


def optimal_exit_curve(pairs: list[TradePair], closes: pd.DataFrame | None = None) -> pd.DataFrame:
    """
    For each day from entry (buy_filed), what's the average return across all pairs?
    Shows the return curve so you can pick the optimal exit window.
    Requires closes DataFrame (from enrich_pairs internal fetch — call separately if needed).
    """
    rows = []
    for day in range(0, 121, 5):
        returns = []
        for p in pairs:
            if closes is not None and p.ticker in closes.columns:
                target_date = p.buy_filed + timedelta(days=day)
                price = _price_on_or_after(closes, p.ticker, target_date)
                entry = _price_on_or_after(closes, p.ticker, p.buy_filed)
                if price and entry:
                    returns.append((price - entry) / entry * 100)
        if returns:
            rows.append({
                "day":      day,
                "avg_ret":  round(np.mean(returns), 2),
                "median_ret": round(np.median(returns), 2),
                "win_pct":  round(sum(1 for r in returns if r > 0) / len(returns) * 100, 1),
                "n":        len(returns),
            })
    return pd.DataFrame(rows)


def print_pair_summary(pairs_df: pd.DataFrame) -> None:
    df = pairs_df.dropna(subset=["ret_at_sell_tx", "ret_at_sell_filed"])

    print(f"\n{'='*65}")
    print(f"  Congress Trade Pair Analysis  ({len(df)} matched buy/sell pairs)")
    print(f"{'='*65}")

    print(f"\n  Typical holding period (buy_tx -> sell_tx):")
    print(f"    Median: {df['hold_days'].median():.0f} days")
    print(f"    Mean:   {df['hold_days'].mean():.0f} days")
    print(f"    Range:  {df['hold_days'].min()}d - {df['hold_days'].max()}d")

    print(f"\n  Sell disclosure lag (sell_tx -> sell_filed):")
    print(f"    Median: {df['lag_sell'].median():.0f} days")
    print(f"    Mean:   {df['lag_sell'].mean():.0f} days")

    print(f"\n  Return if you exit when they exit (sell_tx):")
    print(f"    Avg:    {df['ret_at_sell_tx'].mean():>+.1f}%")
    print(f"    Win%:   {(df['ret_at_sell_tx'] > 0).mean()*100:.0f}%")

    print(f"\n  Return if you wait for sell filing (sell_filed):")
    print(f"    Avg:    {df['ret_at_sell_filed'].mean():>+.1f}%")
    print(f"    Win%:   {(df['ret_at_sell_filed'] > 0).mean()*100:.0f}%")

    drift = df["ret_at_sell_filed"] - df["ret_at_sell_tx"]
    print(f"\n  Price drift during sell lag window:")
    print(f"    Avg move: {drift.mean():>+.1f}%  (negative = price drops while you hold)")
    print(f"    % that drop: {(drift < 0).mean()*100:.0f}%")

    if "ret_30d_after_sell_filed" in df.columns:
        after = df["ret_30d_after_sell_filed"].dropna()
        if not after.empty:
            print(f"\n  Return 30d after sell filing (aftermath):")
            print(f"    Avg:    {after.mean():>+.1f}%")

    print(f"\n  Sell lag effect by disclosure speed:")
    lag_effect = analyse_sell_lag_effect(df)
    print(f"  {'Lag Bucket':<12} {'Pairs':>6} {'Move During Lag':>16} {'% Negative':>11}")
    print("  " + "-" * 50)
    for _, row in lag_effect.iterrows():
        print(f"  {str(row['sell_lag_bucket']):<12} {int(row['pairs']):>6} "
              f"  {row['avg_move_during_lag']:>+10.1f}%  {row['pct_negative']:>9.0f}%")


def strategy2_sensitivity(
    pairs: list[TradePair],
    hold_after_sell: list[int] | None = None,
    reliable_pols: set[str] | None = None,
) -> pd.DataFrame:
    """
    Strategy 2: buy on buy_filed, hold until sell_filed + N days.
    Tests whether holding past the sell filing adds return vs SPY.

    hold_after_sell: days to hold past sell_filed to test [default: 0,10,20,30,60,90]
    reliable_pols:   if provided, filter to only these politicians
    """
    if hold_after_sell is None:
        hold_after_sell = [0, 10, 20, 30, 60, 90]

    filtered = [p for p in pairs if reliable_pols is None or p.politician in reliable_pols]
    if not filtered:
        return pd.DataFrame()

    tickers = list({p.ticker for p in filtered})
    start   = min(p.buy_filed for p in filtered)
    end     = max(p.sell_filed for p in filtered) + timedelta(days=max(hold_after_sell) + 10)

    print(f"  Fetching prices for {len(tickers)} tickers (strategy 2)...")
    closes = fetch_daily_closes(tickers, start, end)

    rows = []
    for n in hold_after_sell:
        returns, spy_rets = [], []
        for p in filtered:
            entry     = _price_on_or_after(closes, p.ticker, p.buy_filed)
            spy_entry = _price_on_or_after(closes, "SPY",    p.buy_filed)
            exit_date = p.sell_filed + timedelta(days=n)
            exit_p    = _price_on_or_after(closes, p.ticker, exit_date)
            spy_exit  = _price_on_or_after(closes, "SPY",    exit_date)
            if not all([entry, spy_entry, exit_p, spy_exit]):
                continue
            ret     = (exit_p   - entry)     / entry     * 100
            spy_ret = (spy_exit - spy_entry) / spy_entry * 100
            returns.append(ret)
            spy_rets.append(spy_ret)

        if returns:
            excess = [r - s for r, s in zip(returns, spy_rets)]
            rows.append({
                "hold_after_sell_d": n,
                "pairs":    len(returns),
                "avg_ret":  round(np.mean(returns), 2),
                "spy":      round(np.mean(spy_rets), 2),
                "excess":   round(np.mean(excess), 2),
                "win_pct":  round(sum(1 for e in excess if e > 0) / len(excess) * 100, 1),
            })

    return pd.DataFrame(rows)


def run_pair_analysis(df: pd.DataFrame | None = None, csv_path: str | None = None) -> pd.DataFrame:
    """Main entry point. Accepts a pre-loaded DataFrame or a CSV path."""
    if df is None:
        if csv_path is None:
            from congress.loader import load_historical
            df = load_historical()
        else:
            df = pd.read_csv(csv_path)
    print(f"  {len(df):,} trades, {df['name'].nunique()} politicians, {df['ticker'].nunique()} tickers")

    print("\nBuilding buy/sell pairs...")
    pairs = build_pairs(df)
    print(f"  {len(pairs)} matched pairs found")

    if not pairs:
        print("No pairs found — need both buy and sell records for the same politician+ticker.")
        return pd.DataFrame()

    print("\nFetching price history...")
    pairs = enrich_pairs(pairs)

    pairs_df = pairs_to_df(pairs)
    print_pair_summary(pairs_df)

    return pairs_df
