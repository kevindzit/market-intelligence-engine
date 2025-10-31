"""
Setup script to create fear_greed_index table
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

def create_feargreed_table():
    """Create fear_greed_index table and indexes"""

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

        print("Creating fear_greed_index table...")

        # Create table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fear_greed_index (
                id SERIAL PRIMARY KEY,
                value INTEGER NOT NULL,
                classification VARCHAR(20),
                timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
                scraped_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT unique_fear_greed UNIQUE (timestamp)
            );
        """)

        print("Creating indexes...")

        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_fear_greed_timestamp ON fear_greed_index(timestamp DESC);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_fear_greed_value ON fear_greed_index(value);")

        conn.commit()

        print("[SUCCESS] Created fear_greed_index table and indexes!")

        # Verify table exists
        cursor.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'fear_greed_index'
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
    create_feargreed_table()
