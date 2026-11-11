from sqlalchemy import text


def apply_schema_migrations(engine) -> None:
    statements = [
        "ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN NOT NULL DEFAULT FALSE",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username ON users(username)",
        """
        CREATE TABLE IF NOT EXISTS market_prices (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
            series VARCHAR NOT NULL,
            source VARCHAR NOT NULL,
            value DOUBLE PRECISION NOT NULL
        )
        """,
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_market_series_time ON market_prices (series, timestamp)",
        "ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS password_changed_at TIMESTAMP WITH TIME ZONE",
        "ALTER TABLE IF EXISTS refuel_logs ADD COLUMN IF NOT EXISTS reference_source VARCHAR NOT NULL DEFAULT 'area'",
        "ALTER TABLE IF EXISTS refuel_logs ADD COLUMN IF NOT EXISTS manual_reference_price DOUBLE PRECISION",
        """
        CREATE TABLE IF NOT EXISTS visitor_location_cache (
            id SERIAL PRIMARY KEY,
            ip_hash VARCHAR NOT NULL UNIQUE,
            country VARCHAR,
            region VARCHAR,
            city VARCHAR,
            latitude DOUBLE PRECISION,
            longitude DOUBLE PRECISION,
            resolved_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_location_cache_coordinates ON visitor_location_cache (latitude, longitude)",
        """
        CREATE TABLE IF NOT EXISTS traffic_events (
            id SERIAL PRIMARY KEY,
            page VARCHAR NOT NULL,
            path VARCHAR NOT NULL,
            source VARCHAR NOT NULL DEFAULT 'direct',
            country VARCHAR,
            region VARCHAR,
            city VARCHAR,
            latitude DOUBLE PRECISION,
            longitude DOUBLE PRECISION,
            visited_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_traffic_event_visited_at ON traffic_events (visited_at)",
        "CREATE INDEX IF NOT EXISTS idx_traffic_event_page_source ON traffic_events (page, source)",
    ]

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
