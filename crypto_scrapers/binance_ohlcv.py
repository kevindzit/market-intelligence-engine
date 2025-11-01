"""
Binance OHLCV Data Scraper
Fetches Open, High, Low, Close, Volume data for all tracked tokens
Uses public API (no authentication required)
Runs every 5 minutes to match Twitter scraper cycles
"""

import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv(override=True)

import ccxt  # Use synchronous version for Windows compatibility

# Database configuration
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '54594')
DB_NAME = os.getenv('DB_NAME', 'postgres')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'postgres')

# Scraper configuration
POLLING_INTERVAL = 5 * 60  # 5 minutes (matches Twitter scrapers)
TIMEFRAME = '5m'  # 5-minute candles
CANDLES_TO_FETCH = 12  # Last hour of data (12 x 5-min candles)

# All 42 tokens we track (using USDT pairs for best liquidity)
TOKENS = [
    # Meme Coins
    'PEPE/USDT', 'DOGE/USDT', 'SHIB/USDT', 'BONK/USDT', 'WIF/USDT',

    # Large Caps
    'BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'XRP/USDT',
    'ADA/USDT', 'TRX/USDT', 'LTC/USDT',

    # DeFi
    'UNI/USDT', 'AAVE/USDT', 'LDO/USDT', 'MKR/USDT', 'CRV/USDT',
    'GMX/USDT', 'SNX/USDT', 'LINK/USDT',

    # Layer 1s
    'AVAX/USDT', 'DOT/USDT', 'NEAR/USDT', 'ATOM/USDT', 'ICP/USDT',
    'ALGO/USDT', 'FTM/USDT',

    # Layer 2s
    'ARB/USDT', 'OP/USDT', 'MATIC/USDT', 'METIS/USDT', 'IMX/USDT',

    # AI/ML
    'RENDER/USDT', 'FET/USDT', 'GRT/USDT', 'OCEAN/USDT', 'AGIX/USDT', 'TAO/USDT',

    # Emerging
    'SUI/USDT', 'TON/USDT', 'SEI/USDT'
]


class BinanceOHLCVScraper:
    """Fetches OHLCV data from Binance public API"""

    def __init__(self):
        self.exchange = None
        self.db_conn = None
        self.failed_tokens = set()  # Track tokens that fail repeatedly
        self.cycle_count = 0

    def init_exchange(self):
        """Initialize CCXT exchange connection"""
        self.exchange = ccxt.binance({
            'enableRateLimit': True,  # Auto rate limiting
            'options': {
                'defaultType': 'spot',  # Use spot market (not futures)
            }
        })
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Connected to Binance API")

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

    def fetch_ohlcv(self, symbol):
        """Fetch OHLCV data for a single token"""
        try:
            # Fetch the candles
            ohlcv = self.exchange.fetch_ohlcv(
                symbol,
                timeframe=TIMEFRAME,
                limit=CANDLES_TO_FETCH
            )

            # Parse token name (remove /USDT)
            token = symbol.split('/')[0]

            # Convert to database format
            records = []
            for candle in ohlcv:
                timestamp_ms, open_price, high, low, close, volume = candle

                # Validate data
                if open_price <= 0 or volume < 0:
                    continue

                records.append({
                    'token': token,
                    'timeframe': TIMEFRAME,
                    'timestamp': datetime.fromtimestamp(timestamp_ms / 1000),
                    'open': float(open_price),
                    'high': float(high),
                    'low': float(low),
                    'close': float(close),
                    'volume': float(volume),
                    'source': 'binance'
                })

            return records

        except Exception as e:
            error_msg = str(e).lower()

            # Handle specific errors
            if 'symbol' in error_msg or 'not found' in error_msg:
                print(f"[WARNING] {symbol} not available on Binance")
                self.failed_tokens.add(symbol)
            elif 'rate' in error_msg:
                print(f"[WARNING] Rate limit hit, will retry later")
                time.sleep(5)
            else:
                print(f"[ERROR] Failed to fetch {symbol}: {e}")

            return []

    def save_to_db(self, all_records):
        """Save OHLCV data to database"""
        if not all_records:
            return 0

        cursor = self.db_conn.cursor()
        saved = 0

        try:
            # Use batch insert for efficiency
            for record in all_records:
                try:
                    cursor.execute("""
                        INSERT INTO crypto_ohlcv
                        (token, timeframe, timestamp, open, high, low, close, volume, source)
                        VALUES (%(token)s, %(timeframe)s, %(timestamp)s, %(open)s,
                                %(high)s, %(low)s, %(close)s, %(volume)s, %(source)s)
                        ON CONFLICT (token, timeframe, timestamp, source)
                        DO UPDATE SET
                            open = EXCLUDED.open,
                            high = EXCLUDED.high,
                            low = EXCLUDED.low,
                            close = EXCLUDED.close,
                            volume = EXCLUDED.volume,
                            scraped_at = CURRENT_TIMESTAMP
                    """, record)
                    saved += 1
                except Exception as e:
                    print(f"[WARNING] Failed to insert record: {e}")
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
        print(f"\n{'='*60}")
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Starting OHLCV cycle #{self.cycle_count}")
        print(f"Fetching {TIMEFRAME} candles for {len(TOKENS)} tokens")
        print('='*60)

        all_records = []
        successful = 0
        failed = 0

        # Fetch data for each token
        for symbol in TOKENS:
            # Skip tokens that consistently fail
            if symbol in self.failed_tokens:
                continue

            # Small delay between requests to be nice to the API
            time.sleep(0.1)

            records = self.fetch_ohlcv(symbol)
            if records:
                all_records.extend(records)
                successful += 1

                # Show current price for monitoring
                latest = records[-1] if records else None
                if latest:
                    print(f"[OK] {symbol:<12} ${latest['close']:>10.4f} "
                          f"(Vol: {latest['volume']:>12.0f})")
            else:
                failed += 1

        # Save to database
        saved = self.save_to_db(all_records)

        # Summary
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Cycle complete:")
        print(f"  Tokens: {successful} successful, {failed} failed")
        print(f"  Records saved: {saved}")

        # Show failed tokens if any
        if self.failed_tokens:
            print(f"  Permanently failed tokens: {', '.join(self.failed_tokens)}")

        return saved

    def run(self):
        """Main loop - runs every 5 minutes"""
        print("\n" + "="*60)
        print("BINANCE OHLCV DATA SCRAPER")
        print(f"Tracking {len(TOKENS)} tokens")
        print(f"Timeframe: {TIMEFRAME} candles")
        print(f"Interval: {POLLING_INTERVAL//60} minutes")
        print("="*60)

        # Initialize connections
        self.init_exchange()
        self.init_db()

        # Main loop
        while True:
            try:
                # Run collection cycle
                saved = self.run_cycle()

                # Health check
                if saved == 0 and self.cycle_count > 1:
                    print("[WARNING] No data saved this cycle")

                # Wait for next cycle
                print(f"\nNext cycle in {POLLING_INTERVAL//60} minutes...")
                time.sleep(POLLING_INTERVAL)

            except KeyboardInterrupt:
                print("\n[INFO] Shutting down...")
                break

            except Exception as e:
                print(f"[ERROR] Cycle failed: {e}")
                print("Retrying in 60 seconds...")
                time.sleep(60)

        # Cleanup
        if self.db_conn:
            self.db_conn.close()


def main():
    scraper = BinanceOHLCVScraper()
    scraper.run()


if __name__ == "__main__":
    main()