"""
AI Trader - Main orchestration with dynamic token discovery
Handles the main loop, Claude decisions, and ensemble verification
"""

import asyncio
import time
import signal
import sys
from contextlib import closing
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import json
import xml.etree.ElementTree as ET
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
    from crypto_ai_trader.macro_intelligence import MacroIntelligence
    from crypto_ai_trader import config
except ImportError:
    # Fall back to local imports (for running directly)
    from data_intelligence import DataIntelligence
    from portfolio_manager import PortfolioManager
    from market_analyzer import MarketAnalyzer
    from ai_optimizer import AIOptimizer
    from trade_learner import TradeLearner
    from macro_intelligence import MacroIntelligence
    import config

# Optional browser modules (safe fallbacks if unavailable)
try:
    from crypto_ai_trader.browser_ai import cleanup_all_browsers
    from crypto_ai_trader.browser_agents.conversation_orchestrator import (
        build_data_orchestrator,
        build_verification_orchestrator,
    )
    from crypto_ai_trader.browser_agents.decision_logger import BrowserDecisionLogger
except ImportError:
    try:
        from browser_ai import cleanup_all_browsers
        from browser_agents.conversation_orchestrator import (
            build_data_orchestrator,
            build_verification_orchestrator,
        )
        from browser_agents.decision_logger import BrowserDecisionLogger
    except ImportError:
        def cleanup_all_browsers():
            return None

        def build_data_orchestrator(*args, **kwargs):
            return None

        def build_verification_orchestrator(*args, **kwargs):
            return None

        class BrowserDecisionLogger:
            def __init__(self, *args, **kwargs):
                pass

            def log(self, *args, **kwargs):
                pass

load_dotenv()

BROWSER_AGENT_PRIMING_PROMPT = """You are an AI crypto trading analyst operating inside a browser chat.

Conversation protocol:
- You will receive an initial quick summary for one token. Reply using a single chat message each turn.
- To request more data, emit one line exactly like:
      REQUEST: sentiment | token=BTC | window=6h
      REQUEST: price | token=BTC | window=24h
  Each REQUEST must specify the token and window as shown.
- After every request you will receive CONTEXT blocks containing the data you asked for.
- When you are ready to decide, respond with EXACTLY one line in this format:
      COMPLETE: decision | action=<BUY/SELL/HOLD/SHORT> | confidence=<0-1> | position_size=<0-1> | stop_loss_pct=<value> | take_profit_pct=<value> | reasoning=<short text>

Rules:
- Actions must be BUY, SELL, HOLD, or SHORT.
- confidence and position_size must be numeric values between 0 and 1.
- stop_loss_pct and take_profit_pct must be numeric percentages (you may omit the % symbol).
- reasoning must be a brief clause (<= 20 words).
- Do NOT add bullet points, markdown, or extra sentences before or after the COMPLETE line.
"""

BROWSER_VERIFIER_PROMPT = """You are a risk officer reviewing AI trading decisions.

Protocol:
1. You will receive the proposed action, confidence, size, stops, and reasoning.
2. Request any additional data you need using:
       REQUEST: sentiment | token=BTC | window=6h
       REQUEST: price | token=BTC | window=24h
3. When ready, respond with:
       COMPLETE: verdict | status=PASS | reason=<one sentence>
       COMPLETE: verdict | status=FAIL | reason=<one sentence>

Rules:
- PASS only when the decision respects risk (liquidity, correlation, cascades).
- FAIL when you detect unacceptable risk and explain why in <= 2 sentences.
- Emit exactly one COMPLETE line with status=PASS or status=FAIL and a concise reason. No extra commentary before or after the line.
- Do not modify the trade parameters; only judge risk suitability.
"""

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

        # Initialize macro intelligence for filtered traditional finance data
        self.macro_intel = MacroIntelligence(self.db_config)

        # Initialize trading interface if enabled
        self.trading_interface = None
        if getattr(config, 'USE_BINANCE_TRADING', False):
            try:
                from crypto_ai_trader.trading_interface import TradingInterface
                paper_trading = getattr(config, 'PAPER_TRADING', True)
                self.trading_interface = TradingInterface(paper_trading=paper_trading)
                if self.trading_interface.test_connection():
                    print(f"[BINANCE] Connected to {'TESTNET' if paper_trading else 'REAL'} trading")
                else:
                    print("[WARNING] Binance connection failed, using simulation only")
                    self.trading_interface = None
            except Exception as e:
                print(f"[WARNING] Could not initialize Binance interface: {e}")
                print("[INFO] Using simulation only")

        # Initialize portfolio manager (with optional trading interface)
        self.portfolio = PortfolioManager(self.db_config, config.INITIAL_CAPITAL, self.trading_interface)

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

        # Describe which data layers should be fetched for dynamic context building
        self.context_layers = self._define_context_layers()

        # Browser utilities
        self.browser_orchestrator = None
        log_dir = getattr(
            config,
            'BROWSER_DECISION_LOG_DIR',
            os.path.join(os.getcwd(), 'logs', 'browser_decisions')
        )
        self.browser_logger = BrowserDecisionLogger(log_dir)
        self.browser_verifier = None

        # Trading state
        self.trading_active = True
        self.last_decision_time = {}
        self.consecutive_losses = 0
        self.daily_trade_count = 0
        self.daily_pnl = 0
        self._last_daily_reset = datetime.now().date()
        self.defi_position_adjustment = 1.0  # DeFi risk-based position adjustment
        self.options_position_adjustment = 1.0  # Options volatility-based position adjustment
        self.price_data_max_age = getattr(config, 'PRICE_DATA_MAX_AGE_MINUTES', 15)
        self.sentiment_data_max_age = getattr(config, 'SENTIMENT_DATA_MAX_AGE_MINUTES', 30)
        self.feed_freshness_limits = getattr(
            config,
            'DATA_FRESHNESS_LIMITS',
            {
                'crypto_ohlcv': 10,
                'twitter_sentiment': 15,
                'order_book_depth': 5,
                'liquidations': 30,
                'open_interest': 60,
                'news_articles': 180,
            },
        )
        self._last_freshness_warning: Optional[str] = None
        self._symbol_check_cache: Dict[str, bool] = {}

        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self.handle_shutdown)
        signal.signal(signal.SIGTERM, self.handle_shutdown)

        print("[AI Trader] Initialization complete")
        print(f"[Settings] Paper Trading: {config.PAPER_TRADING}")
        print(f"[Settings] Initial Capital: ${config.INITIAL_CAPITAL:,.2f}")
        print(f"[Settings] Decision Interval: {config.DECISION_INTERVAL/60:.1f} minutes")
        print()

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
            with closing(psycopg2.connect(
                host=self.db_config['host'],
                port=self.db_config['port'],
                user=self.db_config['user'],
                password=self.db_config['password'],
                database=self.db_config['database']
            )) as conn:
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
        """Main trading loop with dual-cycle architecture driven by config:
        - Fast cycle: Check tactical alerts on config.TACTICAL_MONITOR_INTERVAL cadence
        - Slow cycle: Strategic analysis on config.DECISION_INTERVAL cadence
        """
        def _describe_interval(seconds: int) -> str:
            if seconds < 60:
                return f"{int(seconds)} seconds"
            minutes = seconds / 60
            if float(minutes).is_integer():
                minutes = int(minutes)
                return f"{minutes} minute{'s' if minutes != 1 else ''}"
            return f"{minutes:.1f} minutes"

        base_tactical_interval = max(5, int(getattr(config, 'TACTICAL_MONITOR_INTERVAL', 120)))
        base_strategic_interval = max(60, int(getattr(config, 'DECISION_INTERVAL', 300)))

        # These will be dynamically adjusted based on volatility
        tactical_check_interval = base_tactical_interval
        strategic_interval = base_strategic_interval

        print("\n[START] Beginning AI trading with fast response system...")
        print(f"  • Tactical alerts checked: Every {_describe_interval(tactical_check_interval)}")
        print(f"  • Strategic analysis: Every {_describe_interval(strategic_interval)}")
        print("  • Trades can execute: Within the tactical cadence of critical events!")
        print("Press Ctrl+C to stop gracefully\n")

        # Track when we last ran strategic analysis
        last_strategic_analysis = 0  # Force immediate strategic run on startup

        # Track deferred tactical alerts (70-84% confidence)
        deferred_alerts = []

        while self.trading_active:
            try:
                loop_start = time.time()
                executed_trades = 0
                self._maybe_reset_daily_stats()

                if not self._global_data_is_fresh():
                    await asyncio.sleep(60)
                    continue

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
                        await asyncio.sleep(600)
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
                        await asyncio.sleep(300)
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

                    # Discover active tokens and overlay detector signals
                    active_tokens = self.data_intel.discover_active_tokens(min_activity_hours=24)
                    signal_candidates = self._collect_signal_candidates(limit=20)
                    signal_lookup = {entry['token']: entry for entry in signal_candidates}

                    if not active_tokens and not signal_candidates:
                        print("[WARNING] No active tokens or signals found for strategic analysis")
                    else:
                        print(f"[SCAN] Signals: {len(signal_candidates)} | Active tokens: {len(active_tokens)}")

                        trending = self.data_intel.get_trending_tokens(min_spike=2.0)
                        trending_tokens = [t['token'] for t in trending]

                        priority_tokens: List[str] = []
                        priority_tokens.extend([entry['token'] for entry in signal_candidates])
                        priority_tokens.extend([t for t in trending_tokens if t not in priority_tokens])
                        priority_tokens.extend([t for t in active_tokens if t not in priority_tokens])

                        # Check circuit breakers
                        if not self.check_circuit_breakers():
                            # Check DeFi TVL risk for position sizing
                            defi_risk = self.data_intel.check_defi_risk()
                            if defi_risk:
                                self.defi_position_adjustment = defi_risk.get('position_adjustment', 1.0)
                                risk_level = defi_risk.get('risk_level', 'UNKNOWN')
                                if risk_level != 'UNKNOWN':
                                    print(f"[DEFI RISK] {risk_level} - Position adjustment: {self.defi_position_adjustment:.0%}")
                                    if risk_level == 'HIGH':
                                        print("[DEFI RISK] Reducing all positions by 30-50% due to DeFi capital exodus")

                            # Check Options Volatility risk for position sizing
                            options_risk = self.data_intel.check_options_risk()
                            if options_risk:
                                self.options_position_adjustment = options_risk.get('position_adjustment', 1.0)
                                vol_regime = options_risk.get('volatility_regime', 'UNKNOWN')
                                if vol_regime != 'UNKNOWN':
                                    btc_iv = options_risk.get('btc_iv', 0)
                                    eth_iv = options_risk.get('eth_iv', 0)
                                    print(f"[OPTIONS VOL] {vol_regime} - BTC IV: {btc_iv:.0f}%, ETH IV: {eth_iv:.0f}%")
                                    print(f"[OPTIONS VOL] Position adjustment: {self.options_position_adjustment:.0%}")
                                    if vol_regime == 'EXTREME':
                                        print("[OPTIONS VOL] Extreme volatility detected - halving all position sizes")
                                    warnings = options_risk.get('warnings', [])
                                    for warning in warnings:
                                        print(f"[OPTIONS VOL] Warning: {warning}")

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

                                    # ==== NEW: Check data-driven signals BEFORE expensive AI ====
                                    quick_signal = None
                                    signal_source = None

                                    # 1. Check order book for immediate opportunity
                                    order_signal = self.check_order_book_opportunity(token)
                                    if order_signal:
                                        quick_signal = order_signal
                                        signal_source = "ORDER_BOOK"

                                    # 2. Check funding rate for mean reversion
                                    if not quick_signal:
                                        funding_signal = self.check_funding_rate_opportunity(token)
                                        if funding_signal:
                                            quick_signal = funding_signal
                                            signal_source = "FUNDING_RATE"

                                    # 3. Check exchange flows for whale movements
                                    if not quick_signal:
                                        flow_signal = self.check_exchange_flow_opportunity(token)
                                        if flow_signal:
                                            quick_signal = flow_signal
                                            signal_source = "EXCHANGE_FLOW"

                                    # If we found a data-driven signal, create quick decision
                                    if quick_signal and signal_source:
                                        print(f"[DATA SIGNAL] {token}: {quick_signal} from {signal_source}")
                                        opportunities.append({
                                            'token': token,
                                            'action': quick_signal,
                                            'confidence': 0.75,  # High confidence for data-driven signals
                                            'position_size': 0.02,  # Conservative size
                                            'stop_loss_pct': 0.03,
                                            'take_profit_pct': 0.06,
                                            'reasoning': f"Data-driven signal from {signal_source}",
                                            'timestamp': datetime.now().isoformat(),
                                            'source': signal_source.lower()
                                        })
                                        continue  # Skip expensive AI analysis

                                    # No quick signal, proceed with AI analysis
                                    signal_meta = signal_lookup.get(token)
                                    signal = await self.analyze_token(token, summary, signal_meta)
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
                    next_minutes = strategic_interval / 60
                    time_label = f"{next_minutes:.1f} minutes" if not next_minutes.is_integer() else f"{int(next_minutes)} minute{'s' if next_minutes != 1 else ''}"
                    print(f"[STRATEGIC] Next strategic analysis in {time_label}")

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
                next_tactical_minutes = tactical_check_interval / 60
                if next_tactical_minutes < 1:
                    tactical_label = f"{tactical_check_interval} seconds"
                elif next_tactical_minutes.is_integer():
                    tactical_label = f"{int(next_tactical_minutes)} minute{'s' if next_tactical_minutes != 1 else ''}"
                else:
                    tactical_label = f"{next_tactical_minutes:.1f} minutes"
                print(f"  Next tactical check: {tactical_label}")
                if time_since_strategic < strategic_interval:
                    mins_until_strategic = (strategic_interval - time_since_strategic) / 60
                    print(f"  Next strategic analysis: {mins_until_strategic:.1f} minutes")

                # ADAPTIVE TIMING: Adjust intervals based on market volatility
                tactical_check_interval = self.get_adaptive_check_interval(base_tactical_interval)
                strategic_interval = self.get_adaptive_check_interval(base_strategic_interval)

                # CRITICAL: Sleep strictly according to tactical cadence for responsiveness!
                wait_time = max(1, tactical_check_interval - cycle_time)
                print(f"\n[WAIT] Checking for alerts again in {wait_time:.0f} seconds...")
                await asyncio.sleep(wait_time)

            except Exception as e:
                print(f"[ERROR] Trading loop error: {e}")
                await asyncio.sleep(60)

    async def analyze_token(self, token: str, quick_summary: Dict, signal_meta: Optional[Dict] = None) -> Optional[Dict]:
        """
        Analyze a token and generate a trading signal using the browser AI agent.
        """
        try:
            if not self._token_data_is_fresh(token):
                return None

            # Build market context
            force_deep = signal_meta is not None
            context = await self.build_market_context(token, quick_summary, force_deep=force_deep)
            if signal_meta:
                context['signal'] = signal_meta

            # Generate decision with the browser-based Claude agent
            decision = await self.get_claude_decision(token, context)

            if not decision:
                return None

            decision['market_context'] = context
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
                'position_size': 0.03 * self.defi_position_adjustment * self.options_position_adjustment,  # Apply DeFi & Options risk adjustment
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

    def check_order_book_opportunity(self, token: str) -> Optional[str]:
        """Check if order book shows immediate trading opportunity"""
        try:
            order_book = self.data_intel.get_order_book_intelligence(token)
            if not order_book or not order_book.get('has_data'):
                return None

            pressure = order_book.get('pressure', {})
            spread = order_book.get('spread', {})

            # Strong buy signal from order book
            if pressure.get('signal') == 'BUYERS_DOMINATING' and spread.get('quality') in ['EXCELLENT', 'GOOD']:
                if pressure.get('imbalance', 0) > 0.3:  # Strong imbalance
                    print(f"[ORDER BOOK] {token}: Strong BUY pressure detected (imbalance: {pressure['imbalance']:.2f})")
                    return 'BUY'

            # Strong sell signal from order book
            elif pressure.get('signal') == 'SELLERS_DOMINATING' and spread.get('quality') in ['EXCELLENT', 'GOOD']:
                if pressure.get('imbalance', 0) < -0.3:  # Strong negative imbalance
                    print(f"[ORDER BOOK] {token}: Strong SELL pressure detected (imbalance: {pressure['imbalance']:.2f})")
                    return 'SELL'

            return None
        except Exception as e:
            print(f"[WARNING] Order book check failed for {token}: {e}")
            return None

    def check_funding_rate_opportunity(self, token: str) -> Optional[str]:
        """Check for funding rate mean reversion opportunities"""
        try:
            funding_rate = self.data_intel.get_latest_funding_rate(token)
            if funding_rate is None:
                return None

            # Extreme positive funding = overleveraged longs, likely to drop
            if funding_rate > 0.001:  # 0.1% per 8h = 10%+ APR
                print(f"[FUNDING] {token}: Extreme positive funding {funding_rate:.4f} - SHORT opportunity")
                return 'SHORT'

            # Extreme negative funding = overleveraged shorts, likely to bounce
            elif funding_rate < -0.0005:  # -0.05% per 8h
                print(f"[FUNDING] {token}: Extreme negative funding {funding_rate:.4f} - LONG opportunity")
                return 'BUY'

            return None
        except Exception as e:
            print(f"[WARNING] Funding rate check failed for {token}: {e}")
            return None

    def check_exchange_flow_opportunity(self, token: str) -> Optional[str]:
        """Check if whale exchange flows suggest opportunity"""
        try:
            flows = self.data_intel.get_exchange_flow_signals(hours=6)
            for flow in flows:
                if flow['token'] != token:
                    continue

                # Large outflows = bullish (whales accumulating)
                if flow['signal'] == 'BULLISH' and flow['strength'] > 0.7:
                    print(f"[EXCHANGE FLOW] {token}: Large outflows detected ${flow['total_value']:,.0f} - BULLISH")
                    return 'BUY'

                # Large inflows = bearish (whales preparing to sell)
                elif flow['signal'] == 'BEARISH' and flow['strength'] > 0.7:
                    print(f"[EXCHANGE FLOW] {token}: Large inflows detected ${flow['total_value']:,.0f} - BEARISH")
                    return 'SELL'

            return None
        except Exception as e:
            print(f"[WARNING] Exchange flow check failed for {token}: {e}")
            return None

    def get_adaptive_check_interval(self, base_interval: int) -> int:
        """Adjust check interval based on market volatility"""
        try:
            volatility = self.data_intel.get_market_volatility(hours=1)

            # High volatility = check more often
            if volatility > 0.03:  # 3% hourly volatility
                adjusted = int(base_interval * 0.5)
                print(f"[ADAPTIVE] High volatility ({volatility:.2%}) - checking every {adjusted}s")
                return max(30, adjusted)  # Minimum 30 seconds

            # Low volatility = check less often
            elif volatility < 0.01:  # 1% hourly volatility
                adjusted = int(base_interval * 1.5)
                print(f"[ADAPTIVE] Low volatility ({volatility:.2%}) - checking every {adjusted}s")
                return min(600, adjusted)  # Maximum 10 minutes

            # Normal volatility
            return base_interval

        except Exception as e:
            print(f"[WARNING] Failed to get adaptive interval: {e}")
            return base_interval

    async def build_market_context(self, token: str, quick_summary: Dict, force_deep: bool = False) -> Dict:
        """
        Build comprehensive market context for AI decision.
        Starts with quick summary, then dynamically fetches deeper data layers based
        on activity, liquidity, or forced analysis requests.
        """
        context = {
            'token': token,
            'timestamp': datetime.now().isoformat(),
            'quick_summary': quick_summary
        }

        fetched_layers: List[str] = []
        for layer in self.context_layers:
            try:
                if not layer['condition'](quick_summary, force_deep):
                    continue
                data = layer['fetcher'](token, quick_summary)
                if data is not None:
                    context[layer['name']] = data
                    fetched_layers.append(layer['name'])
            except Exception as exc:
                print(f"[CONTEXT] Failed to load {layer['name']} for {token}: {exc}")

        if fetched_layers:
            context['data_layers'] = fetched_layers

        # Add portfolio context
        context['portfolio'] = {
            'current_positions': self.portfolio.get_positions(),
            'cash_available': self.portfolio.get_available_cash(),
            'total_value': self.portfolio.get_total_value(),
            'daily_pnl': self.daily_pnl,
            'open_position_count': len(self.portfolio.get_positions())
        }

        return context

    def _maybe_reset_daily_stats(self, now: Optional[datetime] = None) -> None:
        """Reset daily trade counters when the calendar day changes."""
        now = now or datetime.now()
        current_date = now.date()
        if current_date != self._last_daily_reset:
            self.daily_trade_count = 0
            self.daily_pnl = 0
            self._last_daily_reset = current_date
            print(f"[RESET] Daily trading stats reset for {current_date.isoformat()}")

    def _global_data_is_fresh(self) -> bool:
        """
        Ensure critical feeds are being updated frequently enough.
        """
        if not self.feed_freshness_limits:
            return True

        freshness = self.data_intel.get_feed_freshness(self.feed_freshness_limits.keys())
        stale = []
        for feed, limit in self.feed_freshness_limits.items():
            age = freshness.get(feed)
            if age is None:
                stale.append(f"{feed}: missing")
            elif age > limit:
                stale.append(f"{feed}: {age:.1f}m (limit {limit}m)")

        if stale:
            message = "; ".join(stale)
            if message != self._last_freshness_warning:
                print(f"[DATA GUARD] Waiting for fresh data – {message}")
                self._last_freshness_warning = message
            return False

        self._last_freshness_warning = None
        return True

    def _token_data_is_fresh(self, token: str) -> bool:
        """
        Ensure per-token feeds are recent enough before executing a trade.
        """
        limits: Dict[str, int] = {}
        # Apply stricter per-token limits where applicable
        limits['crypto_ohlcv'] = min(
            self.price_data_max_age,
            self.feed_freshness_limits.get('crypto_ohlcv', self.price_data_max_age)
        )
        limits['twitter_sentiment'] = min(
            self.sentiment_data_max_age,
            self.feed_freshness_limits.get('twitter_sentiment', self.sentiment_data_max_age)
        )
        # Include any other global limits that are token-specific
        for feed in ['order_book_depth', 'liquidations', 'open_interest']:
            if feed in self.feed_freshness_limits:
                limits[feed] = self.feed_freshness_limits[feed]

        ages = self.data_intel.get_token_freshness(token, limits)
        stale = []
        for feed, limit in limits.items():
            age = ages.get(feed)
            if age is None:
                stale.append(f"{feed}: missing")
            elif age > limit:
                stale.append(f"{feed}: {age:.1f}m (limit {limit}m)")

        if stale:
            print(f"[DATA GUARD] Skipping {token} – {'; '.join(stale)}")
            return False
        return True

    def _symbol_is_tradeable(self, token: str) -> bool:
        """
        Binance-only eligibility check; cached to reduce API calls.
        """
        if token in self._symbol_check_cache:
            return self._symbol_check_cache[token]

        if not self.trading_interface:
            # If no live interface, allow simulation but log once
            self._symbol_check_cache[token] = True
            return True

        ok = self.trading_interface.is_symbol_tradeable(token)
        self._symbol_check_cache[token] = ok
        return ok

    def _define_context_layers(self) -> List[Dict[str, Any]]:
        """Describe optional data layers for market context construction."""
        def high_activity(quick: Dict[str, Any]) -> bool:
            return (
                quick.get('tweets_1h', 0) > 20
                or abs(quick.get('price_change_1h', 0) or 0) > 3
                or quick.get('volume_spike', 0) > 2
            )

        return [
            {
                'name': 'sentiment',
                'condition': lambda quick, force: force or quick.get('tweets_1h', 0) > 0,
                'fetcher': lambda token, quick: self.data_intel.get_sentiment_summary(token, hours=6),
            },
            {
                'name': 'price_data',
                'condition': lambda quick, force: force or abs(quick.get('price_change_1h', 0) or 0) >= 1
                    or quick.get('volume_spike', 0) >= 1.5,
                'fetcher': lambda token, quick: self.data_intel.get_price_history(token, hours=24),
            },
            {
                'name': 'market_metrics',
                'condition': lambda quick, force: force or abs(quick.get('price_change_1h', 0) or 0) >= 0.3,
                'fetcher': lambda token, quick: self.data_intel.get_market_metrics(token),
            },
            {
                'name': 'order_book_intel',
                'condition': lambda quick, force: True,
                'fetcher': lambda token, quick: self.data_intel.get_order_book_intelligence(token),
            },
            {
                'name': 'fear_greed',
                'condition': lambda quick, force: True,
                'fetcher': lambda token, quick: self.data_intel.get_fear_greed_index(),
            },
            {
                'name': 'whale_activity',
                'condition': lambda quick, force: force or quick.get('tweets_1h', 0) > 5,
                'fetcher': lambda token, quick: self._fetch_whale_activity(token),
            },
            {
                'name': 'liquidation_cascade',
                'condition': lambda quick, force: force or abs(quick.get('price_change_1h', 0) or 0) >= 2,
                'fetcher': lambda token, quick: self.data_intel.get_liquidation_cascade_analysis(token),
            },
            {
                'name': 'historical_patterns',
                'condition': lambda quick, force: force or high_activity(quick),
                'fetcher': lambda token, quick: self.data_intel.find_similar_historical_patterns(token, lookback_days=30),
            },
            {
                'name': 'stablecoin_metrics',
                'condition': lambda quick, force: True,
                'fetcher': lambda token, quick: self.data_intel.get_stablecoin_metrics(),
            },
            {
                'name': 'smart_money_flows',
                'condition': lambda quick, force: force or quick.get('volume_spike', 0) >= 1.8,
                'fetcher': lambda token, quick: self.data_intel.get_smart_money_flows(token, hours=6),
            },
            {
                'name': 'dex_metrics',
                'condition': lambda quick, force: force or quick.get('volume_spike', 0) >= 1.2,
                'fetcher': lambda token, quick: self.data_intel.get_dex_liquidity_metrics(token),
            },
            {
                'name': 'volume_profile',
                'condition': lambda quick, force: force or quick.get('volume_spike', 0) >= 1.0,
                'fetcher': lambda token, quick: self.data_intel.get_volume_profile(token, hours=24),
            },
            {
                'name': 'defi_risk',
                'condition': lambda quick, force: True,  # Always include DeFi risk
                'fetcher': lambda token, quick: self.data_intel.check_defi_risk(),
            },
            {
                'name': 'options_volatility',
                'condition': lambda quick, force: True,  # Always include options vol
                'fetcher': lambda token, quick: self.data_intel.check_options_risk(),
            },
            {
                'name': 'macro_intelligence',
                'condition': lambda quick, force: True,  # Always check macro context
                'fetcher': lambda token, quick: self.macro_intel.get_crypto_macro_context(),
            },
            {
                'name': 'bridge_flows',
                'condition': lambda quick, force: True,  # Always check L2 rotation
                'fetcher': lambda token, quick: self.data_intel.check_l2_rotation(token),
            },
        ]

    def _fetch_whale_activity(self, token: str) -> List[Dict[str, Any]]:
        whale_flows = self.data_intel.get_whale_movements(hours=3) or []
        return [w for w in whale_flows if w.get('token') == token]

    def _token_data_is_fresh(self, token: str) -> bool:
        """
        Ensure we only analyze tokens with recently updated DB records.
        """
        freshness = self.data_intel.get_token_data_freshness(token) or {}
        stale_reasons = []

        price_age = freshness.get('price_minutes')
        if price_age is None:
            stale_reasons.append("missing price data")
        elif price_age > self.price_data_max_age:
            stale_reasons.append(
                f"price data {price_age:.1f}m old (> {self.price_data_max_age}m)"
            )

        sentiment_age = freshness.get('sentiment_minutes')
        if sentiment_age is None:
            stale_reasons.append("missing sentiment data")
        elif sentiment_age > self.sentiment_data_max_age:
            stale_reasons.append(
                f"sentiment data {sentiment_age:.1f}m old (> {self.sentiment_data_max_age}m)"
            )

        if stale_reasons:
            reasons = "; ".join(stale_reasons)
            print(f"[DATA GUARD] Skipping {token}: {reasons}")
            return False

        return True

    def _collect_signal_candidates(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Retrieve prioritized signals from data intelligence, ensuring unique tokens.
        """
        signals = self.data_intel.get_signal_candidates(limit=limit) or []
        seen = set()
        ordered: List[Dict[str, Any]] = []
        for entry in signals:
            token = entry.get('token')
            if not token or token in seen:
                continue
            ordered.append(entry)
            seen.add(token)
        return ordered

    def _get_browser_orchestrator(self):
        if self.browser_orchestrator:
            return self.browser_orchestrator

        provider = getattr(config, 'BROWSER_AI_PROVIDER', 'claude')
        session_dir = getattr(config, 'BROWSER_SESSION_DIR', None)
        priming_prompt = getattr(
            config,
            'BROWSER_AGENT_PRIMING_PROMPT',
            BROWSER_AGENT_PRIMING_PROMPT
        )

        self.browser_orchestrator = build_data_orchestrator(
            data_intelligence=self.data_intel,
            provider=provider,
            priming_prompt=priming_prompt,
            session_dir=session_dir
        )
        return self.browser_orchestrator

    def _build_browser_initial_prompt(self, token: str, context: Dict) -> Optional[str]:
        quick = context.get('quick_summary') or self.data_intel.get_quick_summary(token)
        if not quick:
            return None

        def pct(value: Optional[float], digits: int = 2) -> str:
            if value is None:
                return "n/a"
            return f"{value:+.{digits}f}%"

        def fmt(value: Optional[float]) -> str:
            if value is None:
                return "n/a"
            return f"{value:,.2f}"

        sections: List[str] = []

        signal = context.get('signal')
        if signal:
            payload = signal.get('payload', {})
            reasons = ", ".join(signal.get('reasons', [])) or "detector"
            sections.append(
                "SIGNAL SUMMARY:\n"
                f"- Token: {token}\n"
                f"- Reasons: {reasons}\n"
                f"- Detector confidence: {signal.get('confidence', 0):.2f}\n"
                f"- Payload: {json.dumps(payload, default=str)[:800]}"
            )

        regime = self.current_regime.get('regime') if self.current_regime else 'UNKNOWN'
        strategy = self.current_regime.get('recommended_strategy') if self.current_regime else ''
        sections.append(
            "MARKET SNAPSHOT:\n"
            f"- Price: ${quick.get('price', 0):,.2f}\n"
            f"- 1h Change: {pct(quick.get('price_change_1h'))}\n"
            f"- Tweets (1h): {quick.get('tweets_1h', 0)}\n"
            f"- Sentiment (1h): {quick.get('sentiment_1h', 0):+.3f}\n"
            f"- Volume spike: {quick.get('volume_spike', 0):.2f}x\n"
            f"- Regime: {regime} {('('+strategy+')') if strategy else ''}"
        )

        price_data = context.get('price_data')
        if price_data and price_data.get('has_data'):
            sections.append(
                "PRICE ACTION (24H):\n"
                f"- Change: {pct(price_data.get('price_change_24h'))}\n"
                f"- Range: ${price_data.get('low_24h', 0):,.2f} → ${price_data.get('high_24h', 0):,.2f}\n"
                f"- Volatility: {pct(price_data.get('volatility'))}\n"
                f"- Volume: {fmt(price_data.get('volume_24h'))}"
            )

        volume_profile = context.get('volume_profile')
        if volume_profile and volume_profile.get('has_data'):
            sections.append(
                "VOLUME PROFILE:\n"
                f"- Total ({volume_profile.get('window_hours')}h): {fmt(volume_profile.get('total_volume'))}\n"
                f"- Recent avg ({volume_profile.get('recent_window_hours')}h): "
                f"{fmt(volume_profile.get('recent_avg_volume'))} "
                f"({volume_profile.get('volume_ratio', 1):.2f}x baseline)"
            )

        sentiment = context.get('sentiment')
        if sentiment and sentiment.get('has_data', True):
            sections.append(
                "SENTIMENT (6H):\n"
                f"- Tweets: {sentiment.get('tweet_count', 0)}\n"
                f"- Avg: {sentiment.get('avg_sentiment', 0):+.3f} "
                f"(weighted {sentiment.get('avg_weighted', 0):+.3f})\n"
                f"- Whale tweets: {sentiment.get('whale_tweets', 0)}\n"
                f"- Momentum: {sentiment.get('momentum_score', 0):+.3f}"
            )

        order_book = context.get('order_book_intel')
        if order_book and order_book.get('has_data'):
            spread = order_book.get('spread', {}).get('percentage')
            pressure = order_book.get('pressure', {})
            sections.append(
                "ORDER BOOK:\n"
                f"- Spread: {spread if spread is not None else 'n/a'}%\n"
                f"- Recommendation: {order_book.get('recommendation')}\n"
                f"- Pressure: {pressure.get('direction')} ({pressure.get('signal')})"
            )

        smart_money = context.get('smart_money_flows') or []
        if smart_money:
            flows = smart_money[:3]
            flow_lines = [
                f"    • {flow.get('source', 'exchange')} {flow.get('direction', '')} ${flow.get('notional_usd', 0):,.0f}"
                for flow in flows
            ]
            sections.append("SMART MONEY FLOWS:\n" + "\n".join(flow_lines))

        whale_activity = context.get('whale_activity') or []
        if whale_activity:
            whales = whale_activity[:3]
            whale_lines = [
                f"    • {w.get('address', 'wallet')} {w.get('action', '')} {w.get('size', 'n/a')}"
                for w in whales
            ]
            sections.append("WHALE ACTIVITY:\n" + "\n".join(whale_lines))

        liquidation = context.get('liquidation_cascade')
        if liquidation:
            sections.append(
                "LIQUIDATION RISK:\n"
                f"- Status: {liquidation.get('status', 'n/a')}\n"
                f"- Score: {liquidation.get('risk_score', 'n/a')}\n"
                f"- Recommendation: {liquidation.get('recommendation', 'n/a')}"
            )

        portfolio = context.get('portfolio', {})
        positions = portfolio.get('current_positions', {})
        exposure_summary = ", ".join(
            f"{sym}:{pos.get('position_value', 0):,.0f}"
            for sym, pos in list(positions.items())[:5]
        ) or "none"
        sections.append(
            "PORTFOLIO:\n"
            f"- Cash: ${portfolio.get('cash_available', 0):,.0f}\n"
            f"- Total value: ${portfolio.get('total_value', 0):,.0f}\n"
            f"- Open positions: {len(positions)} ({exposure_summary})"
        )

        return "\n\n".join(sections)

    def _get_browser_verifier(self):
        if self.browser_verifier:
            return self.browser_verifier

        provider = getattr(
            config,
            'BROWSER_VERIFIER_PROVIDER',
            getattr(config, 'BROWSER_AI_PROVIDER', 'claude')
        )
        session_dir = getattr(
            config,
            'BROWSER_VERIFIER_SESSION_DIR',
            getattr(config, 'BROWSER_SESSION_DIR', None)
        )
        priming_prompt = getattr(
            config,
            'BROWSER_VERIFIER_PRIMING_PROMPT',
            BROWSER_VERIFIER_PROMPT
        )

        self.browser_verifier = build_verification_orchestrator(
            data_intelligence=self.data_intel,
            provider=provider,
            priming_prompt=priming_prompt,
            session_dir=session_dir
        )
        return self.browser_verifier

    def _build_verifier_initial_prompt(self, token: str, decision: Dict, context: Optional[Dict]) -> str:
        quick = None
        if context and 'quick_summary' in context:
            quick = context['quick_summary']
        if not quick:
            quick = self.data_intel.get_quick_summary(token) or {}

        exposures = []
        for sym, pos in self.portfolio.positions.items():
            exposures.append(
                f"{sym}: ${pos['position_value']:.2f} ({pos.get('position_type', 'LONG')})"
            )

        lines = [
            "DECISION SUMMARY:",
            f"- Token: {token}",
            f"- Action: {decision['action']}",
            f"- Confidence: {decision['confidence']:.2f}",
            f"- Position Size: {decision['position_size']*100:.2f}%",
            f"- Stop Loss: {decision['stop_loss_pct']:.2f}%",
            f"- Take Profit: {decision['take_profit_pct']:.2f}%",
            f"- Reasoning: {decision['reasoning']}",
            "",
            "MARKET SNAPSHOT:",
            f"- Price: ${quick.get('price', 0):,.4f}",
            f"- 1h Change: {quick.get('price_change_1h', 0):+.2f}%",
            f"- Sentiment(1h): {quick.get('sentiment_1h', 0):+.3f}",
            f"- Volume Spike: {quick.get('volume_spike', 0):.2f}x",
            "",
            "PORTFOLIO EXPOSURE:",
            f"- Open positions: {len(exposures)}",
            f"- Details: {', '.join(exposures) if exposures else 'None'}",
            f"- Cash Available: ${self.portfolio.get_available_cash():,.2f}",
        ]

        return "\n".join(lines)

    def verify_browser_decision(self, token: str, decision: Dict, context: Optional[Dict]) -> bool:
        if not getattr(config, 'ENABLE_BROWSER_VERIFIER', True):
            return True

        min_conf = getattr(config, 'BROWSER_VERIFIER_MIN_CONFIDENCE', 0.7)
        if decision.get('confidence', 0) < min_conf:
            return True

        try:
            orchestrator = self._get_browser_verifier()
            prompt = self._build_verifier_initial_prompt(token, decision, context)
            result = orchestrator.run(initial_prompt=prompt)
        except Exception as e:
            print(f"[VERIFIER] Error running browser verifier: {e}")
            return False

        completion = result.completion
        if not completion:
            print("[VERIFIER] No verdict returned; blocking trade.")
            return False

        params = {k.lower(): v for k, v in completion.params.items()}
        status = params.get('status', '').upper() or completion.name.upper()
        reason = params.get('reason') or completion.raw

        decision['verifier'] = {
            'status': status,
            'reason': reason,
            'transcript': result.transcript
        }

        if status != 'PASS':
            print(f"[VERIFIER] {token} blocked: {reason}")
            return False

        print(f"[VERIFIER] {token} approved: {reason}")
        return True

    def get_browser_agent_decision(self, token: str, context: Dict) -> Optional[Dict]:
        try:
            orchestrator = self._get_browser_orchestrator()
            initial_prompt = self._build_browser_initial_prompt(token, context)
            if not initial_prompt:
                print(f"[BROWSER AGENT] No quick summary available for {token}")
                return None

            result = orchestrator.run(initial_prompt=initial_prompt)
        except Exception as e:
            print(f"[BROWSER AGENT] Error running browser orchestrator: {e}")
            return None

        completion = result.completion
        if not completion:
            print(f"[BROWSER AGENT] No completion command returned for {token}")
            return None

        params = {k.lower(): v for k, v in completion.params.items()}
        action = params.get('action')
        if not action:
            print(f"[BROWSER AGENT] Missing action in completion for {token}")
            return None
        action = action.upper()

        def _safe_float(value: Optional[str], default: float) -> float:
            if value is None:
                return default
            try:
                return float(value)
            except (TypeError, ValueError):
                return default

        confidence = _safe_float(params.get('confidence'), 0.6)
        confidence = max(0.0, min(1.0, confidence))

        size_default = min(0.02, config.MAX_POSITION_SIZE_PCT / 100)
        size_value = params.get('size') or params.get('size_pct') or params.get('position_size')
        position_size = _safe_float(size_value, size_default)
        if position_size > 1:
            position_size /= 100

        # Apply DeFi and Options risk adjustments to position size
        position_size = position_size * self.defi_position_adjustment * self.options_position_adjustment

        stop_value = params.get('stop') or params.get('stop_loss')
        stop_loss_pct = _safe_float(stop_value, config.DEFAULT_STOP_LOSS_PCT)

        take_value = params.get('take') or params.get('take_profit')
        take_profit_pct = _safe_float(take_value, config.DEFAULT_TAKE_PROFIT_PCT)

        reasoning = params.get('reasoning') or completion.raw

        decision = {
            'token': token,
            'action': action,
            'confidence': confidence,
            'position_size': position_size,
            'stop_loss_pct': stop_loss_pct,
            'take_profit_pct': take_profit_pct,
            'reasoning': reasoning,
            'timestamp': datetime.now().isoformat(),
            'source': 'browser_agent',
            'browser_transcript': result.transcript
        }
        self._log_browser_decision(decision)
        return decision

    def _log_browser_decision(self, decision: Dict) -> None:
        try:
            self.browser_logger.log(decision)
        except Exception as e:
            print(f"[BROWSER AGENT] Failed to log decision: {e}")

    async def get_claude_decision(self, token: str, context: Dict) -> Optional[Dict]:
        """Generate trading decision using the browser-based agent only."""
        decision = None
        try:
            if config.USE_BROWSER_AI:
                decision = self.get_browser_agent_decision(token, context)
            else:
                print("[BROWSER AGENT] Browser AI disabled in config; cannot create decision.")
        except Exception as e:
            print(f"[BROWSER AGENT] Error retrieving decision: {e}")
            decision = None

        if not decision:
            print(f"[BROWSER AGENT] No decision returned for {token}")
            return None

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

            original_confidence = decision['confidence']
            original_size = decision['position_size']

            decision['confidence'] = max(0.0, min(1.0,
                decision['confidence'] + learned_adjustment['confidence_modifier']))

            decision['position_size'] = max(0.01, min(0.05,
                decision['position_size'] * learned_adjustment['position_size_modifier']))

            if learned_adjustment.get('pattern_type'):
                decision['reasoning'] += f" | LEARNED: {learned_adjustment['pattern_type']} pattern detected"

            if learned_adjustment.get('override_action'):
                print(f"[LEARNING] Overriding action from {decision['action']} to {learned_adjustment['override_action']}")
                decision['action'] = learned_adjustment['override_action']
                decision['reasoning'] += f" | OVERRIDE: {learned_adjustment.get('override_reason', '')}"

            if original_confidence != decision['confidence'] or original_size != decision['position_size']:
                print(f"[LEARNING] Adjusted: Confidence {original_confidence:.2f} -> {decision['confidence']:.2f}, Size {original_size:.2f} -> {decision['position_size']:.2f}")

        print(f"[AI DECISION] {token}: {decision['action']} (confidence: {decision['confidence']:.2f})")

        model_name = decision.get('source', 'browser_agent')
        self.ai_optimizer.track_decision(
            model=model_name,
            token=token,
            decision=decision,
            outcome=None  # Will be updated when position closes
        )

        return decision

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
            min_confidence = config.MIN_DECISION_CONFIDENCE
            if self.current_regime:
                regime_thresholds = self.current_regime.get('thresholds', {})
                min_confidence = regime_thresholds.get('entry_confidence', config.MIN_DECISION_CONFIDENCE)

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

            # Enforce Binance-eligibility (for live/paper aligned with Binance)
            if not self._symbol_is_tradeable(token):
                return False

            # Enforce per-token data freshness before executing
            if not self._token_data_is_fresh(token):
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

                if getattr(config, 'ENABLE_BROWSER_VERIFIER', True):
                    context = decision.get('market_context')
                    if not self.verify_browser_decision(token, decision, context):
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

                if getattr(config, 'ENABLE_BROWSER_VERIFIER', True):
                    context = decision.get('market_context')
                    if not self.verify_browser_decision(token, decision, context):
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

                # TIME-BASED EXIT: Close stagnant positions after 48 hours
                if position.get('entry_time'):
                    position_age_hours = (datetime.now() - position['entry_time']).total_seconds() / 3600
                    if position_age_hours > 48 and abs(pnl_pct) < 2.0:
                        print(f"\n[STAGNANT EXIT] {token} held {position_age_hours:.1f}h with {pnl_pct:+.2f}% return")
                        self.portfolio.close_position(
                            token=token,
                            exit_price=current_price,
                            reasoning=f"Time-based exit: Stagnant after {position_age_hours:.0f} hours"
                        )
                        print(f"  ✓ Closed stagnant position to free capital")

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
