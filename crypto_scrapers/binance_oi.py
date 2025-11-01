"""
Binance Open Interest Scraper
Tracks total $ in active futures contracts (leverage indicator)
High OI + funding rate divergence = potential volatility
Updates every 5 minutes for all tracked tokens
"""

import os
import sys
import time
import requests
from datetime import datetime
from pathlib import Path
import psycopg2
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
UPDATE_INTERVAL = 5 * 60  # 5 minutes
BINANCE_API = "https://fapi.binance.com"

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

# Map to Binance futures symbols
TOKEN_MAP = {token: f"{token}USDT" for token in TOKENS}


class OpenInterestScraper:
    """Fetches Open Interest data from Binance"""

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

    def get_current_price(self, symbol):
        """Get current mark price for a symbol"""
        try:
            url = f"{BINANCE_API}/fapi/v1/premiumIndex"
            params = {'symbol': symbol}
            response = requests.get(url, params=params, timeout=5)

            if response.status_code == 200:
                data = response.json()
                return float(data.get('markPrice', 0))
        except:
            pass
        return None

    def fetch_open_interest(self, token):
        """Fetch open interest for a token"""
        try:
            symbol = TOKEN_MAP.get(token)
            if not symbol:
                return None

            # Get OI in contracts
            url = f"{BINANCE_API}/fapi/v1/openInterest"
            params = {'symbol': symbol}

            response = requests.get(url, params=params, timeout=5)

            if response.status_code == 200:
                data = response.json()
                oi_contracts = float(data.get('openInterest', 0))

                if oi_contracts == 0:
                    return None

                # Get current price to calculate USD value
                price = self.get_current_price(symbol)
                if not price:
                    return None

                oi_usd = oi_contracts * price

                return {
                    'token': token,
                    'open_interest_contracts': oi_contracts,
                    'open_interest_usd': oi_usd,
                    'mark_price': price,
                    'timestamp': datetime.now(),
                    'source': 'binance'
                }

            return None

        except Exception as e:
            # Many tokens won't have futures
            return None

    def calculate_oi_change(self, token, current_oi):
        """Calculate OI change vs 1 hour ago"""
        cursor = self.db_conn.cursor()

        try:
            cursor.execute("""
                SELECT open_interest_usd
                FROM open_interest
                WHERE token = %s
                AND timestamp > NOW() - INTERVAL '1 hour'
                ORDER BY timestamp ASC
                LIMIT 1
            """, (token,))

            result = cursor.fetchone()

            if result and result[0]:
                old_oi = float(result[0])
                if old_oi > 0:
                    change_pct = ((current_oi - old_oi) / old_oi) * 100
                    return change_pct

            return None

        except:
            return None
        finally:
            cursor.close()

    def save_to_db(self, oi_data):
        """Save OI data to database"""
        if not oi_data:
            return 0

        cursor = self.db_conn.cursor()
        saved = 0

        try:
            for oi in oi_data:
                try:
                    cursor.execute("""
                        INSERT INTO open_interest
                        (token, open_interest_contracts, open_interest_usd,
                         mark_price, timestamp, source)
                        VALUES (%(token)s, %(open_interest_contracts)s,
                                %(open_interest_usd)s, %(mark_price)s,
                                %(timestamp)s, %(source)s)
                    """, oi)

                    saved += 1

                except Exception as e:
                    self.db_conn.rollback()

            self.db_conn.commit()

        except Exception as e:
            print(f"[ERROR] Database save failed: {e}")
            self.db_conn.rollback()

        finally:
            cursor.close()

        return saved

    def analyze_oi_signals(self, oi_data):
        """Analyze OI data for trading signals"""
        signals = []

        for oi in oi_data:
            token = oi['token']
            oi_usd = oi['open_interest_usd']

            # Calculate OI change
            oi_change = self.calculate_oi_change(token, oi_usd)

            # Signal logic
            signal = None
            if oi_change:
                if oi_change > 20:
                    signal = f"[HIGH LEVERAGE BUILDUP +{oi_change:.1f}%]"
                elif oi_change < -20:
                    signal = f"[MASS DELEVERAGING {oi_change:.1f}%]"

            if signal:
                signals.append({
                    'token': token,
                    'oi_usd': oi_usd,
                    'oi_change': oi_change,
                    'signal': signal
                })

        return signals

    def run_cycle(self):
        """Run one collection cycle"""
        self.cycle_count += 1
        print(f"\n{'='*70}")
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Open Interest Cycle #{self.cycle_count}")
        print('='*70)

        all_oi = []
        tokens_tracked = 0

        for token in TOKENS:
            oi = self.fetch_open_interest(token)
            if oi:
                all_oi.append(oi)
                tokens_tracked += 1

            time.sleep(0.1)  # Rate limit protection

        # Save to database
        saved = self.save_to_db(all_oi)

        # Analyze for signals
        if all_oi:
            signals = self.analyze_oi_signals(all_oi)

            print(f"\nOpen Interest Summary ({tokens_tracked} tokens):")
            print("-" * 70)

            # Sort by OI value
            sorted_oi = sorted(all_oi, key=lambda x: x['open_interest_usd'], reverse=True)

            for oi in sorted_oi[:15]:  # Top 15
                token = oi['token']
                oi_usd = oi['open_interest_usd']
                oi_change = self.calculate_oi_change(token, oi_usd)

                change_str = f"({oi_change:+.1f}%)" if oi_change else ""
                print(f"{token:<8} ${oi_usd:>15,.0f} {change_str}")

            # Show signals
            if signals:
                print("\n[ALERTS]")
                for sig in signals:
                    print(f"  {sig['token']}: ${sig['oi_usd']:,.0f} {sig['signal']}")

        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Cycle complete:")
        print(f"  Records saved: {saved}")
        print(f"  Tokens tracked: {tokens_tracked}/{len(TOKENS)}")

        return saved

    def run(self):
        """Main loop"""
        print("\n" + "="*70)
        print("BINANCE OPEN INTEREST SCRAPER")
        print(f"Tracking {len(TOKENS)} tokens")
        print(f"Update interval: {UPDATE_INTERVAL//60} minutes")
        print("Purpose: Track total leverage in market (volatility indicator)")
        print("="*70)

        self.init_db()

        while True:
            try:
                self.run_cycle()

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
    scraper = OpenInterestScraper()
    scraper.run()


if __name__ == "__main__":
    main()