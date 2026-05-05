"""
Scrapes Senate PTR (Periodic Transaction Report) filings from efdsearch.senate.gov.

Process:
  1. Accept terms of service (POST with CSRF token) to establish session
  2. Paginate through all PTR filings via JSON API
  3. For each filing: fetch HTML report page, parse transaction table
     (PDF filings fall back to pdfplumber — same logic as house scraper)
  4. Save incrementally to senate_historical.csv + senate_options.csv

Usage:
  python -m congress.senate_scraper
  python -m congress.senate_scraper --options-only
"""

import requests
import pdfplumber
import pandas as pd
import re
import time
import io
import os
from bs4 import BeautifulSoup

_BASE         = "https://efdsearch.senate.gov"
_HOME_URL     = f"{_BASE}/search/home/"
_SEARCH_URL   = f"{_BASE}/search/"
_DATA_URL     = f"{_BASE}/search/report/data/"
_OUT_FILE     = "senate_historical.csv"
_OPTIONS_FILE = "senate_options.csv"
_DELAY        = 0.5
_BATCH        = 100
_PTR_TYPE     = 11      # report_types value for Periodic Transaction Reports
_YEARS_START  = "01/01/2022 00:00:00"

_HEADERS = {
    "User-Agent": "TrackMyCongress/1.0 (research; public STOCK Act data)",
    "Accept": "application/json, text/javascript, */*",
}

TRANSACTION_MAP = {
    "purchase":       "Purchase",
    "sale":           "Sale",
    "sale (full)":    "Sale",
    "sale (partial)": "Sale (Partial)",
    "exchange":       "Exchange",
}


# ── session ──────────────────────────────────────────────────────────────────

def _make_session() -> requests.Session:
    """Establish an authenticated session by agreeing to the ToS."""
    s = requests.Session()
    s.headers.update(_HEADERS)

    # 1. GET home page to obtain CSRF token
    r = s.get(_HOME_URL, timeout=15)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    csrf_input = soup.find("input", {"name": "csrfmiddlewaretoken"})
    if not csrf_input:
        raise RuntimeError("Could not find CSRF token on Senate home page")
    csrf = csrf_input["value"]

    # 2. POST agreement to unlock search
    r = s.post(
        _HOME_URL,
        data={"csrfmiddlewaretoken": csrf, "prohibition_agreement": "1"},
        headers={"Referer": _HOME_URL},
        timeout=15,
    )
    r.raise_for_status()
    return s


# ── filing index ──────────────────────────────────────────────────────────────

def _get_filing_index(session: requests.Session) -> list[dict]:
    """Paginate through all PTR filings and return metadata list."""
    filings = []
    start = 0

    # Get CSRF from the search page cookie for POST headers
    csrf = session.cookies.get("csrftoken") or session.cookies.get("csrf", "")

    while True:
        payload = {
            "start":                start,
            "length":               _BATCH,
            "report_types":         f"[{_PTR_TYPE}]",
            "filer_types":          "[]",
            "submitted_start_date": _YEARS_START,
            "submitted_end_date":   "",
            "candidate_state":      "",
            "senator_state":        "",
            "office_id":            "",
            "first_name":           "",
            "last_name":            "",
            "csrfmiddlewaretoken":  csrf,
        }
        r = session.post(
            _DATA_URL,
            data=payload,
            headers={"Referer": _SEARCH_URL},
            timeout=20,
        )
        r.raise_for_status()
        resp = r.json()

        rows = resp.get("data", [])
        if not rows:
            break

        for row in rows:
            # row: [first, last, "Last, First (Senator)", link_html, filing_date]
            first       = row[0]
            last        = row[1]
            filing_date = row[4]
            link_html   = row[3]

            href = re.search(r'href="([^"]+)"', link_html)
            if not href:
                continue
            href = href.group(1)

            doc_id = href.strip("/").split("/")[-1]

            # All PTR links go to /view/ptr/{uuid}/ — try HTML first, PDF fallback
            filing_type = "pdf" if "/view/paper/" in href else "html"

            filings.append({
                "name":         f"{first} {last}".strip(),
                "state_dst":    "SEN",   # Senate — no state in API response
                "doc_id":       doc_id,
                "filing_date":  filing_date,
                "filing_type":  filing_type,
                "url":          f"{_BASE}{href}",
            })

        total = resp.get("recordsFiltered", 0)
        start += _BATCH
        if start >= total:
            break

        time.sleep(_DELAY)

    return filings


# ── HTML report parser ────────────────────────────────────────────────────────

def _parse_html_report(html: str, filing_meta: dict) -> tuple[list[dict], list[dict]]:
    """Parse a Senate electronic PTR HTML page into stock and option trades."""
    stocks  = []
    options = []
    soup    = BeautifulSoup(html, "html.parser")

    # Transaction table has id="ptr-table" or is the first table in main content
    table = soup.find("table", {"id": "ptr-table"}) or soup.find("table")
    if not table:
        return stocks, options

    rows = table.find_all("tr")
    for row in rows[1:]:   # skip header
        cols = [td.get_text(strip=True) for td in row.find_all("td")]
        # cols: [#, tx_date, owner, ticker, asset_name, asset_type, type, amount, comment]
        if len(cols) < 8:
            continue

        tx_date     = cols[1]
        owner       = cols[2]
        ticker      = cols[3].upper()
        asset_desc  = cols[4]
        asset_type  = cols[5].lower()
        tx_type     = cols[6].lower()
        amount      = cols[7]
        comment     = cols[8] if len(cols) > 8 else ""

        if not re.match(r"\d{2}/\d{2}/\d{4}", tx_date):
            continue

        tx_mapped = TRANSACTION_MAP.get(tx_type, tx_type.title())

        base = {
            "name":              filing_meta["name"],
            "state_dst":         filing_meta["state_dst"],
            "doc_id":            filing_meta["doc_id"],
            "filing_date":       filing_meta["filing_date"],
            "owner":             owner,
            "company":           asset_desc,
            "ticker":            ticker if ticker != "--" else "",
            "transaction":       tx_mapped,
            "transaction_date":  tx_date,
            "notification_date": "",
            "amount_range":      amount,
        }

        if "option" in asset_type:
            from congress.scraper import _parse_option_details
            details = _parse_option_details(comment + " " + asset_desc)
            options.append({
                **base,
                "option_type": details["option_type"],
                "contracts":   details["contracts"],
                "strike":      details["strike"],
                "expiration":  details["expiration"],
                "footnote":    comment,
            })
        else:
            stocks.append(base)

    return stocks, options


# ── PDF fallback ──────────────────────────────────────────────────────────────

def _parse_pdf_report(pdf_url: str, filing_meta: dict, session: requests.Session) -> tuple[list[dict], list[dict]]:
    """Download and parse a PDF PTR — reuses House scraper logic."""
    from congress.scraper import _parse_ptr_pdf
    try:
        r = session.get(pdf_url, timeout=15)
        if r.status_code != 200:
            return [], []
        return _parse_ptr_pdf(r.content, filing_meta)
    except Exception as e:
        print(f"  [warn] PDF parse failed for {pdf_url}: {e}")
        return [], []


# ── main scrape loop ──────────────────────────────────────────────────────────

def _append_to_csv(trades: list[dict], path: str) -> None:
    if not trades:
        return
    df = pd.DataFrame(trades)
    write_header = not os.path.exists(path)
    df.to_csv(path, mode="a", header=write_header, index=False)


def scrape_all(options_only: bool = False) -> None:
    processed_ids: set[str] = set()
    if options_only:
        if os.path.exists(_OPTIONS_FILE):
            existing = pd.read_csv(_OPTIONS_FILE, usecols=["doc_id"], dtype=str)
            processed_ids = set(existing["doc_id"].dropna().unique())
            print(f"  Options mode — resuming from {len(processed_ids)} parsed filings")
    else:
        for path in (_OUT_FILE, _OPTIONS_FILE):
            if os.path.exists(path):
                existing = pd.read_csv(path, usecols=["doc_id"], dtype=str)
                processed_ids.update(existing["doc_id"].dropna().unique())
        if processed_ids:
            print(f"  Resuming — {len(processed_ids)} doc_ids already processed")

    print("Establishing Senate session...")
    session = _make_session()

    print("Fetching PTR filing index...")
    filings = _get_filing_index(session)
    print(f"  {len(filings)} PTR filings found since {_YEARS_START[:10]}")

    all_stocks:  list[dict] = []
    all_options: list[dict] = []
    new_count = 0

    for i, filing in enumerate(filings):
        doc_id = filing["doc_id"]
        if doc_id in processed_ids:
            break  # API returns newest-first; first known = all subsequent known

        try:
            if filing["filing_type"] == "html":
                r = session.get(filing["url"], timeout=15)
                if r.status_code != 200:
                    continue
                stocks, opts = _parse_html_report(r.text, filing)
            else:
                stocks, opts = _parse_pdf_report(filing["url"], filing, session)

            if not options_only:
                all_stocks.extend(stocks)
            all_options.extend(opts)
            processed_ids.add(doc_id)
            new_count += 1

            if new_count % 50 == 0:
                if not options_only:
                    _append_to_csv(all_stocks, _OUT_FILE)
                _append_to_csv(all_options, _OPTIONS_FILE)
                print(f"  {i+1}/{len(filings)} filings | "
                      f"{'' if options_only else f'{len(all_stocks)} stocks, '}"
                      f"{len(all_options)} options saved...")
                all_stocks  = []
                all_options = []

            time.sleep(_DELAY)

        except Exception as e:
            print(f"  SKIP {doc_id}: {e}")
            continue

    # Flush remainder
    if not options_only:
        _append_to_csv(all_stocks, _OUT_FILE)
    _append_to_csv(all_options, _OPTIONS_FILE)
    print(f"\nDone. {new_count} new filings processed.")
    print(f"Stocks: {_OUT_FILE} | Options: {_OPTIONS_FILE}")


def load_historical() -> pd.DataFrame:
    """Load the full Senate historical dataset."""
    if not os.path.exists(_OUT_FILE):
        raise FileNotFoundError(
            f"{_OUT_FILE} not found. Run:\n  python -m congress.senate_scraper"
        )
    df = pd.read_csv(_OUT_FILE)
    df["transaction_date"] = pd.to_datetime(df["transaction_date"], format="%m/%d/%Y", errors="coerce")
    df["filing_date"]      = pd.to_datetime(df["filing_date"], errors="coerce")
    df["disclosure_lag_days"] = (df["filing_date"] - df["transaction_date"]).dt.days
    return df.dropna(subset=["ticker", "transaction_date"]).reset_index(drop=True)


if __name__ == "__main__":
    import sys
    opts_only = "--options-only" in sys.argv
    print("Senate PTR Scraper — fetching all PTR filings since 2022")
    if opts_only:
        print("Mode: options only")
    print("Safe to Ctrl+C and resume later.\n")
    scrape_all(options_only=opts_only)
