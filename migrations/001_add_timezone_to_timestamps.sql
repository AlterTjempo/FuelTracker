-- Migration: Convert TIMESTAMP columns to TIMESTAMP WITH TIME ZONE
-- This fixes the timezone issue where timestamps were stored without timezone info
-- causing a 1-hour offset in Amsterdam timezone

-- Convert stations table timestamps
ALTER TABLE stations 
ALTER COLUMN first_seen TYPE TIMESTAMP WITH TIME ZONE 
USING first_seen AT TIME ZONE 'UTC';

ALTER TABLE stations 
ALTER COLUMN last_updated TYPE TIMESTAMP WITH TIME ZONE 
USING last_updated AT TIME ZONE 'UTC';

-- Convert fuel_prices table timestamp
ALTER TABLE fuel_prices 
ALTER COLUMN timestamp TYPE TIMESTAMP WITH TIME ZONE 
USING timestamp AT TIME ZONE 'UTC';

-- Verify the migration
SELECT 
    table_name, 
    column_name, 
    data_type 
FROM information_schema.columns 
WHERE table_name IN ('stations', 'fuel_prices') 
  AND column_name IN ('first_seen', 'last_updated', 'timestamp')
ORDER BY table_name, column_name;
