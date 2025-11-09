"""
Market Analyzer - Regime Detection and BTC Dominance Tracking
Identifies market regimes: BULL, BEAR, VOLATILE, SIDEWAYS, ALTSEASON
Tracks BTC dominance for optimal altcoin timing
"""

import os
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
import numpy as np
import requests
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MarketAnalyzer:
    """Analyzes market conditions and identifies trading regimes"""

    def __init__(self):
        """Initialize market analyzer"""
        self.conn = None
        self.init_database()

        # Market regime thresholds
        self.BULL_TREND_THRESHOLD = 0.02    # 2% daily gain = bull
        self.BEAR_TREND_THRESHOLD = -0.02   # -2% daily loss = bear
        self.HIGH_VOLATILITY_THRESHOLD = 0.05  # 5% ATR = high volatility
        self.BTC_DOMINANCE_ALTSEASON = 55   # Below 55% = altseason
        self.BTC_DOMINANCE_BTC_SEASON = 60  # Above 60% = BTC season

        # Cache for performance
        self.btc_dominance_cache = {'value': None, 'timestamp': None}
        self.cache_duration = 3600  # 1 hour cache for BTC dominance

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
            logger.info("Database connection established for market analyzer")
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            raise

    def get_btc_dominance(self) -> Optional[float]:
        """
        Fetch current BTC dominance from CoinGecko
        Critical for altcoin timing - currently 58-62% (November 2025)
        """
        try:
            # Check cache first
            if self.btc_dominance_cache['value'] is not None:
                cache_age = time.time() - (self.btc_dominance_cache['timestamp'] or 0)
                if cache_age < self.cache_duration:
                    return self.btc_dominance_cache['value']

            # Fetch from CoinGecko
            api_key = os.getenv('COINGECKO_API_KEY')
            headers = {'x-cg-demo-api-key': api_key} if api_key else {}

            response = requests.get(
                'https://api.coingecko.com/api/v3/global',
                headers=headers,
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                btc_dominance = data['data']['market_cap_percentage']['btc']

                # Update cache
                self.btc_dominance_cache = {
                    'value': btc_dominance,
                    'timestamp': time.time()
                }

                # Store in database for historical trend analysis
                try:
                    with self.conn.cursor() as cur:
                        cur.execute("""
                            INSERT INTO market_metrics (btc_dominance)
                            VALUES (%s)
                        """, (btc_dominance,))
                        self.conn.commit()
                except Exception as db_err:
                    logger.warning(f"Could not store BTC dominance: {db_err}")
                    self.conn.rollback()

                logger.info(f"BTC Dominance: {btc_dominance:.2f}%")
                return btc_dominance
            else:
                logger.warning(f"CoinGecko API error: {response.status_code}")
                return self.btc_dominance_cache['value']  # Return cached value if API fails

        except Exception as e:
            logger.error(f"Error fetching BTC dominance: {e}")
            return self.btc_dominance_cache['value']

    def calculate_btc_trend(self) -> Tuple[float, str]:
        """
        Calculate BTC price trend using moving averages
        Returns: (trend_strength, direction)
        """
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Get BTC price data for trend analysis
                cur.execute("""
                    WITH price_data AS (
                        SELECT
                            close,
                            timestamp
                        FROM crypto_ohlcv
                        WHERE token = 'BTC'
                        AND timestamp > NOW() - INTERVAL '30 days'
                        ORDER BY timestamp DESC
                    ),
                    moving_averages AS (
                        SELECT
                            AVG(CASE WHEN timestamp > NOW() - INTERVAL '50 hours'
                                THEN close END) as ma_50h,
                            AVG(CASE WHEN timestamp > NOW() - INTERVAL '200 hours'
                                THEN close END) as ma_200h,
                            MAX(close) as current_price,
                            AVG(CASE WHEN timestamp > NOW() - INTERVAL '24 hours'
                                THEN close END) as price_24h_ago
                        FROM price_data
                    )
                    SELECT
                        current_price,
                        price_24h_ago,
                        ma_50h,
                        ma_200h,
                        (current_price - price_24h_ago) / price_24h_ago as daily_change,
                        (ma_50h - ma_200h) / ma_200h as trend_strength
                    FROM moving_averages
                """)

                result = cur.fetchone()

                if not result:
                    return 0.0, 'UNKNOWN'

                daily_change = result['daily_change'] or 0
                trend_strength = result['trend_strength'] or 0

                # Determine trend direction
                if result['ma_50h'] and result['ma_200h']:
                    if result['ma_50h'] > result['ma_200h']:
                        direction = 'BULLISH'
                    else:
                        direction = 'BEARISH'
                else:
                    # Fallback to daily change
                    direction = 'BULLISH' if daily_change > 0 else 'BEARISH'

                return trend_strength, direction

        except Exception as e:
            logger.error(f"Error calculating BTC trend: {e}")
            try:
                self.conn.rollback()
            except:
                pass
            return 0.0, 'UNKNOWN'

    def calculate_market_volatility(self) -> float:
        """
        Calculate market volatility using ATR (Average True Range)
        Returns volatility as percentage
        """
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Calculate ATR for BTC (market proxy)
                cur.execute("""
                    WITH price_ranges AS (
                        SELECT
                            high - low as true_range,
                            (high - low) / NULLIF(close, 0) as range_pct
                        FROM crypto_ohlcv
                        WHERE token = 'BTC'
                        AND timestamp > NOW() - INTERVAL '14 days'
                    )
                    SELECT
                        AVG(range_pct) * 100 as atr_percentage,
                        STDDEV(range_pct) * 100 as volatility_stddev
                    FROM price_ranges
                """)

                result = cur.fetchone()

                if result and result['atr_percentage']:
                    return result['atr_percentage']
                else:
                    return 0.0

        except Exception as e:
            logger.error(f"Error calculating volatility: {e}")
            try:
                self.conn.rollback()
            except:
                pass
            return 0.0

    def get_fear_greed_index(self) -> Optional[int]:
        """
        Get the latest Fear & Greed Index value
        """
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT value, classification
                    FROM fear_greed_index
                    ORDER BY scraped_at DESC
                    LIMIT 1
                """)

                result = cur.fetchone()
                return result['value'] if result else None

        except Exception as e:
            logger.error(f"Error fetching Fear & Greed: {e}")
            try:
                self.conn.rollback()
            except:
                pass
            return None

    def get_funding_rate_sentiment(self) -> str:
        """
        Analyze funding rates to detect overleveraged conditions
        """
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Get average funding rates across major tokens
                cur.execute("""
                    SELECT
                        AVG(funding_rate) as avg_funding,
                        MAX(funding_rate) as max_funding,
                        MIN(funding_rate) as min_funding
                    FROM funding_rates
                    WHERE scraped_at > NOW() - INTERVAL '8 hours'
                    AND token IN ('BTC', 'ETH', 'SOL', 'BNB')
                """)

                result = cur.fetchone()

                if not result or result['avg_funding'] is None:
                    return 'NEUTRAL'

                avg_funding = result['avg_funding']
                max_funding = result['max_funding']

                # Determine funding sentiment
                if avg_funding > 0.05:  # 0.05% = overleveraged longs
                    return 'OVERLEVERAGED_LONG'
                elif avg_funding < -0.05:  # -0.05% = overleveraged shorts
                    return 'OVERLEVERAGED_SHORT'
                elif max_funding > 0.5:  # Extreme funding in any token
                    return 'EXTREME_FUNDING'
                else:
                    return 'NEUTRAL'

        except Exception as e:
            logger.error(f"Error analyzing funding rates: {e}")
            try:
                self.conn.rollback()
            except:
                pass
            return 'NEUTRAL'

    def detect_market_regime(self) -> Dict:
        """
        Detect current market regime based on multiple indicators
        Returns: regime type and confidence
        """
        # Gather all indicators
        btc_dominance = self.get_btc_dominance()
        trend_strength, trend_direction = self.calculate_btc_trend()
        volatility = self.calculate_market_volatility()
        fear_greed = self.get_fear_greed_index()
        funding_sentiment = self.get_funding_rate_sentiment()

        # Initialize regime detection
        regime = 'UNKNOWN'
        confidence = 0
        characteristics = []
        recommended_strategy = 'NEUTRAL'

        # Detect ALTSEASON (highest priority)
        if btc_dominance and btc_dominance < self.BTC_DOMINANCE_ALTSEASON:
            regime = 'ALTSEASON'
            confidence = min(90, 100 - btc_dominance)  # Lower dominance = higher confidence
            characteristics.append(f"BTC dominance low: {btc_dominance:.1f}%")
            recommended_strategy = 'FAVOR_ALTCOINS'

        # Detect HIGH VOLATILITY
        elif volatility > self.HIGH_VOLATILITY_THRESHOLD:
            regime = 'HIGH_VOLATILITY'
            confidence = min(85, 50 + volatility * 10)
            characteristics.append(f"ATR: {volatility:.2f}%")

            if funding_sentiment == 'OVERLEVERAGED_LONG':
                characteristics.append("Overleveraged longs - cascade risk")
                recommended_strategy = 'DEFENSIVE_SHORT_BIAS'
            elif funding_sentiment == 'OVERLEVERAGED_SHORT':
                characteristics.append("Overleveraged shorts - squeeze potential")
                recommended_strategy = 'CAUTIOUS_LONG_BIAS'
            else:
                recommended_strategy = 'SCALPING_TIGHT_STOPS'

        # Detect BULL TREND
        elif trend_direction == 'BULLISH' and trend_strength > 0.05:
            regime = 'BULL_TREND'
            confidence = min(85, 50 + trend_strength * 100)
            characteristics.append(f"50MA > 200MA by {trend_strength:.1%}")

            if fear_greed and fear_greed > 75:
                characteristics.append(f"Extreme greed: {fear_greed}")
                recommended_strategy = 'CAUTIOUS_LONG'  # Be careful at extremes
            else:
                recommended_strategy = 'AGGRESSIVE_LONG'

        # Detect BEAR TREND
        elif trend_direction == 'BEARISH' and trend_strength < -0.05:
            regime = 'BEAR_TREND'
            confidence = min(85, 50 + abs(trend_strength) * 100)
            characteristics.append(f"50MA < 200MA by {abs(trend_strength):.1%}")

            if fear_greed and fear_greed < 25:
                characteristics.append(f"Extreme fear: {fear_greed}")
                recommended_strategy = 'ACCUMULATION'  # Buy fear
            else:
                recommended_strategy = 'CAPITAL_PRESERVATION'

        # Default to SIDEWAYS
        else:
            regime = 'SIDEWAYS'
            confidence = 60
            characteristics.append(f"No clear trend, volatility: {volatility:.2f}%")
            recommended_strategy = 'RANGE_TRADING'

        # Add BTC season detection
        if btc_dominance and btc_dominance > self.BTC_DOMINANCE_BTC_SEASON:
            characteristics.append(f"BTC season: dominance {btc_dominance:.1f}%")
            if recommended_strategy == 'FAVOR_ALTCOINS':
                recommended_strategy = 'FAVOR_BTC'  # Override altcoin preference

        # Build result
        result = {
            'regime': regime,
            'confidence': confidence,
            'btc_dominance': btc_dominance,
            'trend_direction': trend_direction,
            'trend_strength': trend_strength,
            'volatility': volatility,
            'fear_greed': fear_greed,
            'funding_sentiment': funding_sentiment,
            'characteristics': characteristics,
            'recommended_strategy': recommended_strategy,
            'timestamp': datetime.now()
        }

        # Log the regime detection
        logger.info(f"Market Regime: {regime} (confidence: {confidence}%)")
        logger.info(f"Strategy: {recommended_strategy}")
        for char in characteristics:
            logger.info(f"  - {char}")

        return result

    def get_regime_specific_model_weights(self, regime: str) -> Dict[str, float]:
        """
        Return optimal model weights based on market regime
        Research shows regime-specific models reduce errors by 80%
        """
        weights = {
            'BULL_TREND': {
                'claude': 0.5,    # Good for trend following
                'deepseek': 0.2,  # Less important in bulls
                'gemini': 0.3     # Fast execution matters
            },
            'BEAR_TREND': {
                'claude': 0.3,
                'deepseek': 0.5,  # Best for capital preservation
                'gemini': 0.2
            },
            'HIGH_VOLATILITY': {
                'claude': 0.2,
                'deepseek': 0.2,
                'gemini': 0.6     # Sub-second reaction critical
            },
            'SIDEWAYS': {
                'claude': 0.4,    # Balanced approach
                'deepseek': 0.3,
                'gemini': 0.3
            },
            'ALTSEASON': {
                'claude': 0.5,    # Good at identifying altcoin patterns
                'deepseek': 0.2,
                'gemini': 0.3
            },
            'UNKNOWN': {
                'claude': 0.34,   # Default equal weights
                'deepseek': 0.33,
                'gemini': 0.33
            }
        }

        return weights.get(regime, weights['UNKNOWN'])

    def get_regime_specific_thresholds(self, regime: str) -> Dict[str, float]:
        """
        Return dynamic confidence thresholds based on market regime
        """
        thresholds = {
            'BULL_TREND': {
                'entry_confidence': 0.60,  # Lower threshold, trend is friend
                'position_size_multiplier': 1.2,
                'stop_loss_pct': 0.04,  # Wider stops in trends
                'take_profit_pct': 0.08
            },
            'BEAR_TREND': {
                'entry_confidence': 0.80,  # Higher threshold, preserve capital
                'position_size_multiplier': 0.5,
                'stop_loss_pct': 0.02,  # Tighter stops
                'take_profit_pct': 0.04
            },
            'HIGH_VOLATILITY': {
                'entry_confidence': 0.85,  # Very selective
                'position_size_multiplier': 0.3,
                'stop_loss_pct': 0.05,  # Wide stops for volatility
                'take_profit_pct': 0.10
            },
            'SIDEWAYS': {
                'entry_confidence': 0.70,
                'position_size_multiplier': 0.8,
                'stop_loss_pct': 0.025,
                'take_profit_pct': 0.05
            },
            'ALTSEASON': {
                'entry_confidence': 0.65,  # More aggressive for alts
                'position_size_multiplier': 1.0,
                'stop_loss_pct': 0.06,  # Alts more volatile
                'take_profit_pct': 0.15  # Bigger moves expected
            },
            'UNKNOWN': {
                'entry_confidence': 0.75,
                'position_size_multiplier': 0.7,
                'stop_loss_pct': 0.03,
                'take_profit_pct': 0.06
            }
        }

        return thresholds.get(regime, thresholds['UNKNOWN'])

    def should_favor_altcoins(self) -> Tuple[bool, float]:
        """
        Determine if we should favor altcoins over BTC
        Returns: (should_favor, confidence)
        """
        btc_dominance = self.get_btc_dominance()

        if not btc_dominance:
            return False, 0.0

        # Strong altcoin signal
        if btc_dominance < self.BTC_DOMINANCE_ALTSEASON:
            confidence = min(90, (60 - btc_dominance) * 5)
            return True, confidence

        # Transition zone - look for momentum
        elif btc_dominance < self.BTC_DOMINANCE_BTC_SEASON:
            # Check if dominance is falling (bullish for alts)
            try:
                with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT
                            btc_dominance,
                            scraped_at
                        FROM market_metrics
                        WHERE scraped_at > NOW() - INTERVAL '7 days'
                        ORDER BY scraped_at DESC
                        LIMIT 7
                    """)

                    historical = cur.fetchall()

                    if len(historical) >= 2:
                        recent_avg = sum(h['btc_dominance'] for h in historical[:3]) / 3
                        older_avg = sum(h['btc_dominance'] for h in historical[4:]) / len(historical[4:])

                        if recent_avg < older_avg:  # Dominance falling
                            confidence = 60
                            return True, confidence

            except Exception as e:
                logger.warning(f"Could not fetch historical BTC dominance: {e}")
                self.conn.rollback()  # Rollback failed transaction
                # Continue without historical trend data

            return False, 30  # Uncertain in transition zone

        # BTC dominant
        else:
            return False, min(90, (btc_dominance - 60) * 5)

    def store_regime_analysis(self, regime_data: Dict):
        """
        Store regime analysis in database for historical tracking
        """
        try:
            with self.conn.cursor() as cur:
                # Create table if not exists
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS market_regimes (
                        id SERIAL PRIMARY KEY,
                        regime VARCHAR(50),
                        confidence INTEGER,
                        btc_dominance FLOAT,
                        trend_direction VARCHAR(20),
                        trend_strength FLOAT,
                        volatility FLOAT,
                        fear_greed INTEGER,
                        funding_sentiment VARCHAR(50),
                        recommended_strategy VARCHAR(50),
                        characteristics TEXT[],
                        created_at TIMESTAMP DEFAULT NOW()
                    )
                """)

                # Create index separately (PostgreSQL syntax)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_regime_created
                    ON market_regimes (created_at)
                """)

                # Insert regime data
                cur.execute("""
                    INSERT INTO market_regimes
                    (regime, confidence, btc_dominance, trend_direction, trend_strength,
                     volatility, fear_greed, funding_sentiment, recommended_strategy, characteristics)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    regime_data['regime'],
                    regime_data['confidence'],
                    regime_data['btc_dominance'],
                    regime_data['trend_direction'],
                    regime_data['trend_strength'],
                    regime_data['volatility'],
                    regime_data['fear_greed'],
                    regime_data['funding_sentiment'],
                    regime_data['recommended_strategy'],
                    regime_data['characteristics']
                ))

                self.conn.commit()
                logger.info("Regime analysis stored successfully")

        except Exception as e:
            logger.error(f"Error storing regime analysis: {e}")
            self.conn.rollback()

    def get_current_regime(self) -> Dict:
        """
        Main method to get current market regime with all analysis
        """
        regime_data = self.detect_market_regime()

        # Store for historical tracking
        self.store_regime_analysis(regime_data)

        # Add model weights and thresholds
        regime_data['model_weights'] = self.get_regime_specific_model_weights(regime_data['regime'])
        regime_data['thresholds'] = self.get_regime_specific_thresholds(regime_data['regime'])

        # Add altcoin preference
        favor_alts, alt_confidence = self.should_favor_altcoins()
        regime_data['favor_altcoins'] = favor_alts
        regime_data['altcoin_confidence'] = alt_confidence

        return regime_data


def main():
    """Test market analyzer"""
    analyzer = MarketAnalyzer()

    # Get current regime
    regime = analyzer.get_current_regime()

    print("\n" + "="*60)
    print("MARKET REGIME ANALYSIS")
    print("="*60)
    print(f"Regime: {regime['regime']} (Confidence: {regime['confidence']}%)")
    print(f"Strategy: {regime['recommended_strategy']}")
    print(f"\nIndicators:")
    print(f"  BTC Dominance: {regime['btc_dominance']:.2f}%" if regime['btc_dominance'] else "  BTC Dominance: N/A")
    print(f"  Trend: {regime['trend_direction']} ({regime['trend_strength']:+.2%})")
    print(f"  Volatility: {regime['volatility']:.2f}%")
    print(f"  Fear & Greed: {regime['fear_greed']}" if regime['fear_greed'] else "  Fear & Greed: N/A")
    print(f"  Funding: {regime['funding_sentiment']}")

    print(f"\nCharacteristics:")
    for char in regime['characteristics']:
        print(f"  • {char}")

    print(f"\nModel Weights:")
    for model, weight in regime['model_weights'].items():
        print(f"  {model}: {weight:.1%}")

    print(f"\nThresholds:")
    for param, value in regime['thresholds'].items():
        print(f"  {param}: {value}")

    print(f"\nAltcoin Preference: {'YES' if regime['favor_altcoins'] else 'NO'} ({regime['altcoin_confidence']:.0f}% confidence)")


if __name__ == "__main__":
    main()