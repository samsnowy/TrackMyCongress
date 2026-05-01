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
OPTIONS_HOLD_DAYS  = 30     # options signal hold period — signal fades faster
MAX_POSITIONS      = 15
POSITION_SIZE_PCT  = 0.05   # 5% of equity per position
SIGNAL_LOOKBACK    = 7      # days back for stock signals
OPTIONS_LOOKBACK   = 30     # days back for options signals
DEEP_ITM_THRESHOLD = 0.85   # strike/current_price below this = call is >=15% ITM
SIMULATED_EQUITY   = 100_000.0  # dry-run fallback when Alpaca is unavailable
