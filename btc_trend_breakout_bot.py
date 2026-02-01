import os
import time
import json
import requests
import pandas as pd
from datetime import datetime, timezone, timedelta

# ================== ENV HELPERS ==================
def env_str(name: str, default: str) -> str:
    v = os.getenv(name)
    return v if (v is not None and v != "") else default

def env_int(name: str, default: int) -> int:
    v = os.getenv(name)
    if v is None or v == "":
        return default
    try:
        return int(v)
    except ValueError:
        raise ValueError(f"Invalid int env {name}={v}")

def env_float(name: str, default: float) -> float:
    v = os.getenv(name)
    if v is None or v == "":
        return default
    try:
        return float(v)
    except ValueError:
        raise ValueError(f"Invalid float env {name}={v}")

def env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None or v == "":
        return default
    return v.strip().lower() in ("1", "true", "yes", "y")

# ================== CONFIG ==================
SYMBOL = env_str("SYMBOL", "BTCUSDT")

POLL_SEC = env_int("POLL_SEC", 5)
KLINE_INTERVAL = env_str("KLINE_INTERVAL", "5m")
KLINES_LIMIT = env_int("KLINES_LIMIT", 800)

COOLDOWN_SEC = env_int("COOLDOWN_SEC", 20)     # เทรดถี่ -> ควรต่ำ
REENTRY_BARS = env_int("REENTRY_BARS", 1)      # ออกจากแล้ว ต้องรอกี่แท่งถึงเข้าใหม่

EMA5M_PERIOD = env_int("EMA_5M_PERIOD", 20)
ATR_PERIOD = env_int("ATR_PERIOD", 14)

# Trend filter 1h (optional)
EMA1H_FILTER = env_bool("EMA_FILTER_1H", True)
EMA1H_PERIOD = env_int("EMA_1H_PERIOD", 200)
EMA1H_KLINES_LIMIT = env_int("EMA_1H_KLINES_LIMIT", 400)

# Volume spike filter (5m)
USE_VOL_FILTER = env_bool("USE_VOL_FILTER", True)
VOL_SMA_PERIOD = env_int("VOL_SMA_PERIOD", 20)
VOL_SPIKE_MULT = env_float("VOL_SPIKE_MULT", 1.2)   # volume >= 1.2x SMA(volume,20)

# ATR volatility filter (5m)
USE_ATR_FILTER = env_bool("USE_ATR_FILTER", True)
MIN_ATR_PCT = env_float("MIN_ATR_PCT", 0.002)       # ATR/Close >= 0.2% ถึงค่อยเทรด (ปรับได้)

# Exit behavior
EXIT_ON_EMA_CROSS = env_bool("EXIT_ON_EMA_CROSS", True)

# Risk: TP/SL/Trailing (paper)
USE_TP_SL = env_bool("USE_TP_SL", True)
SL_ATR_MULT = env_float("SL_ATR_MULT", 1.0)
TP_ATR_MULT = env_float("TP_ATR_MULT", 1.2)
USE_TRAILING = env_bool("USE_TRAILING", True)
TRAIL_ATR_MULT = env_float("TRAIL_ATR_MULT", 1.0)   # trailing distance = 1.0*ATR
TRAIL_ACTIVATE_R = env_float("TRAIL_ACTIVATE_R", 0.8)  # เปิด trailing เมื่อกำไร >= 0.8R

# Kill switch (paper)
USE_KILL_SWITCH = env_bool("USE_KILL_SWITCH", True)
MAX_DAILY_DD_PCT = env_float("MAX_DAILY_DD_PCT", 3.0)  # ขาดทุนเกิน 3% จาก start_cash => หยุดเทรดวันนี้

STATE_FILE = env_str("STATE_FILE", "/app/data/btc_5m_longshort_state.json")

BOT_TOKEN = os.environ["TG_BOT_TOKEN"].strip().strip('"').strip("'")
CHAT_ID = os.environ["TG_CHAT_ID"].strip().strip('"').strip("'")

# Paper trading
PAPER_TRADING = env_bool("PAPER_TRADING", True)
START_CASH_USDT = env_float("START_CASH_USDT", 300.0)
ORDER_PCT = env_float("ORDER_PCT", 1.0)
FEE_RATE = env_float("FEE_RATE", 0.001)
SLIPPAGE_RATE = env_float("SLIPPAGE_RATE", 0.0005)

# Thailand timezone (UTC+7)
TZ_TH = timezone(timedelta(hours=7))

# ================== Telegram ==================
def tg_send(text: str):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text}
    r = requests.post(url, json=payload, timeout=10)
    r.raise_for_status()

def now_th_str() -> str:
    return datetime.now(TZ_TH).strftime("%Y-%m-%d %H:%M:%S")

def today_key_th() -> str:
    return datetime.now(TZ_TH).strftime("%Y-%m-%d")

# ================== Binance ==================
def binance_klines(symbol: str, interval: str, limit: int) -> pd.DataFrame:
    url = "https://api.binance.com/api/v3/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    data = requests.get(url, params=params, timeout=10).json()
    if isinstance(data, dict) and "code" in data:
        raise RuntimeError(f"Binance klines error: {data}")

    df = pd.DataFrame(data, columns=[
        "open_time","open","high","low","close","volume",
        "close_time","quote_av","trades","taker_base","taker_quote","ignore"
    ])
    for c in ["open","high","low","close","volume"]:
        df[c] = df[c].astype(float)
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df["close_time"] = pd.to_datetime(df["close_time"], unit="ms", utc=True)
    return df

def spot_price(symbol: str) -> float:
    url = "https://api.binance.com/api/v3/ticker/price"
    params = {"symbol": symbol}
    data = requests.get(url, params=params, timeout=10).json()
    if isinstance(data, dict) and "code" in data:
        raise RuntimeError(f"Binance price error: {data}")
    return float(data["price"])

# ================== Indicators ==================
def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()

def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low),
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()

def ema_1h_value(symbol: str) -> float:
    df = binance_klines(symbol, "1h", EMA1H_KLINES_LIMIT)
    if len(df) < EMA1H_PERIOD + 5:
        raise RuntimeError(f"Not enough 1h candles for EMA{EMA1H_PERIOD}")
    return float(ema(df["close"], EMA1H_PERIOD).iloc[-1])

# ================== State ==================
def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_state(state):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def init_state(state):
    if state:
        # reset day PnL reference if day changed
        if state.get("day") != today_key_th():
            state["day"] = today_key_th()
            state["day_start_value"] = None
            state["halt_today"] = False
            save_state(state)
        return state

    state = {
        "day": today_key_th(),
        "day_start_value": None,     # ตั้งเมื่อได้ราคาแรก
        "halt_today": False,

        "last_notify_ts": 0,
        "last_bar_ms": 0,
        "cooldown_until_bar_ms": 0,

        "position": "flat",  # flat | long | short
        "paper": {
            "enabled": PAPER_TRADING,
            "start_cash": START_CASH_USDT,
            "cash": START_CASH_USDT,

            "btc_long": 0.0,
            "avg_long": 0.0,

            "btc_short": 0.0,
            "avg_short": 0.0,

            "realized_pnl": 0.0,
            "trades": 0,

            # trailing state
            "trail_active": False,
            "trail_stop": 0.0,
            "entry_atr": 0.0,   # ATR ตอนเข้า
            "entry_price": 0.0
        }
    }
    save_state(state)

    tg_send(
        f"✅ BTC 5m LONG/SHORT bot started\n"
        f"Symbol={SYMBOL} Interval={KLINE_INTERVAL} POLL={POLL_SEC}s\n"
        f"EMA5m({EMA5M_PERIOD}) ATR({ATR_PERIOD})\n"
        f"VolFilter={'ON' if USE_VOL_FILTER else 'OFF'}: vol>={VOL_SPIKE_MULT}xSMA({VOL_SMA_PERIOD})\n"
        f"ATRFilter={'ON' if USE_ATR_FILTER else 'OFF'}: ATR/Close>={MIN_ATR_PCT*100:.2f}%\n"
        f"EMA1H({EMA1H_PERIOD}) filter={'ON' if EMA1H_FILTER else 'OFF'}\n"
        f"TP/SL={'ON' if USE_TP_SL else 'OFF'} Trail={'ON' if USE_TRAILING else 'OFF'}\n"
        f"KillSwitch={'ON' if USE_KILL_SWITCH else 'OFF'} DD={MAX_DAILY_DD_PCT:.2f}%\n"
        f"PaperTrading={'ON' if PAPER_TRADING else 'OFF'} StartCash={START_CASH_USDT:,.2f} USDT\n"
    )
    return state

def cooldown_ok(state) -> bool:
    return (time.time() - float(state.get("last_notify_ts", 0))) >= COOLDOWN_SEC

def mark_notified(state):
    state["last_notify_ts"] = time.time()

# ================== Paper trading accounting ==================
def apply_slippage(price: float, side: str) -> float:
    return price * (1 + SLIPPAGE_RATE) if side in ("buy", "buy_to_cover") else price * (1 - SLIPPAGE_RATE)

def portfolio_value(paper: dict, price: float) -> float:
    cash = float(paper["cash"])
    long_val = float(paper["btc_long"]) * price
    short_liab = float(paper["btc_short"]) * price
    return cash + long_val - short_liab

def notify_trade_summary(state, price_now: float, title: str):
    paper = state["paper"]
    pv = portfolio_value(paper, price_now)
    start = float(paper["start_cash"])
    pnl = pv - start
    pnl_pct = (pnl / start * 100.0) if start > 0 else 0.0
    tg_send(
        f"{title}\n"
        f"Now: {price_now:,.2f}\n"
        f"Cash: {float(paper['cash']):,.2f}\n"
        f"Pos: {state['position']}\n"
        f"Long: {float(paper['btc_long']):.8f} avg {float(paper['avg_long']):,.2f}\n"
        f"Short: {float(paper['btc_short']):.8f} avg {float(paper['avg_short']):,.2f}\n"
        f"Trail: {paper.get('trail_active', False)} stop {float(paper.get('trail_stop', 0.0)):,.2f}\n"
        f"Port: {pv:,.2f}\n"
        f"PnL: {pnl:,.2f} ({pnl_pct:+.2f}%)\n"
        f"Realized: {float(paper['realized_pnl']):,.2f} Trades: {int(paper['trades'])}"
    )

def paper_open_long(state, price: float, atr_at_entry: float, reason: str):
    paper = state["paper"]
    if not paper.get("enabled", False):
        return
    cash = float(paper["cash"])
    if cash <= 1e-6:
        return

    spend = cash * max(0.0, min(ORDER_PCT, 1.0))
    fill = apply_slippage(price, "buy")
    fee = spend * FEE_RATE
    qty = (spend - fee) / fill

    paper["cash"] = cash - spend
    paper["btc_long"] = qty
    paper["avg_long"] = fill
    paper["btc_short"] = 0.0
    paper["avg_short"] = 0.0

    paper["trades"] = int(paper["trades"]) + 1
    paper["entry_price"] = fill
    paper["entry_atr"] = atr_at_entry
    paper["trail_active"] = False
    paper["trail_stop"] = 0.0

    state["position"] = "long"
    tg_send(f"🧪 PAPER OPEN LONG | {reason}\nFill: {fill:,.2f} Qty: {qty:.8f} Fee: {fee:,.2f}")

def paper_close_long(state, price: float, reason: str):
    paper = state["paper"]
    qty = float(paper["btc_long"])
    if qty <= 1e-10:
        return
    fill = apply_slippage(price, "sell")
    gross = qty * fill
    fee = gross * FEE_RATE
    net = gross - fee

    avg = float(paper["avg_long"])
    realized = (fill - avg) * qty - fee

    paper["realized_pnl"] = float(paper["realized_pnl"]) + realized
    paper["cash"] = float(paper["cash"]) + net
    paper["btc_long"] = 0.0
    paper["avg_long"] = 0.0
    paper["trades"] = int(paper["trades"]) + 1
    paper["trail_active"] = False
    paper["trail_stop"] = 0.0

    state["position"] = "flat"
    tg_send(f"🧪 PAPER CLOSE LONG | {reason}\nFill: {fill:,.2f} Realized: {realized:,.2f} Fee: {fee:,.2f}")

def paper_open_short(state, price: float, atr_at_entry: float, reason: str):
    paper = state["paper"]
    if not paper.get("enabled", False):
        return
    cash = float(paper["cash"])
    if cash <= 1e-6:
        return

    notional = cash * max(0.0, min(ORDER_PCT, 1.0))
    fill = apply_slippage(price, "sell_short")
    fee = notional * FEE_RATE
    qty = (notional - fee) / fill

    paper["cash"] = cash + (notional - fee)
    paper["btc_short"] = qty
    paper["avg_short"] = fill
    paper["btc_long"] = 0.0
    paper["avg_long"] = 0.0

    paper["trades"] = int(paper["trades"]) + 1
    paper["entry_price"] = fill
    paper["entry_atr"] = atr_at_entry
    paper["trail_active"] = False
    paper["trail_stop"] = 0.0

    state["position"] = "short"
    tg_send(f"🧪 PAPER OPEN SHORT | {reason}\nFill: {fill:,.2f} Qty: {qty:.8f} Fee: {fee:,.2f}")

def paper_close_short(state, price: float, reason: str):
    paper = state["paper"]
    qty = float(paper["btc_short"])
    if qty <= 1e-10:
        return
    fill = apply_slippage(price, "buy_to_cover")
    gross = qty * fill
    fee = gross * FEE_RATE
    total_cost = gross + fee

    avg = float(paper["avg_short"])
    realized = (avg - fill) * qty - fee

    paper["realized_pnl"] = float(paper["realized_pnl"]) + realized
    paper["cash"] = float(paper["cash"]) - total_cost
    paper["btc_short"] = 0.0
    paper["avg_short"] = 0.0
    paper["trades"] = int(paper["trades"]) + 1
    paper["trail_active"] = False
    paper["trail_stop"] = 0.0

    state["position"] = "flat"
    tg_send(f"🧪 PAPER CLOSE SHORT | {reason}\nFill: {fill:,.2f} Realized: {realized:,.2f} Fee: {fee:,.2f}")

# ================== Strategy context ==================
def compute_5m_context():
    df = binance_klines(SYMBOL, KLINE_INTERVAL, KLINES_LIMIT)
    if len(df) < max(EMA5M_PERIOD, VOL_SMA_PERIOD, ATR_PERIOD) + 10:
        raise RuntimeError("Not enough 5m candles for indicators")

    df["ema5m"] = ema(df["close"], EMA5M_PERIOD)
    df["atr"] = atr(df, ATR_PERIOD)
    df["vol_sma"] = df["volume"].rolling(VOL_SMA_PERIOD).mean()

    last_closed = df.iloc[-2]
    prev_closed = df.iloc[-3]

    atr_v = float(last_closed["atr"]) if pd.notna(last_closed["atr"]) else float(df["atr"].dropna().iloc[-1])
    vol_sma_v = float(last_closed["vol_sma"]) if pd.notna(last_closed["vol_sma"]) else float(df["vol_sma"].dropna().iloc[-1])

    breakout_up = (last_closed["close"] > prev_closed["high"]) and (last_closed["close"] > last_closed["ema5m"])
    breakout_dn = (last_closed["close"] < prev_closed["low"]) and (last_closed["close"] < last_closed["ema5m"])

    # exit signals (structure + optional ema cross)
    exit_long = (last_closed["close"] < prev_closed["low"]) or (EXIT_ON_EMA_CROSS and last_closed["close"] < last_closed["ema5m"])
    exit_short = (last_closed["close"] > prev_closed["high"]) or (EXIT_ON_EMA_CROSS and last_closed["close"] > last_closed["ema5m"])

    # filters
    vol_ok = True
    if USE_VOL_FILTER:
        vol_ok = float(last_closed["volume"]) >= VOL_SPIKE_MULT * vol_sma_v

    atr_ok = True
    if USE_ATR_FILTER:
        atr_ok = (atr_v / float(last_closed["close"])) >= MIN_ATR_PCT

    return {
        "bar_close_ms": int(last_closed["close_time"].value // 10**6),
        "close": float(last_closed["close"]),
        "prev_high": float(prev_closed["high"]),
        "prev_low": float(prev_closed["low"]),
        "ema5m": float(last_closed["ema5m"]),
        "atr": atr_v,
        "volume": float(last_closed["volume"]),
        "vol_sma": vol_sma_v,
        "vol_ok": bool(vol_ok),
        "atr_ok": bool(atr_ok),
        "breakout_up": bool(breakout_up),
        "breakout_dn": bool(breakout_dn),
        "exit_long": bool(exit_long),
        "exit_short": bool(exit_short),
    }

# ================== TP/SL/Trailing checks ==================
def update_trailing_and_maybe_exit(state, price_now: float):
    if not USE_TP_SL and not USE_TRAILING:
        return

    paper = state["paper"]
    pos = state["position"]
    entry = float(paper.get("entry_price", 0.0))
    entry_atr = float(paper.get("entry_atr", 0.0)) or 0.0
    if entry <= 0 or entry_atr <= 0:
        return

    # compute fixed TP/SL levels
    if pos == "long":
        sl = entry - SL_ATR_MULT * entry_atr
        tp = entry + TP_ATR_MULT * entry_atr
        r = (price_now - entry) / (entry_atr * SL_ATR_MULT) if (entry_atr * SL_ATR_MULT) > 0 else 0.0

        # activate trailing
        if USE_TRAILING and (not paper.get("trail_active", False)) and r >= TRAIL_ACTIVATE_R:
            paper["trail_active"] = True
            paper["trail_stop"] = price_now - TRAIL_ATR_MULT * entry_atr
            tg_send(f"🟡 TRAIL ON (LONG)\nStop init ~ {paper['trail_stop']:,.2f}")

        # update trailing stop
        if USE_TRAILING and paper.get("trail_active", False):
            new_stop = price_now - TRAIL_ATR_MULT * entry_atr
            if new_stop > float(paper.get("trail_stop", 0.0)):
                paper["trail_stop"] = new_stop

        # exits
        if USE_TP_SL and price_now <= sl:
            tg_send(f"🛑 STOP LOSS (LONG)\nNow {price_now:,.2f} <= SL {sl:,.2f}")
            paper_close_long(state, price_now, reason="SL hit")
            notify_trade_summary(state, price_now, "📌 After SL LONG")
        elif USE_TP_SL and price_now >= tp:
            tg_send(f"🎯 TAKE PROFIT (LONG)\nNow {price_now:,.2f} >= TP {tp:,.2f}")
            paper_close_long(state, price_now, reason="TP hit")
            notify_trade_summary(state, price_now, "📌 After TP LONG")
        elif USE_TRAILING and paper.get("trail_active", False) and price_now <= float(paper.get("trail_stop", 0.0)):
            tg_send(f"🏁 TRAILING STOP (LONG)\nNow {price_now:,.2f} <= Trail {float(paper.get('trail_stop', 0.0)):,.2f}")
            paper_close_long(state, price_now, reason="TRAIL hit")
            notify_trade_summary(state, price_now, "📌 After TRAIL LONG")

    elif pos == "short":
        sl = entry + SL_ATR_MULT * entry_atr
        tp = entry - TP_ATR_MULT * entry_atr
        r = (entry - price_now) / (entry_atr * SL_ATR_MULT) if (entry_atr * SL_ATR_MULT) > 0 else 0.0

        if USE_TRAILING and (not paper.get("trail_active", False)) and r >= TRAIL_ACTIVATE_R:
            paper["trail_active"] = True
            paper["trail_stop"] = price_now + TRAIL_ATR_MULT * entry_atr
            tg_send(f"🟡 TRAIL ON (SHORT)\nStop init ~ {paper['trail_stop']:,.2f}")

        if USE_TRAILING and paper.get("trail_active", False):
            new_stop = price_now + TRAIL_ATR_MULT * entry_atr
            if float(paper.get("trail_stop", 0.0)) == 0.0 or new_stop < float(paper.get("trail_stop", 0.0)):
                paper["trail_stop"] = new_stop

        if USE_TP_SL and price_now >= sl:
            tg_send(f"🛑 STOP LOSS (SHORT)\nNow {price_now:,.2f} >= SL {sl:,.2f}")
            paper_close_short(state, price_now, reason="SL hit")
            notify_trade_summary(state, price_now, "📌 After SL SHORT")
        elif USE_TP_SL and price_now <= tp:
            tg_send(f"🎯 TAKE PROFIT (SHORT)\nNow {price_now:,.2f} <= TP {tp:,.2f}")
            paper_close_short(state, price_now, reason="TP hit")
            notify_trade_summary(state, price_now, "📌 After TP SHORT")
        elif USE_TRAILING and paper.get("trail_active", False) and price_now >= float(paper.get("trail_stop", 0.0)):
            tg_send(f"🏁 TRAILING STOP (SHORT)\nNow {price_now:,.2f} >= Trail {float(paper.get('trail_stop', 0.0)):,.2f}")
            paper_close_short(state, price_now, reason="TRAIL hit")
            notify_trade_summary(state, price_now, "📌 After TRAIL SHORT")

# ================== Kill switch ==================
def update_kill_switch(state, price_now: float):
    if not USE_KILL_SWITCH:
        return

    paper = state["paper"]
    pv = portfolio_value(paper, price_now)

    if state.get("day_start_value") is None:
        state["day_start_value"] = pv
        return

    day_start = float(state["day_start_value"])
    dd_pct = (day_start - pv) / day_start * 100.0 if day_start > 0 else 0.0

    if dd_pct >= MAX_DAILY_DD_PCT:
        if not state.get("halt_today", False):
            state["halt_today"] = True
            tg_send(f"🧯 KILL SWITCH ON\nDaily DD {dd_pct:.2f}% >= {MAX_DAILY_DD_PCT:.2f}%\nStop trading for today.")
        return

# ================== Main loop ==================
def main():
    state = init_state(load_state())

    while True:
        try:
            # reset day keys
            if state.get("day") != today_key_th():
                state["day"] = today_key_th()
                state["day_start_value"] = None
                state["halt_today"] = False
                save_state(state)

            price_now = spot_price(SYMBOL)

            # TP/SL/trailing can exit anytime (not only at candle close)
            if state.get("position") in ("long", "short"):
                update_trailing_and_maybe_exit(state, price_now)
                save_state(state)

            # update kill switch based on current pv
            update_kill_switch(state, price_now)
            save_state(state)

            # if halted, only manage open position exits, no new entry
            halted = bool(state.get("halt_today", False))

            # compute candle-based signals
            ctx = compute_5m_context()

            # no duplicate on same closed bar
            if ctx["bar_close_ms"] == int(state.get("last_bar_ms", 0)):
                time.sleep(POLL_SEC)
                continue

            state["last_bar_ms"] = ctx["bar_close_ms"]
            pos = state.get("position", "flat")

            # optional 1h filter
            ema1h = None
            allow_long = True
            allow_short = True
            if EMA1H_FILTER:
                ema1h = ema_1h_value(SYMBOL)
                allow_long = price_now > ema1h
                allow_short = price_now < ema1h

            # require filters for entry
            entry_filters_ok = ctx["vol_ok"] and ctx["atr_ok"]

            now_th = now_th_str()

            # ===== EXIT on candle logic =====
            if pos == "long" and ctx["exit_long"] and cooldown_ok(state):
                exit_p = ctx["close"]
                tg_send(
                    f"🔴 5m EXIT LONG (signal)\n[{now_th} TH]\n"
                    f"Close {ctx['close']:,.2f} | EMA5m {ctx['ema5m']:,.2f}\n"
                    f"Vol {ctx['volume']:.2f} (SMA {ctx['vol_sma']:.2f}) ok={ctx['vol_ok']} ATRok={ctx['atr_ok']}\n"
                    + (f"EMA1H({EMA1H_PERIOD}) {ema1h:,.2f}\n" if ema1h is not None else "")
                )
                paper_close_long(state, exit_p, reason="Candle exit signal")
                notify_trade_summary(state, price_now, "📌 After EXIT LONG")
                mark_notified(state)
                save_state(state)
                time.sleep(POLL_SEC)
                continue

            if pos == "short" and ctx["exit_short"] and cooldown_ok(state):
                exit_p = ctx["close"]
                tg_send(
                    f"🟢 5m EXIT SHORT (signal)\n[{now_th} TH]\n"
                    f"Close {ctx['close']:,.2f} | EMA5m {ctx['ema5m']:,.2f}\n"
                    f"Vol {ctx['volume']:.2f} (SMA {ctx['vol_sma']:.2f}) ok={ctx['vol_ok']} ATRok={ctx['atr_ok']}\n"
                    + (f"EMA1H({EMA1H_PERIOD}) {ema1h:,.2f}\n" if ema1h is not None else "")
                )
                paper_close_short(state, exit_p, reason="Candle exit signal")
                notify_trade_summary(state, price_now, "📌 After EXIT SHORT")
                mark_notified(state)
                save_state(state)
                time.sleep(POLL_SEC)
                continue

            # ===== REENTRY guard =====
            # ถ้าเพิ่งเทรด ให้เว้น REENTRY_BARS แท่งก่อน
            # ทำโดยอาศัย cooldown_until_bar_ms (ตั้งเป็น bar_close_ms ปัจจุบัน + N bars)
            if int(state.get("cooldown_until_bar_ms", 0)) and ctx["bar_close_ms"] < int(state["cooldown_until_bar_ms"]):
                save_state(state)
                time.sleep(POLL_SEC)
                continue

            # ===== ENTRY (only when flat and not halted) =====
            if (not halted) and pos == "flat" and entry_filters_ok and cooldown_ok(state):
                # Open long
                if ctx["breakout_up"] and allow_long:
                    entry = ctx["close"]
                    sl = entry - SL_ATR_MULT * ctx["atr"]
                    tp = entry + TP_ATR_MULT * ctx["atr"]
                    tg_send(
                        f"🟢 5m OPEN LONG\n[{now_th} TH]\n"
                        f"Close {ctx['close']:,.2f} > PrevHigh {ctx['prev_high']:,.2f}\n"
                        f"EMA5m {ctx['ema5m']:,.2f}\n"
                        f"Vol {ctx['volume']:.2f} >= {VOL_SPIKE_MULT}xSMA {ctx['vol_sma']:.2f}\n"
                        f"ATR {ctx['atr']:,.2f} ({ctx['atr']/ctx['close']*100:.2f}%)\n"
                        + (f"EMA1H({EMA1H_PERIOD}) {ema1h:,.2f}\n" if ema1h is not None else "")
                        + (f"SL~{sl:,.2f} TP~{tp:,.2f}\n" if USE_TP_SL else "")
                    )
                    paper_open_long(state, entry, ctx["atr"], reason="Breakout up + filters")
                    notify_trade_summary(state, price_now, "📌 After OPEN LONG")
                    mark_notified(state)

                    # re-entry guard
                    # ประมาณ 5m ต่อแท่ง -> เพิ่ม N*5 นาที เป็น ms
                    state["cooldown_until_bar_ms"] = ctx["bar_close_ms"] + REENTRY_BARS * 5 * 60 * 1000
                    save_state(state)

                # Open short
                elif ctx["breakout_dn"] and allow_short:
                    entry = ctx["close"]
                    sl = entry + SL_ATR_MULT * ctx["atr"]
                    tp = entry - TP_ATR_MULT * ctx["atr"]
                    tg_send(
                        f"🔴 5m OPEN SHORT\n[{now_th} TH]\n"
                        f"Close {ctx['close']:,.2f} < PrevLow {ctx['prev_low']:,.2f}\n"
                        f"EMA5m {ctx['ema5m']:,.2f}\n"
                        f"Vol {ctx['volume']:.2f} >= {VOL_SPIKE_MULT}xSMA {ctx['vol_sma']:.2f}\n"
                        f"ATR {ctx['atr']:,.2f} ({ctx['atr']/ctx['close']*100:.2f}%)\n"
                        + (f"EMA1H({EMA1H_PERIOD}) {ema1h:,.2f}\n" if ema1h is not None else "")
                        + (f"SL~{sl:,.2f} TP~{tp:,.2f}\n" if USE_TP_SL else "")
                    )
                    paper_open_short(state, entry, ctx["atr"], reason="Breakout down + filters")
                    notify_trade_summary(state, price_now, "📌 After OPEN SHORT")
                    mark_notified(state)

                    state["cooldown_until_bar_ms"] = ctx["bar_close_ms"] + REENTRY_BARS * 5 * 60 * 1000
                    save_state(state)

            save_state(state)

        except Exception as e:
            try:
                tg_send(f"⚠️ [ERROR] {e}")
            except Exception:
                pass

        time.sleep(POLL_SEC)

if __name__ == "__main__":
    main()
