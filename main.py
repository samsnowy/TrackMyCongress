"""
Entry point for the congress trades research tool.

  python main.py congress            — latest congress trades via Quiver Quant API
  python main.py followcongress      — backtest following politicians' disclosures
  python main.py paircongress        — match buy/sell pairs, analyse sell-lag drift
  python main.py congressoptions     — options overview, Tuberville straddles, House calls
  python main.py optionsreliable     — rank politicians by their options-signal alpha
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

    from config import RELIABLE_MIN_EXCESS, RELIABLE_MIN_TRADES
    reliable = rankings[(rankings["avg_excess"] > RELIABLE_MIN_EXCESS) & (rankings["trades"] >= RELIABLE_MIN_TRADES)]
    print(f"\n--- Reliable group ({len(reliable)} politicians: excess>{RELIABLE_MIN_EXCESS}%, trades>={RELIABLE_MIN_TRADES}) ---")
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
        r2 = run_politician_backtest(df, hold_days=hd, min_trades=min_trades, closes=closes)
        rnk2 = rank_politicians(r2)
        rel2 = rnk2[(rnk2["avg_excess"] > RELIABLE_MIN_EXCESS) & (rnk2["trades"] >= RELIABLE_MIN_TRADES)]
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
    politicians = [
        {"name": _shorten_name(r["politician"]), "excess": round(float(r["avg_excess"]), 1), "trades": int(r["trades"])}
        for _, r in reliable.iterrows()
    ]
    _write_data_js(sensitivity_rows, str(_date.today()), int(len(reliable)), politicians, strategy2=_read_strategy2(), hc=_read_highconv())

    save = input("\nSave full rankings to CSV? [y/N]: ").strip().lower()
    if save == "y":
        rankings.to_csv("congress_rankings.csv", index=False)
        print("  Saved congress_rankings.csv")


def cmd_congressoptions():
    from congress.options_analysis import run_options_analysis
    run_options_analysis()


def cmd_optionsreliable():
    """
    Options-based reliable group analysis.
    Buy the underlying stock on each call-purchase filing date, hold N days.
    Shows which politicians generate alpha via their options signals.
    """
    from congress.options_analysis import load_options, backtest_options_signals, print_options_rankings

    print("Loading options data (House + Senate)...")
    df = load_options()
    print(f"  {len(df)} total options trades  |  {df['name'].nunique()} politicians")

    calls = df[(df["transaction"] == "Purchase") & (df["option_type"] == "Call")]
    print(f"  {len(calls)} call purchases across {calls['name'].nunique()} politicians")

    # All call purchases
    print("\nRunning backtest: all call purchases (buy underlying on filing date)...")
    all_calls = backtest_options_signals(df, hold_days_list=[30, 60, 90])
    print_options_rankings(all_calls, deep_itm=False)

    # Deep ITM only (strike/price < 0.85)
    deep_itm_calls = df[df["strike"].notna()]
    n_with_strike = len(deep_itm_calls[(deep_itm_calls["transaction"] == "Purchase") & (deep_itm_calls["option_type"] == "Call")])
    print(f"\n  ({n_with_strike} call purchases have known strike price for deep ITM filter)")

    if n_with_strike > 0:
        print("\nRunning backtest: deep ITM calls only (strike/price < 0.85)...")
        deep_rankings = backtest_options_signals(df, hold_days_list=[30, 60, 90], deep_itm_only=True)
        print_options_rankings(deep_rankings, deep_itm=True)

    # Check specific politicians
    target_pols = ["Pelosi", "Gottheimer", "Ross", "Bresnahan"]
    print(f"\n{'='*70}")
    print(f"  Focus: {', '.join(target_pols)} (current options signal group)")
    print(f"{'='*70}")
    for hold, rdf in sorted(all_calls.items()):
        if rdf.empty:
            continue
        print(f"\n  Hold {hold}d:")
        for target in target_pols:
            match = rdf[rdf["politician"].str.contains(target, na=False, regex=False)]
            if match.empty:
                print(f"    {target:<20} -- not enough data (< 2 signals)")
            else:
                row = match.iloc[0]
                print(f"    {row['politician']:<32}  {int(row['trades'])} trades  "
                      f"excess={row['avg_excess']:>+.1f}%  win={row['win_rate']:.0f}%")


def cmd_strategy2():
    """
    Strategy 2 backtest: buy on filing date, hold until politician files sell + N days.
    Tests the sell-lag signal as an exit trigger vs fixed 90d hold.
    Filters to reliable politician group if congress_rankings.csv exists.
    """
    import os
    import pandas as pd
    from congress.loader import load_historical
    from congress.trade_pairs import build_pairs, strategy2_sensitivity

    print("Loading scraped congress trades (House + Senate)...")
    df = load_historical()
    print(f"  {len(df):,} trades loaded\n")

    print("Building buy/sell pairs...")
    pairs = build_pairs(df)
    print(f"  {len(pairs)} matched pairs\n")

    reliable_pols = None
    if os.path.exists("congress_rankings.csv"):
        from config import RELIABLE_MIN_EXCESS, RELIABLE_MIN_TRADES
        rankings = pd.read_csv("congress_rankings.csv")
        reliable = rankings[(rankings["avg_excess"] > RELIABLE_MIN_EXCESS) & (rankings["trades"] >= RELIABLE_MIN_TRADES)]
        reliable_pols = set(reliable["politician"].tolist())
        print(f"  Filtering to {len(reliable_pols)} reliable politicians (excess>{RELIABLE_MIN_EXCESS}%, trades>={RELIABLE_MIN_TRADES})")
    else:
        print("  No congress_rankings.csv found — using all politicians")

    print()
    results = strategy2_sensitivity(pairs, reliable_pols=reliable_pols)

    if results.empty:
        print("  No results — not enough matched pairs with price data.")
        return

    print(f"\n--- Strategy 2: buy on buy_filed, exit on sell_filed + N days ---")
    print(f"  (Strategy 1 benchmark: buy on buy_filed, exit after fixed 90d -- +4.8% excess, 12-pol all-trades)\n")
    print(f"  {'Hold after sell':>16}  {'Pairs':>6}  {'Avg Ret':>8}  {'SPY':>7}  {'Excess':>8}  {'Win%':>6}")
    print("  " + "-" * 62)
    for _, row in results.iterrows():
        label = f"sell_filed +{int(row['hold_after_sell_d'])}d"
        marker = " <--" if row['excess'] == results['excess'].max() else ""
        print(
            f"  {label:>16}  {int(row['pairs']):>6}  "
            f"{row['avg_ret']:>+7.1f}%  {row['spy']:>+6.1f}%  "
            f"{row['excess']:>+7.1f}%  {row['win_pct']:>5.1f}%{marker}"
        )

    # Save for export / data.js
    import json
    s2_rows = [
        {
            "hold_after_sell": int(r["hold_after_sell_d"]),
            "pairs":   int(r["pairs"]),
            "avg_ret": round(float(r["avg_ret"]), 1),
            "spy":     round(float(r["spy"]), 1),
            "excess":  round(float(r["excess"]), 1),
            "win_pct": round(float(r["win_pct"]), 1),
        }
        for _, r in results.iterrows()
    ]
    with open("strategy2_results.json", "w") as f:
        json.dump(s2_rows, f, indent=2)
    print("\n  Saved strategy2_results.json (picked up by: python main.py export)")


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


def _write_data_js(sensitivity: list, generated: str, reliable_count: int, politicians: list, source: str = "followcongress", strategy2: list | None = None, hc: dict | None = None) -> None:
    """Write docs/data.js from in-memory data + congress CSVs."""
    import json, os
    import pandas as pd
    from congress.strategy import match_politician

    # Last 90 days of filings — all rows, no per-politician cap
    filings = []
    if os.path.exists("congress_trades.csv") and os.path.exists("congress_rankings.csv"):
        df_t = pd.read_csv("congress_trades.csv")
        df_t["ReportDate"] = pd.to_datetime(df_t["ReportDate"], errors="coerce")
        df_t = df_t.dropna(subset=["ReportDate", "Ticker", "Representative"])
        cutoff = pd.Timestamp.today() - pd.Timedelta(days=90)
        df_t = df_t[df_t["ReportDate"] >= cutoff].sort_values("ReportDate", ascending=False)

        df_r = pd.read_csv("congress_rankings.csv")
        from config import RELIABLE_MIN_EXCESS, RELIABLE_MIN_TRADES
        from congress.strategy import KNOWN_OPTIONS_POLITICIANS, _matches_options_politician
        reliable_pols = {r["politician"]: {} for _, r in df_r[(df_r["avg_excess"] > RELIABLE_MIN_EXCESS) & (df_r["trades"] >= RELIABLE_MIN_TRADES)].iterrows()}
        hc_pols = {}
        if os.path.exists("congress_rankings_hc.csv"):
            df_hc = pd.read_csv("congress_rankings_hc.csv")
            hc_pols = {r["politician"]: {} for _, r in df_hc[(df_hc["avg_excess"] > RELIABLE_MIN_EXCESS) & (df_hc["trades"] >= RELIABLE_MIN_TRADES)].iterrows()}

        for _, row in df_t.iterrows():
            pol    = str(row["Representative"])
            tx_dt  = pd.to_datetime(row.get("TransactionDate"), errors="coerce")
            amount = str(row.get("Range", ""))
            t_type = str(row.get("TickerType", "ST"))
            is_opt = t_type == "OP"
            # Star if: stock reliable group (any trade), OR options politician on an options trade
            is_reliable = (
                match_politician(pol, reliable_pols) or
                (is_opt and _matches_options_politician(pol))
            )
            is_low_conv = amount.strip().startswith("$1,001")
            is_hc = bool(match_politician(pol, hc_pols)) and not is_low_conv
            filings.append({
                "date":     str(row["ReportDate"].date()),
                "tx_date":  str(tx_dt.date()) if pd.notna(tx_dt) else "",
                "name":     pol,
                "party":    str(row.get("Party", "")),
                "ticker":   str(row["Ticker"]),
                "type":     t_type if t_type in ("ST", "OP") else "ST",
                "txn":      str(row.get("Transaction", "")),
                "range":    amount,
                "reliable": is_reliable,
                "hc":       is_hc,
                "low_conv": is_low_conv,
            })

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

    s2 = strategy2 if strategy2 is not None else []
    hc_sensitivity  = (hc or {}).get("sensitivity", [])
    hc_politicians  = (hc or {}).get("politicians", [])
    live_positions = _read_live_positions()
    portfolio = _read_portfolio_snapshot(live_positions)

    out_path = os.path.join("docs", "data.js")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"// Generated by: python main.py {source} -- do not edit manually\n\n")
        f.write(f"const DATA_GENERATED = {json.dumps(generated)};\n\n")
        f.write(f"const STATS = {json.dumps(stats, indent=2)};\n\n")
        f.write(f"const SENSITIVITY = {json.dumps(sensitivity, indent=2)};\n\n")
        f.write(f"const STRATEGY2 = {json.dumps(s2, indent=2)};\n\n")
        f.write(f"const POLITICIANS = {json.dumps(politicians, indent=2)};\n\n")
        f.write(f"const HC_SENSITIVITY = {json.dumps(hc_sensitivity, indent=2)};\n\n")
        f.write(f"const HC_POLITICIANS = {json.dumps(hc_politicians, indent=2)};\n\n")
        f.write(f"const LIVE_POSITIONS = {json.dumps(live_positions, indent=2)};\n\n")
        f.write(f"const PORTFOLIO = {json.dumps(portfolio, indent=2)};\n\n")
        f.write(f"const FILINGS = {json.dumps(filings, indent=2)};\n")

    print(f"  [data.js] Written: {out_path}")
    print(f"  {len(filings)} filings | {len(politicians)} politicians | {len(hc_politicians)} HC politicians | {len(s2)} strategy2 rows | {len(live_positions)} live positions | portfolio: {portfolio.get('source', 'unknown')}")
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


def _read_strategy2() -> list:
    """Read strategy2_results.json written by cmd_strategy2."""
    import json, os
    path = "strategy2_results.json"
    if not os.path.exists(path):
        return []
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return []


def _read_highconv() -> dict:
    """Read highconv_results.json written by cmd_highconv."""
    import json, os
    path = "highconv_results.json"
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def _read_live_positions() -> list:
    """Read open live-strategy positions from strategy_state.json for the site."""
    import json, os
    path = "strategy_state.json"
    if not os.path.exists(path):
        return []
    try:
        with open(path) as f:
            state = json.load(f)
    except Exception:
        return []

    positions = []
    for pos in state.get("open_positions", []):
        positions.append({
            "ticker":       pos.get("ticker", ""),
            "source":       pos.get("source", "stock"),
            "qty":          pos.get("qty", 0),
            "entry_date":   pos.get("entry_date", ""),
            "signal_date":  pos.get("signal_date", ""),
            "planned_exit": pos.get("planned_exit", ""),
            "entry_price":  round(float(pos.get("entry_price") or 0), 2),
            "order_id":     pos.get("order_id", ""),
            "politicians":  pos.get("politicians", []),
        })
    return positions


def _read_portfolio_snapshot(live_positions: list | None = None) -> dict:
    """Read current Alpaca portfolio values for the site, falling back to local state."""
    from datetime import datetime
    from config import PARKING_TICKER

    try:
        from broker.alpaca_paper import get_account, get_positions
        acct = get_account()
        broker_positions = get_positions()
        positions = []
        total_unrealized = 0.0
        total_market_value = 0.0
        for p in broker_positions:
            qty = float(p.get("qty") or 0)
            current = float(p.get("current_price") or 0)
            avg_entry = float(p.get("avg_entry") or 0)
            unrealized = float(p.get("unrealized_pl") or 0)
            market_value = qty * current
            total_market_value += market_value
            total_unrealized += unrealized
            positions.append({
                "ticker":          p.get("ticker", ""),
                "qty":             qty,
                "avg_entry":       round(avg_entry, 2),
                "current_price":   round(current, 2),
                "market_value":    round(market_value, 2),
                "unrealized_pl":   round(unrealized, 2),
                "unrealized_pct":  round((current / avg_entry - 1) * 100, 2) if avg_entry else 0,
                "role":            "parking" if p.get("ticker") == PARKING_TICKER else "signal",
            })

        initial_equity = 1_000_000.0
        equity = float(acct.get("equity") or 0)
        return {
            "source":             "alpaca",
            "as_of":              datetime.now().strftime("%Y-%m-%d %H:%M"),
            "initial_equity":     initial_equity,
            "equity":             round(equity, 2),
            "cash":               round(float(acct.get("cash") or 0), 2),
            "buying_power":       round(float(acct.get("buying_power") or 0), 2),
            "portfolio_value":    round(float(acct.get("portfolio_value") or equity), 2),
            "total_pl":           round(equity - initial_equity, 2),
            "total_pl_pct":       round((equity / initial_equity - 1) * 100, 2) if initial_equity else 0,
            "unrealized_pl":      round(total_unrealized, 2),
            "market_value":       round(total_market_value, 2),
            "positions":          positions,
        }
    except Exception as e:
        positions = []
        for p in live_positions or []:
            positions.append({
                "ticker":          p.get("ticker", ""),
                "qty":             p.get("qty", 0),
                "avg_entry":       p.get("entry_price", 0),
                "current_price":   0,
                "market_value":    0,
                "unrealized_pl":   0,
                "unrealized_pct":  0,
                "role":            "parking" if p.get("ticker") == PARKING_TICKER else "signal",
            })
        return {
            "source":             "strategy_state",
            "error":              str(e),
            "as_of":              datetime.now().strftime("%Y-%m-%d %H:%M"),
            "initial_equity":     1_000_000.0,
            "equity":             0,
            "cash":               0,
            "buying_power":       0,
            "portfolio_value":    0,
            "total_pl":           0,
            "total_pl_pct":       0,
            "unrealized_pl":      0,
            "market_value":       0,
            "positions":          positions,
        }


def cmd_highconv():
    """
    High-conviction backtest: only trades >$15k.
    Finds which politicians show alpha on their meaningful-sized purchases.
    Saves highconv_results.json for pickup by: python main.py export
    """
    import json
    from congress.loader import load_for_backtest
    from congress.backtest import run_politician_backtest, rank_politicians, prefetch_prices, simulate_group
    from config import RELIABLE_MIN_EXCESS, RELIABLE_MIN_TRADES

    print("Loading scraped congress trades (House + Senate)...")
    df_all = load_for_backtest(purchases_only=True)
    low_conv = df_all["amount_range"].str.startswith("$1,001", na=False)
    df_hc = df_all[~low_conv].copy()
    print(f"  {len(df_all):,} total purchases -> {len(df_hc):,} high-conviction (>$15k, {len(df_hc)/len(df_all)*100:.0f}%)")

    print("\nPrefetching prices (once)...")
    closes = prefetch_prices(df_all)

    print("\nRunning high-conviction backtest across hold periods...")
    print(f"  {'Hold':>6}  {'Trades':>7}  {'Avg Ret':>8}  {'SPY':>7}  {'Excess':>8}  {'Win%':>6}")
    print("  " + "-" * 50)
    sensitivity = []
    for hd in [10, 20, 30, 60, 90]:
        r = run_politician_backtest(df_hc, hold_days=hd, min_trades=3, closes=closes)
        rnk = rank_politicians(r)
        rel = rnk[(rnk["avg_excess"] > RELIABLE_MIN_EXCESS) & (rnk["trades"] >= RELIABLE_MIN_TRADES)]
        g = simulate_group(r, rel["politician"].tolist())
        if g:
            sensitivity.append({
                "hold":    hd,
                "trades":  g["total_trades"],
                "avg_ret": round(g["avg_trade_ret"], 1),
                "spy":     round(g["avg_spy_ret"], 1),
                "excess":  round(g["avg_excess"], 1),
                "win_pct": int(round(g["win_rate"])),
            })
            print(f"  {hd:>5}d  {g['total_trades']:>7,}  {g['avg_trade_ret']:>+7.1f}%  {g['avg_spy_ret']:>+6.1f}%  {g['avg_excess']:>+7.1f}%  {g['win_rate']:>5.0f}%")

    r90 = run_politician_backtest(df_hc, hold_days=90, min_trades=3, closes=closes)
    rnk90 = rank_politicians(r90)
    rel90 = rnk90[(rnk90["avg_excess"] > RELIABLE_MIN_EXCESS) & (rnk90["trades"] >= RELIABLE_MIN_TRADES)]
    politicians = [
        {"name": _shorten_name(r["politician"]), "excess": round(float(r["avg_excess"]), 1), "trades": int(r["trades"])}
        for _, r in rel90.iterrows()
    ]

    print(f"\n  High-conviction reliable group ({len(politicians)} politicians):")
    for p in politicians:
        print(f"    {p['name']:<28} {p['trades']:>4} trades  {p['excess']:>+5.1f}% excess")

    # Save sidecar JSON for export/data.js
    results = {"sensitivity": sensitivity, "politicians": politicians}
    with open("highconv_results.json", "w") as f:
        json.dump(results, f, indent=2)

    # Save HC rankings CSV — picked up by live strategy (preferred over congress_rankings.csv)
    rel90.to_csv("congress_rankings_hc.csv", index=False)
    print(f"\n  Saved highconv_results.json + congress_rankings_hc.csv")
    print(f"  Live strategy will now follow {len(politicians)} HC politicians (>$15k trades only).")
    print(f"  Run: python main.py export   to update docs/data.js")


def cmd_walkforward():
    """
    Walk-forward validation: train reliable group on 2022-2023, test OOS on 2024-2026.
    Also runs the HC (>$15k) variant side by side.
    """
    from congress.loader import load_for_backtest
    from congress.backtest import prefetch_prices
    from congress.walkforward import run_walk_forward, print_walk_forward
    from config import RELIABLE_MIN_EXCESS, RELIABLE_MIN_TRADES

    print("Loading scraped congress trades (House + Senate)...")
    df_all = load_for_backtest(purchases_only=True)
    print(f"  {len(df_all):,} purchases loaded  ({df_all['ReportDate'].min().date()} to {df_all['ReportDate'].max().date()})")

    # HC filter (>$15k trades)
    low_conv = df_all["amount_range"].str.startswith("$1,001", na=False)
    df_hc = df_all[~low_conv].copy()
    print(f"  HC subset: {len(df_hc):,} purchases (>$15k, {len(df_hc)/len(df_all)*100:.0f}%)")

    print("\nPrefetching prices (once, covers full 2022–2026 range)...")
    closes = prefetch_prices(df_all)

    # --- All-trades walk-forward ---
    r_all = run_walk_forward(
        df_all, closes,
        hold_days=90,
        min_excess=RELIABLE_MIN_EXCESS,
        min_trades=RELIABLE_MIN_TRADES,
    )
    print_walk_forward(r_all, label="All Trades")

    # --- HC walk-forward ---
    r_hc = run_walk_forward(
        df_hc, closes,
        hold_days=90,
        min_excess=RELIABLE_MIN_EXCESS,
        min_trades=RELIABLE_MIN_TRADES,
    )
    print_walk_forward(r_hc, label="High-Conviction (>$15k trades)")


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
    from config import RELIABLE_MIN_EXCESS, RELIABLE_MIN_TRADES
    reliable_mask = (df_r["avg_excess"] > RELIABLE_MIN_EXCESS) & (df_r["trades"] >= RELIABLE_MIN_TRADES)
    reliable_group = df_r[reliable_mask].sort_values("avg_excess", ascending=False)
    reliable_count = int(reliable_mask.sum())
    politicians = [
        {"name": _shorten_name(r["politician"]), "excess": round(float(r["avg_excess"]), 1), "trades": int(r["trades"])}
        for _, r in reliable_group.iterrows()
    ]

    sensitivity = _read_existing_sensitivity()
    if not sensitivity:
        print("  Note: no sensitivity data found — run followcongress to populate the hold-period table.")
    _write_data_js(sensitivity, str(date.today()), reliable_count, politicians, source="export", strategy2=_read_strategy2(), hc=_read_highconv())


COMMANDS = {
    "congress":        cmd_congress,
    "followcongress":  cmd_followcongress,
    "paircongress":    cmd_paircongress,
    "congressoptions": cmd_congressoptions,
    "optionsreliable": cmd_optionsreliable,
    "strategy2":       cmd_strategy2,
    "highconv":        cmd_highconv,
    "walkforward":     cmd_walkforward,
    "account":         cmd_account,
    "live":            cmd_live,
    "export":          cmd_export,
}

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else None
    if cmd not in COMMANDS:
        print("Usage: python main.py [congress | followcongress | paircongress | congressoptions | optionsreliable | highconv | walkforward | strategy2 | account | live | export]")
        sys.exit(1)
    COMMANDS[cmd]()
