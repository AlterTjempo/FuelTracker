-- Savings meter + token revocation on password change.
-- (The app also applies these automatically at startup via schema_migrations.py
-- / Base.metadata.create_all; this file is for manual deployments.)
ALTER TABLE users ADD COLUMN IF NOT EXISTS password_changed_at TIMESTAMP WITH TIME ZONE;

CREATE TABLE IF NOT EXISTS refuel_logs (
    id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    station_id VARCHAR REFERENCES stations(id),
    fuel_type VARCHAR NOT NULL,
    liters DOUBLE PRECISION NOT NULL,
    price_per_liter DOUBLE PRECISION NOT NULL,
    fueled_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_refuel_user_time ON refuel_logs(user_id, fueled_at);
