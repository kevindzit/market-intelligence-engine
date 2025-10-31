"""
Liquidation Analysis Helper Functions
Functions for analyzing liquidation data to detect reversals
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


def get_recent_liquidations(token: str, minutes: int = 5) -> List[Dict]:
    """
    Get recent liquidations for a token

    Args:
        token: Token symbol
        minutes: How many minutes back to look

    Returns:
        List of liquidation records
    """
    conn = get_db_connection()
    if not conn:
        return []

    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT side, liquidation_value, price, quantity, timestamp
            FROM liquidations
            WHERE token = %s
            AND timestamp > NOW() - INTERVAL '%s minutes'
            ORDER BY timestamp DESC
        """, (token, minutes))

        results = cursor.fetchall()
        liquidations = []

        for row in results:
            liquidations.append({
                'side': row[0],
                'value': float(row[1]),
                'price': float(row[2]) if row[2] else None,
                'quantity': float(row[3]) if row[3] else None,
                'timestamp': row[4]
            })

        return liquidations

    except Exception as e:
        print(f"[ERROR] Failed to get liquidations for {token}: {e}")
        return []

    finally:
        cursor.close()
        conn.close()


def get_liquidation_summary(token: str, minutes: int = 30) -> Dict:
    """
    Get liquidation summary for a token

    Returns:
        Dict with total value, long/short breakdown, signals
    """
    conn = get_db_connection()
    if not conn:
        return {}

    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                COUNT(*) as count,
                SUM(liquidation_value) as total_value,
                SUM(CASE WHEN side = 'BUY' THEN liquidation_value ELSE 0 END) as short_liquidations,
                SUM(CASE WHEN side = 'SELL' THEN liquidation_value ELSE 0 END) as long_liquidations,
                MAX(liquidation_value) as max_single
            FROM liquidations
            WHERE token = %s
            AND timestamp > NOW() - INTERVAL '%s minutes'
        """, (token, minutes))

        result = cursor.fetchone()

        if not result or not result[1]:
            return {'has_liquidations': False}

        total_value = float(result[1])
        short_liq = float(result[2]) if result[2] else 0
        long_liq = float(result[3]) if result[3] else 0

        # Calculate percentages
        long_pct = (long_liq / total_value * 100) if total_value > 0 else 0
        short_pct = (short_liq / total_value * 100) if total_value > 0 else 0

        # Determine signal
        signal = 'NEUTRAL'
        if total_value > 100000:  # Significant liquidations
            if long_pct > 70:
                signal = 'LONG_SQUEEZE'  # Longs squeezed = potential bottom
            elif short_pct > 70:
                signal = 'SHORT_SQUEEZE'  # Shorts squeezed = potential top

        return {
            'has_liquidations': True,
            'count': int(result[0]),
            'total_value': total_value,
            'long_liquidations': long_liq,
            'short_liquidations': short_liq,
            'long_percentage': long_pct,
            'short_percentage': short_pct,
            'max_single': float(result[4]) if result[4] else 0,
            'signal': signal
        }

    except Exception as e:
        print(f"[ERROR] Failed to get liquidation summary for {token}: {e}")
        return {}

    finally:
        cursor.close()
        conn.close()


def get_extreme_liquidations(threshold: float = 1000000) -> List[Dict]:
    """
    Get tokens with extreme liquidation events

    Args:
        threshold: Minimum total liquidation value

    Returns:
        List of tokens with extreme liquidations
    """
    conn = get_db_connection()
    if not conn:
        return []

    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                token,
                SUM(liquidation_value) as total_value,
                COUNT(*) as count,
                SUM(CASE WHEN side = 'BUY' THEN liquidation_value ELSE 0 END) as short_liq,
                SUM(CASE WHEN side = 'SELL' THEN liquidation_value ELSE 0 END) as long_liq
            FROM liquidations
            WHERE timestamp > NOW() - INTERVAL '30 minutes'
            GROUP BY token
            HAVING SUM(liquidation_value) > %s
            ORDER BY SUM(liquidation_value) DESC
        """, (threshold,))

        results = cursor.fetchall()
        extreme_tokens = []

        for row in results:
            total_value = float(row[1])
            short_liq = float(row[3]) if row[3] else 0
            long_liq = float(row[4]) if row[4] else 0

            signal = 'HIGH_VOLATILITY'
            if long_liq > short_liq * 2:
                signal = 'LONG_SQUEEZE_REVERSAL'
            elif short_liq > long_liq * 2:
                signal = 'SHORT_SQUEEZE_REVERSAL'

            extreme_tokens.append({
                'token': row[0],
                'total_value': total_value,
                'count': int(row[2]),
                'signal': signal,
                'long_percentage': (long_liq / total_value * 100) if total_value > 0 else 0,
                'short_percentage': (short_liq / total_value * 100) if total_value > 0 else 0
            })

        return extreme_tokens

    except Exception as e:
        print(f"[ERROR] Failed to get extreme liquidations: {e}")
        return []

    finally:
        cursor.close()
        conn.close()


def is_capitulation_event(token: str) -> bool:
    """
    Check if token is experiencing capitulation (extreme liquidations)

    Returns:
        True if capitulation detected
    """
    summary = get_liquidation_summary(token, minutes=15)

    if not summary.get('has_liquidations'):
        return False

    # Capitulation = over $500K liquidated in 15 minutes
    # with heavy bias to one side
    total = summary.get('total_value', 0)
    long_pct = summary.get('long_percentage', 0)
    short_pct = summary.get('short_percentage', 0)

    return total > 500000 and (long_pct > 75 or short_pct > 75)


def get_liquidation_velocity(token: str) -> Optional[float]:
    """
    Calculate rate of liquidation acceleration

    Returns:
        Velocity score (positive = accelerating liquidations)
    """
    conn = get_db_connection()
    if not conn:
        return None

    try:
        cursor = conn.cursor()

        # Get liquidations in 5-minute buckets
        cursor.execute("""
            SELECT
                DATE_TRUNC('minute', timestamp) -
                    (EXTRACT(minute FROM timestamp)::integer % 5) * INTERVAL '1 minute' as bucket,
                SUM(liquidation_value) as total
            FROM liquidations
            WHERE token = %s
            AND timestamp > NOW() - INTERVAL '30 minutes'
            GROUP BY bucket
            ORDER BY bucket DESC
            LIMIT 6
        """, (token,))

        results = cursor.fetchall()

        if len(results) < 3:
            return None

        # Calculate velocity (rate of change)
        recent = float(results[0][1]) if results[0][1] else 0
        older = float(results[2][1]) if results[2][1] else 0

        if older > 0:
            velocity = (recent - older) / older
        else:
            velocity = 1.0 if recent > 0 else 0

        return velocity

    except Exception as e:
        print(f"[ERROR] Failed to calculate liquidation velocity for {token}: {e}")
        return None

    finally:
        cursor.close()
        conn.close()


# Test function
def test_liquidation_functions():
    """Test liquidation functions"""
    print("Testing liquidation functions...")

    token = 'BTC'

    # Get recent liquidations
    recent = get_recent_liquidations(token, 30)
    if recent:
        print(f"\nRecent {token} liquidations: {len(recent)}")
        for liq in recent[:3]:
            print(f"  {liq['side']}: ${liq['value']:,.0f} at ${liq['price']:,.2f}")

    # Get summary
    summary = get_liquidation_summary(token, 30)
    if summary.get('has_liquidations'):
        print(f"\n{token} Liquidation Summary (30 min):")
        print(f"  Total: ${summary['total_value']:,.0f}")
        print(f"  Longs: {summary['long_percentage']:.1f}%")
        print(f"  Shorts: {summary['short_percentage']:.1f}%")
        print(f"  Signal: {summary['signal']}")

    # Check for extreme events
    extreme = get_extreme_liquidations(100000)
    if extreme:
        print(f"\nExtreme liquidation events:")
        for t in extreme:
            print(f"  {t['token']}: ${t['total_value']:,.0f} - {t['signal']}")

    # Check capitulation
    is_cap = is_capitulation_event(token)
    print(f"\n{token} capitulation event: {is_cap}")


if __name__ == "__main__":
    test_liquidation_functions()