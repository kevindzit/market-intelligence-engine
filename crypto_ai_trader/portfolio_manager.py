"""
Portfolio Manager - Paper trading execution, risk management, position tracking
Handles all portfolio operations with real price data from database
"""

import psycopg2
import psycopg2.extras
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import json

class PortfolioManager:
    """
    Manages paper trading portfolio with realistic execution simulation
    """

    def __init__(self, db_config: Dict, initial_capital: float):
        """Initialize portfolio manager"""
        self.db_config = db_config
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.positions = {}  # token -> position dict
        self.trade_history = []
        self.daily_pnl = 0
        self.total_pnl = 0
        self.trade_count = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.max_drawdown = 0
        self.peak_value = initial_capital

        # Connect to database
        self.conn = psycopg2.connect(
            host=db_config['host'],
            port=db_config['port'],
            database=db_config['database'],
            user=db_config['user'],
            password=db_config['password']
        )

        print(f"[Portfolio] Initialized with ${initial_capital:,.2f}")
        self.save_portfolio_state()

    def get_current_price(self, token: str) -> Optional[float]:
        """
        Get REAL current price from database
        This replaces the fake hardcoded prices!
        """
        try:
            with self.conn.cursor() as cursor:
                cursor.execute("""
                    SELECT close, timestamp
                    FROM crypto_ohlcv
                    WHERE token = %s
                    ORDER BY timestamp DESC
                    LIMIT 1
                """, (token,))

                result = cursor.fetchone()
                if result:
                    price = float(result[0])
                    return price
                else:
                    print(f"[ERROR] No price data for {token}")
                    return None

        except Exception as e:
            print(f"[ERROR] Price fetch failed for {token}: {e}")
            return None

    def calculate_position_size(self, suggested_pct: float, price: float) -> float:
        """Calculate actual position size considering risk limits"""
        import config

        # Get available cash
        available_cash = self.get_available_cash()

        # Apply percentage of available cash
        position_value = available_cash * (suggested_pct / 100)

        # Apply max position size limit
        max_position = available_cash * (config.MAX_POSITION_SIZE_PCT / 100)
        position_value = min(position_value, max_position)

        # Check minimum position size
        if position_value < config.MIN_POSITION_SIZE_USD:
            return 0

        # Apply trading fees and slippage
        total_cost = position_value * (1 + config.TRADING_FEE_PCT/100 + config.SLIPPAGE_PCT/100)

        # Make sure we have enough cash
        if total_cost > available_cash:
            position_value = available_cash / (1 + config.TRADING_FEE_PCT/100 + config.SLIPPAGE_PCT/100)

        return position_value

    def get_available_cash(self) -> float:
        """Get cash available for trading (respecting reserves)"""
        import config

        # Calculate minimum cash reserve
        total_value = self.get_total_value()
        min_reserve = total_value * (config.CASH_RESERVE_PCT / 100)

        # Available cash is current cash minus reserve
        available = max(0, self.cash - min_reserve)

        return available

    def open_position(self, token: str, entry_price: float, position_value: float,
                     stop_loss_pct: float, take_profit_pct: float, reasoning: str) -> bool:
        """Open a new position"""
        try:
            import config

            # Check if position already exists
            if token in self.positions:
                print(f"[WARNING] Position already exists for {token}")
                return False

            # Calculate quantity
            quantity = position_value / entry_price

            # Apply fees and slippage
            fees = position_value * (config.TRADING_FEE_PCT / 100)
            slippage = position_value * (config.SLIPPAGE_PCT / 100)
            total_cost = position_value + fees + slippage

            # Check cash
            if total_cost > self.cash:
                print(f"[ERROR] Insufficient cash: need ${total_cost:.2f}, have ${self.cash:.2f}")
                return False

            # Create position
            position = {
                'token': token,
                'entry_price': entry_price,
                'quantity': quantity,
                'position_value': position_value,
                'stop_loss': entry_price * (1 - stop_loss_pct/100),
                'take_profit': entry_price * (1 + take_profit_pct/100),
                'entry_time': datetime.now(),
                'reasoning': reasoning,
                'fees_paid': fees + slippage,
                'status': 'OPEN'
            }

            # Update portfolio
            self.positions[token] = position
            self.cash -= total_cost
            self.trade_count += 1

            # Log to database
            self.log_trade_decision(
                token=token,
                action='BUY',
                price=entry_price,
                quantity=quantity,
                value=position_value,
                reasoning=reasoning
            )

            # Save state
            self.save_portfolio_state()

            print(f"[POSITION OPENED] {token}")
            print(f"  Entry: ${entry_price:.4f}")
            print(f"  Quantity: {quantity:.6f}")
            print(f"  Value: ${position_value:.2f}")
            print(f"  Stop Loss: ${position['stop_loss']:.4f}")
            print(f"  Take Profit: ${position['take_profit']:.4f}")
            print(f"  Fees: ${fees + slippage:.2f}")

            return True

        except Exception as e:
            print(f"[ERROR] Failed to open position: {e}")
            return False

    def close_position(self, token: str, exit_price: float, reasoning: str) -> bool:
        """Close an existing position"""
        try:
            import config

            # Check if position exists
            if token not in self.positions:
                print(f"[ERROR] No position exists for {token}")
                return False

            position = self.positions[token]

            # Calculate exit value
            exit_value = position['quantity'] * exit_price

            # Apply fees and slippage
            fees = exit_value * (config.TRADING_FEE_PCT / 100)
            slippage = exit_value * (config.SLIPPAGE_PCT / 100)
            net_proceeds = exit_value - fees - slippage

            # Calculate P&L
            total_cost = position['position_value'] + position['fees_paid']
            pnl = net_proceeds - position['position_value']
            pnl_pct = (pnl / position['position_value']) * 100

            # Update cash
            self.cash += net_proceeds

            # Update statistics
            self.total_pnl += pnl
            self.daily_pnl += pnl

            if pnl > 0:
                self.winning_trades += 1
            else:
                self.losing_trades += 1

            # Log to database
            self.log_trade_decision(
                token=token,
                action='SELL',
                price=exit_price,
                quantity=position['quantity'],
                value=exit_value,
                reasoning=f"{reasoning} | P&L: ${pnl:.2f} ({pnl_pct:.1f}%)",
                pnl=pnl
            )

            # Remove position
            del self.positions[token]

            # Save state
            self.save_portfolio_state()

            print(f"[POSITION CLOSED] {token}")
            print(f"  Exit: ${exit_price:.4f}")
            print(f"  P&L: ${pnl:.2f} ({pnl_pct:.1f}%)")
            print(f"  Fees: ${fees + slippage:.2f}")

            # Add to trade history
            self.trade_history.append({
                'token': token,
                'entry_price': position['entry_price'],
                'exit_price': exit_price,
                'quantity': position['quantity'],
                'pnl': pnl,
                'pnl_pct': pnl_pct,
                'entry_time': position['entry_time'],
                'exit_time': datetime.now(),
                'hold_time': (datetime.now() - position['entry_time']).total_seconds() / 3600
            })

            return True

        except Exception as e:
            print(f"[ERROR] Failed to close position: {e}")
            return False

    def update_positions(self):
        """Update all positions with current prices and check stop/take profit"""
        import config

        positions_to_close = []

        for token, position in self.positions.items():
            # Get current price
            current_price = self.get_current_price(token)
            if not current_price:
                continue

            # Check stop loss
            if current_price <= position['stop_loss']:
                positions_to_close.append((token, current_price, "Stop loss triggered"))
                continue

            # Check take profit
            if current_price >= position['take_profit']:
                positions_to_close.append((token, current_price, "Take profit triggered"))
                continue

            # Check max hold time
            hold_time = (datetime.now() - position['entry_time']).total_seconds() / 3600
            if hold_time > config.MAX_HOLD_TIME_HOURS:
                positions_to_close.append((token, current_price, f"Max hold time ({config.MAX_HOLD_TIME_HOURS}h) exceeded"))

        # Close triggered positions
        for token, price, reason in positions_to_close:
            self.close_position(token, price, reason)

    def get_total_value(self) -> float:
        """Calculate total portfolio value"""
        total = self.cash

        # Add value of open positions
        for token, position in self.positions.items():
            current_price = self.get_current_price(token)
            if current_price:
                position_value = position['quantity'] * current_price
                total += position_value

        # Update drawdown
        if total > self.peak_value:
            self.peak_value = total
        else:
            drawdown = (self.peak_value - total) / self.peak_value * 100
            self.max_drawdown = max(self.max_drawdown, drawdown)

        return total

    def get_positions(self) -> Dict:
        """Get current positions with latest values"""
        positions_data = {}

        for token, position in self.positions.items():
            current_price = self.get_current_price(token)
            if current_price:
                current_value = position['quantity'] * current_price
                pnl = current_value - position['position_value']
                pnl_pct = (pnl / position['position_value']) * 100

                positions_data[token] = {
                    'entry_price': position['entry_price'],
                    'current_price': current_price,
                    'quantity': position['quantity'],
                    'current_value': current_value,
                    'pnl': pnl,
                    'pnl_pct': pnl_pct,
                    'stop_loss': position['stop_loss'],
                    'take_profit': position['take_profit'],
                    'hold_time_hours': (datetime.now() - position['entry_time']).total_seconds() / 3600
                }

        return positions_data

    def get_position(self, token: str) -> Optional[Dict]:
        """Get specific position"""
        return self.positions.get(token)

    def log_trade_decision(self, token: str, action: str, price: float,
                           quantity: float, value: float, reasoning: str, pnl: float = 0):
        """Log trading decision to database"""
        try:
            with self.conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO trading_decisions
                    (token, final_action, entry_price, position_size_usd,
                     tier1_reasoning, executed_at, status, pnl_usd)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    token, action, price, value, reasoning,
                    datetime.now(), 'EXECUTED', pnl
                ))
                self.conn.commit()

                # Also log to paper_trades table
                cursor.execute("""
                    INSERT INTO paper_trades
                    (token, side, quantity, price, value_usd, executed_at, pnl_usd)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    token, action, quantity, price, value, datetime.now(), pnl
                ))
                self.conn.commit()

        except Exception as e:
            print(f"[ERROR] Failed to log trade decision: {e}")
            self.conn.rollback()

    def save_portfolio_state(self):
        """Save current portfolio state to database"""
        try:
            with self.conn.cursor() as cursor:
                total_value = self.get_total_value()
                win_rate = (self.winning_trades / max(1, self.winning_trades + self.losing_trades)) * 100

                cursor.execute("""
                    INSERT INTO portfolio_state
                    (total_value, cash, positions_value, positions, daily_pnl, total_pnl,
                     total_pnl_pct, max_drawdown, total_trades, winning_trades, losing_trades, win_rate)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    total_value,
                    self.cash,
                    total_value - self.cash,
                    json.dumps(self.get_positions()),
                    self.daily_pnl,
                    self.total_pnl,
                    (self.total_pnl / self.initial_capital * 100),
                    self.max_drawdown,
                    self.trade_count,
                    self.winning_trades,
                    self.losing_trades,
                    win_rate
                ))
                self.conn.commit()

        except Exception as e:
            print(f"[ERROR] Failed to save portfolio state: {e}")
            self.conn.rollback()

    def print_summary(self):
        """Print portfolio summary"""
        total_value = self.get_total_value()
        total_return = ((total_value - self.initial_capital) / self.initial_capital) * 100
        win_rate = (self.winning_trades / max(1, self.winning_trades + self.losing_trades)) * 100

        print("\n" + "="*60)
        print("PORTFOLIO SUMMARY")
        print("="*60)
        print(f"Total Value: ${total_value:,.2f}")
        print(f"Cash: ${self.cash:,.2f}")
        print(f"Positions Value: ${total_value - self.cash:,.2f}")
        print(f"Total Return: {total_return:.2f}%")
        print(f"Total P&L: ${self.total_pnl:,.2f}")
        print(f"Daily P&L: ${self.daily_pnl:,.2f}")
        print(f"Max Drawdown: {self.max_drawdown:.2f}%")
        print()
        print(f"Total Trades: {self.trade_count}")
        print(f"Winning Trades: {self.winning_trades}")
        print(f"Losing Trades: {self.losing_trades}")
        print(f"Win Rate: {win_rate:.1f}%")
        print()
        print(f"Open Positions: {len(self.positions)}")

        if self.positions:
            print("\nOPEN POSITIONS:")
            for token, pos_data in self.get_positions().items():
                print(f"  {token}:")
                print(f"    Entry: ${self.positions[token]['entry_price']:.4f}")
                print(f"    Current: ${pos_data['current_price']:.4f}")
                print(f"    P&L: ${pos_data['pnl']:.2f} ({pos_data['pnl_pct']:.1f}%)")

        print("="*60)

    def reset_daily_stats(self):
        """Reset daily statistics (call at start of each day)"""
        self.daily_pnl = 0
        print(f"[Portfolio] Daily stats reset")

    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
            print("[Portfolio] Database connection closed")