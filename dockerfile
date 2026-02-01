FROM python:3.12-slim

# ลด log buffer ให้เห็น log ทันที
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# ติดตั้ง dependencies ก่อนเพื่อให้ build cache ทำงานดี
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# copy ตัวสคริปต์
COPY btc_trend_breakout_bot.py /app/btc_trend_breakout_bot.py

# รันบอท
CMD ["python", "/app/btc_trend_breakout_bot.py"]
