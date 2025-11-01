"""
Fear & Greed Index Scraper
Fetches crypto market sentiment from Alternative.me API
Updates daily - simple 0-100 score for market psychology
"""

import os
import sys
import time
from datetime import datetime
from pathlib import Path
import psycopg2
import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv(override=True)

# Database configuration
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '54594')
DB_NAME = os.getenv('DB_NAME', 'postgres')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'postgres')

# Scraper configuration
UPDATE_INTERVAL = 6 * 60 * 60  # 6 hours (updates daily, we check periodically)
API_URL = "https://api.alternative.me/fng/"


class FearGreedScraper:
    """Fetches Fear & Greed Index from Alternative.me"""

    def __init__(self):
        self.db_conn = None
        self.cycle_count = 0

    def init_db(self):
        """Initialize database connection"""
        try:
            self.db_conn = psycopg2.connect(
                host=DB_HOST,
                port=DB_PORT,
                database=DB_NAME,
                user=DB_USER,
                password=DB_PASSWORD
            )
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Connected to PostgreSQL")
        except Exception as e:
            print(f"[ERROR] Database connection failed: {e}")
            raise

    def fetch_index(self):
        """Fetch current Fear & Greed Index"""
        try:
            response = requests.get(API_URL, timeout=10)
            response.raise_for_status()

            data = response.json()

            if 'data' not in data or len(data['data']) == 0:
                print("[ERROR] Invalid API response")
                return None

            latest = data['data'][0]

            value = int(latest['value'])
            classification = latest['value_classification']
            timestamp = datetime.fromtimestamp(int(latest['timestamp']))

            return {
                'value': value,
                'classification': classification,
                'timestamp': timestamp
            }

        except Exception as e:
            print(f"[ERROR] Failed to fetch Fear & Greed Index: {e}")
            return None

    def save_to_db(self, record):
        """Save Fear & Greed Index to database"""
        if not record:
            return False

        cursor = self.db_conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO fear_greed_index (value, classification, timestamp)
                VALUES (%(value)s, %(classification)s, %(timestamp)s)
                ON CONFLICT (timestamp) DO NOTHING
            """, record)

            saved = cursor.rowcount > 0
            self.db_conn.commit()
            return saved

        except Exception as e:
            print(f"[ERROR] Database save failed: {e}")
            self.db_conn.rollback()
            return False

        finally:
            cursor.close()

    def run_cycle(self):
        """Run one collection cycle"""
        self.cycle_count += 1
        print(f"\n{'='*60}")
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Fear & Greed Index Cycle #{self.cycle_count}")
        print('='*60)

        record = self.fetch_index()

        if record:
            value = record['value']
            classification = record['classification']

            # Interpret the score
            interpretation = ""
            if value <= 20:
                interpretation = "[EXTREME FEAR - Potential buying opportunity]"
            elif value <= 40:
                interpretation = "[FEAR - Market cautious]"
            elif value <= 60:
                interpretation = "[NEUTRAL - Balanced market]"
            elif value <= 80:
                interpretation = "[GREED - Market optimistic]"
            else:
                interpretation = "[EXTREME GREED - Potential selling opportunity]"

            print(f"[OK] Fear & Greed Index: {value}/100")
            print(f"     Classification: {classification}")
            print(f"     {interpretation}")

            saved = self.save_to_db(record)

            if saved:
                print(f"     Saved to database")
            else:
                print(f"     Already in database (no update needed)")

            return True
        else:
            print("[ERROR] Failed to fetch index")
            return False

    def run(self):
        """Main loop"""
        print("\n" + "="*60)
        print("FEAR & GREED INDEX SCRAPER")
        print(f"Update interval: {UPDATE_INTERVAL//3600} hours")
        print("Source: Alternative.me API")
        print("="*60)

        self.init_db()

        while True:
            try:
                self.run_cycle()

                print(f"\nNext update in {UPDATE_INTERVAL//3600} hours...")
                time.sleep(UPDATE_INTERVAL)

            except KeyboardInterrupt:
                print("\n[INFO] Shutting down...")
                break

            except Exception as e:
                print(f"[ERROR] Cycle failed: {e}")
                print("Retrying in 60 seconds...")
                time.sleep(60)

        if self.db_conn:
            self.db_conn.close()


def main():
    scraper = FearGreedScraper()
    scraper.run()


if __name__ == "__main__":
    main()
