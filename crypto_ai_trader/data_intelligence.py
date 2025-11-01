"""
Data Intelligence Module - Dynamic Token Discovery & Real Data Access
Provides smart data aggregation with AI-directed exploration capabilities
"""

import psycopg2
import psycopg2.extras
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import json
import numpy as np
from collections import defaultdict

class DataIntelligence:
    """
    Smart data aggregation with dynamic token discovery
    and AI-directed query capabilities
    """

    def __init__(self, db_config: Dict):
        """Initialize with database configuration"""
        self.db_config = db_config
        self.conn = None
        self.connect()

    def connect(self):
        """Establish database connection"""
        try:
            self.conn = psycopg2.connect(
                host=self.db_config['host'],
                port=self.db_config['port'],
                database=self.db_config['database'],
                user=self.db_config['user'],
                password=self.db_config['password']
            )
            print("[DataIntelligence] Connected to database")
        except Exception as e:
            print(f"[ERROR] Database connection failed: {e}")
            raise

    def discover_active_tokens(self, min_activity_hours: int = 24) -> List[str]:
        """
        Dynamically discover all tokens with recent activity
        Returns tokens that have BOTH sentiment data AND price data
        """
        try:
            with self.conn.cursor() as cursor:
                # Find tokens with recent Twitter activity
                cursor.execute("""
                    SELECT DISTINCT token
                    FROM twitter_sentiment
                    WHERE scraped_at > NOW() - INTERVAL '%s hours'
                    AND token IS NOT NULL
                    ORDER BY token
                """, (min_activity_hours,))
                twitter_tokens = {row[0] for row in cursor.fetchall()}

                # Find tokens with recent price data
                cursor.execute("""
                    SELECT DISTINCT token
                    FROM crypto_ohlcv
                    WHERE timestamp > NOW() - INTERVAL '%s hours'
                    AND token IS NOT NULL
                    ORDER BY token
                """, (min_activity_hours,))
                price_tokens = {row[0] for row in cursor.fetchall()}

                # Only return tokens with BOTH sentiment AND prices
                active_tokens = list(twitter_tokens & price_tokens)

                print(f"[Discovery] Found {len(active_tokens)} active tokens:")
                print(f"  Twitter data: {len(twitter_tokens)} tokens")
                print(f"  Price data: {len(price_tokens)} tokens")
                print(f"  Tradeable (both): {len(active_tokens)} tokens")

                # Also check for new tokens (appeared in last hour)
                cursor.execute("""
                    SELECT DISTINCT token, MIN(scraped_at) as first_seen
                    FROM twitter_sentiment
                    WHERE scraped_at > NOW() - INTERVAL '1 hour'
                    GROUP BY token
                    HAVING MIN(scraped_at) > NOW() - INTERVAL '1 hour'
                """)
                new_tokens = cursor.fetchall()
                if new_tokens:
                    print(f"[ALERT] New tokens detected: {[t[0] for t in new_tokens]}")

                return active_tokens

        except Exception as e:
            print(f"[ERROR] Token discovery failed: {e}")
            return []

    def get_current_price(self, token: str) -> Optional[float]:
        """
        Get REAL current price from crypto_ohlcv table
        Falls back to last known good price if very recent data unavailable
        """
        try:
            with self.conn.cursor() as cursor:
                # Get most recent price (within 15 minutes ideally)
                cursor.execute("""
                    SELECT close, timestamp
                    FROM crypto_ohlcv
                    WHERE token = %s
                    ORDER BY timestamp DESC
                    LIMIT 1
                """, (token,))

                result = cursor.fetchone()
                if result:
                    price, timestamp = result
                    return float(price)
                else:
                    print(f"[ERROR] No price data found for {token}")
                    return None

        except Exception as e:
            print(f"[ERROR] Price fetch failed for {token}: {e}")
            return None

    def get_price_history(self, token: str, hours: int = 24) -> Dict:
        """Get price history with calculated metrics"""
        try:
            with self.conn.cursor() as cursor:
                cursor.execute("""
                    SELECT timestamp, open, high, low, close, volume
                    FROM crypto_ohlcv
                    WHERE token = %s
                    AND timestamp > NOW() - INTERVAL '%s hours'
                    ORDER BY timestamp DESC
                """, (token, hours))

                rows = cursor.fetchall()
                if not rows:
                    return {}

                prices = [float(row[4]) for row in rows]
                volumes = [float(row[5]) for row in rows]

                current_price = prices[0]
                price_24h_ago = prices[-1] if len(prices) > 1 else current_price

                return {
                    'current_price': current_price,
                    'price_24h_ago': price_24h_ago,
                    'price_change_24h': ((current_price - price_24h_ago) / price_24h_ago * 100) if price_24h_ago > 0 else 0,
                    'high_24h': max(float(row[2]) for row in rows),
                    'low_24h': min(float(row[3]) for row in rows),
                    'volume_24h': sum(volumes),
                    'avg_volume': np.mean(volumes) if volumes else 0,
                    'volatility': np.std(prices) / np.mean(prices) * 100 if len(prices) > 1 else 0,
                    'price_points': len(rows)
                }
        except Exception as e:
            print(f"[ERROR] Price history failed for {token}: {e}")
            return {}

    def get_sentiment_summary(self, token: str, hours: int = 6) -> Dict:
        """Get Twitter sentiment summary with velocity metrics"""
        try:
            with self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                # Get aggregated sentiment
                cursor.execute("""
                    SELECT
                        COUNT(*) as tweet_count,
                        AVG(sentiment_score) as avg_sentiment,
                        MAX(sentiment_score) as max_sentiment,
                        MIN(sentiment_score) as min_sentiment,
                        AVG(weighted_score) as avg_weighted,
                        MAX(volume_spike) as max_volume_spike,
                        COUNT(DISTINCT author_username) as unique_authors,
                        COUNT(*) FILTER (WHERE is_whale = true) as whale_tweets,
                        COUNT(*) FILTER (WHERE bot_probability < 0.3) as quality_tweets,
                        AVG(sentiment_velocity) as avg_velocity,
                        MAX(momentum_score) as max_momentum
                    FROM twitter_sentiment
                    WHERE token = %s
                    AND scraped_at > NOW() - INTERVAL '%s hours'
                """, (token, hours))

                result = cursor.fetchone()
                if not result or result['tweet_count'] == 0:
                    return {'tweet_count': 0, 'has_data': False}

                return {
                    'tweet_count': result['tweet_count'],
                    'avg_sentiment': float(result['avg_sentiment']) if result['avg_sentiment'] else 0,
                    'max_sentiment': float(result['max_sentiment']) if result['max_sentiment'] else 0,
                    'min_sentiment': float(result['min_sentiment']) if result['min_sentiment'] else 0,
                    'avg_weighted': float(result['avg_weighted']) if result['avg_weighted'] else 0,
                    'max_volume_spike': float(result['max_volume_spike']) if result['max_volume_spike'] else 0,
                    'unique_authors': result['unique_authors'],
                    'whale_tweets': result['whale_tweets'],
                    'quality_tweets': result['quality_tweets'],
                    'sentiment_velocity': float(result['avg_velocity']) if result['avg_velocity'] else 0,
                    'momentum_score': float(result['max_momentum']) if result['max_momentum'] else 0,
                    'has_data': True
                }
        except Exception as e:
            print(f"[ERROR] Sentiment summary failed for {token}: {e}")
            return {'tweet_count': 0, 'has_data': False}

    def get_market_metrics(self, token: str) -> Dict:
        """Get advanced market metrics: order book, funding, OI, liquidations"""
        metrics = {}

        try:
            with self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                # Order book depth (latest)
                cursor.execute("""
                    SELECT best_bid, best_ask, bid_ask_spread, order_imbalance,
                           bid_liquidity_1pct, ask_liquidity_1pct
                    FROM order_book_depth
                    WHERE token = %s
                    ORDER BY timestamp DESC
                    LIMIT 1
                """, (token,))

                order_book = cursor.fetchone()
                if order_book:
                    metrics['order_book'] = {
                        'spread': float(order_book['bid_ask_spread']) if order_book['bid_ask_spread'] else 0,
                        'imbalance': float(order_book['order_imbalance']) if order_book['order_imbalance'] else 0,
                        'bid_liquidity': float(order_book['bid_liquidity_1pct']) if order_book['bid_liquidity_1pct'] else 0,
                        'ask_liquidity': float(order_book['ask_liquidity_1pct']) if order_book['ask_liquidity_1pct'] else 0
                    }

                # Funding rates (latest)
                cursor.execute("""
                    SELECT funding_rate
                    FROM funding_rates
                    WHERE token = %s
                    ORDER BY scraped_at DESC
                    LIMIT 1
                """, (token,))

                funding = cursor.fetchone()
                if funding:
                    metrics['funding_rate'] = float(funding['funding_rate']) if funding['funding_rate'] else 0

                # Open interest change
                cursor.execute("""
                    SELECT open_interest_usd
                    FROM open_interest
                    WHERE token = %s
                    ORDER BY timestamp DESC
                    LIMIT 2
                """, (token,))

                oi_data = cursor.fetchall()
                if len(oi_data) >= 2:
                    current_oi = float(oi_data[0]['open_interest_usd'])
                    previous_oi = float(oi_data[1]['open_interest_usd'])
                    metrics['oi_change_pct'] = ((current_oi - previous_oi) / previous_oi * 100) if previous_oi > 0 else 0
                    metrics['open_interest_usd'] = current_oi

                # Recent liquidations
                cursor.execute("""
                    SELECT COUNT(*) as liq_count,
                           SUM(liquidation_value) as total_liquidated
                    FROM liquidations
                    WHERE token = %s
                    AND timestamp > NOW() - INTERVAL '1 hour'
                """, (token,))

                liquidations = cursor.fetchone()
                if liquidations:
                    metrics['liquidations_1h'] = {
                        'count': liquidations['liq_count'] or 0,
                        'value': float(liquidations['total_liquidated']) if liquidations['total_liquidated'] else 0
                    }

        except Exception as e:
            print(f"[ERROR] Market metrics failed for {token}: {e}")

        return metrics

    def get_quick_summary(self, token: str) -> Dict:
        """
        Get lightweight summary for initial AI screening
        This is what AI sees first before requesting deep dives
        """
        summary = {
            'token': token,
            'timestamp': datetime.now().isoformat()
        }

        # Get current price
        price = self.get_current_price(token)
        if not price:
            return None  # Can't trade without price
        summary['price'] = price

        # Get basic metrics
        with self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
            # Quick sentiment check (last hour)
            cursor.execute("""
                SELECT COUNT(*) as tweets_1h,
                       AVG(sentiment_score) as sentiment_1h,
                       MAX(volume_spike) as max_spike_1h
                FROM twitter_sentiment
                WHERE token = %s AND scraped_at > NOW() - INTERVAL '1 hour'
            """, (token,))

            sentiment = cursor.fetchone()
            if sentiment and sentiment['tweets_1h'] > 0:
                summary['tweets_1h'] = sentiment['tweets_1h']
                summary['sentiment_1h'] = float(sentiment['sentiment_1h']) if sentiment['sentiment_1h'] else 0
                summary['volume_spike'] = float(sentiment['max_spike_1h']) if sentiment['max_spike_1h'] else 0
            else:
                summary['tweets_1h'] = 0
                summary['sentiment_1h'] = 0
                summary['volume_spike'] = 0

            # Price change (if available)
            cursor.execute("""
                SELECT close
                FROM crypto_ohlcv
                WHERE token = %s AND timestamp < NOW() - INTERVAL '1 hour'
                ORDER BY timestamp DESC
                LIMIT 1
            """, (token,))

            old_price = cursor.fetchone()
            if old_price:
                summary['price_change_1h'] = ((price - float(old_price['close'])) / float(old_price['close']) * 100)
            else:
                summary['price_change_1h'] = 0

        return summary

    def execute_ai_query(self, query: str) -> Any:
        """
        Execute custom SQL queries requested by AI
        This allows AI to explore data dynamically

        IMPORTANT: Only allows SELECT queries for safety
        """
        if not query.strip().upper().startswith('SELECT'):
            print("[SECURITY] Blocked non-SELECT query")
            return None

        try:
            with self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                cursor.execute(query)
                results = cursor.fetchall()
                # Convert to list of dicts for easier AI processing
                return [dict(row) for row in results]
        except Exception as e:
            print(f"[ERROR] AI query failed: {e}")
            return None

    def get_fear_greed_index(self) -> Optional[Dict]:
        """Get latest Fear & Greed index value"""
        try:
            with self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                cursor.execute("""
                    SELECT value, classification, timestamp
                    FROM fear_greed_index
                    ORDER BY timestamp DESC
                    LIMIT 1
                """)
                result = cursor.fetchone()
                if result:
                    return {
                        'value': result['value'],
                        'classification': result['classification'],
                        'timestamp': result['timestamp'].isoformat()
                    }
        except Exception as e:
            print(f"[ERROR] Fear & Greed fetch failed: {e}")
        return None

    def get_whale_movements(self, hours: int = 3) -> List[Dict]:
        """Get recent whale movements across all tokens"""
        try:
            with self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                cursor.execute("""
                    SELECT token, flow_type, SUM(usd_value) as total_usd,
                           COUNT(*) as transaction_count
                    FROM exchange_flows
                    WHERE timestamp > NOW() - INTERVAL '%s hours'
                    AND usd_value > 100000
                    GROUP BY token, flow_type
                    HAVING SUM(usd_value) > 500000
                    ORDER BY total_usd DESC
                """, (hours,))

                flows = []
                for row in cursor.fetchall():
                    flows.append({
                        'token': row['token'],
                        'flow_type': row['flow_type'],
                        'total_usd': float(row['total_usd']),
                        'transactions': row['transaction_count']
                    })
                return flows
        except Exception as e:
            print(f"[ERROR] Whale movements fetch failed: {e}")
            return []

    def get_trending_tokens(self, min_spike: float = 2.0) -> List[Dict]:
        """
        Get tokens with unusual activity patterns
        These are potential opportunities the AI should investigate
        """
        trending = []
        try:
            with self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                # Find tokens with volume spikes
                cursor.execute("""
                    SELECT token,
                           MAX(volume_spike) as max_spike,
                           AVG(sentiment_score) as avg_sentiment,
                           COUNT(*) as tweet_count
                    FROM twitter_sentiment
                    WHERE scraped_at > NOW() - INTERVAL '1 hour'
                    GROUP BY token
                    HAVING MAX(volume_spike) >= %s
                    ORDER BY max_spike DESC
                    LIMIT 10
                """, (min_spike,))

                for row in cursor.fetchall():
                    trending.append({
                        'token': row['token'],
                        'volume_spike': float(row['max_spike']),
                        'sentiment': float(row['avg_sentiment']) if row['avg_sentiment'] else 0,
                        'tweets': row['tweet_count'],
                        'reason': 'volume_spike'
                    })

                # Find tokens with extreme sentiment
                cursor.execute("""
                    SELECT token,
                           AVG(sentiment_score) as avg_sentiment,
                           COUNT(*) as tweet_count
                    FROM twitter_sentiment
                    WHERE scraped_at > NOW() - INTERVAL '1 hour'
                    AND bot_probability < 0.3
                    GROUP BY token
                    HAVING AVG(sentiment_score) > 0.5 OR AVG(sentiment_score) < -0.3
                    ORDER BY ABS(AVG(sentiment_score)) DESC
                    LIMIT 5
                """)

                for row in cursor.fetchall():
                    if row['token'] not in [t['token'] for t in trending]:
                        trending.append({
                            'token': row['token'],
                            'volume_spike': 0,
                            'sentiment': float(row['avg_sentiment']),
                            'tweets': row['tweet_count'],
                            'reason': 'extreme_sentiment'
                        })

        except Exception as e:
            print(f"[ERROR] Trending tokens fetch failed: {e}")

        return trending

    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
            print("[DataIntelligence] Database connection closed")