from sqlalchemy import text


def apply_schema_migrations(engine) -> None:
    statements = [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN NOT NULL DEFAULT FALSE",
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
