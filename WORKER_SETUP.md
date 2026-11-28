# ADEMIDE AI independent paper worker

This is a separate, paper-only worker. It does not submit exchange orders and does not use exchange API keys. It reads public Kraken BTC/USDT candles and stores the virtual account in PostgreSQL.

## Safety defaults

- Starting virtual balance: $1,000
- Market: BTC/USDT only; refuses to substitute BTC/USD or another pair
- Entry: completed 5-minute EMA 9/21 crossover with RSI confirmation, aligned with completed 15-minute EMA trend
- Risk checks: completed 1-minute candles
- Risk budget: 0.5% of current equity per trade
- Stop / target: 1.5% / 3%
- Maximum position exposure: 25% of equity
- Daily loss pause: 2%
- Peak-to-equity drawdown pause: 6%
- Maximum 3 entries per UTC day and 30-minute cooldown

These are initial test settings, not evidence of profitability or a guarantee against losses. Stops can be exceeded by gaps or bad data. A safety pause requires manual review before resuming.

## Deployment

1. Provision a persistent PostgreSQL database.
2. Run database/schema.sql once.
3. Deploy this repository as a Docker background worker using render.yaml or the Dockerfile.
4. Set DATABASE_URL as a private environment variable on the worker host. Never paste it into chat or commit it to Git.
5. Verify logs, persistent state, market-data timing, and worker uptime before starting the seven-day paper test.
6. Review trade count, estimated fees, realized/unrealized P&L, drawdown, data failures, and uptime.

The worker is separate from Streamlit. Closing a browser does not stop a deployed worker. It must actually be deployed and running on a host.

## Integration status

This is the first independent execution and persistence layer. The existing Streamlit dashboard still reads its old local JSON/SQLite files until a later dashboard integration change. Do not treat the old dashboard's RUNNING indicator as proof this worker is deployed. No live trading is implemented.
