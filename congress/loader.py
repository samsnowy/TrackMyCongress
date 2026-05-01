"""
Unified loader for scraped congress trade data.

Two functions:
  load_historical()     — combined House + Senate in scraped schema
                          (name, ticker, transaction, transaction_date, filing_date, ...)
                          Used by trade_pairs.py

  load_for_backtest()   — same data normalised to Quiver-style column names
                          (Representative, Ticker, Transaction, TransactionDate, ReportDate, ...)
                          Used by backtest.py / run_politician_backtest()
"""

import os
import pandas as pd

_HOUSE_FILE  = "congress_historical.csv"
_SENATE_FILE = "senate_historical.csv"

_DATE_FMT = "%m/%d/%Y"


def load_historical(chamber: str = "both") -> pd.DataFrame:
    """
    Load scraped trade data in raw scraped schema.
    chamber: "house" | "senate" | "both"
    Adds a 'chamber' column to distinguish sources.
    """
    frames = []

    if chamber in ("house", "both") and os.path.exists(_HOUSE_FILE):
        df = pd.read_csv(_HOUSE_FILE)
        df["chamber"] = "House"
        frames.append(df)
    elif chamber == "house":
        raise FileNotFoundError(f"{_HOUSE_FILE} not found. Run: python -m congress.scraper")

    if chamber in ("senate", "both") and os.path.exists(_SENATE_FILE):
        df = pd.read_csv(_SENATE_FILE)
        df["chamber"] = "Senate"
        frames.append(df)
    elif chamber == "senate":
        raise FileNotFoundError(f"{_SENATE_FILE} not found. Run: python -m congress.senate_scraper")

    if not frames:
        raise FileNotFoundError("No scraped data found. Run python -m congress.scrape_all")

    combined = pd.concat(frames, ignore_index=True)
    combined["transaction_date"] = pd.to_datetime(combined["transaction_date"], format=_DATE_FMT, errors="coerce")
    combined["filing_date"]      = pd.to_datetime(combined["filing_date"],      errors="coerce")
    combined["disclosure_lag_days"] = (combined["filing_date"] - combined["transaction_date"]).dt.days

    return combined.dropna(subset=["ticker", "transaction_date"]).reset_index(drop=True)


def load_for_backtest(chamber: str = "both", purchases_only: bool = False) -> pd.DataFrame:
    """
    Load scraped data normalised to the column names expected by backtest.py.
    Maps: name→Representative, filing_date→ReportDate, transaction_date→TransactionDate,
          ticker→Ticker, transaction→Transaction. Party filled as '?'.
    """
    df = load_historical(chamber=chamber)

    df = df.rename(columns={
        "name":             "Representative",
        "filing_date":      "ReportDate",
        "transaction_date": "TransactionDate",
        "ticker":           "Ticker",
        "transaction":      "Transaction",
    })

    df["Party"] = "?"

    if purchases_only:
        df = df[df["Transaction"] == "Purchase"]

    return df.reset_index(drop=True)
