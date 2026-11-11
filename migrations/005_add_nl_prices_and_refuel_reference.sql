-- Dutch average pump prices (CBS) + selectable reference price for the savings meter.
-- (Also applied automatically at startup; this file is for manual deployments.)
CREATE TABLE IF NOT EXISTS nl_fuel_prices (
    day DATE PRIMARY KEY,
    euro95 DOUBLE PRECISION,
    diesel DOUBLE PRECISION
);
ALTER TABLE refuel_logs ADD COLUMN IF NOT EXISTS reference_source VARCHAR NOT NULL DEFAULT 'area';
ALTER TABLE refuel_logs ADD COLUMN IF NOT EXISTS manual_reference_price DOUBLE PRECISION;
