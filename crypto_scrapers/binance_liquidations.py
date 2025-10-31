"""
Binance Liquidations Scraper
Tracks real-time liquidations for flash crash/pump detection
Updates every 30 seconds with aggregated liquidation data
Critical for catching reversals during capitulation events
"""

import os
import sys
import time
import json
from datetime import datetime, timedelta
from pathlib import Path
import psycopg2
import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv()

# Database configuration
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '54594')
DB_NAME = os.getenv('DB_NAME', 'postgres')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'postgres')

# Scraper configuration
UPDATE_INTERVAL = 30  # 30 seconds between updates
API_URL = "https://fapi.binance.com/fapi/v1/allForceOrders"

# All tokens we track
TOKENS = [
    'PEPE', 'DOGE', 'SHIB', 'BONK', 'WIF',
    'BTC', 'ETH', 'SOL', 'BNB', 'XRP',
    'ADA', 'TRX', 'LTC',
    'UNI', 'AAVE', 'LDO', 'MKR', 'CRV',
    'GMX', 'SNX', 'LINK',
    'AVAX', 'DOT', 'NEAR', 'ATOM', 'ICP',
    'ALGO', 'FTM',
    'ARB', 'OP', 'MATIC', 'METIS', 'IMX',
    'RENDER', 'FET', 'GRT', 'OCEAN', 'AGIX', 'TAO',
    'SUI', 'TON', 'SEI'
]

# Map token symbols to Binance futures format
TOKEN_MAP = {token: f"{token}USDT" for token in TOKENS}


class LiquidationScraper:
    """Fetches liquidation data from Binance"""

    def __init__(self):
        self.db_conn = None
        self.cycle_count = 0
        self.liquidation_cache = {}  # Track recent liquidations

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

    def fetch_liquidations(self, token):
        """Fetch recent liquidations for a token"""
        try:
            symbol = TOKEN_MAP.get(token)
            if not symbol:
                return []

            # Get liquidations from last 5 minutes
            params = {
                'symbol': symbol,
                'limit': 100  # Max recent liquidations
            }

            response = requests.get(API_URL, params=params, timeout=5)

            if response.status_code == 200:
                data = response.json()

                liquidations = []
                for liq in data:
                    # Parse Binance liquidation data
                    liquidations.append({
                        'token': token,
                        'side': liq.get('side', 'UNKNOWN'),
                        'price': float(liq.get('price', 0)),
                        'quantity': float(liq.get('origQty', 0)),
                        'liquidation_value': float(liq.get('price', 0)) * float(liq.get('origQty', 0)),
                        'timestamp': datetime.fromtimestamp(liq.get('time', 0) / 1000),
                        'source': 'binance'
                    })

                return liquidations

            return []

        except Exception as e:
            # Many tokens won't have futures, that's ok
            return []

    def aggregate_liquidations(self, all_liquidations):
        """Aggregate liquidations by token for analysis"""
        aggregated = {}

        for liq in all_liquidations:
            token = liq['token']
            if token not in aggregated:
                aggregated[token] = {
                    'total_value': 0,
                    'long_liquidations': 0,
                    'short_liquidations': 0,
                    'count': 0,
                    'max_single': 0
                }

            aggregated[token]['total_value'] += liq['liquidation_value']
            aggregated[token]['count'] += 1
            aggregated[token]['max_single'] = max(aggregated[token]['max_single'], liq['liquidation_value'])

            if liq['side'].upper() == 'BUY':
                aggregated[token]['short_liquidations'] += liq['liquidation_value']
            else:
                aggregated[token]['long_liquidations'] += liq['liquidation_value']

        return aggregated

    def save_to_db(self, liquidations):
        """Save liquidation data to database"""
        if not liquidations:
            return 0

        cursor = self.db_conn.cursor()
        saved = 0

        try:
            for liq in liquidations:
                try:
                    # Check if we've already saved this liquidation
                    cache_key = f"{liq['token']}_{liq['timestamp']}_{liq['liquidation_value']}"
                    if cache_key in self.liquidation_cache:
                        continue

                    cursor.execute("""
                        INSERT INTO liquidations
                        (token, side, liquidation_value, price, quantity, timestamp, source)
                        VALUES (%(token)s, %(side)s, %(liquidation_value)s,
                                %(price)s, %(quantity)s, %(timestamp)s, %(source)s)
                    """, liq)

                    saved += 1
                    self.liquidation_cache[cache_key] = True

                    # Keep cache size reasonable
                    if len(self.liquidation_cache) > 10000:
                        # Remove oldest entries
                        keys = list(self.liquidation_cache.keys())[:5000]
                        for k in keys:
                            del self.liquidation_cache[k]

                except Exception as e:
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
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Liquidation Cycle #{self.cycle_count}")
        print('='*70)

        all_liquidations = []
        tokens_with_liquidations = 0

        for token in TOKENS:
            liquidations = self.fetch_liquidations(token)
            if liquidations:
                all_liquidations.extend(liquidations)
                tokens_with_liquidations += 1

        # Save to database
        saved = self.save_to_db(all_liquidations)

        # Aggregate for display
        if all_liquidations:
            aggregated = self.aggregate_liquidations(all_liquidations)

            print(f"\nLiquidations detected for {tokens_with_liquidations} tokens:")
            print("-" * 50)

            # Sort by total liquidation value
            sorted_tokens = sorted(aggregated.items(), key=lambda x: x[1]['total_value'], reverse=True)

            for token, data in sorted_tokens[:10]:  # Show top 10
                total_value = data['total_value']
                long_pct = (data['long_liquidations'] / total_value * 100) if total_value > 0 else 0
                short_pct = (data['short_liquidations'] / total_value * 100) if total_value > 0 else 0

                # Signal interpretation
                signal = ""
                if total_value > 1000000:  # Over $1M liquidated
                    if long_pct > 70:
                        signal = "[LONG SQUEEZE - POTENTIAL BOTTOM]"
                    elif short_pct > 70:
                        signal = "[SHORT SQUEEZE - POTENTIAL TOP]"
                    else:
                        signal = "[HIGH VOLATILITY]"

                print(f"{token:<8} ${total_value:>12,.0f} "
                      f"(Longs: {long_pct:>5.1f}% Shorts: {short_pct:>5.1f}%) {signal}")

            # Check for extreme liquidation events
            total_all = sum(agg['total_value'] for agg in aggregated.values())
            if total_all > 10000000:  # Over $10M total
                print(f"\n[ALERT] MAJOR LIQUIDATION EVENT: ${total_all:,.0f} total liquidated!")
                print("         Potential reversal opportunity!")

        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Cycle complete:")
        print(f"  New liquidations saved: {saved}")
        print(f"  Tokens with activity: {tokens_with_liquidations}")

        return saved

    def run(self):
        """Main loop"""
        print("\n" + "="*70)
        print("BINANCE LIQUIDATIONS SCRAPER")
        print(f"Tracking {len(TOKENS)} tokens")
        print(f"Update interval: {UPDATE_INTERVAL} seconds")
        print("Purpose: Detect flash crashes and capitulation events")
        print("="*70)

        self.init_db()

        while True:
            try:
                self.run_cycle()

                print(f"\nNext update in {UPDATE_INTERVAL} seconds...")
                time.sleep(UPDATE_INTERVAL)

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
    scraper = LiquidationScraper()
    scraper.run()


if __name__ == "__main__":
    main()