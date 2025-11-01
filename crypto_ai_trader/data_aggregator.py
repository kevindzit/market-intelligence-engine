"""
Data Aggregation Layer
Queries PostgreSQL database and generates concise market summaries for AI analysis
Reduces data from thousands of rows to ~500 token summaries
Now enhanced with liquidation prediction!
"""

import psycopg2
from datetime import datetime, timedelta
from typing import Dict, Optional, List
import config
from liquidation_predictor import get_liquidation_predictor


def get_db_connection():
    """Get PostgreSQL connection"""
    return psycopg2.connect(
        host=config.DB_HOST,
        port=config.DB_PORT,
        database=config.DB_NAME,
        user=config.DB_USER,
        password=config.DB_PASSWORD
    )


def get_sentiment_summary(token: str, hours: int = 6) -> Dict:
    """
    Aggregate Twitter sentiment data over time window

    Returns:
        Dict with sentiment metrics, volume, whale activity
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Aggregate sentiment over time window
        cursor.execute("""
            SELECT
                AVG(sentiment_score) as avg_sentiment,
                STDDEV(sentiment_score) as sentiment_volatility,
                COUNT(*) as tweet_count,
                COUNT(*) FILTER (WHERE bot_probability < 0.3) as quality_tweets,
                COUNT(*) FILTER (WHERE is_whale = true) as whale_mentions,
                AVG(influence_weight) as avg_influence,
                MAX(volume_spike) as max_volume_spike,
                AVG(sentiment_velocity) as avg_velocity,
                MAX(momentum_score) as max_momentum
            FROM twitter_sentiment
            WHERE token = %s
              AND scraped_at > NOW() - INTERVAL '%s hours'
        """, (token, hours))

        result = cursor.fetchone()

        if not result or result[2] == 0:  # No tweets found
            return {'has_data': False}

        # Determine sentiment trend
        sentiment = float(result[0]) if result[0] else 0
        if sentiment > 0.3:
            trend = "Strong Bullish"
        elif sentiment > 0.1:
            trend = "Bullish"
        elif sentiment < -0.3:
            trend = "Strong Bearish"
        elif sentiment < -0.1:
            trend = "Bearish"
        else:
            trend = "Neutral"

        # Calculate velocity trend
        velocity = float(result[7]) if result[7] else 0
        if velocity > 0.10:
            velocity_trend = "Rapidly Accelerating"
        elif velocity > 0.05:
            velocity_trend = "Accelerating"
        elif velocity < -0.10:
            velocity_trend = "Rapidly Declining"
        elif velocity < -0.05:
            velocity_trend = "Declining"
        else:
            velocity_trend = "Stable"

        return {
            'has_data': True,
            'sentiment': round(sentiment, 4),
            'trend': trend,
            'volatility': round(float(result[1] or 0), 4),
            'tweet_count': int(result[2]),
            'quality_tweets': int(result[3]),
            'whale_mentions': int(result[4]),
            'avg_influence': round(float(result[5] or 0), 4),
            'max_volume_spike': round(float(result[6] or 0), 2),
            'velocity': round(velocity, 4),
            'velocity_trend': velocity_trend,
            'max_momentum': round(float(result[8] or 0), 4)
        }

    finally:
        cursor.close()
        conn.close()


def get_price_context(token: str, hours: int = 24) -> Dict:
    """
    Get price action context

    Returns:
        Current price, recent changes, support/resistance
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Get recent OHLCV data
        cursor.execute("""
            SELECT close, high, low, volume, timestamp
            FROM crypto_ohlcv
            WHERE token = %s
              AND timestamp > NOW() - INTERVAL '%s hours'
            ORDER BY timestamp DESC
            LIMIT 100
        """, (token, hours))

        rows = cursor.fetchall()

        if not rows:
            return {'has_data': False}

        # Current price
        current_price = float(rows[0][0])

        # Calculate price changes
        if len(rows) >= 12:  # Need at least 1 hour of 5-min data
            price_1h_ago = float(rows[11][0])
            change_1h = ((current_price - price_1h_ago) / price_1h_ago) * 100
        else:
            change_1h = 0

        if len(rows) >= 72:  # 6 hours
            price_6h_ago = float(rows[71][0])
            change_6h = ((current_price - price_6h_ago) / price_6h_ago) * 100
        else:
            change_6h = 0

        # 24h change
        if len(rows) >= 99:
            price_24h_ago = float(rows[99][0])
            change_24h = ((current_price - price_24h_ago) / price_24h_ago) * 100
        else:
            change_24h = 0

        # Support and resistance (recent highs/lows)
        recent_high = max([float(row[1]) for row in rows[:72]]) if len(rows) >= 72 else current_price
        recent_low = min([float(row[2]) for row in rows[:72]]) if len(rows) >= 72 else current_price

        # Calculate volatility (ATR approximation)
        if len(rows) >= 20:
            ranges = [float(row[1]) - float(row[2]) for row in rows[:20]]
            avg_range = sum(ranges) / len(ranges)
            volatility_pct = (avg_range / current_price) * 100
        else:
            volatility_pct = 0

        return {
            'has_data': True,
            'current_price': round(current_price, 2),
            'change_1h': round(change_1h, 2),
            'change_6h': round(change_6h, 2),
            'change_24h': round(change_24h, 2),
            'resistance': round(recent_high, 2),
            'support': round(recent_low, 2),
            'volatility': round(volatility_pct, 2)
        }

    finally:
        cursor.close()
        conn.close()


def get_market_conditions(token: str) -> Dict:
    """
    Get broader market conditions (OI, funding, liquidations, fear/greed)

    Returns:
        Dict with market condition indicators
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    conditions = {}

    try:
        # Open Interest (most recent + 1h change)
        cursor.execute("""
            SELECT
                open_interest_usd,
                timestamp
            FROM open_interest
            WHERE token = %s
            ORDER BY timestamp DESC
            LIMIT 1
        """, (token,))

        oi_result = cursor.fetchone()
        if oi_result:
            current_oi = float(oi_result[0])

            # Get OI from 1 hour ago
            cursor.execute("""
                SELECT open_interest_usd
                FROM open_interest
                WHERE token = %s
                  AND timestamp <= NOW() - INTERVAL '1 hour'
                ORDER BY timestamp DESC
                LIMIT 1
            """, (token,))

            oi_1h = cursor.fetchone()
            if oi_1h:
                oi_change = ((current_oi - float(oi_1h[0])) / float(oi_1h[0])) * 100
            else:
                oi_change = 0

            conditions['oi_usd'] = round(current_oi, 0)
            conditions['oi_change_1h'] = round(oi_change, 2)

            # Determine leverage status
            if oi_change > 15:
                conditions['leverage_status'] = "Rapid buildup (risky)"
            elif oi_change < -15:
                conditions['leverage_status'] = "Mass deleveraging"
            else:
                conditions['leverage_status'] = "Normal"
        else:
            conditions['oi_usd'] = None

        # Funding Rate (most recent)
        cursor.execute("""
            SELECT funding_rate
            FROM funding_rates
            WHERE token = %s
            ORDER BY scraped_at DESC
            LIMIT 1
        """, (token,))

        funding_result = cursor.fetchone()
        if funding_result:
            funding_rate = float(funding_result[0])
            conditions['funding_rate'] = round(funding_rate * 100, 4)  # Convert to %

            # Interpret funding rate
            if funding_rate > 0.01:
                conditions['funding_interpretation'] = "Extremely overleveraged longs (reversal risk)"
            elif funding_rate > 0.005:
                conditions['funding_interpretation'] = "Overleveraged longs"
            elif funding_rate < -0.01:
                conditions['funding_interpretation'] = "Extremely overleveraged shorts (short squeeze risk)"
            elif funding_rate < -0.005:
                conditions['funding_interpretation'] = "Overleveraged shorts"
            else:
                conditions['funding_interpretation'] = "Balanced"
        else:
            conditions['funding_rate'] = None

        # Recent liquidations (last 15 min)
        cursor.execute("""
            SELECT
                SUM(liquidation_value) as total_liquidated,
                SUM(CASE WHEN side = 'LONG' THEN liquidation_value ELSE 0 END) as longs_liquidated,
                SUM(CASE WHEN side = 'SHORT' THEN liquidation_value ELSE 0 END) as shorts_liquidated
            FROM liquidations
            WHERE token = %s
              AND timestamp > NOW() - INTERVAL '15 minutes'
        """, (token,))

        liq_result = cursor.fetchone()
        if liq_result and liq_result[0]:
            total_liq = float(liq_result[0] or 0)
            longs_liq = float(liq_result[1] or 0)
            shorts_liq = float(liq_result[2] or 0)

            conditions['liquidations_15m'] = round(total_liq, 0)

            if total_liq > 500000:  # >$500k in 15 min
                conditions['liquidation_status'] = "Capitulation event"
            elif total_liq > 100000:
                conditions['liquidation_status'] = "High liquidations"
            else:
                conditions['liquidation_status'] = "Normal"

            # Determine which side is getting squeezed
            if longs_liq > shorts_liq * 2:
                conditions['squeeze_side'] = "Long squeeze (selling pressure)"
            elif shorts_liq > longs_liq * 2:
                conditions['squeeze_side'] = "Short squeeze (buying pressure)"
            else:
                conditions['squeeze_side'] = "Balanced"
        else:
            conditions['liquidations_15m'] = 0
            conditions['liquidation_status'] = "Normal"

        # Fear & Greed Index (most recent)
        cursor.execute("""
            SELECT value, classification
            FROM fear_greed_index
            ORDER BY timestamp DESC
            LIMIT 1
        """)

        fg_result = cursor.fetchone()
        if fg_result:
            conditions['fear_greed_value'] = int(fg_result[0])
            conditions['fear_greed_class'] = fg_result[1]
        else:
            conditions['fear_greed_value'] = None

        return conditions

    finally:
        cursor.close()
        conn.close()


def format_market_summary(token: str) -> str:
    """
    Generate complete market summary for AI analysis
    Now includes liquidation cascade prediction!

    Returns:
        Formatted text summary (~500 tokens)
    """

    # Gather all data
    sentiment = get_sentiment_summary(token, hours=config.SENTIMENT_LOOKBACK_HOURS)
    price = get_price_context(token, hours=config.PRICE_LOOKBACK_HOURS)
    conditions = get_market_conditions(token)

    # Get liquidation predictor
    liquidation_predictor = get_liquidation_predictor()

    # Build formatted summary
    summary = f"""TOKEN: {token}
TIMESTAMP: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

=== TWITTER SENTIMENT (Last {config.SENTIMENT_LOOKBACK_HOURS}h) ===
"""

    if sentiment.get('has_data'):
        summary += f"""Average Sentiment: {sentiment['sentiment']:+.4f} ({sentiment['trend']})
Tweet Volume: {sentiment['tweet_count']} tweets ({sentiment['quality_tweets']} quality, {sentiment['whale_mentions']} whale mentions)
Volume Spike: {sentiment['max_volume_spike']}x baseline
Sentiment Velocity: {sentiment['velocity']:+.4f} ({sentiment['velocity_trend']})
Momentum Score: {sentiment['max_momentum']:.4f}
"""
    else:
        summary += "No sentiment data available (low tweet volume)\n"

    summary += f"""
=== PRICE ACTION (Last {config.PRICE_LOOKBACK_HOURS}h) ===
"""

    if price.get('has_data'):
        summary += f"""Current Price: ${price['current_price']:,.2f}
1H Change: {price['change_1h']:+.2f}%
6H Change: {price['change_6h']:+.2f}%
24H Change: {price['change_24h']:+.2f}%
Support: ${price['support']:,.2f}
Resistance: ${price['resistance']:,.2f}
Volatility (ATR): {price['volatility']:.2f}%
"""
    else:
        summary += "No price data available\n"

    summary += """
=== MARKET CONDITIONS ===
"""

    if conditions.get('oi_usd'):
        summary += f"""Open Interest: ${conditions['oi_usd']:,.0f} ({conditions['oi_change_1h']:+.2f}% 1H)
Leverage Status: {conditions['leverage_status']}
"""

    if conditions.get('funding_rate') is not None:
        summary += f"""Funding Rate: {conditions['funding_rate']:.4f}%
Funding Status: {conditions['funding_interpretation']}
"""

    if conditions.get('liquidations_15m') is not None:
        summary += f"""Recent Liquidations: ${conditions['liquidations_15m']:,.0f} (15min)
Liquidation Status: {conditions['liquidation_status']}
"""
        if conditions.get('squeeze_side'):
            summary += f"Squeeze Direction: {conditions['squeeze_side']}\n"

    if conditions.get('fear_greed_value'):
        summary += f"""Fear & Greed Index: {conditions['fear_greed_value']}/100 ({conditions['fear_greed_class']})
"""

    # Add liquidation analysis if price data available
    if price.get('has_data'):
        current_price = price['current_price']

        # Get liquidation-enhanced summary
        liquidation_summary = liquidation_predictor.get_enhanced_summary(token, current_price)
        summary += liquidation_summary

    return summary


# Test function
if __name__ == "__main__":
    print("Testing data aggregation...\n")

    token = 'BTC'

    print(f"Generating market summary for {token}...")
    print("=" * 70)

    summary = format_market_summary(token)
    print(summary)

    print("=" * 70)
    print(f"\nSummary length: {len(summary)} characters (~{len(summary.split())} words)")
