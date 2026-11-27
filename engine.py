
import json
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd
import ccxt

DATA_FILE = Path(__file__).parent / "data" / "paper_state.json"

def fetch_market_data(exchange, symbol, timeframe):
    providers = [("Kraken", ccxt.kraken), ("Coinbase", ccxt.coinbase), ("Bitstamp", ccxt.bitstamp), ("OKX", ccxt.okx)]
    base, quote = symbol.split("/")
    candidates = [symbol]
    if quote == "USDT":
        candidates += [f"{base}/USD", f"{base}/USDC"]
    errors = []
    for name, cls in providers:
        try:
            client = cls({"enableRateLimit": True, "timeout": 15000})
            markets = client.load_markets()
            selected = next((s for s in candidates if s in markets and markets[s].get("active", True)), None)
            if not selected:
                errors.append(f"{name}: pair unavailable")
                continue
            rows = client.fetch_ohlcv(selected, timeframe=timeframe, limit=200)
            if not rows:
                errors.append(f"{name}: no candle data")
                continue
            df = pd.DataFrame(rows, columns=["timestamp_ms","open","high","low","close","volume"])
            df["timestamp"] = pd.to_datetime(df["timestamp_ms"], unit="ms", utc=True)
            df["ema_fast"] = df["close"].ewm(span=9, adjust=False).mean()
            df["ema_slow"] = df["close"].ewm(span=21, adjust=False).mean()
            delta = df["close"].diff()
            gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
            loss = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
            rs = gain / loss.replace(0, 1e-12)
            df["rsi"] = 100 - 100/(1+rs)
            df.attrs["provider"] = name
            df.attrs["market_symbol"] = selected
            return df
        except Exception as exc:
            errors.append(f"{name}: {type(exc).__name__}: {str(exc)[:120]}")
    raise RuntimeError("Public market-data providers failed: " + " | ".join(errors))

def build_signal(df):
    if len(df) < 30:
        return "WAIT"
    previous, current = df.iloc[-3], df.iloc[-2]
    bullish = previous["ema_fast"] <= previous["ema_slow"] and current["ema_fast"] > current["ema_slow"]
    bearish = previous["ema_fast"] >= previous["ema_slow"] and current["ema_fast"] < current["ema_slow"]
    if bullish and 45 <= current["rsi"] <= 68:
        return "BUY"
    if bearish or current["rsi"] >= 78:
        return "SELL"
    return "WAIT"

def load_state(balance):
    if DATA_FILE.exists():
        try:
            state = json.loads(DATA_FILE.read_text())
            state.setdefault("initial_balance", float(balance))
            state.setdefault("trades", [])
            state.setdefault("position", None)
            return state
        except Exception:
            pass
    return {"cash": float(balance), "initial_balance": float(balance), "position": None, "trades": []}

def save_state(state):
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(state, indent=2, default=str))

def reset_state(balance):
    save_state({"cash": float(balance), "initial_balance": float(balance), "position": None, "trades": []})

class PaperTrader:
    def __init__(self, state, fee_rate, risk_fraction, stop_fraction, target_fraction):
        self.state, self.fee = state, fee_rate
        self.risk, self.stop, self.target = risk_fraction, stop_fraction, target_fraction

    def manage(self, price, symbol, signal):
        position = self.state.get("position")
        if position and position["symbol"] == symbol:
            reason = None
            if price <= position["stop"]:
                reason = "STOP LOSS"
            elif price >= position["target"]:
                reason = "TAKE PROFIT"
            elif signal == "SELL":
                reason = "SELL SIGNAL"
            if reason:
                proceeds = position["qty"] * price * (1-self.fee)
                pnl = proceeds - position["cost_basis"]
                self.state["cash"] += proceeds
                self.state["trades"].append({
                    "time_utc": datetime.now(timezone.utc).isoformat(), "symbol": symbol,
                    "side": "SELL", "entry": position["entry"], "exit": price,
                    "qty": position["qty"], "reason": reason, "pnl": round(pnl,6), "status": "closed"
                })
                self.state["position"] = None
                position = None
        if signal == "BUY" and position is None:
            risk_cash = self.state["cash"] * self.risk
            qty_by_risk = risk_cash / (price*self.stop) if price*self.stop else 0
            spend = min(self.state["cash"]/(1+self.fee), qty_by_risk*price) * 0.995
            if spend >= 5:
                qty = spend/price
                cost = spend*(1+self.fee)
                self.state["cash"] -= cost
                self.state["position"] = {
                    "symbol": symbol, "entry": price, "qty": qty, "cost_basis": cost,
                    "stop": price*(1-self.stop), "target": price*(1+self.target)
                }
                self.state["trades"].append({
                    "time_utc": datetime.now(timezone.utc).isoformat(), "symbol": symbol,
                    "side": "BUY", "entry": price, "exit": None, "qty": qty,
                    "reason": "EMA/RSI entry", "pnl": 0.0, "status": "open"
                })
