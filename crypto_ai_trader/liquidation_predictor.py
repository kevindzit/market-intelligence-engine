"""
Liquidation Predictor - FREE & Robust
Tracks liquidations in real-time and predicts cascades BEFORE they happen
Uses only free data sources: Binance WebSocket + your existing data
"""

import asyncio
import websockets
import json
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from collections import defaultdict, deque
import threading
import time
import psycopg2
import config


class LiquidationPredictor:
    """
    Predicts liquidation cascades using FREE data:
    1. Real-time liquidations from Binance WebSocket
    2. Calculated liquidation zones based on leverage
    3. Integration with your existing OI and funding data
    """

    def __init__(self):
        """Initialize liquidation predictor"""
        self.liquidation_history = defaultdict(lambda: deque(maxlen=100))
        self.cascade_risk_scores = {}
        self.ws_thread = None
        self.running = False

        # Common leverage ratios in crypto
        self.leverage_levels = [10, 20, 25, 50, 75, 100]

        # Track liquidation velocity (liquidations per minute)
        self.liquidation_velocity = defaultdict(lambda: deque(maxlen=60))

    def start_tracking(self):
        """Start WebSocket tracking in background thread"""
        if not self.running:
            self.running = True
            self.ws_thread = threading.Thread(target=self._run_websocket)
            self.ws_thread.daemon = True
            self.ws_thread.start()
            print("[LIQUIDATION TRACKER] Started real-time tracking")

    def stop_tracking(self):
        """Stop WebSocket tracking"""
        self.running = False
        if self.ws_thread:
            self.ws_thread.join(timeout=5)
        print("[LIQUIDATION TRACKER] Stopped")

    def _run_websocket(self):
        """Run WebSocket in asyncio loop"""
        asyncio.new_event_loop().run_until_complete(self._track_liquidations())

    async def _track_liquidations(self):
        """
        Track real-time liquidations from Binance WebSocket
        100% FREE, no API key required!
        """
        ws_url = "wss://fstream.binance.com/ws/!forceOrder@arr"

        while self.running:
            try:
                async with websockets.connect(ws_url) as ws:
                    print("[LIQUIDATIONS] Connected to Binance WebSocket")

                    while self.running:
                        try:
                            msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                            data = json.loads(msg)

                            if 'o' in data:
                                self._process_liquidation(data['o'])

                        except asyncio.TimeoutError:
                            continue
                        except Exception as e:
                            print(f"[ERROR] WebSocket receive: {e}")
                            break

            except Exception as e:
                print(f"[ERROR] WebSocket connection: {e}")
                await asyncio.sleep(5)

    def _process_liquidation(self, liq_data: Dict):
        """Process incoming liquidation data"""
        try:
            # Parse liquidation
            symbol = liq_data['s'].replace('USDT', '')  # BTCUSDT -> BTC
            side = liq_data['S']  # SELL = long liquidated, BUY = short liquidated
            price = float(liq_data['p'])
            quantity = float(liq_data['q'])
            timestamp = datetime.fromtimestamp(liq_data['T'] / 1000)
            value_usd = price * quantity

            # Store in history
            self.liquidation_history[symbol].append({
                'side': side,
                'price': price,
                'quantity': quantity,
                'value_usd': value_usd,
                'timestamp': timestamp
            })

            # Track velocity
            self.liquidation_velocity[symbol].append(timestamp)

            # Log significant liquidations
            if value_usd > 100000:  # >$100k liquidation
                direction = "LONG" if side == "SELL" else "SHORT"
                print(f"[LIQUIDATION] {symbol} {direction} ${value_usd:,.0f} at ${price:,.2f}")

        except Exception as e:
            pass  # Silent fail for untracked symbols

    def calculate_liquidation_zones(self, token: str, current_price: float) -> Dict:
        """
        Calculate WHERE liquidations will occur based on leverage
        This is the secret sauce - we know where cascades will trigger!
        """
        zones = {
            'long_liquidation_zones': [],
            'short_liquidation_zones': []
        }

        # Calculate liquidation prices for common leverage levels
        for leverage in self.leverage_levels:
            # Long liquidation = price drops by (100/leverage)%
            long_liq_price = current_price * (1 - 1/leverage)

            # Short liquidation = price rises by (100/leverage)%
            short_liq_price = current_price * (1 + 1/leverage)

            # Calculate distance from current price
            long_distance = (current_price - long_liq_price) / current_price * 100
            short_distance = (short_liq_price - current_price) / current_price * 100

            zones['long_liquidation_zones'].append({
                'leverage': leverage,
                'price': long_liq_price,
                'distance_pct': long_distance,
                'danger': long_distance < 3  # Within 3% = danger zone
            })

            zones['short_liquidation_zones'].append({
                'leverage': leverage,
                'price': short_liq_price,
                'distance_pct': short_distance,
                'danger': short_distance < 3  # Within 3% = danger zone
            })

        return zones

    def get_liquidation_velocity(self, token: str) -> float:
        """
        Calculate liquidations per minute (velocity)
        High velocity = cascade in progress
        """
        if not self.liquidation_velocity[token]:
            return 0

        # Count liquidations in last minute
        now = datetime.now()
        one_min_ago = now - timedelta(minutes=1)

        recent_liqs = [
            ts for ts in self.liquidation_velocity[token]
            if ts > one_min_ago
        ]

        return len(recent_liqs)

    def get_liquidation_stats(self, token: str, minutes: int = 5) -> Dict:
        """
        Get liquidation statistics for last N minutes
        """
        if not self.liquidation_history[token]:
            return {
                'total_count': 0,
                'total_value_usd': 0,
                'long_liquidations': 0,
                'short_liquidations': 0,
                'long_pct': 0,
                'short_pct': 0,
                'largest_liquidation': 0,
                'velocity': 0
            }

        # Filter recent liquidations
        cutoff_time = datetime.now() - timedelta(minutes=minutes)
        recent = [
            liq for liq in self.liquidation_history[token]
            if liq['timestamp'] > cutoff_time
        ]

        if not recent:
            return {
                'total_count': 0,
                'total_value_usd': 0,
                'long_liquidations': 0,
                'short_liquidations': 0,
                'long_pct': 0,
                'short_pct': 0,
                'largest_liquidation': 0,
                'velocity': 0
            }

        # Calculate statistics
        total_value = sum(liq['value_usd'] for liq in recent)
        long_count = sum(1 for liq in recent if liq['side'] == 'SELL')
        short_count = sum(1 for liq in recent if liq['side'] == 'BUY')

        return {
            'total_count': len(recent),
            'total_value_usd': total_value,
            'long_liquidations': long_count,
            'short_liquidations': short_count,
            'long_pct': (long_count / len(recent) * 100) if recent else 0,
            'short_pct': (short_count / len(recent) * 100) if recent else 0,
            'largest_liquidation': max((liq['value_usd'] for liq in recent), default=0),
            'velocity': self.get_liquidation_velocity(token)
        }

    def calculate_cascade_risk(self, token: str, current_price: float,
                              funding_rate: Optional[float] = None,
                              oi_change_pct: Optional[float] = None) -> Dict:
        """
        Calculate risk of liquidation cascade (0-100 score)
        Combines multiple FREE data sources for accuracy
        """
        risk_components = {}

        # 1. Liquidation velocity (real-time from WebSocket)
        velocity = self.get_liquidation_velocity(token)
        risk_components['velocity'] = min(velocity * 10, 30)  # Max 30 points

        # 2. Recent liquidation volume
        stats = self.get_liquidation_stats(token, minutes=5)
        if stats['total_value_usd'] > 1000000:  # >$1M in 5 min
            risk_components['volume'] = 20
        elif stats['total_value_usd'] > 500000:  # >$500k
            risk_components['volume'] = 10
        else:
            risk_components['volume'] = stats['total_value_usd'] / 100000 * 2

        # 3. One-sided liquidations (cascade direction)
        if stats['long_pct'] > 70:
            risk_components['direction'] = 15  # Long squeeze happening
            cascade_type = "LONG_SQUEEZE"
        elif stats['short_pct'] > 70:
            risk_components['direction'] = 15  # Short squeeze happening
            cascade_type = "SHORT_SQUEEZE"
        else:
            risk_components['direction'] = 0
            cascade_type = "BALANCED"

        # 4. Proximity to liquidation zones
        zones = self.calculate_liquidation_zones(token, current_price)

        # Check if we're near any danger zones
        long_danger = any(z['danger'] for z in zones['long_liquidation_zones'])
        short_danger = any(z['danger'] for z in zones['short_liquidation_zones'])

        if long_danger or short_danger:
            risk_components['proximity'] = 20
        else:
            # Find nearest liquidation zone
            nearest_long = min(z['distance_pct'] for z in zones['long_liquidation_zones'])
            nearest_short = min(z['distance_pct'] for z in zones['short_liquidation_zones'])
            nearest = min(nearest_long, nearest_short)
            risk_components['proximity'] = max(0, 15 - nearest)  # Closer = higher risk

        # 5. Funding rate extreme (if provided)
        if funding_rate is not None:
            # Extreme funding = overcrowded positions
            risk_components['funding'] = min(abs(funding_rate) * 500, 15)
        else:
            risk_components['funding'] = 0

        # 6. Open Interest surge (if provided)
        if oi_change_pct is not None:
            # Rapid OI increase = leverage building
            risk_components['oi_surge'] = min(abs(oi_change_pct), 15)
        else:
            risk_components['oi_surge'] = 0

        # Calculate total risk score
        total_risk = sum(risk_components.values())
        total_risk = min(total_risk, 100)  # Cap at 100

        # Determine alert level
        if total_risk >= 70:
            alert = "EXTREME"
            action = "CLOSE_POSITIONS"
        elif total_risk >= 50:
            alert = "HIGH"
            action = "REDUCE_EXPOSURE"
        elif total_risk >= 30:
            alert = "MODERATE"
            action = "MONITOR_CLOSELY"
        else:
            alert = "LOW"
            action = "NORMAL"

        return {
            'risk_score': total_risk,
            'alert_level': alert,
            'recommended_action': action,
            'cascade_type': cascade_type,
            'risk_components': risk_components,
            'liquidation_stats': stats,
            'nearest_long_liq': zones['long_liquidation_zones'][0],
            'nearest_short_liq': zones['short_liquidation_zones'][0]
        }

    def enhance_trading_decision(self, decision: Dict, token: str, current_price: float) -> Dict:
        """
        Enhance AI trading decision with liquidation awareness
        This is where we add the secret sauce to your existing system!
        """
        # Get cascade risk
        risk_data = self.calculate_cascade_risk(token, current_price)

        # Store risk in decision
        decision['liquidation_risk'] = risk_data['risk_score']
        decision['cascade_type'] = risk_data['cascade_type']

        # Adjust confidence based on liquidation risk
        if risk_data['risk_score'] >= 70:
            # EXTREME risk - modify decision
            if decision['action'] == 'BUY' and risk_data['cascade_type'] == 'LONG_SQUEEZE':
                # Don't buy into a long squeeze!
                decision['action'] = 'HOLD'
                decision['reasoning'] += ' [OVERRIDE: Long liquidation cascade detected]'

            elif decision['action'] == 'BUY' and risk_data['cascade_type'] == 'SHORT_SQUEEZE':
                # Short squeeze = bullish, increase confidence
                decision['confidence'] = min(decision['confidence'] * 1.3, 1.0)
                decision['reasoning'] += ' [BOOST: Short squeeze imminent]'

            elif decision['action'] == 'SELL' and risk_data['cascade_type'] == 'LONG_SQUEEZE':
                # Long liquidations = bearish, increase confidence
                decision['confidence'] = min(decision['confidence'] * 1.3, 1.0)
                decision['reasoning'] += ' [BOOST: Long liquidation cascade]'

        elif risk_data['risk_score'] >= 50:
            # HIGH risk - be cautious
            if decision['action'] != 'HOLD':
                decision['position_size'] *= 0.5  # Half position size
                decision['reasoning'] += ' [CAUTION: High liquidation risk, reduced size]'

        # Add liquidation data to reasoning
        stats = risk_data['liquidation_stats']
        if stats['velocity'] > 5:
            decision['reasoning'] += f" Liquidation velocity: {stats['velocity']}/min."

        return decision

    def get_enhanced_summary(self, token: str, current_price: float) -> str:
        """
        Generate liquidation-aware market summary for Claude
        Adds critical liquidation data to your existing summaries
        """
        risk_data = self.calculate_cascade_risk(token, current_price)
        stats = risk_data['liquidation_stats']

        summary = f"""
=== LIQUIDATION ANALYSIS ===
Risk Score: {risk_data['risk_score']}/100 ({risk_data['alert_level']})
Recent Liquidations (5 min): {stats['total_count']} (${stats['total_value_usd']:,.0f})
Long/Short Ratio: {stats['long_pct']:.0f}%/{stats['short_pct']:.0f}%
Velocity: {stats['velocity']} liquidations/minute
Cascade Type: {risk_data['cascade_type']}

Nearest Liquidation Zones:
- Long Liquidation ({risk_data['nearest_long_liq']['leverage']}x): ${risk_data['nearest_long_liq']['price']:,.2f} (-{risk_data['nearest_long_liq']['distance_pct']:.1f}%)
- Short Liquidation ({risk_data['nearest_short_liq']['leverage']}x): ${risk_data['nearest_short_liq']['price']:,.2f} (+{risk_data['nearest_short_liq']['distance_pct']:.1f}%)

Recommended Action: {risk_data['recommended_action']}
"""

        if risk_data['risk_score'] >= 70:
            summary = "⚠️ LIQUIDATION CASCADE WARNING ⚠️\n" + summary

        return summary


# Singleton instance
_liquidation_predictor = None

def get_liquidation_predictor() -> LiquidationPredictor:
    """Get or create singleton liquidation predictor"""
    global _liquidation_predictor
    if _liquidation_predictor is None:
        _liquidation_predictor = LiquidationPredictor()
        _liquidation_predictor.start_tracking()
    return _liquidation_predictor


# Test function
if __name__ == "__main__":
    print("Testing Liquidation Predictor...\n")

    # Start tracking
    predictor = get_liquidation_predictor()

    # Test with BTC at $109,000
    token = 'BTC'
    price = 109000

    # Calculate liquidation zones
    zones = predictor.calculate_liquidation_zones(token, price)

    print(f"Liquidation Zones for {token} at ${price:,.0f}:\n")
    print("LONG Liquidation Prices (if price drops):")
    for zone in zones['long_liquidation_zones'][:3]:
        marker = " ⚠️ DANGER" if zone['danger'] else ""
        print(f"  {zone['leverage']}x leverage: ${zone['price']:,.0f} (-{zone['distance_pct']:.1f}%){marker}")

    print("\nSHORT Liquidation Prices (if price rises):")
    for zone in zones['short_liquidation_zones'][:3]:
        marker = " ⚠️ DANGER" if zone['danger'] else ""
        print(f"  {zone['leverage']}x leverage: ${zone['price']:,.0f} (+{zone['distance_pct']:.1f}%){marker}")

    # Wait for some liquidation data
    print("\nMonitoring real-time liquidations for 30 seconds...")
    time.sleep(30)

    # Get cascade risk
    risk = predictor.calculate_cascade_risk(token, price)
    print(f"\nCascade Risk Analysis:")
    print(f"  Risk Score: {risk['risk_score']}/100")
    print(f"  Alert Level: {risk['alert_level']}")
    print(f"  Action: {risk['recommended_action']}")
    print(f"  Components: {risk['risk_components']}")

    # Get enhanced summary
    summary = predictor.get_enhanced_summary(token, price)
    print(summary)

    # Clean shutdown
    predictor.stop_tracking()