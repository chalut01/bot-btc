import pandas as pd
from ..log_setup import setup_logger
from ..http import get_session

logger = setup_logger()


def _session():
    # module-level helper so callers get retries/backoff
    return get_session()


def spot_price(symbol: str) -> float:
    url = "https://api.binance.com/api/v3/ticker/price"
    s = _session()
    r = s.get(url, params={"symbol": symbol}, timeout=10)
    data = r.json()
    if isinstance(data, dict) and "code" in data:
        logger.error(f"Binance price error: {data}")
        raise RuntimeError(f"Binance price error: {data}")

    price = float(data["price"])
    logger.info(f"[SCRAPE] {symbol} price = {price:,.2f} USDT")
    return price


def klines(symbol: str, interval: str, limit: int) -> pd.DataFrame:
    url = "https://api.binance.com/api/v3/klines"
    s = _session()

    # Binance caps klines per request (1000). If user requests more, page backwards
    max_per_request = 1000
    results = []
    end_time = None

    while len(results) < limit:
        req_limit = min(max_per_request, limit - len(results))
        params = {"symbol": symbol, "interval": interval, "limit": req_limit}
        if end_time is not None:
            params["endTime"] = int(end_time)

        r = s.get(url, params=params, timeout=20)
        data = r.json()
        if isinstance(data, dict) and "code" in data:
            logger.error(f"Binance klines error: {data}")
            raise RuntimeError(f"Binance klines error: {data}")

        if not data:
            break

        # First fetch (most recent): keep as-is. Subsequent older pages should be prepended
        if end_time is None:
            results = data
        else:
            results = data + results

        # If we received fewer bars than requested, no more history available
        if len(data) < req_limit:
            break

        # Prepare next page: earliest open time in this batch minus 1 ms
        earliest_open = int(data[0][0])
        end_time = earliest_open - 1

    # Keep only the most recent `limit` bars
    if len(results) > limit:
        results = results[-limit:]

    df = pd.DataFrame(results, columns=[
        "open_time","open","high","low","close","volume",
        "close_time","quote_av","trades","taker_base","taker_quote","ignore"
    ])
    for c in ["open","high","low","close","volume"]:
        df[c] = df[c].astype(float)
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df["close_time"] = pd.to_datetime(df["close_time"], unit="ms", utc=True)
    return df
