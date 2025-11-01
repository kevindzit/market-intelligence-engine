"""
Paper Trading Engine
Simulates trade execution with realistic fees and slippage
Tracks P&L and updates portfolio state
Critical for validation before live trading
"""

import psycopg2
from datetime import datetime
from typing import Dict, Optional, Tuple
import json
import random
import config


class PaperTradingEngine:
    """Simulates trading execution for validation"""

    def __init__(self):
        """Initialize paper trading engine"""
        self.trade_pair_counter = 1000  # For tracking entry/exit pairs

    def get_db_connection(self):
        """Get database connection"""
        return psycopg2.connect(
            host=config.DB_HOST,
            port=config.DB_PORT,
            database=config.DB_NAME,
            user=config.DB_USER,
            password=config.DB_PASSWORD
        )

    def execute_trade(self, decision_id: int, validated_trade: Dict, current_price: float) -> Dict:
        """
        Execute a paper trade

        Args:
            decision_id: ID from trading_decisions table
            validated_trade: Validated trade parameters from risk manager
            current_price: Current market price of token

        Returns:
            Dict with execution details
        """

        token = validated_trade.get('token')
        action = validated_trade['action']

        if action == 'BUY':
            result = self._execute_buy(decision_id, validated_trade, current_price)
        elif action == 'SELL':
            result = self._execute_sell(decision_id, validated_trade, current_price)
        else:  # HOLD
            result = {
                'executed': False,
                'reason': 'HOLD signal - no action taken'
            }

        # Update portfolio state after trade
        if result.get('executed'):
            self._update_portfolio_state(result)

        return result

    def _execute_buy(self, decision_id: int, trade: Dict, market_price: float) -> Dict:
        """Execute a BUY order"""

        # Simulate slippage (price moves against us)
        slippage = random.uniform(0, config.SLIPPAGE_PCT) / 100
        execution_price = market_price * (1 + slippage)

        # Calculate position size in tokens
        position_usd = trade['position_size_usd']
        fee_pct = config.TRADING_FEE_PCT / 100
        fee_usd = position_usd * fee_pct

        # Actual USD spent (including fees)
        total_cost = position_usd + fee_usd

        # Tokens received (after fees)
        tokens_bought = (position_usd - fee_usd) / execution_price

        # Record trade
        conn = self.get_db_connection()
        cursor = conn.cursor()

        try:
            # Insert paper trade record
            cursor.execute("""
                INSERT INTO paper_trades
                (decision_id, token, side, quantity, price, value_usd,
                 fee_pct, fee_usd, trade_pair_id, is_entry, slippage_pct)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                decision_id,
                trade['token'],
                'BUY',
                tokens_bought,
                execution_price,
                position_usd,
                config.TRADING_FEE_PCT,
                fee_usd,
                self.trade_pair_counter,
                True,
                slippage * 100
            ))

            trade_id = cursor.fetchone()[0]
            self.trade_pair_counter += 1

            # Update decision status
            cursor.execute("""
                UPDATE trading_decisions
                SET status = 'EXECUTED',
                    executed_at = NOW(),
                    entry_price = %s
                WHERE id = %s
            """, (execution_price, decision_id))

            conn.commit()

            result = {
                'executed': True,
                'trade_id': trade_id,
                'token': trade['token'],
                'side': 'BUY',
                'quantity': tokens_bought,
                'execution_price': execution_price,
                'market_price': market_price,
                'slippage_pct': slippage * 100,
                'position_usd': position_usd,
                'fee_usd': fee_usd,
                'total_cost': total_cost,
                'trade_pair_id': self.trade_pair_counter - 1
            }

            if config.VERBOSE_LOGGING:
                print(f"\n[PAPER TRADE] BUY Executed:")
                print(f"  Token: {trade['token']}")
                print(f"  Quantity: {tokens_bought:.8f}")
                print(f"  Price: ${execution_price:.2f} (market: ${market_price:.2f})")
                print(f"  Slippage: {slippage*100:.3f}%")
                print(f"  Position Value: ${position_usd:.2f}")
                print(f"  Fees: ${fee_usd:.2f}")
                print(f"  Total Cost: ${total_cost:.2f}")

            return result

        except Exception as e:
            conn.rollback()
            print(f"[ERROR] Failed to execute BUY: {e}")
            return {
                'executed': False,
                'error': str(e)
            }

        finally:
            cursor.close()
            conn.close()

    def _execute_sell(self, decision_id: int, trade: Dict, market_price: float) -> Dict:
        """Execute a SELL order"""

        # Get current position
        position = self._get_position(trade['token'])
        if not position:
            return {
                'executed': False,
                'reason': f"No position found for {trade['token']}"
            }

        # Simulate slippage (price moves against us)
        slippage = random.uniform(0, config.SLIPPAGE_PCT) / 100
        execution_price = market_price * (1 - slippage)

        # Sell entire position
        tokens_to_sell = position['quantity']
        gross_proceeds = tokens_to_sell * execution_price

        # Calculate fees
        fee_pct = config.TRADING_FEE_PCT / 100
        fee_usd = gross_proceeds * fee_pct

        # Net proceeds after fees
        net_proceeds = gross_proceeds - fee_usd

        # Calculate P&L
        entry_price = position['entry_price']
        pnl_usd = net_proceeds - position['cost_basis']
        pnl_pct = (pnl_usd / position['cost_basis']) * 100

        # Record trade
        conn = self.get_db_connection()
        cursor = conn.cursor()

        try:
            # Insert paper trade record
            cursor.execute("""
                INSERT INTO paper_trades
                (decision_id, token, side, quantity, price, value_usd,
                 fee_pct, fee_usd, trade_pair_id, is_entry, slippage_pct,
                 pnl_usd, pnl_pct)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                decision_id,
                trade['token'],
                'SELL',
                tokens_to_sell,
                execution_price,
                gross_proceeds,
                config.TRADING_FEE_PCT,
                fee_usd,
                position['trade_pair_id'],
                False,
                slippage * 100,
                pnl_usd,
                pnl_pct
            ))

            trade_id = cursor.fetchone()[0]

            # Update decision with exit details
            outcome = 'WIN' if pnl_usd > 0 else 'LOSS'
            cursor.execute("""
                UPDATE trading_decisions
                SET status = 'CLOSED',
                    outcome = %s,
                    exit_price = %s,
                    pnl_usd = %s,
                    pnl_pct = %s,
                    closed_at = NOW()
                WHERE id = %s
            """, (outcome, execution_price, pnl_usd, pnl_pct, position['decision_id']))

            conn.commit()

            result = {
                'executed': True,
                'trade_id': trade_id,
                'token': trade['token'],
                'side': 'SELL',
                'quantity': tokens_to_sell,
                'execution_price': execution_price,
                'market_price': market_price,
                'slippage_pct': slippage * 100,
                'gross_proceeds': gross_proceeds,
                'fee_usd': fee_usd,
                'net_proceeds': net_proceeds,
                'entry_price': entry_price,
                'pnl_usd': pnl_usd,
                'pnl_pct': pnl_pct,
                'outcome': outcome
            }

            if config.VERBOSE_LOGGING:
                print(f"\n[PAPER TRADE] SELL Executed:")
                print(f"  Token: {trade['token']}")
                print(f"  Quantity: {tokens_to_sell:.8f}")
                print(f"  Entry Price: ${entry_price:.2f}")
                print(f"  Exit Price: ${execution_price:.2f} (market: ${market_price:.2f})")
                print(f"  Gross Proceeds: ${gross_proceeds:.2f}")
                print(f"  Fees: ${fee_usd:.2f}")
                print(f"  Net Proceeds: ${net_proceeds:.2f}")
                print(f"  P&L: ${pnl_usd:.2f} ({pnl_pct:+.2f}%)")
                print(f"  Outcome: {outcome}")

            return result

        except Exception as e:
            conn.rollback()
            print(f"[ERROR] Failed to execute SELL: {e}")
            return {
                'executed': False,
                'error': str(e)
            }

        finally:
            cursor.close()
            conn.close()

    def _get_position(self, token: str) -> Optional[Dict]:
        """Get current position for a token"""
        conn = self.get_db_connection()
        cursor = conn.cursor()

        try:
            # Get the most recent portfolio state
            cursor.execute("""
                SELECT positions
                FROM portfolio_state
                ORDER BY id DESC
                LIMIT 1
            """)

            result = cursor.fetchone()
            if not result or not result[0]:
                return None

            positions = result[0]
            if token not in positions:
                return None

            position = positions[token]

            # Get additional details from paper_trades
            cursor.execute("""
                SELECT
                    pt.quantity,
                    pt.price,
                    pt.value_usd + pt.fee_usd as cost_basis,
                    pt.trade_pair_id,
                    pt.decision_id
                FROM paper_trades pt
                WHERE pt.token = %s
                  AND pt.side = 'BUY'
                  AND pt.is_entry = true
                  AND NOT EXISTS (
                      SELECT 1 FROM paper_trades pt2
                      WHERE pt2.trade_pair_id = pt.trade_pair_id
                        AND pt2.side = 'SELL'
                  )
                ORDER BY pt.id DESC
                LIMIT 1
            """, (token,))

            trade_result = cursor.fetchone()
            if trade_result:
                return {
                    'token': token,
                    'quantity': float(trade_result[0]),
                    'entry_price': float(trade_result[1]),
                    'cost_basis': float(trade_result[2]),
                    'trade_pair_id': int(trade_result[3]),
                    'decision_id': int(trade_result[4])
                }

            return None

        finally:
            cursor.close()
            conn.close()

    def _update_portfolio_state(self, trade_result: Dict):
        """Update portfolio state after a trade"""
        conn = self.get_db_connection()
        cursor = conn.cursor()

        try:
            # Get current portfolio
            cursor.execute("""
                SELECT id, total_value, cash, positions, winning_trades,
                       losing_trades, total_trades
                FROM portfolio_state
                ORDER BY id DESC
                LIMIT 1
            """)

            portfolio = cursor.fetchone()
            if not portfolio:
                print("[ERROR] No portfolio state found")
                return

            portfolio_id = portfolio[0]
            total_value = float(portfolio[1])
            cash = float(portfolio[2])
            positions = portfolio[3] if portfolio[3] else {}
            winning_trades = int(portfolio[4]) if portfolio[4] else 0
            losing_trades = int(portfolio[5]) if portfolio[5] else 0
            total_trades = int(portfolio[6]) if portfolio[6] else 0

            # Update based on trade type
            if trade_result['side'] == 'BUY':
                # Reduce cash
                cash -= trade_result['total_cost']

                # Add position
                positions[trade_result['token']] = {
                    'quantity': trade_result['quantity'],
                    'entry_price': trade_result['execution_price'],
                    'value_usd': trade_result['position_usd'],
                    'trade_pair_id': trade_result['trade_pair_id']
                }

            elif trade_result['side'] == 'SELL':
                # Increase cash
                cash += trade_result['net_proceeds']

                # Remove position
                if trade_result['token'] in positions:
                    del positions[trade_result['token']]

                # Update trade statistics
                total_trades += 1
                if trade_result['outcome'] == 'WIN':
                    winning_trades += 1
                else:
                    losing_trades += 1

            # Calculate positions value
            positions_value = sum(p.get('value_usd', 0) for p in positions.values())

            # Update total value
            total_value = cash + positions_value

            # Calculate win rate
            win_rate = winning_trades / total_trades if total_trades > 0 else 0

            # Insert new portfolio state
            cursor.execute("""
                INSERT INTO portfolio_state
                (total_value, cash, positions_value, positions,
                 winning_trades, losing_trades, total_trades, win_rate)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                total_value,
                cash,
                positions_value,
                json.dumps(positions),
                winning_trades,
                losing_trades,
                total_trades,
                win_rate
            ))

            conn.commit()

            if config.VERBOSE_LOGGING:
                print(f"\n[PORTFOLIO] Updated:")
                print(f"  Total Value: ${total_value:,.2f}")
                print(f"  Cash: ${cash:,.2f}")
                print(f"  Positions Value: ${positions_value:,.2f}")
                print(f"  Active Positions: {len(positions)}")
                if total_trades > 0:
                    print(f"  Win Rate: {win_rate:.1%} ({winning_trades}W/{losing_trades}L)")

        except Exception as e:
            conn.rollback()
            print(f"[ERROR] Failed to update portfolio: {e}")

        finally:
            cursor.close()
            conn.close()

    def get_current_price(self, token: str) -> float:
        """Get current price for a token from database"""
        conn = self.get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT close
                FROM crypto_ohlcv
                WHERE token = %s
                ORDER BY timestamp DESC
                LIMIT 1
            """, (token,))

            result = cursor.fetchone()
            if result:
                return float(result[0])

            # If no OHLCV data, return a mock price for testing
            mock_prices = {
                'BTC': 109000.0,
                'ETH': 3900.0,
                'SOL': 250.0
            }
            return mock_prices.get(token, 100.0)

        finally:
            cursor.close()
            conn.close()


# Test function
if __name__ == "__main__":
    print("Testing Paper Trading Engine...\n")

    engine = PaperTradingEngine()

    # Test BUY execution
    test_buy = {
        'token': 'BTC',
        'action': 'BUY',
        'position_size_usd': 500.0,
        'stop_loss_pct': 3.0,
        'take_profit_pct': 6.0
    }

    current_price = engine.get_current_price('BTC')
    print(f"Current BTC Price: ${current_price:.2f}")

    print(f"\nExecuting test BUY...")
    result = engine.execute_trade(1, test_buy, current_price)

    if result.get('executed'):
        print(f"Trade executed successfully!")
    else:
        print(f"Trade failed: {result}")