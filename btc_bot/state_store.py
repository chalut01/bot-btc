import os
import json
from . import config

def load_state():
    try:
        with open(config.STATE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)
    except Exception:
        state = {}
    return normalize_state(state)

def save_state(state):
    # Write atomically: write to a temp file then replace the target file.
    dirpath = os.path.dirname(config.STATE_FILE) or "."
    try:
        os.makedirs(dirpath, exist_ok=True)
        target_file = config.STATE_FILE
    except PermissionError:
        # Fallback to a local ./data directory if configured path is not writable.
        fallback_dir = os.path.join(os.getcwd(), "data")
        os.makedirs(fallback_dir, exist_ok=True)
        target_file = os.path.join(fallback_dir, os.path.basename(config.STATE_FILE))
        # update config so other parts of the app read/write the same file
        config.STATE_FILE = target_file

    tmp_path = target_file + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    # atomic replace (works on Windows and POSIX)
    os.replace(tmp_path, target_file)

def normalize_state(state: dict) -> dict:
    state.setdefault("position", "flat")
    state.setdefault("last_bar_ms", 0)
    state.setdefault("last_notify_ts", 0)
    state.setdefault("cooldown_until_bar_ms", 0)
    state.setdefault("day", "")
    state.setdefault("day_start_value", None)
    state.setdefault("halt_today", False)

    paper = state.setdefault("paper", {})
    paper.setdefault("enabled", config.PAPER_TRADING)
    paper.setdefault("start_cash", config.START_CASH_USDT)
    paper.setdefault("cash", config.START_CASH_USDT)

    # migrate from older schema
    if "btc" in paper and "btc_long" not in paper:
        paper["btc_long"] = float(paper.get("btc", 0.0))
    if "avg_entry" in paper and "avg_long" not in paper:
        paper["avg_long"] = float(paper.get("avg_entry", 0.0))

    paper.setdefault("btc_long", 0.0)
    paper.setdefault("avg_long", 0.0)
    paper.setdefault("btc_short", 0.0)
    paper.setdefault("avg_short", 0.0)
    paper.setdefault("realized_pnl", 0.0)
    paper.setdefault("trades", 0)

    paper.setdefault("trail_active", False)
    paper.setdefault("trail_stop", 0.0)
    paper.setdefault("entry_atr", 0.0)
    paper.setdefault("entry_price", 0.0)

    # sanity
    if state["position"] == "long" and paper["btc_long"] <= 1e-12:
        state["position"] = "flat"
    if state["position"] == "short" and paper["btc_short"] <= 1e-12:
        state["position"] = "flat"

    return state
