"""
Setup script to create order_book_depth table
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

def create_orderbook_table():
    """Create order_book_depth table and indexes"""

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

        print("Creating order_book_depth table...")

        # Create table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS order_book_depth (
                id SERIAL PRIMARY KEY,
                token VARCHAR(20) NOT NULL,
                timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
                best_bid NUMERIC(20,8) NOT NULL,
                best_ask NUMERIC(20,8) NOT NULL,
                bid_ask_spread NUMERIC(20,8) NOT NULL,
                bid_liquidity_1pct NUMERIC(30,8),
                ask_liquidity_1pct NUMERIC(30,8),
                order_imbalance NUMERIC(6,4),
                total_bid_volume NUMERIC(30,8),
                total_ask_volume NUMERIC(30,8),
                source VARCHAR(50) DEFAULT 'binance',
                scraped_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)

        print("Creating indexes...")

        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_orderbook_token ON order_book_depth(token);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_orderbook_timestamp ON order_book_depth(timestamp DESC);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_orderbook_token_time ON order_book_depth(token, timestamp DESC);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_orderbook_imbalance ON order_book_depth(order_imbalance DESC);")

        conn.commit()

        print("[SUCCESS] Created order_book_depth table and indexes!")

        # Verify table exists
        cursor.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'order_book_depth'
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
    create_orderbook_table()
