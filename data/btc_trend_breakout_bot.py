import os
import time
import json
import requests
import pandas as pd
from datetime import datetime, timezone, timedelta

# ================== CONFIG ==================
SYMBOL = "BTCUSDT"

POLL_SEC = 5          # ความถี่เช็คราคา (5 วิ กำลังดี)
CONFIRM_SEC = 60      # ต้อง “ยืน” กี่วิถึงคอนเฟิร์มสัญญาณ (30–60)
COOLDOWN_SEC = 180    # กันสแปม (แจ้งแล้วพัก 3 นาที)
STATE_FILE = "/app/data/btc_trend_breakout_state.json"

# ATR-based risk params (ปรับตามสไตล์)
SL_ATR = 0.8          # stop-loss = entry - 0.8*ATR (long) / entry + 0.8*ATR (down)
TP_ATR = 1.2          # take-profit แบบขั้นต่ำจาก entry (ถ้าแนวต้าน/รับใกล้กว่า ใช้อันนั้น)

# Thailand timezone (UTC+7)
TZ_TH = timezone(timedelta(hours=7))

BOT_TOKEN = os.environ["TG_BOT_TOKEN"]
CHAT_ID = os.environ["TG_CHAT_ID"]
# ===========================================


# -------- Telegram --------
def tg_send(text: str):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text}
    r = requests.post(url, json=payload, timeout=10)
    r.raise_for_status()


# -------- Time helpers --------
def today_key_th() -> str:
    return datetime.now(TZ_TH).strftime("%Y-%m-%d")

def now_th_str() -> str:
    return datetime.now(TZ_TH).strftime("%Y-%m-%d %H:%M:%S")


# -------- Market data (Binance public) --------
def get_daily_klines(limit=120) -> pd.DataFrame:
    url = "https://api.binance.com/api/v3/klines"
    params = {"symbol": SYMBOL, "interval": "1d", "limit": limit}
    data = requests.get(url, params=params, timeout=10).json()

    df = pd.DataFrame(data, columns=[
        "open_time","open","high","low","close","volume",
        "close_time","quote_av","trades","taker_base","taker_quote","ignore"
    ])
    for c in ["open","high","low","close"]:
        df[c] = df[c].astype(float)
    return df

def get_spot_price() -> float:
    url = "https://api.binance.com/api/v3/ticker/price"
    params = {"symbol": SYMBOL}
    data = requests.get(url, params=params, timeout=10).json()
    return float(data["price"])


# -------- Indicators --------
def atr14(df: pd.DataFrame) -> float:
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low),
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    v = atr.iloc[-1]
    if pd.isna(v):
        v = atr.dropna().iloc[-1]
    return float(v)

def pivot_levels(y_high, y_low, y_close):
    P = (y_high + y_low + y_close) / 3.0
    R1 = 2*P - y_low
    S1 = 2*P - y_high
    R2 = P + (y_high - y_low)
    S2 = P - (y_high - y_low)
    return {"P": P, "R1": R1, "S1": S1, "R2": R2, "S2": S2}


# -------- State --------
def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def build_today_context():
    df = get_daily_klines()
    y = df.iloc[-2]  # ใช้เมื่อวานสำหรับ level วันนี้
    lv = pivot_levels(y.high, y.low, y.close)
    a = atr14(df)
    return {"levels": {k: float(v) for k, v in lv.items()}, "atr14": float(a)}

def reset_day_if_needed(state):
    tk = today_key_th()
    if state.get("date") != tk:
        ctx = build_today_context()
        state = {
            "date": tk,
            "levels": ctx["levels"],
            "atr14": ctx["atr14"],
            "last_notify_ts": 0,
            # สัญญาณที่แจ้งไปแล้ว (กันยิงซ้ำ)
            "fired": {"R1": False, "R2": False, "S1": False, "S2": False},
            # ตัวจับเวลายืนราคา (เริ่มเมื่อข้ามเงื่อนไข)
            "hold_since": {"R1": None, "R2": None, "S1": None, "S2": None},
        }
        save_state(state)

        lv = state["levels"]
        a = state["atr14"]
        tg_send(
            f"📌 BTC Trend Breakout Levels ({tk} TH)\n"
            f"P:  {lv['P']:,.2f}\n"
            f"R1: {lv['R1']:,.2f} | R2: {lv['R2']:,.2f}\n"
            f"S1: {lv['S1']:,.2f} | S2: {lv['S2']:,.2f}\n"
            f"ATR(14D): {a:,.2f}\n"
            f"Confirm: touch + hold {CONFIRM_SEC}s\n"
            f"Mode: trend-following (breakout/breakdown)\n"
        )
    return state

def cooldown_ok(state) -> bool:
    return (time.time() - state.get("last_notify_ts", 0)) >= COOLDOWN_SEC

def mark_notified(state):
    state["last_notify_ts"] = time.time()


# -------- Signal logic: touch + hold --------
def check_hold_and_fire(state, price):
    lv = state["levels"]
    a = state["atr14"]
    now = time.time()
    now_th = now_th_str()

    def start_or_reset(key, condition: bool):
        """เริ่มนับเวลายืน ถ้าเงื่อนไขจริง; ถ้าไม่จริงรีเซ็ต"""
        if condition:
            if state["hold_since"][key] is None:
                state["hold_since"][key] = now
        else:
            state["hold_since"][key] = None

    def held_long_enough(key) -> bool:
        t0 = state["hold_since"][key]
        return (t0 is not None) and ((now - t0) >= CONFIRM_SEC)

    # Trend-follow breakout LONG:
    # - ราคาอยู่เหนือ R1 ต่อเนื่อง -> BUY breakout
    # - ราคาอยู่เหนือ R2 ต่อเนื่อง -> “Add / TP target extension” (แจ้งเป็นขั้น)
    start_or_reset("R1", price > lv["R1"])
    start_or_reset("R2", price > lv["R2"])

    # Trend-follow breakdown (downtrend):
    # - ราคาอยู่ใต้ S1 ต่อเนื่อง -> SELL/Reduce (หรือ SHORT)
    # - ราคาอยู่ใต้ S2 ต่อเนื่อง -> Strong breakdown
    start_or_reset("S1", price < lv["S1"])
    start_or_reset("S2", price < lv["S2"])

    # ----- Fire rules (once per day per level) -----
    # Breakout above R1 -> BUY
    if (not state["fired"]["R1"]) and held_long_enough("R1") and cooldown_ok(state):
        entry = max(price, lv["R1"])  # แนวคิด: เข้าเมื่อคอนเฟิร์มแล้ว
        sl = entry - SL_ATR * a
        tp_min = entry + TP_ATR * a
        tp_lvl = lv["R2"]  # เป้าหมายตามแนวต้านถัดไป
        tp = max(tp_min, tp_lvl)

        tg_send(
            f"🟢 BUY (Breakout Confirmed)\n"
            f"[{now_th} TH]\n"
            f"Price: {price:,.2f} (held > R1 {lv['R1']:,.2f} for {CONFIRM_SEC}s)\n"
            f"Suggested entry ~ {entry:,.2f}\n"
            f"SL ~ {sl:,.2f}\n"
            f"TP ~ {tp:,.2f} (max of R2 / ATR target)\n"
        )
        state["fired"]["R1"] = True
        mark_notified(state)

    # Breakout above R2 -> extension / tighten trailing
    if (not state["fired"]["R2"]) and held_long_enough("R2") and cooldown_ok(state):
        tg_send(
            f"🔥 Breakout Extension\n"
            f"[{now_th} TH]\n"
            f"Price: {price:,.2f} (held > R2 {lv['R2']:,.2f} for {CONFIRM_SEC}s)\n"
            f"Idea: consider taking partial profit / tighten trailing stop\n"
        )
        state["fired"]["R2"] = True
        mark_notified(state)

    # Breakdown below S1 -> SELL/Reduce
    if (not state["fired"]["S1"]) and held_long_enough("S1") and cooldown_ok(state):
        exit_price = min(price, lv["S1"])
        # ถ้าคุณ “ถือ long อยู่” => ใช้นี่เป็นโซนลด/ออก
        # ถ้าคุณเล่น short => นี่คือ entry short (ปรับข้อความได้)
        rebound_stop = exit_price + SL_ATR * a
        tp_min = exit_price - TP_ATR * a
        tp_lvl = lv["S2"]
        tp = min(tp_min, tp_lvl)

        tg_send(
            f"🔴 SELL/REDUCE (Breakdown Confirmed)\n"
            f"[{now_th} TH]\n"
            f"Price: {price:,.2f} (held < S1 {lv['S1']:,.2f} for {CONFIRM_SEC}s)\n"
            f"Suggested action zone ~ {exit_price:,.2f}\n"
            f"Risk (if short): stop ~ {rebound_stop:,.2f}\n"
            f"Downside target ~ {tp:,.2f} (min of S2 / ATR target)\n"
        )
        state["fired"]["S1"] = True
        mark_notified(state)

    # Breakdown below S2 -> strong down extension
    if (not state["fired"]["S2"]) and held_long_enough("S2") and cooldown_ok(state):
        tg_send(
            f"⚠️ Strong Breakdown\n"
            f"[{now_th} TH]\n"
            f"Price: {price:,.2f} (held < S2 {lv['S2']:,.2f} for {CONFIRM_SEC}s)\n"
            f"Idea: avoid catching falling knife; wait for structure/reclaim\n"
        )
        state["fired"]["S2"] = True
        mark_notified(state)

    return state


def main():
    tg_send("✅ BTC trend-breakout bot started")
    state = load_state()
    state = reset_day_if_needed(state)

    while True:
        try:
            state = reset_day_if_needed(state)
            price = get_spot_price()
            state = check_hold_and_fire(state, price)
            save_state(state)
        except Exception as e:
            try:
                tg_send(f"⚠️ [ERROR] {e}")
            except Exception:
                pass
        time.sleep(POLL_SEC)


if __name__ == "__main__":
    main()
