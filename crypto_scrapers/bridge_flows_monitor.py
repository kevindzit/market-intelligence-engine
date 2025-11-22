"""
Bridge Flows Monitor - Track L1/L2 Capital Rotation via DeFiLlama
Monitors bridge inflows/outflows to identify capital rotation patterns
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor
import requests
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional, Tuple
import time
from dotenv import load_dotenv
import json

load_dotenv()

class BridgeFlowsMonitor:
    """
    Tracks cross-chain bridge flows using DeFiLlama's free API.
    Identifies capital rotation between L1s and L2s for trading signals.
    """

    # L2s to track (most important for trading)
    L2_CHAINS = [
        'Arbitrum',      # Largest L2 by TVL
        'Base',          # Coinbase L2, fastest growing
        'Optimism',      # OP ecosystem
        'Polygon',       # MATIC ecosystem
        'Blast',         # High yield L2
        'zkSync Era',    # zkRollup
        'Linea'          # ConsenSys L2
    ]

    # DeFiLlama API endpoints (FREE, no auth needed)
    BASE_URL = 'https://bridges.llama.fi'

    def __init__(self):
        """Initialize the bridge flows monitor"""
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Bridge Flows Monitor initialized")
        print(f"  Tracking L2s: {', '.join(self.L2_CHAINS)}")
        print(f"  API: DeFiLlama Bridges (free tier)")

        # Database config
        self.db_config = {
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': os.getenv('DB_PORT', '54594'),
            'database': os.getenv('DB_NAME', 'pjx'),
            'user': os.getenv('DB_USER', 'postgres'),
            'password': os.getenv('DB_PASSWORD')
        }

    def fetch_bridge_volume(self, chain: str, lookback_days: int = 30) -> Optional[List[Dict]]:
        """
        Fetch historical bridge volume for a specific chain
        """
        try:
            # DeFiLlama uses URL-encoded chain names for spaces
            chain_encoded = chain.replace(' ', '%20')
            url = f"{self.BASE_URL}/bridgevolume/{chain_encoded}"

            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()

                # Filter to requested lookback period
                if data and isinstance(data, list):
                    cutoff_timestamp = int((datetime.now() - timedelta(days=lookback_days)).timestamp())
                    filtered_data = [
                        d for d in data
                        if int(d.get('date', 0)) >= cutoff_timestamp
                    ]
                    return filtered_data
                return data
            else:
                print(f"  [WARNING] Failed to fetch {chain}: HTTP {response.status_code}")
                return None

        except Exception as e:
            print(f"  [ERROR] Failed to fetch {chain}: {e}")
            return None

    def calculate_metrics(self, volume_data: List[Dict]) -> Dict:
        """
        Calculate key metrics from volume data
        """
        if not volume_data:
            return {}

        # Sort by date
        sorted_data = sorted(volume_data, key=lambda x: int(x.get('date', 0)))

        # Calculate different timeframe metrics
        now = datetime.now()
        metrics = {
            '24h': {'deposits': 0, 'withdrawals': 0, 'net_flow': 0, 'txs': 0},
            '7d': {'deposits': 0, 'withdrawals': 0, 'net_flow': 0, 'txs': 0},
            '30d': {'deposits': 0, 'withdrawals': 0, 'net_flow': 0, 'txs': 0}
        }

        for entry in sorted_data:
            entry_date = datetime.fromtimestamp(int(entry.get('date', 0)))
            days_ago = (now - entry_date).days

            deposits = float(entry.get('depositUSD', 0))
            withdrawals = float(entry.get('withdrawUSD', 0))
            deposit_txs = int(entry.get('depositTxs', 0))
            withdraw_txs = int(entry.get('withdrawTxs', 0))

            # Add to appropriate timeframes
            if days_ago <= 1:
                metrics['24h']['deposits'] += deposits
                metrics['24h']['withdrawals'] += withdrawals
                metrics['24h']['net_flow'] = metrics['24h']['deposits'] - metrics['24h']['withdrawals']
                metrics['24h']['txs'] += deposit_txs + withdraw_txs

            if days_ago <= 7:
                metrics['7d']['deposits'] += deposits
                metrics['7d']['withdrawals'] += withdrawals
                metrics['7d']['net_flow'] = metrics['7d']['deposits'] - metrics['7d']['withdrawals']
                metrics['7d']['txs'] += deposit_txs + withdraw_txs

            if days_ago <= 30:
                metrics['30d']['deposits'] += deposits
                metrics['30d']['withdrawals'] += withdrawals
                metrics['30d']['net_flow'] = metrics['30d']['deposits'] - metrics['30d']['withdrawals']
                metrics['30d']['txs'] += deposit_txs + withdraw_txs

        # Calculate velocity (7d vs 30d average)
        if metrics['30d']['net_flow'] != 0:
            daily_avg_30d = metrics['30d']['net_flow'] / 30
            daily_avg_7d = metrics['7d']['net_flow'] / 7
            metrics['velocity'] = ((daily_avg_7d - daily_avg_30d) / abs(daily_avg_30d)) * 100 if daily_avg_30d != 0 else 0
        else:
            metrics['velocity'] = 0

        return metrics

    def save_to_database(self, chain: str, volume_data: List[Dict]) -> bool:
        """
        Save bridge flow data to PostgreSQL
        """
        conn = None
        try:
            conn = psycopg2.connect(**self.db_config)
            cur = conn.cursor()

            # Insert daily data
            for entry in volume_data:
                entry_date = date.fromtimestamp(int(entry.get('date', 0)))

                cur.execute("""
                    INSERT INTO bridge_flows
                    (chain, date, deposits_usd, withdrawals_usd, deposit_txs, withdraw_txs)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (chain, date)
                    DO UPDATE SET
                        deposits_usd = EXCLUDED.deposits_usd,
                        withdrawals_usd = EXCLUDED.withdrawals_usd,
                        deposit_txs = EXCLUDED.deposit_txs,
                        withdraw_txs = EXCLUDED.withdraw_txs,
                        scraped_at = CURRENT_TIMESTAMP
                """, (
                    chain,
                    entry_date,
                    float(entry.get('depositUSD', 0)),
                    float(entry.get('withdrawUSD', 0)),
                    int(entry.get('depositTxs', 0)),
                    int(entry.get('withdrawTxs', 0))
                ))

            conn.commit()
            return True

        except Exception as e:
            print(f"  [ERROR] Database save failed for {chain}: {e}")
            if conn:
                conn.rollback()
            return False
        finally:
            if conn:
                cur.close()
                conn.close()

    def generate_signals(self, all_metrics: Dict[str, Dict]) -> List[Dict]:
        """
        Generate trading signals from bridge flow metrics
        """
        signals = []

        # Sort chains by 7d net flow
        sorted_chains = sorted(
            all_metrics.items(),
            key=lambda x: x[1].get('7d', {}).get('net_flow', 0),
            reverse=True
        )

        for chain, metrics in sorted_chains:
            if not metrics:
                continue

            net_flow_7d = metrics.get('7d', {}).get('net_flow', 0)
            net_flow_24h = metrics.get('24h', {}).get('net_flow', 0)
            velocity = metrics.get('velocity', 0)

            # Capital rotation signal (>$50M inflow in 7d)
            if net_flow_7d > 50_000_000:
                signals.append({
                    'signal_type': 'capital_rotation',
                    'chain': chain,
                    'timeframe': '7d',
                    'metric_name': 'net_flow',
                    'metric_value': net_flow_7d,
                    'threshold': 50_000_000,
                    'interpretation': f"Major capital rotation into {chain}. {net_flow_7d/1e6:.1f}M net inflow in 7d.",
                    'alert_level': 'critical'
                })

            # Volume spike signal (>$10M in 24h)
            if abs(net_flow_24h) > 10_000_000:
                direction = 'inflow' if net_flow_24h > 0 else 'outflow'
                signals.append({
                    'signal_type': 'volume_spike',
                    'chain': chain,
                    'timeframe': '24h',
                    'metric_name': 'net_flow',
                    'metric_value': net_flow_24h,
                    'threshold': 10_000_000,
                    'interpretation': f"Large {direction} on {chain}. ${abs(net_flow_24h)/1e6:.1f}M in 24h.",
                    'alert_level': 'warning'
                })

            # Outflow warning (<-$20M in 7d)
            if net_flow_7d < -20_000_000:
                signals.append({
                    'signal_type': 'outflow_warning',
                    'chain': chain,
                    'timeframe': '7d',
                    'metric_name': 'net_flow',
                    'metric_value': net_flow_7d,
                    'threshold': -20_000_000,
                    'interpretation': f"Capital fleeing {chain}. ${abs(net_flow_7d)/1e6:.1f}M net outflow in 7d.",
                    'alert_level': 'warning'
                })

            # Velocity signal (accelerating flows)
            if abs(velocity) > 50:
                trend = 'accelerating' if velocity > 0 else 'decelerating'
                signals.append({
                    'signal_type': 'velocity_change',
                    'chain': chain,
                    'timeframe': '7d_vs_30d',
                    'metric_name': 'velocity',
                    'metric_value': velocity,
                    'threshold': 50,
                    'interpretation': f"Flow velocity {trend} on {chain} ({velocity:.1f}% change).",
                    'alert_level': 'info'
                })

        return signals

    def save_signals(self, signals: List[Dict]) -> bool:
        """
        Save generated signals to database
        """
        if not signals:
            return True

        conn = None
        try:
            conn = psycopg2.connect(**self.db_config)
            cur = conn.cursor()

            # Clear old signals (keep only last 24h)
            cur.execute("""
                DELETE FROM bridge_flow_signals
                WHERE created_at < CURRENT_TIMESTAMP - INTERVAL '24 hours'
            """)

            # Insert new signals
            for signal in signals:
                cur.execute("""
                    INSERT INTO bridge_flow_signals
                    (signal_type, chain, timeframe, metric_name, metric_value,
                     threshold, interpretation, alert_level)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    signal['signal_type'],
                    signal['chain'],
                    signal['timeframe'],
                    signal['metric_name'],
                    signal['metric_value'],
                    signal['threshold'],
                    signal['interpretation'],
                    signal['alert_level']
                ))

            conn.commit()
            print(f"  [OK] Saved {len(signals)} signals to database")
            return True

        except Exception as e:
            print(f"  [ERROR] Failed to save signals: {e}")
            if conn:
                conn.rollback()
            return False
        finally:
            if conn:
                cur.close()
                conn.close()

    def print_summary(self, all_metrics: Dict[str, Dict], signals: List[Dict]):
        """
        Print a summary of bridge flows and signals
        """
        print("\n" + "="*60)
        print("BRIDGE FLOWS SUMMARY")
        print("="*60)

        # Sort by 7d net flow
        sorted_chains = sorted(
            all_metrics.items(),
            key=lambda x: x[1].get('7d', {}).get('net_flow', 0) if x[1] else 0,
            reverse=True
        )

        print("\n[L2 CAPITAL FLOWS - 7 Day]:")
        for chain, metrics in sorted_chains[:7]:
            if not metrics:
                continue
            net_flow = metrics.get('7d', {}).get('net_flow', 0)
            velocity = metrics.get('velocity', 0)

            # Format flow
            if abs(net_flow) > 1e6:
                flow_str = f"${net_flow/1e6:+.1f}M"
            else:
                flow_str = f"${net_flow/1e3:+.0f}K"

            # Flow direction indicator
            if net_flow > 10e6:
                indicator = "[INFLOW]"
            elif net_flow < -10e6:
                indicator = "[OUTFLOW]"
            else:
                indicator = "[NEUTRAL]"

            print(f"  {chain:15} {flow_str:>12} {indicator:10} Velocity: {velocity:+.1f}%")

        # Print top signals
        if signals:
            print("\n[TOP SIGNALS]:")
            critical_signals = [s for s in signals if s['alert_level'] == 'critical']
            warning_signals = [s for s in signals if s['alert_level'] == 'warning']

            for signal in critical_signals[:3]:
                print(f"  [CRITICAL] {signal['interpretation']}")

            for signal in warning_signals[:3]:
                print(f"  [WARNING] {signal['interpretation']}")

        # Print rotation leader
        if sorted_chains:
            leader = sorted_chains[0]
            if leader[1] and leader[1].get('7d', {}).get('net_flow', 0) > 10e6:
                print(f"\n[ROTATION LEADER]: {leader[0]} receiving major capital inflows")

        print("="*60)

    def run_once(self) -> bool:
        """
        Single execution of bridge flow monitoring
        """
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Collecting bridge flow data...")

        all_metrics = {}
        success_count = 0

        # Fetch data for each L2
        for chain in self.L2_CHAINS:
            print(f"  Fetching {chain}...", end=' ')

            # Get 30 days of data
            volume_data = self.fetch_bridge_volume(chain, lookback_days=30)

            if volume_data:
                # Calculate metrics
                metrics = self.calculate_metrics(volume_data)
                all_metrics[chain] = metrics

                # Save to database
                if self.save_to_database(chain, volume_data):
                    success_count += 1
                    print("[OK]")
                else:
                    print("[DB ERROR]")
            else:
                print("[API ERROR]")

            # Small delay to be respectful
            time.sleep(0.5)

        # Generate and save signals
        if all_metrics:
            signals = self.generate_signals(all_metrics)
            self.save_signals(signals)

            # Print summary
            self.print_summary(all_metrics, signals)

        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Bridge flow monitoring complete")
        print(f"  Successfully processed {success_count}/{len(self.L2_CHAINS)} chains")

        return success_count > 0

    def run_continuous(self):
        """
        Run continuously with specified interval
        """
        INTERVAL = 30 * 60  # 30 minutes

        print(f"Starting Bridge Flows Monitor (30-minute intervals)...")

        while True:
            try:
                self.run_once()
            except KeyboardInterrupt:
                print("\nShutting down Bridge Flows Monitor...")
                break
            except Exception as e:
                print(f"\n[ERROR] Unexpected error: {e}")

            # Wait for next cycle
            print(f"\nNext update in {INTERVAL//60} minutes...")
            time.sleep(INTERVAL)


if __name__ == "__main__":
    monitor = BridgeFlowsMonitor()

    # Single run for testing
    success = monitor.run_once()

    if success:
        print("\n[SUCCESS] Bridge flows data collected successfully")
        print("\nTo run continuously, uncomment the last line")

    # Uncomment for continuous monitoring
    # monitor.run_continuous()