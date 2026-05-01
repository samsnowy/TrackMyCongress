"""
Entry point for the congress trades research tool.

  python main.py congress            — latest congress trades via Quiver Quant API
  python main.py followcongress      — backtest following politicians' disclosures
  python main.py paircongress        — match buy/sell pairs, analyse sell-lag drift
  python main.py account             — Alpaca paper account status + open positions
  python main.py live                — run live paper trading strategy
  python main.py live --dry-run      — simulate strategy without placing orders
"""

import sys


def cmd_congress():
    from congress.fetcher import (
        fetch_trades, top_politicians, top_tickers,
        disclosure_lag_stats, trades_for_politician, print_recent,
    )

    print("Fetching latest congress trades from Quiver Quant (free)...")
    df = fetch_trades()
    print(f"  {len(df)} trades loaded | {df['ReportDate'].min().date()} to {df['ReportDate'].max().date()}")

    lag = disclosure_lag_stats(df)
    print(f"\nDisclosure lag: median={lag['median_days']}d  mean={lag['mean_days']}d  "
          f"max={lag['max_days']}d  ({lag['pct_under_45']}% filed within 45 days)")

    print("\n--- Top politicians by excess return on purchases (min 3 trades) ---")
    top = top_politicians(df, min_trades=3)
    print(f"  {'Politician':<30} {'P':<2} {'Trades':>6} {'Avg ExRet':>10} {'Avg Return':>11}")
    print("  " + "-" * 65)
    for _, row in top.head(15).iterrows():
        print(f"  {row['Representative']:<30} {row['party']:<2} "
              f"{int(row['trades']):>6} "
              f"{row['avg_excess_r']:>+9.1f}% "
              f"{row['avg_return']:>+10.1f}%")

    print("\n--- Most traded tickers ---")
    tickers = top_tickers(df, min_trades=2)
    print(f"  {'Ticker':<8} {'Trades':>6} {'Buys':>5} {'Sells':>5} {'Avg ExRet':>10}")
    print("  " + "-" * 40)
    for _, row in tickers.head(15).iterrows():
        print(f"  {row['Ticker']:<8} {int(row['trades']):>6} "
              f"{int(row['purchases']):>5} {int(row['sales']):>5} "
              f"{row['avg_excess_r']:>+9.1f}%")

    lookup = input("\nLook up a specific politician? (name or enter to skip): ").strip()
    if lookup:
        person = trades_for_politician(df, lookup)
        if person.empty:
            print("  No trades found.")
        else:
            print(f"  Found {len(person)} trades for '{lookup}':")
            print_recent(person, n=20)

    print("\n--- Most recent disclosures ---")
    print_recent(df, n=15)


def cmd_followcongress():
    from congress.loader import load_for_backtest
    from congress.backtest import (
        run_politician_backtest, rank_politicians, prefetch_prices,
        simulate_group, print_rankings, print_group_result,
    )

    hold_days_raw = input("Hold days after disclosure [default 30]: ").strip()
    try:
        hold_days = int(hold_days_raw) if hold_days_raw else 30
    except ValueError:
        print("  Invalid input, using default: 30")
        hold_days = 30

    min_trades_raw = input("Min trades per politician [default 3]: ").strip()
    try:
        min_trades = int(min_trades_raw) if min_trades_raw else 3
    except ValueError:
        print("  Invalid input, using default: 3")
        min_trades = 3

    print(f"\nLoading scraped congress trades (House + Senate)...")
    df = load_for_backtest(purchases_only=True)
    print(f"  {len(df):,} purchase disclosures loaded")

    print(f"\nPrefetching prices (once)...")
    closes = prefetch_prices(df)

    print(f"\nRunning backtest (hold={hold_days}d, min_trades={min_trades})...")
    results = run_politician_backtest(df, hold_days=hold_days, min_trades=min_trades, closes=closes)

    rankings = rank_politicians(results)
    print(f"\n--- All politicians ranked by avg excess return (hold={hold_days}d) ---")
    print_rankings(rankings, hold_days)

    reliable = rankings[(rankings["avg_excess"] > 0) & (rankings["trades"] >= 5)]
    print(f"\n--- Reliable group ({len(reliable)} politicians with positive excess + 5+ trades) ---")
    group = simulate_group(results, reliable["politician"].tolist())
    print_group_result(group)

    top3 = rankings.head(3)["politician"].tolist()
    print(f"\n--- Top 3 only: {', '.join(top3)} ---")
    group3 = simulate_group(results, top3)
    print_group_result(group3)

    print(f"\n--- Holding period sensitivity (reliable group) ---")
    print(f"  {'Hold Days':>10}  {'Avg Excess':>10}  {'Win%':>6}  {'Trades':>7}")
    print("  " + "-" * 40)
    sensitivity_rows = []
    for hd in [10, 20, 30, 60, 90]:
        r2 = run_politician_backtest(df, hold_days=hd, min_trades=5, closes=closes)
        rnk2 = rank_politicians(r2)
        rel2 = rnk2[(rnk2["avg_excess"] > 0) & (rnk2["trades"] >= 5)]
        g2 = simulate_group(r2, rel2["politician"].tolist())
        if g2:
            sensitivity_rows.append({
                "hold":    hd,
                "trades":  g2["total_trades"],
                "avg_ret": round(g2["avg_trade_ret"], 1),
                "spy":     round(g2["avg_spy_ret"], 1),
                "excess":  round(g2["avg_excess"], 1),
                "win_pct": int(round(g2["win_rate"])),
            })
            print(f"  {hd:>10}d  {g2['avg_excess']:>+9.1f}%  {g2['win_rate']:>5.0f}%  {g2['total_trades']:>7}")

    from datetime import date as _date
    top12 = rankings[rankings["trades"] >= 5].sort_values("avg_excess", ascending=False).head(12)
    politicians = [
        {"name": _shorten_name(r["politician"]), "excess": round(float(r["avg_excess"]), 1), "trades": int(r["trades"])}
        for _, r in top12.iterrows()
    ]
    _write_data_js(sensitivity_rows, str(_date.today()), int(len(reliable)), politicians)

    save = input("\nSave full rankings to CSV? [y/N]: ").strip().lower()
    if save == "y":
        rankings.to_csv("congress_rankings.csv", index=False)
        print("  Saved congress_rankings.csv")


def cmd_congressoptions():
    from congress.options_analysis import run_options_analysis
    run_options_analysis()


def cmd_paircongress():
    from congress.loader import load_historical
    from congress.trade_pairs import run_pair_analysis

    print("Loading scraped congress trades (House + Senate)...")
    df = load_historical()
    print(f"  {len(df):,} trades across {df['name'].nunique()} politicians\n")
    pairs_df = run_pair_analysis(df=df)
    if pairs_df.empty:
        return
    save = input("\nSave pairs to CSV? [y/N]: ").strip().lower()
    if save == "y":
        pairs_df.to_csv("congress_pairs.csv", index=False)
        print("  Saved congress_pairs.csv")


def cmd_live():
    from congress.live import run_live
    dry_run = "--dry-run" in sys.argv
    run_live(dry_run=dry_run)


def cmd_account():
    try:
        from broker.alpaca_paper import get_account, get_positions
        acct = get_account()
        print(f"\nPaper Account")
        print(f"  Equity:         ${acct['equity']:,.2f}")
        print(f"  Cash:           ${acct['cash']:,.2f}")
        print(f"  Buying Power:   ${acct['buying_power']:,.2f}")

        positions = get_positions()
        if positions:
            print(f"\nOpen Positions ({len(positions)}):")
            for p in positions:
                print(f"  {p['ticker']:<6} qty={p['qty']} entry=${p['avg_entry']:.2f} "
                      f"current=${p['current_price']:.2f} P&L=${p['unrealized_pl']:+.2f}")
        else:
            print("\nNo open positions.")
    except Exception as e:
        print(f"Alpaca error: {e}")
        print("Make sure you've added your API keys to .env (see .env.example)")


def _shorten_name(name: str) -> str:
    """'Daniel S Sullivan' → 'Daniel Sullivan', 'Mark Dr Green' → 'Mark Green'"""
    stops = {"dr", "mr", "mrs", "ms", "jr", "sr", "rep", "sen"}
    parts = name.split()
    filtered = [
        p for p in parts
        if p.lower().rstrip(".,") not in stops
        and not (len(p.rstrip(".")) == 1 and p[0].isalpha())
    ]
    return f"{filtered[0]} {filtered[-1]}" if len(filtered) > 2 else " ".join(filtered)


def _write_data_js(sensitivity: list, generated: str, reliable_count: int, politicians: list, source: str = "followcongress") -> None:
    """Write docs/data.js from in-memory data + congress CSVs."""
    import json, os
    import pandas as pd
    from congress.strategy import match_politician

    # Curated filings — max 2 per politician, 25 total
    filings = []
    if os.path.exists("congress_trades.csv") and os.path.exists("congress_rankings.csv"):
        df_t = pd.read_csv("congress_trades.csv")
        df_t["ReportDate"] = pd.to_datetime(df_t["ReportDate"], errors="coerce")
        df_t = df_t.dropna(subset=["ReportDate", "Ticker", "Representative"])
        df_t = df_t.sort_values("ReportDate", ascending=False)

        df_r = pd.read_csv("congress_rankings.csv")
        reliable_pols = {r["politician"]: {} for _, r in df_r[df_r["avg_excess"] > 0].iterrows()}

        seen: dict[str, int] = {}
        for _, row in df_t.iterrows():
            pol = str(row["Representative"])
            if seen.get(pol, 0) >= 2:
                continue
            tx_dt  = pd.to_datetime(row.get("TransactionDate"), errors="coerce")
            amount = str(row.get("Range", ""))
            t_type = str(row.get("TickerType", "ST"))
            filings.append({
                "date":     str(row["ReportDate"].date()),
                "tx_date":  str(tx_dt.date()) if pd.notna(tx_dt) else "",
                "name":     pol,
                "party":    str(row.get("Party", "")),
                "ticker":   str(row["Ticker"]),
                "type":     t_type if t_type in ("ST", "OP") else "ST",
                "txn":      str(row.get("Transaction", "")),
                "range":    amount,
                "reliable": match_politician(pol, reliable_pols),
                "low_conv": amount.strip().startswith("$1,001"),
            })
            seen[pol] = seen.get(pol, 0) + 1
            if len(filings) >= 25:
                break

    # Total options count from scraped CSVs
    total_options = 0
    for path in ("congress_options.csv", "senate_options.csv"):
        if os.path.exists(path):
            try:
                total_options += len(pd.read_csv(path, usecols=["ticker"]))
            except Exception:
                pass

    # Total stock trades from scraped CSVs
    total_stocks = 0
    for path in ("congress_historical.csv", "senate_historical.csv"):
        if os.path.exists(path):
            try:
                total_stocks += len(pd.read_csv(path, usecols=["ticker"]))
            except Exception:
                pass

    stats_90 = next((s for s in sensitivity if s["hold"] == 90), {})
    stats = {
        "total_trades":   total_stocks,
        "total_options":  total_options,
        "reliable_count": reliable_count,
        "avg_excess_90d": stats_90.get("excess", 0),
    }

    out_path = os.path.join("docs", "data.js")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"// Generated by: python main.py {source} — do not edit manually\n\n")
        f.write(f"const DATA_GENERATED = {json.dumps(generated)};\n\n")
        f.write(f"const STATS = {json.dumps(stats, indent=2)};\n\n")
        f.write(f"const SENSITIVITY = {json.dumps(sensitivity, indent=2)};\n\n")
        f.write(f"const POLITICIANS = {json.dumps(politicians, indent=2)};\n\n")
        f.write(f"const FILINGS = {json.dumps(filings, indent=2)};\n")

    print(f"  [data.js] Written: {out_path}")
    print(f"  {len(filings)} filings | {len(politicians)} politicians | {len(sensitivity)} sensitivity rows")
    print(f"  Commit docs/data.js to update the GitHub Pages site.")


def _read_existing_sensitivity() -> list:
    """Preserve the SENSITIVITY array from the current data.js so export doesn't wipe it."""
    import json, os, re
    path = os.path.join("docs", "data.js")
    if not os.path.exists(path):
        return []
    try:
        content = open(path, encoding="utf-8").read()
        m = re.search(r"const SENSITIVITY = (\[.*?\]);", content, re.DOTALL)
        if m:
            return json.loads(m.group(1))
    except Exception:
        pass
    return []


def cmd_export():
    """Regenerate docs/data.js — preserves SENSITIVITY from last followcongress run."""
    import os
    import pandas as pd
    from datetime import date

    if not os.path.exists("congress_rankings.csv"):
        print("  ERROR: congress_rankings.csv not found.")
        print("  Run: python main.py followcongress   (generates data.js automatically)")
        return

    df_r = pd.read_csv("congress_rankings.csv")
    top12 = df_r[df_r["trades"] >= 5].sort_values("avg_excess", ascending=False).head(12)
    politicians = [
        {"name": _shorten_name(r["politician"]), "excess": round(float(r["avg_excess"]), 1), "trades": int(r["trades"])}
        for _, r in top12.iterrows()
    ]
    reliable_count = int((df_r["avg_excess"] > 0).sum())

    sensitivity = _read_existing_sensitivity()
    if not sensitivity:
        print("  Note: no sensitivity data found — run followcongress to populate the hold-period table.")
    _write_data_js(sensitivity, str(date.today()), reliable_count, politicians, source="export")


COMMANDS = {
    "congress":        cmd_congress,
    "followcongress":  cmd_followcongress,
    "paircongress":    cmd_paircongress,
    "congressoptions": cmd_congressoptions,
    "account":         cmd_account,
    "live":            cmd_live,
    "export":          cmd_export,
}

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else None
    if cmd not in COMMANDS:
        print("Usage: python main.py [congress | followcongress | paircongress | congressoptions | account | live]")
        sys.exit(1)
    COMMANDS[cmd]()
