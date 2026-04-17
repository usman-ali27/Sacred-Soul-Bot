import streamlit as st
from mt5_connector import MT5Connector
from grid_engine import GridEngine
from brain import Brain
import time

st.set_page_config(page_title="Grid Bot", layout="wide")

st.title("Grid Bot — MT5 Grid Trading")

# 1. MT5 Connection
mt5 = MT5Connector()
if not mt5.is_connected():
    st.warning("Not connected to MT5. Please connect your account.")
    login = st.text_input("MT5 Login", key="mt5_login")
    password = st.text_input("Password", type="password", key="mt5_password")
    server = st.text_input("Server", key="mt5_server")
    if st.button("Connect"):
        ok, msg = mt5.connect(login, password, server)
        if ok:
            st.success("Connected to MT5!")
        else:
            st.error(f"Failed to connect: {msg}")
    st.stop()
else:
    st.success("Connected to MT5.")

# 2. Grid Settings
st.header("Grid Settings")
symbol = st.text_input("Symbol", value="XAUUSD")
timeframe = st.selectbox("Timeframe", ["1m", "5m", "15m", "1h", "4h"]) 
lot = st.number_input("Base Lot", min_value=0.01, max_value=1.0, value=0.01, step=0.01)
levels = st.number_input("Grid Levels", min_value=1, max_value=20, value=6)
spacing = st.number_input("Grid Spacing (points)", min_value=10, max_value=1000, value=100)

# 3. Brain (future prediction)
brain = Brain()

# 4. Run/Stop
run = st.button("Start Grid Bot")
stop = st.button("Stop Grid Bot")

if run:
    st.session_state['running'] = True
if stop:
    st.session_state['running'] = False

if st.session_state.get('running', False):
    st.success("Grid Bot is running. Will analyze and set grid every 1 minute.")
    grid = GridEngine(symbol, timeframe, lot, levels, spacing, mt5, brain)
    while st.session_state.get('running', False):
        if not mt5.is_connected():
            st.warning("Lost MT5 connection. Attempting auto-reconnect...")
            mt5.auto_reconnect()
            continue
        grid.analyze_and_set_grid()
        brain.train(grid.get_history())
        st.info("Grid updated. Next run in 60s.")
        time.sleep(60)
    st.info("Grid Bot stopped.")
