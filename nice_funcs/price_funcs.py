"""
Price Data Helper Functions
Shared functions for working with OHLCV price data
Includes fallback logic, price calculations, and data retrieval
"""

import os
import time
from datetime import datetime, timedelta
import psycopg2
import requests
from typing import Optional, Dict, List, Tuple
from dotenv import load_dotenv

load_dotenv()

# Database configuration
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '54594')
DB_NAME = os.getenv('DB_NAME', 'postgres')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'postgres')

# CoinGecko API (backup source)
COINGECKO_API_KEY = os.getenv('COINGECKO_API_KEY', '')

# Cache for price data (token -> (price, timestamp))
price_cache = {}
CACHE_TTL = 10  # Cache for 10 seconds


def get_db_connection():
    """Get a database connection"""
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


def get_latest_price(token: str, source: str = 'binance') -> Optional[float]:
    """
    Get the latest price for a token from database

    Args:
        token: Token symbol (e.g., 'BTC', 'ETH')
        source: Data source ('binance' or 'coingecko')

    Returns:
        Latest close price or None if not found
    """
    conn = get_db_connection()
    if not conn:
        return None

    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT close FROM crypto_ohlcv
            WHERE token = %s AND source = %s
            ORDER BY timestamp DESC
            LIMIT 1
        """, (token, source))

        result = cursor.fetchone()
        return float(result[0]) if result else None

    except Exception as e:
        print(f"[ERROR] Failed to get price for {token}: {e}")
        return None

    finally:
        cursor.close()
        conn.close()


def get_cached_price(token: str) -> Optional[float]:
    """Get price from cache if still fresh"""
    if token in price_cache:
        price, timestamp = price_cache[token]
        if time.time() - timestamp < CACHE_TTL:
            return price
    return None


def set_cached_price(token: str, price: float):
    """Store price in cache"""
    price_cache[token] = (price, time.time())


def get_coingecko_price(token: str) -> Optional[float]:
    """
    Get price from CoinGecko API (backup source)

    Token ID mapping for CoinGecko (different from ticker symbols)
    """
    # Map token symbols to CoinGecko IDs
    token_id_map = {
        'BTC': 'bitcoin', 'ETH': 'ethereum', 'SOL': 'solana',
        'BNB': 'binancecoin', 'XRP': 'ripple', 'ADA': 'cardano',
        'TRX': 'tron', 'LTC': 'litecoin', 'DOGE': 'dogecoin',
        'SHIB': 'shiba-inu', 'PEPE': 'pepe', 'BONK': 'bonk',
        'WIF': 'dogwifhat', 'UNI': 'uniswap', 'AAVE': 'aave',
        'LDO': 'lido-dao', 'MKR': 'maker', 'CRV': 'curve-dao-token',
        'GMX': 'gmx', 'SNX': 'synthetix-network-token', 'LINK': 'chainlink',
        'AVAX': 'avalanche-2', 'DOT': 'polkadot', 'NEAR': 'near',
        'ATOM': 'cosmos', 'ICP': 'internet-computer', 'ALGO': 'algorand',
        'FTM': 'fantom', 'ARB': 'arbitrum', 'OP': 'optimism',
        'MATIC': 'matic-network', 'METIS': 'metis-token', 'IMX': 'immutable-x',
        'RENDER': 'render-token', 'FET': 'fetch-ai', 'GRT': 'the-graph',
        'OCEAN': 'ocean-protocol', 'AGIX': 'singularitynet', 'TAO': 'bittensor',
        'SUI': 'sui', 'TON': 'the-open-network', 'SEI': 'sei-network'
    }

    token_id = token_id_map.get(token)
    if not token_id:
        print(f"[WARNING] Unknown token for CoinGecko: {token}")
        return None

    try:
        url = "https://api.coingecko.com/api/v3/simple/price"
        params = {
            'ids': token_id,
            'vs_currencies': 'usd'
        }

        headers = {}
        if COINGECKO_API_KEY:
            headers['x-cg-pro-api-key'] = COINGECKO_API_KEY

        response = requests.get(url, params=params, headers=headers, timeout=5)
        data = response.json()

        if token_id in data and 'usd' in data[token_id]:
            price = float(data[token_id]['usd'])
            return price

    except Exception as e:
        print(f"[WARNING] CoinGecko API failed for {token}: {e}")

    return None


def get_price_with_fallback(token: str) -> Optional[float]:
    """
    Get price with fallback chain:
    1. Cache (if fresh)
    2. Database (Binance)
    3. CoinGecko API
    4. Database (any older price)

    Args:
        token: Token symbol (e.g., 'BTC', 'ETH')

    Returns:
        Price or None if all sources fail
    """
    # Try cache first
    cached = get_cached_price(token)
    if cached:
        return cached

    # Try database (recent Binance data)
    price = get_latest_price(token, 'binance')
    if price:
        set_cached_price(token, price)
        return price

    # Try CoinGecko API
    price = get_coingecko_price(token)
    if price:
        set_cached_price(token, price)
        return price

    # Last resort: any price from database
    price = get_latest_price(token, source='binance')
    if price:
        print(f"[WARNING] Using stale price for {token}")
        set_cached_price(token, price)
        return price

    print(f"[ERROR] No price available for {token}")
    return None


def get_ohlcv_history(token: str, hours: int = 24, timeframe: str = '5m') -> List[Dict]:
    """
    Get OHLCV history for a token

    Args:
        token: Token symbol
        hours: Number of hours of history
        timeframe: Timeframe ('5m', '15m', '1h', etc.)

    Returns:
        List of OHLCV dictionaries
    """
    conn = get_db_connection()
    if not conn:
        return []

    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT timestamp, open, high, low, close, volume
            FROM crypto_ohlcv
            WHERE token = %s
            AND timeframe = %s
            AND timestamp > NOW() - INTERVAL '%s hours'
            ORDER BY timestamp DESC
        """, (token, timeframe, hours))

        results = cursor.fetchall()
        ohlcv_list = []

        for row in results:
            ohlcv_list.append({
                'timestamp': row[0],
                'open': float(row[1]),
                'high': float(row[2]),
                'low': float(row[3]),
                'close': float(row[4]),
                'volume': float(row[5])
            })

        return ohlcv_list

    except Exception as e:
        print(f"[ERROR] Failed to get OHLCV history for {token}: {e}")
        return []

    finally:
        cursor.close()
        conn.close()


def calculate_price_change(token: str, period_hours: int = 1) -> Optional[float]:
    """
    Calculate percentage price change over a period

    Args:
        token: Token symbol
        period_hours: Period in hours (1, 24, etc.)

    Returns:
        Percentage change or None
    """
    conn = get_db_connection()
    if not conn:
        return None

    try:
        cursor = conn.cursor()

        # Get current price
        cursor.execute("""
            SELECT close FROM crypto_ohlcv
            WHERE token = %s
            ORDER BY timestamp DESC
            LIMIT 1
        """, (token,))
        current = cursor.fetchone()
        if not current:
            return None
        current_price = float(current[0])

        # Get price from period_hours ago
        cursor.execute("""
            SELECT close FROM crypto_ohlcv
            WHERE token = %s
            AND timestamp <= NOW() - INTERVAL '%s hours'
            ORDER BY timestamp DESC
            LIMIT 1
        """, (token, period_hours))
        past = cursor.fetchone()
        if not past:
            return None
        past_price = float(past[0])

        # Calculate percentage change
        if past_price > 0:
            change = ((current_price - past_price) / past_price) * 100
            return round(change, 2)

    except Exception as e:
        print(f"[ERROR] Failed to calculate price change for {token}: {e}")

    finally:
        cursor.close()
        conn.close()

    return None


def get_volume_24h(token: str) -> Optional[float]:
    """
    Get 24-hour trading volume for a token

    Args:
        token: Token symbol

    Returns:
        24h volume in USDT or None
    """
    conn = get_db_connection()
    if not conn:
        return None

    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT SUM(volume) FROM crypto_ohlcv
            WHERE token = %s
            AND timestamp > NOW() - INTERVAL '24 hours'
        """, (token,))

        result = cursor.fetchone()
        return float(result[0]) if result and result[0] else None

    except Exception as e:
        print(f"[ERROR] Failed to get 24h volume for {token}: {e}")
        return None

    finally:
        cursor.close()
        conn.close()


def get_price_summary(token: str) -> Dict:
    """
    Get comprehensive price summary for a token

    Returns dict with:
    - current_price
    - change_1h
    - change_24h
    - volume_24h
    - high_24h
    - low_24h
    """
    conn = get_db_connection()
    if not conn:
        return {}

    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                (SELECT close FROM crypto_ohlcv WHERE token = %s ORDER BY timestamp DESC LIMIT 1) as current_price,
                MAX(high) as high_24h,
                MIN(low) as low_24h,
                SUM(volume) as volume_24h
            FROM crypto_ohlcv
            WHERE token = %s
            AND timestamp > NOW() - INTERVAL '24 hours'
        """, (token, token))

        result = cursor.fetchone()
        if not result or not result[0]:
            return {}

        summary = {
            'current_price': float(result[0]) if result[0] else None,
            'high_24h': float(result[1]) if result[1] else None,
            'low_24h': float(result[2]) if result[2] else None,
            'volume_24h': float(result[3]) if result[3] else None,
            'change_1h': calculate_price_change(token, 1),
            'change_24h': calculate_price_change(token, 24)
        }

        return summary

    except Exception as e:
        print(f"[ERROR] Failed to get price summary for {token}: {e}")
        return {}

    finally:
        cursor.close()
        conn.close()


# Test function
def test_price_functions():
    """Test all price functions with BTC"""
    print("Testing price functions...")

    # Test getting latest price
    price = get_latest_price('BTC')
    print(f"Latest BTC price: ${price}")

    # Test with fallback
    price = get_price_with_fallback('BTC')
    print(f"BTC price with fallback: ${price}")

    # Test price change
    change = calculate_price_change('BTC', 1)
    print(f"BTC 1h change: {change}%")

    # Test volume
    volume = get_volume_24h('BTC')
    print(f"BTC 24h volume: ${volume:,.0f}")

    # Test summary
    summary = get_price_summary('BTC')
    print(f"BTC summary: {summary}")


if __name__ == "__main__":
    test_price_functions()