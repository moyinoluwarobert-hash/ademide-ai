import json
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd
import ccxt

DATA_FILE = Path(__file__).parent / "data" / "paper_state.json"

def fetch_market_data(exchange, symbol, timeframe):
    """Fetch OHLCV candles, trying several public exchanges automatically.

    The `exchange` argument is retained for compatibility with older app.py
    versions, but the app no longer depends on a single exchange provider.
    """
    providers = [
        ("Kraken", ccxt.kraken),
        ("Coinbase", ccxt.coinbase),
        ("Bitstamp", ccxt.bitstamp),
        ("OKX", ccxt.okx),
    ]
    errors = []
    base, quote = symbol.split("/")
    candidate_symbols = [symbol]
    if quote == "USDT":
        candidate_symbols.extend([f"{base}/USD", f"{base}/USDC"])

    for provider_name, provider_class in providers:
        try:
            client = provider_class({"enableRateLimit": True, "timeout": 15000})
            markets = client.load_markets()
            selected_symbol = next((s for s in candidate_symbols if s in markets and markets[s].get("active", True)), None)
            if not selected_symbol:
                errors.append(f"{provider_name}: pair unavailable")
                continue
            rows = client.fetch_ohlcv(selected_symbol, timeframe=timeframe, limit=200)
            if not rows:
                errors.append(f"{provider_name}: no candle data")
                continue
            df = pd.DataFrame(rows, columns=["timestamp_ms", "open", "high", "low", "close", "volume"])
            df["timestamp"] = pd.to_datetime(df["timestamp_ms"], unit="ms", utc=True)
            df["ema_fast"] = df["close"].ewm(span=9, adjust=False).mean()
            df["ema_slow"] = df["close"].ewm(span=21, adjust=False).mean()
            delta = df["close"].diff()
            gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
            loss = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
            rs = gain / loss.replace(0, 1e-12)
            df["rsi"] = 100 - 100/(1+rs)
            df.attrs["provider"] = provider_name
            df.attrs["market_symbol"] = selected_symbol
            return df
        except Exception as exc:
            errors.append(f"{provider_name}: {type(exc).__name__}: {str(exc)[:180]}")

    raise RuntimeError("All public market-data providers failed. " + " | ".join(errors))

def build_signal(df):
    if len(df) < 30:
        return "WAIT"
    prev, cur = df.iloc[-2], df.iloc[-1]
    if prev["ema_fast"] <= prev["ema_slow"] and cur["ema_fast"] > cur["ema_slow"] and 45 <= cur["rsi"] <= 68:
        return "BUY"
    if (prev["ema_fast"] >= prev["ema_slow"] and cur["ema_fast"] < cur["ema_slow"]) or cur["rsi"] >= 78:
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
        self.s, self.fee, self.risk = state, fee_rate, risk_fraction
        self.stop, self.target = stop_fraction, target_fraction

    def manage(self, price, symbol, signal):
        p = self.s.get("position")
        if p and p["symbol"] == symbol:
            reason = "STOP LOSS" if price <= p["stop"] else ("TAKE PROFIT" if price >= p["target"] else ("SELL SIGNAL" if signal == "SELL" else None))
            if reason:
                proceeds = p["qty"] * price * (1-self.fee)
                pnl = proceeds - p["cost_basis"]
                self.s["cash"] += proceeds
                self.s["trades"].append({
                    "time_utc": datetime.now(timezone.utc).isoformat(), "symbol": symbol,
                    "side": "SELL", "entry": p["entry"], "exit": price, "qty": p["qty"],
                    "reason": reason, "pnl": round(pnl, 6), "status": "closed"
                })
                self.s["position"] = None
                p = None

        if signal == "BUY" and p is None:
            risk_cash = self.s["cash"] * self.risk
            qty_by_risk = risk_cash / (price*self.stop) if price*self.stop else 0
            spend = min(self.s["cash"]/(1+self.fee), qty_by_risk*price) * 0.995
            if spend >= 5:
                qty = spend/price
                cost = spend*(1+self.fee)
                self.s["cash"] -= cost
                self.s["position"] = {
                    "symbol": symbol, "entry": price, "qty": qty, "cost_basis": cost,
                    "stop": price*(1-self.stop), "target": price*(1+self.target)
                }
                self.s["trades"].append({
                    "time_utc": datetime.now(timezone.utc).isoformat(), "symbol": symbol,
                    "side": "BUY", "entry": price, "exit": None, "qty": qty,
                    "reason": "EMA/RSI entry", "pnl": 0.0, "status": "open"
                })
