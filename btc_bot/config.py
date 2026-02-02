import os

def env_str(name: str, default: str) -> str:
    v = os.getenv(name)
    return v if (v is not None and v != "") else default

def env_int(name: str, default: int) -> int:
    v = os.getenv(name)
    if v is None or v == "":
        return default
    return int(v)

def env_float(name: str, default: float) -> float:
    v = os.getenv(name)
    if v is None or v == "":
        return default
    return float(v)

def env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None or v == "":
        return default
    return v.strip().lower() in ("1", "true", "yes", "y")

# ===== Core =====
SYMBOL = env_str("SYMBOL", "BTCUSDT")
KLINE_INTERVAL = env_str("KLINE_INTERVAL", "5m")
POLL_SEC = env_int("POLL_SEC", 5)

STATE_FILE = env_str("STATE_FILE", "/app/data/state.json")

# ===== Logging =====
LOG_LEVEL = env_str("LOG_LEVEL", "INFO").upper()
LOG_TO_FILE = env_bool("LOG_TO_FILE", True)
LOG_FILE = env_str("LOG_FILE", "/app/data/btc_bot.log")
LOG_MAX_MB = env_int("LOG_MAX_MB", 5)
LOG_BACKUP_COUNT = env_int("LOG_BACKUP_COUNT", 3)

# ===== Telegram =====
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "").strip().strip('"').strip("'")
TG_CHAT_ID = os.getenv("TG_CHAT_ID", "").strip().strip('"').strip("'")

# ===== Strategy Selection =====
# trend | range
STRATEGY = env_str("STRATEGY", "trend")

# ===== Indicators & Filters =====
EMA_5M_PERIOD = env_int("EMA_5M_PERIOD", 20)
ATR_PERIOD = env_int("ATR_PERIOD", 14)

USE_VOL_FILTER = env_bool("USE_VOL_FILTER", True)
VOL_SMA_PERIOD = env_int("VOL_SMA_PERIOD", 20)
VOL_SPIKE_MULT = env_float("VOL_SPIKE_MULT", 1.5)

USE_ATR_FILTER = env_bool("USE_ATR_FILTER", True)
MIN_ATR_PCT = env_float("MIN_ATR_PCT", 0.003)

# 1h trend filter
EMA_FILTER_1H = env_bool("EMA_FILTER_1H", True)
EMA_1H_PERIOD = env_int("EMA_1H_PERIOD", 200)
EMA_1H_KLINES_LIMIT = env_int("EMA_1H_KLINES_LIMIT", 400)

# ===== Risk / Execution =====
COOLDOWN_SEC = env_int("COOLDOWN_SEC", 20)
REENTRY_BARS = env_int("REENTRY_BARS", 3)

USE_TP_SL = env_bool("USE_TP_SL", True)
SL_ATR_MULT = env_float("SL_ATR_MULT", 1.2)
TP_ATR_MULT = env_float("TP_ATR_MULT", 2.0)

USE_TRAILING = env_bool("USE_TRAILING", True)
TRAIL_ATR_MULT = env_float("TRAIL_ATR_MULT", 1.3)
TRAIL_ACTIVATE_R = env_float("TRAIL_ACTIVATE_R", 1.0)

# Kill switch
USE_KILL_SWITCH = env_bool("USE_KILL_SWITCH", True)
MAX_DAILY_DD_PCT = env_float("MAX_DAILY_DD_PCT", 3.0)

# ===== Paper trading =====
PAPER_TRADING = env_bool("PAPER_TRADING", True)
START_CASH_USDT = env_float("START_CASH_USDT", 1000.0)
ORDER_PCT = env_float("ORDER_PCT", 1.0)
FEE_RATE = env_float("FEE_RATE", 0.001)
SLIPPAGE_RATE = env_float("SLIPPAGE_RATE", 0.0005)

# ===== Backtest =====
BACKTEST_KLINES_LIMIT = env_int("BACKTEST_KLINES_LIMIT", 3000)


def validate_config():
    # Basic validation and sanity checks for important env vars
    if START_CASH_USDT <= 0 and PAPER_TRADING:
        raise ValueError("START_CASH_USDT must be > 0 when PAPER_TRADING is enabled")
    if not (0.0 <= ORDER_PCT <= 1.0):
        raise ValueError("ORDER_PCT must be between 0.0 and 1.0")
    if POLL_SEC <= 0:
        raise ValueError("POLL_SEC must be a positive integer")
    if USE_KILL_SWITCH and MAX_DAILY_DD_PCT <= 0:
        raise ValueError("MAX_DAILY_DD_PCT must be > 0 when USE_KILL_SWITCH is enabled")
