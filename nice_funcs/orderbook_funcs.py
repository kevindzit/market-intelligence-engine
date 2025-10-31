"""
Order Book Analysis Helper Functions
Functions for analyzing order book depth data for trading decisions
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


def get_current_orderbook(token: str) -> Optional[Dict]:
    """
    Get the most recent order book data for a token

    Returns:
        Dict with bid/ask prices, spread, imbalance, liquidity
    """
    conn = get_db_connection()
    if not conn:
        return None

    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT best_bid, best_ask, bid_ask_spread,
                   bid_liquidity_1pct, ask_liquidity_1pct,
                   order_imbalance, total_bid_volume, total_ask_volume,
                   timestamp
            FROM order_book_depth
            WHERE token = %s
            ORDER BY timestamp DESC
            LIMIT 1
        """, (token,))

        result = cursor.fetchone()
        if not result:
            return None

        spread_pct = (float(result[2]) / float(result[0])) * 100 if result[0] else 0

        return {
            'best_bid': float(result[0]),
            'best_ask': float(result[1]),
            'spread_absolute': float(result[2]),
            'spread_percent': spread_pct,
            'bid_liquidity_1pct': float(result[3]) if result[3] else 0,
            'ask_liquidity_1pct': float(result[4]) if result[4] else 0,
            'order_imbalance': float(result[5]) if result[5] else 0,
            'total_bid_volume': float(result[6]) if result[6] else 0,
            'total_ask_volume': float(result[7]) if result[7] else 0,
            'timestamp': result[8]
        }

    except Exception as e:
        print(f"[ERROR] Failed to get order book for {token}: {e}")
        return None

    finally:
        cursor.close()
        conn.close()


def get_spread_percent(token: str) -> Optional[float]:
    """Get current bid-ask spread as percentage"""
    orderbook = get_current_orderbook(token)
    return orderbook['spread_percent'] if orderbook else None


def get_order_imbalance(token: str) -> Optional[float]:
    """
    Get current order book imbalance
    Positive = buying pressure, Negative = selling pressure
    Range: -1.0 to 1.0
    """
    orderbook = get_current_orderbook(token)
    return orderbook['order_imbalance'] if orderbook else None


def is_good_entry_time(token: str, side: str = 'buy') -> bool:
    """
    Determine if current order book conditions are good for entry

    Args:
        token: Token symbol
        side: 'buy' or 'sell'

    Returns:
        True if conditions are favorable
    """
    orderbook = get_current_orderbook(token)
    if not orderbook:
        return False

    spread_pct = orderbook['spread_percent']
    imbalance = orderbook['order_imbalance']

    # Good conditions for buying
    if side == 'buy':
        # Tight spread + buying pressure or neutral
        return spread_pct < 0.1 and imbalance >= -0.2

    # Good conditions for selling
    elif side == 'sell':
        # Tight spread + selling pressure or neutral
        return spread_pct < 0.1 and imbalance <= 0.2

    return False


def detect_liquidity_walls(token: str) -> Dict:
    """
    Detect if there are significant liquidity walls

    Returns:
        Dict with buy_wall and sell_wall flags
    """
    orderbook = get_current_orderbook(token)
    if not orderbook:
        return {'buy_wall': False, 'sell_wall': False}

    bid_liq = orderbook['bid_liquidity_1pct']
    ask_liq = orderbook['ask_liquidity_1pct']

    # Wall detected if one side has 3x more liquidity
    buy_wall = bid_liq > ask_liq * 3 if ask_liq > 0 else False
    sell_wall = ask_liq > bid_liq * 3 if bid_liq > 0 else False

    return {
        'buy_wall': buy_wall,
        'sell_wall': sell_wall,
        'buy_wall_strength': bid_liq / ask_liq if ask_liq > 0 else 0,
        'sell_wall_strength': ask_liq / bid_liq if bid_liq > 0 else 0
    }


def get_orderbook_trend(token: str, minutes: int = 5) -> Optional[str]:
    """
    Analyze order book imbalance trend over time

    Returns:
        'INCREASING_BUY', 'INCREASING_SELL', 'STABLE', or None
    """
    conn = get_db_connection()
    if not conn:
        return None

    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT order_imbalance, timestamp
            FROM order_book_depth
            WHERE token = %s
            AND timestamp > NOW() - INTERVAL '%s minutes'
            ORDER BY timestamp DESC
            LIMIT 30
        """, (token, minutes))

        results = cursor.fetchall()
        if len(results) < 10:
            return None

        # Get recent and older imbalances
        recent_avg = sum(float(r[0]) for r in results[:10]) / 10
        older_avg = sum(float(r[0]) for r in results[-10:]) / 10

        # Detect trend
        diff = recent_avg - older_avg

        if diff > 0.1:
            return 'INCREASING_BUY'
        elif diff < -0.1:
            return 'INCREASING_SELL'
        else:
            return 'STABLE'

    except Exception as e:
        print(f"[ERROR] Failed to get order book trend for {token}: {e}")
        return None

    finally:
        cursor.close()
        conn.close()


def get_average_spread(token: str, minutes: int = 60) -> Optional[float]:
    """Get average spread percentage over time period"""
    conn = get_db_connection()
    if not conn:
        return None

    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT AVG(bid_ask_spread / best_bid * 100)
            FROM order_book_depth
            WHERE token = %s
            AND timestamp > NOW() - INTERVAL '%s minutes'
        """, (token, minutes))

        result = cursor.fetchone()
        return float(result[0]) if result and result[0] else None

    except Exception as e:
        print(f"[ERROR] Failed to get average spread for {token}: {e}")
        return None

    finally:
        cursor.close()
        conn.close()


def get_orderbook_summary(token: str) -> Dict:
    """
    Get comprehensive order book summary

    Returns complete picture of current order book state
    """
    current = get_current_orderbook(token)
    if not current:
        return {}

    walls = detect_liquidity_walls(token)
    trend = get_orderbook_trend(token, 5)
    avg_spread = get_average_spread(token, 60)

    return {
        'current': current,
        'walls': walls,
        'trend': trend,
        'avg_spread_1h': avg_spread,
        'is_good_buy_time': is_good_entry_time(token, 'buy'),
        'is_good_sell_time': is_good_entry_time(token, 'sell')
    }


# Test function
def test_orderbook_functions():
    """Test order book functions with BTC"""
    print("Testing order book functions...")

    token = 'BTC'

    # Get current order book
    orderbook = get_current_orderbook(token)
    if orderbook:
        print(f"\nCurrent {token} Order Book:")
        print(f"  Best Bid: ${orderbook['best_bid']:,.2f}")
        print(f"  Best Ask: ${orderbook['best_ask']:,.2f}")
        print(f"  Spread: {orderbook['spread_percent']:.4f}%")
        print(f"  Imbalance: {orderbook['order_imbalance']:.3f}")

    # Check for walls
    walls = detect_liquidity_walls(token)
    print(f"\nLiquidity Walls:")
    print(f"  Buy Wall: {walls['buy_wall']}")
    print(f"  Sell Wall: {walls['sell_wall']}")

    # Check entry timing
    good_buy = is_good_entry_time(token, 'buy')
    good_sell = is_good_entry_time(token, 'sell')
    print(f"\nEntry Timing:")
    print(f"  Good for buying: {good_buy}")
    print(f"  Good for selling: {good_sell}")

    # Get trend
    trend = get_orderbook_trend(token, 5)
    print(f"\nOrder Book Trend (5 min): {trend}")

    # Get summary
    summary = get_orderbook_summary(token)
    print(f"\nFull Summary: {summary}")


if __name__ == "__main__":
    test_orderbook_functions()
