"""
Funding Rates Analysis Helper Functions
Functions for analyzing perpetual futures funding rates
Critical for detecting overleveraged positions and reversals
"""

import os
import psycopg2
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from dotenv import load_dotenv

load_dotenv()

# Database configuration
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '54594')
DB_NAME = os.getenv('DB_NAME', 'postgres')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'postgres')


def get_db_connection():
    """Get database connection"""
    try:
        return psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )
    except Exception as e:
        print(f"[ERROR] Database connection failed: {e}")
        return None


def get_current_funding_rate(token: str) -> Optional[Dict]:
    """
    Get the most recent funding rate for a token

    Returns:
        Dict with funding_rate, mark_price, next_funding_time
    """
    conn = get_db_connection()
    if not conn:
        return None

    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT funding_rate, mark_price, index_price, next_funding_time, scraped_at
            FROM funding_rates
            WHERE token = %s
            ORDER BY scraped_at DESC
            LIMIT 1
        """, (token,))

        result = cursor.fetchone()
        if not result:
            return None

        return {
            'funding_rate': float(result[0]),
            'funding_rate_pct': float(result[0]) * 100,
            'mark_price': float(result[1]) if result[1] else None,
            'index_price': float(result[2]) if result[2] else None,
            'next_funding_time': result[3],
            'last_updated': result[4]
        }

    except Exception as e:
        print(f"[ERROR] Failed to get funding rate for {token}: {e}")
        return None

    finally:
        cursor.close()
        conn.close()


def is_overleveraged(token: str, side: str = 'both') -> bool:
    """
    Check if market is overleveraged

    Args:
        token: Token symbol
        side: 'longs', 'shorts', or 'both'

    Returns:
        True if overleveraged (potential reversal signal)
    """
    funding = get_current_funding_rate(token)
    if not funding:
        return False

    rate = funding['funding_rate']

    # Threshold: ±0.01% (0.0001 in decimal)
    if side == 'longs':
        return rate > 0.0001
    elif side == 'shorts':
        return rate < -0.0001
    else:  # both
        return abs(rate) > 0.0001


def get_funding_signal(token: str) -> Optional[str]:
    """
    Get trading signal from funding rate

    Returns:
        'EXTREME_SHORT' - Shorts overleveraged, potential bounce
        'SHORT' - Negative funding, slight short bias
        'NEUTRAL' - Balanced market
        'LONG' - Positive funding, slight long bias
        'EXTREME_LONG' - Longs overleveraged, potential dump
    """
    funding = get_current_funding_rate(token)
    if not funding:
        return None

    rate = funding['funding_rate']

    if rate < -0.0001:
        return 'EXTREME_SHORT'
    elif rate < -0.00005:
        return 'SHORT'
    elif rate > 0.0001:
        return 'EXTREME_LONG'
    elif rate > 0.00005:
        return 'LONG'
    else:
        return 'NEUTRAL'


def get_funding_history(token: str, hours: int = 24) -> List[Dict]:
    """
    Get funding rate history for a token

    Args:
        token: Token symbol
        hours: Hours of history to retrieve

    Returns:
        List of funding rate records
    """
    conn = get_db_connection()
    if not conn:
        return []

    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT funding_rate, mark_price, scraped_at
            FROM funding_rates
            WHERE token = %s
            AND scraped_at > NOW() - INTERVAL '%s hours'
            ORDER BY scraped_at DESC
        """, (token, hours))

        results = cursor.fetchall()
        history = []

        for row in results:
            history.append({
                'funding_rate': float(row[0]),
                'funding_rate_pct': float(row[0]) * 100,
                'mark_price': float(row[1]) if row[1] else None,
                'timestamp': row[2]
            })

        return history

    except Exception as e:
        print(f"[ERROR] Failed to get funding history for {token}: {e}")
        return []

    finally:
        cursor.close()
        conn.close()


def get_funding_trend(token: str, hours: int = 24) -> Optional[str]:
    """
    Analyze funding rate trend over time

    Returns:
        'INCREASING' - Getting more positive (longs building up)
        'DECREASING' - Getting more negative (shorts building up)
        'STABLE' - Not much change
    """
    history = get_funding_history(token, hours)
    if len(history) < 3:
        return None

    # Compare recent vs older rates
    recent_avg = sum(h['funding_rate'] for h in history[:3]) / 3
    older_avg = sum(h['funding_rate'] for h in history[-3:]) / 3

    diff = recent_avg - older_avg

    if diff > 0.00002:  # 0.002%
        return 'INCREASING'
    elif diff < -0.00002:
        return 'DECREASING'
    else:
        return 'STABLE'


def get_extreme_tokens(threshold: float = 0.0001) -> List[Dict]:
    """
    Get all tokens with extreme funding rates

    Args:
        threshold: Funding rate threshold (default 0.01%)

    Returns:
        List of tokens with extreme rates
    """
    conn = get_db_connection()
    if not conn:
        return []

    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT ON (token) token, funding_rate, mark_price
            FROM funding_rates
            WHERE ABS(funding_rate) > %s
            ORDER BY token, scraped_at DESC
        """, (threshold,))

        results = cursor.fetchall()
        extreme_tokens = []

        for row in results:
            extreme_tokens.append({
                'token': row[0],
                'funding_rate': float(row[1]),
                'funding_rate_pct': float(row[1]) * 100,
                'mark_price': float(row[2]) if row[2] else None,
                'signal': 'SHORTS_OVERLEVERAGED' if row[1] < 0 else 'LONGS_OVERLEVERAGED'
            })

        return sorted(extreme_tokens, key=lambda x: abs(x['funding_rate']), reverse=True)

    except Exception as e:
        print(f"[ERROR] Failed to get extreme tokens: {e}")
        return []

    finally:
        cursor.close()
        conn.close()


def get_funding_summary(token: str) -> Dict:
    """
    Get comprehensive funding rate summary

    Returns complete picture of funding rate state
    """
    current = get_current_funding_rate(token)
    if not current:
        return {}

    signal = get_funding_signal(token)
    trend = get_funding_trend(token, 24)
    overleveraged_longs = is_overleveraged(token, 'longs')
    overleveraged_shorts = is_overleveraged(token, 'shorts')

    return {
        'current': current,
        'signal': signal,
        'trend': trend,
        'overleveraged_longs': overleveraged_longs,
        'overleveraged_shorts': overleveraged_shorts,
        'reversal_likely': overleveraged_longs or overleveraged_shorts
    }


# Test function
def test_funding_functions():
    """Test funding rate functions with BTC"""
    print("Testing funding rate functions...")

    token = 'BTC'

    # Get current funding rate
    funding = get_current_funding_rate(token)
    if funding:
        print(f"\nCurrent {token} Funding Rate:")
        print(f"  Rate: {funding['funding_rate_pct']:.4f}%")
        print(f"  Mark Price: ${funding['mark_price']:,.2f}")
        print(f"  Next Funding: {funding['next_funding_time']}")

    # Get signal
    signal = get_funding_signal(token)
    print(f"\nFunding Signal: {signal}")

    # Check if overleveraged
    longs_over = is_overleveraged(token, 'longs')
    shorts_over = is_overleveraged(token, 'shorts')
    print(f"\nOverleveraged Status:")
    print(f"  Longs: {longs_over}")
    print(f"  Shorts: {shorts_over}")

    # Get trend
    trend = get_funding_trend(token, 24)
    print(f"\nFunding Trend (24h): {trend}")

    # Get extreme tokens
    extreme = get_extreme_tokens(0.00005)
    if extreme:
        print(f"\nExtreme Funding Rates:")
        for t in extreme[:5]:
            print(f"  {t['token']}: {t['funding_rate_pct']:.4f}% - {t['signal']}")


if __name__ == "__main__":
    test_funding_functions()