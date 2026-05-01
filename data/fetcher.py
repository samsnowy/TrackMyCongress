"""
yfinance price helpers shared across the research pipeline.
"""

import yfinance as yf
import pandas as pd
from datetime import timedelta


def fetch_daily_closes(
    tickers: list[str],
    start: pd.Timestamp,
    end: pd.Timestamp,
    end_buffer_days: int = 5,
) -> pd.DataFrame:
    """
    Batch-download daily closing prices for tickers + SPY.
    Returns a DataFrame with dates as index and tickers as columns.

    end_buffer_days: extra days fetched past `end` to cover weekends and
                     post-sell-filing windows (use 40 for sell-lag analysis).
    """
    all_t = list(set(tickers + ["SPY"]))
    raw = yf.download(
        all_t,
        start=start - timedelta(days=5),
        end=end + timedelta(days=end_buffer_days),
        interval="1d",
        auto_adjust=True,
        progress=False,
    )
    closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    closes.index = pd.to_datetime(closes.index).tz_localize(None)
    closes.columns = [str(c) for c in closes.columns]
    return closes


def get_latest_price(ticker: str) -> float | None:
    """Most recent daily close via yfinance. Used by the live strategy."""
    try:
        hist = yf.Ticker(ticker).history(period="3d")
        if hist.empty:
            return None
        return float(hist["Close"].iloc[-1])
    except Exception as e:
        print(f"  [warn] price fetch failed for {ticker}: {e}")
        return None


def get_latest_prices(tickers: list[str]) -> dict[str, float]:
    """Batch-fetch the most recent closing price for multiple tickers in one call."""
    if not tickers:
        return {}
    try:
        closes = fetch_daily_closes(
            tickers,
            pd.Timestamp.today() - pd.Timedelta(days=7),
            pd.Timestamp.today(),
        )
        return {
            t: float(closes[t].dropna().iloc[-1])
            for t in tickers
            if t in closes.columns and not closes[t].dropna().empty
        }
    except Exception as e:
        print(f"  [warn] batch price fetch failed: {e}")
        return {}
