"""Independent, paper-only BTC/USDT worker for ADEMIDE AI.

Uses public Kraken market data only. This module contains no exchange order methods.
Requires DATABASE_URL (PostgreSQL) and runs as a separate cloud process.
"""
import json
import logging
import os
import signal
import time
from datetime import datetime, timezone, timedelta

import ccxt
import pandas as pd
import psycopg
from psycopg.rows import dict_row

LOG = logging.getLogger("ademide.worker")
SYMBOL = "BTC/USDT"
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "60"))
RISK_FRACTION = float(os.getenv("RISK_FRACTION", "0.005"))
STOP_FRACTION = float(os.getenv("STOP_FRACTION", "0.015"))
TARGET_FRACTION = float(os.getenv("TARGET_FRACTION", "0.03"))
MAX_EXPOSURE = float(os.getenv("MAX_EXPOSURE", "0.25"))
DAILY_LOSS_LIMIT = float(os.getenv("DAILY_LOSS_LIMIT", "0.02"))
MAX_DRAWDOWN = float(os.getenv("MAX_DRAWDOWN", "0.06"))
MAX_TRADES_PER_DAY = int(os.getenv("MAX_TRADES_PER_DAY", "3"))
COOLDOWN_MINUTES = int(os.getenv("COOLDOWN_MINUTES", "30"))
FEE_RATE = float(os.getenv("FEE_RATE", "0.001"))

running = True


def stop_handler(*_):
    global running
    running = False


def db():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is required; configure persistent PostgreSQL.")
    return psycopg.connect(url, row_factory=dict_row, connect_timeout=10)


def market_data(exchange, timeframe, limit=120):
    rows = exchange.fetch_ohlcv(SYMBOL, timeframe=timeframe, limit=limit)
    if not rows or len(rows) < 35:
        raise RuntimeError(f"Insufficient {timeframe} market candles")
    frame = pd.DataFrame(rows, columns=["ms", "open", "high", "low", "close", "volume"])
    frame["time"] = pd.to_datetime(frame["ms"], unit="ms", utc=True)
    frame["ema9"] = frame.close.ewm(span=9, adjust=False).mean()
    frame["ema21"] = frame.close.ewm(span=21, adjust=False).mean()
    delta = frame.close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
    rs = gain / loss.replace(0, 1e-12)
    frame["rsi"] = 100 - 100 / (1 + rs)
    return frame


def entry_signal(five, fifteen):
    p, c = five.iloc[-3], five.iloc[-2]
    trend = fifteen.iloc[-2]
    bullish_cross = p.ema9 <= p.ema21 and c.ema9 > c.ema21
    if bullish_cross and trend.ema9 > trend.ema21 and 45 <= c.rsi <= 68:
        return "BUY"
    return "WAIT"


def ensure_account(conn):
    conn.execute("""
        INSERT INTO paper_account (id, cash, initial_balance, peak_equity)
        VALUES (1, 1000, 1000, 1000) ON CONFLICT (id) DO NOTHING
    """)
    conn.commit()


def log_event(conn, level, message, details=None):
    conn.execute(
        "INSERT INTO worker_events(level, message, details) VALUES (%s,%s,%s)",
        (level, message[:500], json.dumps(details or {})),
    )


def run_once(exchange):
    one = market_data(exchange, "1m", 90)
    five = market_data(exchange, "5m", 90)
    fifteen = market_data(exchange, "15m", 90)
    candle = one.iloc[-2]
    price = float(candle.close)
    signal_name = entry_signal(five, fifteen)
    now = datetime.now(timezone.utc)

    with db() as conn:
        ensure_account(conn)
        account = conn.execute("SELECT * FROM paper_account WHERE id=1 FOR UPDATE").fetchone()
        if account["paused"]:
            log_event(conn, "INFO", "Worker is paused", {"reason": account["pause_reason"]})
            conn.commit()
            return

        cash = float(account["cash"])
        position = account["position"]
        equity = cash + (float(position["qty"]) * price if position else 0.0)
        peak = max(float(account["peak_equity"]), equity)
        day_start = float(account["day_start_equity"] or account["initial_balance"])
        if account["risk_date"] != now.date():
            day_start = equity
            conn.execute("UPDATE paper_account SET risk_date=%s, day_start_equity=%s WHERE id=1",
                         (now.date(), day_start))

        daily_loss = (day_start - equity) / day_start if day_start else 0
        drawdown = (peak - equity) / peak if peak else 0
        if daily_loss >= DAILY_LOSS_LIMIT or drawdown >= MAX_DRAWDOWN:
            reason = "DAILY LOSS LIMIT" if daily_loss >= DAILY_LOSS_LIMIT else "MAX DRAWDOWN"
            conn.execute("UPDATE paper_account SET paused=TRUE, pause_reason=%s, peak_equity=%s WHERE id=1",
                         (reason, peak))
            log_event(conn, "WARNING", f"Safety pause: {reason}",
                      {"equity": equity, "daily_loss": daily_loss, "drawdown": drawdown})
            conn.commit()
            return

        if position:
            stop_price, target_price = float(position["stop"]), float(position["target"])
            exit_reason = None
            if float(candle.low) <= stop_price:
                exit_price, exit_reason = stop_price, "STOP LOSS"
            elif float(candle.high) >= target_price:
                exit_price, exit_reason = target_price, "TAKE PROFIT"
            if exit_reason:
                qty = float(position["qty"])
                proceeds = qty * exit_price * (1 - FEE_RATE)
                pnl = proceeds - float(position["cost_basis"])
                cash += proceeds
                conn.execute("""
                    INSERT INTO paper_trades(side, entry_price, exit_price, qty, pnl, reason, opened_at, closed_at)
                    VALUES ('SELL', %s,%s,%s,%s,%s,%s,%s)
                """, (position["entry"], exit_price, qty, pnl, exit_reason,
                      position["opened_at"], now))
                conn.execute("UPDATE paper_account SET cash=%s, position=NULL WHERE id=1", (cash,))
                position = None
                equity = cash
                log_event(conn, "INFO", f"Paper position closed: {exit_reason}",
                          {"exit": exit_price, "pnl": round(pnl, 4)})

        if position is None and signal_name == "BUY":
            midnight = datetime.combine(now.date(), datetime.min.time(), tzinfo=timezone.utc)
            recent = conn.execute("""
                SELECT count(*) AS n, max(opened_at) AS last_open
                FROM paper_trades WHERE side='BUY' AND opened_at >= %s
            """, (midnight,)).fetchone()
            cooled = recent["last_open"] is None or now - recent["last_open"] >= timedelta(minutes=COOLDOWN_MINUTES)
            if int(recent["n"]) < MAX_TRADES_PER_DAY and cooled:
                risk_cash = equity * RISK_FRACTION
                qty_risk = risk_cash / (price * STOP_FRACTION)
                qty_cap = (equity * MAX_EXPOSURE) / price
                qty = min(qty_risk, qty_cap, cash / (price * (1 + FEE_RATE)))
                cost = qty * price * (1 + FEE_RATE)
                if qty > 0 and cost >= 5:
                    cash -= cost
                    pos = {"qty": qty, "entry": price, "cost_basis": cost,
                           "stop": price * (1 - STOP_FRACTION),
                           "target": price * (1 + TARGET_FRACTION),
                           "opened_at": now.isoformat()}
                    conn.execute("UPDATE paper_account SET cash=%s, position=%s WHERE id=1",
                                 (cash, json.dumps(pos)))
                    conn.execute("""
                        INSERT INTO paper_trades(side, entry_price, qty, pnl, reason, opened_at)
                        VALUES ('BUY',%s,%s,0,'5m EMA/RSI + 15m trend',%s)
                    """, (price, qty, now))
                    log_event(conn, "INFO", "Paper BUY opened",
                              {"price": price, "qty": qty, "risk_budget": risk_cash})

        conn.execute("""
            UPDATE paper_account SET peak_equity=%s, last_price=%s, last_check=%s,
            last_signal=%s, updated_at=now() WHERE id=1
        """, (peak, price, now, signal_name))
        conn.commit()
    LOG.info("BTC/USDT price=%.2f signal=%s", price, signal_name)


def main():
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"),
                        format="%(asctime)s %(levelname)s %(message)s")
    signal.signal(signal.SIGTERM, stop_handler)
    signal.signal(signal.SIGINT, stop_handler)
    exchange = ccxt.kraken({"enableRateLimit": True, "timeout": 20000})
    exchange.load_markets()
    if SYMBOL not in exchange.markets:
        raise RuntimeError("Kraken does not list BTC/USDT; refusing to substitute another quote currency.")
    LOG.info("ADEMIDE paper worker starting; public data only; no order methods.")
    with db() as conn:
        ensure_account(conn)
        log_event(conn, "INFO", "Paper worker started")
        conn.commit()
    while running:
        started = time.monotonic()
        try:
            run_once(exchange)
        except Exception:
            LOG.exception("Paper cycle failed; no order was placed")
            try:
                with db() as conn:
                    log_event(conn, "ERROR", "Paper cycle failed; see worker logs")
                    conn.commit()
            except Exception:
                LOG.exception("Could not persist worker error")
        time.sleep(max(5, POLL_SECONDS - (time.monotonic() - started)))
    LOG.info("ADEMIDE paper worker stopped cleanly")


if __name__ == "__main__":
    main()
