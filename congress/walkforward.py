"""
Walk-forward validation for the follow-congress strategy.

1. Train on data before split_date  → rank politicians → select reliable group
2. Test on data after split_date    → measure ONLY pre-selected politicians (no re-ranking)
3. If alpha persists OOS, the edge is not purely an in-sample selection artifact

Run via:  python main.py walkforward
"""

import pandas as pd
import numpy as np
from congress.backtest import run_politician_backtest, rank_politicians, simulate_group

SPLIT_DATE = "2024-01-01"


def run_walk_forward(
    df: pd.DataFrame,
    closes: pd.DataFrame,
    hold_days: int = 90,
    min_excess: float = 2.0,
    min_trades: int = 20,
    split_date: str = SPLIT_DATE,
) -> dict:
    """
    df must already be filtered to purchases only and have ReportDate as Timestamp.
    closes must cover the full date range of df + hold_days.
    """
    split = pd.Timestamp(split_date)
    df_train = df[df["ReportDate"] < split].copy()
    df_test  = df[df["ReportDate"] >= split].copy()

    # --- Training: rank everyone, then select reliable group ---
    print(f"\n  [train] Running backtest on {len(df_train):,} trades "
          f"({df_train['ReportDate'].min().date()} to {df_train['ReportDate'].max().date()})...")
    train_results  = run_politician_backtest(df_train, hold_days=hold_days, min_trades=1, closes=closes)
    train_rankings = rank_politicians(train_results)

    reliable_mask      = (train_rankings["avg_excess"] > min_excess) & (train_rankings["trades"] >= min_trades)
    training_reliable  = train_rankings[reliable_mask]["politician"].tolist()
    train_group        = simulate_group(train_results, training_reliable)

    # --- Test: fix the politician list, measure OOS performance ---
    df_test_selected = df_test[df_test["Representative"].isin(training_reliable)].copy()
    print(f"  [test]  Running backtest on {len(df_test_selected):,} trades "
          f"from {len(training_reliable)} pre-selected politicians "
          f"({df_test['ReportDate'].min().date()} to {df_test['ReportDate'].max().date()})...")
    test_results  = run_politician_backtest(df_test_selected, hold_days=hold_days, min_trades=1, closes=closes)
    test_rankings = rank_politicians(test_results)
    test_group    = simulate_group(test_results, training_reliable)

    return {
        "split_date":        split_date,
        "hold_days":         hold_days,
        "training_reliable": training_reliable,
        "train_rankings":    train_rankings,
        "test_rankings":     test_rankings,
        "train_group":       train_group,
        "test_group":        test_group,
        "n_train_trades":    len(df_train),
        "n_test_trades":     len(df_test),
        "n_test_selected":   len(df_test_selected),
    }


def print_walk_forward(r: dict, label: str = "") -> None:
    """Print a formatted walk-forward result."""
    header = f"Walk-Forward Validation{' — ' + label if label else ''}"
    print(f"\n{'='*68}")
    print(f"  {header}")
    print(f"  Train: before {r['split_date']}   |   Test: {r['split_date']} onwards")
    print(f"  Hold: {r['hold_days']}d")
    print(f"{'='*68}")

    pols = r["training_reliable"]
    tg   = r["train_group"]
    oos  = r["test_group"]

    print(f"\n  Reliable group identified in training ({len(pols)} politicians):")
    for p in pols:
        print(f"    * {p}")

    print(f"\n  {'Metric':<22}  {'Training (IS)':>14}  {'Test (OOS)':>12}")
    print("  " + "-" * 52)

    def _fmt(g: dict) -> tuple[str, str, str, str, str]:
        if not g:
            return ("—", "—", "—", "—", "—")
        return (
            f"{g['total_trades']}",
            f"{g['avg_excess']:>+.1f}%",
            f"{g['win_rate']:.0f}%",
            f"{g['avg_trade_ret']:>+.1f}%",
            f"{g['avg_spy_ret']:>+.1f}%",
        )

    t_trades, t_exc, t_win, t_ret, t_spy = _fmt(tg)
    o_trades, o_exc, o_win, o_ret, o_spy = _fmt(oos)

    print(f"  {'Trades':<22}  {t_trades:>14}  {o_trades:>12}")
    print(f"  {'Avg Excess Return':<22}  {t_exc:>14}  {o_exc:>12}")
    print(f"  {'Win Rate':<22}  {t_win:>14}  {o_win:>12}")
    print(f"  {'Avg Trade Return':<22}  {t_ret:>14}  {o_ret:>12}")
    print(f"  {'Avg SPY Return':<22}  {t_spy:>14}  {o_spy:>12}")

    if oos:
        print(f"\n  Per-politician OOS breakdown:")
        print(f"  {'Politician':<30} {'IS Excess':>10}  {'OOS Excess':>11}  {'OOS Trades':>11}  {'OOS Win%':>9}")
        print("  " + "-" * 68)
        tr = r["train_rankings"].set_index("politician")
        for pol in pols:
            is_exc = tr.loc[pol, "avg_excess"] if pol in tr.index else float("nan")
            oor = r["test_rankings"]
            oos_row = oor[oor["politician"] == pol]
            if oos_row.empty:
                print(f"  {pol:<30}  {is_exc:>+8.1f}%   {'no OOS trades':>11}")
            else:
                oos_exc  = oos_row.iloc[0]["avg_excess"]
                oos_n    = int(oos_row.iloc[0]["trades"])
                oos_win  = oos_row.iloc[0]["win_rate"]
                marker   = " [+]" if oos_exc > 0 else " [-]"
                print(f"  {pol:<30}  {is_exc:>+8.1f}%   {oos_exc:>+10.1f}%  {oos_n:>11}  {oos_win:>8.0f}%{marker}")

    if tg and oos:
        delta = (oos.get("avg_excess", 0) - tg.get("avg_excess", 0))
        pct_retained = oos.get("avg_excess", 0) / tg.get("avg_excess", 1) * 100 if tg.get("avg_excess", 0) != 0 else 0
        oos_exc = oos.get("avg_excess", 0)
        pols_with_oos = sum(1 for p in pols if not r["test_rankings"][r["test_rankings"]["politician"] == p].empty)
        print(f"\n  Politicians with OOS trades: {pols_with_oos}/{len(pols)}")
        print(f"  Alpha retention: {pct_retained:.0f}%  (OOS excess = IS excess {delta:>+.1f}pp)")
        if pols_with_oos == 0:
            print("  Verdict: no OOS trades for any politician in this group — inconclusive.")
        elif oos_exc <= 0:
            print("  Verdict: edge did NOT survive OOS — consistent with in-sample selection bias.")
        elif pct_retained >= 50:
            print("  Verdict: edge substantially survived OOS — consistent with a real informational signal.")
        elif pct_retained >= 20:
            print("  Verdict: edge partially survived OOS — weak positive, needs more OOS data.")
        else:
            print("  Verdict: edge mostly decayed OOS — result may be in-sample overfitting.")
    print()
