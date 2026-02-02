from .. import config

def apply_slippage(price: float, side: str) -> float:
    return price * (1 + config.SLIPPAGE_RATE) if side in ("buy", "buy_to_cover") else price * (1 - config.SLIPPAGE_RATE)

def portfolio_value(paper: dict, price: float) -> float:
    cash = float(paper["cash"])
    long_val = float(paper["btc_long"]) * price
    short_liab = float(paper["btc_short"]) * price
    return cash + long_val - short_liab

def open_long(state, price: float, atr_at_entry: float):
    paper = state["paper"]
    cash = float(paper["cash"])
    spend = cash * max(0.0, min(config.ORDER_PCT, 1.0))
    fill = apply_slippage(price, "buy")
    fee = spend * config.FEE_RATE
    qty = (spend - fee) / fill

    paper["cash"] = cash - spend
    paper["btc_long"] = qty
    paper["avg_long"] = fill

    paper["btc_short"] = 0.0
    paper["avg_short"] = 0.0

    paper["entry_price"] = fill
    paper["entry_atr"] = atr_at_entry
    paper["trail_active"] = False
    paper["trail_stop"] = 0.0

    paper["trades"] = int(paper["trades"]) + 1
    state["position"] = "long"

    return {"fill": fill, "qty": qty, "fee": fee}

def close_long(state, price: float):
    paper = state["paper"]
    qty = float(paper["btc_long"])
    fill = apply_slippage(price, "sell")
    gross = qty * fill
    fee = gross * config.FEE_RATE
    net = gross - fee
    avg = float(paper["avg_long"])
    realized = (fill - avg) * qty - fee

    paper["realized_pnl"] = float(paper["realized_pnl"]) + realized
    paper["cash"] = float(paper["cash"]) + net
    paper["btc_long"] = 0.0
    paper["avg_long"] = 0.0

    paper["trail_active"] = False
    paper["trail_stop"] = 0.0

    paper["trades"] = int(paper["trades"]) + 1
    state["position"] = "flat"

    return {"fill": fill, "qty": qty, "fee": fee, "realized": realized}

def open_short(state, price: float, atr_at_entry: float):
    paper = state["paper"]
    cash = float(paper["cash"])

    notional = cash * max(0.0, min(config.ORDER_PCT, 1.0))
    fill = apply_slippage(price, "sell_short")
    fee = notional * config.FEE_RATE
    qty = (notional - fee) / fill

    paper["cash"] = cash + (notional - fee)
    paper["btc_short"] = qty
    paper["avg_short"] = fill

    paper["btc_long"] = 0.0
    paper["avg_long"] = 0.0

    paper["entry_price"] = fill
    paper["entry_atr"] = atr_at_entry
    paper["trail_active"] = False
    paper["trail_stop"] = 0.0

    paper["trades"] = int(paper["trades"]) + 1
    state["position"] = "short"

    return {"fill": fill, "qty": qty, "fee": fee}

def close_short(state, price: float):
    paper = state["paper"]
    qty = float(paper["btc_short"])
    fill = apply_slippage(price, "buy_to_cover")
    gross = qty * fill
    fee = gross * config.FEE_RATE
    total_cost = gross + fee
    avg = float(paper["avg_short"])
    realized = (avg - fill) * qty - fee

    paper["realized_pnl"] = float(paper["realized_pnl"]) + realized
    paper["cash"] = float(paper["cash"]) - total_cost
    paper["btc_short"] = 0.0
    paper["avg_short"] = 0.0

    paper["trail_active"] = False
    paper["trail_stop"] = 0.0

    paper["trades"] = int(paper["trades"]) + 1
    state["position"] = "flat"

    return {"fill": fill, "qty": qty, "fee": fee, "realized": realized}
