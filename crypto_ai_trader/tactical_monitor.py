"""
Tactical Monitoring Layer - High-frequency monitoring for critical market events
Uses Gemini Flash for ultra-fast, cost-effective real-time analysis
Monitors: Order book imbalances, liquidation cascades, volume spikes, sentiment velocity
"""

import asyncio
import os
import time
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from collections import defaultdict
import google.generativeai as genai
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
from data_intelligence import DataIntelligence

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TacticalMonitor:
    """High-frequency tactical monitoring using Gemini Flash"""

    def __init__(self):
        """Initialize tactical monitor with Gemini Flash"""
        self.conn = None
        self.init_database()
        self.init_gemini()
        self.init_data_intelligence()

        # Monitoring thresholds
        self.ORDER_BOOK_IMBALANCE_THRESHOLD = 0.65  # 65% imbalance triggers alert
        self.LIQUIDATION_CLUSTER_THRESHOLD = 5.0     # 5% price range with heavy liquidations
        self.VOLUME_SPIKE_MULTIPLIER = 3.0           # 3x normal volume = spike
        self.SENTIMENT_VELOCITY_THRESHOLD = 0.3      # 30% sentiment change in 5 min

        # Caching for performance
        self.baseline_volumes = {}
        self.last_sentiment = {}
        self.alert_cooldowns = defaultdict(lambda: datetime.min)

    def init_database(self):
        """Initialize database connection"""
        try:
            self.conn = psycopg2.connect(
                host=os.getenv('DB_HOST', 'localhost'),
                port=int(os.getenv('DB_PORT', 54594)),
                user=os.getenv('DB_USER', 'postgres'),
                password=os.getenv('DB_PASSWORD', 'postgres'),
                database=os.getenv('DB_NAME', 'pjx')
            )
            logger.info("Database connection established for tactical monitoring")
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            raise

    def init_gemini(self):
        """Initialize Gemini Flash for ultra-fast analysis"""
        try:
            genai.configure(api_key=os.getenv('GEMINI_KEY'))
            self.gemini_model = genai.GenerativeModel('gemini-2.0-flash-exp')
            logger.info("Gemini Flash initialized for tactical monitoring")
        except Exception as e:
            logger.error(f"Gemini initialization failed: {e}")
            raise

    def init_data_intelligence(self):
        """Initialize DataIntelligence for sentiment timing analysis"""
        try:
            db_config = {
                'host': os.getenv('DB_HOST', 'localhost'),
                'port': int(os.getenv('DB_PORT', 54594)),
                'database': os.getenv('DB_NAME', 'pjx'),
                'user': os.getenv('DB_USER', 'postgres'),
                'password': os.getenv('DB_PASSWORD', 'postgres')
            }
            self.data_intel = DataIntelligence(db_config)
            logger.info("DataIntelligence initialized for sentiment timing analysis")
        except Exception as e:
            logger.error(f"DataIntelligence initialization failed: {e}")
            raise

    def check_order_book_imbalance(self, token: str) -> Optional[Dict]:
        """
        Detect significant order book imbalances that signal imminent price moves
        Research shows 62% win rate with this signal
        """
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Get latest order book data
                cur.execute("""
                    SELECT
                        token,
                        total_bid_volume,
                        total_ask_volume,
                        bid_liquidity_1pct,
                        ask_liquidity_1pct,
                        bid_ask_spread,
                        scraped_at
                    FROM order_book_depth
                    WHERE token = %s
                    AND scraped_at > NOW() - INTERVAL '2 minutes'
                    ORDER BY scraped_at DESC
                    LIMIT 1
                """, (token,))

                orderbook = cur.fetchone()

                if not orderbook:
                    return None

                # Calculate imbalance ratio
                total_volume = orderbook['total_bid_volume'] + orderbook['total_ask_volume']
                if total_volume == 0:
                    return None

                bid_ratio = orderbook['total_bid_volume'] / total_volume

                # Detect significant imbalance
                if bid_ratio > self.ORDER_BOOK_IMBALANCE_THRESHOLD:
                    return {
                        'token': token,
                        'signal': 'BULLISH_IMBALANCE',
                        'bid_ratio': bid_ratio,
                        'spread': orderbook['bid_ask_spread'],
                        'confidence': min(bid_ratio * 100, 90),  # Cap at 90%
                        'message': f"Strong buying pressure detected: {bid_ratio:.1%} bid volume"
                    }
                elif bid_ratio < (1 - self.ORDER_BOOK_IMBALANCE_THRESHOLD):
                    return {
                        'token': token,
                        'signal': 'BEARISH_IMBALANCE',
                        'bid_ratio': bid_ratio,
                        'spread': orderbook['bid_ask_spread'],
                        'confidence': min((1-bid_ratio) * 100, 90),
                        'message': f"Strong selling pressure detected: {(1-bid_ratio):.1%} ask volume"
                    }

                return None

        except Exception as e:
            logger.error(f"Error checking order book imbalance: {e}")
            return None

    def detect_liquidation_cascade(self, token: str) -> Optional[Dict]:
        """
        Detect potential liquidation cascade by analyzing clustered liquidations
        Critical for avoiding October 2025-style $19B wipeouts
        """
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Get recent liquidations and current price
                cur.execute("""
                    WITH current_price AS (
                        SELECT close
                        FROM crypto_ohlcv
                        WHERE token = %s
                        ORDER BY timestamp DESC
                        LIMIT 1
                    ),
                    recent_liquidations AS (
                        SELECT
                            token,
                            side,
                            price,
                            quantity,
                            liquidation_value,
                            scraped_at
                        FROM liquidations
                        WHERE token = %s
                        AND scraped_at > NOW() - INTERVAL '10 minutes'
                    )
                    SELECT
                        l.*,
                        p.close as current_price,
                        ABS(l.price - p.close) / p.close * 100 as price_distance_pct
                    FROM recent_liquidations l
                    CROSS JOIN current_price p
                    ORDER BY l.scraped_at DESC
                """, (token, token))

                liquidations = cur.fetchall()

                if not liquidations or len(liquidations) < 3:
                    return None

                current_price = liquidations[0]['current_price'] if liquidations else 0
                if current_price == 0:
                    return None

                # Analyze liquidation clustering
                long_liquidations = [l for l in liquidations if l['side'] == 'LONG']
                short_liquidations = [l for l in liquidations if l['side'] == 'SHORT']

                # Check for cascade conditions
                cascade_risk = None

                # Long liquidation cascade (price falling)
                if len(long_liquidations) > len(short_liquidations) * 2:
                    avg_distance = sum(l['price_distance_pct'] for l in long_liquidations[:5]) / min(5, len(long_liquidations))
                    if avg_distance < self.LIQUIDATION_CLUSTER_THRESHOLD:
                        total_value = sum(l['liquidation_value'] for l in long_liquidations)
                        cascade_risk = {
                            'token': token,
                            'signal': 'LONG_CASCADE_RISK',
                            'direction': 'DOWN',
                            'liquidation_value': total_value,
                            'cluster_distance': avg_distance,
                            'confidence': min(70 + len(long_liquidations) * 2, 90),
                            'message': f"⚠️ Long liquidation cascade risk: ${total_value:,.0f} clustered within {avg_distance:.1f}%"
                        }

                # Short liquidation cascade (price rising)
                elif len(short_liquidations) > len(long_liquidations) * 2:
                    avg_distance = sum(l['price_distance_pct'] for l in short_liquidations[:5]) / min(5, len(short_liquidations))
                    if avg_distance < self.LIQUIDATION_CLUSTER_THRESHOLD:
                        total_value = sum(l['liquidation_value'] for l in short_liquidations)
                        cascade_risk = {
                            'token': token,
                            'signal': 'SHORT_CASCADE_RISK',
                            'direction': 'UP',
                            'liquidation_value': total_value,
                            'cluster_distance': avg_distance,
                            'confidence': min(70 + len(short_liquidations) * 2, 90),
                            'message': f"⚠️ Short liquidation cascade risk: ${total_value:,.0f} clustered within {avg_distance:.1f}%"
                        }

                return cascade_risk

        except Exception as e:
            logger.error(f"Error detecting liquidation cascade: {e}")
            return None

    def check_volume_spike(self, token: str) -> Optional[Dict]:
        """
        Detect abnormal volume spikes that often precede major price moves
        """
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Get current and baseline volumes
                cur.execute("""
                    WITH current_volume AS (
                        SELECT
                            token,
                            volume,
                            close,
                            timestamp
                        FROM crypto_ohlcv
                        WHERE token = %s
                        AND timestamp > NOW() - INTERVAL '10 minutes'
                        ORDER BY timestamp DESC
                        LIMIT 2
                    ),
                    baseline_volume AS (
                        SELECT
                            AVG(volume) as avg_volume
                        FROM crypto_ohlcv
                        WHERE token = %s
                        AND timestamp > NOW() - INTERVAL '24 hours'
                        AND timestamp < NOW() - INTERVAL '1 hour'
                    )
                    SELECT
                        c.token,
                        c.volume as current_volume,
                        b.avg_volume as baseline_volume,
                        c.volume / NULLIF(b.avg_volume, 0) as volume_multiplier,
                        c.close
                    FROM current_volume c
                    CROSS JOIN baseline_volume b
                    LIMIT 1
                """, (token, token))

                volume_data = cur.fetchone()

                if not volume_data or not volume_data['baseline_volume']:
                    return None

                multiplier = volume_data['volume_multiplier']

                if multiplier > self.VOLUME_SPIKE_MULTIPLIER:
                    return {
                        'token': token,
                        'signal': 'VOLUME_SPIKE',
                        'multiplier': multiplier,
                        'current_volume': volume_data['current_volume'],
                        'baseline_volume': volume_data['baseline_volume'],
                        'confidence': min(50 + (multiplier - 3) * 10, 85),
                        'message': f"🚀 Volume spike detected: {multiplier:.1f}x normal"
                    }

                return None

        except Exception as e:
            logger.error(f"Error checking volume spike: {e}")
            return None

    def check_sentiment_velocity(self, token: str) -> Optional[Dict]:
        """
        Track rapid sentiment changes that predict pumps 10-15 min early
        Your research shows 74% accuracy with this signal
        """
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Get recent sentiment data
                cur.execute("""
                    WITH sentiment_windows AS (
                        SELECT
                            token,
                            AVG(CASE WHEN scraped_at > NOW() - INTERVAL '5 minutes'
                                THEN sentiment_score END) as sentiment_now,
                            AVG(CASE WHEN scraped_at BETWEEN NOW() - INTERVAL '15 minutes'
                                AND NOW() - INTERVAL '5 minutes'
                                THEN sentiment_score END) as sentiment_before,
                            COUNT(CASE WHEN scraped_at > NOW() - INTERVAL '5 minutes'
                                THEN 1 END) as tweets_now,
                            COUNT(CASE WHEN scraped_at BETWEEN NOW() - INTERVAL '15 minutes'
                                AND NOW() - INTERVAL '5 minutes'
                                THEN 1 END) as tweets_before
                        FROM twitter_sentiment
                        WHERE token = %s
                        AND scraped_at > NOW() - INTERVAL '15 minutes'
                        AND bot_probability < 0.3
                        GROUP BY token
                    )
                    SELECT
                        *,
                        (sentiment_now - sentiment_before) as sentiment_change,
                        (tweets_now - tweets_before) / NULLIF(tweets_before, 0) as volume_change
                    FROM sentiment_windows
                """, (token,))

                sentiment = cur.fetchone()

                if not sentiment or not sentiment['sentiment_before']:
                    return None

                # Calculate velocity
                sentiment_velocity = sentiment['sentiment_change']
                volume_velocity = sentiment['volume_change'] or 0

                # Detect significant velocity changes
                if abs(sentiment_velocity) > self.SENTIMENT_VELOCITY_THRESHOLD:
                    direction = 'BULLISH' if sentiment_velocity > 0 else 'BEARISH'

                    # Momentum = sentiment velocity × volume velocity
                    momentum = abs(sentiment_velocity) * (1 + abs(volume_velocity))

                    return {
                        'token': token,
                        'signal': f'{direction}_MOMENTUM',
                        'sentiment_velocity': sentiment_velocity,
                        'volume_velocity': volume_velocity,
                        'momentum': momentum,
                        'current_sentiment': sentiment['sentiment_now'],
                        'confidence': min(50 + momentum * 20, 85),
                        'message': f"💫 {direction} momentum: sentiment {sentiment_velocity:+.2f}, volume {volume_velocity:+.1%}"
                    }

                return None

        except Exception as e:
            logger.error(f"Error checking sentiment velocity: {e}")
            return None

    async def analyze_with_gemini(self, signals: List[Dict]) -> Optional[Dict]:
        """
        Use Gemini Flash for ultra-fast pattern recognition across signals
        """
        if not signals:
            return None

        try:
            prompt = f"""Analyze these real-time crypto trading signals and determine if immediate action is needed.

Signals detected:
{json.dumps(signals, indent=2)}

Research context:
- Order book imbalance >65% has 62% win rate
- Liquidation cascades can trigger within 5-15 minutes
- Volume spikes 3x+ often precede major moves
- Sentiment velocity predicts pumps 10-15 min early with 74% accuracy

Provide a JSON response with:
{{
    "action_required": true/false,
    "urgency": "IMMEDIATE/HIGH/MEDIUM/LOW",
    "recommended_action": "ENTER_LONG/ENTER_SHORT/EXIT_POSITION/MONITOR/NONE",
    "confidence": 0-100,
    "key_signal": "primary signal driving the recommendation",
    "reasoning": "brief explanation",
    "time_sensitivity": "how quickly to act (e.g., 'within 1 minute', 'within 5 minutes')"
}}

Focus on pattern confluence - multiple signals pointing the same direction = higher confidence.
"""

            response = self.gemini_model.generate_content(prompt)
            result = json.loads(response.text)
            return result

        except Exception as e:
            logger.error(f"Gemini analysis failed: {e}")
            return None

    async def monitor_token(self, token: str) -> Optional[Dict]:
        """
        Complete tactical monitoring for a single token
        """
        signals = []

        # Check all signal types
        if signal := self.check_order_book_imbalance(token):
            signals.append(signal)

        if signal := self.detect_liquidation_cascade(token):
            signals.append(signal)

        if signal := self.check_volume_spike(token):
            signals.append(signal)

        if signal := self.check_sentiment_velocity(token):
            signals.append(signal)

        # Check sentiment timing analysis (research-backed timing signals)
        try:
            timing = self.data_intel.analyze_sentiment_timing(token)
            if timing and timing.get('has_signal'):
                signals.append({
                    'token': token,
                    'signal': f"SENTIMENT_TIMING_{timing['signal']}",
                    'action_timing': timing.get('action_timing'),
                    'confidence': timing.get('confidence', 50),
                    'time_to_act': timing.get('time_to_act'),
                    'message': f"⏱️ Timing signal: {timing.get('reasoning', '')}"
                })
        except Exception as e:
            logger.error(f"Sentiment timing analysis failed for {token}: {e}")

        # If we have signals, analyze with Gemini
        if signals:
            analysis = await self.analyze_with_gemini(signals)
            if analysis:
                return {
                    'token': token,
                    'timestamp': datetime.now(),
                    'signals': signals,
                    'analysis': analysis,
                    'alert_level': 'CRITICAL' if analysis.get('urgency') == 'IMMEDIATE' else 'HIGH'
                }

        return None

    async def monitor_all_active_tokens(self) -> List[Dict]:
        """
        Monitor all tokens with recent activity
        """
        try:
            with self.conn.cursor() as cur:
                # Get most active tokens in last 30 min
                cur.execute("""
                    SELECT DISTINCT token
                    FROM (
                        SELECT token FROM twitter_sentiment
                        WHERE scraped_at > NOW() - INTERVAL '30 minutes'
                        GROUP BY token
                        HAVING COUNT(*) > 10

                        UNION

                        SELECT token FROM crypto_ohlcv
                        WHERE timestamp > NOW() - INTERVAL '30 minutes'
                        AND volume > 0
                        GROUP BY token
                    ) active_tokens
                    LIMIT 20
                """)

                tokens = [row[0] for row in cur.fetchall()]

            # Monitor each token concurrently
            tasks = [self.monitor_token(token) for token in tokens]
            results = await asyncio.gather(*tasks)

            # Filter out None results
            alerts = [r for r in results if r is not None]

            # Log critical alerts
            for alert in alerts:
                if alert.get('alert_level') == 'CRITICAL':
                    logger.warning(f"🚨 CRITICAL ALERT for {alert['token']}: {alert['analysis']}")

            return alerts

        except Exception as e:
            logger.error(f"Error monitoring tokens: {e}")
            return []

    async def run_monitoring_cycle(self):
        """
        Run a single monitoring cycle (1-5 minutes)
        """
        start_time = time.time()
        logger.info("Starting tactical monitoring cycle...")

        try:
            alerts = await self.monitor_all_active_tokens()

            if alerts:
                # Store alerts in database for ai_trader to consume
                with self.conn.cursor() as cur:
                    for alert in alerts:
                        cur.execute("""
                            INSERT INTO tactical_alerts
                            (token, alert_type, urgency, confidence, signals, recommendation, created_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """, (
                            alert['token'],
                            alert['analysis'].get('key_signal'),
                            alert['analysis'].get('urgency'),
                            alert['analysis'].get('confidence'),
                            json.dumps(alert['signals']),
                            alert['analysis'].get('recommended_action'),
                            alert['timestamp']
                        ))
                    self.conn.commit()

                logger.info(f"Generated {len(alerts)} tactical alerts")
            else:
                logger.info("No significant signals detected")

            elapsed = time.time() - start_time
            logger.info(f"Monitoring cycle completed in {elapsed:.2f} seconds")

        except Exception as e:
            logger.error(f"Monitoring cycle failed: {e}")
            self.conn.rollback()

    async def run_forever(self, interval_minutes: int = 2):
        """
        Run tactical monitoring continuously
        Default 2-minute cycles for balance between speed and cost
        """
        logger.info(f"Starting tactical monitor with {interval_minutes}-minute intervals")

        while True:
            try:
                await self.run_monitoring_cycle()
                await asyncio.sleep(interval_minutes * 60)
            except KeyboardInterrupt:
                logger.info("Tactical monitoring stopped by user")
                break
            except Exception as e:
                logger.error(f"Unexpected error in monitoring loop: {e}")
                await asyncio.sleep(60)  # Wait 1 minute before retry

        if self.conn:
            self.conn.close()


async def main():
    """Main entry point for tactical monitoring"""
    monitor = TacticalMonitor()

    # Create alerts table if it doesn't exist
    with monitor.conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tactical_alerts (
                id SERIAL PRIMARY KEY,
                token VARCHAR(20),
                alert_type VARCHAR(50),
                urgency VARCHAR(20),
                confidence INTEGER,
                signals JSONB,
                recommendation VARCHAR(50),
                created_at TIMESTAMP,
                consumed_at TIMESTAMP DEFAULT NULL
            )
        """)

        # Create indexes separately (PostgreSQL syntax)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_tactical_alerts_token ON tactical_alerts (token)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_tactical_alerts_created ON tactical_alerts (created_at)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_tactical_alerts_consumed ON tactical_alerts (consumed_at)")

        monitor.conn.commit()

    # Run monitoring
    await monitor.run_forever(interval_minutes=2)


if __name__ == "__main__":
    asyncio.run(main())