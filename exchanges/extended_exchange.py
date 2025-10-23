"""
Extended Exchange Integration Module
For PJX Crypto Trading System

Extended is a fast, decentralized exchange with points-based rewards.
This module handles both paper trading and live trading on Extended.

Features:
- Paper trading mode for validation
- Real trading via Extended API
- Points tracking for rewards program
- Position management
- Order execution with slippage protection
"""

import os
import sys
import json
import time
import logging
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from decimal import Decimal
import hmac
import hashlib
from enum import Enum

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor
from termcolor import colored

# Load environment variables
load_dotenv()

# ========================
# CONFIGURATION
# ========================

# Extended Exchange API endpoints
EXTENDED_BASE_URL = "https://api.extended.exchange"
EXTENDED_WS_URL = "wss://ws.extended.exchange"

# Trading configuration
DEFAULT_SLIPPAGE = 0.02  # 2% slippage tolerance
MIN_ORDER_SIZE_USD = 10  # Minimum order size
MAX_ORDER_SIZE_USD = 10000  # Maximum single order

# Points program configuration
POINTS_MULTIPLIER = {
    'maker': 1.5,  # 1.5x points for limit orders
    'taker': 1.0,  # 1x points for market orders
    'liquidity': 2.0  # 2x points for providing liquidity
}

# Paper trading initial balance
PAPER_TRADING_INITIAL_BALANCE = 1000  # USD

# Database configuration
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', 54594)),
    'database': os.getenv('DB_NAME', 'postgres'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', 'postgres')
}

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/extended_exchange.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class OrderType(Enum):
    """Order types supported by Extended"""
    MARKET = "market"
    LIMIT = "limit"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"

class OrderSide(Enum):
    """Order sides"""
    BUY = "buy"
    SELL = "sell"

class ExtendedExchange:
    """
    Extended Exchange integration for crypto trading
    Supports both paper trading and live trading
    """

    def __init__(self, paper_trading: bool = True):
        """
        Initialize Extended Exchange connection

        Args:
            paper_trading: If True, use paper trading mode
        """
        self.paper_trading = paper_trading
        self.api_key = os.getenv('EXTENDED_API_KEY')
        self.api_secret = os.getenv('EXTENDED_API_SECRET')
        self.session = requests.Session()
        self.db_conn = None

        # Paper trading state
        self.paper_balance = {}
        self.paper_positions = {}
        self.paper_orders = []
        self.paper_points = 0

        # Initialize components
        self.setup_database()

        if self.paper_trading:
            self.init_paper_trading()
            logger.info(colored("📝 Extended Exchange initialized in PAPER TRADING mode", "yellow"))
        else:
            if not self.api_key or not self.api_secret:
                raise ValueError("Extended API credentials not found in .env file")
            self.authenticate()
            logger.info(colored("✅ Extended Exchange initialized in LIVE mode", "green"))

    def setup_database(self):
        """Initialize database connection and create tables"""
        try:
            self.db_conn = psycopg2.connect(**DB_CONFIG)
            cursor = self.db_conn.cursor()

            # Create orders table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS extended_orders (
                    id SERIAL PRIMARY KEY,
                    order_id VARCHAR(100) UNIQUE,
                    timestamp TIMESTAMP NOT NULL,
                    symbol VARCHAR(20) NOT NULL,
                    side VARCHAR(10) NOT NULL,
                    order_type VARCHAR(20) NOT NULL,
                    quantity DECIMAL(20, 8),
                    price DECIMAL(20, 8),
                    executed_quantity DECIMAL(20, 8) DEFAULT 0,
                    status VARCHAR(20) DEFAULT 'pending',
                    paper_trade BOOLEAN DEFAULT false,
                    points_earned DECIMAL(10, 2) DEFAULT 0,
                    metadata JSONB
                )
            """)

            # Create positions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS extended_positions (
                    id SERIAL PRIMARY KEY,
                    symbol VARCHAR(20) NOT NULL,
                    quantity DECIMAL(20, 8) NOT NULL,
                    avg_entry_price DECIMAL(20, 8) NOT NULL,
                    current_price DECIMAL(20, 8),
                    unrealized_pnl DECIMAL(20, 8),
                    realized_pnl DECIMAL(20, 8) DEFAULT 0,
                    paper_trade BOOLEAN DEFAULT false,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(symbol, paper_trade)
                )
            """)

            # Create points tracking table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS extended_points (
                    id SERIAL PRIMARY KEY,
                    timestamp TIMESTAMP NOT NULL,
                    activity_type VARCHAR(50) NOT NULL,
                    points_earned DECIMAL(10, 2) NOT NULL,
                    total_points DECIMAL(10, 2) NOT NULL,
                    description TEXT,
                    paper_trade BOOLEAN DEFAULT false
                )
            """)

            self.db_conn.commit()
            logger.info("✅ Database tables created/verified")

        except Exception as e:
            logger.error(f"Database setup error: {e}")
            raise

    def init_paper_trading(self):
        """Initialize paper trading with starting balance"""
        self.paper_balance = {
            'USD': PAPER_TRADING_INITIAL_BALANCE,
            'BTC': 0,
            'ETH': 0,
            'SOL': 0,
            'PEPE': 0,
            'EXT': 0  # Extended token
        }
        self.paper_positions = {}
        self.paper_orders = []
        self.paper_points = 0

        logger.info(f"💵 Paper trading initialized with ${PAPER_TRADING_INITIAL_BALANCE}")

    def authenticate(self):
        """Authenticate with Extended Exchange API"""
        try:
            # Set authentication headers
            self.session.headers.update({
                'X-API-KEY': self.api_key,
                'X-API-SECRET': self.api_secret,
                'Content-Type': 'application/json'
            })

            # Test authentication
            response = self.session.get(f"{EXTENDED_BASE_URL}/v1/account")
            if response.status_code == 200:
                logger.info("✅ Extended Exchange authentication successful")
            else:
                raise Exception(f"Authentication failed: {response.text}")

        except Exception as e:
            logger.error(f"Authentication error: {e}")
            raise

    def generate_signature(self, timestamp: str, method: str, path: str, body: str = "") -> str:
        """Generate HMAC signature for API requests"""
        message = f"{timestamp}{method}{path}{body}"
        signature = hmac.new(
            self.api_secret.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
        return signature

    def get_market_price(self, symbol: str) -> float:
        """
        Get current market price for a symbol

        Args:
            symbol: Trading pair (e.g., 'BTC-USD', 'SOL-USD')

        Returns:
            Current market price
        """
        if self.paper_trading:
            # Use mock prices for paper trading
            mock_prices = {
                'BTC-USD': 65000 + np.random.uniform(-1000, 1000),
                'ETH-USD': 3500 + np.random.uniform(-100, 100),
                'SOL-USD': 150 + np.random.uniform(-5, 5),
                'PEPE-USD': 0.00001 + np.random.uniform(-0.000001, 0.000001),
                'EXT-USD': 2.5 + np.random.uniform(-0.1, 0.1)
            }
            return mock_prices.get(symbol, 100)

        try:
            response = self.session.get(f"{EXTENDED_BASE_URL}/v1/ticker/{symbol}")
            if response.status_code == 200:
                data = response.json()
                return float(data['last_price'])
            else:
                logger.error(f"Failed to get price for {symbol}: {response.text}")
                return 0

        except Exception as e:
            logger.error(f"Error fetching market price: {e}")
            return 0

    def place_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        quantity: Optional[float] = None,
        usd_amount: Optional[float] = None,
        price: Optional[float] = None,
        stop_price: Optional[float] = None
    ) -> Dict:
        """
        Place an order on Extended Exchange

        Args:
            symbol: Trading pair (e.g., 'BTC-USD')
            side: Buy or sell
            order_type: Market, limit, etc.
            quantity: Amount of asset to trade
            usd_amount: USD amount (for market buys)
            price: Limit price (for limit orders)
            stop_price: Stop price (for stop orders)

        Returns:
            Order result dictionary
        """
        try:
            # Get current market price
            market_price = self.get_market_price(symbol)

            # Calculate quantity if USD amount provided
            if usd_amount and not quantity:
                quantity = usd_amount / market_price

            # Validate order size
            order_value = quantity * market_price
            if order_value < MIN_ORDER_SIZE_USD:
                return {
                    'success': False,
                    'error': f"Order size too small: ${order_value:.2f} < ${MIN_ORDER_SIZE_USD}"
                }
            if order_value > MAX_ORDER_SIZE_USD:
                return {
                    'success': False,
                    'error': f"Order size too large: ${order_value:.2f} > ${MAX_ORDER_SIZE_USD}"
                }

            # Generate order ID
            order_id = f"EXT-{int(time.time() * 1000)}"

            if self.paper_trading:
                # Execute paper trade
                result = self.execute_paper_trade(
                    order_id, symbol, side, order_type,
                    quantity, price or market_price
                )
            else:
                # Execute real trade
                result = self.execute_real_trade(
                    order_id, symbol, side, order_type,
                    quantity, price, stop_price
                )

            # Save to database
            self.save_order_to_db(order_id, symbol, side, order_type, quantity, price or market_price, result)

            # Calculate and track points
            if result['success']:
                points = self.calculate_points(order_type, order_value)
                self.track_points(points, f"{side.value} {symbol}")
                result['points_earned'] = points

            return result

        except Exception as e:
            logger.error(f"Order placement error: {e}")
            return {'success': False, 'error': str(e)}

    def execute_paper_trade(
        self,
        order_id: str,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        quantity: float,
        price: float
    ) -> Dict:
        """Execute a paper trade"""
        try:
            base_asset = symbol.split('-')[0]
            quote_asset = symbol.split('-')[1]

            if side == OrderSide.BUY:
                # Check USD balance
                required_usd = quantity * price
                if self.paper_balance.get('USD', 0) < required_usd:
                    return {
                        'success': False,
                        'error': f"Insufficient balance: need ${required_usd:.2f}, have ${self.paper_balance.get('USD', 0):.2f}"
                    }

                # Execute buy
                self.paper_balance['USD'] -= required_usd
                self.paper_balance[base_asset] = self.paper_balance.get(base_asset, 0) + quantity

                # Update position
                if base_asset not in self.paper_positions:
                    self.paper_positions[base_asset] = {
                        'quantity': 0,
                        'avg_price': 0,
                        'total_cost': 0
                    }

                pos = self.paper_positions[base_asset]
                total_cost = pos['total_cost'] + required_usd
                total_quantity = pos['quantity'] + quantity
                pos['quantity'] = total_quantity
                pos['total_cost'] = total_cost
                pos['avg_price'] = total_cost / total_quantity if total_quantity > 0 else 0

            else:  # SELL
                # Check asset balance
                if self.paper_balance.get(base_asset, 0) < quantity:
                    return {
                        'success': False,
                        'error': f"Insufficient {base_asset}: have {self.paper_balance.get(base_asset, 0):.8f}"
                    }

                # Execute sell
                self.paper_balance[base_asset] -= quantity
                self.paper_balance['USD'] += quantity * price

                # Update position
                if base_asset in self.paper_positions:
                    pos = self.paper_positions[base_asset]
                    pos['quantity'] -= quantity
                    if pos['quantity'] <= 0:
                        del self.paper_positions[base_asset]

            # Record order
            self.paper_orders.append({
                'order_id': order_id,
                'timestamp': datetime.now(),
                'symbol': symbol,
                'side': side.value,
                'type': order_type.value,
                'quantity': quantity,
                'price': price,
                'status': 'filled'
            })

            logger.info(colored(
                f"📝 Paper {side.value}: {quantity:.8f} {base_asset} @ ${price:.2f}",
                "green" if side == OrderSide.BUY else "red"
            ))

            return {
                'success': True,
                'order_id': order_id,
                'executed_quantity': quantity,
                'executed_price': price,
                'paper_trade': True
            }

        except Exception as e:
            logger.error(f"Paper trade execution error: {e}")
            return {'success': False, 'error': str(e)}

    def execute_real_trade(
        self,
        order_id: str,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        quantity: float,
        price: Optional[float],
        stop_price: Optional[float]
    ) -> Dict:
        """Execute a real trade on Extended Exchange"""
        try:
            # Prepare order payload
            payload = {
                'symbol': symbol,
                'side': side.value,
                'type': order_type.value,
                'quantity': str(quantity),
                'client_order_id': order_id
            }

            if price:
                payload['price'] = str(price)
            if stop_price:
                payload['stop_price'] = str(stop_price)

            # Generate signature
            timestamp = str(int(time.time() * 1000))
            body = json.dumps(payload)
            signature = self.generate_signature(timestamp, 'POST', '/v1/orders', body)

            # Add signature to headers
            headers = {
                'X-TIMESTAMP': timestamp,
                'X-SIGNATURE': signature
            }

            # Send order
            response = self.session.post(
                f"{EXTENDED_BASE_URL}/v1/orders",
                json=payload,
                headers=headers
            )

            if response.status_code == 200:
                data = response.json()
                logger.info(colored(
                    f"✅ Live {side.value}: {quantity:.8f} {symbol} @ ${price or 'market'}",
                    "green" if side == OrderSide.BUY else "red"
                ))
                return {
                    'success': True,
                    'order_id': data.get('order_id', order_id),
                    'executed_quantity': float(data.get('executed_quantity', 0)),
                    'executed_price': float(data.get('executed_price', price or 0)),
                    'status': data.get('status', 'pending')
                }
            else:
                logger.error(f"Order failed: {response.text}")
                return {'success': False, 'error': response.text}

        except Exception as e:
            logger.error(f"Real trade execution error: {e}")
            return {'success': False, 'error': str(e)}

    def get_balance(self) -> Dict[str, float]:
        """Get account balance"""
        if self.paper_trading:
            return self.paper_balance.copy()

        try:
            response = self.session.get(f"{EXTENDED_BASE_URL}/v1/account/balances")
            if response.status_code == 200:
                balances = response.json()
                return {b['asset']: float(b['available']) for b in balances}
            else:
                logger.error(f"Failed to get balance: {response.text}")
                return {}

        except Exception as e:
            logger.error(f"Error fetching balance: {e}")
            return {}

    def get_positions(self) -> Dict[str, Dict]:
        """Get current positions"""
        if self.paper_trading:
            return self.paper_positions.copy()

        try:
            response = self.session.get(f"{EXTENDED_BASE_URL}/v1/positions")
            if response.status_code == 200:
                positions = response.json()
                return {
                    p['symbol']: {
                        'quantity': float(p['quantity']),
                        'avg_price': float(p['avg_price']),
                        'current_price': float(p['current_price']),
                        'unrealized_pnl': float(p['unrealized_pnl'])
                    }
                    for p in positions
                }
            else:
                logger.error(f"Failed to get positions: {response.text}")
                return {}

        except Exception as e:
            logger.error(f"Error fetching positions: {e}")
            return {}

    def calculate_points(self, order_type: OrderType, order_value: float) -> float:
        """Calculate points earned for an order"""
        base_points = order_value * 0.001  # 0.1% of order value as base points

        if order_type == OrderType.LIMIT:
            return base_points * POINTS_MULTIPLIER['maker']
        else:
            return base_points * POINTS_MULTIPLIER['taker']

    def track_points(self, points: float, description: str):
        """Track points earned"""
        try:
            if self.paper_trading:
                self.paper_points += points
                total = self.paper_points
            else:
                # In real mode, fetch from API
                total = self.get_total_points() + points

            cursor = self.db_conn.cursor()
            cursor.execute("""
                INSERT INTO extended_points
                (timestamp, activity_type, points_earned, total_points, description, paper_trade)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                datetime.now(),
                'trading',
                points,
                total,
                description,
                self.paper_trading
            ))
            self.db_conn.commit()

            logger.info(colored(f"🎯 Points earned: +{points:.2f} (Total: {total:.2f})", "cyan"))

        except Exception as e:
            logger.error(f"Error tracking points: {e}")

    def get_total_points(self) -> float:
        """Get total points earned"""
        if self.paper_trading:
            return self.paper_points

        try:
            response = self.session.get(f"{EXTENDED_BASE_URL}/v1/points")
            if response.status_code == 200:
                data = response.json()
                return float(data.get('total_points', 0))
            return 0

        except Exception as e:
            logger.error(f"Error fetching points: {e}")
            return 0

    def save_order_to_db(
        self,
        order_id: str,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        quantity: float,
        price: float,
        result: Dict
    ):
        """Save order to database"""
        try:
            cursor = self.db_conn.cursor()
            cursor.execute("""
                INSERT INTO extended_orders
                (order_id, timestamp, symbol, side, order_type, quantity, price,
                 executed_quantity, status, paper_trade, points_earned, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                order_id,
                datetime.now(),
                symbol,
                side.value,
                order_type.value,
                quantity,
                price,
                result.get('executed_quantity', 0),
                result.get('status', 'failed' if not result.get('success') else 'filled'),
                self.paper_trading,
                result.get('points_earned', 0),
                json.dumps(result)
            ))
            self.db_conn.commit()

        except Exception as e:
            logger.error(f"Error saving order to database: {e}")
            self.db_conn.rollback()

    def get_order_history(self, limit: int = 100) -> pd.DataFrame:
        """Get order history"""
        try:
            query = """
                SELECT * FROM extended_orders
                WHERE paper_trade = %s
                ORDER BY timestamp DESC
                LIMIT %s
            """
            df = pd.read_sql(query, self.db_conn, params=(self.paper_trading, limit))
            return df

        except Exception as e:
            logger.error(f"Error fetching order history: {e}")
            return pd.DataFrame()

    def get_performance_metrics(self) -> Dict:
        """Calculate performance metrics"""
        try:
            # Get order history
            orders = self.get_order_history(1000)
            if orders.empty:
                return {
                    'total_trades': 0,
                    'win_rate': 0,
                    'total_pnl': 0,
                    'avg_profit': 0,
                    'sharpe_ratio': 0,
                    'max_drawdown': 0,
                    'total_points': self.get_total_points()
                }

            # Calculate metrics
            # (This is simplified - you'd want more sophisticated calculations)
            positions = self.get_positions()
            total_pnl = sum(p.get('unrealized_pnl', 0) for p in positions.values())

            return {
                'total_trades': len(orders),
                'win_rate': 0,  # TODO: Calculate from closed positions
                'total_pnl': total_pnl,
                'avg_profit': total_pnl / len(orders) if len(orders) > 0 else 0,
                'sharpe_ratio': 0,  # TODO: Calculate
                'max_drawdown': 0,  # TODO: Calculate
                'total_points': self.get_total_points()
            }

        except Exception as e:
            logger.error(f"Error calculating metrics: {e}")
            return {}

    def close(self):
        """Clean up resources"""
        if self.db_conn:
            self.db_conn.close()
        self.session.close()
        logger.info("Extended Exchange connection closed")

# Convenience functions for the exchange manager pattern
def market_buy(symbol: str, usd_amount: float, paper_trading: bool = True) -> Dict:
    """Quick market buy"""
    exchange = ExtendedExchange(paper_trading=paper_trading)
    result = exchange.place_order(
        symbol=symbol,
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        usd_amount=usd_amount
    )
    exchange.close()
    return result

def market_sell(symbol: str, quantity: float, paper_trading: bool = True) -> Dict:
    """Quick market sell"""
    exchange = ExtendedExchange(paper_trading=paper_trading)
    result = exchange.place_order(
        symbol=symbol,
        side=OrderSide.SELL,
        order_type=OrderType.MARKET,
        quantity=quantity
    )
    exchange.close()
    return result

def get_balance(paper_trading: bool = True) -> Dict:
    """Quick balance check"""
    exchange = ExtendedExchange(paper_trading=paper_trading)
    balance = exchange.get_balance()
    exchange.close()
    return balance

def main():
    """Test the Extended Exchange integration"""
    try:
        # Initialize in paper trading mode
        exchange = ExtendedExchange(paper_trading=True)

        # Test getting balance
        balance = exchange.get_balance()
        logger.info(f"Balance: {balance}")

        # Test market price
        btc_price = exchange.get_market_price('BTC-USD')
        logger.info(f"BTC Price: ${btc_price:.2f}")

        # Test placing a buy order
        result = exchange.place_order(
            symbol='BTC-USD',
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            usd_amount=100
        )
        logger.info(f"Buy result: {result}")

        # Check positions
        positions = exchange.get_positions()
        logger.info(f"Positions: {positions}")

        # Check points
        points = exchange.get_total_points()
        logger.info(f"Total points: {points}")

        # Get performance metrics
        metrics = exchange.get_performance_metrics()
        logger.info(f"Performance: {metrics}")

        exchange.close()

    except Exception as e:
        logger.error(f"Test failed: {e}")

if __name__ == "__main__":
    main()