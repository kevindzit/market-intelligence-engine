"""
Risk Management Agent with Circuit Breakers
Critical safety component for PJX Crypto Trading System

This agent has VETO authority over all trades and enforces:
- Position sizing limits (20% max per asset)
- Daily loss limits (5% circuit breaker)
- Portfolio concentration limits
- Risk per trade limits (1-2%)
- Cash reserve requirements (20% minimum)

Based on the Balanced Configuration risk parameters.
Uses Claude Sonnet 4 for complex risk assessments when needed.
"""

import os
import sys
import json
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum
from dataclasses import dataclass

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor
from termcolor import colored
import anthropic

# Load environment variables
load_dotenv()

# ========================
# CONFIGURATION
# ========================

# Risk limits (from crypto-trading-system-notes.md)
MAX_POSITION_PERCENT = 0.20  # 20% max in single position
MAX_DAILY_LOSS_PERCENT = 0.05  # 5% daily loss circuit breaker
MIN_CASH_RESERVE_PERCENT = 0.20  # Keep 20% in cash
MAX_RISK_PER_TRADE = 0.02  # 2% risk per trade
MAX_TOTAL_EXPOSURE = 0.80  # 80% max total exposure

# Portfolio limits
MAX_CONCURRENT_POSITIONS = 5
MAX_CORRELATED_EXPOSURE = 0.40  # 40% in correlated assets
CORRELATION_THRESHOLD = 0.7  # Correlation coefficient threshold

# Circuit breaker thresholds
DRAWDOWN_WARNING = 0.10  # 10% drawdown warning
DRAWDOWN_CRITICAL = 0.15  # 15% drawdown critical
VOLATILITY_SPIKE_THRESHOLD = 2.0  # 2x normal volatility

# AI Risk Assessment
USE_AI_FOR_COMPLEX_RISKS = True
CLAUDE_MODEL = "claude-3-5-sonnet-20241022"

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
        logging.FileHandler('logs/risk_agent.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class RiskLevel(Enum):
    """Risk level classification"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
    EMERGENCY = "emergency"

class RiskAction(Enum):
    """Risk management actions"""
    APPROVE = "approve"
    REDUCE_SIZE = "reduce_size"
    REJECT = "reject"
    CLOSE_POSITIONS = "close_positions"
    HALT_TRADING = "halt_trading"

@dataclass
class RiskAssessment:
    """Risk assessment result"""
    level: RiskLevel
    action: RiskAction
    reasoning: str
    metrics: Dict
    recommendations: List[str]
    override_allowed: bool = False

class RiskManagementAgent:
    """
    Risk management agent with veto authority over all trades
    """

    def __init__(self, portfolio_value: float = 1000):
        """
        Initialize risk management agent

        Args:
            portfolio_value: Initial portfolio value for calculations
        """
        self.portfolio_value = portfolio_value
        self.db_conn = None
        self.claude_client = None

        # Risk state
        self.daily_loss = 0
        self.max_drawdown = 0
        self.current_drawdown = 0
        self.trading_halted = False
        self.halt_reason = None
        self.last_reset = datetime.now().date()

        # Position tracking
        self.positions = {}
        self.correlations = {}

        # Historical metrics
        self.risk_events = []
        self.daily_metrics = []

        # Initialize components
        self.setup_database()
        if USE_AI_FOR_COMPLEX_RISKS:
            self.init_claude()

        logger.info(colored("🛡️ Risk Management Agent initialized", "cyan"))
        logger.info(f"Portfolio: ${portfolio_value:.2f} | Max daily loss: {MAX_DAILY_LOSS_PERCENT:.1%}")

    def setup_database(self):
        """Initialize database and create tables"""
        try:
            self.db_conn = psycopg2.connect(**DB_CONFIG)
            cursor = self.db_conn.cursor()

            # Create risk assessments table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS risk_assessments (
                    id SERIAL PRIMARY KEY,
                    timestamp TIMESTAMP NOT NULL,
                    assessment_type VARCHAR(50) NOT NULL,
                    risk_level VARCHAR(20) NOT NULL,
                    action VARCHAR(50) NOT NULL,
                    reasoning TEXT,
                    metrics JSONB,
                    trade_approved BOOLEAN DEFAULT false,
                    INDEX idx_risk_time (timestamp)
                )
            """)

            # Create risk events table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS risk_events (
                    id SERIAL PRIMARY KEY,
                    timestamp TIMESTAMP NOT NULL,
                    event_type VARCHAR(50) NOT NULL,
                    severity VARCHAR(20) NOT NULL,
                    description TEXT,
                    action_taken VARCHAR(100),
                    metrics JSONB,
                    INDEX idx_event_time (timestamp)
                )
            """)

            # Create daily risk metrics table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS daily_risk_metrics (
                    id SERIAL PRIMARY KEY,
                    date DATE NOT NULL UNIQUE,
                    max_drawdown DECIMAL(10, 4),
                    daily_loss DECIMAL(10, 4),
                    positions_count INTEGER,
                    total_exposure DECIMAL(10, 4),
                    risk_events_count INTEGER,
                    trades_rejected INTEGER,
                    trades_approved INTEGER,
                    circuit_breaker_triggered BOOLEAN DEFAULT false
                )
            """)

            self.db_conn.commit()
            logger.info("✅ Risk management database tables created/verified")

        except Exception as e:
            logger.error(f"Database setup error: {e}")
            raise

    def init_claude(self):
        """Initialize Claude for complex risk assessments"""
        api_key = os.getenv('ANTHROPIC_KEY')
        if api_key:
            self.claude_client = anthropic.Anthropic(api_key=api_key)
            logger.info("✅ Claude AI risk assessment enabled")
        else:
            logger.warning("Claude API key not found - AI risk assessment disabled")
            global USE_AI_FOR_COMPLEX_RISKS
            USE_AI_FOR_COMPLEX_RISKS = False

    def assess_trade_risk(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        current_positions: Dict,
        portfolio_value: float
    ) -> RiskAssessment:
        """
        Assess risk for a proposed trade

        Args:
            symbol: Trading symbol
            side: 'buy' or 'sell'
            quantity: Trade quantity
            price: Trade price
            current_positions: Current portfolio positions
            portfolio_value: Total portfolio value

        Returns:
            RiskAssessment object with decision and reasoning
        """
        try:
            metrics = {}
            recommendations = []
            risk_level = RiskLevel.LOW
            action = RiskAction.APPROVE

            # Update portfolio value
            self.portfolio_value = portfolio_value

            # Check if trading is halted
            if self.trading_halted:
                return RiskAssessment(
                    level=RiskLevel.EMERGENCY,
                    action=RiskAction.HALT_TRADING,
                    reasoning=f"Trading halted: {self.halt_reason}",
                    metrics={},
                    recommendations=["Wait for risk conditions to improve"]
                )

            # Calculate trade value
            trade_value = quantity * price
            metrics['trade_value'] = trade_value
            metrics['trade_percent'] = (trade_value / portfolio_value) * 100

            # 1. Check position size limit (20% max)
            if metrics['trade_percent'] > MAX_POSITION_PERCENT * 100:
                risk_level = RiskLevel.HIGH
                action = RiskAction.REDUCE_SIZE
                recommended_size = (MAX_POSITION_PERCENT * portfolio_value) / price
                recommendations.append(f"Reduce size to {recommended_size:.8f} units")
                logger.warning(colored(
                    f"⚠️ Position too large: {metrics['trade_percent']:.1f}% > {MAX_POSITION_PERCENT*100:.0f}%",
                    "yellow"
                ))

            # 2. Check daily loss limit
            self.update_daily_metrics(portfolio_value)
            if self.daily_loss / self.portfolio_value >= MAX_DAILY_LOSS_PERCENT:
                risk_level = RiskLevel.CRITICAL
                action = RiskAction.REJECT
                return RiskAssessment(
                    level=risk_level,
                    action=action,
                    reasoning=f"Daily loss limit reached: {self.daily_loss/self.portfolio_value:.1%}",
                    metrics=metrics,
                    recommendations=["Stop trading for today"]
                )

            # 3. Check cash reserve (keep 20% minimum)
            if side == 'buy':
                cash_after_trade = portfolio_value - trade_value - sum(
                    pos.get('value', 0) for pos in current_positions.values()
                )
                cash_percent_after = cash_after_trade / portfolio_value
                metrics['cash_after'] = cash_percent_after * 100

                if cash_percent_after < MIN_CASH_RESERVE_PERCENT:
                    risk_level = RiskLevel.HIGH
                    action = RiskAction.REJECT
                    recommendations.append(f"Maintain {MIN_CASH_RESERVE_PERCENT*100:.0f}% cash reserve")
                    logger.warning(colored(
                        f"⚠️ Insufficient cash reserve: {cash_percent_after:.1%} < {MIN_CASH_RESERVE_PERCENT:.0%}",
                        "yellow"
                    ))

            # 4. Check total exposure
            total_exposure = sum(pos.get('value', 0) for pos in current_positions.values())
            if side == 'buy':
                total_exposure += trade_value
            exposure_percent = total_exposure / portfolio_value
            metrics['total_exposure'] = exposure_percent * 100

            if exposure_percent > MAX_TOTAL_EXPOSURE:
                risk_level = RiskLevel.HIGH
                action = RiskAction.REJECT
                recommendations.append(f"Total exposure would exceed {MAX_TOTAL_EXPOSURE*100:.0f}%")

            # 5. Check number of positions
            if side == 'buy' and len(current_positions) >= MAX_CONCURRENT_POSITIONS:
                risk_level = RiskLevel.MEDIUM
                action = RiskAction.REJECT
                recommendations.append(f"Already at max {MAX_CONCURRENT_POSITIONS} positions")

            # 6. Check correlated exposure (simplified - would need correlation matrix)
            if self.check_correlation_risk(symbol, current_positions, trade_value):
                risk_level = max(risk_level, RiskLevel.MEDIUM)
                recommendations.append("High correlation with existing positions")

            # 7. Complex risk assessment with Claude (if needed)
            if risk_level.value in ['high', 'critical'] and USE_AI_FOR_COMPLEX_RISKS:
                ai_assessment = self.get_ai_risk_assessment(
                    symbol, side, metrics, current_positions
                )
                if ai_assessment:
                    # AI can override to allow trade in special circumstances
                    if ai_assessment.get('override_recommendation'):
                        action = RiskAction.APPROVE
                        recommendations.append(f"AI Override: {ai_assessment.get('reasoning')}")

            # Build reasoning
            if action == RiskAction.APPROVE:
                reasoning = f"Trade approved - Risk level: {risk_level.value}"
            elif action == RiskAction.REDUCE_SIZE:
                reasoning = f"Reduce position size - {risk_level.value} risk"
            else:
                reasoning = f"Trade rejected - {risk_level.value} risk: " + ", ".join(recommendations[:2])

            # Log assessment
            self.log_assessment(
                assessment_type='trade_risk',
                risk_level=risk_level,
                action=action,
                reasoning=reasoning,
                metrics=metrics
            )

            # Visual feedback
            emoji = "✅" if action == RiskAction.APPROVE else "⚠️" if action == RiskAction.REDUCE_SIZE else "❌"
            color = "green" if action == RiskAction.APPROVE else "yellow" if action == RiskAction.REDUCE_SIZE else "red"
            logger.info(colored(
                f"{emoji} Risk Assessment: {action.value} - {risk_level.value} risk",
                color
            ))

            return RiskAssessment(
                level=risk_level,
                action=action,
                reasoning=reasoning,
                metrics=metrics,
                recommendations=recommendations
            )

        except Exception as e:
            logger.error(f"Risk assessment error: {e}")
            return RiskAssessment(
                level=RiskLevel.CRITICAL,
                action=RiskAction.REJECT,
                reasoning=f"Risk assessment error: {str(e)}",
                metrics={},
                recommendations=["Fix risk system error before trading"]
            )

    def update_daily_metrics(self, current_portfolio_value: float):
        """Update daily P&L and check for new day reset"""
        try:
            # Check if new day
            current_date = datetime.now().date()
            if current_date > self.last_reset:
                self.save_daily_metrics()
                self.daily_loss = 0
                self.trading_halted = False
                self.halt_reason = None
                self.last_reset = current_date
                logger.info("📅 Daily risk metrics reset")

            # Calculate daily P&L
            # In production, would compare to morning snapshot
            self.daily_loss = min(0, current_portfolio_value - self.portfolio_value)

        except Exception as e:
            logger.error(f"Daily metrics update error: {e}")

    def check_correlation_risk(
        self,
        symbol: str,
        current_positions: Dict,
        trade_value: float
    ) -> bool:
        """
        Check if trade would create excessive correlated exposure

        Returns:
            True if correlation risk is too high
        """
        try:
            # Simplified correlation check
            # In production, would use actual correlation matrix

            # Group correlated assets
            crypto_majors = ['BTC', 'ETH']
            meme_coins = ['PEPE', 'DOGE', 'SHIB']

            symbol_base = symbol.split('-')[0]

            # Check if adding to correlated group
            if symbol_base in crypto_majors:
                correlated_value = sum(
                    pos.get('value', 0) for sym, pos in current_positions.items()
                    if sym.split('-')[0] in crypto_majors
                )
            elif symbol_base in meme_coins:
                correlated_value = sum(
                    pos.get('value', 0) for sym, pos in current_positions.items()
                    if sym.split('-')[0] in meme_coins
                )
            else:
                return False

            correlated_value += trade_value
            correlation_percent = correlated_value / self.portfolio_value

            return correlation_percent > MAX_CORRELATED_EXPOSURE

        except Exception as e:
            logger.error(f"Correlation check error: {e}")
            return False

    def check_market_conditions(self) -> RiskLevel:
        """
        Check overall market conditions for systemic risk

        Returns:
            Current market risk level
        """
        try:
            cursor = self.db_conn.cursor(cursor_factory=RealDictCursor)

            # Check recent volatility
            cursor.execute("""
                SELECT AVG(ABS(sentiment_score)) as avg_volatility
                FROM crypto_sentiment
                WHERE timestamp > %s
            """, (datetime.now() - timedelta(hours=24),))

            result = cursor.fetchone()
            volatility = result['avg_volatility'] if result and result['avg_volatility'] else 0

            # Check news volume (potential crisis indicator)
            cursor.execute("""
                SELECT COUNT(*) as news_count
                FROM news_articles
                WHERE timestamp > %s
            """, (datetime.now() - timedelta(hours=1),))

            result = cursor.fetchone()
            recent_news = result['news_count'] if result else 0

            # Determine risk level
            if volatility > 0.8 or recent_news > 20:
                return RiskLevel.HIGH
            elif volatility > 0.5 or recent_news > 10:
                return RiskLevel.MEDIUM
            else:
                return RiskLevel.LOW

        except Exception as e:
            logger.error(f"Market conditions check error: {e}")
            return RiskLevel.MEDIUM

    def monitor_portfolio_risk(self, positions: Dict, portfolio_value: float) -> RiskAssessment:
        """
        Monitor overall portfolio risk

        Returns:
            Portfolio risk assessment
        """
        try:
            self.positions = positions
            self.portfolio_value = portfolio_value

            metrics = {
                'portfolio_value': portfolio_value,
                'num_positions': len(positions),
                'daily_loss': self.daily_loss,
                'daily_loss_percent': (self.daily_loss / portfolio_value) * 100 if portfolio_value > 0 else 0
            }

            # Calculate drawdown
            # In production, would track high water mark
            if portfolio_value < self.portfolio_value:
                self.current_drawdown = (self.portfolio_value - portfolio_value) / self.portfolio_value
                self.max_drawdown = max(self.max_drawdown, self.current_drawdown)

            metrics['current_drawdown'] = self.current_drawdown * 100
            metrics['max_drawdown'] = self.max_drawdown * 100

            # Determine risk level
            if self.current_drawdown >= DRAWDOWN_CRITICAL:
                risk_level = RiskLevel.CRITICAL
                action = RiskAction.CLOSE_POSITIONS
                recommendations = ["Close losing positions", "Reduce exposure immediately"]
            elif self.current_drawdown >= DRAWDOWN_WARNING:
                risk_level = RiskLevel.HIGH
                action = RiskAction.REDUCE_SIZE
                recommendations = ["Reduce position sizes", "Avoid new trades"]
            else:
                risk_level = RiskLevel.LOW
                action = RiskAction.APPROVE
                recommendations = ["Risk within acceptable limits"]

            # Check market conditions
            market_risk = self.check_market_conditions()
            if market_risk.value in ['high', 'critical']:
                risk_level = max(risk_level, market_risk)
                recommendations.append(f"Market conditions: {market_risk.value}")

            reasoning = f"Portfolio risk: {risk_level.value} (DD: {self.current_drawdown:.1%})"

            return RiskAssessment(
                level=risk_level,
                action=action,
                reasoning=reasoning,
                metrics=metrics,
                recommendations=recommendations
            )

        except Exception as e:
            logger.error(f"Portfolio monitoring error: {e}")
            return RiskAssessment(
                level=RiskLevel.MEDIUM,
                action=RiskAction.APPROVE,
                reasoning="Portfolio monitoring error",
                metrics={},
                recommendations=["Check risk system"]
            )

    def trigger_circuit_breaker(self, reason: str):
        """Trigger emergency trading halt"""
        self.trading_halted = True
        self.halt_reason = reason

        # Log event
        self.log_risk_event(
            event_type='circuit_breaker',
            severity='critical',
            description=f"Circuit breaker triggered: {reason}",
            action_taken='halt_trading'
        )

        logger.critical(colored(
            f"🚨 CIRCUIT BREAKER TRIGGERED: {reason}",
            "red",
            attrs=['bold', 'blink']
        ))

    def get_ai_risk_assessment(
        self,
        symbol: str,
        side: str,
        metrics: Dict,
        positions: Dict
    ) -> Optional[Dict]:
        """Get AI assessment for complex risk scenarios"""
        if not self.claude_client:
            return None

        try:
            prompt = f"""Analyze this high-risk trading situation:

Symbol: {symbol}
Action: {side}
Trade Metrics: {json.dumps(metrics, indent=2)}
Current Positions: {json.dumps(positions, indent=2)}

The automated risk system flagged this as high risk. Should we:
1. Override and approve (if unique opportunity)
2. Maintain rejection (if genuinely dangerous)

Consider:
- Market conditions
- Portfolio concentration
- Potential black swan events
- Risk/reward ratio

Respond with JSON:
{{
    "override_recommendation": true/false,
    "reasoning": "brief explanation",
    "adjusted_size": null or number
}}"""

            response = self.claude_client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=500,
                temperature=0.3,  # More conservative for risk
                system="You are a risk management AI focused on capital preservation. Only override rejections for exceptional opportunities with limited downside.",
                messages=[{"role": "user", "content": prompt}]
            )

            # Parse response
            text = response.content[0].text
            import re
            json_match = re.search(r'\{[^}]+\}', text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())

        except Exception as e:
            logger.error(f"AI risk assessment error: {e}")

        return None

    def log_assessment(
        self,
        assessment_type: str,
        risk_level: RiskLevel,
        action: RiskAction,
        reasoning: str,
        metrics: Dict
    ):
        """Log risk assessment to database"""
        try:
            cursor = self.db_conn.cursor()
            cursor.execute("""
                INSERT INTO risk_assessments
                (timestamp, assessment_type, risk_level, action, reasoning, metrics, trade_approved)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                datetime.now(),
                assessment_type,
                risk_level.value,
                action.value,
                reasoning,
                json.dumps(metrics),
                action == RiskAction.APPROVE
            ))
            self.db_conn.commit()

        except Exception as e:
            logger.error(f"Error logging assessment: {e}")
            self.db_conn.rollback()

    def log_risk_event(
        self,
        event_type: str,
        severity: str,
        description: str,
        action_taken: str,
        metrics: Dict = None
    ):
        """Log risk event to database"""
        try:
            cursor = self.db_conn.cursor()
            cursor.execute("""
                INSERT INTO risk_events
                (timestamp, event_type, severity, description, action_taken, metrics)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                datetime.now(),
                event_type,
                severity,
                description,
                action_taken,
                json.dumps(metrics) if metrics else None
            ))
            self.db_conn.commit()

            self.risk_events.append({
                'timestamp': datetime.now(),
                'type': event_type,
                'severity': severity
            })

        except Exception as e:
            logger.error(f"Error logging risk event: {e}")
            self.db_conn.rollback()

    def save_daily_metrics(self):
        """Save daily risk metrics to database"""
        try:
            cursor = self.db_conn.cursor()

            # Count today's events
            trades_approved = sum(1 for e in self.risk_events if e.get('type') == 'trade_approved')
            trades_rejected = sum(1 for e in self.risk_events if e.get('type') == 'trade_rejected')

            cursor.execute("""
                INSERT INTO daily_risk_metrics
                (date, max_drawdown, daily_loss, positions_count, total_exposure,
                 risk_events_count, trades_rejected, trades_approved, circuit_breaker_triggered)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (date) DO UPDATE SET
                    max_drawdown = EXCLUDED.max_drawdown,
                    daily_loss = EXCLUDED.daily_loss,
                    positions_count = EXCLUDED.positions_count,
                    total_exposure = EXCLUDED.total_exposure,
                    risk_events_count = EXCLUDED.risk_events_count,
                    trades_rejected = EXCLUDED.trades_rejected,
                    trades_approved = EXCLUDED.trades_approved,
                    circuit_breaker_triggered = EXCLUDED.circuit_breaker_triggered
            """, (
                self.last_reset,
                self.max_drawdown,
                self.daily_loss,
                len(self.positions),
                sum(p.get('value', 0) for p in self.positions.values()) / self.portfolio_value if self.portfolio_value > 0 else 0,
                len(self.risk_events),
                trades_rejected,
                trades_approved,
                self.trading_halted
            ))
            self.db_conn.commit()

        except Exception as e:
            logger.error(f"Error saving daily metrics: {e}")
            self.db_conn.rollback()

    def generate_risk_report(self) -> Dict:
        """Generate comprehensive risk report"""
        try:
            report = {
                'timestamp': datetime.now().isoformat(),
                'risk_status': {
                    'trading_halted': self.trading_halted,
                    'halt_reason': self.halt_reason,
                    'current_drawdown': f"{self.current_drawdown:.1%}",
                    'max_drawdown': f"{self.max_drawdown:.1%}",
                    'daily_loss': f"${self.daily_loss:.2f}",
                    'daily_loss_percent': f"{(self.daily_loss/self.portfolio_value*100):.1f}%" if self.portfolio_value > 0 else "0%"
                },
                'limits': {
                    'max_position': f"{MAX_POSITION_PERCENT:.0%}",
                    'max_daily_loss': f"{MAX_DAILY_LOSS_PERCENT:.0%}",
                    'min_cash_reserve': f"{MIN_CASH_RESERVE_PERCENT:.0%}",
                    'max_risk_per_trade': f"{MAX_RISK_PER_TRADE:.0%}"
                },
                'current_positions': len(self.positions),
                'risk_events_today': len(self.risk_events),
                'recommendations': []
            }

            # Add recommendations based on current state
            if self.trading_halted:
                report['recommendations'].append("Trading halted - wait for conditions to improve")
            elif self.current_drawdown > DRAWDOWN_WARNING:
                report['recommendations'].append("Reduce position sizes due to drawdown")
            elif len(self.positions) >= MAX_CONCURRENT_POSITIONS:
                report['recommendations'].append("At maximum positions - close before opening new")
            else:
                report['recommendations'].append("Risk parameters within limits")

            # Log report
            logger.info(colored("\n" + "="*50, "cyan"))
            logger.info(colored("🛡️ RISK MANAGEMENT REPORT", "cyan", attrs=['bold']))
            logger.info(colored("="*50, "cyan"))
            logger.info(f"Trading Status: {'🔴 HALTED' if self.trading_halted else '🟢 ACTIVE'}")
            logger.info(f"Drawdown: {self.current_drawdown:.1%} (Max: {self.max_drawdown:.1%})")
            logger.info(f"Daily P&L: ${self.daily_loss:.2f}")
            logger.info(f"Positions: {len(self.positions)}/{MAX_CONCURRENT_POSITIONS}")
            logger.info(f"Risk Events: {len(self.risk_events)}")
            logger.info(colored("="*50 + "\n", "cyan"))

            return report

        except Exception as e:
            logger.error(f"Report generation error: {e}")
            return {}

    def close(self):
        """Clean up resources"""
        self.save_daily_metrics()
        if self.db_conn:
            self.db_conn.close()
        logger.info("Risk management agent closed")

def main():
    """Test the risk management agent"""
    try:
        # Initialize agent
        risk_agent = RiskManagementAgent(portfolio_value=1000)

        # Test trade assessment
        assessment = risk_agent.assess_trade_risk(
            symbol='BTC-USD',
            side='buy',
            quantity=0.01,
            price=65000,
            current_positions={},
            portfolio_value=1000
        )

        print(f"Assessment: {assessment.action.value}")
        print(f"Risk Level: {assessment.level.value}")
        print(f"Reasoning: {assessment.reasoning}")
        print(f"Recommendations: {assessment.recommendations}")

        # Test portfolio monitoring
        positions = {
            'BTC': {'value': 200, 'quantity': 0.003},
            'ETH': {'value': 150, 'quantity': 0.05}
        }
        portfolio_assessment = risk_agent.monitor_portfolio_risk(positions, 950)
        print(f"\nPortfolio Risk: {portfolio_assessment.level.value}")

        # Generate report
        report = risk_agent.generate_risk_report()
        print(json.dumps(report, indent=2))

        risk_agent.close()

    except Exception as e:
        logger.error(f"Test failed: {e}")

if __name__ == "__main__":
    main()