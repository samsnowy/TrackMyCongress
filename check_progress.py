"""
Quick summary of House scrape progress.
Usage: python check_progress.py
"""

import os
import pandas as pd


def main():
    path = "congress_historical.csv"
    if not os.path.exists(path):
        print(f"{path} not found. Run: python -m congress.scraper")
        return

    df = pd.read_csv(path)
    print(f"Trades:          {len(df):,}")
    print(f"Filings:         {df['doc_id'].nunique():,}")
    print(f"Unique tickers:  {df['ticker'].nunique():,}")
    print(f"Date range:      {df['transaction_date'].min()} to {df['transaction_date'].max()}")
    print(f"Transactions:    {df['transaction'].value_counts().to_dict()}")


if __name__ == "__main__":
    main()
