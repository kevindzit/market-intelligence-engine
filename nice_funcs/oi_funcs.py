"""
Open Interest Analysis Helper Functions
Functions for analyzing OI data to detect leverage buildups and deleverage events
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


def get_current_oi(token: str) -> Optional[Dict]:
    """
    Get most recent OI data for a token

    Returns:
        Dict with current OI data or None
    """
    conn = get_db_connection()
    if not conn:
        return None

    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT open_interest_usd, open_interest_contracts,
                   mark_price, timestamp
            FROM open_interest
            WHERE token = %s
            ORDER BY timestamp DESC
            LIMIT 1
        """, (token,))

        result = cursor.fetchone()

        if result:
            return {
                'oi_usd': float(result[0]) if result[0] else 0,
                'oi_contracts': float(result[1]) if result[1] else 0,
                'mark_price': float(result[2]) if result[2] else 0,
                'timestamp': result[3]
            }

        return None

    except Exception as e:
        print(f"[ERROR] Failed to get current OI for {token}: {e}")
        return None

    finally:
        cursor.close()
        conn.close()


def get_oi_change(token: str, hours: int = 1) -> Optional[float]:
    """
    Calculate OI change percentage over time period

    Args:
        token: Token symbol
        hours: Lookback period in hours

    Returns:
        Change percentage or None
    """
    conn = get_db_connection()
    if not conn:
        return None

    try:
        cursor = conn.cursor()

        # Get current OI
        cursor.execute("""
            SELECT open_interest_usd
            FROM open_interest
            WHERE token = %s
            ORDER BY timestamp DESC
            LIMIT 1
        """, (token,))

        current_result = cursor.fetchone()
        if not current_result:
            return None

        current_oi = float(current_result[0])

        # Get historical OI
        cursor.execute("""
            SELECT open_interest_usd
            FROM open_interest
            WHERE token = %s
            AND timestamp <= NOW() - INTERVAL '%s hours'
            ORDER BY timestamp DESC
            LIMIT 1
        """, (token, hours))

        historical_result = cursor.fetchone()
        if not historical_result:
            return None

        historical_oi = float(historical_result[0])

        if historical_oi > 0:
            change_pct = ((current_oi - historical_oi) / historical_oi) * 100
            return change_pct

        return None

    except Exception as e:
        print(f"[ERROR] Failed to calculate OI change for {token}: {e}")
        return None

    finally:
        cursor.close()
        conn.close()


def get_oi_velocity(token: str) -> Optional[float]:
    """
    Calculate rate of OI change (acceleration)

    Returns:
        Velocity score (positive = OI increasing rapidly)
    """
    conn = get_db_connection()
    if not conn:
        return None

    try:
        cursor = conn.cursor()

        # Get OI in 15-minute buckets for last hour
        cursor.execute("""
            SELECT
                DATE_TRUNC('minute', timestamp) -
                    (EXTRACT(minute FROM timestamp)::integer % 15) * INTERVAL '1 minute' as bucket,
                AVG(open_interest_usd) as avg_oi
            FROM open_interest
            WHERE token = %s
            AND timestamp > NOW() - INTERVAL '1 hour'
            GROUP BY bucket
            ORDER BY bucket DESC
            LIMIT 4
        """, (token,))

        results = cursor.fetchall()

        if len(results) < 3:
            return None

        # Calculate velocity (rate of change)
        recent_oi = float(results[0][1]) if results[0][1] else 0
        older_oi = float(results[2][1]) if results[2][1] else 0

        if older_oi > 0:
            velocity = (recent_oi - older_oi) / older_oi
        else:
            velocity = 1.0 if recent_oi > 0 else 0

        return velocity

    except Exception as e:
        print(f"[ERROR] Failed to calculate OI velocity for {token}: {e}")
        return None

    finally:
        cursor.close()
        conn.close()


def get_high_oi_tokens(min_oi_usd: float = 100000000) -> List[Dict]:
    """
    Get tokens with high open interest (high leverage)

    Args:
        min_oi_usd: Minimum OI in USD (default $100M)

    Returns:
        List of tokens with high OI
    """
    conn = get_db_connection()
    if not conn:
        return []

    try:
        cursor = conn.cursor()

        # Get most recent OI for each token
        cursor.execute("""
            SELECT DISTINCT ON (token)
                token,
                open_interest_usd,
                open_interest_contracts,
                mark_price,
                timestamp
            FROM open_interest
            WHERE timestamp > NOW() - INTERVAL '30 minutes'
            ORDER BY token, timestamp DESC
        """)

        results = cursor.fetchall()
        high_oi_tokens = []

        for row in results:
            oi_usd = float(row[1])

            if oi_usd >= min_oi_usd:
                token = row[0]

                # Get 1h and 24h change
                change_1h = get_oi_change(token, hours=1)
                change_24h = get_oi_change(token, hours=24)

                high_oi_tokens.append({
                    'token': token,
                    'oi_usd': oi_usd,
                    'oi_contracts': float(row[2]),
                    'mark_price': float(row[3]),
                    'timestamp': row[4],
                    'change_1h': change_1h,
                    'change_24h': change_24h
                })

        # Sort by OI value
        high_oi_tokens.sort(key=lambda x: x['oi_usd'], reverse=True)

        return high_oi_tokens

    except Exception as e:
        print(f"[ERROR] Failed to get high OI tokens: {e}")
        return []

    finally:
        cursor.close()
        conn.close()


def detect_leverage_buildup(token: str) -> bool:
    """
    Detect if token is experiencing rapid leverage buildup

    Returns:
        True if dangerous leverage buildup detected
    """
    # Check 1h and 4h OI change
    change_1h = get_oi_change(token, hours=1)
    change_4h = get_oi_change(token, hours=4)

    if not change_1h or not change_4h:
        return False

    # Rapid buildup = >15% increase in 1h OR >30% in 4h
    if change_1h > 15 or change_4h > 30:
        return True

    return False


def detect_deleveraging(token: str) -> bool:
    """
    Detect if token is experiencing mass deleveraging

    Returns:
        True if mass deleveraging detected
    """
    change_1h = get_oi_change(token, hours=1)

    if not change_1h:
        return False

    # Mass deleveraging = >20% decrease in 1h
    if change_1h < -20:
        return True

    return False


def get_oi_summary(token: str) -> Dict:
    """
    Get comprehensive OI summary for a token

    Returns:
        Dict with current OI, changes, and signals
    """
    current = get_current_oi(token)

    if not current:
        return {'has_data': False}

    change_1h = get_oi_change(token, hours=1)
    change_4h = get_oi_change(token, hours=4)
    change_24h = get_oi_change(token, hours=24)
    velocity = get_oi_velocity(token)

    # Determine signal
    signal = 'NEUTRAL'
    if change_1h:
        if change_1h > 15:
            signal = 'LEVERAGE_BUILDUP'
        elif change_1h < -20:
            signal = 'MASS_DELEVERAGING'

    return {
        'has_data': True,
        'token': token,
        'current_oi_usd': current['oi_usd'],
        'current_oi_contracts': current['oi_contracts'],
        'mark_price': current['mark_price'],
        'change_1h': change_1h,
        'change_4h': change_4h,
        'change_24h': change_24h,
        'velocity': velocity,
        'signal': signal,
        'timestamp': current['timestamp']
    }


# Test function
def test_oi_functions():
    """Test OI helper functions"""
    print("Testing OI functions...")

    token = 'BTC'

    # Get current OI
    current = get_current_oi(token)
    if current:
        print(f"\n{token} Current OI:")
        print(f"  USD Value: ${current['oi_usd']:,.0f}")
        print(f"  Contracts: {current['oi_contracts']:,.2f}")
        print(f"  Mark Price: ${current['mark_price']:,.2f}")

    # Get changes
    change_1h = get_oi_change(token, hours=1)
    change_24h = get_oi_change(token, hours=24)
    if change_1h or change_24h:
        print(f"\n{token} OI Changes:")
        if change_1h:
            print(f"  1h: {change_1h:+.2f}%")
        if change_24h:
            print(f"  24h: {change_24h:+.2f}%")

    # Get high OI tokens
    high_oi = get_high_oi_tokens(min_oi_usd=50000000)
    if high_oi:
        print(f"\nHigh OI Tokens (>$50M):")
        for t in high_oi[:5]:
            print(f"  {t['token']}: ${t['oi_usd']:,.0f} "
                  f"(1h: {t['change_1h']:+.1f}% if t['change_1h'] else 'N/A')")

    # Get summary
    summary = get_oi_summary(token)
    if summary.get('has_data'):
        print(f"\n{token} Summary:")
        print(f"  OI: ${summary['current_oi_usd']:,.0f}")
        print(f"  Signal: {summary['signal']}")


if __name__ == "__main__":
    test_oi_functions()
