"""
PJX AI Trading System - Main Loop
Orchestrates all components: data -> AI decision -> risk validation -> paper trading
Simple, robust, high-quality design for profitable crypto trading
"""

import time
import psycopg2
from datetime import datetime, timedelta
from typing import Dict, Optional
import traceback
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import all components
import config
from data_aggregator import format_market_summary
from claude_engine import ClaudeEngine
from ensemble_verifier import EnsembleVerifier
from risk_manager import RiskManager
from paper_trading import PaperTradingEngine


class TradingSystem:
    """Main trading system orchestrator"""

    def __init__(self):
        """Initialize all components"""
        print("\n" + "="*70)
        print("PJX AI TRADING SYSTEM - INITIALIZING")
        print("="*70)

        # Validate configuration
        if not config.validate_config():
            raise ValueError("Configuration validation failed - check .env file")

        # Initialize components
        try:
            print("\n[1/5] Initializing Claude Engine...")
            self.claude_engine = ClaudeEngine()

            if config.ENABLE_TIER2_VERIFICATION:
                print("[2/5] Initializing Ensemble Verifier...")
                self.ensemble_verifier = EnsembleVerifier()
            else:
                print("[2/5] Ensemble Verifier disabled")
                self.ensemble_verifier = None

            print("[3/5] Initializing Risk Manager...")
            self.risk_manager = RiskManager()

            print("[4/5] Initializing Paper Trading Engine...")
            self.paper_trading = PaperTradingEngine()

            print("[5/5] Loading configuration...")
            self.tokens = config.TOKENS_TO_TRADE
            self.decision_interval = config.DECISION_INTERVAL

            print(f"\n[SUCCESS] System initialized!")
            print(f"  Mode: {'PAPER TRADING' if config.PAPER_TRADING else 'LIVE TRADING'}")
            print(f"  Tokens: {', '.join(self.tokens)}")
            print(f"  Decision Interval: {self.decision_interval//60} minutes")
            print(f"  Tier 2 Verification: {'ENABLED' if config.ENABLE_TIER2_VERIFICATION else 'DISABLED'}")
            print(f"  Initial Capital: ${config.INITIAL_CAPITAL:,.2f}")

        except Exception as e:
            print(f"\n[ERROR] Failed to initialize: {e}")
            raise

        # Statistics tracking
        self.cycle_count = 0
        self.start_time = datetime.now()
        self.last_report_time = datetime.now()

    def run(self):
        """Main trading loop"""
        print("\n" + "="*70)
        print("STARTING TRADING LOOP")
        print("="*70)
        print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("Press Ctrl+C to stop\n")

        while True:
            try:
                self.cycle_count += 1
                cycle_start = time.time()

                print(f"\n{'='*70}")
                print(f"CYCLE #{self.cycle_count} - {datetime.now().strftime('%H:%M:%S')}")
                print(f"{'='*70}")

                # Get current portfolio state
                portfolio = self.risk_manager.get_portfolio_state()

                # Check if trading is halted
                if portfolio['trading_halted']:
                    print(f"\n[HALTED] Trading suspended: {portfolio['halt_reason']}")
                    print(f"Waiting {self.decision_interval//60} minutes...")
                    time.sleep(self.decision_interval)
                    continue

                # Process each token
                decisions_made = 0
                for token in self.tokens:
                    try:
                        decision = self.process_token(token, portfolio)
                        if decision:
                            decisions_made += 1
                    except Exception as e:
                        print(f"\n[ERROR] Failed to process {token}: {e}")
                        if config.VERBOSE_LOGGING:
                            traceback.print_exc()

                # Print cycle summary
                cycle_time = time.time() - cycle_start
                print(f"\n[CYCLE COMPLETE]")
                print(f"  Decisions: {decisions_made}/{len(self.tokens)}")
                print(f"  Time: {cycle_time:.1f}s")
                print(f"  Portfolio: ${portfolio['total_value']:,.2f}")
                print(f"  Positions: {len(portfolio['positions'])}")

                # Generate performance report if needed
                if datetime.now() - self.last_report_time > timedelta(hours=config.REPORT_INTERVAL_HOURS):
                    self.generate_performance_report()
                    self.last_report_time = datetime.now()

                # Sleep until next cycle
                sleep_time = max(0, self.decision_interval - cycle_time)
                if sleep_time > 0:
                    print(f"\n[SLEEP] Sleeping {sleep_time//60:.0f} minutes until next cycle...")
                    time.sleep(sleep_time)

            except KeyboardInterrupt:
                print("\n\n[INFO] Shutdown signal received")
                self.shutdown()
                break

            except Exception as e:
                print(f"\n[ERROR] Unexpected error in main loop: {e}")
                traceback.print_exc()
                print("Waiting 60 seconds before retry...")
                time.sleep(60)

    def process_token(self, token: str, portfolio: Dict) -> Optional[Dict]:
        """
        Process a single token through the full decision pipeline

        Pipeline:
        1. Data aggregation
        2. Tier 1 Claude screening
        3. Tier 2 ensemble verification (BUY signals only)
        4. Risk validation
        5. Paper trading execution

        Returns:
            Decision dict if executed, None otherwise
        """

        print(f"\n[{token}] Processing...")

        # Step 1: Aggregate market data
        try:
            market_summary = format_market_summary(token)
        except Exception as e:
            print(f"  [ERROR] Failed to get market data: {e}")
            return None

        # Step 2: Tier 1 Claude decision
        tier1_decision = self.claude_engine.analyze_market(token, market_summary)

        if tier1_decision.get('error'):
            print(f"  [ERROR] Tier 1 error: {tier1_decision.get('reasoning')}")
            return None

        print(f"  Tier 1: {tier1_decision['action']} ({tier1_decision['confidence']:.0%} confidence)")

        # Step 3: Tier 2 verification (BUY signals only)
        final_decision = tier1_decision.copy()

        if (config.ENABLE_TIER2_VERIFICATION and
            tier1_decision['action'] == 'BUY'):

            print(f"  Triggering Tier 2 verification...")
            tier2_result = self.ensemble_verifier.verify_decision(
                token, market_summary, tier1_decision
            )

            # Update decision with Tier 2 results
            final_decision.update(tier2_result)
            final_decision['action'] = tier2_result['tier2_action']
            final_decision['confidence'] = tier2_result['tier2_confidence']

            print(f"  Tier 2: {final_decision['action']} ({tier2_result['tier2_consensus_score']:.0%} consensus)")

        # Save decision to database
        decision_id = self.save_decision(final_decision, market_summary)

        # Step 4: Risk validation
        final_decision['token'] = token
        validated = self.risk_manager.validate_trade(final_decision, portfolio)

        if not validated['approved']:
            print(f"  [REJECTED] Risk check failed: {validated['rejection_reason']}")
            self.update_decision_status(decision_id, 'REJECTED', validated['rejection_reason'])
            return None

        print(f"  [APPROVED] Risk approved: ${validated['position_size_usd']:.2f}")

        # Step 5: Paper trading execution
        if final_decision['action'] != 'HOLD':
            current_price = self.paper_trading.get_current_price(token)
            trade_result = self.paper_trading.execute_trade(
                decision_id, validated, current_price
            )

            if trade_result.get('executed'):
                print(f"  [EXECUTED] Trade executed: {final_decision['action']} at ${current_price:.2f}")

                # Update risk manager statistics
                if 'outcome' in trade_result:
                    self.risk_manager.update_trade_statistics(trade_result)
            else:
                print(f"  [FAILED] Trade execution failed")
        else:
            print(f"  ✅ HOLD signal - no action needed")
            self.update_decision_status(decision_id, 'HOLD', None)

        return final_decision

    def save_decision(self, decision: Dict, market_summary: str) -> int:
        """Save trading decision to database"""
        conn = self.get_db_connection()
        cursor = conn.cursor()

        try:
            # Prepare sentiment summary (truncate market data)
            sentiment_summary = {
                'market_data': market_summary[:1000],  # Truncate for storage
                'timestamp': datetime.now().isoformat()
            }

            cursor.execute("""
                INSERT INTO trading_decisions
                (token, tier1_action, tier1_confidence, tier1_reasoning,
                 tier2_triggered, tier2_action, tier2_confidence, tier2_consensus_score,
                 final_action, final_confidence, position_size_pct,
                 stop_loss, take_profit, sentiment_summary)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                decision['token'],
                decision['action'],
                decision.get('confidence', 0),
                decision.get('reasoning', ''),
                decision.get('tier2_triggered', False),
                decision.get('tier2_action'),
                decision.get('tier2_confidence'),
                decision.get('tier2_consensus_score'),
                decision.get('tier2_action', decision['action']),
                decision.get('tier2_confidence', decision.get('confidence', 0)),
                decision.get('position_size', 0),
                decision.get('stop_loss_pct', config.DEFAULT_STOP_LOSS_PCT),
                decision.get('take_profit_pct', config.DEFAULT_TAKE_PROFIT_PCT),
                psycopg2.extras.Json(sentiment_summary)
            ))

            decision_id = cursor.fetchone()[0]
            conn.commit()

            return decision_id

        except Exception as e:
            conn.rollback()
            print(f"[ERROR] Failed to save decision: {e}")
            return None

        finally:
            cursor.close()
            conn.close()

    def update_decision_status(self, decision_id: int, status: str, reason: Optional[str]):
        """Update decision status in database"""
        if not decision_id:
            return

        conn = self.get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                UPDATE trading_decisions
                SET status = %s, rejected_reason = %s
                WHERE id = %s
            """, (status, reason, decision_id))
            conn.commit()

        except Exception as e:
            conn.rollback()
            print(f"[ERROR] Failed to update decision status: {e}")

        finally:
            cursor.close()
            conn.close()

    def generate_performance_report(self):
        """Generate performance report"""
        print("\n" + "="*70)
        print("PERFORMANCE REPORT")
        print("="*70)

        conn = self.get_db_connection()
        cursor = conn.cursor()

        try:
            # Get portfolio performance
            cursor.execute("""
                SELECT
                    total_value,
                    total_pnl,
                    total_pnl_pct,
                    winning_trades,
                    losing_trades,
                    win_rate,
                    max_drawdown
                FROM portfolio_state
                ORDER BY id DESC
                LIMIT 1
            """)

            portfolio = cursor.fetchone()
            if portfolio:
                print(f"\nPORTFOLIO METRICS:")
                print(f"  Current Value: ${float(portfolio[0]):,.2f}")
                print(f"  Total P&L: ${float(portfolio[1]):,.2f} ({float(portfolio[2]):+.2f}%)")
                print(f"  Trades: {int(portfolio[3])+int(portfolio[4])} ({int(portfolio[3])}W/{int(portfolio[4])}L)")
                print(f"  Win Rate: {float(portfolio[5]):.1%}")
                print(f"  Max Drawdown: {float(portfolio[6]):.1%}")

            # Get recent trades
            cursor.execute("""
                SELECT
                    token,
                    final_action,
                    outcome,
                    pnl_usd,
                    pnl_pct,
                    decision_time
                FROM trading_decisions
                WHERE status = 'CLOSED'
                ORDER BY closed_at DESC
                LIMIT 10
            """)

            trades = cursor.fetchall()
            if trades:
                print(f"\nRECENT TRADES:")
                for trade in trades:
                    token = trade[0]
                    outcome = trade[2] or 'PENDING'
                    pnl = float(trade[3]) if trade[3] else 0
                    pnl_pct = float(trade[4]) if trade[4] else 0
                    print(f"  {token}: {outcome} ${pnl:+.2f} ({pnl_pct:+.1f}%)")

            # System uptime
            uptime = datetime.now() - self.start_time
            print(f"\nSYSTEM STATUS:")
            print(f"  Uptime: {uptime.days}d {uptime.seconds//3600}h")
            print(f"  Cycles: {self.cycle_count}")
            print(f"  Mode: {'PAPER' if config.PAPER_TRADING else 'LIVE'}")

        finally:
            cursor.close()
            conn.close()

        print("="*70)

    def get_db_connection(self):
        """Get database connection"""
        return psycopg2.connect(
            host=config.DB_HOST,
            port=config.DB_PORT,
            database=config.DB_NAME,
            user=config.DB_USER,
            password=config.DB_PASSWORD
        )

    def shutdown(self):
        """Clean shutdown"""
        print("\n[INFO] Shutting down trading system...")
        self.generate_performance_report()
        print("\n[SUCCESS] Trading system stopped")
        print(f"Total runtime: {datetime.now() - self.start_time}")


def main():
    """Main entry point"""
    print("""
    ================================================================
                      PJX AI TRADING SYSTEM

      Architecture: Tiered AI Verification
      Tier 1: Claude Sonnet 4 (all signals)
      Tier 2: 3-Model Ensemble (BUY verification)

      WARNING: This is PAPER TRADING mode
      No real money will be traded
    ================================================================
    """)

    try:
        # Extra import to ensure psycopg2.extras is available
        import psycopg2.extras

        # Create and run trading system
        system = TradingSystem()
        system.run()

    except KeyboardInterrupt:
        print("\n[INFO] Shutdown requested")

    except Exception as e:
        print(f"\n[FATAL ERROR] {e}")
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())