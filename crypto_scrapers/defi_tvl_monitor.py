"""
DeFi TVL Monitor - Tracks protocol TVL and capital flows via DeFiLlama API
Provides AI trader with insights on where DeFi capital is parking
Free API, no key required
"""

import os
import sys
import time
import requests
import psycopg2
from psycopg2.extras import execute_values
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import json
from pathlib import Path

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

class DeFiTVLMonitor:
    """
    Monitor DeFi protocol TVL and flows using DeFiLlama's free API

    Key metrics tracked:
    - Total TVL by chain (Ethereum, Arbitrum, Solana, etc.)
    - Top protocols by TVL and daily change
    - Sector breakdown (Lending, DEXes, Derivatives, etc.)
    - Capital flow leaders (biggest gainers/losers)
    """

    def __init__(self):
        """Initialize the DeFi TVL monitor"""
        # Database connection parameters
        self.db_params = {
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': os.getenv('DB_PORT', '54594'),
            'database': os.getenv('DB_NAME', 'pjx'),
            'user': os.getenv('DB_USER', 'postgres'),
            'password': os.getenv('DB_PASSWORD', 'password')
        }

        # DeFiLlama API endpoints (free, no key needed)
        # Updated Nov 2024 - using correct free API endpoint
        self.BASE_URL = "https://api.llama.fi"

        # Key chains to monitor (adjust based on your focus)
        self.CHAINS_TO_TRACK = [
            'Ethereum', 'Arbitrum', 'Optimism', 'Solana',
            'Base', 'Polygon', 'BSC', 'Avalanche'
        ]

        # Top protocols to track individually
        self.TOP_PROTOCOLS_LIMIT = 20

        # Categories to track
        self.CATEGORIES = [
            'Lending', 'Dexes', 'Derivatives', 'Yield',
            'Liquid Staking', 'Bridge', 'CDP', 'Yield Aggregator'
        ]

        print(f"[{datetime.now().strftime('%H:%M:%S')}] DeFi TVL Monitor initialized")
        print(f"  Tracking chains: {', '.join(self.CHAINS_TO_TRACK)}")
        print(f"  API: DeFiLlama (free tier)")

    def get_db_connection(self):
        """Create a database connection"""
        return psycopg2.connect(**self.db_params)

    def fetch_tvl_overview(self) -> Optional[Dict]:
        """Fetch overall DeFi TVL across all chains"""
        try:
            # First get list of all chains with current TVL
            url = f"{self.BASE_URL}/chains"
            response = requests.get(url, timeout=30)

            if response.status_code == 200:
                all_chains = response.json()

                # Filter for our tracked chains and extract TVL
                chain_tvls = {}
                for chain_data in all_chains:
                    chain_name = chain_data.get('name', '')
                    if chain_name in self.CHAINS_TO_TRACK:
                        chain_tvls[chain_name] = {
                            'tvl': chain_data.get('tvl', 0),
                            'date': datetime.now()  # Current snapshot
                        }

                # For any missing chains, try the historical endpoint
                for chain in self.CHAINS_TO_TRACK:
                    if chain not in chain_tvls:
                        try:
                            chain_url = f"{self.BASE_URL}/v2/historicalChainTvl/{chain}"
                            chain_response = requests.get(chain_url, timeout=30)
                            if chain_response.status_code == 200:
                                chain_data = chain_response.json()
                                if chain_data:
                                    latest = chain_data[-1]  # Most recent entry
                                    chain_tvls[chain] = {
                                        'tvl': latest.get('tvl', 0),
                                        'date': datetime.fromtimestamp(latest.get('date', 0))
                                    }
                            time.sleep(0.5)  # Be respectful with rate limits
                        except:
                            pass  # Skip if individual chain fails

                return chain_tvls
            else:
                print(f"[WARNING] Failed to fetch TVL overview: {response.status_code}")
                return None

        except Exception as e:
            print(f"[ERROR] Failed to fetch TVL overview: {e}")
            return None

    def fetch_top_protocols(self) -> Optional[List[Dict]]:
        """Fetch top DeFi protocols by TVL with 24h changes"""
        try:
            url = f"{self.BASE_URL}/protocols"
            response = requests.get(url, timeout=30)

            if response.status_code == 200:
                protocols = response.json()

                # Sort by TVL and get top protocols
                sorted_protocols = sorted(
                    protocols,
                    key=lambda x: x.get('tvl', 0) or 0,
                    reverse=True
                )[:self.TOP_PROTOCOLS_LIMIT * 2]  # Get extra to filter

                # Extract key metrics
                top_protocols = []
                for protocol in sorted_protocols:
                    # Skip if no TVL
                    if not protocol.get('tvl'):
                        continue

                    # Calculate 24h change
                    change_1d = protocol.get('change_1d', 0)
                    change_7d = protocol.get('change_7d', 0)

                    # Get chain breakdown if available
                    chains = protocol.get('chains', [])
                    main_chain = chains[0] if chains else 'Multi-Chain'

                    mcap = protocol.get('mcap') or 0
                    tvl = protocol.get('tvl') or 0

                    top_protocols.append({
                        'name': protocol.get('name'),
                        'symbol': protocol.get('symbol', ''),
                        'tvl': tvl,
                        'change_1d_pct': change_1d,
                        'change_7d_pct': change_7d,
                        'category': protocol.get('category', 'Unknown'),
                        'chains': chains,
                        'main_chain': main_chain,
                        'mcap': mcap,
                        'tvl_to_mcap': tvl / mcap if mcap > 0 else 0
                    })

                    if len(top_protocols) >= self.TOP_PROTOCOLS_LIMIT:
                        break

                return top_protocols
            else:
                print(f"[WARNING] Failed to fetch protocols: {response.status_code}")
                return None

        except Exception as e:
            print(f"[ERROR] Failed to fetch protocols: {e}")
            return None

    def calculate_flow_signals(self, protocols: List[Dict]) -> Dict:
        """Calculate capital flow signals from protocol data"""
        signals = {
            'biggest_gainers': [],
            'biggest_losers': [],
            'category_flows': {},
            'chain_dominance': {},
            'risk_indicator': 'NEUTRAL'
        }

        if not protocols:
            return signals

        # Find biggest gainers/losers by absolute TVL change
        for protocol in protocols:
            tvl = protocol.get('tvl') or 0
            change_1d = protocol.get('change_1d_pct') or 0

            if tvl and tvl > 100_000_000:  # Only consider protocols > $100M TVL
                tvl_change = tvl * (change_1d / 100)

                if change_1d > 5:  # >5% gain
                    signals['biggest_gainers'].append({
                        'name': protocol['name'],
                        'change_pct': change_1d,
                        'tvl_change_usd': tvl_change,
                        'category': protocol.get('category')
                    })
                elif change_1d < -5:  # >5% loss
                    signals['biggest_losers'].append({
                        'name': protocol['name'],
                        'change_pct': change_1d,
                        'tvl_change_usd': tvl_change,
                        'category': protocol.get('category')
                    })

        # Sort by absolute TVL change
        signals['biggest_gainers'] = sorted(
            signals['biggest_gainers'],
            key=lambda x: abs(x['tvl_change_usd']),
            reverse=True
        )[:5]

        signals['biggest_losers'] = sorted(
            signals['biggest_losers'],
            key=lambda x: abs(x['tvl_change_usd']),
            reverse=True
        )[:5]

        # Category analysis
        category_stats = {}
        for protocol in protocols:
            category = protocol.get('category', 'Unknown')
            if category not in category_stats:
                category_stats[category] = {
                    'total_tvl': 0,
                    'protocols': 0,
                    'avg_change_1d': 0
                }

            category_stats[category]['total_tvl'] += protocol.get('tvl', 0)
            category_stats[category]['protocols'] += 1
            category_stats[category]['avg_change_1d'] += protocol.get('change_1d_pct', 0)

        # Calculate averages
        for category, stats in category_stats.items():
            if stats['protocols'] > 0:
                stats['avg_change_1d'] /= stats['protocols']
                signals['category_flows'][category] = {
                    'tvl': stats['total_tvl'],
                    'avg_change_1d': round(stats['avg_change_1d'], 2),
                    'protocol_count': stats['protocols']
                }

        # Risk indicator based on outflows
        total_outflows = sum(abs(p['tvl_change_usd']) for p in signals['biggest_losers'])
        total_inflows = sum(abs(p['tvl_change_usd']) for p in signals['biggest_gainers'])

        if total_outflows > total_inflows * 2:
            signals['risk_indicator'] = 'HIGH_OUTFLOWS'
        elif total_outflows > total_inflows * 1.5:
            signals['risk_indicator'] = 'MODERATE_OUTFLOWS'
        elif total_inflows > total_outflows * 2:
            signals['risk_indicator'] = 'STRONG_INFLOWS'

        return signals

    def save_to_database(self, chain_tvls: Dict, protocols: List[Dict], signals: Dict):
        """Save TVL data to database"""
        try:
            with self.get_db_connection() as conn:
                with conn.cursor() as cur:
                    timestamp = datetime.now()

                    # Save chain TVL data
                    if chain_tvls:
                        chain_records = []
                        for chain, data in chain_tvls.items():
                            chain_records.append((
                                chain,
                                data['tvl'],
                                timestamp
                            ))

                        if chain_records:
                            execute_values(
                                cur,
                                """
                                INSERT INTO defi_tvl_chains
                                (chain_name, tvl_usd, scraped_at)
                                VALUES %s
                                """,
                                chain_records
                            )

                    # Save protocol data
                    if protocols:
                        protocol_records = []
                        for protocol in protocols[:self.TOP_PROTOCOLS_LIMIT]:
                            protocol_records.append((
                                protocol['name'],
                                protocol.get('symbol', ''),
                                protocol['tvl'],
                                protocol['change_1d_pct'],
                                protocol['change_7d_pct'],
                                protocol['category'],
                                protocol['main_chain'],
                                json.dumps(protocol.get('chains', [])),
                                protocol.get('mcap', 0),
                                protocol.get('tvl_to_mcap', 0),
                                timestamp
                            ))

                        if protocol_records:
                            execute_values(
                                cur,
                                """
                                INSERT INTO defi_protocols
                                (protocol_name, symbol, tvl_usd, change_1d_pct, change_7d_pct,
                                 category, main_chain, all_chains, market_cap, tvl_to_mcap_ratio,
                                 scraped_at)
                                VALUES %s
                                """,
                                protocol_records
                            )

                    # Save flow signals
                    if signals:
                        cur.execute(
                            """
                            INSERT INTO defi_flow_signals
                            (biggest_gainers, biggest_losers, category_flows,
                             risk_indicator, scraped_at)
                            VALUES (%s, %s, %s, %s, %s)
                            """,
                            (
                                json.dumps(signals['biggest_gainers']),
                                json.dumps(signals['biggest_losers']),
                                json.dumps(signals['category_flows']),
                                signals['risk_indicator'],
                                timestamp
                            )
                        )

                    conn.commit()
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Saved TVL data to database")

        except Exception as e:
            print(f"[ERROR] Failed to save to database: {e}")

    def print_summary(self, chain_tvls: Dict, protocols: List[Dict], signals: Dict):
        """Print a summary of the TVL data"""
        print("\n" + "="*60)
        print("DEFI TVL SUMMARY")
        print("="*60)

        # Chain TVL
        if chain_tvls:
            print("\n[CHAIN TVL]:")
            total_tvl = sum(data['tvl'] for data in chain_tvls.values())
            for chain, data in sorted(chain_tvls.items(), key=lambda x: x[1]['tvl'], reverse=True):
                percentage = (data['tvl'] / total_tvl * 100) if total_tvl > 0 else 0
                print(f"  {chain:15} ${data['tvl']/1e9:6.2f}B ({percentage:4.1f}%)")
            print(f"  {'TOTAL':15} ${total_tvl/1e9:6.2f}B")

        # Top protocols
        if protocols and len(protocols) > 0:
            print("\n[TOP PROTOCOLS BY TVL]:")
            for i, protocol in enumerate(protocols[:10], 1):
                change_indicator = "[+]" if protocol['change_1d_pct'] > 0 else "[-]"
                print(f"  {i:2}. {protocol['name']:20} ${protocol['tvl']/1e9:6.2f}B "
                      f"{change_indicator} {protocol['change_1d_pct']:+6.1f}% "
                      f"({protocol['category']})")

        # Flow signals
        if signals:
            print(f"\n[RISK INDICATOR]: {signals['risk_indicator']}")

            if signals['biggest_gainers']:
                print("\n[BIGGEST GAINERS (24h)]:")
                for gainer in signals['biggest_gainers'][:3]:
                    print(f"  {gainer['name']:20} +{gainer['change_pct']:.1f}% "
                          f"(+${abs(gainer['tvl_change_usd'])/1e6:.1f}M)")

            if signals['biggest_losers']:
                print("\n[BIGGEST LOSERS (24h)]:")
                for loser in signals['biggest_losers'][:3]:
                    print(f"  {loser['name']:20} {loser['change_pct']:.1f}% "
                          f"(-${abs(loser['tvl_change_usd'])/1e6:.1f}M)")

        print("\n" + "="*60 + "\n")

    def run_once(self):
        """Run one collection cycle"""
        try:
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Starting DeFi TVL collection...")

            # Fetch chain TVL overview
            chain_tvls = self.fetch_tvl_overview()

            # Fetch top protocols
            protocols = self.fetch_top_protocols()

            # Calculate flow signals
            signals = {}
            if protocols:
                signals = self.calculate_flow_signals(protocols)

            # Save to database
            if chain_tvls or protocols:
                self.save_to_database(chain_tvls, protocols, signals)

            # Print summary
            self.print_summary(chain_tvls, protocols, signals)

            return True

        except Exception as e:
            print(f"[ERROR] Collection cycle failed: {e}")
            return False

    def run(self):
        """Main loop - runs every 30 minutes"""
        print(f"[{datetime.now().strftime('%H:%M:%S')}] DeFi TVL Monitor starting...")
        print("  Collection interval: 30 minutes")
        print("  Data source: DeFiLlama API (free)")

        while True:
            try:
                # Run collection
                success = self.run_once()

                if success:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Sleeping for 30 minutes...")
                else:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Collection failed, retrying in 5 minutes...")
                    time.sleep(300)  # 5 minutes on failure
                    continue

                # Sleep for 30 minutes
                time.sleep(1800)

            except KeyboardInterrupt:
                print("\n[INFO] DeFi TVL Monitor stopped by user")
                break
            except Exception as e:
                print(f"[ERROR] Unexpected error: {e}")
                time.sleep(300)  # 5 minutes on error

def main():
    """Entry point"""
    from dotenv import load_dotenv
    load_dotenv()

    monitor = DeFiTVLMonitor()
    monitor.run()

if __name__ == "__main__":
    main()