"""
yfinance price helpers shared across the research pipeline.
"""

import json
import os

import yfinance as yf
import pandas as pd
from datetime import timedelta


PRICE_CACHE_DIR = "price_cache"
PRICE_CACHE_CSV = os.path.join(PRICE_CACHE_DIR, "daily_closes.csv")
FAILED_TICKERS_JSON = os.path.join(PRICE_CACHE_DIR, "failed_tickers.json")


def _clean_tickers(tickers: list[str]) -> list[str]:
    cleaned = {str(t).upper().strip() for t in tickers if str(t).strip()}
    cleaned.add("SPY")
    return sorted(cleaned)


def _normalize_date(value: pd.Timestamp) -> pd.Timestamp:
    return pd.to_datetime(value).tz_localize(None).normalize()


def _load_price_cache(path: str = PRICE_CACHE_CSV) -> pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame()
    try:
        df = pd.read_csv(path, index_col=0)
        df.index = pd.to_datetime(df.index).tz_localize(None)
        df.columns = [str(c).upper() for c in df.columns]
        return df.sort_index()
    except Exception as e:
        print(f"  [warn] price cache ignored: {e}")
        return pd.DataFrame()


def _save_price_cache(df: pd.DataFrame, path: str = PRICE_CACHE_CSV) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    df = df.sort_index()
    df.to_csv(path, index_label="Date")


def _load_failed_tickers(path: str = FAILED_TICKERS_JSON) -> set[str]:
    if not os.path.exists(path):
        return set()
    try:
        with open(path, encoding="utf-8") as f:
            payload = json.load(f)
        return {str(t).upper() for t in payload.get("tickers", [])}
    except Exception:
        return set()


def _save_failed_tickers(tickers: set[str], path: str = FAILED_TICKERS_JSON) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"tickers": sorted(tickers)}, f, indent=2)


def _download_daily_closes(
    tickers: list[str],
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.DataFrame:
    raw = yf.download(
        tickers,
        start=start,
        end=end,
        interval="1d",
        auto_adjust=True,
        progress=False,
    )
    closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    if isinstance(closes, pd.Series):
        closes = closes.to_frame(name=tickers[0])
    closes.index = pd.to_datetime(closes.index).tz_localize(None)
    closes.columns = [str(c).upper() for c in closes.columns]
    return closes


def fetch_daily_closes(
    tickers: list[str],
    start: pd.Timestamp,
    end: pd.Timestamp,
    end_buffer_days: int = 5,
    use_cache: bool = True,
) -> pd.DataFrame:
    """
    Batch-download daily closing prices for tickers + SPY.
    Returns a DataFrame with dates as index and tickers as columns.

    end_buffer_days: extra days fetched past `end` to cover weekends and
                     post-sell-filing windows (use 40 for sell-lag analysis).
    """
    all_t = _clean_tickers(tickers)
    fetch_start = _normalize_date(start - timedelta(days=5))
    requested_end = _normalize_date(end + timedelta(days=end_buffer_days))
    # yfinance's end date is exclusive. Cap at today so backtests do not
    # repeatedly request future bars that cannot exist yet.
    fetch_end = min(requested_end, _normalize_date(pd.Timestamp.today()))

    if not use_cache:
        return _download_daily_closes(all_t, fetch_start, fetch_end)

    failed_tickers = _load_failed_tickers()
    if failed_tickers:
        skipped_failed = [t for t in all_t if t in failed_tickers]
        all_t = [t for t in all_t if t not in failed_tickers]
        if skipped_failed:
            print(f"  Price cache: skipping {len(skipped_failed)} known failed ticker(s)")
    if not all_t:
        return pd.DataFrame()

    cache = _load_price_cache()
    if not cache.empty:
        empty_cached = {c for c in cache.columns if c != "SPY" and cache[c].dropna().empty}
        if empty_cached:
            failed_tickers.update(empty_cached)
            _save_failed_tickers(failed_tickers)
            cache = cache.drop(columns=sorted(empty_cached), errors="ignore")
            _save_price_cache(cache)
            print(f"  Price cache: moved {len(empty_cached)} empty ticker(s) to failed list")

    missing_tickers = [t for t in all_t if t not in cache.columns]

    missing_ranges: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    if cache.empty:
        missing_ranges.append((fetch_start, fetch_end))
    else:
        cache_start = _normalize_date(cache.index.min())
        cache_end = _normalize_date(cache.index.max())
        if fetch_start < cache_start:
            missing_ranges.append((fetch_start, cache_start))
        if fetch_end > cache_end + timedelta(days=1):
            missing_ranges.append((cache_end + timedelta(days=1), fetch_end))

    fetched: list[pd.DataFrame] = []

    # Fetch all tickers for missing date ranges so the cache extends cleanly.
    for range_start, range_end in missing_ranges:
        if range_start >= range_end:
            continue
        print(f"  Price cache miss: fetching {len(all_t)} tickers from {range_start.date()} to {range_end.date()}")
        fetched.append(_download_daily_closes(all_t, range_start, range_end))

    # Fetch newly requested tickers only for the span already covered by cache.
    # Missing date ranges above already fetch all requested tickers.
    if missing_tickers and not cache.empty:
        cache_start = max(_normalize_date(cache.index.min()), fetch_start)
        cache_end = min(_normalize_date(cache.index.max()) + timedelta(days=1), fetch_end)
        if cache_start < cache_end:
            print(
                f"  Price cache miss: fetching {len(missing_tickers)} new ticker(s) "
                f"from {cache_start.date()} to {cache_end.date()}"
            )
            fetched.append(_download_daily_closes(missing_tickers, cache_start, cache_end))

    combined = cache.copy()
    for df_new in fetched:
        if df_new.empty:
            continue
        if combined.empty:
            combined = df_new
        else:
            combined = df_new.combine_first(combined)
    combined = combined.sort_index() if not combined.empty else combined

    if not combined.empty:
        newly_failed = {
            t for t in all_t
            if t != "SPY" and (t not in combined.columns or combined[t].dropna().empty)
        }
        if newly_failed:
            failed_tickers.update(newly_failed)
            _save_failed_tickers(failed_tickers)
            print(f"  Price cache: remembered {len(newly_failed)} failed ticker(s)")
            combined = combined.drop(columns=[t for t in newly_failed if t in combined.columns], errors="ignore")

        _save_price_cache(combined)
        available = [t for t in all_t if t in combined.columns]
        return combined.loc[(combined.index >= fetch_start) & (combined.index <= fetch_end), available]

    return combined


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
