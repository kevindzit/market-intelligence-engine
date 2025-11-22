"""
DEX Liquidity Monitor
Tracks liquidity and volume on major DEXs (Uniswap, PancakeSwap, etc.)
Uses free APIs - no expensive services required
Critical for complete market view as DEXs now have 40% market share
"""

import os
import sys
import time
import json
import requests
from datetime import datetime, timedelta
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
UPDATE_INTERVAL = 30 * 60  # 30 minutes
MAX_RETRIES = 3

# Top DEX platforms to monitor (using DexScreener free API)
TOP_DEXS = ['uniswap', 'pancakeswap', 'sushiswap']
TOP_DEX_FILTER = tuple(dex.lower() for dex in TOP_DEXS)

# Top tokens to track DEX activity
TOKENS_TO_TRACK = {
    'BTC': ['WBTC', 'bitcoin'],
    'ETH': ['ETH', 'ethereum'],
    'USDT': ['USDT', 'tether'],
    'USDC': ['USDC', 'usd-coin'],
    'SOL': ['SOL', 'solana'],
    'BNB': ['BNB', 'binancecoin'],
    'ARB': ['ARB', 'arbitrum'],
    'PEPE': ['PEPE', 'pepe'],
    'SHIB': ['SHIB', 'shiba-inu']
}


class DEXLiquidityMonitor:
    """
    Monitor DEX liquidity and volume for trading signals
    - Liquidity depth indicates price stability
    - Volume spikes often precede CEX movements
    - LP movements signal smart money activity
    """

    def __init__(self):
        self.db_conn = None
        self.cycle_count = 0
        self.dex_filter = TOP_DEX_FILTER

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
        """Create dex_liquidity table if not exists"""
        try:
            with self.db_conn.cursor() as cursor:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS dex_liquidity (
                        id SERIAL PRIMARY KEY,
                        token VARCHAR(20) NOT NULL,
                        dex_name VARCHAR(50) NOT NULL,
                        timestamp TIMESTAMP WITH TIME ZONE NOT NULL,

                        -- Core liquidity metrics
                        liquidity_usd NUMERIC(20,2),
                        volume_24h NUMERIC(20,2),
                        volume_change_24h NUMERIC(10,4),  -- Percentage

                        -- Price data
                        price_usd NUMERIC(20,10),
                        price_change_24h NUMERIC(10,4),  -- Percentage

                        -- DEX-specific metrics
                        pool_count INTEGER,
                        fdv NUMERIC(20,2),  -- Fully diluted valuation
                        market_cap NUMERIC(20,2),

                        -- Trading signals
                        volume_to_liquidity_ratio NUMERIC(10,4),  -- High = hot
                        liquidity_change_24h NUMERIC(10,4),  -- Percentage

                        -- Metadata
                        source VARCHAR(50) DEFAULT 'dexscreener',
                        scraped_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

                        CONSTRAINT unique_dex_reading
                            UNIQUE (token, dex_name, timestamp)
                    );
                """)

                # Create indexes
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_dex_token
                    ON dex_liquidity(token);
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_dex_timestamp
                    ON dex_liquidity(timestamp DESC);
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_dex_volume
                    ON dex_liquidity(volume_24h DESC);
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_dex_liquidity
                    ON dex_liquidity(liquidity_usd DESC);
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_dex_ratio
                    ON dex_liquidity(volume_to_liquidity_ratio DESC);
                """)

                self.db_conn.commit()
                print(f"[{datetime.now().strftime('%H:%M:%S')}] DEX liquidity table ready")

        except Exception as e:
            print(f"[ERROR] Failed to create tables: {e}")
            self.db_conn.rollback()

    def _is_supported_dex(self, dex_name: str) -> bool:
        """Check if the dex matches our monitored platforms."""
        if not self.dex_filter:
            return True
        name = (dex_name or "").lower()
        return any(name.startswith(prefix) for prefix in self.dex_filter)

    def fetch_dexscreener_data(self, token_symbol):
        """
        Fetch DEX data from DexScreener (free API, no key required)
        Alternative to expensive Dune Analytics
        """
        try:
            # DexScreener search endpoint (free)
            url = f"https://api.dexscreener.com/latest/dex/search/?q={token_symbol}"

            response = requests.get(url, timeout=10)

            if response.status_code == 200:
                data = response.json()
                return data.get('pairs', [])
            else:
                print(f"[WARNING] DexScreener API returned {response.status_code}")
                return []

        except Exception as e:
            print(f"[WARNING] Failed to fetch DexScreener data for {token_symbol}: {e}")
            return []

    def fetch_coingecko_dex_data(self, token_id):
        """
        Get DEX volume from CoinGecko (free tier)
        Provides aggregated DEX metrics
        """
        try:
            url = f"https://api.coingecko.com/api/v3/coins/{token_id}"
            params = {
                'localization': 'false',
                'tickers': 'false',
                'market_data': 'true',
                'community_data': 'false',
                'developer_data': 'false'
            }

            response = requests.get(url, params=params, timeout=10)

            if response.status_code == 200:
                data = response.json()
                market_data = data.get('market_data', {})

                return {
                    'total_volume': market_data.get('total_volume', {}).get('usd', 0),
                    'market_cap': market_data.get('market_cap', {}).get('usd', 0),
                    'price': market_data.get('current_price', {}).get('usd', 0),
                    'price_change_24h': market_data.get('price_change_percentage_24h', 0)
                }
            return None

        except Exception as e:
            print(f"[WARNING] CoinGecko API error: {e}")
            return None

    def process_dex_data(self, token_symbol, dex_pairs):
        """Process raw DEX data into metrics"""
        metrics = []
        timestamp = datetime.now()

        # Aggregate by DEX platform
        dex_aggregates = {}

        for pair in dex_pairs[:20]:  # Top 20 pairs
            # Extract DEX name
            dex_name = pair.get('dexId', 'unknown').lower()
            if not self._is_supported_dex(dex_name):
                continue

            # Skip low liquidity pairs
            liquidity = float(pair.get('liquidity', {}).get('usd', 0))
            if liquidity < 10000:  # $10k minimum
                continue

            # Aggregate by DEX
            if dex_name not in dex_aggregates:
                dex_aggregates[dex_name] = {
                    'liquidity_usd': 0,
                    'volume_24h': 0,
                    'pool_count': 0,
                    'prices': [],
                    'price_changes': [],
                    'fdv': float(pair.get('fdv', 0))
                }

            dex_aggregates[dex_name]['liquidity_usd'] += liquidity
            dex_aggregates[dex_name]['volume_24h'] += float(pair.get('volume', {}).get('h24', 0))
            dex_aggregates[dex_name]['pool_count'] += 1

            # Collect prices for weighted average
            price = float(pair.get('priceUsd', 0))
            if price > 0:
                dex_aggregates[dex_name]['prices'].append(price)

            price_change = float(pair.get('priceChange', {}).get('h24', 0))
            dex_aggregates[dex_name]['price_changes'].append(price_change)

        # Create metrics for each DEX
        for dex_name, agg_data in dex_aggregates.items():
            if agg_data['pool_count'] == 0:
                continue

            # Calculate weighted average price
            avg_price = sum(agg_data['prices']) / len(agg_data['prices']) if agg_data['prices'] else 0
            avg_price_change = sum(agg_data['price_changes']) / len(agg_data['price_changes']) if agg_data['price_changes'] else 0

            # Calculate volume to liquidity ratio (key metric!)
            vol_liq_ratio = (agg_data['volume_24h'] / agg_data['liquidity_usd']) if agg_data['liquidity_usd'] > 0 else 0

            metric = {
                'token': token_symbol,
                'dex_name': dex_name,
                'timestamp': timestamp,
                'liquidity_usd': agg_data['liquidity_usd'],
                'volume_24h': agg_data['volume_24h'],
                'volume_change_24h': 0,  # Would need historical data
                'price_usd': avg_price,
                'price_change_24h': avg_price_change,
                'pool_count': agg_data['pool_count'],
                'fdv': agg_data['fdv'],
                'market_cap': 0,  # Would need token supply
                'volume_to_liquidity_ratio': vol_liq_ratio,
                'liquidity_change_24h': 0  # Would need historical data
            }

            metrics.append(metric)

        return metrics

    def save_metrics(self, metrics):
        """Save DEX metrics to database"""
        if not metrics:
            return 0

        saved_count = 0
        try:
            with self.db_conn.cursor() as cursor:
                for metric in metrics:
                    liq_change_pct, vol_change_pct = self._calculate_historical_changes(cursor, metric)
                    metric['liquidity_change_24h'] = liq_change_pct
                    metric['volume_change_24h'] = vol_change_pct

                    cursor.execute("""
                        INSERT INTO dex_liquidity
                        (token, dex_name, timestamp, liquidity_usd, volume_24h,
                         volume_change_24h, price_usd, price_change_24h,
                         pool_count, fdv, market_cap, volume_to_liquidity_ratio,
                         liquidity_change_24h)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (token, dex_name, timestamp) DO NOTHING
                    """, (
                        metric['token'], metric['dex_name'], metric['timestamp'],
                        metric['liquidity_usd'], metric['volume_24h'],
                        metric['volume_change_24h'], metric['price_usd'],
                        metric['price_change_24h'], metric['pool_count'],
                        metric['fdv'], metric['market_cap'],
                        metric['volume_to_liquidity_ratio'],
                        metric['liquidity_change_24h']
                    ))

                    if cursor.rowcount > 0:
                        saved_count += 1

                self.db_conn.commit()

        except Exception as e:
            print(f"[ERROR] Failed to save DEX metrics: {e}")
            self.db_conn.rollback()

        return saved_count

    def _calculate_historical_changes(self, cursor, metric):
        """Compute 24h percentage changes for liquidity and volume."""
        try:
            comparison_time = metric['timestamp'] - timedelta(hours=24)
            cursor.execute("""
                SELECT liquidity_usd, volume_24h
                FROM dex_liquidity
                WHERE token = %s
                  AND dex_name = %s
                  AND timestamp <= %s
                ORDER BY timestamp DESC
                LIMIT 1
            """, (metric['token'], metric['dex_name'], comparison_time))
            row = cursor.fetchone()

            if not row:
                cursor.execute("""
                    SELECT liquidity_usd, volume_24h
                    FROM dex_liquidity
                    WHERE token = %s
                      AND dex_name = %s
                      AND timestamp < %s
                    ORDER BY timestamp DESC
                    LIMIT 1
                """, (metric['token'], metric['dex_name'], metric['timestamp']))
                row = cursor.fetchone()

            if not row:
                return 0.0, 0.0

            prev_liquidity = float(row[0]) if row[0] else 0.0
            prev_volume = float(row[1]) if row[1] else 0.0

            liq_change = ((metric['liquidity_usd'] - prev_liquidity) / prev_liquidity * 100) if prev_liquidity else 0.0
            vol_change = ((metric['volume_24h'] - prev_volume) / prev_volume * 100) if prev_volume else 0.0
            return liq_change, vol_change
        except Exception as exc:
            print(f"[WARNING] Failed to compute historical changes for {metric['token']} on {metric['dex_name']}: {exc}")
            return 0.0, 0.0

    def analyze_dex_signals(self):
        """Analyze DEX data for trading signals"""
        try:
            with self.db_conn.cursor() as cursor:
                # Get aggregated DEX metrics for last hour
                cursor.execute("""
                    SELECT
                        token,
                        SUM(liquidity_usd) as total_liquidity,
                        SUM(volume_24h) as total_volume,
                        AVG(volume_to_liquidity_ratio) as avg_ratio,
                        COUNT(DISTINCT dex_name) as dex_count,
                        MAX(price_usd) as max_price,
                        MIN(price_usd) as min_price
                    FROM dex_liquidity
                    WHERE timestamp > NOW() - INTERVAL '1 hour'
                    GROUP BY token
                    HAVING SUM(volume_24h) > 100000
                    ORDER BY total_volume DESC
                """)

                results = cursor.fetchall()

                if results:
                    print("\n🔄 DEX Market Overview:")
                    print("=" * 60)

                    for row in results:
                        token = row[0]
                        liquidity = float(row[1]) if row[1] else 0
                        volume = float(row[2]) if row[2] else 0
                        ratio = float(row[3]) if row[3] else 0
                        dex_count = row[4]
                        max_price = float(row[5]) if row[5] else 0
                        min_price = float(row[6]) if row[6] else 0

                        print(f"\n{token}:")
                        print(f"  Liquidity: ${liquidity:,.0f} across {dex_count} DEXs")
                        print(f"  24h Volume: ${volume:,.0f}")
                        print(f"  V/L Ratio: {ratio:.3f}")

                        # Price spread indicates arbitrage opportunity
                        if max_price > 0 and min_price > 0:
                            spread = ((max_price - min_price) / min_price) * 100
                            if spread > 1.0:
                                print(f"  ⚠️ ARBITRAGE: {spread:.2f}% price spread")

                        # High V/L ratio indicates hot token
                        if ratio > 0.5:
                            print(f"  🔥 HIGH ACTIVITY: Volume exceeds 50% of liquidity")

                        # Low liquidity warning
                        if liquidity < 1000000 and volume > 500000:
                            print(f"  ⚠️ THIN LIQUIDITY: High slippage risk")

        except Exception as e:
            print(f"[ERROR] Failed to analyze DEX signals: {e}")

    def run_cycle(self):
        """Run one collection cycle"""
        self.cycle_count += 1
        print(f"\n{'='*70}")
        print(f"[{datetime.now().strftime('%H:%M:%S')}] DEX Monitor Cycle #{self.cycle_count}")
        print('='*70)

        all_metrics = []

        # Fetch data for each token
        for token_symbol, identifiers in TOKENS_TO_TRACK.items():
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Fetching {token_symbol} DEX data...")

            dex_pairs = []
            seen_pairs = set()

            for identifier in identifiers:
                pairs = self.fetch_dexscreener_data(identifier)
                if not pairs:
                    continue

                for pair in pairs:
                    pair_id = pair.get('pairAddress')
                    if pair_id and pair_id in seen_pairs:
                        continue
                    dex_pairs.append(pair)
                    if pair_id:
                        seen_pairs.add(pair_id)

            if dex_pairs:
                # Process into metrics
                metrics = self.process_dex_data(token_symbol, dex_pairs)
                all_metrics.extend(metrics)

                # Print summary
                total_liq = sum(m['liquidity_usd'] for m in metrics)
                total_vol = sum(m['volume_24h'] for m in metrics)

                if total_liq > 0:
                    print(f"  Found ${total_liq:,.0f} liquidity, ${total_vol:,.0f} volume")

            time.sleep(2)  # Rate limiting

        # Save to database
        saved = self.save_metrics(all_metrics)

        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Cycle complete:")
        print(f"  DEX metrics saved: {saved}")

        # Analyze signals
        if saved > 0:
            self.analyze_dex_signals()

        return saved

    def run_forever(self):
        """Main loop - runs every 30 minutes"""
        print(f"\n🚀 Starting DEX Liquidity Monitor")
        print(f"📊 Tracking: {', '.join(TOKENS_TO_TRACK.keys())}")
        print(f"🏦 DEXs: Multiple via DexScreener API")
        print(f"⏰ Update interval: {UPDATE_INTERVAL//60} minutes")

        self.init_db()

        while True:
            try:
                start_time = time.time()

                # Run collection cycle
                self.run_cycle()

                # Calculate next run time
                elapsed = time.time() - start_time
                sleep_time = max(1, UPDATE_INTERVAL - elapsed)

                print(f"\n⏸ Sleeping for {sleep_time//60:.0f} minutes...")
                print(f"Next update at {(datetime.now() + timedelta(seconds=sleep_time)).strftime('%H:%M:%S')}")

                time.sleep(sleep_time)

            except KeyboardInterrupt:
                print("\n[STOPPED] DEX monitor stopped by user")
                break

            except Exception as e:
                print(f"[ERROR] Unexpected error: {e}")
                time.sleep(60)  # Wait 1 minute before retry

        # Cleanup
        if self.db_conn:
            self.db_conn.close()
            print("[OK] Database connection closed")


if __name__ == "__main__":
    monitor = DEXLiquidityMonitor()
    monitor.run_forever()
