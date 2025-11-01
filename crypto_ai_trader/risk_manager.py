"""
Risk Management Layer
Validates trades, enforces position limits, and manages circuit breakers
Critical for protecting capital and preventing catastrophic losses
"""

import psycopg2
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import config


class RiskManager:
    """Manages all risk aspects of trading system"""

    def __init__(self):
        """Initialize risk manager"""
        self.db_conn = None
        self.consecutive_losses = 0
        self.daily_trades = 0
        self.last_trade_date = datetime.now().date()

    def get_db_connection(self):
        """Get database connection"""
        return psycopg2.connect(
            host=config.DB_HOST,
            port=config.DB_PORT,
            database=config.DB_NAME,
            user=config.DB_USER,
            password=config.DB_PASSWORD
        )

    def validate_trade(self, decision: Dict, portfolio: Dict) -> Dict:
        """
        Validate a trading decision against risk parameters

        Args:
            decision: Trading decision with action, confidence, position_size
            portfolio: Current portfolio state

        Returns:
            Dict with approval status and adjusted parameters
        """

        validation_result = {
            'approved': False,
            'action': decision['action'],
            'position_size_pct': 0.0,
            'position_size_usd': 0.0,
            'stop_loss_pct': decision.get('stop_loss_pct', config.DEFAULT_STOP_LOSS_PCT),
            'take_profit_pct': decision.get('take_profit_pct', config.DEFAULT_TAKE_PROFIT_PCT),
            'rejection_reason': None
        }

        # HOLD signals always approved (no risk)
        if decision['action'] == 'HOLD':
            validation_result['approved'] = True
            return validation_result

        # Check circuit breakers first
        breaker_status = self.check_circuit_breakers(portfolio)
        if breaker_status['halted']:
            validation_result['rejection_reason'] = f"Circuit breaker: {breaker_status['reason']}"
            return validation_result

        # Validate confidence threshold
        min_confidence = config.MIN_TIER1_CONFIDENCE
        if 'tier2_confidence' in decision:  # If Tier 2 was triggered
            min_confidence = config.MIN_TIER2_CONSENSUS

        if decision.get('confidence', 0) < min_confidence:
            validation_result['rejection_reason'] = f"Confidence {decision['confidence']:.2%} below minimum {min_confidence:.0%}"
            return validation_result

        # Calculate position size
        position_size = self.calculate_position_size(
            decision=decision,
            portfolio=portfolio
        )

        if position_size['size_usd'] < config.MIN_POSITION_SIZE_USD:
            validation_result['rejection_reason'] = f"Position size ${position_size['size_usd']:.2f} below minimum ${config.MIN_POSITION_SIZE_USD}"
            return validation_result

        # Check portfolio constraints
        if decision['action'] == 'BUY':
            # Check if we have enough cash
            if position_size['size_usd'] > portfolio['cash']:
                validation_result['rejection_reason'] = f"Insufficient cash: ${portfolio['cash']:.2f} available, ${position_size['size_usd']:.2f} needed"
                return validation_result

            # Check cash reserve requirement
            cash_after_trade = portfolio['cash'] - position_size['size_usd']
            min_cash_required = portfolio['total_value'] * (config.CASH_RESERVE_PCT / 100)

            if cash_after_trade < min_cash_required:
                validation_result['rejection_reason'] = f"Would violate cash reserve: ${cash_after_trade:.2f} < ${min_cash_required:.2f} required"
                return validation_result

            # Check if position already exists
            if decision['token'] in portfolio.get('positions', {}):
                existing_position = portfolio['positions'][decision['token']]
                if existing_position.get('size_usd', 0) > 0:
                    validation_result['rejection_reason'] = f"Position already exists in {decision['token']}"
                    return validation_result

        elif decision['action'] == 'SELL':
            # Check if we have position to sell
            if decision['token'] not in portfolio.get('positions', {}):
                validation_result['rejection_reason'] = f"No position to sell in {decision['token']}"
                return validation_result

        # All checks passed
        validation_result['approved'] = True
        validation_result['position_size_pct'] = position_size['size_pct']
        validation_result['position_size_usd'] = position_size['size_usd']

        if config.VERBOSE_LOGGING:
            print(f"\n[RISK] Trade Validation:")
            print(f"  Action: {decision['action']}")
            print(f"  Approved: {validation_result['approved']}")
            if validation_result['approved']:
                print(f"  Position Size: ${validation_result['position_size_usd']:.2f} ({validation_result['position_size_pct']:.1f}%)")
                print(f"  Stop Loss: {validation_result['stop_loss_pct']:.1f}%")
                print(f"  Take Profit: {validation_result['take_profit_pct']:.1f}%")
            else:
                print(f"  Reason: {validation_result['rejection_reason']}")

        return validation_result

    def calculate_position_size(self, decision: Dict, portfolio: Dict) -> Dict:
        """
        Calculate appropriate position size based on confidence and risk

        Uses simple confidence-based sizing:
        - Base size = confidence * max_position_size
        - Capped at portfolio and risk limits
        """

        confidence = decision.get('confidence', 0.5)
        if 'tier2_confidence' in decision:
            confidence = decision['tier2_confidence']

        # Base position size (confidence-scaled)
        base_size_pct = confidence * config.MAX_POSITION_SIZE_PCT

        # Apply minimum and maximum constraints
        position_size_pct = max(1.0, min(base_size_pct, config.MAX_POSITION_SIZE_PCT))

        # Convert to USD
        position_size_usd = (position_size_pct / 100) * portfolio['total_value']

        # Apply USD constraints
        position_size_usd = max(
            config.MIN_POSITION_SIZE_USD,
            min(position_size_usd, portfolio['cash'])
        )

        return {
            'size_pct': position_size_pct,
            'size_usd': position_size_usd
        }

    def check_circuit_breakers(self, portfolio: Dict) -> Dict:
        """
        Check all circuit breakers

        Returns:
            Dict with halted status and reason
        """

        # Check if already halted
        if portfolio.get('trading_halted', False):
            return {
                'halted': True,
                'reason': portfolio.get('halt_reason', 'Trading halted')
            }

        # Check daily drawdown
        if portfolio.get('current_drawdown', 0) > config.MAX_DAILY_DRAWDOWN_PCT:
            self._trigger_circuit_breaker(
                'DAILY_DRAWDOWN',
                f"Daily drawdown {portfolio['current_drawdown']:.1f}% exceeds {config.MAX_DAILY_DRAWDOWN_PCT}% limit",
                portfolio
            )
            return {
                'halted': True,
                'reason': f"Daily drawdown limit reached"
            }

        # Check consecutive losses
        if self.consecutive_losses >= config.MAX_CONSECUTIVE_LOSSES:
            self._trigger_circuit_breaker(
                'CONSECUTIVE_LOSSES',
                f"{self.consecutive_losses} consecutive losses",
                portfolio
            )
            return {
                'halted': True,
                'reason': f"{config.MAX_CONSECUTIVE_LOSSES} consecutive losses"
            }

        # Check daily trade limit
        if datetime.now().date() > self.last_trade_date:
            self.daily_trades = 0
            self.last_trade_date = datetime.now().date()

        if self.daily_trades >= config.MAX_DAILY_TRADES:
            return {
                'halted': True,
                'reason': f"Daily trade limit ({config.MAX_DAILY_TRADES}) reached"
            }

        return {
            'halted': False,
            'reason': None
        }

    def _trigger_circuit_breaker(self, event_type: str, reason: str, portfolio: Dict):
        """Log circuit breaker event to database"""
        conn = self.get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO circuit_breaker_events
                (event_type, reason, portfolio_value, daily_drawdown, consecutive_losses)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                event_type,
                reason,
                portfolio.get('total_value', 0),
                portfolio.get('current_drawdown', 0),
                self.consecutive_losses
            ))

            # Update portfolio state
            cursor.execute("""
                UPDATE portfolio_state
                SET trading_halted = true, halt_reason = %s
                WHERE id = (SELECT MAX(id) FROM portfolio_state)
            """, (reason,))

            conn.commit()

            print(f"\n[ALERT] CIRCUIT BREAKER TRIGGERED: {reason}")

        finally:
            cursor.close()
            conn.close()

    def update_trade_statistics(self, trade_result: Dict):
        """Update risk manager statistics after a trade"""

        if trade_result['outcome'] == 'LOSS':
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0

        self.daily_trades += 1

    def get_portfolio_state(self) -> Dict:
        """Get current portfolio state from database"""
        conn = self.get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT
                    total_value,
                    cash,
                    positions_value,
                    positions,
                    current_drawdown,
                    trading_halted,
                    halt_reason,
                    winning_trades,
                    losing_trades,
                    total_trades
                FROM portfolio_state
                ORDER BY id DESC
                LIMIT 1
            """)

            result = cursor.fetchone()

            if result:
                return {
                    'total_value': float(result[0]),
                    'cash': float(result[1]),
                    'positions_value': float(result[2]) if result[2] else 0,
                    'positions': result[3] if result[3] else {},
                    'current_drawdown': float(result[4]) if result[4] else 0,
                    'trading_halted': bool(result[5]),
                    'halt_reason': result[6],
                    'winning_trades': int(result[7]) if result[7] else 0,
                    'losing_trades': int(result[8]) if result[8] else 0,
                    'total_trades': int(result[9]) if result[9] else 0
                }
            else:
                # Return default state if no portfolio exists
                return {
                    'total_value': config.INITIAL_CAPITAL,
                    'cash': config.INITIAL_CAPITAL,
                    'positions_value': 0,
                    'positions': {},
                    'current_drawdown': 0,
                    'trading_halted': False,
                    'halt_reason': None,
                    'winning_trades': 0,
                    'losing_trades': 0,
                    'total_trades': 0
                }

        finally:
            cursor.close()
            conn.close()

    def calculate_stop_loss_price(self, entry_price: float, stop_loss_pct: float, action: str) -> float:
        """Calculate stop loss price"""
        if action == 'BUY':
            return entry_price * (1 - stop_loss_pct / 100)
        else:  # SHORT positions (future feature)
            return entry_price * (1 + stop_loss_pct / 100)

    def calculate_take_profit_price(self, entry_price: float, take_profit_pct: float, action: str) -> float:
        """Calculate take profit price"""
        if action == 'BUY':
            return entry_price * (1 + take_profit_pct / 100)
        else:  # SHORT positions (future feature)
            return entry_price * (1 - take_profit_pct / 100)


# Test function
if __name__ == "__main__":
    print("Testing Risk Manager...\n")

    # Initialize risk manager
    rm = RiskManager()

    # Get current portfolio
    portfolio = rm.get_portfolio_state()
    print(f"Portfolio State:")
    print(f"  Total Value: ${portfolio['total_value']:,.2f}")
    print(f"  Cash: ${portfolio['cash']:,.2f}")
    print(f"  Positions: {len(portfolio['positions'])}")
    print(f"  Halted: {portfolio['trading_halted']}")

    # Test decision validation
    test_decision = {
        'token': 'BTC',
        'action': 'BUY',
        'confidence': 0.75,
        'position_size': 3.0,
        'stop_loss_pct': 3.0,
        'take_profit_pct': 6.0
    }

    print(f"\nValidating test decision: {test_decision['action']} {test_decision['token']}")
    validation = rm.validate_trade(test_decision, portfolio)

    print(f"\nValidation Result:")
    print(f"  Approved: {validation['approved']}")
    if validation['approved']:
        print(f"  Position Size: ${validation['position_size_usd']:.2f}")
    else:
        print(f"  Rejection Reason: {validation['rejection_reason']}")