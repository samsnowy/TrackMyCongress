"""
Scrapes all House PTR (Periodic Transaction Report) filings from the official
House clerk website: disclosures-clerk.house.gov

Process:
  1. Download the annual filing index XML for each year (free, official)
  2. Filter to PTR filings (FilingType == 'P') — these are stock trade reports
  3. For each PTR, download the PDF and parse the transaction table
  4. Save incrementally to congress_historical.csv

Run once to build the dataset, then it resumes from where it left off.
Usage: python -m congress.scraper
"""

import requests
import pdfplumber
import pandas as pd
import defusedxml.ElementTree as ET
import zipfile
import io
import re
import time
import os

_HEADERS   = {"User-Agent": "TrackMyCongress/1.0 (research; public STOCK Act data)"}
_OUT_FILE      = "congress_historical.csv"
_OPTIONS_FILE  = "congress_options.csv"
_YEARS         = [2022, 2023, 2024, 2025, 2026]
_DELAY         = 0.3   # seconds between PDF requests — be polite to the server

TRANSACTION_MAP = {
    "P": "Purchase",
    "S": "Sale",
    "S (partial)": "Sale (Partial)",
    "E": "Exchange",
    "O": "Other",
}


def _get_filing_index(year: int) -> list[dict]:
    """Download and parse the annual PTR filing index for a given year."""
    url = f"https://disclosures-clerk.house.gov/public_disc/financial-pdfs/{year}FD.zip"
    r = requests.get(url, headers=_HEADERS, timeout=20)
    r.raise_for_status()

    z = zipfile.ZipFile(io.BytesIO(r.content))
    with z.open(f"{year}FD.xml") as f:
        tree = ET.parse(f)
    root = tree.getroot()

    ptrs = []
    for member in root:
        filing_type = member.findtext("FilingType", "")
        if filing_type != "P":
            continue
        first = member.findtext("First", "")
        last  = member.findtext("Last", "")
        ptrs.append({
            "year":        year,
            "name":        f"{first} {last}".strip(),
            "state_dst":   member.findtext("StateDst", ""),
            "filing_date": member.findtext("FilingDate", ""),
            "doc_id":      member.findtext("DocID", ""),
        })
    return ptrs


def _parse_option_details(text: str) -> dict:
    """
    Extract option_type, strike, expiration, contracts from footnote text.
    Footnote example: "Purchased 50 call options with a strike price of $200
                       and an expiration date of 1/17/25."
    """
    t = text.lower()

    option_type = None
    if "call" in t:
        option_type = "Call"
    elif "put" in t:
        option_type = "Put"

    # Number of contracts: "50 call options", "purchased 20 call"
    contracts = None
    c_match = re.search(r"(\d+)\s+(?:call|put)\s+option", t)
    if c_match:
        contracts = int(c_match.group(1))

    # Strike price: "strike price of $200", "strike price $145", "$145; expires"
    strike = None
    s_match = re.search(r"strike\s+(?:price\s+)?(?:of\s+)?\$\s*(\d+(?:\.\d+)?)", t)
    if not s_match:
        # fallback: dollar amount followed by semicolon or "strike" or "exp"
        s_match = re.search(r"\$\s*(\d+(?:\.\d+)?)\s*(?:;|\bstrike\b|\bexp)", t)
    if s_match:
        strike = float(s_match.group(1))

    # Expiration: "expiration date of 1/17/25", "1/16/26", "Jan 2026"
    expiration = None
    e_match = re.search(r"expiration\s+(?:date\s+of\s+)?(\d{1,2}/\d{1,2}/\d{2,4}|\d{1,2}/\d{4})", t)
    if e_match:
        expiration = e_match.group(1)
    else:
        e_match2 = re.search(r"\b(\d{1,2}/\d{1,2}/\d{2,4}|\d{1,2}/\d{4})\b", t)
        if e_match2:
            expiration = e_match2.group(1)

    return {
        "option_type": option_type,
        "contracts":   contracts,
        "strike":      strike,
        "expiration":  expiration,
    }


def _parse_ptr_pdf(pdf_bytes: bytes, filing_meta: dict) -> tuple[list[dict], list[dict]]:
    """
    Extract stock and option transactions from a PTR PDF.
    Options use a multi-row structure: main row has ticker/date/amount,
    subsequent footnote rows (possibly spanning pages) have call/put/strike/expiry.
    Flattens all rows across all pages before processing so pending state
    carries across page boundaries.
    Returns (stock_trades, option_trades).
    """
    stocks  = []
    options = []

    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            # Flatten all rows from all pages into one sequence
            all_rows = []
            for page in pdf.pages:
                for table in page.extract_tables():
                    for row in table:
                        if row:
                            all_rows.append([str(c).strip() if c else "" for c in row])

        pending_option: dict | None = None

        for clean in all_rows:
            date_col = clean[4] if len(clean) > 4 else ""
            has_date = bool(re.match(r"\d{2}/\d{2}/\d{4}", date_col))

            # Accumulate footnote rows for a pending option
            if pending_option is not None:
                if has_date:
                    # New transaction row — flush pending option first
                    options.append(pending_option)
                    pending_option = None
                    # fall through to process this row
                else:
                    # Gather text from all columns — description may span any cell
                    all_text = " ".join(c for c in clean if c)
                    if all_text:
                        accumulated = (pending_option["footnote"] + " " + all_text).strip()
                        pending_option["footnote"] = accumulated.replace("\n", " ")
                        details = _parse_option_details(accumulated)
                        if details["option_type"] or details["strike"] or details["expiration"]:
                            pending_option.update(details)
                    continue

            if len(clean) < 6 or not has_date:
                continue

            owner      = clean[1] if len(clean) > 1 else ""
            asset      = clean[2] if len(clean) > 2 else ""
            tx_type    = clean[3] if len(clean) > 3 else ""
            notif_date = clean[5] if len(clean) > 5 else ""
            amount     = clean[6] if len(clean) > 6 else ""

            if tx_type not in ("P", "S", "S (partial)", "E"):
                continue

            ticker_match = re.search(
                r"\(([A-Z]{1,5}(?:\.[A-Z])?)\)\s*\[(ST|OP)\]", asset
            )
            if not ticker_match:
                continue
            ticker     = ticker_match.group(1)
            asset_code = ticker_match.group(2)
            company    = re.sub(r"\s*\([A-Z.]+\)\s*\[.*?\].*", "", asset).strip()

            base = {
                "name":              filing_meta["name"],
                "state_dst":         filing_meta["state_dst"],
                "doc_id":            filing_meta["doc_id"],
                "filing_date":       filing_meta["filing_date"],
                "owner":             owner,
                "company":           company,
                "ticker":            ticker,
                "transaction":       TRANSACTION_MAP.get(tx_type, tx_type),
                "transaction_date":  date_col,
                "notification_date": notif_date,
                "amount_range":      amount.replace("\n", " ").strip(),
            }

            if asset_code == "ST":
                stocks.append(base)
            else:
                # Check if details are already embedded in the asset cell (merged rows)
                details = _parse_option_details(asset)
                pending_option = {
                    **base,
                    "option_type": details["option_type"],
                    "contracts":   details["contracts"],
                    "strike":      details["strike"],
                    "expiration":  details["expiration"],
                    "footnote":    asset.replace("\n", " "),
                }

        if pending_option is not None:
            options.append(pending_option)

    except Exception as e:
        print(f"  [warn] PDF parse failed: {e}")

    return stocks, options


def scrape_all(
    years: list[int] = _YEARS,
    max_per_year: int | None = None,
    options_only: bool = False,
) -> pd.DataFrame:
    """
    Download and parse all PTR filings for the given years.
    options_only=False (default): skips doc_ids in both CSVs, writes both.
    options_only=True: only deduplicates against congress_options.csv so every
        PDF is re-downloaded and re-parsed; writes only options (stocks skipped).
        Use this to build congress_options.csv without re-scraping stocks.
    """
    processed_ids: set[str] = set()
    if options_only:
        if os.path.exists(_OPTIONS_FILE):
            existing_opts = pd.read_csv(_OPTIONS_FILE, usecols=["doc_id"], dtype=str)
            processed_ids = set(existing_opts["doc_id"].dropna().unique())
            print(f"  Options mode — resuming from {len(processed_ids)} already-parsed option filings")
        else:
            print("  Options mode — building congress_options.csv from scratch")
    else:
        if os.path.exists(_OUT_FILE):
            existing = pd.read_csv(_OUT_FILE, usecols=["doc_id"], dtype=str)
            processed_ids = set(existing["doc_id"].dropna().unique())
        if os.path.exists(_OPTIONS_FILE):
            existing_opts = pd.read_csv(_OPTIONS_FILE, usecols=["doc_id"], dtype=str)
            processed_ids.update(existing_opts["doc_id"].dropna().unique())
        if processed_ids:
            print(f"  Resuming — {len(processed_ids)} doc_ids already processed")

    all_stocks:  list[dict] = []
    all_options: list[dict] = []

    for year in years:
        print(f"\n[{year}] Fetching filing index...")
        try:
            filings = _get_filing_index(year)
        except Exception as e:
            print(f"  ERROR fetching index: {e}")
            continue

        print(f"  {len(filings)} PTR filings found")
        if max_per_year:
            filings = filings[:max_per_year]

        new_count = 0
        for i, filing in enumerate(filings):
            doc_id = filing["doc_id"]
            if doc_id in processed_ids:
                continue

            url = f"https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/{year}/{doc_id}.pdf"
            try:
                r = requests.get(url, headers=_HEADERS, timeout=15)
                if r.status_code != 200:
                    continue
                stocks, options = _parse_ptr_pdf(r.content, filing)
                if not options_only:
                    all_stocks.extend(stocks)
                all_options.extend(options)
                processed_ids.add(doc_id)
                new_count += 1

                if new_count % 50 == 0:
                    if not options_only:
                        _append_to_csv(all_stocks, _OUT_FILE)
                    _append_to_csv(all_options, _OPTIONS_FILE)
                    print(f"  [{year}] {i+1}/{len(filings)} filings | "
                          f"{'' if options_only else f'{len(all_stocks)} stocks, '}"
                          f"{len(all_options)} options saved...")
                    all_stocks  = []
                    all_options = []

                time.sleep(_DELAY)

            except Exception as e:
                print(f"  SKIP {doc_id}: {e}")
                continue

        if all_stocks or all_options:
            if not options_only:
                _append_to_csv(all_stocks, _OUT_FILE)
            _append_to_csv(all_options, _OPTIONS_FILE)
            print(f"  [{year}] Done — {new_count} new filings processed")
            all_stocks  = []
            all_options = []

    print(f"\nComplete. Stocks → {_OUT_FILE} | Options → {_OPTIONS_FILE}")
    if options_only or not os.path.exists(_OUT_FILE):
        return pd.DataFrame()
    return pd.read_csv(_OUT_FILE)


def _append_to_csv(trades: list[dict], path: str) -> None:
    if not trades:
        return
    df = pd.DataFrame(trades)
    write_header = not os.path.exists(path)
    df.to_csv(path, mode="a", header=write_header, index=False)


def load_historical() -> pd.DataFrame:
    """Load the full historical dataset. Run scrape_all() first to build it."""
    if not os.path.exists(_OUT_FILE):
        raise FileNotFoundError(
            f"{_OUT_FILE} not found. Run:\n"
            "  python -m congress.scraper\n"
            "to download and parse all House PTR filings."
        )
    df = pd.read_csv(_OUT_FILE)
    df["transaction_date"]    = pd.to_datetime(df["transaction_date"],    format="%m/%d/%Y", errors="coerce")
    df["notification_date"]   = pd.to_datetime(df["notification_date"],   format="%m/%d/%Y", errors="coerce")
    df["filing_date"]         = pd.to_datetime(df["filing_date"],         errors="coerce")
    df["disclosure_lag_days"] = (df["notification_date"] - df["transaction_date"]).dt.days
    return df.dropna(subset=["ticker", "transaction_date"]).reset_index(drop=True)


if __name__ == "__main__":
    import sys as _sys
    opts_only = "--options-only" in _sys.argv
    print("House PTR Scraper — fetching all PTR filings 2022–2026")
    if opts_only:
        print("Mode: options only (re-parses all PDFs, writes congress_options.csv)")
    print("This will take ~10–15 minutes. Safe to Ctrl+C and resume later.\n")
    df = scrape_all(years=_YEARS, options_only=opts_only)
    print(f"\nStocks ({_OUT_FILE}):")
    print(f"  Total trades:    {len(df):,}")
    print(f"  Unique tickers:  {df['ticker'].nunique():,}")
    print(f"  Unique reps:     {df['name'].nunique():,}")
    print(f"  Date range:      {df['transaction_date'].min()} to {df['transaction_date'].max()}")
    print(f"  Purchases:       {(df['transaction'] == 'Purchase').sum():,}")
    print(f"  Sales:           {(df['transaction'].str.contains('Sale', regex=False)).sum():,}")
    if os.path.exists(_OPTIONS_FILE):
        opts = pd.read_csv(_OPTIONS_FILE)
        print(f"\nOptions ({_OPTIONS_FILE}):")
        print(f"  Total:           {len(opts):,}")
        print(f"  Calls:           {(opts['option_type'] == 'Call').sum():,}")
        print(f"  Puts:            {(opts['option_type'] == 'Put').sum():,}")
        print(f"  Unknown type:    {opts['option_type'].isna().sum():,}")
        print(f"  Unique tickers:  {opts['ticker'].nunique():,}")
