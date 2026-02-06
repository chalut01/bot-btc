# 📈 BTC 5m Long/Short Trend Bot  
**Telegram Alert + Paper Trading (Docker-ready)**

บอทนี้เป็น **บอทเทรดสั้น (5 นาที)** แนว **trend-following**  
ออกแบบมาเพื่อ:
- แจ้งสัญญาณ **เข้า / ออก (Long & Short)** ผ่าน Telegram
- จำลองการเทรดแบบ **Paper Trading** (ดู PnL จริงจัง)
- ลด fake breakout ด้วย volume + volatility filter
- ใช้ได้ทันทีผ่าน Docker / docker-compose

> ⚠️ ใช้เพื่อการทดลองและการศึกษาเท่านั้น ไม่ใช่คำแนะนำการลงทุน

---

## ✨ Features Overview

### ✅ 1. Timeframe 5 นาที (Scalping / Intraday)
- ใช้แท่งเทียน **5m จาก Binance**
- พิจารณาจาก “แท่งที่ปิดแล้ว” → ลดสัญญาณหลอก
- เหมาะกับการเข้า–ออกถี่

---

### ✅ 2. เข้า/ออกได้ทั้งขาขึ้นและขาลง
รองรับ 3 สถานะ:
- `flat`  → ไม่ถือสถานะ
- `long`  → เล่นขาขึ้น
- `short` → เล่นขาลง

---

### ✅ 3. Breakout / Breakdown ตามเทรนด์
**เข้า Long**
- 5m close > high ของแท่งก่อนหน้า
- close อยู่เหนือ EMA(5m)

**เข้า Short**
- 5m close < low ของแท่งก่อนหน้า
- close อยู่ใต้ EMA(5m)

**ออก**
- หลุดโครงสร้าง (prev high / low)
- หรือ EMA cross (เปิด/ปิดได้)

---

### ✅ 4. Volume Spike Filter (ลด Fake Breakout)
เข้าเทรดเฉพาะตอน “มีแรงจริง”

volume ล่าสุด ≥ VOL_SPIKE_MULT × SMA(volume)

ตัวอย่าง:
- `1.2 × SMA(20)`

---

### ✅ 5. ATR Volatility Filter (กันตลาดนิ่ง)
ไม่เทรดตอนตลาดแคบ/นิ่งเกิน
ATR / Close ≥ MIN_ATR_PCT
ตัวอย่าง:
- `0.002 = 0.2%`

---

### ✅ 6. Trend Filter จาก Timeframe ใหญ่ (1h)
ช่วยให้เทรด “ไปทางเดียวกับเทรนด์ใหญ่”

- Long เฉพาะตอน `ราคา > EMA200 (1h)`
- Short เฉพาะตอน `ราคา < EMA200 (1h)`

เปิด/ปิดได้ด้วย env

---

### ✅ 7. TP / SL + Trailing Stop (Paper Trading)
ระบบจำลองการเทรดครบ:
- Stop Loss จาก ATR
- Take Profit จาก ATR
- Trailing Stop (ATR-based)
- เปิด trailing เมื่อกำไรถึงระดับ R ที่กำหนด

---

### ✅ 8. Kill Switch (หยุดเทรดเมื่อขาดทุนเกินกำหนด)
เพื่อความมีวินัย:
- ถ้า PnL ของวันนั้นติดลบเกิน `%` ที่ตั้งไว้
- บอทจะ **หยุดเปิดสถานะใหม่ทั้งวัน**
- ยังดูแลสถานะเดิม (SL / trailing) ต่อ

---

### ✅ 9. Telegram Notification (ไม่ spam)
แจ้งเตือนเฉพาะเหตุการณ์สำคัญ:
- OPEN LONG / OPEN SHORT
- EXIT / SL / TP / TRAILING
- Summary หลังจบแต่ละ trade
- Kill switch trigger
- Error สำคัญ

❌ ไม่มีรายงานรายชั่วโมงรก ๆ

---

## 🧱 Tech Stack
- Python 3
- Binance Public API (no API key)
- Telegram Bot API
- Docker / docker-compose
- State เก็บใน JSON (รองรับ restart container)

---

## 📂 Project Structure

BTC_BOT/
├─ btc_trend_breakout_bot.py
├─ Dockerfile
├─ docker-compose.yml
├─ requirements.txt
├─ .env
└─ data/
└─ btc_5m_longshort_state.json

---

## 🚀 Quick Start

ทำตามขั้นตอนนี้ได้เลย ใช้เวลาไม่เกิน 5 นาที

Note: This project requires Python 3.8+ (the code uses Python 3 syntax). If your system's `python` points to Python 2, use `python3` or the `py -3` launcher on Windows.

---

### 1️⃣ เตรียม Telegram Bot
1. คุยกับ **@BotFather**
2. สร้าง bot ใหม่ → ได้ `TG_BOT_TOKEN`
3. ส่งข้อความอะไรก็ได้เข้า bot ของคุณ
4. เปิดลิงก์นี้ใน browser (แทน token):
5. ดูค่า `chat.id` → นี่คือ `TG_CHAT_ID`

---

### 2️⃣ สร้างไฟล์ `.env`
> ❗ สำคัญมาก: **ห้ามใส่เครื่องหมาย quote (`"`) ครอบค่า**

ตัวอย่าง `.env` ขั้นต่ำ:
```env
TG_BOT_TOKEN=123456:abcdefg
TG_CHAT_ID=123456789
SYMBOL=BTCUSDT
KLINE_INTERVAL=5m
POLL_SEC=5
COOLDOWN_SEC=20
REENTRY_BARS=1
EMA_5M_PERIOD=20
EMA_FILTER_1H=true
EMA_1H_PERIOD=200
USE_VOL_FILTER=true
VOL_SMA_PERIOD=20
VOL_SPIKE_MULT=1.2
USE_ATR_FILTER=true
MIN_ATR_PCT=0.002
USE_TP_SL=true
SL_ATR_MULT=1.0
TP_ATR_MULT=1.2
USE_TRAILING=true
TRAIL_ATR_MULT=1.0
TRAIL_ACTIVATE_R=0.8
USE_KILL_SWITCH=true
MAX_DAILY_DD_PCT=3.0
PAPER_TRADING=true
START_CASH_USDT=300
ORDER_PCT=1.0
FEE_RATE=0.001
SLIPPAGE_RATE=0.0005
STATE_FILE=/app/data/btc_5m_longshort_state.json

---

### 3️⃣ RUN
Docker (recommended):

	docker compose up -d --build
	docker compose logs -f

Local (without Docker):

WSL / Linux / macOS:

	python3 -m pip install -r requirements.txt
	python3 -m btc_bot.backtest --strategy trend --limit 200

PowerShell (Windows):

	py -3 -m pip install -r requirements.txt
	py -3 -m btc_bot.backtest --strategy trend --limit 200

Or use the provided helper scripts:

WSL / Linux: `./scripts/run_backtest.sh [strategy] [limit]`
PowerShell: `./scripts/run_backtest.ps1 -strategy trend -limit 200`
