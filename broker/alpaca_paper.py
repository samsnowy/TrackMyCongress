"""
Alpaca paper trading wrapper.
Requires free account at alpaca.markets — generate Paper API keys there.
Copy .env.example to .env and fill in your keys.
"""

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest
import config


def get_client() -> TradingClient:
    if not config.ALPACA_API_KEY or not config.ALPACA_SECRET_KEY:
        raise EnvironmentError(
            "Alpaca API keys not configured. Add ALPACA_API_KEY and ALPACA_SECRET_KEY to .env"
        )
    # paper=True is the real live-vs-paper guard — ALPACA_BASE_URL alone does not control this.
    return TradingClient(config.ALPACA_API_KEY, config.ALPACA_SECRET_KEY, paper=True)


def get_account() -> dict:
    client = get_client()
    acct = client.get_account()
    return {
        "equity": float(acct.equity),
        "cash": float(acct.cash),
        "buying_power": float(acct.buying_power),
        "portfolio_value": float(acct.portfolio_value),
    }


def get_positions() -> list[dict]:
    client = get_client()
    positions = client.get_all_positions()
    return [
        {
            "ticker": p.symbol,
            "qty": float(p.qty),
            "avg_entry": float(p.avg_entry_price),
            "current_price": float(p.current_price),
            "unrealized_pl": float(p.unrealized_pl),
        }
        for p in positions
    ]


def get_order(order_id: str) -> dict:
    """Return the fill lifecycle fields needed to reconcile strategy state."""
    order = get_client().get_order_by_id(order_id)
    status = getattr(order.status, "value", str(order.status)).lower()
    return {
        "id": str(order.id),
        "ticker": order.symbol,
        "status": status,
        "qty": float(order.qty or 0),
        "filled_qty": float(order.filled_qty or 0),
        "filled_avg_price": (
            float(order.filled_avg_price) if order.filled_avg_price is not None else None
        ),
        "submitted_at": str(order.submitted_at) if order.submitted_at else "",
        "filled_at": str(order.filled_at) if order.filled_at else "",
    }


def place_market_order(ticker: str, side: str, qty: int) -> dict:
    """Place a market order. side = 'buy' or 'sell'."""
    client = get_client()
    side = side.lower()
    if side not in ("buy", "sell"):
        raise ValueError(f"Invalid order side: {side!r}. Expected 'buy' or 'sell'.")
    order_side = OrderSide.BUY if side == "buy" else OrderSide.SELL
    req = MarketOrderRequest(
        symbol=ticker,
        qty=qty,
        side=order_side,
        time_in_force=TimeInForce.GTC,
    )
    order = client.submit_order(req)
    return {"id": str(order.id), "status": str(order.status), "ticker": ticker, "qty": qty, "side": side}


def place_bracket_order(ticker: str, qty: int, entry: float, stop: float, target: float) -> dict:
    """
    Place a bracket order: limit entry with OCO stop-loss and take-profit legs.
    This automates the entire trade — entry, stop, and target in one order.
    """
    client = get_client()
    req = LimitOrderRequest(
        symbol=ticker,
        qty=qty,
        side=OrderSide.BUY,
        type="limit",
        time_in_force=TimeInForce.GTC,
        limit_price=round(entry, 2),
        order_class="bracket",
        stop_loss={"stop_price": round(stop, 2)},
        take_profit={"limit_price": round(target, 2)},
    )
    order = client.submit_order(req)
    return {"id": str(order.id), "status": str(order.status), "ticker": ticker}


def calculate_shares(account_equity: float, entry: float, stop: float) -> int:
    """
    Calculate position size based on 1% account risk.
    Risk per share = entry - stop
    Shares = (equity * 0.01) / risk_per_share
    """
    risk_per_share = entry - stop
    if risk_per_share <= 0:
        raise ValueError("Entry must be above stop")
    dollar_risk = account_equity * config.RISK_PER_TRADE
    shares = int(dollar_risk / risk_per_share)
    return max(shares, 1)


def cancel_all_orders() -> None:
    client = get_client()
    client.cancel_orders()
    print("[broker] all open orders cancelled")


def close_all_positions() -> None:
    client = get_client()
    client.close_all_positions(cancel_orders=True)
    print("[broker] all positions closed")
