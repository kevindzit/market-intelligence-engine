"""
Binance Funding Rates Scraper
Fetches perpetual futures funding rates for market leverage analysis
Updates every hour (funding rates change every 8 hours, we monitor continuously)
Critical for detecting overleveraged positions and potential reversals
"""

import os
import sys
import time
from datetime import datetime
from pathlib import Path
import psycopg2
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv()

import ccxt

# Database configuration
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '54594')
DB_NAME = os.getenv('DB_NAME', 'postgres')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'postgres')

# Scraper configuration
UPDATE_INTERVAL = 60 * 60  # 1 hour (funding rates change every 8 hours)

# All 42 tokens - using perpetual futures pairs
TOKENS = [
    'PEPE/USDT', 'DOGE/USDT', 'SHIB/USDT', 'BONK/USDT', 'WIF/USDT',
    'BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'XRP/USDT',
    'ADA/USDT', 'TRX/USDT', 'LTC/USDT',
    'UNI/USDT', 'AAVE/USDT', 'LDO/USDT', 'MKR/USDT', 'CRV/USDT',
    'GMX/USDT', 'SNX/USDT', 'LINK/USDT',
    'AVAX/USDT', 'DOT/USDT', 'NEAR/USDT', 'ATOM/USDT', 'ICP/USDT',
    'ALGO/USDT', 'FTM/USDT',
    'ARB/USDT', 'OP/USDT', 'MATIC/USDT', 'METIS/USDT', 'IMX/USDT',
    'RENDER/USDT', 'FET/USDT', 'GRT/USDT', 'OCEAN/USDT', 'AGIX/USDT', 'TAO/USDT',
    'SUI/USDT', 'TON/USDT', 'SEI/USDT'
]


class FundingRateScraper:
    """Fetches funding rates from Binance perpetual futures"""

    def __init__(self):
        self.exchange = None
        self.db_conn = None
        self.failed_tokens = set()
        self.cycle_count = 0

    def init_exchange(self):
        """Initialize Binance futures connection"""
        self.exchange = ccxt.binance({
            'enableRateLimit': True,
            'options': {'defaultType': 'future'}  # Use perpetual futures
        })
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Connected to Binance Futures API")

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

    def fetch_funding_rate(self, symbol):
        """Fetch funding rate for a single token"""
        try:
            # Fetch funding rate
            funding_rate_data = self.exchange.fetch_funding_rate(symbol)

            # Parse token name
            token = symbol.split('/')[0]

            # Extract data
            funding_rate = funding_rate_data.get('fundingRate', 0)
            next_funding_time = funding_rate_data.get('fundingTimestamp')
            mark_price = funding_rate_data.get('markPrice')
            index_price = funding_rate_data.get('indexPrice')

            # Convert timestamp to datetime
            if next_funding_time:
                next_funding_time = datetime.fromtimestamp(next_funding_time / 1000)

            return {
                'token': token,
                'funding_rate': float(funding_rate) if funding_rate else 0,
                'next_funding_time': next_funding_time,
                'mark_price': float(mark_price) if mark_price else None,
                'index_price': float(index_price) if index_price else None,
                'source': 'binance'
            }

        except Exception as e:
            error_msg = str(e).lower()

            if 'symbol' in error_msg or 'not found' in error_msg:
                print(f"[WARNING] {symbol} futures not available")
                self.failed_tokens.add(symbol)
            elif 'rate' in error_msg:
                print(f"[WARNING] Rate limit hit, slowing down...")
                time.sleep(3)
            else:
                print(f"[ERROR] Failed to fetch {symbol}: {e}")

            return None

    def save_to_db(self, records):
        """Save funding rate data to database"""
        if not records:
            return 0

        cursor = self.db_conn.cursor()
        saved = 0

        try:
            for record in records:
                try:
                    cursor.execute("""
                        INSERT INTO funding_rates
                        (token, funding_rate, next_funding_time, mark_price, index_price, source)
                        VALUES (%(token)s, %(funding_rate)s, %(next_funding_time)s,
                                %(mark_price)s, %(index_price)s, %(source)s)
                    """, record)
                    saved += 1
                except Exception as e:
                    print(f"[WARNING] Failed to insert {record['token']}: {e}")
                    self.db_conn.rollback()

            self.db_conn.commit()

        except Exception as e:
            print(f"[ERROR] Database save failed: {e}")
            self.db_conn.rollback()

        finally:
            cursor.close()

        return saved

    def run_cycle(self):
        """Run one collection cycle for all tokens"""
        self.cycle_count += 1
        print(f"\n{'='*70}")
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Funding Rates Cycle #{self.cycle_count}")
        print(f"Fetching rates for {len(TOKENS) - len(self.failed_tokens)} active tokens")
        print('='*70)

        all_records = []
        successful = 0

        for symbol in TOKENS:
            if symbol in self.failed_tokens:
                continue

            # Small delay to avoid rate limits
            time.sleep(0.1)

            record = self.fetch_funding_rate(symbol)
            if record:
                all_records.append(record)
                successful += 1

                # Display with signal interpretation
                rate = record['funding_rate']
                rate_pct = rate * 100

                # Signal interpretation
                signal = ""
                if rate < -0.0001:  # -0.01%
                    signal = "[SHORTS OVERLEVERAGED - POTENTIAL BOUNCE]"
                elif rate > 0.0001:  # +0.01%
                    signal = "[LONGS OVERLEVERAGED - POTENTIAL DUMP]"

                print(f"[OK] {record['token']:<8} "
                      f"Rate: {rate_pct:>7.4f}% "
                      f"Mark: ${record['mark_price']:>10.2f} {signal}")

        # Save to database
        saved = self.save_to_db(all_records)

        # Summary
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Cycle complete:")
        print(f"  Successful: {successful}")
        print(f"  Saved: {saved}")
        if self.failed_tokens:
            print(f"  Failed tokens: {len(self.failed_tokens)}")

        return saved

    def run(self):
        """Main loop"""
        print("\n" + "="*70)
        print("BINANCE FUNDING RATES SCRAPER")
        print(f"Tracking {len(TOKENS)} tokens")
        print(f"Update interval: {UPDATE_INTERVAL//60} minutes")
        print("Funding rates change every 8 hours (00:00, 08:00, 16:00 UTC)")
        print("="*70)

        self.init_exchange()
        self.init_db()

        while True:
            try:
                saved = self.run_cycle()

                if saved == 0 and self.cycle_count > 1:
                    print("[WARNING] No data saved this cycle")

                print(f"\nNext update in {UPDATE_INTERVAL//60} minutes...")
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
    scraper = FundingRateScraper()
    scraper.run()


if __name__ == "__main__":
    main()