"""
AI Trader - Main orchestration with dynamic token discovery
Handles the main loop, Claude decisions, and ensemble verification
"""

import asyncio
import time
import signal
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import json
import anthropic
import google.generativeai as genai
from openai import OpenAI
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
import os
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor

try:
    # Try package imports first (for running as module)
    from crypto_ai_trader.data_intelligence import DataIntelligence
    from crypto_ai_trader.portfolio_manager import PortfolioManager
    from crypto_ai_trader.market_analyzer import MarketAnalyzer
    from crypto_ai_trader.ai_optimizer import AIOptimizer
    from crypto_ai_trader.trade_learner import TradeLearner
    from crypto_ai_trader.browser_ai import get_browser_ai, cleanup_all_browsers
    from crypto_ai_trader import config
except ImportError:
    # Fall back to local imports (for running directly)
    from data_intelligence import DataIntelligence
    from portfolio_manager import PortfolioManager
    from market_analyzer import MarketAnalyzer
    from ai_optimizer import AIOptimizer
    from trade_learner import TradeLearner
    from browser_ai import get_browser_ai, cleanup_all_browsers
    import config

load_dotenv()

class AITrader:
    """
    Main AI trading orchestrator with unlimited token support
    """

    def __init__(self):
        """Initialize the AI trader"""
        print("\n" + "="*60)
        print("PJX AI TRADER - UNLIMITED TOKEN EDITION")
        print("="*60)

        # Validate configuration
        if not config.validate_config():
            raise ValueError("Configuration validation failed")

        # Initialize components
        self.db_config = {
            'host': config.DB_HOST,
            'port': int(config.DB_PORT),
            'database': config.DB_NAME,
            'user': config.DB_USER,
            'password': config.DB_PASSWORD
        }

        # Initialize data intelligence
        self.data_intel = DataIntelligence(self.db_config)

        # Initialize portfolio manager
        self.portfolio = PortfolioManager(self.db_config, config.INITIAL_CAPITAL)

        # Initialize market analyzer for regime detection
        self.market_analyzer = MarketAnalyzer()
        self.current_regime = None
        self.regime_check_time = datetime.now() - timedelta(hours=1)  # Force initial check

        # Initialize AI Optimizer for dynamic prompt and weight optimization
        self.ai_optimizer = AIOptimizer(self.db_config)

        # Initialize Trade Learner for self-improving strategies
        self.trade_learner = TradeLearner(self.db_config)
        print("[Trade Learner] Self-learning system initialized")

        # Track active trades for learning
        self.active_trades = {}  # token -> (entry_time, entry_price, decision)

        # Initialize Claude client
        self.claude_client = anthropic.Anthropic(api_key=config.CLAUDE_API_KEY)

        # Initialize ensemble clients if enabled
        if config.ENABLE_TIER2_VERIFICATION:
            self.init_ensemble_clients()
        else:
            self.ensemble_clients = None

        # Trading state
        self.trading_active = True
        self.last_decision_time = {}
        self.consecutive_losses = 0
        self.daily_trade_count = 0
        self.daily_pnl = 0

        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self.handle_shutdown)
        signal.signal(signal.SIGTERM, self.handle_shutdown)

        print("[AI Trader] Initialization complete")
        print(f"[Settings] Paper Trading: {config.PAPER_TRADING}")
        print(f"[Settings] Initial Capital: ${config.INITIAL_CAPITAL:,.2f}")
        print(f"[Settings] Decision Interval: {config.DECISION_INTERVAL/60:.1f} minutes")
        print(f"[Settings] Tier 2 Verification: {config.ENABLE_TIER2_VERIFICATION}")
        print()

    def init_ensemble_clients(self):
        """Initialize ensemble model clients for Tier 2 verification"""
        self.ensemble_clients = {}

        # DeepSeek client
        if config.ENSEMBLE_MODELS['deepseek']['api_key']:
            self.ensemble_clients['deepseek'] = OpenAI(
                api_key=config.ENSEMBLE_MODELS['deepseek']['api_key'],
                base_url="https://api.deepseek.com/v1"
            )

        # Gemini client
        if config.ENSEMBLE_MODELS['gemini']['api_key']:
            genai.configure(api_key=config.ENSEMBLE_MODELS['gemini']['api_key'])
            self.ensemble_clients['gemini'] = genai.GenerativeModel(
                config.ENSEMBLE_MODELS['gemini']['name']
            )

        print(f"[Ensemble] Initialized {len(self.ensemble_clients)} additional models")

    def handle_shutdown(self, signum, frame):
        """Handle graceful shutdown"""
        print("\n[SHUTDOWN] Received shutdown signal...")
        self.trading_active = False

        # Cleanup browser instances if using browser AI
        try:
            if hasattr(config, 'USE_BROWSER_AI') and config.USE_BROWSER_AI:
                print("[SHUTDOWN] Closing browser sessions...")
                cleanup_all_browsers()
        except:
            pass

        # Print AI performance insights
        print("\n" + "="*60)
        print("AI PERFORMANCE INSIGHTS")
        print("="*60)

        # Get and print improvement suggestions
        suggestions = self.ai_optimizer.suggest_improvements()
        if suggestions:
            print("\n[AI OPTIMIZER] Recommendations:")
            for suggestion in suggestions:
                print(f"  - {suggestion}")

        # Print recent performance
        recent_perf = self.ai_optimizer.get_recent_performance(hours=24)
        if recent_perf:
            print(f"\n[PERFORMANCE] Last 24h:")
            print(f"  Success Rate: {recent_perf['success_rate']:.1f}%")
            print(f"  Total Trades: {recent_perf['total_trades']}")
            print(f"  Total P&L: ${recent_perf['total_pnl']:.2f}")
            print(f"  Market Bias: {recent_perf['bias']}")

        # Print Trade Learner insights
        print("\n" + "="*60)
        print("TRADE LEARNING INSIGHTS")
        print("="*60)

        # Get learning statistics
        learning_stats = self.trade_learner.get_learning_statistics()
        print(f"\n[LEARNING STATS]:")
        print(f"  Total Experiences: {learning_stats['total_experiences']}")
        print(f"  Unique Patterns: {learning_stats['unique_patterns']}")
        print(f"  Strategy Evolution: {learning_stats['evolution_count']} generations")
        print(f"  Avg Reward: {learning_stats['avg_reward']:.3f}")

        # Get top patterns
        top_patterns = self.trade_learner.get_top_patterns(limit=3)
        if top_patterns:
            print(f"\n[TOP PATTERNS]:")
            for pattern in top_patterns:
                print(f"  - {pattern['pattern_type']}: {pattern['success_rate']:.1f}% success ({pattern['count']} trades)")

        # Get evolved strategy parameters
        evolved_params = self.trade_learner.get_evolved_parameters()
        print(f"\n[EVOLVED PARAMETERS]:")
        print(f"  Confidence Threshold: {evolved_params['confidence_threshold']:.2f}")
        print(f"  Risk Tolerance: {evolved_params['risk_tolerance']:.2f}")
        print(f"  Position Sizing: {evolved_params['position_sizing_factor']:.2f}x")

        # Close positions if needed (optional for paper trading)
        self.portfolio.print_summary()

        # Save trade learner experience
        print("\n[SAVE] Saving trade learning experience...")
        self.trade_learner.save_experience_buffer()

        # Close connections
        self.data_intel.close()
        self.portfolio.close()
        self.ai_optimizer.close()
        self.trade_learner.close()
        if hasattr(self.market_analyzer, 'conn') and self.market_analyzer.conn:
            self.market_analyzer.conn.close()

        print("[SHUTDOWN] Cleanup complete. Goodbye!")
        sys.exit(0)

    def check_tactical_alerts(self) -> List[Dict]:
        """Check for critical tactical alerts from high-frequency monitor"""
        try:
            # Connect to database to check alerts
            conn = psycopg2.connect(
                host=self.db_config['host'],
                port=self.db_config['port'],
                user=self.db_config['user'],
                password=self.db_config['password'],
                database=self.db_config['database']
            )

            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Get unconsumed critical alerts from last 5 minutes
                cur.execute("""
                    SELECT
                        id,
                        token,
                        alert_type,
                        urgency,
                        confidence,
                        signals,
                        recommendation,
                        created_at
                    FROM tactical_alerts
                    WHERE consumed_at IS NULL
                    AND urgency IN ('IMMEDIATE', 'HIGH')
                    AND created_at > NOW() - INTERVAL '5 minutes'
                    ORDER BY confidence DESC, created_at DESC
                    LIMIT 5
                """)

                alerts = cur.fetchall()

                # Mark alerts as consumed
                if alerts:
                    alert_ids = [a['id'] for a in alerts]
                    cur.execute("""
                        UPDATE tactical_alerts
                        SET consumed_at = NOW()
                        WHERE id = ANY(%s)
                    """, (alert_ids,))
                    conn.commit()

            conn.close()
            return alerts

        except Exception as e:
            print(f"[WARNING] Could not check tactical alerts: {e}")
            return []

    def update_market_regime(self):
        """Update market regime if needed (every hour)"""
        now = datetime.now()
        if (now - self.regime_check_time).total_seconds() > 3600:  # Check hourly
            try:
                self.current_regime = self.market_analyzer.get_current_regime()
                self.regime_check_time = now

                print(f"\n[REGIME] Market: {self.current_regime['regime']} (confidence: {self.current_regime['confidence']}%)")
                print(f"[REGIME] Strategy: {self.current_regime['recommended_strategy']}")
                if self.current_regime['btc_dominance']:
                    print(f"[REGIME] BTC Dominance: {self.current_regime['btc_dominance']:.1f}%")
                    if self.current_regime['favor_altcoins']:
                        print(f"[REGIME] Favoring ALTCOINS ({self.current_regime['altcoin_confidence']:.0f}% confidence)")

            except Exception as e:
                print(f"[WARNING] Could not update market regime: {e}")

    async def run_forever(self):
        """Main trading loop with dual-cycle architecture:
        - Fast cycle: Check tactical alerts every 2 minutes (can trade immediately!)
        - Slow cycle: Strategic analysis every 30 minutes
        """
        print("\n[START] Beginning AI trading with fast response system...")
        print("  • Tactical alerts checked: Every 2 minutes")
        print("  • Strategic analysis: Every 30 minutes")
        print("  • Trades can execute: Within 2 minutes of critical events!")
        print("Press Ctrl+C to stop gracefully\n")

        # Track when we last ran strategic analysis
        last_strategic_analysis = 0  # Force immediate strategic run on startup
        tactical_check_interval = 120  # 2 minutes
        strategic_interval = 1800  # 30 minutes

        # Track deferred tactical alerts (70-84% confidence)
        deferred_alerts = []

        while self.trading_active:
            try:
                loop_start = time.time()
                executed_trades = 0

                # ===========================================================
                # EMERGENCY: Check for market crash using MULTIPLE INDICATORS
                # ===========================================================
                crash_analysis = self.data_intel.detect_market_crash_multi_indicator()

                if crash_analysis['action_required']:
                    print(f"\n[MARKET CRASH] {crash_analysis['status']}")
                    print(f"  Severity: {crash_analysis['severity']}")
                    print(f"  Probability: {crash_analysis['probability']}%")
                    print(f"  Reasoning: {crash_analysis['reasoning']}")
                    print(f"  Recommendation: {crash_analysis['recommendation']}")

                    # Take action based on recommendation
                    if crash_analysis['recommendation'] == "EXIT_ALL_POSITIONS":
                        print("\n[EMERGENCY] Exiting ALL positions immediately!")

                        # Close all open positions
                        for token in list(self.portfolio.positions.keys()):
                            current_price = self.portfolio.get_current_price(token)
                            if current_price:
                                self.portfolio.close_position(
                                    token=token,
                                    exit_price=current_price,
                                    reasoning=f"EMERGENCY: {crash_analysis['reasoning']}"
                                )

                        # Pause trading for 10 minutes
                        print("\n[PAUSE] Halting trading for 10 minutes to let market stabilize...")
                        time.sleep(600)
                        continue

                    elif crash_analysis['recommendation'] == "REDUCE_EXPOSURE_50%":
                        print("\n[WARNING] Reducing exposure by 50%")

                        # Close half of positions (worst performing first)
                        positions = self.portfolio.get_positions()
                        if positions:
                            # Sort by P&L (worst first)
                            sorted_positions = sorted(positions.items(),
                                                    key=lambda x: x[1]['pnl_pct'])
                            positions_to_close = len(sorted_positions) // 2

                            for i in range(positions_to_close):
                                token = sorted_positions[i][0]
                                current_price = self.portfolio.get_current_price(token)
                                if current_price:
                                    self.portfolio.close_position(
                                        token=token,
                                        exit_price=current_price,
                                        reasoning=f"CRASH WARNING: {crash_analysis['reasoning']}"
                                    )

                        # Pause new positions for 5 minutes
                        print("\n[PAUSE] No new positions for 5 minutes...")
                        time.sleep(300)
                        continue

                elif crash_analysis['severity'] == "MODERATE":
                    # Just log the alert but continue trading conservatively
                    print(f"\n[ALERT] Market stress detected: {crash_analysis['reasoning']}")
                    print(f"  Recommendation: {crash_analysis['recommendation']}")
                    continue

                # Update market regime (hourly)
                self.update_market_regime()

                # ===========================================================
                # CHECK PARTIAL PROFIT TARGETS (every cycle)
                # ===========================================================
                self.check_partial_profit_targets()

                # ===========================================================
                # FAST CYCLE: Check tactical alerts EVERY 1 minute (optimized)
                # ===========================================================
                tactical_alerts = self.check_tactical_alerts()
                if tactical_alerts:
                    print(f"\n🚨 [TACTICAL] {len(tactical_alerts)} critical alerts detected!")
                    for alert in tactical_alerts:
                        print(f"  - {alert['token']}: {alert['recommendation']} ({alert['urgency']}, {alert['confidence']}% confidence)")

                        # Process critical alerts with tiered confidence system
                        if alert['recommendation'] in ['ENTER_LONG', 'ENTER_SHORT', 'EXIT_POSITION']:
                            status, decision = await self.process_tactical_alert(alert)

                            if status == 'EXECUTED':
                                executed_trades += 1
                            elif status == 'DEFERRED':
                                # Add to deferred list for strategic cycle
                                deferred_alerts.append(decision)

                # ===========================================================
                # STRATEGIC CYCLE: Analysis every 5 minutes (optimized from 30)
                # Research shows 9-11x returns with 5-min intervals
                # ===========================================================
                time_since_strategic = time.time() - last_strategic_analysis

                if time_since_strategic >= strategic_interval:
                    print(f"\n[STRATEGIC] Running 5-minute strategic analysis...")

                    # Discover all active tokens
                    active_tokens = self.data_intel.discover_active_tokens(min_activity_hours=24)

                    if not active_tokens:
                        print("[WARNING] No active tokens found for strategic analysis")
                    else:
                        print(f"[SCAN] Processing {len(active_tokens)} active tokens...")

                        # Get trending tokens for priority processing
                        trending = self.data_intel.get_trending_tokens(min_spike=2.0)
                        trending_tokens = [t['token'] for t in trending]

                        # Process trending tokens first, then others
                        priority_tokens = trending_tokens + [t for t in active_tokens if t not in trending_tokens]

                        # Check circuit breakers
                        if not self.check_circuit_breakers():
                            # Start with deferred tactical alerts (70-84% confidence)
                            opportunities = deferred_alerts.copy()
                            if deferred_alerts:
                                print(f"[STRATEGIC] Processing {len(deferred_alerts)} deferred tactical alerts")
                                deferred_alerts.clear()  # Clear for next cycle

                            # Process each token
                            for token in priority_tokens[:20]:  # Process top 20
                                try:
                                    # Get quick summary first
                                    summary = self.data_intel.get_quick_summary(token)
                                    if not summary:
                                        continue

                                    # Quick filter: Skip if no activity
                                    if summary['tweets_1h'] < 5 and abs(summary['price_change_1h']) < 1:
                                        continue

                                    # Check liquidity before expensive analysis (min $10M daily volume)
                                    if not self.data_intel.check_liquidity(token):
                                        continue

                                    # Interesting enough for deeper analysis
                                    signal = await self.analyze_token(token, summary)
                                    if signal and signal['action'] != 'HOLD':
                                        opportunities.append(signal)

                                except Exception as e:
                                    print(f"[ERROR] Failed to process {token}: {e}")
                                    continue

                            # Sort opportunities by confidence
                            opportunities.sort(key=lambda x: x['confidence'], reverse=True)

                            # Execute top opportunities
                            for opp in opportunities:
                                if executed_trades >= 3:  # Max 3 new positions per cycle
                                    break

                                success = await self.execute_decision(opp)
                                if success:
                                    executed_trades += 1

                            print(f"[STRATEGIC] Found {len(opportunities)} opportunities, executed {executed_trades} trades")
                        else:
                            print("[HALT] Circuit breaker triggered, skipping strategic analysis")

                    # Update last strategic analysis time
                    last_strategic_analysis = time.time()
                    print(f"[STRATEGIC] Next strategic analysis in 5 minutes")

                # ===========================================================
                # ALWAYS-ON MONITORING: Top tokens every 5 minutes
                # Never miss major market moves in BTC/ETH/SOL
                # ===========================================================
                if time_since_strategic >= config.ALWAYS_MONITOR_INTERVAL:
                    print(f"\n[ALWAYS-ON] Monitoring critical tokens: {config.ALWAYS_MONITOR_TOKENS}")

                    for token in config.ALWAYS_MONITOR_TOKENS:
                        try:
                            # Skip filters - always analyze these tokens
                            summary = self.data_intel.get_quick_summary(token)
                            if summary:
                                # Direct to AI analysis (bypass activity filters)
                                print(f"  Analyzing {token} (always-on)...")
                                signal = await self.analyze_token(token, summary)

                                if signal and signal['action'] != 'HOLD':
                                    # High-priority tokens get immediate execution
                                    if executed_trades < config.MAX_DAILY_TRADES:
                                        success = await self.execute_decision(signal)
                                        if success:
                                            executed_trades += 1
                                            print(f"  ✓ Executed {signal['action']} on {token}")

                        except Exception as e:
                            print(f"  [ERROR] Failed to monitor {token}: {e}")
                            continue

                # Update portfolio state
                self.portfolio.update_positions()

                # Check for closed positions (stop loss / take profit)
                self.check_and_record_closed_positions()

                # Print cycle summary
                cycle_time = time.time() - loop_start

                # Determine what type of cycle this was
                cycle_type = "TACTICAL+STRATEGIC" if time_since_strategic >= strategic_interval else "TACTICAL"

                print(f"\n[{cycle_type} CYCLE] Completed in {cycle_time:.1f}s")
                if executed_trades > 0:
                    print(f"  🎯 Trades executed: {executed_trades}")
                print(f"  Portfolio value: ${self.portfolio.get_total_value():,.2f}")
                print(f"  Next tactical check: 1 minute")
                if time_since_strategic < strategic_interval:
                    mins_until_strategic = (strategic_interval - time_since_strategic) / 60
                    print(f"  Next strategic analysis: {mins_until_strategic:.1f} minutes")

                # CRITICAL: Sleep only 2 minutes for tactical responsiveness!
                wait_time = max(1, tactical_check_interval - cycle_time)
                print(f"\n[WAIT] Checking for alerts again in {wait_time:.0f} seconds...")
                await asyncio.sleep(wait_time)

            except Exception as e:
                print(f"[ERROR] Trading loop error: {e}")
                await asyncio.sleep(60)

    async def analyze_token(self, token: str, quick_summary: Dict) -> Optional[Dict]:
        """
        Analyze a token and generate trading signal
        Uses Tier 1 Claude for initial decision
        """
        try:
            # Build market context
            context = await self.build_market_context(token, quick_summary)

            # Generate Tier 1 decision with Claude
            decision = await self.get_claude_decision(token, context)

            if not decision:
                return None

            # If BUY signal with high confidence, run Tier 2 verification
            if (config.ENABLE_TIER2_VERIFICATION and
                decision['action'] == 'BUY' and
                decision['confidence'] >= config.TIER2_TRIGGER_CONFIDENCE):

                print(f"[TIER 2] Verifying BUY signal for {token}...")
                verified = await self.run_ensemble_verification(token, context, decision)

                if not verified:
                    print(f"[TIER 2] Ensemble rejected BUY for {token}")
                    decision['action'] = 'HOLD'
                    decision['reasoning'] += " (Ensemble verification failed)"

            return decision

        except Exception as e:
            print(f"[ERROR] Analysis failed for {token}: {e}")
            return None

    async def process_tactical_alert(self, alert: Dict) -> tuple:
        """
        Process a critical tactical alert with tiered confidence system.

        Returns: (status, decision) where status is:
            - 'EXECUTED': Trade executed immediately (confidence >= 85%)
            - 'DEFERRED': Deferred to strategic cycle (70-84% confidence)
            - 'IGNORED': Below threshold (< 70% confidence)
        """
        try:
            token = alert['token']
            recommendation = alert['recommendation']
            confidence = alert['confidence']

            # Check liquidity before processing (min $10M daily volume)
            if not self.data_intel.check_liquidity(token):
                print(f"[TACTICAL] Ignoring {token} - insufficient liquidity")
                return ('IGNORED', None)

            # Build quick decision based on tactical alert
            decision = {
                'token': token,
                'action': 'HOLD',
                'confidence': confidence / 100,  # Convert to decimal
                'position_size': 0.03,  # Conservative size for tactical trades
                'stop_loss_pct': 0.05,  # Wider stop for volatile conditions
                'take_profit_pct': 0.10,
                'reasoning': f"TACTICAL ALERT: {alert['alert_type']} - {alert.get('signals', [])}",
                'timestamp': datetime.now().isoformat()
            }

            # Map recommendation to action
            if recommendation == 'ENTER_LONG':
                decision['action'] = 'BUY'
            elif recommendation == 'ENTER_SHORT':
                decision['action'] = 'SHORT'
            elif recommendation == 'EXIT_POSITION':
                decision['action'] = 'SELL'

            # Tiered execution based on confidence
            if decision['action'] == 'HOLD':
                return ('IGNORED', None)

            # High confidence: Execute immediately!
            if confidence >= config.TACTICAL_ALERT_IMMEDIATE_THRESHOLD:
                success = await self.execute_decision(decision)
                if success:
                    print(f"[TACTICAL] ✓ EXECUTED IMMEDIATELY: {token} at {confidence}% confidence")
                    return ('EXECUTED', decision)
                else:
                    return ('IGNORED', None)

            # Medium confidence: Defer to strategic cycle
            elif confidence >= config.TACTICAL_ALERT_DEFERRED_THRESHOLD:
                print(f"[TACTICAL] → DEFERRED: {token} at {confidence}% confidence (will process in strategic cycle)")
                return ('DEFERRED', decision)

            # Low confidence: Ignore
            else:
                print(f"[TACTICAL] ✗ IGNORED: {token} at {confidence}% confidence (below {config.TACTICAL_ALERT_DEFERRED_THRESHOLD}% threshold)")
                return ('IGNORED', None)

        except Exception as e:
            print(f"[ERROR] Failed to process tactical alert: {e}")
            return ('IGNORED', None)

    async def build_market_context(self, token: str, quick_summary: Dict) -> Dict:
        """
        Build comprehensive market context for AI decision
        Starts with quick summary, adds deep data as needed
        """
        context = {
            'token': token,
            'timestamp': datetime.now().isoformat(),
            'quick_summary': quick_summary
        }

        # If token looks interesting (high activity or price movement), get deep data
        if (quick_summary['tweets_1h'] > 20 or
            abs(quick_summary['price_change_1h']) > 3 or
            quick_summary['volume_spike'] > 2):

            # Get detailed sentiment
            context['sentiment'] = self.data_intel.get_sentiment_summary(token, hours=6)

            # Get price history
            context['price_data'] = self.data_intel.get_price_history(token, hours=24)

            # Get market metrics
            context['market_metrics'] = self.data_intel.get_market_metrics(token)

            # Get order book intelligence for better entry/exit timing
            context['order_book_intel'] = self.data_intel.get_order_book_intelligence(token)

            # Add market-wide context
            context['fear_greed'] = self.data_intel.get_fear_greed_index()

            # Check for whale movements
            whale_flows = self.data_intel.get_whale_movements(hours=3)
            context['whale_activity'] = [w for w in whale_flows if w['token'] == token]

            # CRITICAL: Check for liquidation cascades
            context['liquidation_cascade'] = self.data_intel.get_liquidation_cascade_analysis(token)

            # Find similar historical patterns for prediction
            context['historical_patterns'] = self.data_intel.find_similar_historical_patterns(token, lookback_days=30)

        # Add portfolio context
        context['portfolio'] = {
            'current_positions': self.portfolio.get_positions(),
            'cash_available': self.portfolio.get_available_cash(),
            'total_value': self.portfolio.get_total_value(),
            'daily_pnl': self.daily_pnl,
            'open_position_count': len(self.portfolio.get_positions())
        }

        return context

    async def get_claude_decision(self, token: str, context: Dict) -> Optional[Dict]:
        """Generate trading decision using Browser AI or API fallback"""
        try:
            # Use browser AI if enabled (avoids API costs)
            if config.USE_BROWSER_AI:
                provider = getattr(config, 'BROWSER_AI_PROVIDER', 'claude')
                browser_ai = get_browser_ai(provider)

                # Get decision from browser
                decision = browser_ai.get_trading_decision(token, context)

                if decision:
                    print(f"[BROWSER AI] Got decision from {browser_ai.provider}")
                    return decision
                else:
                    print(f"[BROWSER AI] Failed, falling back to API")
                    # Fall through to API method

            # Original API method (fallback)
            # Apply learned adjustments from Trade Learner
            learned_adjustment = self.trade_learner.get_learned_adjustment(
                token=token,
                market_context=context
            )

            if learned_adjustment['should_adjust']:
                print(f"[LEARNING] Applying adjustments for {token}:")
                print(f"  Confidence modifier: {learned_adjustment['confidence_modifier']:+.2f}")
                print(f"  Position size modifier: {learned_adjustment['position_size_modifier']:.2f}x")
                print(f"  Pattern detected: {learned_adjustment.get('pattern_type', 'None')}")
                if learned_adjustment.get('recommendation'):
                    print(f"  Recommendation: {learned_adjustment['recommendation']}")

            # Build prompt
            prompt = f"""
Analyze this cryptocurrency opportunity and provide a trading decision.

TOKEN: {token}
CURRENT PRICE: ${context['quick_summary']['price']:.4f}
TIMESTAMP: {context['timestamp']}

QUICK METRICS:
- Tweets (1h): {context['quick_summary']['tweets_1h']}
- Sentiment (1h): {context['quick_summary']['sentiment_1h']:.3f}
- Price Change (1h): {context['quick_summary']['price_change_1h']:.2f}%
- Volume Spike: {context['quick_summary']['volume_spike']:.1f}x

"""
            # Add detailed data if available
            if 'sentiment' in context:
                prompt += f"""
SENTIMENT DETAILS (6h):
- Total Tweets: {context['sentiment']['tweet_count']}
- Avg Sentiment: {context['sentiment']['avg_sentiment']:.3f}
- Whale Tweets: {context['sentiment']['whale_tweets']}
- Quality Tweets: {context['sentiment']['quality_tweets']}
- Momentum Score: {context['sentiment']['momentum_score']:.3f}
"""

            if 'price_data' in context:
                prompt += f"""
PRICE ACTION (24h):
- 24h Change: {context['price_data']['price_change_24h']:.2f}%
- 24h High: ${context['price_data']['high_24h']:.4f}
- 24h Low: ${context['price_data']['low_24h']:.4f}
- Volatility: {context['price_data']['volatility']:.2f}%
"""

            if 'market_metrics' in context:
                if 'order_book' in context['market_metrics']:
                    prompt += f"""
ORDER BOOK:
- Spread: {context['market_metrics']['order_book']['spread']:.4f}
- Imbalance: {context['market_metrics']['order_book']['imbalance']:.2f}
"""
                if 'funding_rate' in context['market_metrics']:
                    prompt += f"""
FUNDING: {context['market_metrics']['funding_rate']:.4f}%
"""

            # Add order book intelligence
            if 'order_book_intel' in context and context['order_book_intel']['has_data']:
                book = context['order_book_intel']
                prompt += f"""
ORDER BOOK INTELLIGENCE:
- Entry Quality: {book['entry_quality']} (Score: {book.get('entry_score', 0)}/100)
- Recommendation: {book['recommendation']}
- Spread: {book['spread']['quality']} ({book['spread']['percentage']:.3f}%)
- Buy Liquidity: {book['liquidity']['buy_quality']} (Est. Slippage: {book['liquidity']['estimated_buy_slippage']}%)
- Sell Liquidity: {book['liquidity']['sell_quality']} (Est. Slippage: {book['liquidity']['estimated_sell_slippage']}%)
- Order Pressure: {book['pressure']['direction']} ({book['pressure']['signal']})
- Walls Detected: {', '.join(book['walls'])}
- Analysis: {book['reasoning']}
- Trading Advice: {' | '.join(book['trading_advice'])}
"""

            # Add liquidation cascade analysis
            if 'liquidation_cascade' in context:
                liq = context['liquidation_cascade']
                prompt += f"""
LIQUIDATION CASCADE ANALYSIS:
- Risk Score: {liq['risk_score']}/100
- Type: {liq['cascade_type']}
- Velocity: {liq['velocity']} liquidations/min
- Total Liquidated (1h): ${liq['total_liquidated_1h']:,.0f}
- Longs Liquidated: ${liq['long_liquidated']:,.0f}
- Shorts Liquidated: ${liq['short_liquidated']:,.0f}
- Recommendation: {liq['recommendation']}
- Confidence: {liq['confidence']}%
- Analysis: {liq['reasoning']}
"""

            # Add historical pattern analysis
            if 'historical_patterns' in context and context['historical_patterns']['has_patterns']:
                patterns = context['historical_patterns']
                stats = patterns['historical_stats']
                prompt += f"""
HISTORICAL PATTERN ANALYSIS:
- Similar Patterns Found: {patterns['pattern_count']} (Similarity: {patterns.get('similarity_score', 0)}%)
- Prediction: {patterns['prediction']} (Confidence: {patterns['confidence']})
- Signal: {patterns['signal']}
- Average 24h Outcome: {stats['avg_outcome_24h']:+.1f}%
- Win Rate: {stats['win_rate']}%
- Risk/Reward Ratio: {stats['risk_reward_ratio']}:1
- Best Historical Outcome: {stats['best_outcome']:+.1f}%
- Worst Historical Outcome: {stats['worst_outcome']:+.1f}%
- Analysis: {patterns['reasoning']}
"""

            # Add portfolio context
            prompt += f"""
PORTFOLIO:
- Available Cash: ${context['portfolio']['cash_available']:,.2f}
- Open Positions: {context['portfolio']['open_position_count']}
- Daily P&L: ${context['portfolio']['daily_pnl']:.2f}

Provide your trading decision in the specified XML format.
"""

            # Get optimized prompt from AI Optimizer
            market_conditions = {
                'btc_change': context.get('price_data', {}).get('price_change_24h', 0) if 'price_data' in context else 0,
                'atr': self.portfolio.calculate_volatility(token, hours=24),
                'liquidation_velocity': context.get('liquidation_cascade', {}).get('velocity', 0) if 'liquidation_cascade' in context else 0,
                'liquidation_total': context.get('liquidation_cascade', {}).get('total_liquidated_1h', 0) if 'liquidation_cascade' in context else 0,
                'cascade_type': context.get('liquidation_cascade', {}).get('cascade_type', 'NONE') if 'liquidation_cascade' in context else 'NONE',
                'spread': context.get('order_book_intel', {}).get('spread', {}).get('percentage', 0.1) if 'order_book_intel' in context else 0.1,
                'sentiment': context.get('sentiment', {}).get('avg_sentiment', 0) if 'sentiment' in context else 0,
                'tweet_volume_spike': context.get('quick_summary', {}).get('volume_spike', 1),
                'crash_probability': 0  # Will be set if crash analysis available
            }

            # Add crash probability if we have it
            crash_analysis = self.data_intel.detect_market_crash_multi_indicator()
            market_conditions['crash_probability'] = crash_analysis.get('probability', 0)

            # Get optimized prompt
            optimized_prompt = self.ai_optimizer.get_optimal_prompt(token, market_conditions, prompt)

            # Call Claude with optimized prompt
            response = self.claude_client.messages.create(
                model=config.CLAUDE_MODEL,
                max_tokens=config.CLAUDE_MAX_TOKENS,
                temperature=config.CLAUDE_TEMPERATURE,
                system=config.SYSTEM_PROMPT,
                messages=[{"role": "user", "content": optimized_prompt}]
            )

            # Parse response
            decision = self.parse_claude_response(response.content[0].text, token)

            if decision and learned_adjustment['should_adjust']:
                # Apply learned adjustments to the decision
                original_confidence = decision['confidence']
                original_size = decision['position_size']

                # Adjust confidence
                decision['confidence'] = max(0.0, min(1.0,
                    decision['confidence'] + learned_adjustment['confidence_modifier']))

                # Adjust position size
                decision['position_size'] = max(0.01, min(0.05,
                    decision['position_size'] * learned_adjustment['position_size_modifier']))

                # Add learning context to reasoning
                if learned_adjustment.get('pattern_type'):
                    decision['reasoning'] += f" | LEARNED: {learned_adjustment['pattern_type']} pattern detected"

                # Override action if learner strongly recommends it
                if learned_adjustment.get('override_action'):
                    print(f"[LEARNING] Overriding action from {decision['action']} to {learned_adjustment['override_action']}")
                    decision['action'] = learned_adjustment['override_action']
                    decision['reasoning'] += f" | OVERRIDE: {learned_adjustment.get('override_reason', '')}"

                if original_confidence != decision['confidence'] or original_size != decision['position_size']:
                    print(f"[LEARNING] Adjusted: Confidence {original_confidence:.2f} -> {decision['confidence']:.2f}, Size {original_size:.2f} -> {decision['position_size']:.2f}")

            if decision:
                print(f"[TIER 1] {token}: {decision['action']} (confidence: {decision['confidence']:.2f})")

                # Track decision for performance optimization
                self.ai_optimizer.track_decision(
                    model='claude',
                    token=token,
                    decision=decision,
                    outcome=None  # Will be updated when position closes
                )

            return decision

        except Exception as e:
            print(f"[ERROR] Claude decision failed for {token}: {e}")
            return None

    def parse_claude_response(self, response_text: str, token: str) -> Optional[Dict]:
        """Parse Claude's enhanced XML response with analysis and scores"""
        try:
            # Extract analysis section (optional, for logging)
            analysis = {}
            if '<analysis>' in response_text and '</analysis>' in response_text:
                analysis_start = response_text.find('<analysis>')
                analysis_end = response_text.find('</analysis>') + len('</analysis>')
                try:
                    analysis_xml = response_text[analysis_start:analysis_end]
                    analysis_root = ET.fromstring(analysis_xml)
                    analysis = {
                        'market_regime': analysis_root.find('market_regime').text if analysis_root.find('market_regime') is not None else 'UNKNOWN',
                        'sentiment_analysis': analysis_root.find('sentiment_analysis').text if analysis_root.find('sentiment_analysis') is not None else '',
                        'technical_analysis': analysis_root.find('technical_analysis').text if analysis_root.find('technical_analysis') is not None else '',
                        'risk_assessment': analysis_root.find('risk_assessment').text if analysis_root.find('risk_assessment') is not None else ''
                    }
                    print(f"[ANALYSIS] {token} - Regime: {analysis['market_regime']}")
                except:
                    pass

            # Extract scores section (optional, for tracking)
            scores = {}
            if '<scores>' in response_text and '</scores>' in response_text:
                scores_start = response_text.find('<scores>')
                scores_end = response_text.find('</scores>') + len('</scores>')
                try:
                    scores_xml = response_text[scores_start:scores_end]
                    scores_root = ET.fromstring(scores_xml)
                    scores = {
                        'sentiment': float(scores_root.find('sentiment_score').text) if scores_root.find('sentiment_score') is not None else 50,
                        'technical': float(scores_root.find('technical_score').text) if scores_root.find('technical_score') is not None else 50,
                        'liquidity': float(scores_root.find('liquidity_score').text) if scores_root.find('liquidity_score') is not None else 50,
                        'risk': float(scores_root.find('risk_score').text) if scores_root.find('risk_score') is not None else 50,
                        'momentum': float(scores_root.find('momentum_score').text) if scores_root.find('momentum_score') is not None else 50,
                        'timing': float(scores_root.find('timing_score').text) if scores_root.find('timing_score') is not None else 50,
                        'fundamental': float(scores_root.find('fundamental_score').text) if scores_root.find('fundamental_score') is not None else 50,
                        'overall': float(scores_root.find('overall_score').text) if scores_root.find('overall_score') is not None else 50
                    }
                    print(f"[SCORES] {token} - Overall: {scores['overall']:.0f}/100")
                except:
                    pass

            # Find trading decision XML (required)
            start = response_text.find('<trading_decision>')
            end = response_text.find('</trading_decision>') + len('</trading_decision>')

            if start == -1 or end == -1:
                print(f"[ERROR] No valid trading_decision XML found in Claude response")
                return None

            xml_content = response_text[start:end]
            root = ET.fromstring(xml_content)

            # Extract fields
            decision = {
                'token': token,
                'action': root.find('action').text.upper(),
                'confidence': float(root.find('confidence').text),
                'position_size': float(root.find('position_size').text),
                'stop_loss_pct': float(root.find('stop_loss_pct').text),
                'take_profit_pct': float(root.find('take_profit_pct').text),
                'reasoning': root.find('reasoning').text,
                'risk_factors': root.find('risk_factors').text if root.find('risk_factors') is not None else "",
                'exit_plan': root.find('exit_plan').text if root.find('exit_plan') is not None else "",
                'timestamp': datetime.now().isoformat(),
                'analysis': analysis,  # Store analysis for tracking
                'scores': scores,  # Store scores for performance tracking
                'scenario': analysis.get('market_regime', 'UNKNOWN')  # Store scenario for optimizer
            }

            # Apply dynamic confidence threshold based on market regime
            min_confidence = config.MIN_TIER1_CONFIDENCE
            if self.current_regime:
                regime_thresholds = self.current_regime.get('thresholds', {})
                min_confidence = regime_thresholds.get('entry_confidence', config.MIN_TIER1_CONFIDENCE)

                # Apply regime-specific adjustments
                if 'position_size_multiplier' in regime_thresholds:
                    decision['position_size'] *= regime_thresholds['position_size_multiplier']
                if 'stop_loss_pct' in regime_thresholds:
                    decision['stop_loss_pct'] = regime_thresholds['stop_loss_pct']
                if 'take_profit_pct' in regime_thresholds:
                    decision['take_profit_pct'] = regime_thresholds['take_profit_pct']

            # Validate against dynamic threshold
            if decision['confidence'] < min_confidence:
                decision['action'] = 'HOLD'
                decision['reasoning'] += f" (Confidence {decision['confidence']:.2f} below regime threshold {min_confidence:.2f})"

            return decision

        except Exception as e:
            print(f"[ERROR] Failed to parse Claude response: {e}")
            return None

    async def run_ensemble_verification(self, token: str, context: Dict, tier1_decision: Dict) -> bool:
        """
        Run Tier 2 ensemble verification for high-stakes BUY decisions
        Returns True if ensemble agrees with BUY
        """
        if not self.ensemble_clients:
            return True  # Skip if ensemble not configured

        votes = {}

        # Prepare verification prompt
        prompt = f"""
Another AI model has recommended BUYING {token} with {tier1_decision['confidence']:.0%} confidence.

Reasoning: {tier1_decision['reasoning']}

Current Price: ${context['quick_summary']['price']:.4f}
Recent Sentiment: {context['quick_summary']['sentiment_1h']:.3f}
Price Change (1h): {context['quick_summary']['price_change_1h']:.2f}%

Do you agree with this BUY decision? Answer: AGREE or DISAGREE with brief reasoning.
"""

        # Get votes from each model (parallel)
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {}

            # Submit Claude vote
            futures['claude'] = executor.submit(
                self._get_claude_vote, prompt
            )

            # Submit DeepSeek vote if available
            if 'deepseek' in self.ensemble_clients:
                futures['deepseek'] = executor.submit(
                    self._get_deepseek_vote, prompt
                )

            # Submit Gemini vote if available
            if 'gemini' in self.ensemble_clients:
                futures['gemini'] = executor.submit(
                    self._get_gemini_vote, prompt
                )

            # Collect votes
            for model_name, future in futures.items():
                try:
                    vote = future.result(timeout=10)
                    votes[model_name] = vote
                    print(f"[ENSEMBLE] {model_name}: {vote}")
                except Exception as e:
                    print(f"[ERROR] {model_name} vote failed: {e}")
                    votes[model_name] = 'DISAGREE'  # Conservative default

        # Calculate weighted consensus using dynamic performance-based weights
        total_weight = 0
        agree_weight = 0

        # Get dynamic weights from AI optimizer based on performance
        scenario = tier1_decision.get('scenario', 'STANDARD')
        dynamic_weights = self.ai_optimizer.calculate_dynamic_weights(scenario)

        # Use dynamic weights if available, else fallback to regime/config weights
        if dynamic_weights:
            regime_weights = dynamic_weights
        elif self.current_regime and 'model_weights' in self.current_regime:
            regime_weights = self.current_regime['model_weights']
        else:
            # Fallback to config weights
            regime_weights = {
                'claude': config.ENSEMBLE_MODELS['claude']['weight'],
                'deepseek': config.ENSEMBLE_MODELS['deepseek']['weight'],
                'gemini': config.ENSEMBLE_MODELS['gemini']['weight']
            }

        for model_name, vote in votes.items():
            weight = regime_weights.get(model_name, 0.33)
            total_weight += weight
            if vote == 'AGREE':
                agree_weight += weight

        consensus = agree_weight / total_weight if total_weight > 0 else 0

        print(f"[ENSEMBLE] Consensus: {consensus:.0%} (threshold: {config.MIN_TIER2_CONSENSUS:.0%})")

        return consensus >= config.MIN_TIER2_CONSENSUS

    def _get_claude_vote(self, prompt: str) -> str:
        """Get vote from Claude"""
        try:
            response = self.claude_client.messages.create(
                model=config.CLAUDE_MODEL,
                max_tokens=200,
                temperature=0.3,
                messages=[{"role": "user", "content": prompt}]
            )
            text = response.content[0].text.upper()
            return 'AGREE' if 'AGREE' in text else 'DISAGREE'
        except:
            return 'DISAGREE'

    def _get_deepseek_vote(self, prompt: str) -> str:
        """Get vote from DeepSeek"""
        try:
            response = self.ensemble_clients['deepseek'].chat.completions.create(
                model=config.ENSEMBLE_MODELS['deepseek']['name'],
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
                temperature=0.3
            )
            text = response.choices[0].message.content.upper()
            return 'AGREE' if 'AGREE' in text else 'DISAGREE'
        except:
            return 'DISAGREE'

    def _get_gemini_vote(self, prompt: str) -> str:
        """Get vote from Gemini"""
        try:
            response = self.ensemble_clients['gemini'].generate_content(prompt)
            text = response.text.upper()
            return 'AGREE' if 'AGREE' in text else 'DISAGREE'
        except:
            return 'DISAGREE'

    async def execute_decision(self, decision: Dict) -> bool:
        """Execute trading decision through portfolio manager"""
        try:
            token = decision['token']
            action = decision['action']

            # Get current price
            price = self.data_intel.get_current_price(token)
            if not price:
                print(f"[ERROR] Cannot execute - no price for {token}")
                return False

            if action == 'BUY':
                # Calculate position size (with adaptive sizing if enabled)
                position_value = self.portfolio.calculate_position_size(
                    decision['position_size'],
                    price,
                    token=token,
                    confidence=decision['confidence']
                )

                if position_value < config.MIN_POSITION_SIZE_USD:
                    print(f"[SKIP] Position too small: ${position_value:.2f}")
                    return False

                # Check correlation risk with existing positions
                existing_tokens = list(self.portfolio.positions.keys())
                if existing_tokens:
                    correlation_risk = self.data_intel.get_portfolio_correlation_risk(
                        token, existing_tokens, hours=24
                    )

                    if correlation_risk['recommendation'] == 'BLOCK':
                        print(f"⚠️ [CORRELATION BLOCKED] {token}")
                        print(f"   Risk Level: {correlation_risk['risk_level']}")
                        print(f"   Max Correlation: {correlation_risk['max_correlation']:.2f}")
                        print(f"   {correlation_risk['warning']}")
                        print(f"   Correlations: {correlation_risk['correlations']}")
                        return False
                    elif correlation_risk['warning']:
                        print(f"⚠️ [CORRELATION WARNING] {token}: {correlation_risk['warning']}")

                # Validate risk-reward ratio (minimum 2:1)
                risk_reward = decision['take_profit_pct'] / decision['stop_loss_pct']
                if risk_reward < 2.0:
                    print(f"[REJECTED] {token} - Poor R:R: {risk_reward:.2f}:1 (minimum 2:1 required)")
                    print(f"   Take Profit: {decision['take_profit_pct']:.1f}% / Stop Loss: {decision['stop_loss_pct']:.1f}%")
                    return False

                # Execute buy (LONG position)
                success = self.portfolio.open_position(
                    token=token,
                    entry_price=price,
                    position_value=position_value,
                    stop_loss_pct=decision['stop_loss_pct'],
                    take_profit_pct=decision['take_profit_pct'],
                    reasoning=decision['reasoning'],
                    position_type='LONG'
                )

                if success:
                    self.daily_trade_count += 1
                    print(f"[BUY] {token} - ${position_value:.2f} at ${price:.4f}")

                    # Track the trade for learning
                    self.active_trades[token] = {
                        'entry_time': datetime.now(),
                        'entry_price': price,
                        'position_value': position_value,
                        'position_type': 'LONG',
                        'decision': decision,
                        'market_context': {
                            'btc_price': self.data_intel.get_current_price('BTC'),
                            'fear_greed': self.data_intel.get_fear_greed_index(),
                            'regime': self.current_regime.get('regime', 'UNKNOWN') if self.current_regime else 'UNKNOWN'
                        }
                    }

                return success

            elif action == 'SHORT':
                # Count existing SHORT positions
                short_positions = [p for p in self.portfolio.positions.values() if p.get('position_type') == 'SHORT']
                short_count = len(short_positions)

                # Check MAX_SHORT_POSITIONS limit
                if short_count >= config.MAX_SHORT_POSITIONS:
                    print(f"[REJECTED] {token} - Max SHORT positions reached: {short_count}/{config.MAX_SHORT_POSITIONS}")
                    return False

                # Calculate total SHORT exposure
                total_short_value = sum(p['position_value'] for p in short_positions)
                portfolio_value = self.portfolio.get_total_value()

                # Calculate position size (with adaptive sizing if enabled)
                position_value = self.portfolio.calculate_position_size(
                    decision['position_size'],
                    price,
                    token=token,
                    confidence=decision['confidence']
                )

                if position_value < config.MIN_POSITION_SIZE_USD:
                    print(f"[SKIP] Position too small: ${position_value:.2f}")
                    return False

                # Check MAX_SHORT_EXPOSURE_PCT limit
                new_short_exposure_pct = ((total_short_value + position_value) / portfolio_value) * 100
                if new_short_exposure_pct > config.MAX_SHORT_EXPOSURE_PCT:
                    print(f"[REJECTED] {token} - SHORT exposure would exceed limit: {new_short_exposure_pct:.1f}% > {config.MAX_SHORT_EXPOSURE_PCT}%")
                    return False

                # Check correlation risk with existing positions
                existing_tokens = list(self.portfolio.positions.keys())
                if existing_tokens:
                    correlation_risk = self.data_intel.get_portfolio_correlation_risk(
                        token, existing_tokens, hours=24
                    )

                    if correlation_risk['recommendation'] == 'BLOCK':
                        print(f"⚠️ [CORRELATION BLOCKED] {token}")
                        print(f"   Risk Level: {correlation_risk['risk_level']}")
                        print(f"   Max Correlation: {correlation_risk['max_correlation']:.2f}")
                        print(f"   {correlation_risk['warning']}")
                        print(f"   Correlations: {correlation_risk['correlations']}")
                        return False
                    elif correlation_risk['warning']:
                        print(f"⚠️ [CORRELATION WARNING] {token}: {correlation_risk['warning']}")

                # Validate risk-reward ratio (minimum 2:1)
                risk_reward = decision['take_profit_pct'] / decision['stop_loss_pct']
                if risk_reward < 2.0:
                    print(f"[REJECTED] {token} - Poor R:R: {risk_reward:.2f}:1 (minimum 2:1 required)")
                    print(f"   Take Profit: {decision['take_profit_pct']:.1f}% / Stop Loss: {decision['stop_loss_pct']:.1f}%")
                    return False

                # Execute short (SHORT position)
                success = self.portfolio.open_position(
                    token=token,
                    entry_price=price,
                    position_value=position_value,
                    stop_loss_pct=decision['stop_loss_pct'],
                    take_profit_pct=decision['take_profit_pct'],
                    reasoning=decision['reasoning'],
                    position_type='SHORT'
                )

                if success:
                    self.daily_trade_count += 1
                    print(f"[SHORT] {token} - ${position_value:.2f} at ${price:.4f}")

                    # Track the trade for learning
                    self.active_trades[token] = {
                        'entry_time': datetime.now(),
                        'entry_price': price,
                        'position_value': position_value,
                        'position_type': 'SHORT',
                        'decision': decision,
                        'market_context': {
                            'btc_price': self.data_intel.get_current_price('BTC'),
                            'fear_greed': self.data_intel.get_fear_greed_index(),
                            'regime': self.current_regime.get('regime', 'UNKNOWN') if self.current_regime else 'UNKNOWN'
                        }
                    }

                return success

            elif action == 'SELL':
                # Check if we have a position
                position = self.portfolio.get_position(token)
                if position:
                    success = self.portfolio.close_position(
                        token=token,
                        exit_price=price,
                        reasoning=decision['reasoning']
                    )

                    if success:
                        print(f"[SELL] {token} at ${price:.4f}")

                        # Record trade experience for learning
                        if token in self.active_trades:
                            trade_info = self.active_trades[token]
                            position_type = trade_info.get('position_type', 'LONG')

                            # Calculate actual reward (profit/loss percentage) based on position type
                            if position_type == 'LONG':
                                pnl_pct = ((price - trade_info['entry_price']) / trade_info['entry_price']) * 100
                            else:  # SHORT
                                pnl_pct = ((trade_info['entry_price'] - price) / trade_info['entry_price']) * 100

                            # Record the experience
                            self.trade_learner.record_experience(
                                state={
                                    'token': token,
                                    'entry_price': trade_info['entry_price'],
                                    'market_context': trade_info['market_context'],
                                    'decision_confidence': trade_info['decision']['confidence'],
                                    'position_size': trade_info['decision']['position_size'],
                                    'hold_duration': (datetime.now() - trade_info['entry_time']).total_seconds() / 3600  # hours
                                },
                                action=trade_info['decision']['action'],
                                decision=trade_info['decision'],
                                reward=pnl_pct / 100,  # Normalized reward
                                outcome={
                                    'exit_price': price,
                                    'pnl_pct': pnl_pct,
                                    'exit_reason': decision['reasoning']
                                }
                            )

                            # Learn from this experience immediately
                            print(f"[LEARNING] Recording {position_type} experience: {pnl_pct:+.2f}% return")
                            self.trade_learner.learn_from_recent_trades()

                            # Remove from active trades
                            del self.active_trades[token]

                            # Update consecutive losses tracker
                            if pnl_pct < 0:
                                self.consecutive_losses += 1
                            else:
                                self.consecutive_losses = 0

                            # Update daily P&L
                            self.daily_pnl += (pnl_pct / 100) * trade_info['position_value']

                    return success
                else:
                    print(f"[SKIP] No position to sell for {token}")
                    return False

        except Exception as e:
            print(f"[ERROR] Execution failed: {e}")
            return False

    def check_partial_profit_targets(self):
        """
        Check open positions for partial profit taking opportunities
        Strategy: 30% at 1.5x risk | 40% at 2.5x risk | 30% trailing stop
        Works for both LONG and SHORT positions
        """
        for token, position in list(self.portfolio.positions.items()):
            try:
                # Get current price
                current_price = self.portfolio.get_current_price(token)
                if not current_price:
                    continue

                # Get position type (default to LONG for backward compatibility)
                position_type = position.get('position_type', 'LONG')
                entry_price = position['entry_price']

                # Calculate unrealized P&L percentage based on position type
                if position_type == 'LONG':
                    # LONG: Profit when price goes UP
                    pnl_pct = ((current_price - entry_price) / entry_price) * 100
                else:  # SHORT
                    # SHORT: Profit when price goes DOWN
                    pnl_pct = ((entry_price - current_price) / entry_price) * 100

                # Get stop loss percentage for calculating targets
                # For both LONG and SHORT, we stored stop_loss_pct as the original percentage
                stop_loss_pct = position.get('stop_loss_pct', 3.0)

                # Calculate profit targets (same for both LONG and SHORT since we use percentages)
                target_1_pct = stop_loss_pct * 1.5  # 1.5x risk
                target_2_pct = stop_loss_pct * 2.5  # 2.5x risk

                # Track which exits have been taken
                partial_exits = position.get('partial_exits', [])
                remaining_pct = position.get('remaining_pct', 100.0)

                # Target 1: Take 30% profit at 1.5x risk
                if pnl_pct >= target_1_pct and remaining_pct == 100.0:
                    print(f"\n[PROFIT TARGET 1] {token} {position_type} hit {target_1_pct:.1f}% (1.5x risk)")
                    success = self.portfolio.partial_close_position(
                        token=token,
                        exit_percentage=30.0,
                        exit_price=current_price,
                        reasoning=f"Target 1: 1.5x risk ({target_1_pct:.1f}%)"
                    )
                    if success:
                        print(f"  ✓ Took 30% profit | Remaining: 70%")

                # Target 2: Take 40% profit at 2.5x risk
                elif pnl_pct >= target_2_pct and remaining_pct >= 70.0:
                    print(f"\n[PROFIT TARGET 2] {token} {position_type} hit {target_2_pct:.1f}% (2.5x risk)")
                    success = self.portfolio.partial_close_position(
                        token=token,
                        exit_percentage=40.0,
                        exit_price=current_price,
                        reasoning=f"Target 2: 2.5x risk ({target_2_pct:.1f}%)"
                    )
                    if success:
                        print(f"  ✓ Took 40% profit | Remaining: 30%")
                        print(f"  💎 Letting 30% run with trailing stop")

                # Target 3: Trailing stop for final 30% (handled by existing stop-loss logic)
                # The remaining 30% stays in the position and exits via stop-loss or manual SELL

            except Exception as e:
                print(f"[ERROR] Failed to check partial profits for {token}: {e}")
                continue

    def check_and_record_closed_positions(self):
        """Check for positions that were closed automatically and record experiences"""
        current_positions = set(self.portfolio.positions.keys())
        tracked_positions = set(self.active_trades.keys())

        # Find positions that were closed
        closed_positions = tracked_positions - current_positions

        for token in closed_positions:
            if token in self.active_trades:
                trade_info = self.active_trades[token]
                position_type = trade_info.get('position_type', 'LONG')

                # Get the exit price (current market price)
                exit_price = self.data_intel.get_current_price(token)
                if exit_price:
                    # Calculate actual reward based on position type
                    if position_type == 'LONG':
                        pnl_pct = ((exit_price - trade_info['entry_price']) / trade_info['entry_price']) * 100
                    else:  # SHORT
                        pnl_pct = ((trade_info['entry_price'] - exit_price) / trade_info['entry_price']) * 100

                    # Record the experience
                    self.trade_learner.record_experience(
                        state={
                            'token': token,
                            'entry_price': trade_info['entry_price'],
                            'market_context': trade_info['market_context'],
                            'decision_confidence': trade_info['decision']['confidence'],
                            'position_size': trade_info['decision']['position_size'],
                            'hold_duration': (datetime.now() - trade_info['entry_time']).total_seconds() / 3600
                        },
                        action=trade_info['decision']['action'],
                        decision=trade_info['decision'],
                        reward=pnl_pct / 100,
                        outcome={
                            'exit_price': exit_price,
                            'pnl_pct': pnl_pct,
                            'exit_reason': 'AUTO_CLOSE (SL/TP)'
                        }
                    )

                    print(f"[LEARNING] Recording auto-closed {position_type}: {token} ({pnl_pct:+.2f}%)")

                    # Update tracking
                    if pnl_pct < 0:
                        self.consecutive_losses += 1
                    else:
                        self.consecutive_losses = 0

                    self.daily_pnl += (pnl_pct / 100) * trade_info['position_value']

                # Remove from tracking
                del self.active_trades[token]

    def check_circuit_breakers(self) -> bool:
        """Check if any circuit breakers are triggered"""
        # Daily drawdown check
        if self.daily_pnl < -(config.MAX_DAILY_DRAWDOWN_PCT / 100 * config.INITIAL_CAPITAL):
            print(f"[CIRCUIT BREAKER] Daily drawdown exceeded: ${self.daily_pnl:.2f}")
            return True

        # Consecutive losses check
        if self.consecutive_losses >= config.MAX_CONSECUTIVE_LOSSES:
            print(f"[CIRCUIT BREAKER] {self.consecutive_losses} consecutive losses")
            return True

        # Daily trade limit
        if self.daily_trade_count >= config.MAX_DAILY_TRADES:
            print(f"[CIRCUIT BREAKER] Daily trade limit reached: {self.daily_trade_count}")
            return True

        return False

def main():
    """Main entry point"""
    trader = AITrader()

    # Run the trading loop
    try:
        asyncio.run(trader.run_forever())
    except KeyboardInterrupt:
        print("\n[STOP] Trading stopped by user")
    except Exception as e:
        print(f"\n[FATAL] Unexpected error: {e}")
    finally:
        trader.handle_shutdown(None, None)

if __name__ == "__main__":
    main()