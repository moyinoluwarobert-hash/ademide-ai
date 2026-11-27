# ADEMIDE AI — Free-first web prototype

This is a responsive Streamlit web app intended for browser access on phone or laptop.

## Included
- First-run local username/password creation (password stored as salted PBKDF2 hash)
- Binance and Bybit public spot market data
- EMA 9/21 + RSI rules-based signal
- Virtual USDT paper account
- Simulated entries/exits, estimated fees, stop-loss and take-profit
- Trade journal and basic performance metrics

## Important limitations
- This version does **not** place real exchange orders.
- It does **not** need API keys or exchange passwords.
- The strategy is rules-based, not a trained AI prediction model.
- The app only processes trades when the app session refreshes/processes market data. It is not a guaranteed always-on 24/7 background worker.
- Free web hosting can sleep, restart, or have resource limits. Do not rely on a free host for unattended live trading.
- No profitability is promised. Backtesting, demo execution, slippage/fee modelling and extended testing are required before considering real funds.

## Run locally
Python 3.11+ recommended:
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Free web deployment
This project is structured for Streamlit Community Cloud deployment from a GitHub repository:
1. Create a GitHub account and a new repository.
2. Upload these project files (do not upload `data/` or credentials).
3. In Streamlit Community Cloud, deploy the repository with `app.py` as the entry point.
4. For a first deployment, test using non-sensitive demo data only.

The SQLite login and JSON paper account are local-file storage in this prototype. Some hosted platforms have ephemeral storage; accounts/trade history may reset after a restart. Before a real public deployment, replace this with a managed persistent database and stronger production authentication.

No API keys, exchange secrets, or real-money trading credentials should be added to this prototype.
