"""
Run both House and Senate PTR scrapers in sequence.

Usage:
  python -m congress.scrape_all                # full run (stocks + options)
  python -m congress.scrape_all --options-only # re-parse options only
"""

import sys
from congress.scraper import scrape_all as scrape_house
from congress.senate_scraper import scrape_all as scrape_senate

opts_only = "--options-only" in sys.argv

print("=" * 55)
print("  House PTR Scraper")
print("=" * 55)
scrape_house(options_only=opts_only)

print()
print("=" * 55)
print("  Senate PTR Scraper")
print("=" * 55)
scrape_senate(options_only=opts_only)

print("\nAll done.")
