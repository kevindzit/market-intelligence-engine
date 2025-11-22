"""
Data Intelligence Module - Dynamic Token Discovery & Real Data Access
Provides smart data aggregation with AI-directed exploration capabilities
"""

import psycopg2
import psycopg2.extras
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any, Iterable
import json
import numpy as np
from collections import defaultdict

# ============================================================================
# OVERFITTING PREVENTION CONSTANTS - Historical Pattern Matching
# ============================================================================

# Minimum pattern samples required for different confidence levels
MIN_PATTERNS_HIGH_CONFIDENCE = 50   # For 80%+ confidence predictions
MIN_PATTERNS_MEDIUM_CONFIDENCE = 30  # For 60-80% confidence predictions
MIN_PATTERNS_LOW_CONFIDENCE = 15     # For <60% confidence predictions

# Historical lookback window (longer = more data, less regime-specific overfitting)
DEFAULT_PATTERN_LOOKBACK_DAYS = 90  # Increased from 30 to capture multiple market cycles

# Confidence ceiling based on sample size (prevents overconfidence)
MAX_CONFIDENCE_WITH_50_PATTERNS = 0.80   # Even with 50 patterns, cap at 80%
MAX_CONFIDENCE_WITH_100_PATTERNS = 0.90  # With 100+ patterns, cap at 90%
ABSOLUTE_MAX_CONFIDENCE = 0.95           # Never exceed 95% confidence

# Statistical significance thresholds
MIN_WIN_RATE_FOR_BULLISH = 65   # Need 65%+ win rate for bullish signal
MIN_WIN_RATE_FOR_BEARISH = 35   # Below 35% win rate = bearish signal

# Correlation analysis - sample size validation
MIN_CORRELATION_DATA_POINTS_RELIABLE = 100   # Need 100+ data points for reliable correlation
MIN_CORRELATION_DATA_POINTS_MINIMUM = 30     # Absolute minimum 30 data points

# Default freshness queries (in minutes) for critical feeds
FEED_FRESHNESS_QUERIES: Dict[str, str] = {
    'crypto_ohlcv': "SELECT MAX(timestamp) FROM crypto_ohlcv",
    'twitter_sentiment': "SELECT MAX(scraped_at) FROM twitter_sentiment",
    'order_book_depth': "SELECT MAX(timestamp) FROM order_book_depth",
    'liquidations': "SELECT MAX(timestamp) FROM liquidations",
    'open_interest': "SELECT MAX(timestamp) FROM open_interest",
    'news_articles': "SELECT MAX(published_at) FROM news_articles",
}

SIGNAL_CONFIDENCE_MAP = {
    'STRONG BUY': 0.9,
    'BUY': 0.8,
    'SELL': 0.75,
    'PUMP WARNING': 0.7,
    'HOLD': 0.6,
}

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
                    WHERE scraped_at > NOW() - INTERVAL '1 hour' * %s
                    AND token IS NOT NULL
                    ORDER BY token
                """, (min_activity_hours,))
                twitter_tokens = {row[0] for row in cursor.fetchall()}

                # Find tokens with recent price data
                cursor.execute("""
                    SELECT DISTINCT token
                    FROM crypto_ohlcv
                    WHERE timestamp > NOW() - INTERVAL '1 hour' * %s
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

    def check_liquidity(self, token: str, min_volume_usd: float = 10_000_000) -> bool:
        """
        Check if token has sufficient liquidity (min $10M daily volume)
        Prevents trading illiquid tokens with massive slippage
        """
        try:
            with self.conn.cursor() as cursor:
                # Get 24h volume in token units and average price
                cursor.execute("""
                    SELECT
                        SUM(volume) as total_volume,
                        AVG(close) as avg_price
                    FROM crypto_ohlcv
                    WHERE token = %s
                    AND timestamp > NOW() - INTERVAL '24 hours'
                """, (token,))

                result = cursor.fetchone()

                if result and result[0] and result[1]:
                    total_volume = float(result[0])
                    avg_price = float(result[1])
                    volume_usd = total_volume * avg_price

                    if volume_usd < min_volume_usd:
                        print(f"⚠️ {token} LOW LIQUIDITY: ${volume_usd:,.0f}/day (need ${min_volume_usd:,.0f}+)")
                        return False

                    return True

                # No volume data
                print(f"⚠️ {token} NO LIQUIDITY DATA")
                return False

        except Exception as e:
            print(f"[ERROR] Liquidity check failed for {token}: {e}")
            return False

    def get_price_history(self, token: str, hours: int = 24) -> Dict:
        """Get price history with calculated metrics"""
        try:
            with self.conn.cursor() as cursor:
                cursor.execute("""
                    SELECT timestamp, open, high, low, close, volume
                    FROM crypto_ohlcv
                    WHERE token = %s
                    AND timestamp > NOW() - INTERVAL '1 hour' * %s
                    ORDER BY timestamp DESC
                """, (token, hours))

                rows = cursor.fetchall()
                if not rows:
                    return {'has_data': False}

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
                    'price_points': len(rows),
                    'has_data': True,
                }
        except Exception as e:
            print(f"[ERROR] Price history failed for {token}: {e}")
            return {'has_data': False}

    def get_token_data_freshness(self, token: str) -> Dict[str, Optional[float]]:
        """Return age (in minutes) of recent price and sentiment data."""
        def _minutes_since(ts: Optional[datetime]) -> Optional[float]:
            if not ts:
                return None
            if ts.tzinfo:
                now_utc = datetime.now(timezone.utc)
                delta = now_utc - ts.astimezone(timezone.utc)
            else:
                now_utc = datetime.utcnow()
                delta = now_utc - ts
            return max(delta.total_seconds() / 60.0, 0.0)

        freshness = {
            'price_minutes': None,
            'sentiment_minutes': None,
        }

        try:
            with self.conn.cursor() as cursor:
                cursor.execute(
                    "SELECT MAX(timestamp) FROM crypto_ohlcv WHERE token = %s",
                    (token,),
                )
                price_ts = cursor.fetchone()[0]
                freshness['price_minutes'] = _minutes_since(price_ts)

                cursor.execute(
                    "SELECT MAX(scraped_at) FROM twitter_sentiment WHERE token = %s",
                    (token,),
                )
                sentiment_ts = cursor.fetchone()[0]
                freshness['sentiment_minutes'] = _minutes_since(sentiment_ts)

        except Exception as e:
            print(f"[ERROR] Data freshness check failed for {token}: {e}")

        return freshness

    def get_volume_profile(self, token: str, hours: int = 24) -> Dict:
        """Aggregate volume metrics with recent-vs-baseline comparison."""
        try:
            with self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                cursor.execute("""
                    SELECT
                        SUM(volume) AS total_volume,
                        AVG(volume) AS avg_volume,
                        MAX(volume) AS max_volume,
                        MIN(volume) AS min_volume,
                        COUNT(*) AS candles,
                        AVG(close) AS avg_price
                    FROM crypto_ohlcv
                    WHERE token = %s
                      AND timestamp >= NOW() - INTERVAL '1 hour' * %s
                """, (token, hours))

                stats = cursor.fetchone()
                if not stats or not stats['candles']:
                    return {'has_data': False}

                recent_window = max(1, min(6, (hours // 4) or 1))
                cursor.execute("""
                    SELECT
                        AVG(volume) AS avg_volume,
                        SUM(volume) AS total_volume,
                        COUNT(*) AS candles
                    FROM crypto_ohlcv
                    WHERE token = %s
                      AND timestamp >= NOW() - INTERVAL '1 hour' * %s
                """, (token, recent_window))

                recent = cursor.fetchone() or {}

                avg_volume = float(stats['avg_volume'] or 0)
                total_volume = float(stats['total_volume'] or 0)
                recent_avg = float(recent.get('avg_volume') or 0)
                volume_ratio = (recent_avg / avg_volume) if avg_volume else 1.0
                avg_price = float(stats['avg_price'] or 0)
                total_volume_usd = total_volume * avg_price if avg_price else 0

                return {
                    'has_data': True,
                    'window_hours': hours,
                    'candles': int(stats['candles']),
                    'total_volume': total_volume,
                    'avg_volume': avg_volume,
                    'max_volume': float(stats['max_volume'] or 0),
                    'min_volume': float(stats['min_volume'] or 0),
                    'avg_price': avg_price,
                    'total_volume_usd': total_volume_usd,
                    'recent_window_hours': recent_window,
                    'recent_avg_volume': recent_avg,
                    'volume_ratio': volume_ratio,
                }
        except Exception as e:
            print(f"[ERROR] Volume profile failed for {token}: {e}")
            return {'has_data': False}

    def get_signal_candidates(self, limit: int = 15) -> List[Dict[str, Any]]:
        """
        Surface tokens with meaningful movements (social, volume, price).
        """
        candidates: Dict[str, Dict[str, Any]] = {}

        def _ensure_entry(token: str) -> Dict[str, Any]:
            entry = candidates.get(token)
            if not entry:
                entry = {'token': token, 'reasons': [], 'confidence': 0.6, 'payload': {}}
                candidates[token] = entry
            return entry

        try:
            with self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                cursor.execute(
                    """
                    SELECT token, signal, volume_signal, quality_sentiment,
                           high_impact_tweets, signal_time
                    FROM twitter_trading_signals
                    ORDER BY signal_time DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
                for row in cursor.fetchall():
                    token = row['token']
                    entry = _ensure_entry(token)
                    entry['reasons'].append(f"twitter_signal:{row.get('signal')}")
                    signal_name = (row.get('signal') or '').upper().strip()
                    confidence = SIGNAL_CONFIDENCE_MAP.get(signal_name, 0.65)
                    entry['confidence'] = max(entry['confidence'], confidence)
                    entry['payload']['twitter_signal'] = {
                        'label': row.get('signal'),
                        'volume_signal': row.get('volume_signal'),
                        'quality_sentiment': row.get('quality_sentiment'),
                        'high_impact_tweets': row.get('high_impact_tweets'),
                    }
        except Exception as e:
            print(f"[WARNING] twitter_trading_signals unavailable: {e}")

        try:
            with self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                cursor.execute(
                    """
                    SELECT token, max_spike, avg_sentiment, whale_count
                    FROM recent_volume_spikes
                    ORDER BY max_spike DESC NULLS LAST
                    LIMIT %s
                    """,
                    (limit,),
                )
                for row in cursor.fetchall():
                    token = row['token']
                    entry = _ensure_entry(token)
                    entry['reasons'].append("volume_spike")
                    spike = float(row.get('max_spike') or 0)
                    confidence = min(0.6 + max(spike - 2.0, 0) * 0.1, 0.85)
                    entry['confidence'] = max(entry['confidence'], confidence)
                    entry['payload']['volume_spike'] = {
                        'ratio': spike,
                        'avg_sentiment': row.get('avg_sentiment'),
                        'whale_count': row.get('whale_count'),
                    }
        except Exception as e:
            print(f"[WARNING] recent_volume_spikes unavailable: {e}")

        sorted_candidates = sorted(
            candidates.values(),
            key=lambda item: item.get('confidence', 0),
            reverse=True,
        )
        return sorted_candidates[:limit]

    def get_feed_freshness(self, feeds: Optional[Iterable[str]] = None) -> Dict[str, Optional[float]]:
        """
        Return age in minutes for each requested feed (table).
        """
        def _minutes_since(ts: Optional[datetime]) -> Optional[float]:
            if not ts:
                return None
            if ts.tzinfo:
                delta = datetime.now(timezone.utc) - ts.astimezone(timezone.utc)
            else:
                delta = datetime.utcnow() - ts
            return max(delta.total_seconds() / 60.0, 0.0)

        queries = FEED_FRESHNESS_QUERIES
        if feeds is not None:
            feeds = list(feeds)
            queries = {name: sql for name, sql in FEED_FRESHNESS_QUERIES.items() if name in feeds}

        freshness: Dict[str, Optional[float]] = {name: None for name in queries}
        if not queries:
            return freshness

        try:
            with self.conn.cursor() as cursor:
                for name, sql in queries.items():
                    try:
                        cursor.execute(sql)
                        ts = cursor.fetchone()[0]
                        freshness[name] = _minutes_since(ts)
                    except Exception as feed_err:
                        print(f"[ERROR] Freshness query failed for {name}: {feed_err}")
                        freshness[name] = None
        except Exception as e:
            print(f"[ERROR] Feed freshness check failed: {e}")

        return freshness

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
                    AND scraped_at > NOW() - INTERVAL '1 hour' * %s
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
            'timestamp': datetime.now().isoformat(),
            'has_sentiment_data': False,
            'has_price_change': False,
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
                summary['has_sentiment_data'] = True
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
            if old_price and old_price['close']:
                summary['price_change_1h'] = ((price - float(old_price['close'])) / float(old_price['close']) * 100)
                summary['has_price_change'] = True
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
                    WHERE timestamp > NOW() - INTERVAL '1 hour' * %s
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

    def get_token_freshness(self, token: str, limits: Dict[str, int]) -> Dict[str, Optional[float]]:
        """
        Return per-feed age (minutes) for a given token. Only checks feeds provided in limits.
        """
        from datetime import timezone

        now = datetime.now(timezone.utc)
        ages: Dict[str, Optional[float]] = {}

        def _age(query: str, params: tuple) -> Optional[float]:
            with self.conn.cursor() as cursor:
                cursor.execute(query, params)
                row = cursor.fetchone()
                ts = row[0] if row else None
                if not ts:
                    return None
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                return max((now - ts).total_seconds() / 60, 0)

        for feed, _limit in limits.items():
            if feed == 'crypto_ohlcv':
                ages[feed] = _age(
                    "SELECT MAX(timestamp) FROM crypto_ohlcv WHERE token = %s",
                    (token,)
                )
            elif feed == 'twitter_sentiment':
                ages[feed] = _age(
                    "SELECT MAX(scraped_at) FROM twitter_sentiment WHERE token = %s",
                    (token,)
                )
            elif feed == 'order_book_depth':
                ages[feed] = _age(
                    "SELECT MAX(timestamp) FROM order_book_depth WHERE token = %s",
                    (token,)
                )
            elif feed == 'liquidations':
                ages[feed] = _age(
                    "SELECT MAX(timestamp) FROM liquidations WHERE token = %s",
                    (token,)
                )
            elif feed == 'open_interest':
                ages[feed] = _age(
                    "SELECT MAX(scraped_at) FROM open_interest WHERE token = %s",
                    (token,)
                )
            elif feed == 'news_articles':
                ages[feed] = _age(
                    "SELECT MAX(scraped_at) FROM news_articles WHERE token = %s",
                    (token,)
                )
        return ages

    def analyze_sentiment_timing(self, token: str) -> Dict:
        """
        Analyze sentiment timing patterns for optimal entry/exit
        Research shows:
        - Negative sentiment → immediate impact (trade within 5 min)
        - Positive sentiment → delayed impact (24-48 hour lag)
        - Reply/quote velocity → 74% accurate pump detection
        """
        try:
            with self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                # Get sentiment patterns over multiple timeframes
                cursor.execute("""
                    WITH sentiment_windows AS (
                        SELECT
                            -- Very recent (5 minutes)
                            AVG(CASE WHEN scraped_at > NOW() - INTERVAL '5 minutes'
                                THEN sentiment_score END) as sentiment_5min,
                            COUNT(CASE WHEN scraped_at > NOW() - INTERVAL '5 minutes'
                                THEN 1 END) as tweets_5min,

                            -- Recent (1 hour)
                            AVG(CASE WHEN scraped_at > NOW() - INTERVAL '1 hour'
                                THEN sentiment_score END) as sentiment_1h,
                            COUNT(CASE WHEN scraped_at > NOW() - INTERVAL '1 hour'
                                THEN 1 END) as tweets_1h,

                            -- Medium term (6 hours)
                            AVG(CASE WHEN scraped_at > NOW() - INTERVAL '6 hours'
                                THEN sentiment_score END) as sentiment_6h,
                            COUNT(CASE WHEN scraped_at > NOW() - INTERVAL '6 hours'
                                THEN 1 END) as tweets_6h,

                            -- Longer term (24 hours)
                            AVG(CASE WHEN scraped_at > NOW() - INTERVAL '24 hours'
                                THEN sentiment_score END) as sentiment_24h,
                            COUNT(CASE WHEN scraped_at > NOW() - INTERVAL '24 hours'
                                THEN 1 END) as tweets_24h,

                            -- Reply/quote metrics (pump detection)
                            AVG(CASE WHEN scraped_at > NOW() - INTERVAL '1 hour'
                                THEN reply_count + quote_count END) as engagement_1h,
                            MAX(CASE WHEN scraped_at > NOW() - INTERVAL '1 hour'
                                THEN reply_count + quote_count END) as max_engagement_1h,

                            -- Sentiment polarity
                            COUNT(CASE WHEN scraped_at > NOW() - INTERVAL '1 hour'
                                AND sentiment_score > 0.5 THEN 1 END) as positive_tweets_1h,
                            COUNT(CASE WHEN scraped_at > NOW() - INTERVAL '1 hour'
                                AND sentiment_score < -0.5 THEN 1 END) as negative_tweets_1h
                        FROM twitter_sentiment
                        WHERE token = %s
                        AND scraped_at > NOW() - INTERVAL '24 hours'
                        AND bot_probability < 0.3
                    )
                    SELECT *,
                        (sentiment_5min - sentiment_1h) as sentiment_acceleration,
                        (sentiment_1h - sentiment_6h) as sentiment_momentum,
                        (tweets_5min * 12.0 - tweets_1h) / NULLIF(tweets_1h, 0) as volume_acceleration
                    FROM sentiment_windows
                """, (token,))

                result = cursor.fetchone()

                if not result or result['tweets_1h'] == 0:
                    return {'has_signal': False, 'reason': 'Insufficient data'}

                # Calculate sentiment lag indicators
                timing_analysis = {
                    'token': token,
                    'timestamp': datetime.now().isoformat()
                }

                # Determine sentiment polarity and timing
                sentiment_current = result['sentiment_5min'] or result['sentiment_1h'] or 0
                sentiment_trend = result['sentiment_momentum'] or 0

                # Negative sentiment analysis (immediate action required)
                if sentiment_current < -0.3:
                    timing_analysis['signal'] = 'NEGATIVE_SPIKE'
                    timing_analysis['action_timing'] = 'IMMEDIATE'
                    timing_analysis['confidence'] = min(90, abs(sentiment_current) * 100)
                    timing_analysis['reasoning'] = 'Strong negative sentiment requires immediate action'
                    timing_analysis['time_to_act'] = '0-5 minutes'
                    timing_analysis['has_signal'] = True

                    # Check if cascade potential
                    if result['negative_tweets_1h'] > result['positive_tweets_1h'] * 2:
                        timing_analysis['cascade_risk'] = True
                        timing_analysis['confidence'] = min(95, timing_analysis['confidence'] + 10)

                # Positive sentiment analysis (delayed impact)
                elif sentiment_current > 0.5:
                    timing_analysis['signal'] = 'POSITIVE_MOMENTUM'
                    timing_analysis['action_timing'] = 'DELAYED'
                    timing_analysis['confidence'] = min(75, sentiment_current * 100)
                    timing_analysis['reasoning'] = 'Positive sentiment typically has 24-48h delayed impact'
                    timing_analysis['time_to_act'] = '24-48 hours'
                    timing_analysis['has_signal'] = True

                    # Check if sustained (more reliable)
                    if result['sentiment_6h'] > 0.3 and result['sentiment_24h'] > 0.2:
                        timing_analysis['sustained'] = True
                        timing_analysis['confidence'] = min(85, timing_analysis['confidence'] + 10)

                # Reply/quote velocity (pump detection)
                engagement_spike = (result['max_engagement_1h'] or 0) > (result['engagement_1h'] or 0) * 3
                if engagement_spike and result['tweets_1h'] > 20:
                    timing_analysis['pump_signal'] = True
                    timing_analysis['pump_confidence'] = 74  # Research-backed accuracy
                    timing_analysis['reasoning'] = 'High reply/quote velocity indicates potential pump'

                    if not timing_analysis.get('has_signal'):
                        timing_analysis['signal'] = 'ENGAGEMENT_SPIKE'
                        timing_analysis['action_timing'] = 'TACTICAL'
                        timing_analysis['confidence'] = 74
                        timing_analysis['time_to_act'] = '10-15 minutes'
                        timing_analysis['has_signal'] = True

                # Volume acceleration
                if result['volume_acceleration'] and result['volume_acceleration'] > 2:
                    timing_analysis['volume_surge'] = True
                    timing_analysis['volume_multiplier'] = result['volume_acceleration']

                    if timing_analysis.get('confidence'):
                        timing_analysis['confidence'] = min(95, timing_analysis['confidence'] + 5)

                # Add raw metrics
                timing_analysis['metrics'] = {
                    'sentiment_5min': result['sentiment_5min'],
                    'sentiment_1h': result['sentiment_1h'],
                    'sentiment_6h': result['sentiment_6h'],
                    'sentiment_24h': result['sentiment_24h'],
                    'sentiment_acceleration': result['sentiment_acceleration'],
                    'sentiment_momentum': result['sentiment_momentum'],
                    'tweets_1h': result['tweets_1h'],
                    'positive_ratio': result['positive_tweets_1h'] / max(1, result['tweets_1h']),
                    'negative_ratio': result['negative_tweets_1h'] / max(1, result['tweets_1h'])
                }

                # Default to no action if no clear signal
                if not timing_analysis.get('has_signal'):
                    timing_analysis['has_signal'] = False
                    timing_analysis['signal'] = 'NEUTRAL'
                    timing_analysis['action_timing'] = 'NONE'
                    timing_analysis['reasoning'] = 'No clear sentiment timing signal'

                return timing_analysis

        except Exception as e:
            print(f"[ERROR] Sentiment timing analysis failed for {token}: {e}")
            return {'has_signal': False, 'reason': 'Analysis error'}

    def get_sentiment_lag_recommendation(self, token: str) -> Dict:
        """
        Get specific trading recommendation based on sentiment lag patterns
        Simplified wrapper for AI consumption
        """
        timing = self.analyze_sentiment_timing(token)

        if not timing.get('has_signal'):
            return {
                'token': token,
                'recommendation': 'WAIT',
                'confidence': 0,
                'reasoning': timing.get('reason', 'No clear signal')
            }

        # Map timing signals to trading actions
        signal_map = {
            'NEGATIVE_SPIKE': {
                'recommendation': 'SELL_NOW' if timing.get('cascade_risk') else 'REDUCE_POSITION',
                'urgency': 'IMMEDIATE'
            },
            'POSITIVE_MOMENTUM': {
                'recommendation': 'PREPARE_BUY' if timing.get('sustained') else 'MONITOR',
                'urgency': 'LOW'  # Wait 24-48h
            },
            'ENGAGEMENT_SPIKE': {
                'recommendation': 'QUICK_SCALP' if timing.get('pump_signal') else 'MONITOR',
                'urgency': 'HIGH'
            }
        }

        action = signal_map.get(timing['signal'], {'recommendation': 'MONITOR', 'urgency': 'LOW'})

        return {
            'token': token,
            'recommendation': action['recommendation'],
            'urgency': action['urgency'],
            'confidence': timing.get('confidence', 50),
            'time_to_act': timing.get('time_to_act', 'Variable'),
            'reasoning': timing.get('reasoning', ''),
            'metrics': timing.get('metrics', {})
        }

    def get_liquidation_cascade_analysis(self, token: str) -> Dict:
        """
        Analyze liquidation cascade risk for a token

        Detects:
        - LONG_SQUEEZE: Overleveraged longs getting liquidated (bearish)
        - SHORT_SQUEEZE: Overleveraged shorts getting liquidated (bullish)
        - Cascade velocity: How fast liquidations are occurring
        - Critical zones: Price levels with high liquidation risk

        Returns:
        {
            'risk_score': 0-100,  # Higher = more extreme cascade risk
            'cascade_type': 'LONG_SQUEEZE' | 'SHORT_SQUEEZE' | 'NEUTRAL',
            'velocity': float,  # liquidations per minute
            'total_liquidated_1h': float,  # Total USD liquidated
            'recommendation': 'AVOID_LONG' | 'AVOID_SHORT' | 'OPPORTUNITY_LONG' | 'OPPORTUNITY_SHORT' | 'NEUTRAL',
            'confidence': 0-100
        }
        """
        try:
            with self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                # Get liquidation data for the last hour
                cursor.execute("""
                    WITH recent_liquidations AS (
                        SELECT
                            side,
                            liquidation_value,
                            timestamp,
                            EXTRACT(EPOCH FROM (NOW() - timestamp))/60 as minutes_ago
                        FROM liquidations
                        WHERE token = %s
                        AND timestamp > NOW() - INTERVAL '1 hour'
                        ORDER BY timestamp DESC
                    ),
                    liquidation_summary AS (
                        SELECT
                            COUNT(*) FILTER (WHERE side = 'LONG') as long_liq_count,
                            COUNT(*) FILTER (WHERE side = 'SHORT') as short_liq_count,
                            SUM(liquidation_value) FILTER (WHERE side = 'LONG') as long_liq_value,
                            SUM(liquidation_value) FILTER (WHERE side = 'SHORT') as short_liq_value,
                            COUNT(*) as total_count,
                            SUM(liquidation_value) as total_value,
                            COUNT(*) FILTER (WHERE minutes_ago < 5) as recent_5min_count,
                            SUM(liquidation_value) FILTER (WHERE minutes_ago < 5) as recent_5min_value
                        FROM recent_liquidations
                    )
                    SELECT * FROM liquidation_summary
                """, (token,))

                result = cursor.fetchone()

                if not result or result['total_count'] == 0:
                    return {
                        'risk_score': 0,
                        'cascade_type': 'NEUTRAL',
                        'velocity': 0,
                        'total_liquidated_1h': 0,
                        'recommendation': 'NEUTRAL',
                        'confidence': 0,
                        'reason': 'No recent liquidations'
                    }

                # Extract metrics
                long_liq_value = float(result['long_liq_value'] or 0)
                short_liq_value = float(result['short_liq_value'] or 0)
                total_value = float(result['total_value'] or 0)
                total_count = result['total_count']
                recent_5min_count = result['recent_5min_count'] or 0
                recent_5min_value = float(result['recent_5min_value'] or 0)

                # Calculate velocity (liquidations per minute)
                velocity = recent_5min_count / 5.0 if recent_5min_count > 0 else total_count / 60.0

                # Determine cascade type
                if long_liq_value > short_liq_value * 2:
                    cascade_type = 'LONG_SQUEEZE'
                    dominant_side_value = long_liq_value
                elif short_liq_value > long_liq_value * 2:
                    cascade_type = 'SHORT_SQUEEZE'
                    dominant_side_value = short_liq_value
                else:
                    cascade_type = 'NEUTRAL'
                    dominant_side_value = total_value

                # Calculate risk score (0-100)
                # Factors: velocity, total value, dominance ratio
                velocity_score = min(40, velocity * 8)  # Up to 40 points for velocity
                value_score = min(30, (dominant_side_value / 1_000_000) * 10)  # Up to 30 points for $1M+

                if cascade_type != 'NEUTRAL':
                    dominance_ratio = dominant_side_value / max(1, total_value - dominant_side_value)
                    dominance_score = min(30, dominance_ratio * 10)  # Up to 30 points
                else:
                    dominance_score = 0

                risk_score = min(100, velocity_score + value_score + dominance_score)

                # Generate recommendation
                confidence = risk_score

                if cascade_type == 'LONG_SQUEEZE':
                    if risk_score >= 70:
                        recommendation = 'AVOID_LONG'  # Extreme bearish cascade
                        reasoning = f"LONG cascade in progress (${long_liq_value:,.0f} liquidated, {velocity:.1f} liq/min)"
                    elif risk_score >= 50:
                        recommendation = 'OPPORTUNITY_SHORT'  # Cascade building
                        reasoning = f"LONG liquidations building momentum (${long_liq_value:,.0f})"
                    else:
                        recommendation = 'NEUTRAL'
                        reasoning = f"Moderate LONG liquidations (${long_liq_value:,.0f})"

                elif cascade_type == 'SHORT_SQUEEZE':
                    if risk_score >= 70:
                        recommendation = 'OPPORTUNITY_LONG'  # Extreme bullish cascade
                        reasoning = f"SHORT cascade in progress (${short_liq_value:,.0f} liquidated, {velocity:.1f} liq/min)"
                    elif risk_score >= 50:
                        recommendation = 'AVOID_SHORT'  # Cascade building
                        reasoning = f"SHORT liquidations building momentum (${short_liq_value:,.0f})"
                    else:
                        recommendation = 'NEUTRAL'
                        reasoning = f"Moderate SHORT liquidations (${short_liq_value:,.0f})"

                else:
                    recommendation = 'NEUTRAL'
                    reasoning = 'Balanced liquidations, no clear cascade direction'
                    confidence = max(30, 100 - risk_score)  # Low confidence for neutral

                # Check if cascade is exhausting (opportunity to fade)
                if risk_score >= 80 and velocity < 1:
                    reasoning += " | CASCADE EXHAUSTING - potential reversal"
                    if cascade_type == 'LONG_SQUEEZE':
                        recommendation = 'OPPORTUNITY_LONG'  # Buy the panic
                    elif cascade_type == 'SHORT_SQUEEZE':
                        recommendation = 'OPPORTUNITY_SHORT'  # Sell the euphoria

                return {
                    'token': token,
                    'risk_score': round(risk_score, 1),
                    'cascade_type': cascade_type,
                    'velocity': round(velocity, 2),
                    'total_liquidated_1h': round(total_value, 2),
                    'long_liquidated': round(long_liq_value, 2),
                    'short_liquidated': round(short_liq_value, 2),
                    'recommendation': recommendation,
                    'confidence': round(confidence, 1),
                    'reasoning': reasoning,
                    'liquidation_count': total_count,
                    'recent_5min_count': recent_5min_count
                }

        except Exception as e:
            print(f"[ERROR] Liquidation cascade analysis failed for {token}: {e}")
            return {
                'risk_score': 0,
                'cascade_type': 'NEUTRAL',
                'velocity': 0,
                'total_liquidated_1h': 0,
                'recommendation': 'NEUTRAL',
                'confidence': 0,
                'reason': f'Analysis error: {str(e)}'
            }

    def get_token_correlation(self, token1: str, token2: str, hours: int = 24) -> Optional[Dict]:
        """
        Calculate price correlation between two tokens over specified timeframe

        Returns: Dict with correlation data and sample size validation
        - correlation: Correlation coefficient (-1 to 1)
        - data_points: Number of matching time buckets used
        - reliable: True if enough data for reliable correlation
        - warning: Warning message if sample size is insufficient

        OVERFITTING PROTECTION:
        - Requires minimum 30 data points
        - Warns if < 100 data points (not fully reliable)
        - Returns None if insufficient data
        """
        try:
            with self.conn.cursor() as cursor:
                # Get aligned price data for both tokens WITH COUNT
                cursor.execute("""
                    WITH token1_prices AS (
                        SELECT
                            DATE_TRUNC('minute', timestamp) as time_bucket,
                            AVG(close) as price1
                        FROM crypto_ohlcv
                        WHERE token = %s
                        AND timestamp > NOW() - INTERVAL '1 hour' * %s
                        GROUP BY time_bucket
                    ),
                    token2_prices AS (
                        SELECT
                            DATE_TRUNC('minute', timestamp) as time_bucket,
                            AVG(close) as price2
                        FROM crypto_ohlcv
                        WHERE token = %s
                        AND timestamp > NOW() - INTERVAL '1 hour' * %s
                        GROUP BY time_bucket
                    )
                    SELECT
                        CORR(t1.price1, t2.price2) as correlation,
                        COUNT(*) as data_points
                    FROM token1_prices t1
                    INNER JOIN token2_prices t2 ON t1.time_bucket = t2.time_bucket
                    WHERE t1.price1 IS NOT NULL AND t2.price2 IS NOT NULL
                """, (token1, hours, token2, hours))

                result = cursor.fetchone()

                if not result or result[0] is None:
                    return None

                correlation = float(result[0])
                data_points = int(result[1])

                # === SAMPLE SIZE VALIDATION ===
                if data_points < MIN_CORRELATION_DATA_POINTS_MINIMUM:
                    # INSUFFICIENT DATA - Don't trust this correlation
                    print(f"[CORRELATION] {token1}-{token2}: Only {data_points} data points (need {MIN_CORRELATION_DATA_POINTS_MINIMUM}+) - REJECTED")
                    return None

                # Determine reliability
                reliable = data_points >= MIN_CORRELATION_DATA_POINTS_RELIABLE
                warning = None

                if not reliable:
                    warning = f"Low sample size: {data_points} data points (need {MIN_CORRELATION_DATA_POINTS_RELIABLE}+ for reliable correlation)"
                    print(f"[CORRELATION] {token1}-{token2}: {correlation:.3f} with {data_points} points - LIMITED DATA")
                else:
                    print(f"[CORRELATION] {token1}-{token2}: {correlation:.3f} with {data_points} points - RELIABLE")

                return {
                    'correlation': correlation,
                    'data_points': data_points,
                    'reliable': reliable,
                    'warning': warning
                }

        except Exception as e:
            print(f"[ERROR] Correlation calculation failed for {token1}-{token2}: {e}")
            return None

    def get_portfolio_correlation_risk(self, new_token: str, existing_tokens: List[str], hours: int = 24) -> Dict:
        """
        Calculate correlation risk when adding a new token to portfolio
        Returns correlation with each existing position and overall risk assessment

        OVERFITTING PROTECTION:
        - Now includes sample size validation
        - Warns if correlations based on insufficient data
        - Skips correlations with < 30 data points
        """
        if not existing_tokens:
            return {
                'risk_level': 'NONE',
                'max_correlation': 0,
                'correlations': {},
                'warning': None,
                'data_quality_warnings': []
            }

        correlations = {}
        max_correlation = 0
        data_quality_warnings = []
        min_data_points = float('inf')

        for existing_token in existing_tokens:
            corr_result = self.get_token_correlation(new_token, existing_token, hours)

            if corr_result is not None:
                corr_value = corr_result['correlation']
                data_points = corr_result['data_points']

                # Track correlation
                correlations[existing_token] = {
                    'correlation': round(corr_value, 3),
                    'data_points': data_points,
                    'reliable': corr_result['reliable']
                }

                max_correlation = max(max_correlation, abs(corr_value))
                min_data_points = min(min_data_points, data_points)

                # Add warning if unreliable
                if corr_result['warning']:
                    data_quality_warnings.append(f"{existing_token}: {corr_result['warning']}")

        # === SAMPLE SIZE VALIDATION ===
        if min_data_points < MIN_CORRELATION_DATA_POINTS_RELIABLE:
            data_quality_warnings.append(
                f"⚠️ CORRELATION DATA QUALITY: Minimum {min_data_points} data points across correlations (need {MIN_CORRELATION_DATA_POINTS_RELIABLE}+ for high confidence)"
            )

        # Assess risk level
        if max_correlation >= 0.85:
            risk_level = 'EXTREME'
            warning = f"Very high correlation with existing positions (max {max_correlation:.2f}). Concentrated risk!"
        elif max_correlation >= 0.70:
            risk_level = 'HIGH'
            warning = f"High correlation with existing positions (max {max_correlation:.2f}). Consider diversification."
        elif max_correlation >= 0.50:
            risk_level = 'MODERATE'
            warning = f"Moderate correlation (max {max_correlation:.2f}). Acceptable diversification."
        else:
            risk_level = 'LOW'
            warning = None

        return {
            'new_token': new_token,
            'risk_level': risk_level,
            'max_correlation': round(max_correlation, 3),
            'correlations': correlations,
            'warning': warning,
            'recommendation': 'BLOCK' if max_correlation >= 0.85 else 'ALLOW',
            'data_quality_warnings': data_quality_warnings,  # NEW - Shows sample size issues
            'min_data_points': int(min_data_points) if min_data_points != float('inf') else 0
        }

    def get_order_book_intelligence(self, token: str) -> Dict:
        """
        Analyze order book depth for optimal entry/exit timing

        Provides:
        - Wall detection (large orders that block price movement)
        - Liquidity quality (can you enter/exit without slippage?)
        - Order imbalance signals (buying/selling pressure)
        - Optimal entry timing based on spread and liquidity

        Returns actionable trading intelligence for AI decision making
        """
        try:
            with self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                # Get latest order book data
                cursor.execute("""
                    SELECT
                        best_bid, best_ask, bid_ask_spread,
                        bid_liquidity_1pct, ask_liquidity_1pct,
                        order_imbalance,
                        total_bid_volume, total_ask_volume,
                        timestamp
                    FROM order_book_depth
                    WHERE token = %s
                    ORDER BY timestamp DESC
                    LIMIT 1
                """, (token,))

                current = cursor.fetchone()

                if not current:
                    return {
                        'has_data': False,
                        'entry_quality': 'UNKNOWN',
                        'recommendation': 'NO_DATA',
                        'reason': 'No order book data available'
                    }

                # Get historical data for trend analysis (last 15 minutes)
                cursor.execute("""
                    SELECT
                        AVG(bid_ask_spread) as avg_spread,
                        STDDEV(bid_ask_spread) as spread_volatility,
                        AVG(order_imbalance) as avg_imbalance,
                        MAX(bid_liquidity_1pct) as max_bid_liquidity,
                        MAX(ask_liquidity_1pct) as max_ask_liquidity,
                        COUNT(*) as data_points
                    FROM order_book_depth
                    WHERE token = %s
                    AND timestamp > NOW() - INTERVAL '15 minutes'
                """, (token,))

                historical = cursor.fetchone()

                # Extract current metrics
                spread = float(current['bid_ask_spread']) if current['bid_ask_spread'] else 0
                bid_liquidity = float(current['bid_liquidity_1pct']) if current['bid_liquidity_1pct'] else 0
                ask_liquidity = float(current['ask_liquidity_1pct']) if current['ask_liquidity_1pct'] else 0
                imbalance = float(current['order_imbalance']) if current['order_imbalance'] else 0
                bid_volume = float(current['total_bid_volume']) if current['total_bid_volume'] else 0
                ask_volume = float(current['total_ask_volume']) if current['total_ask_volume'] else 0

                # Historical comparisons
                avg_spread = float(historical['avg_spread']) if historical and historical['avg_spread'] else spread
                spread_volatility = float(historical['spread_volatility']) if historical and historical['spread_volatility'] else 0

                # Initialize intelligence report
                intelligence = {
                    'token': token,
                    'timestamp': current['timestamp'].isoformat() if current['timestamp'] else datetime.now().isoformat(),
                    'has_data': True
                }

                # 1. SPREAD ANALYSIS - Is it cheap to enter?
                spread_pct = (spread / float(current['best_bid'])) * 100 if current['best_bid'] else 0

                if spread_pct < 0.05:
                    spread_quality = 'EXCELLENT'
                    spread_score = 100
                elif spread_pct < 0.1:
                    spread_quality = 'GOOD'
                    spread_score = 80
                elif spread_pct < 0.2:
                    spread_quality = 'FAIR'
                    spread_score = 60
                elif spread_pct < 0.5:
                    spread_quality = 'POOR'
                    spread_score = 30
                else:
                    spread_quality = 'TERRIBLE'
                    spread_score = 0

                intelligence['spread'] = {
                    'value': round(spread, 6),
                    'percentage': round(spread_pct, 3),
                    'quality': spread_quality,
                    'score': spread_score,
                    'vs_average': 'TIGHT' if spread < avg_spread * 0.8 else 'NORMAL' if spread < avg_spread * 1.2 else 'WIDE'
                }

                # 2. LIQUIDITY ANALYSIS - Can you get in/out without moving the market?
                # Calculate approximate slippage for a $10k trade
                typical_trade_size = 10000  # $10k
                price = float(current['best_bid']) if current['best_bid'] else 1

                if bid_liquidity > typical_trade_size * 2:
                    buy_liquidity = 'DEEP'
                    buy_slippage = 0.05  # Minimal slippage
                elif bid_liquidity > typical_trade_size:
                    buy_liquidity = 'GOOD'
                    buy_slippage = 0.1
                elif bid_liquidity > typical_trade_size * 0.5:
                    buy_liquidity = 'FAIR'
                    buy_slippage = 0.2
                else:
                    buy_liquidity = 'THIN'
                    buy_slippage = 0.5

                if ask_liquidity > typical_trade_size * 2:
                    sell_liquidity = 'DEEP'
                    sell_slippage = 0.05
                elif ask_liquidity > typical_trade_size:
                    sell_liquidity = 'GOOD'
                    sell_slippage = 0.1
                elif ask_liquidity > typical_trade_size * 0.5:
                    sell_liquidity = 'FAIR'
                    sell_slippage = 0.2
                else:
                    sell_liquidity = 'THIN'
                    sell_slippage = 0.5

                intelligence['liquidity'] = {
                    'bid_depth': round(bid_liquidity, 2),
                    'ask_depth': round(ask_liquidity, 2),
                    'buy_quality': buy_liquidity,
                    'sell_quality': sell_liquidity,
                    'estimated_buy_slippage': round(buy_slippage, 2),
                    'estimated_sell_slippage': round(sell_slippage, 2)
                }

                # 3. ORDER IMBALANCE - Who's winning, buyers or sellers?
                if abs(imbalance) < 0.1:
                    pressure = 'NEUTRAL'
                    pressure_signal = 'BALANCED'
                elif imbalance > 0.3:
                    pressure = 'STRONG_BUY'
                    pressure_signal = 'BUYERS_DOMINATING'
                elif imbalance > 0.1:
                    pressure = 'BUY'
                    pressure_signal = 'MORE_BUYERS'
                elif imbalance < -0.3:
                    pressure = 'STRONG_SELL'
                    pressure_signal = 'SELLERS_DOMINATING'
                else:
                    pressure = 'SELL'
                    pressure_signal = 'MORE_SELLERS'

                intelligence['pressure'] = {
                    'imbalance': round(imbalance, 3),
                    'direction': pressure,
                    'signal': pressure_signal,
                    'bid_volume': round(bid_volume, 2),
                    'ask_volume': round(ask_volume, 2)
                }

                # 4. WALL DETECTION - Are there big orders blocking movement?
                # If liquidity at 1% is huge compared to average, there's likely a wall
                wall_threshold = typical_trade_size * 10  # $100k+ is a wall

                walls = []
                if bid_liquidity > wall_threshold:
                    walls.append(f"BID_WALL (${bid_liquidity:,.0f} support below)")
                if ask_liquidity > wall_threshold:
                    walls.append(f"ASK_WALL (${ask_liquidity:,.0f} resistance above)")

                intelligence['walls'] = walls if walls else ['NONE']

                # 5. ENTRY QUALITY SCORE (0-100)
                entry_score = spread_score * 0.3  # 30% weight on spread

                # Liquidity score (30% weight)
                if buy_liquidity == 'DEEP':
                    entry_score += 30
                elif buy_liquidity == 'GOOD':
                    entry_score += 20
                elif buy_liquidity == 'FAIR':
                    entry_score += 10

                # Pressure alignment (20% weight) - buying into buy pressure is good
                if pressure in ['BUY', 'STRONG_BUY']:
                    entry_score += 20
                elif pressure == 'NEUTRAL':
                    entry_score += 10

                # Spread stability (20% weight) - volatile spreads = risky
                if spread_volatility and spread_volatility < avg_spread * 0.2:
                    entry_score += 20  # Very stable
                elif spread_volatility and spread_volatility < avg_spread * 0.5:
                    entry_score += 10  # Somewhat stable

                # Generate final recommendation
                if entry_score >= 80:
                    entry_quality = 'EXCELLENT'
                    recommendation = 'IDEAL_ENTRY'
                    reasoning = f"Tight spread ({spread_pct:.2f}%), deep liquidity, favorable conditions"
                elif entry_score >= 60:
                    entry_quality = 'GOOD'
                    recommendation = 'GOOD_ENTRY'
                    reasoning = f"Acceptable spread, adequate liquidity"
                elif entry_score >= 40:
                    entry_quality = 'FAIR'
                    recommendation = 'WAIT_BETTER'
                    reasoning = f"Wide spread or thin liquidity, wait for improvement"
                else:
                    entry_quality = 'POOR'
                    recommendation = 'AVOID_ENTRY'
                    reasoning = f"Poor conditions: wide spread ({spread_pct:.2f}%), thin liquidity"

                # Add wall warnings
                if 'ASK_WALL' in str(walls):
                    reasoning += " | Strong resistance above"
                if 'BID_WALL' in str(walls):
                    reasoning += " | Strong support below"

                intelligence['entry_quality'] = entry_quality
                intelligence['entry_score'] = round(entry_score, 1)
                intelligence['recommendation'] = recommendation
                intelligence['reasoning'] = reasoning

                # Add specific trading advice
                advice = []
                if spread_quality in ['EXCELLENT', 'GOOD'] and buy_liquidity in ['DEEP', 'GOOD']:
                    advice.append("Use MARKET order - liquidity is sufficient")
                else:
                    advice.append("Use LIMIT order - avoid slippage")

                if 'ASK_WALL' in str(walls):
                    advice.append(f"Set take-profit BELOW the wall at ${ask_liquidity:,.0f}")

                if pressure == 'STRONG_BUY' and entry_quality in ['EXCELLENT', 'GOOD']:
                    advice.append("Strong momentum - consider larger position")
                elif pressure == 'STRONG_SELL':
                    advice.append("Selling pressure - reduce position size or wait")

                intelligence['trading_advice'] = advice

                return intelligence

        except Exception as e:
            print(f"[ERROR] Order book intelligence failed for {token}: {e}")
            return {
                'has_data': False,
                'entry_quality': 'ERROR',
                'recommendation': 'NO_DATA',
                'reason': f'Analysis error: {str(e)}'
            }

    def find_similar_historical_patterns(self, token: str, lookback_days: int = DEFAULT_PATTERN_LOOKBACK_DAYS) -> Dict:
        """
        Find similar historical patterns and their outcomes
        Helps AI predict what's likely to happen based on past similar setups

        Matches patterns based on:
        - Price action similarity (% changes)
        - Sentiment patterns
        - Volume patterns
        - Market conditions (funding, liquidations)

        Returns what happened after similar patterns occurred

        OVERFITTING PROTECTION:
        - Default lookback increased to 90 days (captures multiple market cycles)
        - Requires 15-50 patterns depending on confidence level
        - Caps confidence based on sample size
        - Provides statistical warnings for low sample sizes
        """
        try:
            with self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                # Get current pattern metrics
                current_pattern = self.get_current_pattern_metrics(token)

                if not current_pattern['has_data']:
                    return {
                        'has_patterns': False,
                        'reason': 'Insufficient current data',
                        'prediction': None
                    }

                # Find similar historical patterns
                cursor.execute("""
                    WITH current_metrics AS (
                        -- Current 4-hour pattern
                        SELECT
                            %s::NUMERIC as current_price_change_4h,
                            %s::NUMERIC as current_sentiment,
                            %s::NUMERIC as current_volume_ratio,
                            %s::NUMERIC as current_funding
                    ),
                    historical_patterns AS (
                        -- Find all 4-hour periods in history
                        SELECT
                            timestamp as pattern_time,
                            -- Price pattern
                            (close - LAG(close, 48) OVER (ORDER BY timestamp)) /
                                NULLIF(LAG(close, 48) OVER (ORDER BY timestamp), 0) * 100 as price_change_4h,
                            -- Get price 24 hours later for outcome
                            LEAD(close, 288) OVER (ORDER BY timestamp) as price_24h_later,
                            close as pattern_price
                        FROM crypto_ohlcv
                        WHERE token = %s
                        AND timestamp < NOW() - INTERVAL '24 hours'
                        AND timestamp > NOW() - INTERVAL '1 day' * %s
                        AND timeframe = '5m'
                    ),
                    sentiment_patterns AS (
                        -- Get sentiment for each pattern period
                        SELECT
                            DATE_TRUNC('hour', scraped_at) as hour,
                            AVG(sentiment_score) as avg_sentiment,
                            COUNT(*) as tweet_volume
                        FROM twitter_sentiment
                        WHERE token = %s
                        AND scraped_at > NOW() - INTERVAL '1 day' * %s
                        GROUP BY hour
                    ),
                    pattern_matches AS (
                        -- Find patterns similar to current
                        SELECT
                            hp.pattern_time,
                            hp.pattern_price,
                            hp.price_24h_later,
                            hp.price_change_4h,
                            sp.avg_sentiment,
                            -- Calculate outcome
                            (hp.price_24h_later - hp.pattern_price) / NULLIF(hp.pattern_price, 0) * 100 as outcome_24h,
                            -- Similarity score (0-100)
                            100 - (
                                ABS(hp.price_change_4h - cm.current_price_change_4h) * 5 +
                                ABS(COALESCE(sp.avg_sentiment, 0) - cm.current_sentiment) * 50
                            ) as similarity_score
                        FROM historical_patterns hp
                        CROSS JOIN current_metrics cm
                        LEFT JOIN sentiment_patterns sp
                            ON DATE_TRUNC('hour', hp.pattern_time) = sp.hour
                        WHERE hp.price_24h_later IS NOT NULL
                        AND ABS(hp.price_change_4h - cm.current_price_change_4h) < 3  -- Within 3% price change
                    )
                    SELECT
                        COUNT(*) as pattern_count,
                        AVG(outcome_24h) as avg_outcome_24h,
                        STDDEV(outcome_24h) as outcome_volatility,
                        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY outcome_24h) as median_outcome,
                        MAX(outcome_24h) as best_outcome,
                        MIN(outcome_24h) as worst_outcome,
                        AVG(similarity_score) as avg_similarity,
                        -- Win rate (profitable outcomes)
                        COUNT(*) FILTER (WHERE outcome_24h > 0) * 100.0 / NULLIF(COUNT(*), 0) as win_rate,
                        -- Average win vs average loss
                        AVG(outcome_24h) FILTER (WHERE outcome_24h > 0) as avg_win,
                        ABS(AVG(outcome_24h) FILTER (WHERE outcome_24h < 0)) as avg_loss
                    FROM pattern_matches
                    WHERE similarity_score > 60  -- At least 60% similar
                """, (
                    current_pattern['price_change_4h'],
                    current_pattern['sentiment'],
                    current_pattern['volume_ratio'],
                    current_pattern.get('funding_rate', 0),
                    token, lookback_days,
                    token, lookback_days
                ))

                result = cursor.fetchone()

                if not result or result['pattern_count'] == 0:
                    return {
                        'has_patterns': False,
                        'reason': 'No similar historical patterns found',
                        'prediction': None
                    }

                pattern_count = result['pattern_count']
                avg_outcome = float(result['avg_outcome_24h']) if result['avg_outcome_24h'] else 0
                median_outcome = float(result['median_outcome']) if result['median_outcome'] else 0
                win_rate = float(result['win_rate']) if result['win_rate'] else 50
                avg_win = float(result['avg_win']) if result['avg_win'] else 0
                avg_loss = float(result['avg_loss']) if result['avg_loss'] else 0
                similarity = float(result['avg_similarity']) if result['avg_similarity'] else 0

                # ============================================================
                # OVERFITTING PROTECTION - Confidence Calculation
                # ============================================================

                # Initialize statistical warnings
                statistical_warnings = []

                # Step 1: Base confidence from sample size (prevents overconfidence)
                if pattern_count < MIN_PATTERNS_LOW_CONFIDENCE:
                    # INSUFFICIENT DATA - Very low confidence
                    base_confidence = 0.30  # Cap at 30%
                    statistical_warnings.append(
                        f"⚠️ VERY LOW SAMPLE SIZE: Only {pattern_count} patterns found (need {MIN_PATTERNS_LOW_CONFIDENCE}+ for reliable predictions)"
                    )
                elif pattern_count < MIN_PATTERNS_MEDIUM_CONFIDENCE:
                    # LOW DATA - Moderate confidence cap
                    base_confidence = 0.50  # Cap at 50%
                    statistical_warnings.append(
                        f"⚠️ LOW SAMPLE SIZE: Only {pattern_count} patterns (need {MIN_PATTERNS_MEDIUM_CONFIDENCE}+ for medium confidence)"
                    )
                elif pattern_count < MIN_PATTERNS_HIGH_CONFIDENCE:
                    # MEDIUM DATA - Good confidence cap
                    base_confidence = 0.70  # Cap at 70%
                    statistical_warnings.append(
                        f"ℹ️ MEDIUM SAMPLE SIZE: {pattern_count} patterns (need {MIN_PATTERNS_HIGH_CONFIDENCE}+ for high confidence)"
                    )
                else:
                    # SUFFICIENT DATA - Allow high confidence
                    if pattern_count >= 100:
                        base_confidence = MAX_CONFIDENCE_WITH_100_PATTERNS  # 90% max
                    elif pattern_count >= 50:
                        base_confidence = MAX_CONFIDENCE_WITH_50_PATTERNS  # 80% max
                    else:
                        # Scale between 70% and 80% for 50-99 patterns
                        base_confidence = 0.70 + (pattern_count - MIN_PATTERNS_HIGH_CONFIDENCE) * 0.002

                    statistical_warnings.append(f"✅ SUFFICIENT DATA: {pattern_count} patterns analyzed")

                # Step 2: Adjust for outcome consistency (reduce confidence if volatile)
                if result['outcome_volatility']:
                    volatility = float(result['outcome_volatility'])
                    # High volatility = less predictable = lower confidence
                    consistency_penalty = min(0.20, volatility / 100)  # Max 20% penalty
                    base_confidence = base_confidence * (1 - consistency_penalty)

                    if volatility > 20:
                        statistical_warnings.append(
                            f"⚠️ HIGH OUTCOME VOLATILITY: {volatility:.1f}% (reduces prediction reliability)"
                        )

                # Step 3: Apply absolute ceiling
                confidence = min(base_confidence, ABSOLUTE_MAX_CONFIDENCE)

                # ============================================================
                # Determine prediction and signal (using new thresholds)
                # ============================================================
                if avg_outcome > 2 and win_rate > MIN_WIN_RATE_FOR_BULLISH:
                    prediction = 'BULLISH'
                    signal = 'BUY'
                    reasoning = f"Historical patterns suggest +{avg_outcome:.1f}% in 24h ({win_rate:.0f}% win rate, {pattern_count} samples)"
                elif avg_outcome < -2 and win_rate < MIN_WIN_RATE_FOR_BEARISH:
                    prediction = 'BEARISH'
                    signal = 'SELL'
                    reasoning = f"Historical patterns suggest {avg_outcome:.1f}% in 24h ({100-win_rate:.0f}% loss rate, {pattern_count} samples)"
                elif win_rate > 70 and avg_win > avg_loss * 1.5:
                    prediction = 'BULLISH'
                    signal = 'BUY'
                    reasoning = f"High win rate ({win_rate:.0f}%) with favorable risk/reward ({avg_win:.1f}%/-{avg_loss:.1f}%, {pattern_count} samples)"
                elif win_rate < 30:
                    prediction = 'BEARISH'
                    signal = 'SELL'
                    reasoning = f"Low win rate ({win_rate:.0f}%) suggests downside risk ({pattern_count} samples)"
                else:
                    prediction = 'NEUTRAL'
                    signal = 'HOLD'
                    reasoning = f"Mixed signals: {avg_outcome:+.1f}% avg outcome, {win_rate:.0f}% win rate ({pattern_count} samples)"

                # Add sample size to reasoning if confidence is capped
                if pattern_count < MIN_PATTERNS_HIGH_CONFIDENCE:
                    reasoning += f" - LIMITED DATA"

                return {
                    'has_patterns': True,
                    'pattern_count': pattern_count,
                    'current_pattern': current_pattern,
                    'historical_stats': {
                        'avg_outcome_24h': round(avg_outcome, 2),
                        'median_outcome_24h': round(median_outcome, 2),
                        'best_outcome': round(float(result['best_outcome']), 2) if result['best_outcome'] else 0,
                        'worst_outcome': round(float(result['worst_outcome']), 2) if result['worst_outcome'] else 0,
                        'win_rate': round(win_rate, 1),
                        'avg_win': round(avg_win, 2),
                        'avg_loss': round(avg_loss, 2),
                        'risk_reward_ratio': round(avg_win / max(avg_loss, 0.1), 2)
                    },
                    'prediction': prediction,
                    'signal': signal,
                    'confidence': round(confidence, 2),
                    'similarity_score': round(similarity, 1),
                    'reasoning': reasoning,
                    'statistical_warnings': statistical_warnings,  # NEW - Critical for Claude to see
                    'lookback_days': lookback_days  # NEW - Shows how much history was analyzed
                }

        except Exception as e:
            print(f"[ERROR] Historical pattern matching failed for {token}: {e}")
            return {
                'has_patterns': False,
                'reason': f'Analysis error: {str(e)}',
                'prediction': None
            }

    def get_current_pattern_metrics(self, token: str) -> Dict:
        """Get current market pattern metrics for comparison"""
        try:
            with self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                # Get price pattern (4 hour change)
                cursor.execute("""
                    SELECT
                        (SELECT close FROM crypto_ohlcv WHERE token = %s ORDER BY timestamp DESC LIMIT 1) as current_price,
                        (SELECT close FROM crypto_ohlcv WHERE token = %s
                         AND timestamp <= NOW() - INTERVAL '4 hours'
                         ORDER BY timestamp DESC LIMIT 1) as price_4h_ago,
                        (SELECT AVG(volume) FROM crypto_ohlcv WHERE token = %s
                         AND timestamp > NOW() - INTERVAL '4 hours') as recent_volume,
                        (SELECT AVG(volume) FROM crypto_ohlcv WHERE token = %s
                         AND timestamp > NOW() - INTERVAL '24 hours') as avg_volume
                """, (token, token, token, token))

                price_data = cursor.fetchone()

                if not price_data or not price_data['current_price']:
                    return {'has_data': False}

                # Calculate price change
                if price_data['price_4h_ago']:
                    price_change_4h = ((float(price_data['current_price']) - float(price_data['price_4h_ago'])) /
                                      float(price_data['price_4h_ago']) * 100)
                else:
                    price_change_4h = 0

                # Get sentiment pattern
                cursor.execute("""
                    SELECT AVG(sentiment_score) as avg_sentiment
                    FROM twitter_sentiment
                    WHERE token = %s
                    AND scraped_at > NOW() - INTERVAL '4 hours'
                """, (token,))

                sentiment_data = cursor.fetchone()
                sentiment = float(sentiment_data['avg_sentiment']) if sentiment_data and sentiment_data['avg_sentiment'] else 0

                # Volume ratio
                if price_data['avg_volume'] and float(price_data['avg_volume']) > 0:
                    volume_ratio = float(price_data['recent_volume']) / float(price_data['avg_volume'])
                else:
                    volume_ratio = 1

                # Get funding rate if available
                cursor.execute("""
                    SELECT funding_rate
                    FROM funding_rates
                    WHERE token = %s
                    ORDER BY scraped_at DESC
                    LIMIT 1
                """, (token,))

                funding_data = cursor.fetchone()
                funding_rate = float(funding_data['funding_rate']) if funding_data and funding_data['funding_rate'] else 0

                return {
                    'has_data': True,
                    'price_change_4h': round(price_change_4h, 2),
                    'sentiment': round(sentiment, 3),
                    'volume_ratio': round(volume_ratio, 2),
                    'funding_rate': round(funding_rate, 4),
                    'current_price': float(price_data['current_price'])
                }

        except Exception as e:
            print(f"[ERROR] Failed to get current pattern metrics for {token}: {e}")
            return {'has_data': False}

    def detect_market_crash_multi_indicator(self) -> Dict:
        """
        Comprehensive market crash detection using multiple indicators
        Returns crash analysis with confidence score and recommendations
        """
        try:
            crash_signals = 0
            total_weight = 0
            indicators = {}

            # 1. BTC PRICE DROPS (Weight: 30%)
            with self.conn.cursor() as cursor:
                cursor.execute("""
                    SELECT
                        -- 1 minute drop
                        (SELECT (close - LAG(close, 12) OVER (ORDER BY timestamp)) / LAG(close, 12) OVER (ORDER BY timestamp) * 100
                         FROM crypto_ohlcv WHERE token = 'BTC' ORDER BY timestamp DESC LIMIT 1) as drop_1min,
                        -- 5 minute drop
                        (SELECT (close - LAG(close, 60) OVER (ORDER BY timestamp)) / LAG(close, 60) OVER (ORDER BY timestamp) * 100
                         FROM crypto_ohlcv WHERE token = 'BTC' ORDER BY timestamp DESC LIMIT 1) as drop_5min,
                        -- 15 minute drop
                        (SELECT (close - LAG(close, 180) OVER (ORDER BY timestamp)) / LAG(close, 180) OVER (ORDER BY timestamp) * 100
                         FROM crypto_ohlcv WHERE token = 'BTC' ORDER BY timestamp DESC LIMIT 1) as drop_15min,
                        -- Current price
                        (SELECT close FROM crypto_ohlcv WHERE token = 'BTC' ORDER BY timestamp DESC LIMIT 1) as current_price
                """)

                result = cursor.fetchone()
                if result:
                    drop_1min = float(result[0]) if result[0] else 0
                    drop_5min = float(result[1]) if result[1] else 0
                    drop_15min = float(result[2]) if result[2] else 0
                    current_price = float(result[3]) if result[3] else 0

                    # Score price drops
                    price_score = 0
                    if drop_1min < -2:  # 2% in 1 minute is extreme
                        price_score += 10
                    if drop_5min < -5:  # 5% in 5 minutes
                        price_score += 10
                    if drop_15min < -8:  # 8% in 15 minutes
                        price_score += 10

                    indicators['btc_drops'] = {
                        '1min': round(drop_1min, 2),
                        '5min': round(drop_5min, 2),
                        '15min': round(drop_15min, 2),
                        'score': price_score
                    }
                    crash_signals += price_score
                    total_weight += 30

            # 2. VOLUME SPIKE DETECTION (Weight: 20%)
            with self.conn.cursor() as cursor:
                cursor.execute("""
                    SELECT
                        AVG(volume) as avg_volume_24h,
                        MAX(volume) as current_volume
                    FROM (
                        SELECT volume FROM crypto_ohlcv
                        WHERE token = 'BTC'
                        AND timestamp > NOW() - INTERVAL '24 hours'
                        ORDER BY timestamp DESC
                        LIMIT 288
                    ) t
                """)

                result = cursor.fetchone()
                if result and result[0] and result[1]:
                    avg_volume = float(result[0])
                    current_volume = float(result[1])
                    volume_spike = current_volume / avg_volume if avg_volume > 0 else 1

                    volume_score = 0
                    if volume_spike > 3:  # 3x normal volume
                        volume_score = 10
                    elif volume_spike > 2:  # 2x normal volume
                        volume_score = 5

                    indicators['volume_spike'] = {
                        'ratio': round(volume_spike, 2),
                        'score': volume_score
                    }
                    crash_signals += volume_score
                    total_weight += 20

            # 3. LIQUIDATION CASCADE CHECK (Weight: 25%)
            liquidation_data = self.get_liquidation_cascade_analysis('BTC')
            liq_score = 0
            if liquidation_data['risk_score'] > 80:
                liq_score = 25
            elif liquidation_data['risk_score'] > 60:
                liq_score = 15
            elif liquidation_data['risk_score'] > 40:
                liq_score = 5

            indicators['liquidations'] = {
                'risk_score': liquidation_data['risk_score'],
                'velocity': liquidation_data['velocity'],
                'score': liq_score
            }
            crash_signals += liq_score
            total_weight += 25

            # 4. CORRELATION SPIKE - Everything moving together (Weight: 15%)
            with self.conn.cursor() as cursor:
                cursor.execute("""
                    WITH price_changes AS (
                        SELECT
                            token,
                            (close - LAG(close, 60) OVER (PARTITION BY token ORDER BY timestamp))
                            / LAG(close, 60) OVER (PARTITION BY token ORDER BY timestamp) * 100 as change_5min
                        FROM crypto_ohlcv
                        WHERE token IN ('BTC', 'ETH', 'SOL', 'BNB', 'AVAX')
                        AND timestamp > NOW() - INTERVAL '10 minutes'
                    )
                    SELECT
                        COUNT(CASE WHEN change_5min < -3 THEN 1 END) as tokens_dropping,
                        AVG(change_5min) as avg_drop
                    FROM (
                        SELECT DISTINCT ON (token) token, change_5min
                        FROM price_changes
                        ORDER BY token, change_5min DESC
                    ) t
                """)

                result = cursor.fetchone()
                if result:
                    tokens_dropping = int(result[0]) if result[0] else 0
                    avg_drop = float(result[1]) if result[1] else 0

                    correlation_score = 0
                    if tokens_dropping >= 4 and avg_drop < -3:  # 4+ major tokens dropping >3%
                        correlation_score = 15
                    elif tokens_dropping >= 3 and avg_drop < -2:
                        correlation_score = 8

                    indicators['correlation'] = {
                        'tokens_dropping': tokens_dropping,
                        'avg_drop': round(avg_drop, 2),
                        'score': correlation_score
                    }
                    crash_signals += correlation_score
                    total_weight += 15

            # 5. FEAR & GREED INDEX (Weight: 10%)
            fear_greed = self.get_fear_greed_index()
            fg_score = 0
            if fear_greed and fear_greed['value'] < 20:  # Extreme fear
                fg_score = 10
            elif fear_greed and fear_greed['value'] < 30:  # Fear
                fg_score = 5

            indicators['fear_greed'] = {
                'value': fear_greed.get('value', 50) if fear_greed else 50,
                'label': fear_greed.get('label', 'Unknown') if fear_greed else 'Unknown',
                'score': fg_score
            }
            crash_signals += fg_score
            total_weight += 10

            # 6. DEFI TVL OUTFLOWS (Weight: 15%) - NEW!
            defi_tvl_score = 0
            try:
                defi_risk = self.check_defi_risk()
                if defi_risk:
                    risk_level = defi_risk.get('risk_level', 'UNKNOWN')
                    if risk_level == 'HIGH':
                        defi_tvl_score = 15
                    elif risk_level == 'MODERATE':
                        defi_tvl_score = 8

                    indicators['defi_tvl'] = {
                        'risk_level': risk_level,
                        'protocols_losing': defi_risk.get('protocols_losing', 0),
                        'position_adjustment': defi_risk.get('position_adjustment', 1.0),
                        'score': defi_tvl_score
                    }
                    crash_signals += defi_tvl_score
                    total_weight += 15
            except:
                pass  # Don't fail if DeFi data unavailable

            # 7. OPTIONS VOLATILITY (Weight: 15%) - NEW!
            options_vol_score = 0
            try:
                # Get volatility risk score from database function
                vol_risk_score = self.get_volatility_risk_score()

                # Convert 0-100 score to 0-15 points
                if vol_risk_score >= 70:
                    options_vol_score = 15
                elif vol_risk_score >= 50:
                    options_vol_score = 10
                elif vol_risk_score >= 30:
                    options_vol_score = 5

                # Also get current options data for details
                options_risk = self.check_options_risk()
                options_data = self.get_options_volatility()

                indicators['options_volatility'] = {
                    'risk_score': vol_risk_score,
                    'iv': options_data.get('btc_iv', 50) if options_data else 50,
                    'regime': options_data.get('volatility_regime', 'UNKNOWN') if options_data else 'UNKNOWN',
                    'bias': options_data.get('directional_bias', 'NEUTRAL') if options_data else 'NEUTRAL',
                    'score': options_vol_score
                }
                crash_signals += options_vol_score
                total_weight += 15
            except:
                pass  # Don't fail if options data unavailable

            # Calculate overall crash probability
            crash_probability = (crash_signals / total_weight * 100) if total_weight > 0 else 0

            # Determine crash status and recommendation
            if crash_probability >= 70:
                status = "CRASH_DETECTED"
                severity = "EXTREME"
                recommendation = "EXIT_ALL_POSITIONS"
                action_required = True
            elif crash_probability >= 50:
                status = "CRASH_WARNING"
                severity = "HIGH"
                recommendation = "REDUCE_EXPOSURE_50%"
                action_required = True
            elif crash_probability >= 30:
                status = "CRASH_ALERT"
                severity = "MODERATE"
                recommendation = "STOP_NEW_POSITIONS"
                action_required = False
            else:
                status = "NORMAL"
                severity = "LOW"
                recommendation = "CONTINUE_NORMAL"
                action_required = False

            # Generate detailed reasoning
            reasons = []
            if indicators.get('btc_drops', {}).get('score', 0) >= 20:
                reasons.append(f"BTC flash crash detected: {indicators['btc_drops']['5min']:.1f}% in 5min")
            if indicators.get('volume_spike', {}).get('score', 0) >= 10:
                reasons.append(f"Panic selling volume: {indicators['volume_spike']['ratio']:.1f}x normal")
            if indicators.get('liquidations', {}).get('score', 0) >= 15:
                reasons.append(f"Liquidation cascade active: {indicators['liquidations']['velocity']} liq/min")
            if indicators.get('correlation', {}).get('score', 0) >= 10:
                reasons.append(f"Market-wide selloff: {indicators['correlation']['tokens_dropping']} major tokens dropping")
            if indicators.get('fear_greed', {}).get('score', 0) >= 10:
                reasons.append(f"Extreme fear sentiment: {indicators['fear_greed']['value']}/100")
            if indicators.get('defi_tvl', {}).get('score', 0) >= 10:
                reasons.append(f"DeFi capital exodus: {indicators['defi_tvl']['risk_level']} risk, {indicators['defi_tvl']['protocols_losing']} protocols losing")
            if indicators.get('options_volatility', {}).get('score', 0) >= 10:
                reasons.append(f"Options panic: IV={indicators['options_volatility']['iv']:.0f}%, regime={indicators['options_volatility']['regime']}")

            return {
                'status': status,
                'severity': severity,
                'probability': round(crash_probability, 1),
                'recommendation': recommendation,
                'action_required': action_required,
                'indicators': indicators,
                'reasoning': ' | '.join(reasons) if reasons else 'Market conditions normal',
                'timestamp': datetime.now().isoformat()
            }

        except Exception as e:
            print(f"[ERROR] Market crash detection failed: {e}")
            import traceback
            traceback.print_exc()
            return {
                'status': 'ERROR',
                'severity': 'UNKNOWN',
                'probability': 0,
                'recommendation': 'MANUAL_CHECK_REQUIRED',
                'action_required': False,
                'indicators': {},
                'reasoning': f'Detection failed: {str(e)}',
                'timestamp': datetime.now().isoformat()
            }

    def get_stablecoin_metrics(self) -> Dict:
        """Get stablecoin velocity and flow metrics (0.87 BTC correlation)"""
        try:
            with self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                # Get latest stablecoin metrics
                cursor.execute("""
                    SELECT
                        SUM(market_cap) as total_mcap,
                        AVG(velocity_ratio) as avg_velocity,
                        SUM(supply_change_24h) as net_flow_24h,
                        AVG(supply_change_pct_24h) as supply_change_pct,
                        MAX(price_deviation_pct) as max_deviation
                    FROM stablecoin_metrics
                    WHERE timestamp > NOW() - INTERVAL '1 hour'
                    AND symbol IN ('USDT', 'USDC', 'DAI')
                """)

                row = cursor.fetchone()
                if not row or not row['total_mcap']:
                    return None

                # Interpret signals
                signal = 'NEUTRAL'
                if row['supply_change_pct'] and row['supply_change_pct'] > 2:
                    signal = 'BULLISH_INFLOW'  # Money entering crypto
                elif row['supply_change_pct'] and row['supply_change_pct'] < -2:
                    signal = 'BEARISH_OUTFLOW'  # Money leaving crypto
                elif row['avg_velocity'] and row['avg_velocity'] > 0.5:
                    signal = 'HIGH_ACTIVITY'  # Volatility incoming

                return {
                    'total_mcap': float(row['total_mcap']) if row['total_mcap'] else 0,
                    'avg_velocity': float(row['avg_velocity']) if row['avg_velocity'] else 0,
                    'net_flow_24h': float(row['net_flow_24h']) if row['net_flow_24h'] else 0,
                    'supply_change_pct': float(row['supply_change_pct']) if row['supply_change_pct'] else 0,
                    'max_deviation': float(row['max_deviation']) if row['max_deviation'] else 0,
                    'signal': signal
                }
        except Exception as e:
            print(f"[WARNING] Failed to get stablecoin metrics: {e}")
            return None

    def get_smart_money_flows(self, token: str, hours: int = 6) -> Dict:
        """Get Smart Money movement data (23% better stability signals)"""
        try:
            with self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                # Get Smart Money flows for specific token
                cursor.execute("""
                    SELECT
                        SUM(CASE WHEN flow_type = 'INFLOW' THEN usd_value ELSE -usd_value END) as net_flow,
                        COUNT(DISTINCT from_entity) + COUNT(DISTINCT to_entity) as entity_count,
                        ARRAY_AGG(DISTINCT
                            CASE WHEN from_entity != 'Unknown' THEN from_entity
                                 WHEN to_entity != 'Unknown' THEN to_entity
                            END
                        ) as entities,
                        MAX(signal_strength) as max_signal
                    FROM exchange_flows
                    WHERE token = %s
                    AND timestamp > NOW() - INTERVAL '1 hour' * %s
                    AND is_smart_money = true
                """, (token, hours))

                row = cursor.fetchone()
                if not row or not row['net_flow']:
                    return None

                net_flow = float(row['net_flow'])

                # Determine direction and action
                if net_flow > 1000000:  # >$1M inflow
                    direction = 'ACCUMULATING'
                    recommended_action = 'BUY'
                elif net_flow < -1000000:  # >$1M outflow
                    direction = 'DISTRIBUTING'
                    recommended_action = 'SELL'
                elif abs(net_flow) > 100000:
                    direction = 'ACTIVE'
                    recommended_action = 'WATCH'
                else:
                    direction = 'NEUTRAL'
                    recommended_action = 'HOLD'

                # Clean entities list
                entities = [e for e in (row['entities'] or []) if e and e != 'Unknown']

                return {
                    'net_flow': net_flow,
                    'direction': direction,
                    'entities': entities[:5],  # Top 5 entities
                    'entity_count': row['entity_count'] or 0,
                    'signal_strength': float(row['max_signal']) if row['max_signal'] else 0,
                    'recommended_action': recommended_action
                }
        except Exception as e:
            print(f"[WARNING] Failed to get Smart Money flows: {e}")
            return None

    def get_dex_liquidity_metrics(self, token: str) -> Dict:
        """Get DEX liquidity and volume metrics (40% market share)"""
        try:
            with self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                # Get latest DEX metrics for token
                cursor.execute("""
                    SELECT
                        SUM(liquidity_usd) as total_liquidity,
                        SUM(volume_24h) as total_volume,
                        AVG(volume_to_liquidity_ratio) as vol_liq_ratio,
                        COUNT(DISTINCT dex_name) as dex_count,
                        MAX(price_usd) as max_price,
                        MIN(price_usd) as min_price
                    FROM dex_liquidity
                    WHERE token = %s
                    AND timestamp > NOW() - INTERVAL '1 hour'
                """, (token,))

                row = cursor.fetchone()
                if not row or not row['total_liquidity']:
                    return None

                # Calculate price spread (arbitrage indicator)
                price_spread = 0
                arb_opportunity = 'NO'
                if row['max_price'] and row['min_price'] and row['min_price'] > 0:
                    price_spread = ((float(row['max_price']) - float(row['min_price'])) / float(row['min_price'])) * 100
                    if price_spread > 1.0:
                        arb_opportunity = 'YES'

                return {
                    'total_liquidity': float(row['total_liquidity']) if row['total_liquidity'] else 0,
                    'total_volume': float(row['total_volume']) if row['total_volume'] else 0,
                    'vol_liq_ratio': float(row['vol_liq_ratio']) if row['vol_liq_ratio'] else 0,
                    'dex_count': row['dex_count'] or 0,
                    'price_spread': price_spread,
                    'arb_opportunity': arb_opportunity
                }
        except Exception as e:
            print(f"[WARNING] Failed to get DEX metrics: {e}")
            return None

    def get_latest_funding_rate(self, token: str) -> Optional[float]:
        """Get latest funding rate for mean reversion trading"""
        try:
            with self.conn.cursor() as cursor:
                cursor.execute("""
                    SELECT funding_rate
                    FROM funding_rates
                    WHERE token = %s
                    ORDER BY scraped_at DESC
                    LIMIT 1
                """, (token,))

                result = cursor.fetchone()
                return float(result[0]) if result else None
        except Exception as e:
            print(f"[WARNING] Failed to get funding rate for {token}: {e}")
            return None

    def get_market_volatility(self, hours: int = 1) -> float:
        """Calculate average market volatility for adaptive timing"""
        try:
            with self.conn.cursor() as cursor:
                # Get BTC volatility as market proxy
                cursor.execute("""
                    SELECT
                        STDDEV((close - LAG(close) OVER (ORDER BY timestamp)) / LAG(close) OVER (ORDER BY timestamp))
                    FROM crypto_ohlcv
                    WHERE token = 'BTC'
                    AND timestamp > NOW() - INTERVAL %s
                    AND timeframe = '5m'
                """, (f"{hours} hours",))

                result = cursor.fetchone()
                return float(result[0]) if result and result[0] else 0.01  # Default 1% volatility
        except Exception as e:
            print(f"[WARNING] Failed to get market volatility: {e}")
            return 0.01

    def get_news_sentiment(self, token: str, hours: int = 24) -> Optional[Dict]:
        """Get recent news sentiment for a token"""
        try:
            with self.conn.cursor() as cursor:
                # Search for token mentions in news
                cursor.execute("""
                    SELECT
                        COUNT(*) as article_count,
                        MAX(published_at) as latest_article
                    FROM news_articles
                    WHERE (title ILIKE %s OR content ILIKE %s)
                    AND published_at > NOW() - INTERVAL %s
                """, (f'%{token}%', f'%{token}%', f'{hours} hours'))

                result = cursor.fetchone()
                if result and result[0] > 0:
                    return {
                        'has_news': True,
                        'article_count': result[0],
                        'latest_article': result[1],
                        'signal': 'BULLISH' if result[0] > 5 else 'NEUTRAL'  # Many articles = attention
                    }
                return {'has_news': False}
        except Exception as e:
            print(f"[WARNING] Failed to get news sentiment: {e}")
            return None

    def get_congressional_signals(self, days: int = 7) -> List[Dict]:
        """Get recent congressional trades that might signal insider knowledge"""
        try:
            with self.conn.cursor() as cursor:
                cursor.execute("""
                    SELECT
                        ticker,
                        transaction_type,
                        COUNT(*) as trade_count,
                        MAX(transaction_date) as latest_trade
                    FROM congressional_trades
                    WHERE transaction_date > NOW() - INTERVAL %s
                    GROUP BY ticker, transaction_type
                    HAVING COUNT(*) > 1  -- Multiple politicians = stronger signal
                    ORDER BY trade_count DESC
                    LIMIT 10
                """, (f'{days} days',))

                signals = []
                for row in cursor.fetchall():
                    # Map stock tickers to related crypto (e.g., COIN -> BTC, SQ -> BTC)
                    crypto_map = {
                        'COIN': 'BTC',  # Coinbase
                        'MSTR': 'BTC',  # MicroStrategy
                        'TSLA': 'BTC',  # Tesla holds BTC
                        'SQ': 'BTC',    # Square/Block
                        'PYPL': 'ETH',  # PayPal crypto
                    }

                    if row[0] in crypto_map:
                        signals.append({
                            'stock': row[0],
                            'crypto': crypto_map[row[0]],
                            'action': row[1],
                            'trade_count': row[2],
                            'signal': 'BULLISH' if 'purchase' in row[1].lower() else 'BEARISH'
                        })
                return signals
        except Exception as e:
            print(f"[WARNING] Failed to get congressional signals: {e}")
            return []

    def get_exchange_flow_signals(self, hours: int = 6) -> List[Dict]:
        """Get recent exchange flows for front-running"""
        try:
            with self.conn.cursor() as cursor:
                cursor.execute("""
                    SELECT
                        token,
                        flow_type,
                        SUM(usd_value) as total_value,
                        COUNT(*) as flow_count,
                        MAX(timestamp) as latest_flow
                    FROM exchange_flows
                    WHERE timestamp > NOW() - INTERVAL %s
                    AND usd_value > 100000  -- Only whale movements
                    GROUP BY token, flow_type
                    HAVING SUM(usd_value) > 500000  -- Significant total
                    ORDER BY total_value DESC
                """, (f"{hours} hours",))

                flows = []
                for row in cursor.fetchall():
                    signal = 'BEARISH' if row[1] == 'INFLOW' else 'BULLISH'
                    flows.append({
                        'token': row[0],
                        'flow_type': row[1],
                        'total_value': float(row[2]),
                        'flow_count': row[3],
                        'latest_flow': row[4],
                        'signal': signal,
                        'strength': min(row[2] / 1000000, 1.0)  # Normalize to 0-1
                    })
                return flows
        except Exception as e:
            print(f"[WARNING] Failed to get exchange flow signals: {e}")
            return []

    def get_defi_tvl_signals(self, lookback_hours: int = 24) -> Optional[Dict]:
        """Get DeFi TVL flow signals for risk assessment"""
        try:
            with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                # Get latest flow signals
                cursor.execute("""
                    SELECT *
                    FROM defi_flow_signals
                    WHERE scraped_at > NOW() - INTERVAL '%s hours'
                    ORDER BY scraped_at DESC
                    LIMIT 1
                """, (lookback_hours,))

                flow_signal = cursor.fetchone()
                if not flow_signal:
                    return None

                # Get chain TVL breakdown
                cursor.execute("""
                    WITH latest_chains AS (
                        SELECT DISTINCT ON (chain_name)
                            chain_name,
                            tvl_usd,
                            scraped_at
                        FROM defi_tvl_chains
                        WHERE scraped_at > NOW() - INTERVAL '%s hours'
                        ORDER BY chain_name, scraped_at DESC
                    )
                    SELECT
                        chain_name,
                        tvl_usd,
                        tvl_usd / SUM(tvl_usd) OVER () * 100 as dominance_pct
                    FROM latest_chains
                    ORDER BY tvl_usd DESC
                """, (lookback_hours,))

                chain_data = cursor.fetchall()

                # Parse JSONB fields
                biggest_gainers = flow_signal['biggest_gainers'] if isinstance(flow_signal['biggest_gainers'], list) else json.loads(flow_signal['biggest_gainers']) if flow_signal['biggest_gainers'] else []
                biggest_losers = flow_signal['biggest_losers'] if isinstance(flow_signal['biggest_losers'], list) else json.loads(flow_signal['biggest_losers']) if flow_signal['biggest_losers'] else []
                category_flows = flow_signal['category_flows'] if isinstance(flow_signal['category_flows'], dict) else json.loads(flow_signal['category_flows']) if flow_signal['category_flows'] else {}

                return {
                    'risk_indicator': flow_signal['risk_indicator'],
                    'top_gainers': biggest_gainers[:5],
                    'top_losers': biggest_losers[:5],
                    'chain_dominance': [
                        {
                            'chain': row['chain_name'],
                            'tvl': float(row['tvl_usd']),
                            'dominance': float(row['dominance_pct'])
                        }
                        for row in chain_data
                    ],
                    'category_flows': category_flows,
                    'last_updated': flow_signal['scraped_at']
                }
        except Exception as e:
            print(f"[WARNING] Failed to get DeFi TVL signals: {e}")
            return None

    def check_defi_risk(self) -> Dict:
        """Check for DeFi-wide risk conditions"""
        try:
            signals = self.get_defi_tvl_signals(lookback_hours=6)
            if not signals:
                return {
                    'should_reduce_exposure': False,
                    'risk_level': 'UNKNOWN',
                    'position_adjustment': 1.0,
                    'reasons': []
                }

            reasons = []
            risk_score = 0

            # Check for massive outflows
            if signals['risk_indicator'] == 'HIGH_OUTFLOWS':
                reasons.append("Significant DeFi capital outflows detected")
                risk_score += 3
            elif signals['risk_indicator'] == 'MODERATE_OUTFLOWS':
                reasons.append("Moderate DeFi capital outflows detected")
                risk_score += 1

            # Check for protocol collapses
            for loser in signals.get('top_losers', [])[:3]:
                change_pct = loser.get('change_pct', 0)
                if change_pct and change_pct < -20:
                    reasons.append(f"{loser['name']} lost {abs(change_pct):.1f}% TVL")
                    risk_score += 2

            # Check chain concentration risk
            chain_dominance = signals.get('chain_dominance', [])
            if chain_dominance and chain_dominance[0].get('dominance', 0) > 85:
                dominance_val = chain_dominance[0].get('dominance', 0)
                chain_name = chain_dominance[0].get('chain', 'Unknown')
                reasons.append(f"High chain concentration risk: {chain_name} at {dominance_val:.1f}%")
                risk_score += 1

            # Determine risk level and position adjustment
            if risk_score >= 5:
                risk_level = 'HIGH'
                should_reduce = True
                position_adjustment = 0.5  # Cut position in half
            elif risk_score >= 3:
                risk_level = 'MODERATE'
                should_reduce = False
                position_adjustment = 0.8  # Reduce to 80%
            else:
                risk_level = 'LOW'
                should_reduce = False
                position_adjustment = 1.0  # Full position

            return {
                'should_reduce_exposure': should_reduce,
                'risk_level': risk_level,
                'position_adjustment': position_adjustment,
                'reasons': reasons,
                'risk_score': risk_score
            }
        except Exception as e:
            print(f"[WARNING] Failed to check DeFi risk: {e}")
            return {'should_reduce_exposure': False, 'risk_level': 'UNKNOWN', 'reasons': []}

    def get_protocol_tvl(self, protocol_name: str) -> Optional[Dict]:
        """Get TVL data for a specific DeFi protocol"""
        try:
            with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT *
                    FROM defi_protocols
                    WHERE LOWER(protocol_name) = LOWER(%s)
                    ORDER BY scraped_at DESC
                    LIMIT 1
                """, (protocol_name,))

                protocol = cursor.fetchone()
                if not protocol:
                    return None

                return {
                    'name': protocol['protocol_name'],
                    'tvl': float(protocol['tvl_usd']),
                    'change_1d': float(protocol['change_1d_pct']) if protocol['change_1d_pct'] else 0,
                    'change_7d': float(protocol['change_7d_pct']) if protocol['change_7d_pct'] else 0,
                    'category': protocol['category'],
                    'main_chain': protocol['main_chain'],
                    'risk_level': 'HIGH' if protocol['change_1d_pct'] and protocol['change_1d_pct'] < -10 else 'NORMAL'
                }
        except Exception as e:
            print(f"[WARNING] Failed to get protocol TVL: {e}")
            return None

    def get_options_volatility(self) -> Optional[Dict]:
        """Get latest options volatility data for risk assessment"""
        try:
            with self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                cursor.execute("""
                    SELECT
                        btc_iv, btc_skew, btc_iv_rank,
                        eth_iv, eth_skew, eth_iv_rank,
                        avg_iv, volatility_regime, directional_bias,
                        risk_level, position_adjustment, scraped_at
                    FROM options_volatility
                    ORDER BY scraped_at DESC
                    LIMIT 1
                """)

                row = cursor.fetchone()
                if not row:
                    return None

                # Skip age check for now - data should be managed by orchestrator
                # Options data updates every 30 minutes

                return {
                    'btc_iv': float(row['btc_iv']) if row['btc_iv'] else 50,
                    'btc_skew': float(row['btc_skew']) if row['btc_skew'] else 0,
                    'btc_iv_rank': float(row['btc_iv_rank']) if row['btc_iv_rank'] else 50,
                    'eth_iv': float(row['eth_iv']) if row['eth_iv'] else 50,
                    'eth_skew': float(row['eth_skew']) if row['eth_skew'] else 0,
                    'eth_iv_rank': float(row['eth_iv_rank']) if row['eth_iv_rank'] else 50,
                    'avg_iv': float(row['avg_iv']) if row['avg_iv'] else 50,
                    'volatility_regime': row['volatility_regime'] or 'MODERATE',
                    'directional_bias': row['directional_bias'] or 'NEUTRAL',
                    'risk_level': row['risk_level'] or 'NORMAL',
                    'position_adjustment': float(row['position_adjustment']) if row['position_adjustment'] else 1.0
                }

        except Exception as e:
            return None  # Don't print to avoid spam, options data is optional

    def check_options_risk(self) -> Dict:
        """Check options-based risk for position sizing"""
        try:
            vol_data = self.get_options_volatility()

            if not vol_data:
                return {
                    'risk_level': 'UNKNOWN',
                    'position_adjustment': 1.0,
                    'warnings': []
                }

            warnings = []
            position_adjustment = vol_data['position_adjustment']

            # Check for extreme conditions
            if vol_data['avg_iv'] > 80:
                warnings.append(f"Extreme IV: {vol_data['avg_iv']:.1f}%")

            if vol_data['btc_skew'] < -8 or vol_data['eth_skew'] < -8:
                warnings.append(f"Heavy put buying: BTC skew={vol_data['btc_skew']:.1f}, ETH skew={vol_data['eth_skew']:.1f}")

            if vol_data['btc_iv_rank'] > 80 or vol_data['eth_iv_rank'] > 80:
                warnings.append("IV at 30-day highs")

            return {
                'risk_level': vol_data['risk_level'],
                'volatility_regime': vol_data['volatility_regime'],
                'directional_bias': vol_data['directional_bias'],
                'position_adjustment': position_adjustment,
                'btc_iv': vol_data['btc_iv'],
                'eth_iv': vol_data['eth_iv'],
                'warnings': warnings
            }

        except Exception as e:
            return {
                'risk_level': 'UNKNOWN',
                'position_adjustment': 1.0,
                'warnings': []
            }

    def get_volatility_risk_score(self) -> int:
        """Get volatility risk score (0-100) for crash detection"""
        try:
            with self.conn.cursor() as cursor:
                cursor.execute("SELECT * FROM get_volatility_risk_score()")
                result = cursor.fetchone()
                if result:
                    return int(result[0])  # Return the risk score
                return 0
        except:
            return 0

    def get_bridge_flow_signals(self, lookback_hours: int = 24) -> Optional[Dict]:
        """Get bridge flow signals for L2 capital rotation"""
        try:
            with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                # Get latest flow signals
                cursor.execute("""
                    SELECT *
                    FROM bridge_flow_signals
                    WHERE created_at > NOW() - INTERVAL '%s hours'
                    ORDER BY created_at DESC
                """, (lookback_hours,))

                signals = cursor.fetchall()

                # Get 7-day aggregated flows
                cursor.execute("""
                    SELECT
                        chain,
                        SUM(deposits_usd) as deposits_7d,
                        SUM(withdrawals_usd) as withdrawals_7d,
                        SUM(net_flow_usd) as net_flow_7d
                    FROM bridge_flows
                    WHERE date >= CURRENT_DATE - INTERVAL '7 days'
                    GROUP BY chain
                    ORDER BY net_flow_7d DESC
                """)

                flow_data = cursor.fetchall()

                if not flow_data:
                    return None

                # Find rotation leader (highest net inflows)
                rotation_leader = None
                if flow_data and flow_data[0]['net_flow_7d'] > 10_000_000:
                    rotation_leader = {
                        'chain': flow_data[0]['chain'],
                        'net_flow': float(flow_data[0]['net_flow_7d']),
                        'signal': 'CAPITAL_ROTATION'
                    }

                # Find outflow warnings
                outflow_chains = []
                for chain in flow_data:
                    if chain['net_flow_7d'] < -10_000_000:
                        outflow_chains.append({
                            'chain': chain['chain'],
                            'net_flow': float(chain['net_flow_7d'])
                        })

                # Process signals
                critical_signals = [s for s in signals if s['alert_level'] == 'critical']
                warning_signals = [s for s in signals if s['alert_level'] == 'warning']

                return {
                    'rotation_leader': rotation_leader,
                    'outflow_warnings': outflow_chains,
                    'critical_signals': critical_signals[:3],
                    'warning_signals': warning_signals[:3],
                    'l2_flows': [
                        {
                            'chain': row['chain'],
                            'net_flow_7d': float(row['net_flow_7d']),
                            'deposits_7d': float(row['deposits_7d']),
                            'withdrawals_7d': float(row['withdrawals_7d'])
                        }
                        for row in flow_data
                    ]
                }

        except Exception as e:
            print(f"[WARNING] Failed to get bridge flow signals: {e}")
            return None

    def check_l2_rotation(self, token: str = None) -> Dict:
        """Check for L2 rotation signals that might affect a token"""
        try:
            signals = self.get_bridge_flow_signals(lookback_hours=24)

            if not signals:
                return {
                    'rotation_detected': False,
                    'affected_chains': [],
                    'recommendation': 'No significant L2 rotation detected'
                }

            affected_chains = []
            recommendations = []

            # Check rotation leader
            if signals.get('rotation_leader'):
                leader = signals['rotation_leader']
                affected_chains.append(leader['chain'])

                # Token-specific recommendations based on chain
                chain_tokens = {
                    'Arbitrum': ['ARB', 'GMX', 'MAGIC', 'RDNT'],
                    'Optimism': ['OP', 'VELO', 'SNX'],
                    'Base': ['AERO', 'BRETT', 'DEGEN'],
                    'Polygon': ['MATIC', 'QUICK', 'AAVE'],
                    'Blast': ['BLAST', 'JUICE'],
                }

                if token and leader['chain'] in chain_tokens:
                    if token.upper() in chain_tokens[leader['chain']]:
                        recommendations.append(f"{token} could benefit from {leader['chain']} inflows (${leader['net_flow']/1e6:.1f}M in 7d)")

            # Check outflows
            for outflow in signals.get('outflow_warnings', []):
                affected_chains.append(outflow['chain'])
                recommendations.append(f"Avoid {outflow['chain']} tokens - capital fleeing (${abs(outflow['net_flow'])/1e6:.1f}M outflow)")

            return {
                'rotation_detected': len(affected_chains) > 0,
                'affected_chains': affected_chains,
                'rotation_leader': signals.get('rotation_leader'),
                'recommendations': recommendations,
                'l2_flows': signals.get('l2_flows', [])[:5]  # Top 5 L2s
            }

        except Exception as e:
            print(f"[WARNING] Failed to check L2 rotation: {e}")
            return {
                'rotation_detected': False,
                'affected_chains': [],
                'recommendation': 'Unable to check L2 rotation'
            }

    def get_bridge_flow_velocity(self, chain: str, days: int = 7) -> Optional[Dict]:
        """Calculate flow velocity for a specific chain"""
        try:
            with self.conn.cursor() as cursor:
                cursor.execute("""
                    SELECT * FROM calculate_flow_velocity(%s, %s)
                """, (chain, days))

                result = cursor.fetchone()
                if result:
                    return {
                        'velocity': float(result[0]) if result[0] else 0,
                        'acceleration': float(result[1]) if result[1] else 0,
                        'trend': result[2] if result[2] else 'UNKNOWN'
                    }
                return None

        except Exception as e:
            print(f"[WARNING] Failed to get flow velocity: {e}")
            return None

    def get_l2_ranking(self) -> List[Dict]:
        """Get L2 chains ranked by capital flows"""
        try:
            with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT * FROM l2_rotation_rankings
                    LIMIT 10
                """)

                rankings = cursor.fetchall()
                if not rankings:
                    return []

                return [
                    {
                        'chain': row['chain'],
                        'flow_24h': float(row['flow_24h']) if row['flow_24h'] else 0,
                        'flow_7d': float(row['flow_7d']) if row['flow_7d'] else 0,
                        'flow_30d': float(row['flow_30d']) if row['flow_30d'] else 0,
                        'velocity_ratio': float(row['velocity_ratio']) if row['velocity_ratio'] else 0,
                        'rank': row['flow_rank_7d'],
                        'status': row['rotation_status']
                    }
                    for row in rankings
                ]

        except Exception as e:
            print(f"[WARNING] Failed to get L2 rankings: {e}")
            return []

    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
            print("[DataIntelligence] Database connection closed")
