-- Migration 002: Use link as primary key for energy_news
-- Fixes "duplicate key value violates unique constraint energy_news_pkey"
-- caused by the integer sequence drifting out of sync.
-- The link column is already unique and is the natural key for articles.

BEGIN;

-- Drop the old integer primary key and the separate unique constraint on link
ALTER TABLE energy_news DROP CONSTRAINT energy_news_pkey;
ALTER TABLE energy_news DROP CONSTRAINT IF EXISTS energy_news_link_key;
ALTER TABLE energy_news DROP COLUMN id;

-- Promote link to primary key
ALTER TABLE energy_news ADD PRIMARY KEY (link);

-- Drop the now-redundant explicit index (PK already provides one)
DROP INDEX IF EXISTS idx_energy_news_link;

COMMIT;
