-- Dedicated PostgreSQL schema for ADEMIDE AI paper trading.
CREATE TABLE IF NOT EXISTS paper_account (
    id SMALLINT PRIMARY KEY CHECK (id = 1),
    cash NUMERIC(20,8) NOT NULL DEFAULT 1000 CHECK (cash >= 0),
    initial_balance NUMERIC(20,8) NOT NULL DEFAULT 1000 CHECK (initial_balance > 0),
    position JSONB,
    paused BOOLEAN NOT NULL DEFAULT FALSE,
    pause_reason TEXT,
    risk_date DATE,
    day_start_equity NUMERIC(20,8),
    peak_equity NUMERIC(20,8) NOT NULL DEFAULT 1000,
    last_price NUMERIC(20,8),
    last_check TIMESTAMPTZ,
    last_signal TEXT NOT NULL DEFAULT 'WAIT',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS paper_trades (
    id BIGSERIAL PRIMARY KEY,
    side TEXT NOT NULL CHECK (side IN ('BUY','SELL')),
    entry_price NUMERIC(20,8) NOT NULL,
    exit_price NUMERIC(20,8),
    qty NUMERIC(28,12) NOT NULL,
    pnl NUMERIC(20,8) NOT NULL DEFAULT 0,
    reason TEXT NOT NULL,
    opened_at TIMESTAMPTZ NOT NULL,
    closed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS paper_trades_opened_at_idx ON paper_trades(opened_at);
CREATE TABLE IF NOT EXISTS worker_events (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    level TEXT NOT NULL,
    message TEXT NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb
);
