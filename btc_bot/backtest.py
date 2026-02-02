import argparse
from . import config
from .log_setup import setup_logger
from .market.binance_api import klines
from .trading import paper
from .strategy import trend_breakout_5m, range_reversion_5m

logger = setup_logger()

def pick_strategy(name: str):
    if name == "trend":
        return trend_breakout_5m
    if name == "range":
        return range_reversion_5m
    raise ValueError("Unknown strategy. Use 'trend' or 'range'.")

def run_backtest(strategy_name: str, limit: int):
    strat = pick_strategy(strategy_name)
    # validate config for backtest run
    config.validate_config()
    df = klines(config.SYMBOL, config.KLINE_INTERVAL, limit)

    # state (paper only)
    state = {
        "position": "flat",
        "paper": {
            "enabled": True,
            "start_cash": config.START_CASH_USDT,
            "cash": config.START_CASH_USDT,
            "btc_long": 0.0,
            "avg_long": 0.0,
            "btc_short": 0.0,
            "avg_short": 0.0,
            "realized_pnl": 0.0,
            "trades": 0,
            "trail_active": False,
            "trail_stop": 0.0,
            "entry_atr": 0.0,
            "entry_price": 0.0,
        }
    }

    trades = 0
    for i in range(60, len(df)):  # warmup
        window = df.iloc[:i].copy()

        # allow filters (for backtest keep them simple: no 1h filter here)
        allow_long = True
        allow_short = True

        ctx = strat.build_context(window)
        action = strat.decide(ctx, state["position"], allow_long=allow_long, allow_short=allow_short)

        price = float(ctx["close"])

        if action == "open_long" and state["position"] == "flat":
            paper.open_long(state, price, atr_at_entry=float(ctx.get("atr", 0.0) or 0.0))
            trades += 1

        elif action == "open_short" and state["position"] == "flat":
            paper.open_short(state, price, atr_at_entry=float(ctx.get("atr", 0.0) or 0.0))
            trades += 1

        elif action == "close_long" and state["position"] == "long":
            paper.close_long(state, price)
            trades += 1

        elif action == "close_short" and state["position"] == "short":
            paper.close_short(state, price)
            trades += 1

    # end value with last close
    last_price = float(df.iloc[-1]["close"])
    pv = paper.portfolio_value(state["paper"], last_price)
    start = float(state["paper"]["start_cash"])
    pnl = pv - start
    pnl_pct = (pnl / start * 100.0) if start > 0 else 0.0

    logger.info(f"Backtest done. strategy={strategy_name} limit={limit} bars interval={config.KLINE_INTERVAL}")
    logger.info(f"Trades={trades}, EndValue={pv:.2f}, PnL={pnl:.2f} ({pnl_pct:+.2f}%), Realized={state['paper']['realized_pnl']:.2f}")
    print(f"strategy={strategy_name} bars={limit} trades={trades} end={pv:.2f} pnl={pnl:.2f} ({pnl_pct:+.2f}%) realized={state['paper']['realized_pnl']:.2f}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", choices=["trend", "range"], default="trend")
    ap.add_argument("--limit", type=int, default=config.BACKTEST_KLINES_LIMIT)
    args = ap.parse_args()
    run_backtest(args.strategy, args.limit)

if __name__ == "__main__":
    main()
