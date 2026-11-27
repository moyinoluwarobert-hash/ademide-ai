import streamlit as st
import pandas as pd
from auth import setup_needed, create_user, verify_user, logout
from engine import fetch_market_data, build_signal, load_state, save_state, reset_state, PaperTrader

st.set_page_config(page_title="ADEMIDE AI", page_icon="◆", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
.block-container {max-width: 1200px; padding-top: 1.7rem;}
[data-testid="stAppViewContainer"] {background: #0b1220;}
[data-testid="stSidebar"] {background: #101a2b;}
div[data-testid="stMetric"] {background:#142238;border:1px solid #263851;padding:16px;border-radius:14px;}
.stButton>button {border-radius:10px; min-height:42px;}
h1,h2,h3,p, label {color:#e8eef8;}
small, .stCaption {color:#9aaac0;}
</style>
""", unsafe_allow_html=True)

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

def login_screen():
    st.markdown("<h1 style='text-align:center;letter-spacing:2px'>ADEMIDE AI</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align:center;color:#9aaac0'>PRIVATE AUTONOMOUS TRADING WORKSPACE</p>", unsafe_allow_html=True)
    _, center, _ = st.columns([1, 1.1, 1])
    with center:
        st.write("")
        if setup_needed():
            st.subheader("Create your private account")
            st.caption("Create a private login. Use a unique password and keep it safe.")
            with st.form("create_account"):
                username = st.text_input("Username")
                password = st.text_input("Password", type="password")
                confirm = st.text_input("Confirm password", type="password")
                submitted = st.form_submit_button("Create account", use_container_width=True)
            if submitted:
                if not username.strip() or len(password) < 12:
                    st.error("Choose a username and a password with at least 12 characters.")
                elif password != confirm:
                    st.error("Passwords do not match.")
                else:
                    try:
                        create_user(username.strip(), password)
                        st.success("Account created. Log in with your new details.")
                        st.rerun()
                    except Exception:
                        st.error("That username may already be in use.")
        else:
            st.subheader("Welcome back")
            with st.form("login"):
                username = st.text_input("Username")
                password = st.text_input("Password", type="password")
                submitted = st.form_submit_button("Log in", use_container_width=True)
            if submitted:
                if verify_user(username.strip(), password):
                    st.session_state.authenticated = True
                    st.session_state.username = username.strip()
                    st.rerun()
                else:
                    st.error("Username or password is incorrect.")

if not st.session_state.authenticated:
    login_screen()
    st.stop()

st.title("ADEMIDE AI")
st.caption(f"Private trading workspace  ·  Signed in as {st.session_state.username}")
st.warning("SAFE TEST MODE: this build uses virtual funds only. It cannot place real exchange orders and does not need API keys.")

with st.sidebar:
    st.markdown("### Control centre")
    if st.button("Log out", use_container_width=True):
        logout()
        st.rerun()
    st.divider()
    st.caption("Market data provider: automatic fallback across public exchanges")
    symbol = st.selectbox("Spot pair", ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"])
    timeframe = st.selectbox("Analysis timeframe", ["5m", "15m", "30m", "1h"], index=1)
    st.divider()
    st.markdown("### Paper account")
    initial_balance = st.number_input("Virtual balance (USDT)", 10.0, 100000.0, 10.0, 1.0)
    risk_pct = st.slider("Risk budget per trade", 0.25, 2.0, 1.0, 0.25)
    stop_pct = st.slider("Stop loss", 0.5, 5.0, 1.5, 0.25)
    target_pct = st.slider("Take profit", 0.5, 10.0, 3.0, 0.25)
    fee_pct = st.number_input("Estimated fee per side (%)", 0.0, 1.0, 0.1, 0.01)
    if st.button("Reset paper account", use_container_width=True):
        reset_state(initial_balance)
        st.rerun()
    st.caption("Fee estimate is adjustable. Check the exchange's current fee schedule.")

state = load_state(initial_balance)
trader = PaperTrader(state, fee_pct/100, risk_pct/100, stop_pct/100, target_pct/100)

try:
    candles = fetch_market_data("auto", symbol, timeframe)
    current_price = float(candles["close"].iloc[-1])
    signal = build_signal(candles)
    trader.manage(current_price, symbol, signal)
    save_state(state)
    provider = candles.attrs.get("provider", "public provider")
    market_symbol = candles.attrs.get("market_symbol", symbol)
    data_note = f"Market data loaded from {provider} ({market_symbol}). Last candle: {candles['timestamp'].iloc[-1]}"
except Exception as exc:
    candles, current_price, signal = None, None, "UNAVAILABLE"
    data_note = f"Market data could not be loaded: {exc}"

closed = [t for t in state["trades"] if t.get("status") == "closed"]
wins = sum(float(t.get("pnl", 0)) > 0 for t in closed)
realized = sum(float(t.get("pnl", 0)) for t in closed)
position = state.get("position")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Virtual cash", f"${state['cash']:.2f}")
c2.metric("Latest market price", f"${current_price:,.4f}" if current_price else "—")
c3.metric("Current signal", signal)
c4.metric("Closed trade win rate", f"{wins/len(closed)*100:.1f}%" if closed else "—")
st.caption(data_note)

if candles is not None:
    st.subheader(f"{symbol} · {timeframe}")
    st.line_chart(candles.tail(120).set_index("timestamp")[["close", "ema_fast", "ema_slow"]])
    st.caption("Strategy baseline: EMA 9/21 crossover plus RSI confirmation. It is a transparent rules-based strategy, not a trained predictive model.")
    if position:
        st.subheader("Open simulated position")
        market_value = position["qty"] * current_price
        unrealized = market_value * (1-fee_pct/100) - position["cost_basis"]
        p1,p2,p3,p4 = st.columns(4)
        p1.metric("Entry", f"${position['entry']:.5f}")
        p2.metric("Quantity", f"{position['qty']:.8f}")
        p3.metric("Stop loss", f"${position['stop']:.5f}")
        p4.metric("Take profit", f"${position['target']:.5f}")
        st.metric("Estimated unrealized P/L after exit fee", f"${unrealized:.4f}")

st.subheader("Performance")
p1,p2,p3 = st.columns(3)
p1.metric("Closed trades", len(closed))
p2.metric("Realized P/L after estimated fees", f"${realized:.4f}")
p3.metric("Initial virtual balance", f"${state['initial_balance']:.2f}")

st.subheader("Trade journal")
if state["trades"]:
    st.dataframe(pd.DataFrame(state["trades"]).iloc[::-1], use_container_width=True, hide_index=True)
else:
    st.info("No simulated trades yet. The strategy waits for a qualifying signal.")

st.subheader("Operating status")
st.markdown("""
- **Automatic decisions:** the rules engine can open/close simulated positions when this app processes a market update.
- **Not continuous yet:** this free prototype processes updates when the app is active/refreshed; it is not a guaranteed 24/7 background trader.
- **No real orders:** public exchange candle data is used only for paper trading. Never enter API secrets into this prototype.
- **No profit promise:** results need proper historical backtesting, out-of-sample testing, realistic fees/slippage and extended demo testing.
""")
st.info("This is a paper-trading prototype. Free hosting may sleep, and its local files may not persist reliably between restarts. Do not use it for real-money trading.")
