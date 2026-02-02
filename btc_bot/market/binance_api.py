import requests
import pandas as pd
from ..log_setup import setup_logger

logger = setup_logger()

def spot_price(symbol: str) -> float:
    url = "https://api.binance.com/api/v3/ticker/price"
    data = requests.get(url, params={"symbol": symbol}, timeout=10).json()
    if isinstance(data, dict) and "code" in data:
        logger.error(f"Binance price error: {data}")
        raise RuntimeError(f"Binance price error: {data}")

    price = float(data["price"])
    logger.info(f"[SCRAPE] {symbol} price = {price:,.2f} USDT")
    return price

def klines(symbol: str, interval: str, limit: int) -> pd.DataFrame:
    url = "https://api.binance.com/api/v3/klines"
    data = requests.get(url, params={"symbol": symbol, "interval": interval, "limit": limit}, timeout=10).json()
    if isinstance(data, dict) and "code" in data:
        logger.error(f"Binance klines error: {data}")
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
