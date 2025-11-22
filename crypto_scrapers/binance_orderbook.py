"""
Binance Order Book Depth Scraper
Fetches real-time order book data for optimal trade entry/exit timing
Uses REST API polling for reliability (not WebSocket complexity)
Critical for: Avoiding slippage, detecting walls, timing execution
"""

import os
import sys
import time
from datetime import datetime
from pathlib import Path
import psycopg2
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv(override=True)

import ccxt

# Database configuration
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '54594')
DB_NAME = os.getenv('DB_NAME', 'pjx')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'postgres')

# Scraper configuration
UPDATE_INTERVAL = 30  # Seconds between updates (real-time but not excessive)
DEPTH_LEVELS = 20  # Number of bid/ask levels to fetch

# All 42 tokens we track
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


class OrderBookScraper:
    """Fetches order book depth from Binance"""

    def __init__(self):
        self.exchange = None
        self.db_conn = None
        self.failed_tokens = set()
        self.cycle_count = 0
        self.cycles_with_no_data = 0  # Track consecutive empty cycles

    def init_exchange(self):
        """Initialize Binance connection"""
        self.exchange = ccxt.binance({
            'enableRateLimit': True,
            'timeout': 5000,  # Reduced to 5 second timeout for faster recovery
            'options': {'defaultType': 'spot'}
        })
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Connected to Binance API (5s timeout)")

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

    def fetch_order_book(self, symbol):
        """Fetch order book for a single token"""
        try:
            # Fetch order book depth
            order_book = self.exchange.fetch_order_book(symbol, limit=DEPTH_LEVELS)

            # Extract bids and asks
            bids = order_book['bids']  # [[price, amount], ...]
            asks = order_book['asks']  # [[price, amount], ...]

            if not bids or not asks:
                return None

            # Best bid/ask
            best_bid = float(bids[0][0])
            best_ask = float(asks[0][0])

            # Bid-ask spread
            spread = best_ask - best_bid
            spread_pct = (spread / best_bid) * 100 if best_bid > 0 else 0

            # Calculate total volumes
            total_bid_volume = sum(float(price) * float(amount) for price, amount in bids)
            total_ask_volume = sum(float(price) * float(amount) for price, amount in asks)

            # Liquidity within 1% of best price
            bid_1pct_threshold = best_bid * 0.99
            ask_1pct_threshold = best_ask * 1.01

            bid_liquidity_1pct = sum(
                float(price) * float(amount)
                for price, amount in bids
                if float(price) >= bid_1pct_threshold
            )

            ask_liquidity_1pct = sum(
                float(price) * float(amount)
                for price, amount in asks
                if float(price) <= ask_1pct_threshold
            )

            # Order imbalance: positive = more buying pressure, negative = more selling pressure
            # Formula: (bid_volume - ask_volume) / (bid_volume + ask_volume)
            total_volume = total_bid_volume + total_ask_volume
            order_imbalance = (total_bid_volume - total_ask_volume) / total_volume if total_volume > 0 else 0

            # Parse token name
            token = symbol.split('/')[0]

            return {
                'token': token,
                'timestamp': datetime.now(),
                'best_bid': best_bid,
                'best_ask': best_ask,
                'bid_ask_spread': spread,
                'bid_liquidity_1pct': bid_liquidity_1pct,
                'ask_liquidity_1pct': ask_liquidity_1pct,
                'order_imbalance': order_imbalance,
                'total_bid_volume': total_bid_volume,
                'total_ask_volume': total_ask_volume,
                'source': 'binance'
            }

        except Exception as e:
            error_msg = str(e).lower()

            if 'symbol' in error_msg or 'not found' in error_msg:
                print(f"[WARNING] {symbol} not available on Binance - skipping")
                self.failed_tokens.add(symbol)
            elif 'timeout' in error_msg or 'timed out' in error_msg:
                print(f"[WARNING] Timeout fetching {symbol} (5s limit exceeded), will retry next cycle...")
                # Don't add to failed_tokens for timeout errors - transient issue
            elif 'rate' in error_msg or 'limit' in error_msg:
                print(f"[WARNING] Rate limit hit for {symbol}, backing off...")
                time.sleep(2)  # Reduced from 3 to 2 seconds
            else:
                # Don't add to failed_tokens for transient errors
                print(f"[ERROR] Failed to fetch {symbol}: {e} (will retry)")

            return None

    def save_to_db(self, records):
        """Save order book data to database"""
        if not records:
            return 0

        cursor = self.db_conn.cursor()
        saved = 0

        try:
            for record in records:
                try:
                    cursor.execute("""
                        INSERT INTO order_book_depth
                        (token, timestamp, best_bid, best_ask, bid_ask_spread,
                         bid_liquidity_1pct, ask_liquidity_1pct, order_imbalance,
                         total_bid_volume, total_ask_volume, source)
                        VALUES (%(token)s, %(timestamp)s, %(best_bid)s, %(best_ask)s,
                                %(bid_ask_spread)s, %(bid_liquidity_1pct)s, %(ask_liquidity_1pct)s,
                                %(order_imbalance)s, %(total_bid_volume)s, %(total_ask_volume)s, %(source)s)
                    """, record)
                    saved += 1
                except Exception as e:
                    print(f"[WARNING] Failed to insert {record['token']}: {e}")
                    # Don't rollback the entire transaction, just skip this record
                    continue

            self.db_conn.commit()

            if saved == 0 and len(records) > 0:
                print(f"[WARNING] No records were saved out of {len(records)} attempted")

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
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Order Book Cycle #{self.cycle_count}")
        print(f"Fetching depth for {len(TOKENS) - len(self.failed_tokens)} active tokens")

        # Clear failed tokens every 3 cycles to give them another chance (more frequent retries)
        if self.cycle_count % 3 == 0 and self.failed_tokens:
            print(f"[INFO] Clearing {len(self.failed_tokens)} failed tokens for retry")
            self.failed_tokens.clear()

        # Force recovery if all tokens have failed
        if len(self.failed_tokens) >= len(TOKENS):
            print(f"[FORCE RECOVERY] All {len(TOKENS)} tokens failed - clearing for retry")
            self.failed_tokens.clear()
            self.init_exchange()  # Reconnect to exchange

        print('='*70)

        all_records = []
        successful = 0

        for symbol in TOKENS:
            if symbol in self.failed_tokens:
                continue

            # Small delay to avoid rate limits
            time.sleep(0.05)

            record = self.fetch_order_book(symbol)
            if record:
                all_records.append(record)
                successful += 1

                # Show key metrics
                imbalance = record['order_imbalance']
                spread_pct = (record['bid_ask_spread'] / record['best_bid']) * 100

                # Signal indicators
                signal = ""
                if abs(imbalance) > 0.3:
                    signal = "[BUY PRESSURE]" if imbalance > 0 else "[SELL PRESSURE]"

                print(f"[OK] {record['token']:<8} "
                      f"Bid: ${record['best_bid']:>10.6f} "
                      f"Ask: ${record['best_ask']:>10.6f} "
                      f"Spread: {spread_pct:.4f}% "
                      f"Imbalance: {imbalance:>6.3f} {signal}")

        # Save to database
        saved = self.save_to_db(all_records)

        # Summary
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Cycle complete:")
        print(f"  Successful: {successful}")
        print(f"  Saved: {saved}")
        if self.failed_tokens:
            print(f"  Failed tokens: {len(self.failed_tokens)}")

        # Track empty cycles
        if saved == 0:
            self.cycles_with_no_data += 1
            if self.cycles_with_no_data >= 3:
                print(f"[WARNING] {self.cycles_with_no_data} consecutive empty cycles")
        else:
            self.cycles_with_no_data = 0

        return saved

    def run(self):
        """Main loop"""
        print("\n" + "="*70)
        print("BINANCE ORDER BOOK DEPTH SCRAPER")
        print(f"Tracking {len(TOKENS)} tokens")
        print(f"Update interval: {UPDATE_INTERVAL} seconds")
        print(f"Depth levels: {DEPTH_LEVELS}")
        print("="*70)

        self.init_exchange()
        self.init_db()

        while True:
            try:
                cycle_start = time.time()
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Starting cycle #{self.cycle_count + 1}...")
                saved = self.run_cycle()

                if saved == 0 and self.cycle_count > 1:
                    print("[WARNING] No data saved this cycle")

                # Auto-recovery: If stuck for 2 consecutive cycles, try reconnecting
                if self.cycles_with_no_data >= 2:
                    print(f"[AUTO-RECOVERY] {self.cycles_with_no_data} empty cycles, reconnecting to Binance...")
                    try:
                        self.init_exchange()
                        print("[OK] Reconnected to Binance")
                        self.cycles_with_no_data = 0
                        self.failed_tokens.clear()
                        print("[INFO] Cleared all failed tokens for fresh retry")
                    except Exception as e:
                        print(f"[ERROR] Reconnection failed: {e}")

                elapsed = time.time() - cycle_start
                sleep_time = max(1, UPDATE_INTERVAL - elapsed)
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Sleeping for {sleep_time:.0f} seconds (cycle took {elapsed:.1f}s)...")
                time.sleep(sleep_time)
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Woke from sleep, starting next cycle...")

            except KeyboardInterrupt:
                print("\n[INFO] Shutting down...")
                break

            except Exception as e:
                print(f"[ERROR] Cycle failed: {e}")
                print("Retrying in 30 seconds...")
                time.sleep(30)

        if self.db_conn:
            self.db_conn.close()


def main():
    scraper = OrderBookScraper()
    scraper.run()


if __name__ == "__main__":
    main()
