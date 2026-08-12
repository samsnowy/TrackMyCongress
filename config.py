import os
from dotenv import load_dotenv

load_dotenv()

# Alpaca paper trading (broker/alpaca_paper.py)
ALPACA_API_KEY    = os.getenv("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "")

# Used by broker/alpaca_paper.py calculate_shares() only.
# The live strategy uses POSITION_SIZE_PCT (fixed fractional) instead.
RISK_PER_TRADE = 0.01

# Live strategy parameters (congress/strategy.py + congress/live.py)
HOLD_DAYS          = 90     # stock signal hold period (days)
OPTIONS_HOLD_DAYS  = 30     # options signal hold period -- signal fades faster
MAX_POSITIONS      = 15
MAX_SIGNALS_PER_FILING_BATCH = 1  # prevent one politician's bulk filing dominating entries
POSITION_SIZE_PCT  = 0.05   # 5% of equity per position
PARKING_TICKER     = "SPY"  # idle cash parking vehicle for the paper strategy
CASH_BUFFER_PCT    = 0.01   # keep 1% of equity as cash for small price/order drift
SIGNAL_LOOKBACK    = 7      # days back for stock signals
OPTIONS_LOOKBACK   = 30     # days back for options signals
MAX_SIGNAL_AGE     = 7      # skip signals older than this many days on first run
DEEP_ITM_THRESHOLD = 0.85   # strike/current_price below this = call is >=15% ITM
SIMULATED_EQUITY   = 100_000.0  # dry-run fallback when Alpaca is unavailable

# Reliable politician filter (congress/strategy.py + main.py followcongress)
# Tighter than the old excess>0/trades>=5 defaults to cut bottom-of-list noise.
RELIABLE_MIN_EXCESS = 2.0   # minimum avg excess return % to be considered reliable
RELIABLE_MIN_TRADES = 20    # minimum trade count (sample size floor)
