import time
from . import config
from .log_setup import setup_logger
from .telegram_client import TelegramClient
from .state_store import load_state, save_state
from .market.binance_api import spot_price, klines
from .market.indicators import ema
from .trading import paper
from .strategy import trend_breakout_5m, range_reversion_5m
import datetime

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
    # validate config
    config.validate_config()

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

            # update daily start value and reset halt flag on new UTC day
            try:
                now_day = datetime.datetime.utcnow().strftime("%Y-%m-%d")
                pv = paper.portfolio_value(state["paper"], float(price_now))
                if state.get("day") != now_day:
                    state["day"] = now_day
                    state["day_start_value"] = pv
                    state["halt_today"] = False
                    logger.info(f"New day {now_day}, day_start_value={pv:.2f}")
                    save_state(state)
                else:
                    # check kill-switch
                    if config.USE_KILL_SWITCH and not state.get("halt_today", False) and state.get("day_start_value"):
                        dd_pct = (state["day_start_value"] - pv) / float(state["day_start_value"]) * 100.0
                        if dd_pct >= float(config.MAX_DAILY_DD_PCT):
                            state["halt_today"] = True
                            save_state(state)
                            msg = f"⛔ Kill switch triggered: daily drawdown {dd_pct:.2f}% >= {config.MAX_DAILY_DD_PCT}%"
                            logger.warning(msg)
                            if tg.enabled():
                                tg.send(msg)

            except Exception:
                logger.exception("Error computing daily PnL / kill-switch")

            action = strat.decide(ctx, state["position"], allow_long=allow_long, allow_short=allow_short)

            # reentry guard by bars
            if int(state.get("cooldown_until_bar_ms", 0)) and ctx["bar_close_ms"] < int(state["cooldown_until_bar_ms"]):
                save_state(state)
                time.sleep(config.POLL_SEC)
                continue

            # risk-based exits (TP/SL/trailing) take precedence over strategy opens
            def risk_exit_check(price_now: float):
                paper_state = state["paper"]
                entry_atr = float(paper_state.get("entry_atr", 0.0) or 0.0)
                entry_price = float(paper_state.get("entry_price", 0.0) or 0.0)

                if state["position"] == "long":
                    # TP
                    if config.USE_TP_SL and entry_atr > 0 and price_now >= entry_price + config.TP_ATR_MULT * entry_atr:
                        return "close_long"
                    # SL
                    if config.USE_TP_SL and entry_atr > 0 and price_now <= entry_price - config.SL_ATR_MULT * entry_atr:
                        return "close_long"
                    # trailing
                    if config.USE_TRAILING and entry_atr > 0:
                        if not paper_state.get("trail_active"):
                            # activate trailing when profit >= R * atr
                            if (price_now - entry_price) >= config.TRAIL_ACTIVATE_R * entry_atr:
                                paper_state["trail_active"] = True
                                paper_state["trail_stop"] = price_now - config.TRAIL_ATR_MULT * entry_atr
                                logger.info(f"Trail activated, stop={paper_state['trail_stop']:.2f}")
                        else:
                            # update trail stop to max(current, new)
                            candidate = price_now - config.TRAIL_ATR_MULT * entry_atr
                            if candidate > float(paper_state.get("trail_stop", 0.0)):
                                paper_state["trail_stop"] = candidate
                            if price_now <= float(paper_state.get("trail_stop", 0.0)):
                                return "close_long"

                if state["position"] == "short":
                    if config.USE_TP_SL and entry_atr > 0 and price_now <= entry_price - config.TP_ATR_MULT * entry_atr:
                        return "close_short"
                    if config.USE_TP_SL and entry_atr > 0 and price_now >= entry_price + config.SL_ATR_MULT * entry_atr:
                        return "close_short"
                    if config.USE_TRAILING and entry_atr > 0:
                        if not paper_state.get("trail_active"):
                            if (entry_price - price_now) >= config.TRAIL_ACTIVATE_R * entry_atr:
                                paper_state["trail_active"] = True
                                paper_state["trail_stop"] = price_now + config.TRAIL_ATR_MULT * entry_atr
                                logger.info(f"Trail activated (short), stop={paper_state['trail_stop']:.2f}")
                        else:
                            candidate = price_now + config.TRAIL_ATR_MULT * entry_atr
                            if candidate < float(paper_state.get("trail_stop", 0.0)) or float(paper_state.get("trail_stop", 0.0)) == 0.0:
                                paper_state["trail_stop"] = candidate
                            if price_now >= float(paper_state.get("trail_stop", 0.0)) and paper_state.get("trail_stop"):
                                return "close_short"

                return None

            # allow strategy to request opens/closes, but check risk exits first for position closes
            risk_action = risk_exit_check(float(ctx["close"]))
            if risk_action == "close_long" and state["position"] == "long":
                logger.info(f"[TRADE] CLOSE LONG (risk) @ {ctx['close']:.2f} strategy={strat_name}")
                paper.close_long(state, float(ctx["close"]))
                notify_summary(state, price_now, "📌 After CLOSE LONG (risk)")
                state["cooldown_until_bar_ms"] = ctx["bar_close_ms"] + config.REENTRY_BARS * 5 * 60 * 1000
                save_state(state)
                time.sleep(config.POLL_SEC)
                continue

            if risk_action == "close_short" and state["position"] == "short":
                logger.info(f"[TRADE] CLOSE SHORT (risk) @ {ctx['close']:.2f} strategy={strat_name}")
                paper.close_short(state, float(ctx["close"]))
                notify_summary(state, price_now, "📌 After CLOSE SHORT (risk)")
                state["cooldown_until_bar_ms"] = ctx["bar_close_ms"] + config.REENTRY_BARS * 5 * 60 * 1000
                save_state(state)
                time.sleep(config.POLL_SEC)
                continue

            # execute strategy actions
            if action == "open_long" and state["position"] == "flat":
                if state.get("halt_today"):
                    logger.info("Open blocked by kill switch (halt_today)")
                    save_state(state)
                else:
                    logger.info(f"[TRADE] OPEN LONG @ {ctx['close']:.2f} strategy={strat_name}")
                    paper.open_long(state, float(ctx["close"]), atr_at_entry=float(ctx.get("atr", 0.0) or 0.0))
                    notify_summary(state, price_now, "📌 After OPEN LONG")
                    state["cooldown_until_bar_ms"] = ctx["bar_close_ms"] + config.REENTRY_BARS * 5 * 60 * 1000
                    save_state(state)

            elif action == "open_short" and state["position"] == "flat":
                if state.get("halt_today"):
                    logger.info("Open blocked by kill switch (halt_today)")
                    save_state(state)
                else:
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
