"""
Setup script to create liquidations table
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

def create_liquidations_table():
    """Create liquidations table and indexes"""

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

        print("Creating liquidations table...")

        # Create table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS liquidations (
                id SERIAL PRIMARY KEY,
                token VARCHAR(20) NOT NULL,
                side VARCHAR(10) NOT NULL,
                liquidation_value NUMERIC(20,8) NOT NULL,
                price NUMERIC(20,8),
                quantity NUMERIC(20,8),
                timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
                source VARCHAR(50) DEFAULT 'binance',
                scraped_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)

        print("Creating indexes...")

        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_liquidations_token ON liquidations(token);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_liquidations_timestamp ON liquidations(timestamp DESC);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_liquidations_value ON liquidations(liquidation_value DESC);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_liquidations_side ON liquidations(side);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_liquidations_token_time ON liquidations(token, timestamp DESC);")

        conn.commit()

        print("[SUCCESS] Created liquidations table and indexes!")

        # Verify table exists
        cursor.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'liquidations'
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
    create_liquidations_table()