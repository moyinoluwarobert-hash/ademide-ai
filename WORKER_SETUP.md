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

## Database connection choice (important for Render)

For a Render background worker using Supabase, use the **Supabase Shared Pooler — Session mode**, not the Direct connection shown by default in the Supabase Connect panel.

Why: Supabase direct connections are IPv6 by default on the Free plan, while Render outbound networking is IPv4. The shared pooler is available on the Free plan and is reachable over IPv4. This avoids buying the paid Supabase IPv4 add-on.

In Supabase:
1. Open **Connect**.
2. Choose **Direct connection** to open the connection options, then select **Session pooler** under Connection Method.
3. Keep **Type: URI**.
4. Copy the session-pooler connection string. It has a pooler hostname and port **5432**; do not use the direct `db.<project-ref>.supabase.co` hostname.
5. Replace the password placeholder locally with the database password. If the password contains reserved URL characters such as `&`, `#`, `?`, or spaces, percent-encode them.

In Render, set the complete session-pooler URI as the private `DATABASE_URL` environment variable for the worker. Never paste it into chat or commit it to Git. Do not enable Supabase's paid IPv4 add-on for this setup.

## Deployment

1. Run `database/schema.sql` once in the ADEMIDE AI Supabase project's SQL Editor.
2. Deploy this repository as a Docker background worker using `render.yaml` or the Dockerfile.
3. Set `DATABASE_URL` as a private environment variable on the worker host.
4. Verify logs, persistent state, market-data timing, and worker uptime before starting the seven-day paper test.
5. Review trade count, estimated fees, realized/unrealized P&L, drawdown, data failures, and uptime.

The worker is separate from Streamlit. Closing a browser does not stop a deployed worker. It must actually be deployed and running on a host.

## Integration status

This is the first independent execution and persistence layer. The existing Streamlit dashboard still reads its old local JSON/SQLite files until a later dashboard integration change. Do not treat the old dashboard's RUNNING indicator as proof this worker is deployed. No live trading is implemented.
