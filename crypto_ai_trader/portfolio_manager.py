"""
Portfolio Manager - Paper trading execution, risk management, position tracking
Handles all portfolio operations with real price data from database
"""

import psycopg2
import psycopg2.extras
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import json

# ============================================================================
# OVERFITTING PREVENTION CONSTANTS FOR POSITION SIZING
# ============================================================================
# These prevent the Gambler's Fallacy (betting more after wins)

# Minimum trade history required before trusting win/loss streaks
MIN_TRADES_FOR_STREAK_ADJUSTMENT = 50  # Need 50+ trades before adjusting size based on streaks
STREAK_LOOKBACK_WINDOW = 20  # Look at last 20 trades (not just 5)

# Cap the maximum adjustment from win streaks (prevents overconfidence)
MAX_STREAK_BOOST = 1.20  # Maximum 20% increase (down from 50%)
MAX_STREAK_REDUCTION = 0.80  # Maximum 20% reduction (down from 30%)

# Require statistical significance
MIN_WIN_RATE_FOR_BOOST = 0.70  # Need 70%+ win rate in window for boost (14/20 wins)
MAX_WIN_RATE_FOR_REDUCTION = 0.35  # Only reduce if <35% win rate (7/20 losses)

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

    def calculate_adaptive_position_size(self, token: str, base_confidence: float) -> float:
        """
        Calculate adaptive position size based on market conditions and performance
        Returns position size as percentage (0.5 to 5.0)
        """
        import config

        # Start with confidence-based sizing (60% conf = 1%, 90% conf = 5%)
        base_size = 1.0 + (base_confidence - 0.6) * 13.33  # Maps 0.6-0.9 to 1.0-5.0
        base_size = max(0.5, min(5.0, base_size))  # Clamp to 0.5-5.0 range

        # Calculate adjustment factors
        multiplier = 1.0

        # 1. MARKET VOLATILITY ADJUSTMENT (-50% to 0%)
        volatility = self.calculate_volatility(token, hours=24)
        if volatility > 7.0:  # Extreme volatility
            volatility_adj = 0.5  # Reduce size by 50%
            print(f"  [VOL] Volatility adjustment: -50% (ATR={volatility:.1f}% - extreme)")
        elif volatility > 5.0:  # High volatility
            volatility_adj = 0.7  # Reduce by 30%
            print(f"  [VOL] Volatility adjustment: -30% (ATR={volatility:.1f}% - high)")
        elif volatility < 2.0:  # Low volatility
            volatility_adj = 1.0  # No adjustment
            print(f"  [VOL] Volatility adjustment: 0% (ATR={volatility:.1f}% - low)")
        else:  # Normal volatility
            volatility_adj = 0.85  # Reduce by 15%
            print(f"  [VOL] Volatility adjustment: -15% (ATR={volatility:.1f}% - normal)")

        multiplier *= volatility_adj

        # 2. WIN STREAK ADJUSTMENT (WITH OVERFITTING PROTECTION)
        total_trades = len(self.trade_history)

        # === SAMPLE SIZE VALIDATION ===
        if total_trades < MIN_TRADES_FOR_STREAK_ADJUSTMENT:
            # INSUFFICIENT HISTORY - Don't trust streaks yet
            streak_adj = 0.90  # Slight reduction for new accounts (conservative)
            print(f"  [NEW] New account: -10% size (only {total_trades}/{MIN_TRADES_FOR_STREAK_ADJUSTMENT} trades)")
            print(f"  [INFO] Need {MIN_TRADES_FOR_STREAK_ADJUSTMENT} trades before streak adjustments activate")
        else:
            # SUFFICIENT HISTORY - Can trust statistics
            lookback_trades = self.trade_history[-STREAK_LOOKBACK_WINDOW:]
            wins_in_window = sum(1 for t in lookback_trades if t['pnl'] > 0)
            win_rate = wins_in_window / len(lookback_trades)

            # Statistical significance check
            if win_rate >= MIN_WIN_RATE_FOR_BOOST:
                # Strong performance - modest boost (capped at 20%)
                streak_adj = MAX_STREAK_BOOST
                print(f"  [WIN-STREAK] Win rate adjustment: +20% ({wins_in_window}/{len(lookback_trades)} wins = {win_rate:.0%})")
                print(f"  [PROTECTED] Boost capped at 20% (down from old 50% to prevent overconfidence)")
            elif win_rate <= MAX_WIN_RATE_FOR_REDUCTION:
                # Poor performance - modest reduction (capped at 20%)
                streak_adj = MAX_STREAK_REDUCTION
                print(f"  [LOSS-STREAK] Win rate adjustment: -20% ({wins_in_window}/{len(lookback_trades)} wins = {win_rate:.0%})")
                print(f"  [PROTECTED] Reduction capped at 20% to maintain liquidity")
            else:
                # Normal performance - no adjustment
                streak_adj = 1.0
                print(f"  [NEUTRAL] Win rate adjustment: 0% ({wins_in_window}/{len(lookback_trades)} wins = {win_rate:.0%} - within normal range)")

        multiplier *= streak_adj

        # 3. DRAWDOWN ADJUSTMENT (-50% to 0%)
        total_value = self.get_total_value()
        drawdown_pct = ((self.peak_value - total_value) / self.peak_value) * 100 if self.peak_value > 0 else 0

        if drawdown_pct > 15:  # Severe drawdown
            drawdown_adj = 0.5  # Reduce by 50%
            print(f"  [DD-HIGH] Drawdown adjustment: -50% (down {drawdown_pct:.1f}%)")
        elif drawdown_pct > 10:  # High drawdown
            drawdown_adj = 0.6  # Reduce by 40%
            print(f"  [DD-MED] Drawdown adjustment: -40% (down {drawdown_pct:.1f}%)")
        elif drawdown_pct > 5:  # Moderate drawdown
            drawdown_adj = 0.75  # Reduce by 25%
            print(f"  [DD-LOW] Drawdown adjustment: -25% (down {drawdown_pct:.1f}%)")
        else:  # Low/no drawdown
            drawdown_adj = 1.0
            print(f"  [DD-OK] Drawdown adjustment: 0% (down {drawdown_pct:.1f}%)")

        multiplier *= drawdown_adj

        # 4. MARKET REGIME ADJUSTMENT (-30% to +20%)
        # Check if BTC (market leader) is trending
        try:
            with self.conn.cursor() as cursor:
                cursor.execute("""
                    SELECT
                        (close - LAG(close, 288) OVER (ORDER BY timestamp)) / LAG(close, 288) OVER (ORDER BY timestamp) * 100 as daily_change
                    FROM crypto_ohlcv
                    WHERE token = 'BTC'
                    ORDER BY timestamp DESC
                    LIMIT 1
                """)
                result = cursor.fetchone()

                if result and result[0]:
                    btc_daily_change = float(result[0])

                    if btc_daily_change < -5:  # Bear market
                        regime_adj = 0.7  # Reduce by 30%
                        print(f"  [BEAR] Market regime adjustment: -30% (BTC down {btc_daily_change:.1f}%)")
                    elif btc_daily_change > 5:  # Bull market
                        regime_adj = 1.2  # Increase by 20%
                        print(f"  [BULL] Market regime adjustment: +20% (BTC up {btc_daily_change:.1f}%)")
                    else:  # Neutral
                        regime_adj = 1.0
                        print(f"  [NEUTRAL] Market regime adjustment: 0% (BTC {btc_daily_change:+.1f}%)")
                else:
                    regime_adj = 0.9  # Conservative if no data
                    print(f"  [NO-DATA] Market regime adjustment: -10% (no BTC data)")

        except Exception as e:
            regime_adj = 0.9  # Conservative on error
            print(f"  [ERROR] Market regime adjustment: -10% (error: {e})")

        multiplier *= regime_adj

        # 5. POSITION COUNT ADJUSTMENT (-50% to 0%)
        open_positions = len(self.positions)
        if open_positions >= 8:  # Too many positions
            position_adj = 0.5  # Reduce by 50%
            print(f"  [POS-MAX] Position count adjustment: -50% ({open_positions} open)")
        elif open_positions >= 5:  # Many positions
            position_adj = 0.7  # Reduce by 30%
            print(f"  [POS-HIGH] Position count adjustment: -30% ({open_positions} open)")
        elif open_positions >= 3:  # Some positions
            position_adj = 0.85  # Reduce by 15%
            print(f"  [POS-MED] Position count adjustment: -15% ({open_positions} open)")
        else:  # Few positions
            position_adj = 1.0
            print(f"  [POS-OK] Position count adjustment: 0% ({open_positions} open)")

        multiplier *= position_adj

        # Calculate final adaptive size
        adaptive_size = base_size * multiplier

        # Apply final bounds
        adaptive_size = max(0.5, min(5.0, adaptive_size))

        print(f"  [FINAL] Position size: {adaptive_size:.1f}% (base {base_size:.1f}% x {multiplier:.2f})")

        return adaptive_size

    def calculate_position_size(self, suggested_pct: float, price: float, token: str = None, confidence: float = 0.7) -> float:
        """Calculate actual position size considering risk limits"""
        import config

        # Get available cash
        available_cash = self.get_available_cash()

        # Use adaptive sizing if token and confidence provided
        if token and hasattr(config, 'ENABLE_ADAPTIVE_POSITION_SIZING') and config.ENABLE_ADAPTIVE_POSITION_SIZING:
            suggested_pct = self.calculate_adaptive_position_size(token, confidence)

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

    def check_sector_exposure(self, new_token: str) -> bool:
        """
        Prevent opening too many positions in same sector (max 3 per sector)
        Prevents correlated losses when entire sector dumps
        """
        # Define crypto sectors based on your Twitter scrapers
        sectors = {
            'MEME': ['PEPE', 'DOGE', 'SHIB', 'BONK', 'WIF'],
            'DEFI': ['UNI', 'AAVE', 'LDO', 'MKR', 'CRV', 'GMX', 'SNX', 'LINK'],
            'L1': ['BTC', 'ETH', 'SOL', 'BNB', 'ADA', 'AVAX', 'DOT', 'NEAR', 'ATOM',
                   'ICP', 'ALGO', 'FTM', 'TRX', 'XRP', 'SUI', 'TON', 'SEI', 'LTC'],
            'L2': ['ARB', 'OP', 'MATIC', 'METIS', 'IMX'],
            'AI': ['RENDER', 'FET', 'GRT', 'OCEAN', 'AGIX', 'TAO']
        }

        # Find new token's sector
        new_sector = None
        for sector, tokens in sectors.items():
            if new_token in tokens:
                new_sector = sector
                break

        if not new_sector:
            # Unknown sector - allow it (could be a new emerging token)
            return True

        # Count open positions in same sector
        sector_count = 0
        for token in self.positions.keys():
            if token in sectors.get(new_sector, []):
                sector_count += 1

        max_per_sector = 3  # User requested 3 positions max per sector

        if sector_count >= max_per_sector:
            print(f"[WARNING] BLOCKED: Already have {sector_count} positions in {new_sector} sector (max {max_per_sector})")
            print(f"   Open positions: {[t for t in self.positions.keys() if t in sectors[new_sector]]}")
            return False

        return True

    def open_position(self, token: str, entry_price: float, position_value: float,
                     stop_loss_pct: float, take_profit_pct: float, reasoning: str, position_type: str = 'LONG') -> bool:
        """
        Open a new position (LONG or SHORT)

        LONG: Profit when price goes UP (standard buy)
        SHORT: Profit when price goes DOWN (sell first, buy back later)

        Paper trading simulation - no real futures needed yet
        """
        try:
            import config

            # Validate position type
            if position_type not in ['LONG', 'SHORT']:
                print(f"[ERROR] Invalid position type: {position_type}")
                return False

            # Check if position already exists
            if token in self.positions:
                print(f"[WARNING] Position already exists for {token}")
                return False

            # Check sector exposure limit (max 3 per sector)
            if not self.check_sector_exposure(token):
                return False

            # Calculate quantity
            quantity = position_value / entry_price

            # Apply fees and slippage
            fees = position_value * (config.TRADING_FEE_PCT / 100)
            slippage = position_value * (config.SLIPPAGE_PCT / 100)
            total_cost = position_value + fees + slippage

            # Check cash (needed for both LONG and SHORT as collateral)
            if total_cost > self.cash:
                print(f"[ERROR] Insufficient cash: need ${total_cost:.2f}, have ${self.cash:.2f}")
                return False

            # Calculate stop loss and take profit based on position type
            if position_type == 'LONG':
                # LONG: Stop below, profit above
                stop_loss_price = entry_price * (1 - stop_loss_pct/100)
                take_profit_price = entry_price * (1 + take_profit_pct/100)
            else:  # SHORT
                # SHORT: Stop above (price goes UP = loss), profit below (price goes DOWN = profit)
                stop_loss_price = entry_price * (1 + stop_loss_pct/100)
                take_profit_price = entry_price * (1 - take_profit_pct/100)

            # Create position
            position = {
                'token': token,
                'position_type': position_type,  # NEW: Track position type
                'entry_price': entry_price,
                'quantity': quantity,
                'position_value': position_value,
                'stop_loss': stop_loss_price,
                'take_profit': take_profit_price,
                'stop_loss_pct': stop_loss_pct,  # NEW: Store original percentages
                'take_profit_pct': take_profit_pct,
                'entry_time': datetime.now(),
                'reasoning': reasoning,
                'fees_paid': fees + slippage,
                'status': 'OPEN',
                'partial_exits': [],  # Track partial profit taking
                'remaining_pct': 100.0  # Track remaining position percentage
            }

            # Update portfolio
            self.positions[token] = position
            self.cash -= total_cost
            self.trade_count += 1

            # Log to database
            action = 'BUY' if position_type == 'LONG' else 'SHORT'
            self.log_trade_decision(
                token=token,
                action=action,
                price=entry_price,
                quantity=quantity,
                value=position_value,
                reasoning=reasoning
            )

            # Save state
            self.save_portfolio_state()

            print(f"[{position_type} POSITION OPENED] {token}")
            print(f"  Type: {position_type}")
            print(f"  Entry: ${entry_price:.4f}")
            print(f"  Quantity: {quantity:.6f}")
            print(f"  Value: ${position_value:.2f}")
            print(f"  Stop Loss: ${stop_loss_price:.4f} ({'+' if position_type == 'SHORT' else '-'}{stop_loss_pct:.1f}%)")
            print(f"  Take Profit: ${take_profit_price:.4f} ({'-' if position_type == 'SHORT' else '+'}{take_profit_pct:.1f}%)")
            print(f"  Fees: ${fees + slippage:.2f}")

            return True

        except Exception as e:
            print(f"[ERROR] Failed to open position: {e}")
            return False

    def close_position(self, token: str, exit_price: float, reasoning: str) -> bool:
        """Close an existing position (handles both LONG and SHORT)"""
        try:
            import config

            # Check if position exists
            if token not in self.positions:
                print(f"[ERROR] No position exists for {token}")
                return False

            position = self.positions[token]
            position_type = position.get('position_type', 'LONG')  # Default to LONG for backward compatibility

            # Calculate exit value
            exit_value = position['quantity'] * exit_price

            # Apply fees and slippage
            fees = exit_value * (config.TRADING_FEE_PCT / 100)
            slippage = exit_value * (config.SLIPPAGE_PCT / 100)

            # Calculate P&L based on position type
            if position_type == 'LONG':
                # LONG: Profit when price goes UP
                net_proceeds = exit_value - fees - slippage
                pnl = net_proceeds - position['position_value']
                pnl_pct = ((exit_price - position['entry_price']) / position['entry_price']) * 100
                cash_returned = net_proceeds
            else:  # SHORT
                # SHORT: Profit when price goes DOWN
                # Entry: sold at entry_price (got cash)
                # Exit: buy back at exit_price (pay cash)
                # P&L = (entry_value - exit_value) - fees
                entry_value = position['quantity'] * position['entry_price']
                exit_cost = exit_value + fees + slippage
                pnl = entry_value - exit_value - fees - slippage
                pnl_pct = ((position['entry_price'] - exit_price) / position['entry_price']) * 100
                # Return collateral + profit (or - loss)
                cash_returned = position['position_value'] + pnl

            # Update cash
            self.cash += cash_returned

            # Update statistics
            self.total_pnl += pnl
            self.daily_pnl += pnl

            if pnl > 0:
                self.winning_trades += 1
            else:
                self.losing_trades += 1

            # Log to database
            action = 'COVER' if position_type == 'SHORT' else 'SELL'
            self.log_trade_decision(
                token=token,
                action=action,
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

            print(f"[{position_type} POSITION CLOSED] {token}")
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

    def partial_close_position(self, token: str, exit_percentage: float, exit_price: float, reasoning: str) -> bool:
        """
        Partially close a position (e.g., take 30% profit)
        Handles both LONG and SHORT positions
        exit_percentage: 0-100 (e.g., 30 = close 30% of position)
        """
        try:
            import config

            # Check if position exists
            if token not in self.positions:
                print(f"[ERROR] No position exists for {token}")
                return False

            position = self.positions[token]
            position_type = position.get('position_type', 'LONG')

            # Validate exit percentage
            if exit_percentage <= 0 or exit_percentage > position.get('remaining_pct', 100):
                print(f"[ERROR] Invalid exit percentage: {exit_percentage}% (remaining: {position.get('remaining_pct', 100)}%)")
                return False

            # Calculate partial quantity to close
            partial_quantity = position['quantity'] * (exit_percentage / 100)
            exit_value = partial_quantity * exit_price

            # Apply fees and slippage
            fees = exit_value * (config.TRADING_FEE_PCT / 100)
            slippage = exit_value * (config.SLIPPAGE_PCT / 100)

            # Calculate partial P&L based on position type
            partial_cost_basis = position['position_value'] * (exit_percentage / 100)

            if position_type == 'LONG':
                # LONG: Profit when price goes UP
                net_proceeds = exit_value - fees - slippage
                partial_pnl = net_proceeds - partial_cost_basis
                partial_pnl_pct = ((exit_price - position['entry_price']) / position['entry_price']) * 100
                cash_returned = net_proceeds
            else:  # SHORT
                # SHORT: Profit when price goes DOWN
                entry_value = partial_quantity * position['entry_price']
                partial_pnl = entry_value - exit_value - fees - slippage
                partial_pnl_pct = ((position['entry_price'] - exit_price) / position['entry_price']) * 100
                cash_returned = partial_cost_basis + partial_pnl

            # Update cash
            self.cash += cash_returned

            # Update position (reduce quantity and value)
            position['quantity'] -= partial_quantity
            position['position_value'] -= partial_cost_basis
            position['remaining_pct'] = position.get('remaining_pct', 100) - exit_percentage

            # Track partial exit
            if 'partial_exits' not in position:
                position['partial_exits'] = []

            position['partial_exits'].append({
                'exit_time': datetime.now(),
                'exit_price': exit_price,
                'exit_percentage': exit_percentage,
                'quantity_sold': partial_quantity,
                'pnl': partial_pnl,
                'pnl_pct': partial_pnl_pct,
                'reasoning': reasoning
            })

            # Update statistics (partial exits count as partial wins/losses)
            self.total_pnl += partial_pnl
            self.daily_pnl += partial_pnl

            # Log to database
            self.log_trade_decision(
                token=token,
                action='PARTIAL_SELL',
                price=exit_price,
                quantity=partial_quantity,
                value=exit_value,
                reasoning=f"{reasoning} | Partial Exit: {exit_percentage}% | P&L: ${partial_pnl:.2f} ({partial_pnl_pct:.1f}%)",
                pnl=partial_pnl
            )

            # Save state
            self.save_portfolio_state()

            print(f"[PARTIAL CLOSE] {token} - {exit_percentage}% exited")
            print(f"  Exit Price: ${exit_price:.4f}")
            print(f"  Quantity Sold: {partial_quantity:.6f}")
            print(f"  Partial P&L: ${partial_pnl:.2f} ({partial_pnl_pct:.1f}%)")
            print(f"  Remaining: {position['remaining_pct']:.0f}% ({position['quantity']:.6f})")
            print(f"  Fees: ${fees + slippage:.2f}")

            return True

        except Exception as e:
            print(f"[ERROR] Failed to partially close position: {e}")
            return False

    def calculate_volatility(self, token: str, hours: int = 24) -> float:
        """Calculate ATR-based volatility for adaptive stop-loss"""
        try:
            with self.conn.cursor() as cursor:
                cursor.execute("""
                    SELECT
                        AVG((high - low) / NULLIF(close, 0)) * 100 as atr_percentage
                    FROM crypto_ohlcv
                    WHERE token = %s
                    AND timestamp > NOW() - INTERVAL '1 hour' * %s
                """, (token, hours))

                result = cursor.fetchone()
                return float(result[0]) if result and result[0] else 3.0  # Default 3% if no data

        except Exception as e:
            print(f"[ERROR] Volatility calculation failed for {token}: {e}")
            return 3.0  # Default volatility

    def check_liquidation_clusters(self, token: str, current_price: float) -> Optional[float]:
        """Check for liquidation clusters near current price"""
        try:
            with self.conn.cursor() as cursor:
                # Look for liquidation clusters below current price
                cursor.execute("""
                    SELECT
                        price,
                        SUM(liquidation_value) as cluster_value
                    FROM liquidations
                    WHERE token = %s
                    AND scraped_at > NOW() - INTERVAL '1 hour'
                    AND side = 'LONG'
                    AND price BETWEEN %s AND %s
                    GROUP BY price
                    ORDER BY cluster_value DESC
                    LIMIT 1
                """, (token, current_price * 0.9, current_price * 0.98))

                result = cursor.fetchone()
                if result and result[1] > 100000:  # Significant cluster
                    return float(result[0])  # Return price level with cluster
                return None

        except Exception as e:
            print(f"[ERROR] Liquidation cluster check failed: {e}")
            return None

    def update_adaptive_stop_loss(self, token: str, position: Dict) -> float:
        """Calculate adaptive stop-loss based on volatility and market conditions"""
        import config

        current_price = self.get_current_price(token)
        if not current_price:
            return position['stop_loss']  # Keep existing if no price

        position_type = position.get('position_type', 'LONG')

        # Get current volatility (ATR)
        volatility = self.calculate_volatility(token, hours=24)

        # Base stop-loss adjustment based on volatility
        if volatility < 2.0:  # Low volatility
            adaptive_stop_pct = 2.0  # Tighter stop
            adjustment_reason = "low volatility"
        elif volatility > 5.0:  # High volatility
            adaptive_stop_pct = min(volatility, 8.0)  # Wider stop, max 8%
            adjustment_reason = "high volatility"
        else:  # Normal volatility
            adaptive_stop_pct = 3.0
            adjustment_reason = "normal volatility"

        # Check for liquidation clusters (LONG positions only for now)
        if position_type == 'LONG':
            cluster_level = self.check_liquidation_clusters(token, current_price)
            if cluster_level and cluster_level < current_price:
                # Place stop above liquidation cluster to avoid cascade
                new_stop = cluster_level * 1.01  # 1% above cluster
                if new_stop > position['stop_loss']:
                    print(f"[STOP] {token}: Adjusted stop to ${new_stop:.4f} (above liquidation cluster)")
                    return new_stop

        # Calculate new stop based on volatility and position type
        if position_type == 'LONG':
            # LONG: Stop below current price
            new_stop = current_price * (1 - adaptive_stop_pct/100)

            # Implement trailing stop - only move stop UP (tighter), never down
            if new_stop > position['stop_loss']:
                # Check if price has moved favorably
                price_gain_pct = (current_price - position['entry_price']) / position['entry_price'] * 100

                # Only trail stop if we're in profit
                if price_gain_pct > 2.0:  # At least 2% profit
                    print(f"[STOP] {token} LONG: Trailing stop to ${new_stop:.4f} ({adjustment_reason}, +{price_gain_pct:.1f}% gain)")
                    return new_stop

        else:  # SHORT
            # SHORT: Stop above current price
            new_stop = current_price * (1 + adaptive_stop_pct/100)

            # Implement trailing stop - only move stop DOWN (tighter), never up
            if new_stop < position['stop_loss']:
                # Check if price has moved favorably (fallen from entry)
                price_gain_pct = (position['entry_price'] - current_price) / position['entry_price'] * 100

                # Only trail stop if we're in profit
                if price_gain_pct > 2.0:  # At least 2% profit (price dropped)
                    print(f"[STOP] {token} SHORT: Trailing stop to ${new_stop:.4f} ({adjustment_reason}, +{price_gain_pct:.1f}% gain)")
                    return new_stop

        return position['stop_loss']  # Keep existing stop

    def update_positions(self):
        """Update all positions with current prices and adaptive stop-loss"""
        import config

        positions_to_close = []

        for token, position in self.positions.items():
            # Get current price
            current_price = self.get_current_price(token)
            if not current_price:
                continue

            # Get position type
            position_type = position.get('position_type', 'LONG')

            # Update adaptive stop-loss if enabled
            if hasattr(config, 'ENABLE_ADAPTIVE_STOPS') and config.ENABLE_ADAPTIVE_STOPS:
                position['stop_loss'] = self.update_adaptive_stop_loss(token, position)

            # Check stop loss (direction depends on position type)
            if position_type == 'LONG':
                # LONG: Stop triggers when price goes DOWN
                if current_price <= position['stop_loss']:
                    positions_to_close.append((token, current_price, "Stop loss triggered"))
                    continue
            else:  # SHORT
                # SHORT: Stop triggers when price goes UP
                if current_price >= position['stop_loss']:
                    positions_to_close.append((token, current_price, "Stop loss triggered"))
                    continue

            # Check take profit (direction depends on position type)
            if position_type == 'LONG':
                # LONG: Profit triggers when price goes UP
                if current_price >= position['take_profit']:
                    positions_to_close.append((token, current_price, "Take profit triggered"))
                    continue
            else:  # SHORT
                # SHORT: Profit triggers when price goes DOWN
                if current_price <= position['take_profit']:
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

    def check_market_crash(self) -> bool:
        """
        Check if BTC is crashing (>5% drop in 5 min) - emergency exit signal
        Prevents getting wiped out in liquidation cascades
        """
        try:
            with self.conn.cursor() as cursor:
                # Get BTC price now vs 5 minutes ago
                cursor.execute("""
                    SELECT
                        (SELECT close FROM crypto_ohlcv
                         WHERE token = 'BTC'
                         ORDER BY timestamp DESC LIMIT 1) as current_price,
                        (SELECT close FROM crypto_ohlcv
                         WHERE token = 'BTC'
                         AND timestamp <= NOW() - INTERVAL '5 minutes'
                         ORDER BY timestamp DESC LIMIT 1) as price_5min_ago
                """)

                result = cursor.fetchone()

                if result and result[0] and result[1]:
                    current_price = float(result[0])
                    price_5min_ago = float(result[1])
                    pct_change = ((current_price - price_5min_ago) / price_5min_ago) * 100

                    if pct_change < -5.0:
                        print(f"[CRASH] MARKET CRASH DETECTED: BTC down {pct_change:.2f}% in 5min")
                        return True

                return False

        except Exception as e:
            print(f"[ERROR] Market crash check failed: {e}")
            return False

    def get_positions(self) -> Dict:
        """Get current positions with latest values"""
        positions_data = {}

        for token, position in self.positions.items():
            current_price = self.get_current_price(token)
            if current_price:
                position_type = position.get('position_type', 'LONG')
                current_value = position['quantity'] * current_price

                # Calculate P&L based on position type
                if position_type == 'LONG':
                    # LONG: Profit when current > entry
                    pnl = current_value - position['position_value']
                else:  # SHORT
                    # SHORT: Profit when current < entry
                    pnl = position['position_value'] - current_value

                pnl_pct = (pnl / position['position_value']) * 100

                positions_data[token] = {
                    'entry_price': position['entry_price'],
                    'current_price': current_price,
                    'quantity': position['quantity'],
                    'position_type': position_type,
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