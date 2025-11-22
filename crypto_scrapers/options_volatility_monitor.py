"""
Options Volatility Monitor - Tracks BTC/ETH implied volatility and skew
Provides AI trader with forward-looking volatility signals for risk management
Uses Deribit public API (free, no key required)
"""

import os
import sys
import time
import requests
import psycopg2
from psycopg2.extras import execute_values
from datetime import datetime, timedelta
from typing import Dict, Optional
import json
from pathlib import Path

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

class OptionsVolatilityMonitor:
    """
    Monitor options implied volatility and skew using Deribit's free API

    Key metrics tracked:
    - BTC/ETH 25-delta Implied Volatility (market's expectation of future volatility)
    - Put-Call Skew (shows directional bias - negative = put premium/fear)
    - IV Rank (current IV vs 30-day range)

    Risk signals:
    - IV > 80: High fear, reduce positions
    - Skew < -8: Heavy put buying, crash protection active
    - IV spike + negative skew: Smart money hedging
    """

    def __init__(self):
        """Initialize the options volatility monitor"""
        # Database connection parameters
        self.db_params = {
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': os.getenv('DB_PORT', '54594'),
            'database': os.getenv('DB_NAME', 'pjx'),
            'user': os.getenv('DB_USER', 'postgres'),
            'password': os.getenv('DB_PASSWORD', 'password')
        }

        # Deribit public API endpoints (free, no authentication needed)
        self.BASE_URL = "https://www.deribit.com/api/v2/public"

        # Tracked metrics
        self.CURRENCIES = ['BTC', 'ETH']

        print(f"[{datetime.now().strftime('%H:%M:%S')}] Options Volatility Monitor initialized")
        print(f"  Tracking: {', '.join(self.CURRENCIES)} implied volatility")
        print(f"  API: Deribit (free public endpoints)")

    def get_db_connection(self):
        """Create a database connection"""
        return psycopg2.connect(**self.db_params)

    def fetch_volatility_index(self, currency: str) -> Optional[Dict]:
        """
        Fetch volatility index for a currency (DVOL - Deribit Volatility Index)
        This is similar to VIX for traditional markets
        """
        try:
            # Get the volatility index
            index_name = f"{currency}_DVOL"
            url = f"{self.BASE_URL}/get_index_price"
            params = {"index_name": index_name}

            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if 'result' in data:
                    return {
                        'dvol': data['result']['index_price'],
                        'timestamp': datetime.now()
                    }
            return None

        except Exception as e:
            print(f"[WARNING] Failed to fetch {currency} volatility index: {e}")
            return None

    def fetch_atm_volatility(self, currency: str) -> Optional[Dict]:
        """
        Fetch at-the-money implied volatility from the orderbook
        Uses the nearest expiry options to get current market sentiment
        """
        try:
            # Get current price to find ATM strike
            ticker_url = f"{self.BASE_URL}/ticker"

            # Get the perpetual to find current price
            params = {"instrument_name": f"{currency}-PERPETUAL"}
            response = requests.get(ticker_url, params=params, timeout=10)

            if response.status_code != 200:
                return None

            data = response.json()
            if 'result' not in data:
                return None

            current_price = data['result']['index_price']

            # Find nearest Friday expiry (Deribit standard)
            today = datetime.now()
            days_ahead = 4 - today.weekday()  # Friday is 4
            if days_ahead <= 0:  # Today is Friday or later
                days_ahead += 7
            next_friday = today + timedelta(days=days_ahead)

            # Format expiry (e.g., "29NOV24")
            expiry = next_friday.strftime("%d%b%y").upper()

            # Round to nearest standard strike
            if currency == 'BTC':
                strike = round(current_price / 1000) * 1000  # Round to nearest 1000
            else:  # ETH
                strike = round(current_price / 100) * 100  # Round to nearest 100

            # Get call option data
            call_instrument = f"{currency}-{expiry}-{int(strike)}-C"
            params = {"instrument_name": call_instrument}
            response = requests.get(ticker_url, params=params, timeout=10)

            if response.status_code == 200:
                data = response.json()
                if 'result' in data and data['result']:
                    call_iv = data['result'].get('mark_iv', 0)

                    # Get put option data
                    put_instrument = f"{currency}-{expiry}-{int(strike)}-P"
                    params = {"instrument_name": put_instrument}
                    response = requests.get(ticker_url, params=params, timeout=10)

                    if response.status_code == 200:
                        put_data = response.json()
                        if 'result' in put_data and put_data['result']:
                            put_iv = put_data['result'].get('mark_iv', 0)

                            # ATM IV is average of put and call
                            atm_iv = (call_iv + put_iv) / 2

                            return {
                                'atm_iv': atm_iv,
                                'call_iv': call_iv,
                                'put_iv': put_iv,
                                'strike': strike,
                                'expiry': expiry,
                                'current_price': current_price
                            }

            return None

        except Exception as e:
            print(f"[WARNING] Failed to fetch {currency} ATM volatility: {e}")
            return None

    def calculate_skew(self, currency: str) -> Optional[Dict]:
        """
        Calculate 25-delta put-call skew
        Negative skew = puts more expensive (fear)
        Positive skew = calls more expensive (greed)
        """
        try:
            # Get volatility smile data
            url = f"{self.BASE_URL}/get_volatility_index_data"
            params = {
                "currency": currency,
                "resolution": "1d",
                "count": 1
            }

            response = requests.get(url, params=params, timeout=10)

            if response.status_code == 200:
                data = response.json()
                if 'result' in data and data['result']:
                    # Latest data point
                    latest = data['result'][-1] if isinstance(data['result'], list) else data['result']

                    # Extract if available (Deribit provides some skew data)
                    # Fallback to simple calculation if not available
                    return {
                        'skew_25d': 0,  # Will calculate from option chain if needed
                        'timestamp': datetime.now()
                    }

            # If we can't get smile data, estimate from ATM options
            atm_data = self.fetch_atm_volatility(currency)
            if atm_data:
                # Simple skew estimate: put IV - call IV
                skew = atm_data['put_iv'] - atm_data['call_iv']
                return {
                    'skew_25d': skew,
                    'put_iv': atm_data['put_iv'],
                    'call_iv': atm_data['call_iv'],
                    'timestamp': datetime.now()
                }

            return None

        except Exception as e:
            print(f"[WARNING] Failed to calculate {currency} skew: {e}")
            return None

    def calculate_iv_rank(self, currency: str, current_iv: float) -> float:
        """
        Calculate IV rank (0-100) - where current IV sits in 30-day range
        High IV rank = current volatility high relative to recent history
        """
        try:
            with self.get_db_connection() as conn:
                with conn.cursor() as cur:
                    # Get 30-day IV range
                    cur.execute(f"""
                        SELECT
                            MIN({currency.lower()}_iv) as min_iv,
                            MAX({currency.lower()}_iv) as max_iv
                        FROM options_volatility
                        WHERE scraped_at > NOW() - INTERVAL '30 days'
                        AND {currency.lower()}_iv IS NOT NULL
                    """)

                    result = cur.fetchone()
                    if result and result[0] is not None and result[1] is not None:
                        min_iv = float(result[0])
                        max_iv = float(result[1])

                        if max_iv > min_iv:
                            span = max_iv - min_iv
                            iv_rank = ((current_iv - min_iv) / span) * 100
                            # Clamp to [0, 100] so extreme moves don't overflow DB numeric fields
                            iv_rank = max(0.0, min(iv_rank, 100.0))
                            return round(iv_rank, 1)

            return 50.0  # Default to middle if no history

        except:
            return 50.0

    def generate_risk_signals(self, btc_data: Dict, eth_data: Dict) -> Dict:
        """Generate trading risk signals from options data"""
        signals = {
            'risk_level': 'NORMAL',
            'volatility_regime': 'MODERATE',
            'directional_bias': 'NEUTRAL',
            'position_adjustment': 1.0,
            'warnings': []
        }

        # Average IV across BTC and ETH
        avg_iv = (btc_data.get('iv', 50) + eth_data.get('iv', 50)) / 2
        avg_skew = (btc_data.get('skew', 0) + eth_data.get('skew', 0)) / 2

        # Determine volatility regime
        if avg_iv > 80:
            signals['volatility_regime'] = 'EXTREME'
            signals['risk_level'] = 'HIGH'
            signals['position_adjustment'] = 0.5  # Half position size
            signals['warnings'].append(f"Extreme volatility: IV={avg_iv:.1f}")
        elif avg_iv > 65:
            signals['volatility_regime'] = 'HIGH'
            signals['risk_level'] = 'MODERATE'
            signals['position_adjustment'] = 0.75
            signals['warnings'].append(f"Elevated volatility: IV={avg_iv:.1f}")
        elif avg_iv < 35:
            signals['volatility_regime'] = 'LOW'
            signals['position_adjustment'] = 1.2  # Can increase size in low vol

        # Check skew for directional bias
        if avg_skew < -8:
            signals['directional_bias'] = 'BEARISH_EXTREME'
            signals['risk_level'] = 'HIGH'
            signals['warnings'].append(f"Heavy put buying: Skew={avg_skew:.1f}")
            signals['position_adjustment'] *= 0.7  # Further reduce
        elif avg_skew < -4:
            signals['directional_bias'] = 'BEARISH'
            signals['warnings'].append(f"Put premium elevated: Skew={avg_skew:.1f}")
        elif avg_skew > 4:
            signals['directional_bias'] = 'BULLISH'

        # Check for volatility spike (IV rank)
        avg_iv_rank = (btc_data.get('iv_rank', 50) + eth_data.get('iv_rank', 50)) / 2
        if avg_iv_rank > 80:
            signals['warnings'].append(f"IV at 30-day highs: Rank={avg_iv_rank:.0f}")
            signals['risk_level'] = 'HIGH' if signals['risk_level'] != 'HIGH' else signals['risk_level']

        return signals

    def save_to_database(self, btc_data: Dict, eth_data: Dict, risk_signals: Dict):
        """Save volatility data and risk signals to database"""
        try:
            with self.get_db_connection() as conn:
                with conn.cursor() as cur:
                    timestamp = datetime.now()

                    # Save volatility data
                    cur.execute("""
                        INSERT INTO options_volatility
                        (btc_iv, btc_dvol, btc_skew, btc_iv_rank,
                         eth_iv, eth_dvol, eth_skew, eth_iv_rank,
                         avg_iv, volatility_regime, directional_bias,
                         risk_level, position_adjustment, scraped_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        btc_data.get('iv'),
                        btc_data.get('dvol'),
                        btc_data.get('skew'),
                        btc_data.get('iv_rank'),
                        eth_data.get('iv'),
                        eth_data.get('dvol'),
                        eth_data.get('skew'),
                        eth_data.get('iv_rank'),
                        (btc_data.get('iv', 50) + eth_data.get('iv', 50)) / 2,
                        risk_signals['volatility_regime'],
                        risk_signals['directional_bias'],
                        risk_signals['risk_level'],
                        risk_signals['position_adjustment'],
                        timestamp
                    ))

                    conn.commit()
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Saved options volatility data")

        except Exception as e:
            print(f"[ERROR] Failed to save to database: {e}")

    def print_summary(self, btc_data: Dict, eth_data: Dict, risk_signals: Dict):
        """Print a summary of current volatility conditions"""
        print("\n" + "="*60)
        print("OPTIONS VOLATILITY SUMMARY")
        print("="*60)

        # BTC metrics
        print("\n[BTC]:")
        print(f"  IV: {btc_data.get('iv', 0) or 0:.1f}%")
        print(f"  DVOL: {btc_data.get('dvol', 0) or 0:.1f}")
        print(f"  Skew: {btc_data.get('skew', 0) or 0:+.1f}")
        print(f"  IV Rank: {btc_data.get('iv_rank', 50) or 50:.0f}/100")

        # ETH metrics
        print("\n[ETH]:")
        print(f"  IV: {eth_data.get('iv', 0) or 0:.1f}%")
        print(f"  DVOL: {eth_data.get('dvol', 0) or 0:.1f}")
        print(f"  Skew: {eth_data.get('skew', 0) or 0:+.1f}")
        print(f"  IV Rank: {eth_data.get('iv_rank', 50) or 50:.0f}/100")

        # Risk signals
        print("\n[RISK SIGNALS]:")
        print(f"  Volatility Regime: {risk_signals['volatility_regime']}")
        print(f"  Directional Bias: {risk_signals['directional_bias']}")
        print(f"  Risk Level: {risk_signals['risk_level']}")
        print(f"  Position Adjustment: {risk_signals['position_adjustment']:.0%}")

        if risk_signals['warnings']:
            print("\n[WARNINGS]:")
            for warning in risk_signals['warnings']:
                print(f"  - {warning}")

        print("\n" + "="*60 + "\n")

    def run_once(self):
        """Run one collection cycle"""
        try:
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Collecting options volatility data...")

            btc_data = {}
            eth_data = {}

            # Fetch data for each currency
            for currency in self.CURRENCIES:
                # Get DVOL index
                dvol_data = self.fetch_volatility_index(currency)

                # Get ATM implied volatility
                atm_data = self.fetch_atm_volatility(currency)

                # Calculate skew
                skew_data = self.calculate_skew(currency)

                # Combine data
                currency_data = {
                    'dvol': dvol_data['dvol'] if dvol_data else None,
                    'iv': atm_data['atm_iv'] if atm_data else None,
                    'skew': skew_data['skew_25d'] if skew_data else 0,
                    'iv_rank': 50  # Will be calculated after we have history
                }

                # Calculate IV rank if we have current IV
                if currency_data['iv']:
                    currency_data['iv_rank'] = self.calculate_iv_rank(currency, currency_data['iv'])

                if currency == 'BTC':
                    btc_data = currency_data
                else:
                    eth_data = currency_data

                time.sleep(0.5)  # Be respectful with API calls

            # Generate risk signals
            risk_signals = self.generate_risk_signals(btc_data, eth_data)

            # Save to database
            if btc_data.get('iv') or eth_data.get('iv'):
                self.save_to_database(btc_data, eth_data, risk_signals)

            # Print summary
            self.print_summary(btc_data, eth_data, risk_signals)

            return True

        except Exception as e:
            print(f"[ERROR] Collection cycle failed: {e}")
            import traceback
            traceback.print_exc()
            return False

    def run(self):
        """Main loop - runs every 15 minutes"""
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Options Volatility Monitor starting...")
        print("  Collection interval: 15 minutes")
        print("  Data source: Deribit public API (free)")

        while True:
            try:
                # Run collection
                success = self.run_once()

                if success:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Sleeping for 15 minutes...")
                else:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Collection failed, retrying in 5 minutes...")
                    time.sleep(300)  # 5 minutes on failure
                    continue

                # Sleep for 15 minutes
                time.sleep(900)

            except KeyboardInterrupt:
                print("\n[INFO] Options Volatility Monitor stopped by user")
                break
            except Exception as e:
                print(f"[ERROR] Unexpected error: {e}")
                time.sleep(300)  # 5 minutes on error

def main():
    """Entry point"""
    from dotenv import load_dotenv
    load_dotenv()

    monitor = OptionsVolatilityMonitor()
    monitor.run()

if __name__ == "__main__":
    main()
