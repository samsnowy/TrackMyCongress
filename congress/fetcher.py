"""
Congress trade data via Quiver Quantitative's endpoint.
Caches to congress_trades.csv so repeated calls don't re-fetch.

Fields per trade:
  Representative  — politician name
  Party           — D / R
  House           — Representatives / Senate
  TransactionDate — when the trade happened
  ReportDate      — when disclosed (our realistic entry point)
  Ticker          — stock symbol
  Transaction     — Purchase / Sale
  Range           — dollar size bracket
  ExcessReturn    — % return vs SPY from TransactionDate (pre-calc'd by Quiver)
  PriceChange     — raw % price change since TransactionDate
  SPYChange       — SPY % change over same window
"""

import re
import requests
import pandas as pd
import os
from datetime import datetime, timedelta

_ENDPOINT   = "https://api.quiverquant.com/beta/live/congresstrading"
_CACHE_FILE = "congress_trades.csv"
_CACHE_TTL_HOURS = 12
_MAX_STALE_CACHE_HOURS = 72

_HEADERS = {
    "User-Agent": "TrackMyCongress/1.0 (research; public STOCK Act data)",
    "Accept": "application/json",
}


def _get_auth_headers() -> dict:
    return dict(_HEADERS)


def _cache_fresh() -> bool:
    if not os.path.exists(_CACHE_FILE):
        return False
    age_hours = (datetime.now().timestamp() - os.path.getmtime(_CACHE_FILE)) / 3600
    return age_hours < _CACHE_TTL_HOURS


def fetch_trades(purchases_only: bool = False, sales_only: bool = False, force_refresh: bool = False) -> pd.DataFrame:
    """
    Fetch congress trade disclosures.
    Uses a local CSV cache (congress_trades.csv) — refreshes every 12 hours.
    Pass force_refresh=True to bypass cache.
    """
    df: pd.DataFrame
    if not force_refresh and _cache_fresh():
        df = pd.read_csv(_CACHE_FILE)
        print(f"  [cache] loaded {len(df)} trades from {_CACHE_FILE}")
    else:
        print(f"  [fetch] hitting Quiver API...")
        try:
            r = requests.get(_ENDPOINT, headers=_get_auth_headers(), timeout=20)
            if r.status_code == 401:
                raise PermissionError(
                    "Quiver API returned 401 — the free public endpoint may have been restricted.\n"
                    "Options:\n"
                    "  1. Use cached data if available: the last fetch is saved to congress_trades.csv\n"
                    "  2. Re-run — sometimes the endpoint is temporarily rate-limited"
                )
            r.raise_for_status()
            df = pd.DataFrame(r.json())
            df.to_csv(_CACHE_FILE, index=False)
            print(f"  [fetch] {len(df)} trades saved to {_CACHE_FILE}")
        except (PermissionError, requests.RequestException) as e:
            if os.path.exists(_CACHE_FILE):
                age_h = (datetime.now().timestamp() - os.path.getmtime(_CACHE_FILE)) / 3600
                if age_h > _MAX_STALE_CACHE_HOURS:
                    raise RuntimeError(
                        f"Cache is {age_h:.0f}h old (>{_MAX_STALE_CACHE_HOURS}h limit) and API is unavailable. "
                        f"Delete {_CACHE_FILE} or restore API access."
                    ) from e
                age_str = f"{age_h:.0f}h old"
                warn = "  [WARN] cache is >24h stale" if age_h > 24 else ""
                print(f"  [cache] API unavailable — loading stale cache ({age_str}) from {_CACHE_FILE}{warn}")
                df = pd.read_csv(_CACHE_FILE)
            else:
                raise

    df["TransactionDate"] = pd.to_datetime(df["TransactionDate"])
    df["ReportDate"]      = pd.to_datetime(df["ReportDate"])
    df["disclosure_lag_days"] = (df["ReportDate"] - df["TransactionDate"]).dt.days
    df["ExcessReturn"]    = pd.to_numeric(df["ExcessReturn"], errors="coerce")
    df["PriceChange"]     = pd.to_numeric(df["PriceChange"],  errors="coerce")
    df["SPYChange"]       = pd.to_numeric(df["SPYChange"],    errors="coerce")

    if purchases_only:
        df = df[df["Transaction"] == "Purchase"]
    if sales_only:
        df = df[df["Transaction"] == "Sale"]

    return df.sort_values("ReportDate", ascending=False).reset_index(drop=True)


def top_politicians(df: pd.DataFrame, min_trades: int = 3, purchases_only: bool = True) -> pd.DataFrame:
    """
    Rank politicians by average ExcessReturn on their purchases.
    Only includes those with at least min_trades to filter noise.
    """
    if purchases_only:
        df = df[df["Transaction"] == "Purchase"]

    grouped = df.groupby("Representative").agg(
        trades       = ("Ticker", "count"),
        avg_excess_r = ("ExcessReturn", "mean"),
        avg_return   = ("PriceChange",  "mean"),
        party        = ("Party",        "first"),
        house        = ("House",        "first"),
    ).reset_index()

    grouped = grouped[grouped["trades"] >= min_trades]
    return grouped.sort_values("avg_excess_r", ascending=False).reset_index(drop=True)


def top_tickers(df: pd.DataFrame, min_trades: int = 2) -> pd.DataFrame:
    """Most frequently traded tickers with average excess return."""
    grouped = df.groupby("Ticker").agg(
        trades       = ("Representative", "count"),
        purchases    = ("Transaction",    lambda x: (x == "Purchase").sum()),
        sales        = ("Transaction",    lambda x: (x == "Sale").sum()),
        avg_excess_r = ("ExcessReturn",   "mean"),
        avg_return   = ("PriceChange",    "mean"),
    ).reset_index()

    grouped = grouped[grouped["trades"] >= min_trades]
    return grouped.sort_values("trades", ascending=False).reset_index(drop=True)


def disclosure_lag_stats(df: pd.DataFrame) -> dict:
    """How long does it typically take for trades to be disclosed?"""
    lag = df["disclosure_lag_days"].dropna()
    return {
        "median_days": int(lag.median()),
        "mean_days":   round(lag.mean(), 1),
        "min_days":    int(lag.min()),
        "max_days":    int(lag.max()),
        "pct_under_30": round((lag <= 30).mean() * 100, 1),
        "pct_under_45": round((lag <= 45).mean() * 100, 1),
    }


_OPT_DESC_RE = re.compile(
    r"(CALL|PUT) OPTIONS.*?STRIKE PRICE \$?([\d.]+).*?EXPIRES (\d{2}/\d{2}/\d{4})",
    re.IGNORECASE,
)


def fetch_options(force_refresh: bool = False) -> pd.DataFrame:
    """
    Extract options purchase rows from the Quiver live feed (TickerType == 'OP').
    Parses Description for option_type, strike, and expiry.
    Returns a DataFrame in the same normalised schema used by detect_options_signals().

    Columns: name, ticker, filing_date, transaction_date, option_type,
             strike, expiration, amount_range, transaction
    """
    df = fetch_trades(force_refresh=force_refresh)
    ops = df[df["TickerType"] == "OP"].copy()

    parsed = []
    for _, row in ops.iterrows():
        desc = str(row.get("Description", ""))
        m    = _OPT_DESC_RE.search(desc)
        parsed.append({
            "name":             row["Representative"],
            "ticker":           row["Ticker"],
            "filing_date":      row["ReportDate"],
            "transaction_date": row["TransactionDate"],
            "transaction":      row["Transaction"],
            "amount_range":     row["Range"],
            "option_type":      m.group(1).capitalize() if m else None,
            "strike":           float(m.group(2))       if m else None,
            "expiration":       pd.to_datetime(m.group(3), format="%m/%d/%Y") if m else pd.NaT,
        })

    return pd.DataFrame(parsed) if parsed else pd.DataFrame(
        columns=["name","ticker","filing_date","transaction_date","transaction",
                 "amount_range","option_type","strike","expiration"]
    )


def trades_for_politician(df: pd.DataFrame, name: str) -> pd.DataFrame:
    """Filter to a specific politician (case-insensitive literal match, not regex)."""
    mask = df["Representative"].str.contains(name, case=False, na=False, regex=False)
    return df[mask].sort_values("TransactionDate", ascending=False)


def print_recent(df: pd.DataFrame, n: int = 20) -> None:
    print(f"\n{'Date':<12} {'Rep':<28} {'P':<2} {'Ticker':<7} {'Type':<10} {'Range':<22} {'Lag':>5} {'ExRet':>7}")
    print("-" * 100)
    for _, row in df.head(n).iterrows():
        lag = f"{int(row['disclosure_lag_days'])}d" if pd.notna(row['disclosure_lag_days']) else "?"
        ex  = f"{row['ExcessReturn']:>+.1f}%" if pd.notna(row['ExcessReturn']) else "?"
        print(
            f"{str(row['ReportDate'].date()):<12} "
            f"{str(row['Representative']):<28} "
            f"{str(row['Party']):<2} "
            f"{str(row['Ticker']):<7} "
            f"{str(row['Transaction']):<10} "
            f"{str(row['Range']):<22} "
            f"{lag:>5} "
            f"{ex:>7}"
        )
