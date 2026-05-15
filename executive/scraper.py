"""
Scrape executive branch OGE Form 278-T PDFs into executive_trades.csv.

OGE disclosures are less structured than House/Senate PTRs. This scraper takes
known OGE PDF URLs, parses transaction rows, infers stock tickers when possible,
and writes the normalized display-only CSV consumed by executive.loader.

Usage:
  python -m executive.scraper --url <OGE_PDF_URL> --name "Donald J. Trump" --role President --agency "Executive Office of the President"
  python -m executive.scraper --urls-file oge_urls.txt --name "Donald J. Trump" --role President
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from html import unescape
from urllib.parse import urljoin
from urllib.parse import urlparse

import pandas as pd
import pdfplumber
import requests
from bs4 import BeautifulSoup

from executive.loader import EXECUTIVE_TRADES_CSV


_HEADERS = {"User-Agent": "TrackMyCongress/1.0 (research; public OGE disclosure data)"}
_DELAY = 0.5
_OGE_API_URL = "https://extapps2.oge.gov/201/Presiden.nsf/API.xsp/v2/rest"
_OGE_COLUMNS = ["docDate", "title", "type", "name", "agency", "level"]
_SCRAPE_STATE_JSON = "executive_scrape_state.json"

_ALIASES = {
    "ADOBE": "ADBE",
    "ADOBE INC": "ADBE",
    "ADVANCED MICRO DEVICES": "AMD",
    "ALPHABET": "GOOGL",
    "AMAZON": "AMZN",
    "AMAZON.COM": "AMZN",
    "APPLE": "AAPL",
    "APPLE INC": "AAPL",
    "BROADCOM": "AVGO",
    "CADENCE": "CDNS",
    "CADENCE DESIGN": "CDNS",
    "DELL": "DELL",
    "DELL TECHNOLOGIES": "DELL",
    "INTEL": "INTC",
    "INTEL CORP": "INTC",
    "META": "META",
    "META PLATFORMS": "META",
    "MICROSOFT": "MSFT",
    "MICROSOFT CORP": "MSFT",
    "NVIDIA": "NVDA",
    "NVIDIA CORP": "NVDA",
    "ORACLE": "ORCL",
    "ORACLE CORP": "ORCL",
    "PALANTIR": "PLTR",
    "ROBINHOOD": "HOOD",
    "SERVICENOW": "NOW",
    "SYNOPSYS": "SNPS",
    "TEXAS INSTRUMENTS": "TXN",
    "WORKDAY": "WDAY",
}


@dataclass
class Filer:
    name: str
    role: str = ""
    agency: str = ""


@dataclass
class DisclosureRecord:
    url: str
    filer: Filer
    doc_date: str = ""


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").replace("\n", " ")).strip()


def _infer_ticker(description: str, ticker_map: dict[str, str] | None = None) -> str | None:
    desc = _clean(description).upper()

    match = re.search(r"\(([A-Z]{1,5}(?:\.[A-Z])?)\)", desc)
    if match:
        return match.group(1)

    ticker_map = ticker_map or {}
    for key, ticker in {**_ALIASES, **ticker_map}.items():
        if key.upper() in desc:
            return ticker.upper()

    return None


def _load_ticker_map(path: str | None) -> dict[str, str]:
    if not path:
        return {}
    df = pd.read_csv(path)
    if not {"pattern", "ticker"}.issubset(df.columns):
        raise ValueError("ticker map must have columns: pattern,ticker")
    return {
        str(row["pattern"]).upper(): str(row["ticker"]).upper()
        for _, row in df.dropna(subset=["pattern", "ticker"]).iterrows()
    }


def _parse_row_from_cells(cells: list[str]) -> dict | None:
    cells = [_clean(c) for c in cells if _clean(c)]
    if len(cells) < 4:
        return None

    date_idx = next((i for i, c in enumerate(cells) if re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}", c)), None)
    if date_idx is None or date_idx < 2:
        return None

    tx_type = cells[date_idx - 1].lower()
    if not any(word in tx_type for word in ("purchase", "sale", "exchange")):
        return None

    description = " ".join(cells[1:date_idx - 1]) if cells[0].isdigit() else " ".join(cells[:date_idx - 1])
    amount = next((c for c in cells[date_idx + 1:] if "$" in c), "")

    return {
        "description": description,
        "transaction": "Purchase" if "purchase" in tx_type else "Sale" if "sale" in tx_type else "Exchange",
        "transaction_date": cells[date_idx],
        "amount_range": amount,
    }


def _parse_rows_from_text(text: str) -> list[dict]:
    """Parse newer Integrity.gov text-layout OGE 278-T transaction pages."""
    clean_text = text.replace("\r", "\n")
    if "DESCRIPTION" not in clean_text:
        return []
    section = clean_text
    for marker in ("Endnotes", "Summary of Contents"):
        marker_idx = section.find(marker)
        if marker_idx >= 0:
            section = section[:marker_idx]

    rows: list[dict] = []
    chunks = re.split(r"(?m)^\s*(\d+)\s+", section)
    for i in range(1, len(chunks), 2):
        raw = _clean(chunks[i + 1])
        if not raw or raw.startswith("DESCRIPTION "):
            continue

        date_match = re.search(r"\b\d{1,2}/\d{1,2}/\d{4}\b", raw)
        if not date_match:
            continue

        before_date = raw[:date_match.start()].strip()
        after_date = raw[date_match.end():].strip()
        tx_matches = list(re.finditer(r"\b(Purchase|Sale|Exchange)\b", before_date, flags=re.IGNORECASE))
        if not tx_matches:
            continue

        tx_match = tx_matches[-1]
        description = before_date[:tx_match.start()]
        description = re.sub(r"\bSee Endnote\b", "", description, flags=re.IGNORECASE)
        description = _clean(description)
        ticker_hints = re.findall(r"\(([A-Z]{1,5}(?:\.[A-Z])?)\)", after_date)
        if ticker_hints and not re.search(r"\([A-Z]{1,5}(?:\.[A-Z])?\)", description):
            description = f"{description} ({ticker_hints[0]})"
        amount = re.sub(r"^(Yes|No)\s+", "", after_date, flags=re.IGNORECASE).strip()
        amount = re.sub(r"\s*\([A-Z]{1,5}(?:\.[A-Z])?\)\s*", " ", amount)
        amount = _clean(amount)

        rows.append({
            "description": description,
            "transaction": tx_match.group(1).title(),
            "transaction_date": date_match.group(0),
            "amount_range": amount,
        })

    return rows


def parse_278t_pdf(pdf_bytes: bytes, filer: Filer, doc_url: str, ticker_map: dict[str, str] | None = None) -> list[dict]:
    rows: list[dict] = []
    seen: set[tuple[str, str, str, str]] = set()

    def add_parsed(parsed: dict) -> None:
        ticker = _infer_ticker(parsed["description"], ticker_map)
        if not ticker:
            return
        key = (ticker, parsed["transaction"], parsed["transaction_date"], parsed["amount_range"])
        if key in seen:
            return
        seen.add(key)
        rows.append({
            "name":             filer.name,
            "role":             filer.role,
            "agency":           filer.agency,
            "filing_date":      filing_date,
            "transaction_date": parsed["transaction_date"],
            "ticker":           ticker,
            "transaction":      parsed["transaction"],
            "amount_range":     parsed["amount_range"],
            "source":           "OGE",
            "doc_url":          doc_url,
        })

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        filing_date = _filing_date_from_url(doc_url)
        for page in pdf.pages:
            tables = page.extract_tables() or []
            for table in tables:
                for raw in table:
                    parsed = _parse_row_from_cells([str(c or "") for c in raw])
                    if not parsed:
                        continue
                    add_parsed(parsed)

            text = page.extract_text() or ""
            for parsed in _parse_rows_from_text(text):
                add_parsed(parsed)
    return rows


def _set_filing_date(rows: list[dict], filing_date: str) -> list[dict]:
    if not filing_date:
        return rows
    for row in rows:
        row["filing_date"] = filing_date
    return rows


def _filing_date_from_url(url: str) -> str:
    path = urlparse(url).path
    match = re.search(r"(\d{1,2})[.\-](\d{1,2})[.\-](\d{4})", path)
    if not match:
        return ""
    month, day, year = match.groups()
    return f"{year}-{int(month):02d}-{int(day):02d}"


def scrape_pdf_url(url: str, filer: Filer, ticker_map: dict[str, str] | None = None) -> list[dict]:
    r = requests.get(url, headers=_HEADERS, timeout=30)
    r.raise_for_status()
    return parse_278t_pdf(r.content, filer=filer, doc_url=url, ticker_map=ticker_map)


def _data_tables_params(start: int, length: int) -> dict[str, str]:
    params = {
        "draw": "1",
        "start": str(start),
        "length": str(length),
        "search[value]": "",
        "search[regex]": "false",
        "order[0][column]": "0",
        "order[0][dir]": "desc",
    }
    for i, col in enumerate(_OGE_COLUMNS):
        params.update({
            f"columns[{i}][data]": col,
            f"columns[{i}][name]": "",
            f"columns[{i}][searchable]": "true",
            f"columns[{i}][orderable]": "true",
            f"columns[{i}][search][value]": "",
            f"columns[{i}][search][regex]": "false",
        })
    return params


def _parse_doc_date(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _extract_pdf_url(type_html: str) -> str | None:
    soup = BeautifulSoup(unescape(type_html or ""), "html.parser")
    link = soup.find("a", href=True)
    if not link:
        return None
    url = urljoin(_OGE_API_URL, link["href"])
    if "$FILE" not in url and "%24FILE" not in url and not url.lower().endswith(".pdf"):
        return None
    return url


def discover_recent_records(months: int = 6, limit: int | None = None) -> list[DisclosureRecord]:
    """Discover recent public OGE 278-T PDFs from the official OGE index API."""
    cutoff = datetime.today() - timedelta(days=months * 31)
    records: list[DisclosureRecord] = []
    seen_urls: set[str] = set()
    start = 0
    page_size = 100

    while True:
        params = _data_tables_params(start=start, length=page_size)
        r = requests.get(_OGE_API_URL, params=params, headers=_HEADERS, timeout=30)
        if r.status_code == 400:
            print(f"  [warn] OGE index stopped at offset {start}; using records discovered so far.")
            break
        r.raise_for_status()
        payload = r.json()
        page = [row for row in payload.get("data", []) if isinstance(row, dict)]
        if not page:
            break

        should_stop = False
        for row in page:
            doc_date = _parse_doc_date(row.get("docDate", ""))
            if doc_date and doc_date < cutoff:
                should_stop = True
                continue
            if "278 Transaction" not in str(row.get("type", "")):
                continue
            pdf_url = _extract_pdf_url(str(row.get("type", "")))
            if not pdf_url:
                continue
            if pdf_url in seen_urls:
                continue
            seen_urls.add(pdf_url)
            records.append(DisclosureRecord(
                url=pdf_url,
                filer=Filer(
                    name=str(row.get("name", "")).strip(),
                    role=str(row.get("title", "")).strip(),
                    agency=str(row.get("agency", "")).strip(),
                ),
                doc_date=doc_date.date().isoformat() if doc_date else "",
            ))
            if limit and len(records) >= limit:
                return records

        if should_stop:
            break
        start += page_size

    return records


def _append_deduped(rows: list[dict], out_path: str = EXECUTIVE_TRADES_CSV) -> None:
    if not rows:
        print("  No executive stock rows parsed.")
        return
    new_df = pd.DataFrame(rows)
    if os.path.exists(out_path):
        old_df = pd.read_csv(out_path)
        df = pd.concat([old_df, new_df], ignore_index=True)
    else:
        df = new_df
    key_cols = ["name", "filing_date", "transaction_date", "ticker", "transaction", "amount_range", "doc_url"]
    df = df.drop_duplicates(subset=key_cols).sort_values(["filing_date", "transaction_date"], ascending=False)
    df.to_csv(out_path, index=False)
    print(f"  Saved {len(new_df)} parsed row(s); {len(df)} total row(s) in {out_path}")


def _load_seen_urls(out_path: str, state_path: str) -> set[str]:
    seen: set[str] = set()
    if os.path.exists(state_path):
        try:
            with open(state_path, encoding="utf-8") as f:
                payload = json.load(f)
            seen.update(str(row.get("url", "")) for row in payload.get("scraped", []) if row.get("url"))
        except Exception:
            pass

    if os.path.exists(out_path):
        try:
            df = pd.read_csv(out_path, usecols=["doc_url"])
            seen.update(df["doc_url"].dropna().astype(str))
        except Exception:
            pass
    return seen


def _mark_seen(records: list[tuple[DisclosureRecord, int]], state_path: str) -> None:
    existing: dict[str, dict] = {}
    if os.path.exists(state_path):
        try:
            with open(state_path, encoding="utf-8") as f:
                payload = json.load(f)
            existing = {
                str(row.get("url")): row
                for row in payload.get("scraped", [])
                if row.get("url")
            }
        except Exception:
            existing = {}

    scraped_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for record, parsed_rows in records:
        existing[record.url] = {
            "url": record.url,
            "name": record.filer.name,
            "role": record.filer.role,
            "agency": record.filer.agency,
            "doc_date": record.doc_date,
            "parsed_rows": int(parsed_rows),
            "scraped_at": scraped_at,
        }

    payload = {"scraped": sorted(existing.values(), key=lambda row: row.get("doc_date", ""), reverse=True)}
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def _read_urls(args: argparse.Namespace) -> list[str]:
    urls = list(args.url or [])
    if args.urls_file:
        with open(args.urls_file, encoding="utf-8") as f:
            urls.extend(line.strip() for line in f if line.strip() and not line.startswith("#"))
    return urls


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape OGE 278-T PDFs into executive_trades.csv")
    parser.add_argument("--url", action="append", help="OGE 278-T PDF URL. Can be repeated.")
    parser.add_argument("--urls-file", help="Text file with one OGE PDF URL per line.")
    parser.add_argument("--recent-months", type=int, help="Discover and scrape OGE 278-T reports released in the last N months.")
    parser.add_argument("--limit", type=int, help="Optional cap on discovered PDFs to scrape.")
    parser.add_argument("--name", help="Filer name for manual --url mode, e.g. Donald J. Trump")
    parser.add_argument("--role", default="", help="Filer role, e.g. President")
    parser.add_argument("--agency", default="", help="Filer agency")
    parser.add_argument("--ticker-map", help="Optional CSV with pattern,ticker columns for ticker inference.")
    parser.add_argument("--out", default=EXECUTIVE_TRADES_CSV, help="Output CSV path.")
    parser.add_argument("--state", default=_SCRAPE_STATE_JSON, help="Local scrape state path for skipping already-seen PDFs.")
    parser.add_argument("--rescrape", action="store_true", help="Fetch PDFs even if they are already in local scrape state.")
    args = parser.parse_args()

    ticker_map = _load_ticker_map(args.ticker_map)
    records: list[DisclosureRecord] = []
    if args.recent_months:
        print(f"Discovering OGE 278-T PDFs from the last {args.recent_months} month(s)...")
        records = discover_recent_records(months=args.recent_months, limit=args.limit)
        print(f"  Found {len(records)} recent 278-T PDF(s).")
    else:
        urls = _read_urls(args)
        if not urls:
            raise SystemExit("Provide --recent-months, --url, or --urls-file")
        if not args.name:
            raise SystemExit("--name is required for manual --url/--urls-file mode")
        filer = Filer(name=args.name, role=args.role, agency=args.agency)
        records = [DisclosureRecord(url=url, filer=filer) for url in urls]

    if not args.rescrape:
        seen_urls = _load_seen_urls(args.out, args.state)
        before = len(records)
        records = [record for record in records if record.url not in seen_urls]
        skipped = before - len(records)
        if skipped:
            print(f"  Skipped {skipped} already-scraped PDF(s). Use --rescrape to force.")

    all_rows: list[dict] = []
    seen_records: list[tuple[DisclosureRecord, int]] = []

    for i, record in enumerate(records, 1):
        print(f"[{i}/{len(records)}] Fetching {record.filer.name} - {record.url}")
        try:
            rows = scrape_pdf_url(record.url, filer=record.filer, ticker_map=ticker_map)
            rows = _set_filing_date(rows, record.doc_date)
            print(f"  parsed {len(rows)} stock row(s)")
            all_rows.extend(rows)
            seen_records.append((record, len(rows)))
        except Exception as e:
            print(f"  [warn] skipped: {e}")
        time.sleep(_DELAY)

    _append_deduped(all_rows, out_path=args.out)
    if seen_records:
        _mark_seen(seen_records, args.state)
        print(f"  Updated scrape state: {args.state}")


if __name__ == "__main__":
    main()
