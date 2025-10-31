"""
Setup script to create funding_rates table
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

def create_funding_table():
    """Create funding_rates table and indexes"""

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

        print("Creating funding_rates table...")

        # Create table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS funding_rates (
                id SERIAL PRIMARY KEY,
                token VARCHAR(20) NOT NULL,
                funding_rate NUMERIC(10,6) NOT NULL,
                next_funding_time TIMESTAMP WITH TIME ZONE,
                mark_price NUMERIC(20,8),
                index_price NUMERIC(20,8),
                source VARCHAR(50) DEFAULT 'binance',
                scraped_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT unique_funding UNIQUE (token, scraped_at)
            );
        """)

        print("Creating indexes...")

        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_funding_token ON funding_rates(token);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_funding_scraped_at ON funding_rates(scraped_at DESC);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_funding_rate ON funding_rates(funding_rate DESC);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_funding_token_time ON funding_rates(token, scraped_at DESC);")

        conn.commit()

        print("[SUCCESS] Created funding_rates table and indexes!")

        # Verify table exists
        cursor.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'funding_rates'
            ORDER BY ordinal_position;
        """)

        print("\nTable schema:")
        for row in cursor.fetchall():
            print(f"  {row[0]:<25} {row[1]}")

        cursor.close()
        conn.close()

    except Exception as e:
        print(f"[ERROR] Error creating table: {e}")
        raise


if __name__ == "__main__":
    create_funding_table()