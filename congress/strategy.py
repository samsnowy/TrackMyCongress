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
import hashlib
from collections import defaultdict
from datetime import date, datetime, timedelta

import pandas as pd

from config import (
    HOLD_DAYS, OPTIONS_HOLD_DAYS, MAX_POSITIONS, POSITION_SIZE_PCT,
    MAX_SIGNALS_PER_FILING_BATCH,
    SIGNAL_LOOKBACK, OPTIONS_LOOKBACK, DEEP_ITM_THRESHOLD,
    RELIABLE_MIN_EXCESS, RELIABLE_MIN_TRADES, MAX_SIGNAL_AGE,
)
from data.fetcher import clean_ticker_symbol

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
        ticker = clean_ticker_symbol(row["Ticker"])
        if not ticker:
            continue
        key = f"{ticker}_{row['ReportDate'].date()}_{row['Representative']}"
        if key in seen:
            continue
        signals.append({
            "ticker":      ticker,
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
        politicians = list(dict.fromkeys(s["politician"] for s in group))
        lead["politicians"] = politicians
        lead["accumulation"] = len(politicians) > 1
        deduped.append(lead)

    return deduped


def all_signal_keys_for_ticker(signals: list[dict], ticker: str) -> set:
    """Return every signal_key for a given ticker from a raw signals list."""
    return {s["signal_key"] for s in signals if s["ticker"] == ticker}


def _amount_floor(range_str: str) -> int:
    """Return the disclosed range's lower bound for deterministic ranking."""
    match = re.search(r"\$?([\d,]+)", str(range_str))
    return int(match.group(1).replace(",", "")) if match else 0


def rank_signals(signals: list[dict], reliable_pols: dict[str, dict]) -> list[dict]:
    """Rank capacity-constrained signals using transparent evidence tiers.

    Priority is lexicographic rather than a fitted score: independent accumulation,
    curated deep-ITM option signals, politician backtest strength, disclosed size,
    filing and transaction recency. Signals from one politician/report batch are
    capped so a bulk filing cannot consume the portfolio. Fully tied candidates use
    a stable hash draw rather than ticker alphabetization. Each returned signal
    includes the components so live output can explain why it was ordered there.
    """
    ranked = []
    for signal in signals:
        item = dict(signal)
        politicians = item.get("politicians") or [item.get("politician", "")]
        unique_politicians = {str(name) for name in politicians if name}
        excess_values = []
        for name in unique_politicians:
            words = set(_normalize_name(name).split())
            for reliable_name, profile in reliable_pols.items():
                reliable_words = set(_normalize_name(reliable_name).split())
                if reliable_words <= words or words <= reliable_words:
                    excess_values.append(float(profile.get("avg_excess", 0)))
                    break
        report_date = str(item.get("report_date", ""))
        try:
            report_ordinal = datetime.strptime(report_date, "%Y-%m-%d").date().toordinal()
        except ValueError:
            report_ordinal = 0
        tx_date = str(item.get("tx_date", ""))
        try:
            tx_ordinal = datetime.strptime(tx_date, "%Y-%m-%d").date().toordinal()
        except ValueError:
            tx_ordinal = 0
        batch_key = "|".join(
            [str(item.get("source", "stock")), report_date, *sorted(unique_politicians)]
        )
        neutral_draw = int.from_bytes(
            hashlib.sha256(f"{batch_key}|{item.get('ticker', '')}".encode()).digest()[:8],
            "big",
        )
        components = {
            "politician_count": len(unique_politicians),
            "options": item.get("source") == "options",
            "max_avg_excess": max(excess_values, default=0.0),
            "amount_floor": _amount_floor(item.get("range", "")),
            "report_date": report_date,
            "report_ordinal": report_ordinal,
            "tx_date": tx_date,
            "tx_ordinal": tx_ordinal,
            "batch_key": batch_key,
            "neutral_draw": neutral_draw,
        }
        item["rank"] = components
        ranked.append(item)

    ranked = sorted(
        ranked,
        key=lambda item: (
            -item["rank"]["politician_count"],
            -int(item["rank"]["options"]),
            -item["rank"]["max_avg_excess"],
            -item["rank"]["amount_floor"],
            -item["rank"]["report_ordinal"],
            -item["rank"]["tx_ordinal"],
            -item["rank"]["neutral_draw"],
        ),
    )

    batch_counts: dict[str, int] = defaultdict(int)
    for item in ranked:
        batch_key = item["rank"]["batch_key"]
        selected = batch_counts[batch_key] < MAX_SIGNALS_PER_FILING_BATCH
        item["rank"]["batch_selected"] = selected
        if selected:
            batch_counts[batch_key] += 1
    return ranked


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
        ticker = clean_ticker_symbol(row["ticker"])
        if not ticker:
            continue

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
