from .. import config
from ..market.indicators import ema, atr

def build_context(df):
    df["ema5m"] = ema(df["close"], config.EMA_5M_PERIOD)
    df["atr"] = atr(df, config.ATR_PERIOD)
    df["vol_sma"] = df["volume"].rolling(config.VOL_SMA_PERIOD).mean()

    last = df.iloc[-2]  # closed
    prev = df.iloc[-3]

    atr_v = float(last["atr"])
    vol_sma_v = float(last["vol_sma"]) if config.USE_VOL_FILTER else float("nan")

    breakout_up = (last["close"] > prev["high"]) and (last["close"] > last["ema5m"])
    breakout_dn = (last["close"] < prev["low"]) and (last["close"] < last["ema5m"])

    # exits
    exit_long = (last["close"] < prev["low"]) or (config.USE_TRAILING and last["close"] < last["ema5m"])
    exit_short = (last["close"] > prev["high"]) or (config.USE_TRAILING and last["close"] > last["ema5m"])

    # filters
    vol_ok = True
    if config.USE_VOL_FILTER:
        vol_ok = float(last["volume"]) >= config.VOL_SPIKE_MULT * vol_sma_v

    atr_ok = True
    if config.USE_ATR_FILTER:
        atr_ok = (atr_v / float(last["close"])) >= config.MIN_ATR_PCT

    return {
        "bar_close_ms": int(last["close_time"].value // 10**6),
        "close": float(last["close"]),
        "prev_high": float(prev["high"]),
        "prev_low": float(prev["low"]),
        "ema5m": float(last["ema5m"]),
        "atr": atr_v,
        "volume": float(last["volume"]),
        "vol_sma": vol_sma_v,
        "vol_ok": bool(vol_ok),
        "atr_ok": bool(atr_ok),
        "breakout_up": bool(breakout_up),
        "breakout_dn": bool(breakout_dn),
        "exit_long": bool(exit_long),
        "exit_short": bool(exit_short),
    }

def decide(ctx, position, allow_long=True, allow_short=True):
    # returns action: "open_long", "open_short", "close_long", "close_short", "hold"
    if position == "long" and ctx["exit_long"]:
        return "close_long"
    if position == "short" and ctx["exit_short"]:
        return "close_short"

    if position == "flat" and ctx["vol_ok"] and ctx["atr_ok"]:
        if ctx["breakout_up"] and allow_long:
            return "open_long"
        if ctx["breakout_dn"] and allow_short:
            return "open_short"

    return "hold"
