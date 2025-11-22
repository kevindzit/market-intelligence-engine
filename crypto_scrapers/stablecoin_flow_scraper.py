"""
Stablecoin Flow Scraper
Tracks USDT, USDC, DAI metrics - research shows 0.87 BTC correlation
Stablecoin velocity and exchange balances are leading indicators for rallies
Free tier: CoinGecko API (10,000 calls/month)
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
load_dotenv(override=True)

# Database configuration
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '54594')
DB_NAME = os.getenv('DB_NAME', 'postgres')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'postgres')

# Scraper configuration
UPDATE_INTERVAL = 30 * 60  # 30 minutes
STABLECOINS = {
    'tether': 'USDT',
    'usd-coin': 'USDC',
    'dai': 'DAI',
    'true-usd': 'TUSD',
    'binance-usd': 'BUSD'  # Track even though declining
}

# CoinGecko free tier - no API key needed for basic calls
COINGECKO_BASE = "https://api.coingecko.com/api/v3"


class StablecoinFlowScraper:
    """
    Tracks stablecoin metrics that provide edge:
    - Supply changes (money entering/leaving crypto)
    - Market cap velocity (transaction volume / market cap)
    - Exchange reserves ("dry powder" for next move)
    - Price deviations (de-pegging signals stress)
    """

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

            # Create table if not exists
            self.create_tables()

        except Exception as e:
            print(f"[ERROR] Database connection failed: {e}")
            sys.exit(1)

    def create_tables(self):
        """Create stablecoin_metrics table if not exists"""
        try:
            with self.db_conn.cursor() as cursor:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS stablecoin_metrics (
                        id SERIAL PRIMARY KEY,
                        symbol VARCHAR(10) NOT NULL,
                        timestamp TIMESTAMP WITH TIME ZONE NOT NULL,

                        -- Core metrics
                        market_cap NUMERIC(20,2),
                        total_volume_24h NUMERIC(20,2),
                        circulating_supply NUMERIC(20,2),

                        -- Velocity metrics (key for edge)
                        velocity_ratio NUMERIC(10,4),  -- volume/mcap

                        -- Supply changes
                        supply_change_24h NUMERIC(20,2),
                        supply_change_pct_24h NUMERIC(10,4),

                        -- Price stability
                        price_usd NUMERIC(10,6),
                        price_deviation_pct NUMERIC(10,4),  -- deviation from $1

                        -- Additional context
                        btc_price NUMERIC(20,2),  -- For correlation analysis
                        total_stablecoin_mcap NUMERIC(20,2),  -- Total across all stables
                        dominance_pct NUMERIC(10,4),  -- This stable's % of total

                        -- Metadata
                        source VARCHAR(50) DEFAULT 'coingecko',
                        scraped_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

                        CONSTRAINT unique_stablecoin_reading
                            UNIQUE (symbol, timestamp)
                    );
                """)

                # Create indexes for efficient queries
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_stablecoin_symbol
                    ON stablecoin_metrics(symbol);
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_stablecoin_timestamp
                    ON stablecoin_metrics(timestamp DESC);
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_stablecoin_velocity
                    ON stablecoin_metrics(velocity_ratio DESC);
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_stablecoin_supply_change
                    ON stablecoin_metrics(supply_change_pct_24h DESC);
                """)

                self.db_conn.commit()
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Database tables ready")

        except Exception as e:
            print(f"[ERROR] Failed to create tables: {e}")
            self.db_conn.rollback()

    def fetch_stablecoin_data(self):
        """Fetch current stablecoin metrics from CoinGecko"""
        try:
            # Get stablecoin data in one call (more efficient)
            coin_ids = ','.join(STABLECOINS.keys())
            url = f"{COINGECKO_BASE}/coins/markets"
            params = {
                'vs_currency': 'usd',
                'ids': coin_ids,
                'order': 'market_cap_desc',
                'sparkline': 'false',
                'price_change_percentage': '24h'
            }

            response = requests.get(url, params=params, timeout=10)

            if response.status_code == 200:
                return response.json()
            else:
                print(f"[ERROR] API returned {response.status_code}")
                return None

        except Exception as e:
            print(f"[ERROR] Failed to fetch stablecoin data: {e}")
            return None

    def fetch_btc_price(self):
        """Get current BTC price for correlation tracking"""
        try:
            url = f"{COINGECKO_BASE}/simple/price"
            params = {
                'ids': 'bitcoin',
                'vs_currencies': 'usd'
            }
            response = requests.get(url, params=params, timeout=5)

            if response.status_code == 200:
                data = response.json()
                return data.get('bitcoin', {}).get('usd', 0)
            return 0

        except Exception as e:
            print(f"[WARNING] Could not fetch BTC price: {e}")
            return 0

    def calculate_metrics(self, coin_data, btc_price):
        """Calculate velocity and other key metrics"""
        metrics = []
        total_mcap = 0
        timestamp = datetime.now()

        # First pass: calculate total market cap
        for coin in coin_data:
            if coin['market_cap']:
                total_mcap += coin['market_cap']

        # Second pass: calculate individual metrics
        for coin in coin_data:
            coin_id = coin['id']
            symbol = STABLECOINS.get(coin_id, coin['symbol'].upper())

            # Core metrics
            market_cap = coin['market_cap'] or 0
            volume_24h = coin['total_volume'] or 0
            supply = coin['circulating_supply'] or 0
            price = coin['current_price'] or 1.0

            # Calculate velocity (key metric!)
            velocity = volume_24h / market_cap if market_cap > 0 else 0

            # Price deviation from $1 (stress indicator)
            price_deviation = abs(price - 1.0) * 100

            # Supply changes
            supply_change_24h = 0
            supply_change_pct = 0
            historical_supply = self._get_supply_snapshot(symbol, timestamp - timedelta(hours=24))
            if historical_supply and historical_supply > 0:
                supply_change_24h = supply - historical_supply
                supply_change_pct = (supply_change_24h / historical_supply) * 100

            # Dominance in stablecoin market
            dominance = (market_cap / total_mcap * 100) if total_mcap > 0 else 0

            metric = {
                'symbol': symbol,
                'timestamp': timestamp,
                'market_cap': market_cap,
                'total_volume_24h': volume_24h,
                'circulating_supply': supply,
                'velocity_ratio': velocity,
                'supply_change_24h': supply_change_24h,
                'supply_change_pct_24h': supply_change_pct,
                'price_usd': price,
                'price_deviation_pct': price_deviation,
                'btc_price': btc_price,
                'total_stablecoin_mcap': total_mcap,
                'dominance_pct': dominance
            }

            metrics.append(metric)

        return metrics

    def save_metrics(self, metrics):
        """Save metrics to database"""
        if not metrics:
            return 0

        saved_count = 0
        try:
            with self.db_conn.cursor() as cursor:
                for metric in metrics:
                    cursor.execute("""
                        INSERT INTO stablecoin_metrics
                        (symbol, timestamp, market_cap, total_volume_24h,
                         circulating_supply, velocity_ratio, supply_change_24h,
                         supply_change_pct_24h, price_usd, price_deviation_pct,
                         btc_price, total_stablecoin_mcap, dominance_pct)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (symbol, timestamp) DO NOTHING
                    """, (
                        metric['symbol'], metric['timestamp'],
                        metric['market_cap'], metric['total_volume_24h'],
                        metric['circulating_supply'], metric['velocity_ratio'],
                        metric['supply_change_24h'], metric['supply_change_pct_24h'],
                        metric['price_usd'], metric['price_deviation_pct'],
                        metric['btc_price'], metric['total_stablecoin_mcap'],
                        metric['dominance_pct']
                    ))

                    if cursor.rowcount > 0:
                        saved_count += 1

                self.db_conn.commit()

        except Exception as e:
            print(f"[ERROR] Failed to save metrics: {e}")
            self.db_conn.rollback()

        return saved_count

    def _get_supply_snapshot(self, symbol: str, before_time: datetime):
        """Fetch the most recent circulating supply for a symbol before a given time."""
        if not self.db_conn:
            return None
        try:
            with self.db_conn.cursor() as cursor:
                cursor.execute("""
                    SELECT circulating_supply
                    FROM stablecoin_metrics
                    WHERE symbol = %s
                      AND timestamp <= %s
                    ORDER BY timestamp DESC
                    LIMIT 1
                """, (symbol, before_time))
                row = cursor.fetchone()
                if row and row[0] is not None:
                    return float(row[0])
        except Exception as exc:
            print(f"[WARNING] Could not load historical supply for {symbol}: {exc}")
        return None

    def print_summary(self, metrics):
        """Print current stablecoin state"""
        if not metrics:
            return

        total_mcap = metrics[0]['total_stablecoin_mcap']

        print(f"\n{'='*60}")
        print(f"STABLECOIN METRICS - Cycle {self.cycle_count}")
        print(f"Total Market Cap: ${total_mcap/1e9:.2f}B")
        print(f"BTC Price: ${metrics[0]['btc_price']:,.0f}")
        print(f"{'='*60}")

        # Sort by market cap for display
        metrics_sorted = sorted(metrics, key=lambda x: x['market_cap'], reverse=True)

        for metric in metrics_sorted[:5]:  # Top 5
            symbol = metric['symbol']
            mcap = metric['market_cap'] / 1e9
            velocity = metric['velocity_ratio']
            supply_change = metric['supply_change_pct_24h']
            dominance = metric['dominance_pct']
            deviation = metric['price_deviation_pct']

            print(f"\n{symbol}:")
            print(f"  Market Cap: ${mcap:.2f}B ({dominance:.1f}% of stables)")
            print(f"  Velocity: {velocity:.3f} (volume/mcap ratio)")

            if supply_change != 0:
                emoji = "📈" if supply_change > 0 else "📉"
                print(f"  Supply Change 24h: {emoji} {supply_change:+.2f}%")

            if deviation > 0.5:  # More than 0.5% from $1
                print(f"  ⚠️ Price Deviation: {deviation:.3f}% from $1.00")

            # Alert on high velocity (money moving)
            if velocity > 0.5:
                print(f"  🔥 HIGH VELOCITY - Heavy trading activity!")

        print(f"\n{'='*60}")

    def check_critical_signals(self, metrics):
        """Identify critical market signals from stablecoin flows"""
        if not metrics:
            return

        signals = []

        # Check for significant supply changes (money flow)
        for metric in metrics:
            symbol = metric['symbol']
            supply_change = metric['supply_change_pct_24h']
            velocity = metric['velocity_ratio']
            deviation = metric['price_deviation_pct']

            # Major inflow signal
            if supply_change > 2.0:  # 2% daily increase
                signals.append(f"💰 MAJOR INFLOW: {symbol} supply +{supply_change:.1f}% (bullish)")

            # Major outflow signal
            elif supply_change < -2.0:  # 2% daily decrease
                signals.append(f"🚨 MAJOR OUTFLOW: {symbol} supply {supply_change:.1f}% (bearish)")

            # High velocity signal
            if velocity > 1.0:  # Volume exceeds market cap
                signals.append(f"🔥 EXTREME VELOCITY: {symbol} at {velocity:.2f}x (volatility incoming)")

            # De-peg risk
            if deviation > 1.0:  # More than 1% from $1
                signals.append(f"⚠️ DE-PEG RISK: {symbol} at ${metric['price_usd']:.4f}")

        # Print signals if any
        if signals:
            print("\n🎯 CRITICAL SIGNALS DETECTED:")
            for signal in signals:
                print(f"  {signal}")

    def run_forever(self):
        """Main loop - runs every 30 minutes"""
        print(f"\n🚀 Starting Stablecoin Flow Monitor")
        print(f"📊 Tracking: {', '.join(STABLECOINS.values())}")
        print(f"⏰ Update interval: {UPDATE_INTERVAL//60} minutes")

        self.init_db()

        while True:
            try:
                self.cycle_count += 1
                start_time = time.time()

                # Fetch data
                print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Fetching stablecoin data...")
                coin_data = self.fetch_stablecoin_data()

                if coin_data:
                    # Get BTC price for correlation
                    btc_price = self.fetch_btc_price()

                    # Calculate metrics
                    metrics = self.calculate_metrics(coin_data, btc_price)

                    # Save to database
                    saved = self.save_metrics(metrics)
                    print(f"[OK] Saved {saved} stablecoin metrics to database")

                    # Print summary
                    self.print_summary(metrics)

                    # Check for critical signals
                    self.check_critical_signals(metrics)

                else:
                    print(f"[WARNING] No data received from API")

                # Calculate next run time
                elapsed = time.time() - start_time
                sleep_time = max(1, UPDATE_INTERVAL - elapsed)

                print(f"\n⏸ Sleeping for {sleep_time//60:.0f} minutes...")
                print(f"Next update at {(datetime.now() + timedelta(seconds=sleep_time)).strftime('%H:%M:%S')}")

                time.sleep(sleep_time)

            except KeyboardInterrupt:
                print("\n[STOPPED] Stablecoin monitor stopped by user")
                break

            except Exception as e:
                print(f"[ERROR] Unexpected error: {e}")
                time.sleep(60)  # Wait 1 minute before retry

        # Cleanup
        if self.db_conn:
            self.db_conn.close()
            print("[OK] Database connection closed")


if __name__ == "__main__":
    scraper = StablecoinFlowScraper()
    scraper.run_forever()
