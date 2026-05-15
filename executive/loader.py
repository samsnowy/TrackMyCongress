"""
Load executive branch OGE disclosure trades for display.

This module intentionally does not feed the live strategy or congressional
backtests. It normalizes an optional executive_trades.csv into the dashboard
filings shape.
"""

from __future__ import annotations

import os

import pandas as pd


EXECUTIVE_TRADES_CSV = "executive_trades.csv"

REQUIRED_COLUMNS = {
    "name",
    "role",
    "filing_date",
    "transaction_date",
    "ticker",
    "transaction",
    "amount_range",
}


def load_executive_trades(path: str = EXECUTIVE_TRADES_CSV) -> pd.DataFrame:
    """Load normalized executive disclosure trades, or an empty DataFrame."""
    if not os.path.exists(path):
        return pd.DataFrame(columns=sorted(REQUIRED_COLUMNS | {"agency", "source", "doc_url"}))

    df = pd.read_csv(path)
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"{path} missing required columns: {', '.join(sorted(missing))}")

    for col in ("filing_date", "transaction_date"):
        df[col] = pd.to_datetime(df[col], errors="coerce")

    df = df.dropna(subset=["filing_date", "ticker", "name"])
    df["ticker"] = df["ticker"].astype(str).str.upper().str.strip()
    df["source"] = df.get("source", "OGE").fillna("OGE")
    df["role"] = df.get("role", "").fillna("")
    df["agency"] = df.get("agency", "").fillna("")
    df["doc_url"] = df.get("doc_url", "").fillna("")
    return df
