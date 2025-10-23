"""
Claude Sonnet 4 Trading Decision Agent
Core AI decision-making system for PJX Crypto Trading System

Based on the Balanced Configuration with proven +28% returns in Alpha Arena.
Uses hybrid reasoning (fast or deep thinking) based on market conditions.

Features:
- Multi-source data synthesis (news, sentiment, congressional, technical)
- Confidence-based position sizing
- Integration with paper trading and risk management
- Extended Exchange points optimization
"""

import os
import sys
import json
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum
import asyncio

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor
from termcolor import colored
import anthropic

# Import our modules
from paper_trading.tracker import PaperTradingTracker
from exchanges.extended_exchange import ExtendedExchange, OrderSide, OrderType
from crypto_scrapers.twitter_sentiment import TwitterSentimentScraper

# Load environment variables
load_dotenv()

# ========================
# CONFIGURATION
# ========================

# Model configuration (from crypto-trading-system-notes.md)
CLAUDE_MODEL = "claude-3-5-sonnet-20241022"  # Proven +28% returns
TEMPERATURE = 0.7  # Balance between creativity and consistency
MAX_TOKENS = 4096

# Trading parameters
MIN_CONFIDENCE = 0.65  # Minimum confidence to trade (65%)
MAX_POSITIONS = 5  # Maximum concurrent positions
POSITION_SIZE_USD = 25  # Base position size
MAX_ORDER_SIZE_USD = 100  # Maximum single order

# Timing
ANALYSIS_INTERVAL = 900  # 15 minutes between analyses
QUICK_DECISION_TIMEOUT = 10  # 10 seconds for fast decisions
DEEP_THINKING_TIMEOUT = 60  # 60 seconds for complex analysis

# Tokens to monitor (prioritizing meme coins and Extended)
MONITORED_TOKENS = [
    'SOL-USD',
    'PEPE-USD',
    'DOGE-USD',
    'SHIB-USD',
    'EXT-USD',  # Extended token
    'BTC-USD',  # Market leader for context
    'ETH-USD'   # Altcoin leader for context
]

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
        logging.FileHandler('logs/trading_agent.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class TradingSignal(Enum):
    """Trading signal types"""
    STRONG_BUY = "strong_buy"
    BUY = "buy"
    HOLD = "hold"
    SELL = "sell"
    STRONG_SELL = "strong_sell"

class MarketCondition(Enum):
    """Market condition assessment"""
    BULL_RUN = "bull_run"
    BULLISH = "bullish"
    NEUTRAL = "neutral"
    BEARISH = "bearish"
    CRASH = "crash"

class ClaudeTradingAgent:
    """
    Claude Sonnet 4 powered trading agent with hybrid reasoning
    """

    def __init__(self, paper_trading: bool = True):
        """
        Initialize the trading agent

        Args:
            paper_trading: If True, use paper trading mode
        """
        self.paper_trading = paper_trading
        self.db_conn = None
        self.client = None

        # Components
        self.paper_tracker = None
        self.exchange = None
        self.sentiment_scraper = None

        # State
        self.current_positions = {}
        self.recent_signals = []
        self.market_condition = MarketCondition.NEUTRAL
        self.last_analysis_time = {}

        # Initialize components
        self.setup_database()
        self.init_claude()
        self.init_components()

        mode = "PAPER" if paper_trading else "LIVE"
        logger.info(colored(f"🤖 Claude Trading Agent initialized in {mode} mode", "cyan"))

    def setup_database(self):
        """Initialize database connection and create tables"""
        try:
            self.db_conn = psycopg2.connect(**DB_CONFIG)
            cursor = self.db_conn.cursor()

            # Create signals table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trading_signals (
                    id SERIAL PRIMARY KEY,
                    timestamp TIMESTAMP NOT NULL,
                    symbol VARCHAR(20) NOT NULL,
                    signal VARCHAR(20) NOT NULL,
                    confidence DECIMAL(5, 2) NOT NULL,
                    reasoning TEXT,
                    market_data JSONB,
                    executed BOOLEAN DEFAULT false,
                    trade_id VARCHAR(50),
                    paper_trade BOOLEAN DEFAULT true,
                    INDEX idx_signal_time (timestamp),
                    INDEX idx_signal_symbol (symbol)
                )
            """)

            # Create agent decisions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS agent_decisions (
                    id SERIAL PRIMARY KEY,
                    timestamp TIMESTAMP NOT NULL,
                    decision_type VARCHAR(50) NOT NULL,
                    thinking_mode VARCHAR(20),
                    response_time_ms INTEGER,
                    input_data JSONB,
                    output_data JSONB,
                    tokens_used INTEGER,
                    cost DECIMAL(10, 6)
                )
            """)

            self.db_conn.commit()
            logger.info("✅ Trading agent database tables created/verified")

        except Exception as e:
            logger.error(f"Database setup error: {e}")
            raise

    def init_claude(self):
        """Initialize Claude API client"""
        api_key = os.getenv('ANTHROPIC_KEY')
        if not api_key:
            raise ValueError("ANTHROPIC_KEY not found in .env file")

        self.client = anthropic.Anthropic(api_key=api_key)
        logger.info("✅ Claude API initialized")

    def init_components(self):
        """Initialize trading components"""
        # Paper trading tracker
        if self.paper_trading:
            self.paper_tracker = PaperTradingTracker()

        # Exchange connection
        self.exchange = ExtendedExchange(paper_trading=self.paper_trading)

        # Sentiment scraper (optional)
        try:
            self.sentiment_scraper = TwitterSentimentScraper()
        except Exception as e:
            logger.warning(f"Sentiment scraper not available: {e}")

    def fetch_market_data(self, symbol: str) -> Dict:
        """
        Fetch all relevant data for a trading decision

        Returns:
            Dictionary with market data, sentiment, news, etc.
        """
        try:
            cursor = self.db_conn.cursor(cursor_factory=RealDictCursor)
            data = {
                'symbol': symbol,
                'timestamp': datetime.now().isoformat(),
                'price': self.exchange.get_market_price(symbol)
            }

            # Get recent sentiment
            if self.sentiment_scraper:
                base_token = symbol.split('-')[0].lower()
                sentiment_df = self.sentiment_scraper.get_recent_sentiment(base_token, hours=24)
                if not sentiment_df.empty:
                    data['sentiment'] = {
                        'current': float(sentiment_df.iloc[0]['sentiment_score']) if len(sentiment_df) > 0 else 0,
                        'avg_24h': float(sentiment_df['sentiment_score'].mean()),
                        'trend': 'improving' if len(sentiment_df) > 1 and sentiment_df.iloc[0]['sentiment_score'] > sentiment_df.iloc[1]['sentiment_score'] else 'declining'
                    }

            # Get recent news (from ChromaDB via SQL query)
            cursor.execute("""
                SELECT headline, url, timestamp
                FROM news_articles
                WHERE timestamp > %s
                ORDER BY timestamp DESC
                LIMIT 10
            """, (datetime.now() - timedelta(hours=6),))
            news = cursor.fetchall()
            data['recent_news'] = [dict(n) for n in news] if news else []

            # Get congressional trades if relevant
            cursor.execute("""
                SELECT filer_name, ticker, transaction_type, filing_date
                FROM congressional_trades
                WHERE filing_date > %s
                AND ticker IN ('COIN', 'MSTR', 'SQ', 'PYPL')
                ORDER BY filing_date DESC
                LIMIT 5
            """, (datetime.now() - timedelta(days=7),))
            trades = cursor.fetchall()
            data['congressional_activity'] = [dict(t) for t in trades] if trades else []

            # Get economic indicators
            cursor.execute("""
                SELECT indicator_code, value, date
                FROM economic_indicators
                WHERE date = (SELECT MAX(date) FROM economic_indicators)
            """)
            indicators = cursor.fetchall()
            data['economic_indicators'] = {i['indicator_code']: float(i['value']) for i in indicators} if indicators else {}

            # Get current positions
            positions = self.exchange.get_positions()
            if symbol.split('-')[0] in positions:
                data['current_position'] = positions[symbol.split('-')[0]]

            # Get Extended points status
            data['extended_points'] = self.exchange.get_total_points()

            return data

        except Exception as e:
            logger.error(f"Error fetching market data: {e}")
            return {'symbol': symbol, 'error': str(e)}

    def analyze_with_claude(
        self,
        market_data: Dict,
        use_deep_thinking: bool = False
    ) -> Tuple[TradingSignal, float, str]:
        """
        Analyze market data with Claude Sonnet 4

        Args:
            market_data: All relevant market data
            use_deep_thinking: Whether to use deep reasoning mode

        Returns:
            (signal, confidence, reasoning)
        """
        try:
            start_time = time.time()

            # Build the system prompt
            system_prompt = """You are an elite cryptocurrency trading AI with proven success (+28% returns in live trading).
            You analyze multiple data sources to make trading decisions with a focus on crypto/meme coins where inefficiencies exist.

            Your strengths:
            - Sentiment analysis from Twitter/social media (major edge in crypto)
            - News impact assessment
            - Congressional trade correlation
            - Technical price action
            - Risk management (1-2% risk per trade, 20% max position)

            Trading rules:
            - Only suggest trades with >65% confidence
            - Prioritize meme coins and Extended tokens for points
            - Consider Extended Exchange points optimization
            - Factor in current positions to avoid overexposure
            - Use 5% daily loss limit as circuit breaker

            Output format (JSON):
            {
                "signal": "strong_buy|buy|hold|sell|strong_sell",
                "confidence": 0.0-1.0,
                "reasoning": "2-3 sentences explaining the decision",
                "position_size_multiplier": 0.5-2.0,
                "stop_loss_percent": 2-10,
                "take_profit_percent": 5-50
            }"""

            # Build the user prompt
            user_prompt = f"""Analyze this crypto market data and provide a trading decision:

            Symbol: {market_data.get('symbol')}
            Current Price: ${market_data.get('price', 0):.4f}

            Sentiment Analysis:
            {json.dumps(market_data.get('sentiment', {}), indent=2)}

            Recent News (last 6 hours):
            {json.dumps(market_data.get('recent_news', [])[:5], indent=2)}

            Congressional Activity:
            {json.dumps(market_data.get('congressional_activity', []), indent=2)}

            Economic Indicators:
            {json.dumps(market_data.get('economic_indicators', {}), indent=2)}

            Current Position:
            {json.dumps(market_data.get('current_position', {}), indent=2)}

            Extended Points: {market_data.get('extended_points', 0):.2f}

            {"Use deep analysis - this appears to be a complex market situation." if use_deep_thinking else "Provide a quick but accurate assessment."}
            """

            # Call Claude with appropriate timeout
            timeout = DEEP_THINKING_TIMEOUT if use_deep_thinking else QUICK_DECISION_TIMEOUT

            response = self.client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=MAX_TOKENS,
                temperature=TEMPERATURE,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": user_prompt}
                ]
            )

            # Parse response
            response_text = response.content[0].text
            response_time_ms = int((time.time() - start_time) * 1000)

            # Try to parse JSON from response
            try:
                # Find JSON in response
                import re
                json_match = re.search(r'\{[^}]+\}', response_text, re.DOTALL)
                if json_match:
                    decision = json.loads(json_match.group())
                else:
                    # Fallback parsing
                    decision = {
                        'signal': 'hold',
                        'confidence': 0.5,
                        'reasoning': response_text[:200]
                    }
            except:
                decision = {
                    'signal': 'hold',
                    'confidence': 0.5,
                    'reasoning': response_text[:200]
                }

            # Map signal to enum
            signal_map = {
                'strong_buy': TradingSignal.STRONG_BUY,
                'buy': TradingSignal.BUY,
                'hold': TradingSignal.HOLD,
                'sell': TradingSignal.SELL,
                'strong_sell': TradingSignal.STRONG_SELL
            }
            signal = signal_map.get(decision.get('signal', 'hold'), TradingSignal.HOLD)
            confidence = float(decision.get('confidence', 0.5))
            reasoning = decision.get('reasoning', 'No specific reasoning provided')

            # Log the decision
            self.log_decision(
                decision_type='trading_signal',
                thinking_mode='deep' if use_deep_thinking else 'fast',
                response_time_ms=response_time_ms,
                input_data=market_data,
                output_data=decision,
                tokens_used=response.usage.total_tokens,
                cost=(response.usage.prompt_tokens * 0.003 + response.usage.completion_tokens * 0.015) / 1000
            )

            # Log signal
            thinking = "🧠 Deep thinking" if use_deep_thinking else "⚡ Fast decision"
            logger.info(colored(
                f"{thinking}: {signal.value} {market_data['symbol']} (Confidence: {confidence:.1%})",
                "green" if 'buy' in signal.value else "red" if 'sell' in signal.value else "yellow"
            ))
            logger.info(f"Reasoning: {reasoning}")

            return signal, confidence, reasoning

        except Exception as e:
            logger.error(f"Claude analysis error: {e}")
            return TradingSignal.HOLD, 0.0, f"Analysis error: {str(e)}"

    def should_use_deep_thinking(self, market_data: Dict) -> bool:
        """
        Determine if deep thinking is needed based on market conditions

        Criteria for deep thinking:
        - High volatility or unusual price movement
        - Conflicting signals (e.g., positive sentiment but negative news)
        - Large existing position
        - Near daily loss limit
        - Congressional trades detected
        """
        try:
            # Check for conflicting signals
            sentiment = market_data.get('sentiment', {})
            if sentiment.get('current', 0) > 0.3 and len(market_data.get('recent_news', [])) > 3:
                # Positive sentiment with lots of news - might be complex
                return True

            # Check for congressional activity
            if len(market_data.get('congressional_activity', [])) > 0:
                return True

            # Check for large position
            position = market_data.get('current_position', {})
            if position and position.get('quantity', 0) * market_data.get('price', 0) > 100:
                return True

            # Default to fast decision
            return False

        except Exception as e:
            logger.error(f"Error determining thinking mode: {e}")
            return False

    def execute_signal(
        self,
        symbol: str,
        signal: TradingSignal,
        confidence: float,
        market_data: Dict
    ) -> Dict:
        """
        Execute a trading signal

        Returns:
            Execution result dictionary
        """
        try:
            # Check confidence threshold
            if confidence < MIN_CONFIDENCE:
                return {
                    'executed': False,
                    'reason': f'Confidence too low: {confidence:.1%} < {MIN_CONFIDENCE:.0%}'
                }

            # Determine action based on signal
            if signal in [TradingSignal.STRONG_BUY, TradingSignal.BUY]:
                # Calculate position size based on confidence
                size_multiplier = 1.0 + (confidence - MIN_CONFIDENCE)
                position_size = POSITION_SIZE_USD * size_multiplier
                position_size = min(position_size, MAX_ORDER_SIZE_USD)

                # Execute buy
                if self.paper_trading:
                    result = self.paper_tracker.execute_trade(
                        symbol=symbol,
                        side='buy',
                        quantity=position_size / market_data['price'],
                        price=market_data['price'],
                        metadata={'signal': signal.value, 'confidence': confidence}
                    )
                else:
                    result = self.exchange.place_order(
                        symbol=symbol,
                        side=OrderSide.BUY,
                        order_type=OrderType.MARKET,
                        usd_amount=position_size
                    )

                return {
                    'executed': result.get('success', False),
                    'trade_id': result.get('trade_id'),
                    'position_size': position_size,
                    'result': result
                }

            elif signal in [TradingSignal.STRONG_SELL, TradingSignal.SELL]:
                # Check if we have a position to sell
                positions = self.exchange.get_positions() if not self.paper_trading else self.paper_tracker.positions
                base_asset = symbol.split('-')[0]

                if base_asset not in positions:
                    return {
                        'executed': False,
                        'reason': f'No position in {symbol} to sell'
                    }

                # Determine sell quantity based on signal strength
                position = positions[base_asset]
                sell_percent = 1.0 if signal == TradingSignal.STRONG_SELL else 0.5
                sell_quantity = position.quantity * sell_percent if hasattr(position, 'quantity') else position['quantity'] * sell_percent

                # Execute sell
                if self.paper_trading:
                    result = self.paper_tracker.execute_trade(
                        symbol=symbol,
                        side='sell',
                        quantity=sell_quantity,
                        price=market_data['price'],
                        metadata={'signal': signal.value, 'confidence': confidence}
                    )
                else:
                    result = self.exchange.place_order(
                        symbol=symbol,
                        side=OrderSide.SELL,
                        order_type=OrderType.MARKET,
                        quantity=sell_quantity
                    )

                return {
                    'executed': result.get('success', False),
                    'trade_id': result.get('trade_id'),
                    'quantity_sold': sell_quantity,
                    'result': result
                }

            else:  # HOLD
                return {
                    'executed': False,
                    'reason': 'HOLD signal - no action taken'
                }

        except Exception as e:
            logger.error(f"Signal execution error: {e}")
            return {
                'executed': False,
                'reason': f'Execution error: {str(e)}'
            }

    def analyze_token(self, symbol: str) -> Dict:
        """
        Complete analysis and potential execution for a token

        Returns:
            Analysis and execution results
        """
        try:
            logger.info(colored(f"\n{'='*50}", "cyan"))
            logger.info(colored(f"📈 Analyzing {symbol}", "cyan", attrs=['bold']))
            logger.info(colored(f"{'='*50}", "cyan"))

            # Fetch market data
            market_data = self.fetch_market_data(symbol)

            # Determine thinking mode
            use_deep = self.should_use_deep_thinking(market_data)

            # Get Claude's analysis
            signal, confidence, reasoning = self.analyze_with_claude(market_data, use_deep)

            # Save signal to database
            self.save_signal(symbol, signal, confidence, reasoning, market_data)

            # Execute if confident
            execution_result = self.execute_signal(symbol, signal, confidence, market_data)

            # Build result
            result = {
                'symbol': symbol,
                'signal': signal.value,
                'confidence': confidence,
                'reasoning': reasoning,
                'executed': execution_result.get('executed', False),
                'execution_details': execution_result,
                'thinking_mode': 'deep' if use_deep else 'fast',
                'timestamp': datetime.now().isoformat()
            }

            # Update last analysis time
            self.last_analysis_time[symbol] = datetime.now()

            return result

        except Exception as e:
            logger.error(f"Token analysis error for {symbol}: {e}")
            return {
                'symbol': symbol,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }

    def run_analysis_cycle(self):
        """Run a complete analysis cycle for all monitored tokens"""
        try:
            logger.info(colored("\n" + "="*60, "cyan"))
            logger.info(colored("🚀 STARTING TRADING ANALYSIS CYCLE", "cyan", attrs=['bold']))
            logger.info(colored("="*60, "cyan"))

            results = []

            for symbol in MONITORED_TOKENS:
                # Check if we should analyze this token
                last_analysis = self.last_analysis_time.get(symbol)
                if last_analysis and (datetime.now() - last_analysis).seconds < 300:  # 5 min cooldown
                    logger.info(f"⏭️ Skipping {symbol} (recently analyzed)")
                    continue

                # Analyze token
                result = self.analyze_token(symbol)
                results.append(result)

                # Small delay between analyses
                time.sleep(5)

            # Generate summary
            executed_trades = [r for r in results if r.get('executed')]
            total_confidence = np.mean([r.get('confidence', 0) for r in results if 'confidence' in r])

            logger.info(colored("\n" + "="*60, "cyan"))
            logger.info(colored("📊 CYCLE SUMMARY", "cyan", attrs=['bold']))
            logger.info(colored("="*60, "cyan"))
            logger.info(f"Tokens analyzed: {len(results)}")
            logger.info(f"Trades executed: {len(executed_trades)}")
            logger.info(f"Average confidence: {total_confidence:.1%}")

            # Show portfolio status if paper trading
            if self.paper_trading and self.paper_tracker:
                report = self.paper_tracker.generate_report()
                portfolio = report.get('portfolio', {})
                logger.info(f"Portfolio value: ${portfolio.get('total_value', 0):.2f}")
                logger.info(f"Total P&L: ${report.get('performance', {}).get('total_pnl', 0):.2f}")

            return results

        except Exception as e:
            logger.error(f"Analysis cycle error: {e}")
            return []

    def save_signal(
        self,
        symbol: str,
        signal: TradingSignal,
        confidence: float,
        reasoning: str,
        market_data: Dict
    ):
        """Save trading signal to database"""
        try:
            cursor = self.db_conn.cursor()
            cursor.execute("""
                INSERT INTO trading_signals
                (timestamp, symbol, signal, confidence, reasoning, market_data, paper_trade)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                datetime.now(),
                symbol,
                signal.value,
                confidence,
                reasoning,
                json.dumps(market_data),
                self.paper_trading
            ))
            self.db_conn.commit()

        except Exception as e:
            logger.error(f"Error saving signal: {e}")
            self.db_conn.rollback()

    def log_decision(
        self,
        decision_type: str,
        thinking_mode: str,
        response_time_ms: int,
        input_data: Dict,
        output_data: Dict,
        tokens_used: int,
        cost: float
    ):
        """Log agent decision to database"""
        try:
            cursor = self.db_conn.cursor()
            cursor.execute("""
                INSERT INTO agent_decisions
                (timestamp, decision_type, thinking_mode, response_time_ms,
                 input_data, output_data, tokens_used, cost)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                datetime.now(),
                decision_type,
                thinking_mode,
                response_time_ms,
                json.dumps(input_data),
                json.dumps(output_data),
                tokens_used,
                cost
            ))
            self.db_conn.commit()

        except Exception as e:
            logger.error(f"Error logging decision: {e}")
            self.db_conn.rollback()

    def start(self):
        """Start the trading agent"""
        logger.info(colored("\n🤖 Claude Trading Agent Starting...", "green", attrs=['bold']))
        logger.info(f"Mode: {'PAPER' if self.paper_trading else 'LIVE'}")
        logger.info(f"Monitoring: {', '.join(MONITORED_TOKENS)}")
        logger.info(f"Min confidence: {MIN_CONFIDENCE:.0%}")
        logger.info(f"Analysis interval: {ANALYSIS_INTERVAL} seconds\n")

        try:
            while True:
                # Run analysis cycle
                self.run_analysis_cycle()

                # Wait for next cycle
                logger.info(f"\n⏰ Next analysis in {ANALYSIS_INTERVAL} seconds...")
                time.sleep(ANALYSIS_INTERVAL)

        except KeyboardInterrupt:
            logger.info("\n👋 Trading agent stopped by user")
            self.close()
        except Exception as e:
            logger.error(f"Fatal error: {e}")
            self.close()
            raise

    def close(self):
        """Clean up resources"""
        if self.paper_tracker:
            self.paper_tracker.close()
        if self.exchange:
            self.exchange.close()
        if self.db_conn:
            self.db_conn.close()
        logger.info("Trading agent closed")

def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description='Claude Sonnet 4 Trading Agent')
    parser.add_argument('--live', action='store_true', help='Run in live trading mode')
    parser.add_argument('--once', action='store_true', help='Run one analysis cycle and exit')
    args = parser.parse_args()

    # Initialize agent
    agent = ClaudeTradingAgent(paper_trading=not args.live)

    if args.once:
        # Run single analysis
        results = agent.run_analysis_cycle()
        print(json.dumps(results, indent=2))
        agent.close()
    else:
        # Start continuous trading
        agent.start()

if __name__ == "__main__":
    main()