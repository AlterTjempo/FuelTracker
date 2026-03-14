"""
Migration script to convert existing TIMESTAMP columns to TIMESTAMP WITH TIME ZONE
and set all existing timestamps to UTC timezone
"""

import psycopg2
from urllib.parse import urlparse
from config import settings

# Parse DATABASE_URL safely (handles passwords with special characters)
parsed = urlparse(settings.DATABASE_URL)
user = parsed.username
password = parsed.password
host = parsed.hostname
port = parsed.port or 5432
dbname = parsed.path.lstrip("/")

print(f"Connecting to database: {host}:{port}/{dbname}")

# Connect to database
conn = psycopg2.connect(
    host=host, port=port, dbname=dbname, user=user, password=password
)
conn.autocommit = True
cursor = conn.cursor()

print("Converting timestamp columns to TIMESTAMP WITH TIME ZONE...")

# Alter stations table
try:
    cursor.execute(
        """
        ALTER TABLE stations 
        ALTER COLUMN first_seen TYPE TIMESTAMP WITH TIME ZONE 
        USING first_seen AT TIME ZONE 'UTC';
    """
    )
    print("✓ Converted stations.first_seen")
except Exception as e:
    print(f"✗ Error converting stations.first_seen: {e}")

try:
    cursor.execute(
        """
        ALTER TABLE stations 
        ALTER COLUMN last_updated TYPE TIMESTAMP WITH TIME ZONE 
        USING last_updated AT TIME ZONE 'UTC';
    """
    )
    print("✓ Converted stations.last_updated")
except Exception as e:
    print(f"✗ Error converting stations.last_updated: {e}")

# Alter fuel_prices table
try:
    cursor.execute(
        """
        ALTER TABLE fuel_prices 
        ALTER COLUMN timestamp TYPE TIMESTAMP WITH TIME ZONE 
        USING timestamp AT TIME ZONE 'UTC';
    """
    )
    print("✓ Converted fuel_prices.timestamp")
except Exception as e:
    print(f"✗ Error converting fuel_prices.timestamp: {e}")

print("\nMigration completed!")

# Close connection
cursor.close()
conn.close()
