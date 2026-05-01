"""
Live paper trading strategy — congressional disclosure follow-through.

Two signal sources:
  Stock:   Quiver Quant live feed — purchase disclosures by the reliable group.
           Hold 90 days.
  Options: congress_options.csv (scraped) — deep-ITM call purchases by known
           options-active politicians (Gottheimer, Pelosi). Buy the underlying.
           Hold 30 days (signal peaks earlier than stocks).

State is persisted to strategy_state.json between runs.

Run:
    python main.py live           — execute (places real paper orders)
    python main.py live --dry-run — simulate without placing orders
"""

import json
import os
from datetime import date, datetime, timedelta

from config import HOLD_DAYS, MAX_POSITIONS, POSITION_SIZE_PCT, SIMULATED_EQUITY
from congress.fetcher import fetch_trades
from congress.strategy import (
    all_signal_keys_for_ticker,
    deduplicate_signals,
    detect_new_signals,
    detect_options_signals,
    load_reliable_politicians,
    positions_to_exit,
)
from data.fetcher import get_latest_price, get_latest_prices

STATE_FILE = "strategy_state.json"


# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------

def _load_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return {"open_positions": [], "closed_positions": [], "seen_signals": []}
    try:
        with open(STATE_FILE) as f:
            state = json.load(f)
        for key in ("open_positions", "closed_positions", "seen_signals"):
            if not isinstance(state.get(key), list):
                raise ValueError(f"key '{key}' missing or not a list")
        return state
    except (json.JSONDecodeError, ValueError) as e:
        print(f"  [error] {STATE_FILE} is malformed: {e}")
        print(f"         Rename or delete it to start fresh.")
        raise SystemExit(1)


def _save_state(state: dict) -> None:
    # File permissions (e.g. 0o600) are not set — os.chmod mode bits are no-ops on Windows.
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2, default=str)
    os.replace(tmp, STATE_FILE)


# ---------------------------------------------------------------------------
# Price helpers
# ---------------------------------------------------------------------------


def _calc_qty(equity: float, price: float) -> int:
    """Fixed fractional position sizing — POSITION_SIZE_PCT of equity."""
    return max(1, int(equity * POSITION_SIZE_PCT / price))


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run_live(dry_run: bool = False) -> None:
    today = str(date.today())
    tag   = "[DRY RUN] " if dry_run else ""
    print(f"\n=== Congress Trade Strategy {tag}=== {today} ===\n")

    # --- State + reliable politicians ---
    state     = _load_state()
    seen      = set(state.get("seen_signals", []))
    open_pos  = state.get("open_positions", [])

    reliable_pols = load_reliable_politicians()
    using_fallback = not os.path.exists("congress_rankings.csv")
    print(f"  Reliable politicians : {len(reliable_pols)}"
          + ("  [fallback list — run followcongress + save to improve]" if using_fallback else ""))

    # --- Alpaca connection ---
    equity        = SIMULATED_EQUITY
    live_tickers  = set()
    _place_order  = None

    try:
        from broker.alpaca_paper import get_account, get_positions, place_market_order
        acct         = get_account()
        equity       = acct["equity"]
        live_tickers = {p["ticker"] for p in get_positions()}
        _place_order = place_market_order
        print(f"  Alpaca equity        : ${equity:,.2f}")
        print(f"  Live positions       : {len(live_tickers)}")
    except Exception as e:
        if dry_run:
            print(f"  Alpaca unavailable ({e}) — simulating with ${SIMULATED_EQUITY:,.0f}")
        else:
            print(f"  [error] Alpaca connection failed: {e}")
            print("  Add API keys to .env or use --dry-run to simulate.")
            return

    # --- Process exits ---
    to_exit = positions_to_exit(open_pos, today)
    if to_exit:
        print(f"\n--- Exits ({len(to_exit)} position(s) past their hold target) ---")

    new_closed = []
    remaining  = []
    for pos in open_pos:
        # TODO: match on order_id instead of ticker+entry_date — collapses if same ticker
        # entered twice on the same calendar day (unlikely but possible after a manual state edit)
        exit_match = next((e for e in to_exit if e["ticker"] == pos["ticker"]
                           and e["entry_date"] == pos["entry_date"]), None)
        if exit_match is None:
            remaining.append(pos)
            continue

        ticker = pos["ticker"]
        qty    = pos.get("qty", 0)
        held   = exit_match["held_days"]

        exit_price = get_latest_price(ticker)
        if exit_price is None:
            print(f"  DEFER {ticker:<6}  held={held}d — price unavailable, deferring exit")
            remaining.append(pos)
            continue

        print(f"  EXIT  {ticker:<6}  held={held}d  qty={qty}")

        if not dry_run and _place_order and ticker in live_tickers and qty > 0:
            try:
                r = _place_order(ticker, "sell", qty)
                print(f"         order {r['id']} ({r['status']})")
            except Exception as e:
                print(f"         [error] sell failed for {ticker}: {e} — keeping position open")
                remaining.append(pos)
                continue

        closed = {
            **pos,
            "exit_date":  today,
            "exit_price": exit_price,
            "held_days":  held,
        }
        if pos.get("entry_price"):
            closed["realized_pct"] = round(
                (exit_price / pos["entry_price"] - 1) * 100, 2
            )
        new_closed.append(closed)

    open_pos = remaining

    # --- Detect stock signals (Quiver feed) ---
    print(f"\n--- Scanning for stock signals ---")
    df         = fetch_trades(purchases_only=True)
    raw_sigs   = detect_new_signals(df, seen, reliable_pols)
    signals    = deduplicate_signals(raw_sigs)

    if not raw_sigs:
        print("  No new stock signals.")
    else:
        print(f"  {len(raw_sigs)} raw signal(s) -> {len(signals)} after dedup")

    # --- Detect options signals (Quiver live feed, TickerType==OP) ---
    print(f"\n--- Scanning for options signals ---")
    from congress.fetcher import fetch_options
    from congress.options_analysis import load_options
    opts_df = fetch_options()   # live feed first (same 12h cache as stock signals)
    source_label = "Quiver live"
    if opts_df.empty and os.path.exists("congress_options.csv"):
        # NOTE: scraped CSV uses a different column schema than the Quiver feed; detect_options_signals
        # expects Quiver-style columns (filing_date, transaction, option_type, strike, expiration,
        # amount_range). If the scraped CSV fallback ever diverges, signals will silently be empty.
        opts_df      = load_options(chamber="house")
        source_label = "scraped CSV fallback"
    print(f"  Options source: {source_label} ({len(opts_df)} rows)")

    opt_sigs = []
    if not opts_df.empty:
        opt_tickers = opts_df[
            (opts_df["transaction"] == "Purchase") &
            (opts_df["option_type"] == "Call")
        ]["ticker"].dropna().unique().tolist()
        opt_prices  = get_latest_prices(opt_tickers)
        opt_sigs    = detect_options_signals(opts_df, seen, opt_prices)

    if not opt_sigs:
        print("  No new options signals.")
    else:
        print(f"  {len(opt_sigs)} options signal(s):")
        for s in opt_sigs:
            strike_str = f"  strike=${s['strike']:.0f}" if s.get("strike") else ""
            print(f"    {s['ticker']} ({s['range']})  filed {s['report_date']}"
                  f"  by {s['politician']}{strike_str}  hold {s['hold_days']}d")

    # Merge both signal lists; options signals already have hold_days set
    all_signals = signals + opt_sigs

    # --- Execute entries ---
    for sig in all_signals:
        ticker    = sig["ticker"]
        pols      = sig["politicians"]
        pol_disp  = ", ".join(pols) if len(pols) <= 2 else f"{pols[0]} + {len(pols)-1} others"
        acc_flag  = "  [ACCUMULATION]" if sig.get("accumulation") else ""
        src_flag  = "  [OPTIONS->STOCK]" if sig.get("source") == "options" else ""
        hold_days = sig.get("hold_days", HOLD_DAYS)
        print(f"\n  SIGNAL  {ticker}  ({sig['range']})  {sig['report_date']}{acc_flag}{src_flag}")
        print(f"          filed by {pol_disp}")

        # raw_keys covers both stock and options signal keys for this ticker
        raw_keys = all_signal_keys_for_ticker(raw_sigs, ticker) | \
                   all_signal_keys_for_ticker(opt_sigs, ticker)

        if len(open_pos) >= MAX_POSITIONS:
            print(f"          -> skip: at max positions ({MAX_POSITIONS})")
            continue   # intentionally don't mark seen — retry after an exit

        if any(p["ticker"] == ticker for p in open_pos):
            print(f"          -> skip: already holding {ticker}")
            seen.update(raw_keys)
            continue

        price = get_latest_price(ticker)
        if price is None:
            print(f"          -> skip: could not fetch price")
            seen.update(raw_keys)
            continue

        qty          = _calc_qty(equity, price)
        planned_exit = str(
            datetime.strptime(sig["report_date"], "%Y-%m-%d").date() + timedelta(days=hold_days)
        )

        print(f"          price=${price:.2f}  qty={qty}  "
              f"value=${qty*price:,.0f}  planned_exit={planned_exit}")

        # NOTE: equity is captured once at run start (line ~100) and not updated after exits
        # within the same run, so position sizing for later entries uses pre-exit equity.
        # Fine in practice (at most a few exits per run) but worth knowing if sizing feels off.
        order_id = "dry-run"
        if not dry_run and _place_order:
            try:
                r        = _place_order(ticker, "buy", qty)
                order_id = r["id"]
                print(f"          -> order {order_id} ({r['status']})")
            except Exception as e:
                print(f"          -> [error] {e}")
                seen.update(raw_keys)
                continue

        # NOTE: if _place_order is None (broker unreachable, non-dry-run), the block above is
        # skipped entirely and order_id stays "dry-run". The position is still appended below,
        # creating a phantom state entry. Guard: check Alpaca connectivity before running live.
        open_pos.append({
            "ticker":       ticker,
            "politicians":  pols,
            "signal_date":  sig["report_date"],
            "entry_date":   today,
            "planned_exit": planned_exit,
            "hold_days":    hold_days,
            "order_id":     order_id,
            "qty":          qty,
            "entry_price":  price,
            "accumulation": sig.get("accumulation", False),
            "source":       sig.get("source", "stock"),
        })
        seen.update(raw_keys)

    # --- Portfolio summary ---
    print(f"\n--- Open Positions ({len(open_pos)}) ---")
    if open_pos:
        current_prices = get_latest_prices([p["ticker"] for p in open_pos])
        print(f"  {'Ticker':<6}  {'Src':<3}  {'Entry':>7}  {'Now':>7}  {'P&L':>7}  "
              f"{'Held':>5}  {'Exit':<11}  Politicians")
        print("  " + "-" * 88)
        for pos in open_pos:
            current   = current_prices.get(pos["ticker"])
            entry     = pos.get("entry_price")
            pct       = (current / entry - 1) * 100 if current and entry else 0.0
            entry_dt  = datetime.strptime(pos["entry_date"], "%Y-%m-%d").date()
            held_days = (date.today() - entry_dt).days
            pols      = pos.get("politicians", ["?"])
            pol_str   = ", ".join(pols) if isinstance(pols, list) else str(pols)
            src       = "opt" if pos.get("source") == "options" else "stk"
            print(
                f"  {pos['ticker']:<6}  "
                f"{src:<3}  "
                f"${entry or 0:>6.2f}  "
                f"${current or 0:>6.2f}  "
                f"{pct:>+6.1f}%  "
                f"{held_days:>4}d  "
                f"{pos.get('planned_exit','?'):<11}  "
                f"{pol_str[:35]}"
            )
    else:
        print("  (none)")

    # --- Persist ---
    state["open_positions"]  = open_pos
    state["closed_positions"] = state.get("closed_positions", []) + new_closed
    state["seen_signals"]    = list(seen)
    state["last_checked"]    = today

    if dry_run:
        print(f"\n  [dry run] state not saved")
    else:
        _save_state(state)
        print(f"\n  State saved to {STATE_FILE}")

    # Closed summary
    if new_closed:
        print(f"\n--- Closed This Run ({len(new_closed)}) ---")
        for c in new_closed:
            pct = c.get("realized_pct")
            pct_str = f"{pct:+.1f}%" if pct is not None else "?"
            print(f"  {c['ticker']:<6}  held={c['held_days']}d  realized={pct_str}")
