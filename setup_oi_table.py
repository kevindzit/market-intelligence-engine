"""
Setup script to create open_interest table
Run this once to create the table in your database
"""

import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

# Database configuration
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '54594')
DB_NAME = os.getenv('DB_NAME', 'postgres')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'postgres')

def create_oi_table():
    """Create open_interest table and indexes"""

    try:
        # Connect to database
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )

        cursor = conn.cursor()

        print("Creating open_interest table...")

        # Create table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS open_interest (
                id SERIAL PRIMARY KEY,
                token VARCHAR(20) NOT NULL,
                open_interest_contracts NUMERIC(30,8) NOT NULL,
                open_interest_usd NUMERIC(30,2) NOT NULL,
                mark_price NUMERIC(20,8),
                timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
                source VARCHAR(50) DEFAULT 'binance',
                scraped_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)

        print("Creating indexes...")

        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_oi_token ON open_interest(token);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_oi_timestamp ON open_interest(timestamp DESC);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_oi_usd ON open_interest(open_interest_usd DESC);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_oi_token_time ON open_interest(token, timestamp DESC);")

        conn.commit()

        print("[SUCCESS] Created open_interest table and indexes!")

        # Verify table exists
        cursor.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'open_interest'
            ORDER BY ordinal_position;
        """)

        print("\nTable schema:")
        for row in cursor.fetchall():
            print(f"  {row[0]:<30} {row[1]}")

        cursor.close()
        conn.close()

    except Exception as e:
        print(f"[ERROR] Error creating table: {e}")
        raise


if __name__ == "__main__":
    create_oi_table()