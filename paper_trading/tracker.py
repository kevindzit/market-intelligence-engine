"""
Paper Trading Framework for PJX Crypto Trading System

This module provides comprehensive paper trading capabilities including:
- Virtual portfolio management
- Trade execution simulation
- Performance tracking and metrics
- Risk management validation
- Transition to live trading

Based on the Balanced Configuration strategy with:
- 1-2% risk per trade
- 20% max position size
- 5% daily loss limit
"""

import os
import sys
import json
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from decimal import Decimal
from enum import Enum
import uuid

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor
from termcolor import colored
from dataclasses import dataclass, asdict

# Load environment variables
load_dotenv()

# ========================
# CONFIGURATION
# ========================

# Initial portfolio settings
INITIAL_BALANCE_USD = 1000  # Starting balance for paper trading
DEFAULT_COMMISSION = 0.002  # 0.2% trading fee

# Risk management parameters (from crypto-trading-system-notes.md)
MAX_POSITION_PERCENT = 20  # Maximum 20% in a single position
MAX_RISK_PER_TRADE = 0.02  # 2% risk per trade
MAX_DAILY_LOSS = 0.05  # 5% daily loss limit
CASH_RESERVE_PERCENT = 0.20  # Keep 20% in cash

# Performance tracking intervals
METRICS_UPDATE_INTERVAL = 60  # Update metrics every minute
REPORT_INTERVAL = 3600  # Generate reports every hour

# Database configuration
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', 54594)),
    'database': os.getenv('DB_NAME', 'postgres'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', 'postgres')
}

# Logging setup
os.makedirs('logs', exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/paper_trading.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class TradeStatus(Enum):
    """Trade status enum"""
    PENDING = "pending"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"

class PositionStatus(Enum):
    """Position status enum"""
    OPEN = "open"
    CLOSED = "closed"
    PARTIAL = "partial"

@dataclass
class Trade:
    """Trade data structure"""
    trade_id: str
    timestamp: datetime
    symbol: str
    side: str  # 'buy' or 'sell'
    quantity: float
    price: float
    commission: float
    status: TradeStatus
    paper_trade: bool = True
    metadata: Dict = None

    def to_dict(self):
        d = asdict(self)
        d['timestamp'] = self.timestamp.isoformat()
        d['status'] = self.status.value
        return d

@dataclass
class Position:
    """Position data structure"""
    symbol: str
    quantity: float
    avg_entry_price: float
    current_price: float
    unrealized_pnl: float
    realized_pnl: float
    status: PositionStatus
    opened_at: datetime
    closed_at: Optional[datetime] = None
    max_drawdown: float = 0
    peak_pnl: float = 0

class PaperTradingTracker:
    """
    Comprehensive paper trading system for validation before live trading
    """

    def __init__(self, initial_balance: float = INITIAL_BALANCE_USD):
        """
        Initialize paper trading tracker

        Args:
            initial_balance: Starting USD balance for paper trading
        """
        self.initial_balance = initial_balance
        self.db_conn = None

        # Portfolio state
        self.balance = {'USD': initial_balance}
        self.positions = {}  # symbol -> Position
        self.trades = []  # List of Trade objects
        self.daily_pnl = 0
        self.session_start = datetime.now()

        # Performance metrics
        self.metrics = {
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'win_rate': 0,
            'avg_win': 0,
            'avg_loss': 0,
            'profit_factor': 0,
            'sharpe_ratio': 0,
            'max_drawdown': 0,
            'current_drawdown': 0,
            'total_pnl': 0,
            'roi': 0,
            'daily_returns': []
        }

        # Risk management state
        self.daily_loss_triggered = False
        self.last_reset = datetime.now().date()

        # Initialize database
        self.setup_database()
        self.load_state()

        logger.info(colored(f"📊 Paper Trading Tracker initialized with ${initial_balance}", "cyan"))

    def setup_database(self):
        """Initialize database connection and create tables"""
        try:
            self.db_conn = psycopg2.connect(**DB_CONFIG)
            cursor = self.db_conn.cursor()

            # Create trades table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS paper_trades (
                    trade_id VARCHAR(50) PRIMARY KEY,
                    timestamp TIMESTAMP NOT NULL,
                    symbol VARCHAR(20) NOT NULL,
                    side VARCHAR(10) NOT NULL,
                    quantity DECIMAL(20, 8) NOT NULL,
                    price DECIMAL(20, 8) NOT NULL,
                    commission DECIMAL(20, 8) NOT NULL,
                    status VARCHAR(20) NOT NULL,
                    paper_trade BOOLEAN DEFAULT true,
                    metadata JSONB,
                    INDEX idx_timestamp (timestamp),
                    INDEX idx_symbol (symbol)
                )
            """)

            # Create positions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS paper_positions (
                    id SERIAL PRIMARY KEY,
                    symbol VARCHAR(20) NOT NULL,
                    quantity DECIMAL(20, 8) NOT NULL,
                    avg_entry_price DECIMAL(20, 8) NOT NULL,
                    current_price DECIMAL(20, 8),
                    unrealized_pnl DECIMAL(20, 8) DEFAULT 0,
                    realized_pnl DECIMAL(20, 8) DEFAULT 0,
                    status VARCHAR(20) NOT NULL,
                    opened_at TIMESTAMP NOT NULL,
                    closed_at TIMESTAMP,
                    max_drawdown DECIMAL(20, 8) DEFAULT 0,
                    peak_pnl DECIMAL(20, 8) DEFAULT 0,
                    UNIQUE(symbol, status)
                )
            """)

            # Create portfolio snapshots table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                    id SERIAL PRIMARY KEY,
                    timestamp TIMESTAMP NOT NULL,
                    total_value DECIMAL(20, 8) NOT NULL,
                    cash_balance DECIMAL(20, 8) NOT NULL,
                    positions_value DECIMAL(20, 8) NOT NULL,
                    daily_pnl DECIMAL(20, 8) DEFAULT 0,
                    total_pnl DECIMAL(20, 8) DEFAULT 0,
                    metrics JSONB,
                    INDEX idx_snapshot_time (timestamp)
                )
            """)

            # Create performance metrics table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trading_metrics (
                    id SERIAL PRIMARY KEY,
                    date DATE NOT NULL UNIQUE,
                    total_trades INTEGER DEFAULT 0,
                    winning_trades INTEGER DEFAULT 0,
                    losing_trades INTEGER DEFAULT 0,
                    win_rate DECIMAL(5, 2) DEFAULT 0,
                    avg_win DECIMAL(20, 8) DEFAULT 0,
                    avg_loss DECIMAL(20, 8) DEFAULT 0,
                    profit_factor DECIMAL(10, 2) DEFAULT 0,
                    sharpe_ratio DECIMAL(10, 2) DEFAULT 0,
                    max_drawdown DECIMAL(10, 2) DEFAULT 0,
                    daily_pnl DECIMAL(20, 8) DEFAULT 0,
                    cumulative_pnl DECIMAL(20, 8) DEFAULT 0,
                    roi DECIMAL(10, 2) DEFAULT 0
                )
            """)

            self.db_conn.commit()
            logger.info("✅ Paper trading database tables created/verified")

        except Exception as e:
            logger.error(f"Database setup error: {e}")
            raise

    def load_state(self):
        """Load existing portfolio state from database"""
        try:
            cursor = self.db_conn.cursor(cursor_factory=RealDictCursor)

            # Load latest portfolio snapshot
            cursor.execute("""
                SELECT * FROM portfolio_snapshots
                ORDER BY timestamp DESC
                LIMIT 1
            """)
            snapshot = cursor.fetchone()

            if snapshot:
                self.balance['USD'] = float(snapshot['cash_balance'])
                self.metrics = json.loads(snapshot['metrics']) if snapshot['metrics'] else self.metrics
                logger.info(f"📂 Loaded portfolio state: ${snapshot['total_value']:.2f}")

            # Load open positions
            cursor.execute("""
                SELECT * FROM paper_positions
                WHERE status = 'open'
            """)
            positions = cursor.fetchall()

            for pos in positions:
                self.positions[pos['symbol']] = Position(
                    symbol=pos['symbol'],
                    quantity=float(pos['quantity']),
                    avg_entry_price=float(pos['avg_entry_price']),
                    current_price=float(pos['current_price'] or pos['avg_entry_price']),
                    unrealized_pnl=float(pos['unrealized_pnl']),
                    realized_pnl=float(pos['realized_pnl']),
                    status=PositionStatus.OPEN,
                    opened_at=pos['opened_at'],
                    max_drawdown=float(pos['max_drawdown']),
                    peak_pnl=float(pos['peak_pnl'])
                )

            # Load recent trades
            cursor.execute("""
                SELECT * FROM paper_trades
                ORDER BY timestamp DESC
                LIMIT 100
            """)
            trades = cursor.fetchall()

            for trade in trades:
                self.trades.append(Trade(
                    trade_id=trade['trade_id'],
                    timestamp=trade['timestamp'],
                    symbol=trade['symbol'],
                    side=trade['side'],
                    quantity=float(trade['quantity']),
                    price=float(trade['price']),
                    commission=float(trade['commission']),
                    status=TradeStatus(trade['status']),
                    metadata=trade['metadata']
                ))

        except Exception as e:
            logger.warning(f"Could not load state (may be first run): {e}")

    def validate_trade(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float
    ) -> Tuple[bool, str]:
        """
        Validate a trade against risk management rules

        Returns:
            (is_valid, reason)
        """
        # Check daily loss limit
        if self.daily_loss_triggered:
            return False, "Daily loss limit reached - trading suspended"

        trade_value = quantity * price
        portfolio_value = self.get_portfolio_value()

        # Check position size limit (20% max)
        position_percent = trade_value / portfolio_value
        if position_percent > MAX_POSITION_PERCENT:
            return False, f"Position too large: {position_percent:.1%} > {MAX_POSITION_PERCENT:.0%} limit"

        # Check cash reserve requirement (keep 20% in cash)
        if side == 'buy':
            remaining_cash = self.balance.get('USD', 0) - trade_value
            cash_percent = remaining_cash / portfolio_value
            if cash_percent < CASH_RESERVE_PERCENT:
                return False, f"Insufficient cash reserve: {cash_percent:.1%} < {CASH_RESERVE_PERCENT:.0%} required"

            # Check if we have enough balance
            if self.balance.get('USD', 0) < trade_value:
                return False, f"Insufficient balance: ${self.balance.get('USD', 0):.2f} < ${trade_value:.2f}"

        else:  # sell
            # Check if we have the position to sell
            if symbol not in self.positions:
                return False, f"No position in {symbol}"
            if self.positions[symbol].quantity < quantity:
                return False, f"Insufficient {symbol}: {self.positions[symbol].quantity:.8f} < {quantity:.8f}"

        # Check risk per trade (2% max)
        # Simplified - in real system would calculate based on stop loss
        risk_amount = trade_value * 0.1  # Assume 10% risk for now
        risk_percent = risk_amount / portfolio_value
        if risk_percent > MAX_RISK_PER_TRADE:
            return False, f"Risk too high: {risk_percent:.1%} > {MAX_RISK_PER_TRADE:.0%} limit"

        return True, "Trade validated"

    def execute_trade(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        metadata: Dict = None
    ) -> Dict:
        """
        Execute a paper trade

        Returns:
            Trade result dictionary
        """
        # Validate trade
        is_valid, reason = self.validate_trade(symbol, side, quantity, price)
        if not is_valid:
            logger.warning(colored(f"❌ Trade rejected: {reason}", "red"))
            return {
                'success': False,
                'error': reason,
                'trade_id': None
            }

        try:
            # Generate trade ID
            trade_id = f"PT-{uuid.uuid4().hex[:8]}-{int(time.time())}"

            # Calculate commission
            trade_value = quantity * price
            commission = trade_value * DEFAULT_COMMISSION

            # Create trade object
            trade = Trade(
                trade_id=trade_id,
                timestamp=datetime.now(),
                symbol=symbol,
                side=side,
                quantity=quantity,
                price=price,
                commission=commission,
                status=TradeStatus.FILLED,
                metadata=metadata or {}
            )

            # Update balances and positions
            if side == 'buy':
                # Deduct USD
                self.balance['USD'] -= (trade_value + commission)

                # Update or create position
                if symbol not in self.positions:
                    self.positions[symbol] = Position(
                        symbol=symbol,
                        quantity=quantity,
                        avg_entry_price=price,
                        current_price=price,
                        unrealized_pnl=0,
                        realized_pnl=0,
                        status=PositionStatus.OPEN,
                        opened_at=datetime.now()
                    )
                else:
                    pos = self.positions[symbol]
                    total_cost = (pos.quantity * pos.avg_entry_price) + trade_value
                    pos.quantity += quantity
                    pos.avg_entry_price = total_cost / pos.quantity

            else:  # sell
                # Add USD
                self.balance['USD'] += (trade_value - commission)

                # Update position
                pos = self.positions[symbol]

                # Calculate realized P&L
                realized_pnl = (price - pos.avg_entry_price) * quantity - commission
                pos.realized_pnl += realized_pnl
                pos.quantity -= quantity

                # Close position if fully sold
                if pos.quantity <= 0.00000001:  # Small threshold for floating point
                    pos.status = PositionStatus.CLOSED
                    pos.closed_at = datetime.now()
                    del self.positions[symbol]

            # Record trade
            self.trades.append(trade)
            self.save_trade(trade)

            # Update metrics
            self.update_metrics()

            # Log success
            emoji = "📈" if side == 'buy' else "📉"
            color = "green" if side == 'buy' else "red"
            logger.info(colored(
                f"{emoji} Paper {side.upper()}: {quantity:.8f} {symbol} @ ${price:.2f} (Fee: ${commission:.2f})",
                color
            ))

            return {
                'success': True,
                'trade_id': trade_id,
                'executed_quantity': quantity,
                'executed_price': price,
                'commission': commission,
                'new_balance': self.balance.copy()
            }

        except Exception as e:
            logger.error(f"Trade execution error: {e}")
            return {
                'success': False,
                'error': str(e),
                'trade_id': None
            }

    def update_positions(self, market_prices: Dict[str, float]):
        """Update position prices and P&L"""
        for symbol, position in self.positions.items():
            if symbol in market_prices:
                old_price = position.current_price
                position.current_price = market_prices[symbol]

                # Update unrealized P&L
                position.unrealized_pnl = (position.current_price - position.avg_entry_price) * position.quantity

                # Track peak and drawdown
                if position.unrealized_pnl > position.peak_pnl:
                    position.peak_pnl = position.unrealized_pnl

                current_drawdown = position.peak_pnl - position.unrealized_pnl
                if current_drawdown > position.max_drawdown:
                    position.max_drawdown = current_drawdown

    def get_portfolio_value(self) -> float:
        """Calculate total portfolio value"""
        total = self.balance.get('USD', 0)

        for position in self.positions.values():
            total += position.quantity * position.current_price

        return total

    def update_metrics(self):
        """Update performance metrics"""
        try:
            # Calculate basic metrics
            self.metrics['total_trades'] = len(self.trades)

            # Separate winning and losing trades
            closed_pnls = []
            for trade in self.trades:
                if trade.side == 'sell':
                    # Find the corresponding position's P&L
                    # Simplified - in production would track matched trades
                    closed_pnls.append(trade.quantity * trade.price * 0.01)  # Mock P&L

            if closed_pnls:
                wins = [p for p in closed_pnls if p > 0]
                losses = [p for p in closed_pnls if p < 0]

                self.metrics['winning_trades'] = len(wins)
                self.metrics['losing_trades'] = len(losses)
                self.metrics['win_rate'] = len(wins) / len(closed_pnls) * 100 if closed_pnls else 0
                self.metrics['avg_win'] = np.mean(wins) if wins else 0
                self.metrics['avg_loss'] = np.mean(losses) if losses else 0

                # Profit factor
                total_wins = sum(wins) if wins else 0
                total_losses = abs(sum(losses)) if losses else 1
                self.metrics['profit_factor'] = total_wins / total_losses if total_losses > 0 else 0

            # Portfolio metrics
            portfolio_value = self.get_portfolio_value()
            self.metrics['total_pnl'] = portfolio_value - self.initial_balance
            self.metrics['roi'] = (self.metrics['total_pnl'] / self.initial_balance) * 100

            # Calculate drawdown
            current_drawdown_pct = ((self.initial_balance - portfolio_value) / self.initial_balance) * 100
            self.metrics['current_drawdown'] = max(0, current_drawdown_pct)
            self.metrics['max_drawdown'] = max(self.metrics['max_drawdown'], self.metrics['current_drawdown'])

            # Check daily loss limit
            self.check_daily_loss_limit()

        except Exception as e:
            logger.error(f"Metrics update error: {e}")

    def check_daily_loss_limit(self):
        """Check and enforce daily loss limit"""
        # Reset daily tracking if new day
        current_date = datetime.now().date()
        if current_date > self.last_reset:
            self.daily_pnl = 0
            self.daily_loss_triggered = False
            self.last_reset = current_date

        # Calculate today's P&L
        portfolio_value = self.get_portfolio_value()
        self.daily_pnl = portfolio_value - self.initial_balance  # Simplified

        # Check if daily loss limit exceeded
        daily_loss_pct = abs(self.daily_pnl / self.initial_balance)
        if daily_loss_pct >= MAX_DAILY_LOSS and self.daily_pnl < 0:
            self.daily_loss_triggered = True
            logger.warning(colored(
                f"⚠️ Daily loss limit reached: -{daily_loss_pct:.1%} >= -{MAX_DAILY_LOSS:.0%}",
                "red"
            ))

    def save_trade(self, trade: Trade):
        """Save trade to database"""
        try:
            cursor = self.db_conn.cursor()
            cursor.execute("""
                INSERT INTO paper_trades
                (trade_id, timestamp, symbol, side, quantity, price,
                 commission, status, paper_trade, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                trade.trade_id,
                trade.timestamp,
                trade.symbol,
                trade.side,
                trade.quantity,
                trade.price,
                trade.commission,
                trade.status.value,
                trade.paper_trade,
                json.dumps(trade.metadata) if trade.metadata else None
            ))
            self.db_conn.commit()

        except Exception as e:
            logger.error(f"Error saving trade: {e}")
            self.db_conn.rollback()

    def save_snapshot(self):
        """Save portfolio snapshot to database"""
        try:
            portfolio_value = self.get_portfolio_value()
            positions_value = sum(p.quantity * p.current_price for p in self.positions.values())

            cursor = self.db_conn.cursor()
            cursor.execute("""
                INSERT INTO portfolio_snapshots
                (timestamp, total_value, cash_balance, positions_value,
                 daily_pnl, total_pnl, metrics)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                datetime.now(),
                portfolio_value,
                self.balance.get('USD', 0),
                positions_value,
                self.daily_pnl,
                self.metrics['total_pnl'],
                json.dumps(self.metrics)
            ))
            self.db_conn.commit()

        except Exception as e:
            logger.error(f"Error saving snapshot: {e}")
            self.db_conn.rollback()

    def generate_report(self) -> Dict:
        """Generate performance report"""
        try:
            portfolio_value = self.get_portfolio_value()
            positions_value = sum(p.quantity * p.current_price for p in self.positions.values())

            report = {
                'timestamp': datetime.now().isoformat(),
                'portfolio': {
                    'total_value': portfolio_value,
                    'cash_balance': self.balance.get('USD', 0),
                    'positions_value': positions_value,
                    'num_positions': len(self.positions)
                },
                'performance': self.metrics.copy(),
                'positions': [
                    {
                        'symbol': p.symbol,
                        'quantity': p.quantity,
                        'avg_price': p.avg_entry_price,
                        'current_price': p.current_price,
                        'unrealized_pnl': p.unrealized_pnl,
                        'pnl_percent': (p.unrealized_pnl / (p.quantity * p.avg_entry_price)) * 100
                    }
                    for p in self.positions.values()
                ],
                'recent_trades': [
                    t.to_dict() for t in self.trades[-10:]  # Last 10 trades
                ],
                'risk_status': {
                    'daily_loss_triggered': self.daily_loss_triggered,
                    'daily_pnl': self.daily_pnl,
                    'daily_pnl_percent': (self.daily_pnl / self.initial_balance) * 100,
                    'position_concentration': max(
                        [(p.quantity * p.current_price) / portfolio_value * 100
                         for p in self.positions.values()],
                        default=0
                    )
                }
            }

            # Log summary
            logger.info(colored("\n" + "="*50, "cyan"))
            logger.info(colored("📊 PAPER TRADING REPORT", "cyan", attrs=['bold']))
            logger.info(colored("="*50, "cyan"))
            logger.info(f"Portfolio Value: ${portfolio_value:.2f}")
            logger.info(f"Total P&L: ${self.metrics['total_pnl']:.2f} ({self.metrics['roi']:.2f}%)")
            logger.info(f"Win Rate: {self.metrics['win_rate']:.1f}%")
            logger.info(f"Profit Factor: {self.metrics['profit_factor']:.2f}")
            logger.info(f"Max Drawdown: {self.metrics['max_drawdown']:.2f}%")
            logger.info(f"Daily P&L: ${self.daily_pnl:.2f}")
            logger.info(colored("="*50 + "\n", "cyan"))

            return report

        except Exception as e:
            logger.error(f"Report generation error: {e}")
            return {}

    def should_graduate_to_live(self) -> Tuple[bool, List[str]]:
        """
        Check if ready to graduate from paper to live trading

        Returns:
            (is_ready, list_of_reasons)
        """
        criteria = []
        is_ready = True

        # Check minimum trades (100+)
        if self.metrics['total_trades'] < 100:
            is_ready = False
            criteria.append(f"❌ Need more trades: {self.metrics['total_trades']}/100")
        else:
            criteria.append(f"✅ Sufficient trades: {self.metrics['total_trades']}")

        # Check win rate (> 45%)
        if self.metrics['win_rate'] < 45:
            is_ready = False
            criteria.append(f"❌ Win rate too low: {self.metrics['win_rate']:.1f}% < 45%")
        else:
            criteria.append(f"✅ Good win rate: {self.metrics['win_rate']:.1f}%")

        # Check profit factor (> 1.2)
        if self.metrics['profit_factor'] < 1.2:
            is_ready = False
            criteria.append(f"❌ Profit factor too low: {self.metrics['profit_factor']:.2f} < 1.2")
        else:
            criteria.append(f"✅ Good profit factor: {self.metrics['profit_factor']:.2f}")

        # Check positive returns
        if self.metrics['total_pnl'] <= 0:
            is_ready = False
            criteria.append(f"❌ Negative returns: ${self.metrics['total_pnl']:.2f}")
        else:
            criteria.append(f"✅ Positive returns: ${self.metrics['total_pnl']:.2f}")

        # Check max drawdown (< 15%)
        if self.metrics['max_drawdown'] > 15:
            is_ready = False
            criteria.append(f"❌ Drawdown too high: {self.metrics['max_drawdown']:.1f}% > 15%")
        else:
            criteria.append(f"✅ Acceptable drawdown: {self.metrics['max_drawdown']:.1f}%")

        return is_ready, criteria

    def close(self):
        """Clean up resources"""
        self.save_snapshot()
        if self.db_conn:
            self.db_conn.close()
        logger.info("Paper trading tracker closed")

def main():
    """Test the paper trading framework"""
    try:
        # Initialize tracker
        tracker = PaperTradingTracker(initial_balance=1000)

        # Test some trades
        # Buy BTC
        result = tracker.execute_trade(
            symbol='BTC-USD',
            side='buy',
            quantity=0.001,
            price=65000,
            metadata={'strategy': 'momentum'}
        )
        print(f"Buy result: {result}")

        # Update position price (simulate price movement)
        tracker.update_positions({'BTC-USD': 66000})

        # Sell half
        result = tracker.execute_trade(
            symbol='BTC-USD',
            side='sell',
            quantity=0.0005,
            price=66000
        )
        print(f"Sell result: {result}")

        # Generate report
        report = tracker.generate_report()
        print(json.dumps(report, indent=2))

        # Check graduation criteria
        is_ready, criteria = tracker.should_graduate_to_live()
        print(f"\nReady for live trading: {is_ready}")
        for criterion in criteria:
            print(f"  {criterion}")

        tracker.close()

    except Exception as e:
        logger.error(f"Test failed: {e}")

if __name__ == "__main__":
    main()