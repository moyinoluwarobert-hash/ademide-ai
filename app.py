
import streamlit as st
import pandas as pd
from auth import setup_needed, create_user, verify_user, logout
from engine import fetch_market_data, build_signal, load_state, save_state, reset_state, PaperTrader

st.set_page_config(page_title="ADEMIDE AI", page_icon="◆", layout="wide")
st.markdown('''
<style>
[data-testid="stAppViewContainer"]{background:#0b1220}
[data-testid="stSidebar"]{background:#101a2b}
.block-container{max-width:1180px;padding:1.4rem 1rem 3rem}
h1,h2,h3,p,label,span{color:#edf3ff}
[data-testid="stMetric"]{background:#142238;border:1px solid #2a405d;padding:14px;border-radius:14px}
[data-testid="stMetricLabel"]{color:#b7c7dc!important}
[data-testid="stMetricValue"]{color:#fff!important}
.stButton>button{border-radius:10px;min-height:44px;font-weight:600}
@media(max-width:700px){.block-container{padding:.8rem .6rem 2rem}h1{font-size:1.8rem!important}}
</style>
''', unsafe_allow_html=True)

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "paper_running" not in st.session_state:
    st.session_state.paper_running = False

if not st.session_state.authenticated:
    st.title("ADEMIDE AI")
    st.caption("PRIVATE BTC PAPER-TRADING WORKSPACE")
    if setup_needed():
        st.subheader("Create your account")
        with st.form("create_account"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            confirm = st.text_input("Confirm password", type="password")
            submitted = st.form_submit_button("Create account", use_container_width=True)
        if submitted:
            if not username.strip() or len(password) < 12:
                st.error("Enter a username and a password with at least 12 characters.")
            elif password != confirm:
                st.error("Passwords do not match.")
            else:
                try:
                    create_user(username.strip(), password)
                    st.success("Account created. Please log in.")
                    st.rerun()
                except Exception:
                    st.error("Could not create account. Username may already exist.")
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
            st.error("Username or password is incorrect.")
    st.stop()

st.title("ADEMIDE AI")
st.caption(f"Private trading workspace · Signed in as {st.session_state.username}")
st.warning("SAFE TEST MODE — virtual funds only. No real exchange orders or API keys are used.")

with st.sidebar:
    st.subheader("Control centre")
    if st.button("Log out", use_container_width=True):
        logout()
        st.rerun()
    st.divider()
    st.markdown("**Market:** BTC/USDT · 15-minute candles")
    risk = st.slider("Risk budget per trade (%)", 0.25, 2.0, 1.0, 0.25)
    stop = st.slider("Stop loss (%)", 0.5, 5.0, 1.5, 0.25)
    target = st.slider("Take profit (%)", 0.5, 10.0, 3.0, 0.25)
    fee = st.number_input("Estimated fee per side (%)", 0.0, 1.0, 0.1, 0.01)
    st.caption("Starting virtual balance: $1,000")
    if st.button("Reset paper account to $1,000", use_container_width=True):
        reset_state(1000.0)
        st.session_state.paper_running = False
        st.success("Paper account reset.")
        st.rerun()

state = load_state(1000.0)
trader = PaperTrader(state, fee/100, risk/100, stop/100, target/100)

left, middle, right = st.columns([1, 1, 2])
with left:
    if st.button("▶ Start paper trading", type="primary", use_container_width=True):
        st.session_state.paper_running = True
with middle:
    if st.button("Ⅱ Pause", use_container_width=True):
        st.session_state.paper_running = False
with right:
    st.write("**Status:** " + ("RUNNING · paper mode" if st.session_state.paper_running else "PAUSED"))

try:
    candles = fetch_market_data("auto", "BTC/USDT", "15m")
    price = float(candles["close"].iloc[-2])
    signal = build_signal(candles)
    if st.session_state.paper_running:
        trader.manage(price, "BTC/USDT", signal)
        save_state(state)
    provider = candles.attrs.get("provider", "public provider")
    pair = candles.attrs.get("market_symbol", "BTC/USDT")
    market_note = f"Market data: {provider} ({pair}) · Last completed candle: {candles['timestamp'].iloc[-2]}"
except Exception as exc:
    candles, price, signal = None, None, "UNAVAILABLE"
    market_note = f"Market data unavailable: {exc}"

closed = [t for t in state["trades"] if t.get("status") == "closed"]
wins = sum(float(t.get("pnl", 0)) > 0 for t in closed)
realized = sum(float(t.get("pnl", 0)) for t in closed)

a,b,c,d = st.columns(4)
a.metric("Virtual cash", f"${state['cash']:,.2f}")
b.metric("BTC market price", f"${price:,.2f}" if price else "—")
c.metric("Current signal", signal)
d.metric("Closed-trade win rate", f"{wins/len(closed)*100:.1f}%" if closed else "—")
st.caption(market_note)

if candles is not None:
    st.subheader("Bitcoin market")
    st.line_chart(candles.iloc[:-1].tail(100).set_index("timestamp")[["close", "ema_fast", "ema_slow"]])
    st.caption("EMA 9/21 crossover with RSI confirmation. Decisions use completed 15-minute candles.")

if state.get("position"):
    pos = state["position"]
    st.subheader("Open simulated BTC position")
    p1,p2,p3 = st.columns(3)
    p1.metric("Entry price", f"${pos['entry']:,.2f}")
    p2.metric("Stop loss", f"${pos['stop']:,.2f}")
    p3.metric("Take profit", f"${pos['target']:,.2f}")

st.subheader("Performance")
p1,p2,p3 = st.columns(3)
p1.metric("Closed trades", len(closed))
p2.metric("Realized P/L after estimated fees", f"${realized:,.4f}")
p3.metric("Starting virtual balance", f"${state['initial_balance']:,.2f}")

st.subheader("Trade journal")
if state["trades"]:
    st.dataframe(pd.DataFrame(state["trades"]).iloc[::-1], use_container_width=True, hide_index=True)
else:
    st.info("No simulated trades yet. ADEMIDE waits when entry conditions are not met.")

st.info("The $1,000 balance is virtual. This is paper trading, not a 24/7 background service or a trained AI model. Do not add exchange API keys.")
