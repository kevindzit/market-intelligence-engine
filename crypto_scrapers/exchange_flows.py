"""
Exchange Flow Scraper
Tracks large movements to/from major exchanges
Uses free APIs to monitor whale activity
Critical for detecting potential dumps/pumps
"""

import os
import sys
import time
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

# API Keys
ETHERSCAN_API_KEY = os.getenv('ETHERSCAN_API_KEY', '')

# Scraper configuration
UPDATE_INTERVAL = 6 * 60 * 60  # 6 hours (within free tier limits)

# Focus on top 3 tokens for free tier
TOKENS_TO_TRACK = ['BTC', 'ETH', 'SOL']

# Major exchange addresses (simplified list)
EXCHANGE_ADDRESSES = {
    'BTC': {
        'binance': ['1JDknRvZTi5XdhQB3cgvJ9R8aogUvfbwUB', '1NDyJtNTjmwk5xPNhjgAMu4HDHigtobu1s'],
        'coinbase': ['1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa'],
    },
    'ETH': {
        'binance': ['0x28C6c06298d514Db089934071355E5743bf21d60'],
        'coinbase': ['0x71660c4005BA85c37ccec55d0C4493E66Fe775d3'],
    }
}


class ExchangeFlowScraper:
    """Tracks exchange flows using free blockchain APIs"""

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

    def create_table_if_not_exists(self):
        """Create exchange_flows table if it doesn't exist"""
        cursor = self.db_conn.cursor()
        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS exchange_flows (
                    id SERIAL PRIMARY KEY,
                    token VARCHAR(20) NOT NULL,
                    flow_type VARCHAR(20) NOT NULL,
                    amount NUMERIC(20,8) NOT NULL,
                    usd_value NUMERIC(20,2),
                    exchange VARCHAR(50),
                    transaction_hash VARCHAR(100),
                    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
                    source VARCHAR(50) DEFAULT 'blockchain',
                    scraped_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # Create indexes
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_flows_token ON exchange_flows(token);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_flows_timestamp ON exchange_flows(timestamp DESC);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_flows_type ON exchange_flows(flow_type);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_flows_value ON exchange_flows(usd_value DESC);")

            self.db_conn.commit()
            print("[INFO] Exchange flows table ready")

        except Exception as e:
            print(f"[WARNING] Table might already exist: {e}")
            self.db_conn.rollback()

        finally:
            cursor.close()

    def get_btc_flows(self):
        """Get Bitcoin exchange flows using blockchain.info API (free)"""
        flows = []

        try:
            # Check major Binance address (simplified)
            address = '1JDknRvZTi5XdhQB3cgvJ9R8aogUvfbwUB'
            url = f'https://blockchain.info/rawaddr/{address}?limit=10'

            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()

                # Get current BTC price
                price_response = requests.get('https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT')
                btc_price = float(price_response.json()['price']) if price_response.status_code == 200 else 0

                # Parse recent transactions
                for tx in data.get('txs', [])[:5]:  # Last 5 transactions
                    timestamp = datetime.fromtimestamp(tx.get('time', 0))

                    # Check if inflow or outflow
                    total_in = sum(inp.get('prev_out', {}).get('value', 0) for inp in tx.get('inputs', []) if inp.get('prev_out', {}).get('addr') == address) / 1e8
                    total_out = sum(out.get('value', 0) for out in tx.get('out', []) if out.get('addr') == address) / 1e8

                    if total_in > 0:
                        flows.append({
                            'token': 'BTC',
                            'flow_type': 'OUTFLOW',
                            'amount': total_in,
                            'usd_value': total_in * btc_price,
                            'exchange': 'binance',
                            'transaction_hash': tx.get('hash'),
                            'timestamp': timestamp,
                            'source': 'blockchain.info'
                        })

                    if total_out > 0:
                        flows.append({
                            'token': 'BTC',
                            'flow_type': 'INFLOW',
                            'amount': total_out,
                            'usd_value': total_out * btc_price,
                            'exchange': 'binance',
                            'transaction_hash': tx.get('hash'),
                            'timestamp': timestamp,
                            'source': 'blockchain.info'
                        })

        except Exception as e:
            print(f"[WARNING] Failed to get BTC flows: {e}")

        return flows

    def get_eth_flows(self):
        """Get Ethereum exchange flows using Etherscan API (free tier)"""
        flows = []

        if not ETHERSCAN_API_KEY:
            print("[WARNING] ETH flow tracking requires Etherscan API key in .env file")
            return flows

        try:
            # Major Binance ETH hot wallet
            address = '0x28C6c06298d514Db089934071355E5743bf21d60'

            # Get last 10 transactions (Etherscan V2 API)
            url = 'https://api.etherscan.io/v2/api'
            params = {
                'chainid': 1,  # Ethereum mainnet
                'module': 'account',
                'action': 'txlist',
                'address': address,
                'startblock': 0,
                'endblock': 99999999,
                'page': 1,
                'offset': 10,
                'sort': 'desc',
                'apikey': ETHERSCAN_API_KEY
            }

            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()

                if data.get('status') == '1' and data.get('result'):
                    # Get current ETH price
                    price_response = requests.get('https://api.binance.com/api/v3/ticker/price?symbol=ETHUSDT')
                    eth_price = float(price_response.json()['price']) if price_response.status_code == 200 else 0

                    for tx in data['result']:
                        # Convert Wei to ETH
                        value_eth = int(tx.get('value', 0)) / 1e18

                        # Only track significant transactions (>1 ETH)
                        if value_eth < 1:
                            continue

                        timestamp = datetime.fromtimestamp(int(tx.get('timeStamp', 0)))

                        # Determine if inflow or outflow
                        if tx.get('to', '').lower() == address.lower():
                            flow_type = 'INFLOW'
                        else:
                            flow_type = 'OUTFLOW'

                        flows.append({
                            'token': 'ETH',
                            'flow_type': flow_type,
                            'amount': value_eth,
                            'usd_value': value_eth * eth_price,
                            'exchange': 'binance',
                            'transaction_hash': tx.get('hash'),
                            'timestamp': timestamp,
                            'source': 'etherscan'
                        })

                else:
                    print(f"[WARNING] Etherscan API error: {data.get('message', 'Unknown error')}")

        except Exception as e:
            print(f"[WARNING] Failed to get ETH flows: {e}")

        return flows

    def save_to_db(self, flows):
        """Save flow data to database"""
        if not flows:
            return 0

        cursor = self.db_conn.cursor()
        saved = 0

        try:
            for flow in flows:
                try:
                    # Check if we already have this transaction
                    cursor.execute("""
                        SELECT id FROM exchange_flows
                        WHERE transaction_hash = %s AND token = %s
                    """, (flow.get('transaction_hash'), flow.get('token')))

                    if cursor.fetchone():
                        continue  # Skip duplicate

                    cursor.execute("""
                        INSERT INTO exchange_flows
                        (token, flow_type, amount, usd_value, exchange,
                         transaction_hash, timestamp, source)
                        VALUES (%(token)s, %(flow_type)s, %(amount)s, %(usd_value)s,
                                %(exchange)s, %(transaction_hash)s, %(timestamp)s, %(source)s)
                    """, flow)

                    saved += 1

                except Exception as e:
                    print(f"[WARNING] Failed to save flow: {e}")
                    self.db_conn.rollback()

            self.db_conn.commit()

        except Exception as e:
            print(f"[ERROR] Database save failed: {e}")
            self.db_conn.rollback()

        finally:
            cursor.close()

        return saved

    def analyze_flows(self):
        """Analyze recent flows for signals"""
        cursor = self.db_conn.cursor()

        try:
            # Get net flows for last 24 hours
            cursor.execute("""
                SELECT
                    token,
                    SUM(CASE WHEN flow_type = 'INFLOW' THEN usd_value ELSE 0 END) as total_inflow,
                    SUM(CASE WHEN flow_type = 'OUTFLOW' THEN usd_value ELSE 0 END) as total_outflow,
                    COUNT(*) as transaction_count
                FROM exchange_flows
                WHERE timestamp > NOW() - INTERVAL '24 hours'
                GROUP BY token
            """)

            results = cursor.fetchall()

            if results:
                print("\n24-Hour Exchange Flow Summary:")
                print("-" * 50)

                for row in results:
                    token = row[0]
                    inflow = float(row[1]) if row[1] else 0
                    outflow = float(row[2]) if row[2] else 0
                    net_flow = inflow - outflow

                    signal = ""
                    if net_flow > 1000000:  # Over $1M net inflow
                        signal = "[SELLING PRESSURE - Potential dump]"
                    elif net_flow < -1000000:  # Over $1M net outflow
                        signal = "[ACCUMULATION - Potential pump]"

                    print(f"{token}: Net ${net_flow:>12,.0f} "
                          f"(In: ${inflow:>12,.0f} Out: ${outflow:>12,.0f}) {signal}")

        except Exception as e:
            print(f"[ERROR] Failed to analyze flows: {e}")

        finally:
            cursor.close()

    def run_cycle(self):
        """Run one collection cycle"""
        self.cycle_count += 1
        print(f"\n{'='*70}")
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Exchange Flow Cycle #{self.cycle_count}")
        print('='*70)

        all_flows = []

        # Get BTC flows
        btc_flows = self.get_btc_flows()
        all_flows.extend(btc_flows)

        # Get ETH flows (requires API key)
        eth_flows = self.get_eth_flows()
        all_flows.extend(eth_flows)

        # Save to database
        saved = self.save_to_db(all_flows)

        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Cycle complete:")
        print(f"  New flows saved: {saved}")

        # Analyze flows
        if saved > 0:
            self.analyze_flows()

        return saved

    def run(self):
        """Main loop"""
        print("\n" + "="*70)
        print("EXCHANGE FLOW TRACKER")
        print(f"Tracking: {', '.join(TOKENS_TO_TRACK)}")
        print(f"Update interval: {UPDATE_INTERVAL//3600} hours")
        print("Purpose: Detect whale movements to/from exchanges")
        print("="*70)

        self.init_db()
        self.create_table_if_not_exists()

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
    scraper = ExchangeFlowScraper()
    scraper.run()


if __name__ == "__main__":
    main()