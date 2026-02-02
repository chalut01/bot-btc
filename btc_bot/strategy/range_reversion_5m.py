from .. import config
import pandas as pd

def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def bollinger(series: pd.Series, period: int = 20, mult: float = 2.0):
    ma = series.rolling(period).mean()
    sd = series.rolling(period).std()
    upper = ma + mult * sd
    lower = ma - mult * sd
    return ma, upper, lower

# Tunables via env (optional)
BB_PERIOD = int(config.env_int("BB_PERIOD", 20))
BB_MULT = float(config.env_float("BB_MULT", 2.0))
RSI_PERIOD = int(config.env_int("RSI_PERIOD", 14))
RSI_BUY = float(config.env_float("RSI_BUY", 30))
RSI_SELL = float(config.env_float("RSI_SELL", 70))

def build_context(df):
    df["rsi"] = rsi(df["close"], RSI_PERIOD)
    mid, up, lo = bollinger(df["close"], BB_PERIOD, BB_MULT)
    df["bb_mid"] = mid
    df["bb_up"] = up
    df["bb_lo"] = lo

    last = df.iloc[-2]  # closed
    return {
        "bar_close_ms": int(last["close_time"].value // 10**6),
        "close": float(last["close"]),
        "bb_mid": float(last["bb_mid"]),
        "bb_up": float(last["bb_up"]),
        "bb_lo": float(last["bb_lo"]),
        "rsi": float(last["rsi"]),
    }

def decide(ctx, position, allow_long=True, allow_short=True):
    # mean-reversion:
    # open long when close < lower band and RSI low
    # open short when close > upper band and RSI high
    # exit at mid band
    if position == "long":
        if ctx["close"] >= ctx["bb_mid"]:
            return "close_long"
        return "hold"

    if position == "short":
        if ctx["close"] <= ctx["bb_mid"]:
            return "close_short"
        return "hold"

    if position == "flat":
        if allow_long and ctx["close"] <= ctx["bb_lo"] and ctx["rsi"] <= RSI_BUY:
            return "open_long"
        if allow_short and ctx["close"] >= ctx["bb_up"] and ctx["rsi"] >= RSI_SELL:
            return "open_short"

    return "hold"
