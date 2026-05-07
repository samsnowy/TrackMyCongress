"""
Strategy logic for the congressional disclosure follow-through.

Two signal types:
  Stock:   purchase disclosure by a politician in the reliable group
           Entry on ReportDate, hold 90 days.
  Options: deep-ITM call purchase by a known options-active politician
           Buy the underlying on filing_date, hold 30 days (signal fades faster).

Filters: exclude $1k-$15k filings (low conviction)
         deduplicate same-ticker signals within the lookback window

No I/O here — load_reliable_politicians() reads a CSV, everything else is
pure computation on DataFrames and dicts.
"""

import os
import re
from collections import defaultdict
from datetime import date, datetime, timedelta

import pandas as pd

from config import (
    HOLD_DAYS, OPTIONS_HOLD_DAYS, MAX_POSITIONS, POSITION_SIZE_PCT,
    SIGNAL_LOOKBACK, OPTIONS_LOOKBACK, DEEP_ITM_THRESHOLD,
    RELIABLE_MIN_EXCESS, RELIABLE_MIN_TRADES, MAX_SIGNAL_AGE,
)

# Known options-active politicians whose deep-ITM calls signal the underlying.
# Langevin and Tuberville excluded: Langevin buys OTM speculative calls;
# Tuberville runs straddles, not directional bets.
KNOWN_OPTIONS_POLITICIANS = {
    "Josh Gottheimer",
    "Nancy Pelosi",
    "Deborah Ross",
    "Rob Bresnahan",
}

def _is_low_conviction(range_str: str) -> bool:
    return str(range_str).strip().startswith("$1,001")


# Embedded fallback derived from a prior backtest run.
# Approximate — regenerate congress_rankings.csv for current results.
# Used only when congress_rankings.csv hasn't been generated yet.
_FALLBACK_RELIABLE: dict[str, dict] = {
    "Tim Moore":          {"avg_excess": 11.2, "trades": 41},
    "Mark Green":         {"avg_excess":  9.0, "trades":  9},
    "James Langevin":     {"avg_excess":  8.6, "trades":  7},
    "David McCormick":    {"avg_excess":  8.0, "trades": 24},
    "Daniel Sullivan":    {"avg_excess":  7.7, "trades": 40},
    "Kelly Morrison":     {"avg_excess":  7.2, "trades":  5},
    "Cleo Fields":        {"avg_excess":  6.4, "trades": 81},
    "Thomas Suozzi":      {"avg_excess":  4.1, "trades": 30},
    "Julie Johnson":      {"avg_excess":  4.1, "trades": 42},
}


def load_reliable_politicians(rankings_csv: str = "congress_rankings.csv") -> dict[str, dict]:
    """
    Load the reliable politician list from a saved backtest rankings CSV.
    Uses congress_rankings.csv (all-trades, 12 politicians) by default.
    Falls back to the embedded list if no CSV exists.
    Generate with: python main.py followcongress.
    """
    for path in (os.path.basename(rankings_csv), "congress_rankings_hc.csv"):
        if not os.path.exists(path):
            continue
        try:
            df = pd.read_csv(path)
            reliable = df[(df["avg_excess"] > RELIABLE_MIN_EXCESS) & (df["trades"] >= RELIABLE_MIN_TRADES)]
            if reliable.empty:
                continue
            label = "HC" if "hc" in path else "all-trades"
            print(f"  [strategy] loaded {len(reliable)} reliable politicians from {path} ({label})")
            return {
                row["politician"]: {"avg_excess": row["avg_excess"], "trades": int(row["trades"])}
                for _, row in reliable.iterrows()
            }
        except Exception as e:
            print(f"  [warn] could not parse {path}: {e}")

    print("  [warn] no rankings CSV found — using embedded fallback list")
    print("         Run: python main.py highconv")
    return _FALLBACK_RELIABLE


def _normalize_name(name: str) -> str:
    """Lowercase, strip titles and middle initials for fuzzy matching."""
    name = name.lower()
    for title in ["dr.", "mr.", "mrs.", "ms.", "jr.", "sr.", "rep.", "sen."]:
        name = name.replace(title, " ")
    name = re.sub(r"\b[a-z]\.\s*", " ", name)  # "H." → stripped
    name = re.sub(r"\b[a-z]\b", " ", name)      # bare "H" → stripped
    return " ".join(name.split())


def match_politician(quiver_name: str, reliable_pols: dict) -> bool:
    """
    Return True if quiver_name matches any politician in reliable_pols.
    Uses word-set containment after normalization to handle middle initials
    and minor format differences without substring false-positives.
    """
    words_q = set(_normalize_name(quiver_name).split())
    for pol_name in reliable_pols:
        words_p = set(_normalize_name(pol_name).split())
        if words_p <= words_q or words_q <= words_p:
            return True
    return False


def detect_new_signals(
    df: pd.DataFrame,
    seen: set,
    reliable_pols: dict,
    lookback_days: int = SIGNAL_LOOKBACK,
    max_age_days: int = MAX_SIGNAL_AGE,
) -> list[dict]:
    """
    Find purchase disclosures in the last lookback_days from reliable politicians.
    Returns all matching signals that haven't been seen before.
    Each signal has a unique signal_key so the caller can mark it seen.
    max_age_days: skip signals older than this many days (avoids stale entries on first run).
    """
    today  = pd.Timestamp.today().normalize()
    cutoff = today - pd.Timedelta(days=lookback_days)
    fresh  = today - pd.Timedelta(days=max_age_days)

    candidates = df[
        (df["Transaction"] == "Purchase") &
        (df["ReportDate"] >= cutoff) &
        (df["ReportDate"] >= fresh)
    ]

    signals = []
    for _, row in candidates.iterrows():
        if not match_politician(str(row["Representative"]), reliable_pols):
            continue
        key = f"{row['Ticker']}_{row['ReportDate'].date()}_{row['Representative']}"
        if key in seen:
            continue
        signals.append({
            "ticker":      str(row["Ticker"]),
            "politician":  str(row["Representative"]),
            "report_date": str(row["ReportDate"].date()),
            "tx_date":     str(row["TransactionDate"].date()),
            "range":       str(row["Range"]),
            "signal_key":  key,
        })
    return signals


def deduplicate_signals(signals: list[dict]) -> list[dict]:
    """
    If multiple politicians disclosed the same ticker in the lookback window,
    treat it as one (potentially stronger) accumulation signal.
    Takes the latest report_date; groups all politicians together.
    Returns the original list unchanged for keys — caller marks them all seen.
    """
    by_ticker: dict[str, list[dict]] = defaultdict(list)
    for s in signals:
        by_ticker[s["ticker"]].append(s)

    deduped = []
    for _, group in by_ticker.items():
        group.sort(key=lambda x: x["report_date"])
        lead = dict(group[-1])  # latest filing drives the signal
        if len(group) > 1:
            lead["politicians"]   = [s["politician"] for s in group]
            lead["accumulation"]  = True
        else:
            lead["politicians"]   = [lead["politician"]]
            lead["accumulation"]  = False
        deduped.append(lead)

    return deduped


def all_signal_keys_for_ticker(signals: list[dict], ticker: str) -> set:
    """Return every signal_key for a given ticker from a raw signals list."""
    return {s["signal_key"] for s in signals if s["ticker"] == ticker}


def positions_to_exit(open_positions: list[dict], today: str | None = None) -> list[dict]:
    """
    Return positions that have been held long enough to exit.

    Uses planned_exit (report_date + hold_days) when present — consistent with
    the backtest, which holds from ReportDate. Falls back to held_days >= target
    for legacy positions that pre-date planned_exit storage.
    """
    if today is None:
        today = str(date.today())
    today_dt = datetime.strptime(today, "%Y-%m-%d").date()

    exits = []
    for pos in open_positions:
        entry_dt  = datetime.strptime(pos["entry_date"], "%Y-%m-%d").date()
        held_days = (today_dt - entry_dt).days

        if "planned_exit" in pos:
            planned = datetime.strptime(pos["planned_exit"], "%Y-%m-%d").date()
            if today_dt >= planned:
                exits.append({**pos, "held_days": held_days})
        else:
            target = pos.get("hold_days", HOLD_DAYS)
            if held_days >= target:
                exits.append({**pos, "held_days": held_days})
    return exits


def _matches_options_politician(name: str) -> bool:
    """Check if name matches any known options-active politician (word-set match)."""
    words_n = set(_normalize_name(name).split())
    for pol in KNOWN_OPTIONS_POLITICIANS:
        words_p = set(_normalize_name(pol).split())
        if words_p <= words_n:
            return True
    return False


def detect_options_signals(
    options_df: pd.DataFrame,
    seen: set,
    current_prices: dict,
    lookback_days: int = OPTIONS_LOOKBACK,
    max_age_days: int = MAX_SIGNAL_AGE,
) -> list[dict]:
    """
    Find deep-ITM call purchases by known options-active politicians.
    Generates a signal to buy the underlying stock.

    options_df:     loaded from congress_options.csv (House only — Senate = Tuberville straddles)
    current_prices: dict of ticker -> current price for moneyness check
    max_age_days:   skip signals older than this many days (avoids stale entries on first run).
    """
    today  = pd.Timestamp.today().normalize()
    cutoff = today - pd.Timedelta(days=lookback_days)
    fresh  = today - pd.Timedelta(days=max_age_days)

    candidates = options_df[
        (options_df["transaction"] == "Purchase") &
        (options_df["option_type"] == "Call") &
        (options_df["filing_date"] >= cutoff) &
        (options_df["filing_date"] >= fresh)
    ]

    signals = []
    for _, row in candidates.iterrows():
        name   = str(row["name"])
        ticker = str(row["ticker"])

        if not _matches_options_politician(name):
            continue

        if _is_low_conviction(str(row.get("amount_range", ""))):
            continue

        # Skip if strike unknown — can't verify ITM without it.
        # Moneyness is checked against today's price (current_prices), not the
        # filing-date price. This means a call filed 20 days ago is re-evaluated
        # against today's stock level, which is a current-state filter rather than
        # a replay of the original signal condition.
        strike = row.get("strike")
        if not pd.notna(strike):
            continue
        if ticker not in current_prices:
            continue
        # NOTE: moneyness is evaluated against TODAY's price, not the filing-date price.
        # A signal filed 20 days ago is re-checked against today's stock level. This means
        # a call that was ITM at filing may be filtered out if the stock has since dropped,
        # and vice versa. It's a current-state filter, not a replay of the original condition.
        moneyness = float(strike) / current_prices[ticker]
        if moneyness >= DEEP_ITM_THRESHOLD:
            continue   # not deep enough ITM at current price

        # Unique key (OPT_ prefix distinguishes from stock signal keys)
        filed  = row["filing_date"]
        key    = f"OPT_{ticker}_{filed.date()}_{name}"
        if key in seen:
            continue

        tx_date = row.get("transaction_date")
        signals.append({
            "ticker":      ticker,
            "politician":  name,
            "report_date": str(filed.date()),
            "tx_date":     str(tx_date.date()) if pd.notna(tx_date) else str(filed.date()),
            "range":       str(row.get("amount_range", "?")),
            "signal_key":  key,
            "source":      "options",
            "hold_days":   OPTIONS_HOLD_DAYS,
            "politicians": [name],
            "accumulation": False,
            "strike":      float(strike) if pd.notna(strike) else None,
            "expiry":      str(row["expiration"].date()) if pd.notna(row.get("expiration")) else None,
        })

    return signals
