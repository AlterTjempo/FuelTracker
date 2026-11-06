-- Refined products, Brent (USD) and EUR/USD for the trend model.
-- (Also applied automatically at startup by schema_migrations.py.)
CREATE TABLE IF NOT EXISTS market_prices (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    series VARCHAR NOT NULL,
    source VARCHAR NOT NULL,
    value DOUBLE PRECISION NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_market_series_time ON market_prices (series, timestamp);
