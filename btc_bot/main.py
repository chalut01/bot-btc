import time
from . import config
from .log_setup import setup_logger
from .telegram_client import TelegramClient
from .state_store import load_state, save_state
from .market.binance_api import spot_price, klines
from .market.indicators import ema
from .trading import paper
from .strategy import trend_breakout_5m, range_reversion_5m

logger = setup_logger()
tg = TelegramClient()

def pick_strategy():
    if config.STRATEGY == "trend":
        return trend_breakout_5m, "trend"
    if config.STRATEGY == "range":
        return range_reversion_5m, "range"
    raise ValueError("STRATEGY must be 'trend' or 'range'")

def ema1h_filter_allow(symbol: str):
    if not config.EMA_FILTER_1H:
        return True, True, None

    df = klines(symbol, "1h", config.EMA_1H_KLINES_LIMIT)
    if len(df) < config.EMA_1H_PERIOD + 5:
        return True, True, None

    e = float(ema(df["close"], config.EMA_1H_PERIOD).iloc[-1])
    p = float(df["close"].iloc[-1])
    allow_long = p > e
    allow_short = p < e
    return allow_long, allow_short, e

def notify_summary(state, price_now: float, title: str):
    pv = paper.portfolio_value(state["paper"], price_now)
    start = float(state["paper"]["start_cash"])
    pnl = pv - start
    pnl_pct = (pnl / start * 100.0) if start > 0 else 0.0
    msg = (
        f"{title}\n"
        f"Now: {price_now:,.2f}\n"
        f"Cash: {float(state['paper']['cash']):,.2f}\n"
        f"Pos: {state['position']}\n"
        f"Long: {float(state['paper']['btc_long']):.8f} avg {float(state['paper']['avg_long']):,.2f}\n"
        f"Short: {float(state['paper']['btc_short']):.8f} avg {float(state['paper']['avg_short']):,.2f}\n"
        f"Port: {pv:,.2f}\n"
        f"PnL: {pnl:,.2f} ({pnl_pct:+.2f}%)\n"
        f"Realized: {float(state['paper']['realized_pnl']):,.2f} Trades: {int(state['paper']['trades'])}"
    )
    tg.send(msg)

def main():
    strat, strat_name = pick_strategy()

    state = load_state()
    if tg.enabled():
        tg.send(f"✅ bot started | strategy={strat_name} | symbol={config.SYMBOL} interval={config.KLINE_INTERVAL}")

    while True:
        try:
            price_now = spot_price(config.SYMBOL)
            df = klines(config.SYMBOL, config.KLINE_INTERVAL, 800)

            allow_long, allow_short, ema1h = ema1h_filter_allow(config.SYMBOL)

            ctx = strat.build_context(df)

            # avoid duplicate same bar
            if ctx["bar_close_ms"] == int(state.get("last_bar_ms", 0)):
                time.sleep(config.POLL_SEC)
                continue

            state["last_bar_ms"] = ctx["bar_close_ms"]

            action = strat.decide(ctx, state["position"], allow_long=allow_long, allow_short=allow_short)

            # reentry guard by bars
            if int(state.get("cooldown_until_bar_ms", 0)) and ctx["bar_close_ms"] < int(state["cooldown_until_bar_ms"]):
                save_state(state)
                time.sleep(config.POLL_SEC)
                continue

            # execute
            if action == "open_long" and state["position"] == "flat":
                logger.info(f"[TRADE] OPEN LONG @ {ctx['close']:.2f} strategy={strat_name}")
                paper.open_long(state, float(ctx["close"]), atr_at_entry=float(ctx.get("atr", 0.0) or 0.0))
                notify_summary(state, price_now, "📌 After OPEN LONG")
                state["cooldown_until_bar_ms"] = ctx["bar_close_ms"] + config.REENTRY_BARS * 5 * 60 * 1000
                save_state(state)

            elif action == "open_short" and state["position"] == "flat":
                logger.info(f"[TRADE] OPEN SHORT @ {ctx['close']:.2f} strategy={strat_name}")
                paper.open_short(state, float(ctx["close"]), atr_at_entry=float(ctx.get("atr", 0.0) or 0.0))
                notify_summary(state, price_now, "📌 After OPEN SHORT")
                state["cooldown_until_bar_ms"] = ctx["bar_close_ms"] + config.REENTRY_BARS * 5 * 60 * 1000
                save_state(state)

            elif action == "close_long" and state["position"] == "long":
                logger.info(f"[TRADE] CLOSE LONG @ {ctx['close']:.2f} strategy={strat_name}")
                paper.close_long(state, float(ctx["close"]))
                notify_summary(state, price_now, "📌 After CLOSE LONG")
                state["cooldown_until_bar_ms"] = ctx["bar_close_ms"] + config.REENTRY_BARS * 5 * 60 * 1000
                save_state(state)

            elif action == "close_short" and state["position"] == "short":
                logger.info(f"[TRADE] CLOSE SHORT @ {ctx['close']:.2f} strategy={strat_name}")
                paper.close_short(state, float(ctx["close"]))
                notify_summary(state, price_now, "📌 After CLOSE SHORT")
                state["cooldown_until_bar_ms"] = ctx["bar_close_ms"] + config.REENTRY_BARS * 5 * 60 * 1000
                save_state(state)

            else:
                save_state(state)

        except Exception:
            logger.exception("Unhandled exception")
            tg.send("⚠️ [ERROR] check logs")
        time.sleep(config.POLL_SEC)

if __name__ == "__main__":
    main()
