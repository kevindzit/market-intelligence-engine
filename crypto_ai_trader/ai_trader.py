"""
AI Trader - Main orchestration with dynamic token discovery
Handles the main loop, Claude decisions, and ensemble verification
"""

import asyncio
import time
import signal
import sys
from datetime import datetime
from typing import Dict, List, Optional, Any
import json
import anthropic
import google.generativeai as genai
from openai import OpenAI
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
import os
from dotenv import load_dotenv

from data_intelligence import DataIntelligence
from portfolio_manager import PortfolioManager
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
            'port': config.DB_PORT,
            'database': config.DB_NAME,
            'user': config.DB_USER,
            'password': config.DB_PASSWORD
        }

        # Initialize data intelligence
        self.data_intel = DataIntelligence(self.db_config)

        # Initialize portfolio manager
        self.portfolio = PortfolioManager(self.db_config, config.INITIAL_CAPITAL)

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

        # Close positions if needed (optional for paper trading)
        self.portfolio.print_summary()

        # Close connections
        self.data_intel.close()
        self.portfolio.close()

        print("[SHUTDOWN] Cleanup complete. Goodbye!")
        sys.exit(0)

    async def run_forever(self):
        """Main trading loop with dynamic token discovery"""
        print("\n[START] Beginning unlimited token trading loop...")
        print("Press Ctrl+C to stop gracefully\n")

        while self.trading_active:
            try:
                loop_start = time.time()

                # Discover all active tokens
                active_tokens = self.data_intel.discover_active_tokens(min_activity_hours=24)

                if not active_tokens:
                    print("[WARNING] No active tokens found, waiting...")
                    await asyncio.sleep(60)
                    continue

                print(f"\n[SCAN] Processing {len(active_tokens)} active tokens...")

                # Get trending tokens for priority processing
                trending = self.data_intel.get_trending_tokens(min_spike=2.0)
                trending_tokens = [t['token'] for t in trending]

                # Process trending tokens first, then others
                priority_tokens = trending_tokens + [t for t in active_tokens if t not in trending_tokens]

                # Check circuit breakers
                if self.check_circuit_breakers():
                    print("[HALT] Circuit breaker triggered, skipping this cycle")
                    await asyncio.sleep(config.DECISION_INTERVAL)
                    continue

                # Process each token
                opportunities = []
                for token in priority_tokens[:20]:  # Process top 20 to keep cycle time reasonable
                    try:
                        # Get quick summary first
                        summary = self.data_intel.get_quick_summary(token)
                        if not summary:
                            continue

                        # Quick filter: Skip if no activity
                        if summary['tweets_1h'] < 5 and abs(summary['price_change_1h']) < 1:
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

                # Execute top opportunities (respecting position limits)
                executed = 0
                for opp in opportunities:
                    if executed >= 3:  # Max 3 new positions per cycle
                        break

                    success = await self.execute_decision(opp)
                    if success:
                        executed += 1

                # Update portfolio state
                self.portfolio.update_positions()

                # Print cycle summary
                cycle_time = time.time() - loop_start
                print(f"\n[CYCLE] Completed in {cycle_time:.1f}s")
                print(f"  Tokens scanned: {len(priority_tokens[:20])}")
                print(f"  Opportunities found: {len(opportunities)}")
                print(f"  Positions executed: {executed}")
                print(f"  Portfolio value: ${self.portfolio.get_total_value():,.2f}")

                # Wait for next cycle
                wait_time = max(1, config.DECISION_INTERVAL - cycle_time)
                print(f"\n[WAIT] Next cycle in {wait_time:.0f} seconds...")
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

            # Add market-wide context
            context['fear_greed'] = self.data_intel.get_fear_greed_index()

            # Check for whale movements
            whale_flows = self.data_intel.get_whale_movements(hours=3)
            context['whale_activity'] = [w for w in whale_flows if w['token'] == token]

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
        """Generate trading decision using Claude Sonnet"""
        try:
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

            # Add portfolio context
            prompt += f"""
PORTFOLIO:
- Available Cash: ${context['portfolio']['cash_available']:,.2f}
- Open Positions: {context['portfolio']['open_position_count']}
- Daily P&L: ${context['portfolio']['daily_pnl']:.2f}

Provide your trading decision in the specified XML format.
"""

            # Call Claude
            response = self.claude_client.messages.create(
                model=config.CLAUDE_MODEL,
                max_tokens=config.CLAUDE_MAX_TOKENS,
                temperature=config.CLAUDE_TEMPERATURE,
                system=config.SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}]
            )

            # Parse response
            decision = self.parse_claude_response(response.content[0].text, token)

            if decision:
                print(f"[TIER 1] {token}: {decision['action']} (confidence: {decision['confidence']:.2f})")

            return decision

        except Exception as e:
            print(f"[ERROR] Claude decision failed for {token}: {e}")
            return None

    def parse_claude_response(self, response_text: str, token: str) -> Optional[Dict]:
        """Parse Claude's XML response"""
        try:
            # Find XML content
            start = response_text.find('<trading_decision>')
            end = response_text.find('</trading_decision>') + len('</trading_decision>')

            if start == -1 or end == -1:
                print(f"[ERROR] No valid XML found in Claude response")
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
                'timestamp': datetime.now().isoformat()
            }

            # Validate
            if decision['confidence'] < config.MIN_TIER1_CONFIDENCE:
                decision['action'] = 'HOLD'
                decision['reasoning'] += f" (Confidence {decision['confidence']:.2f} below threshold)"

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

        # Calculate weighted consensus
        total_weight = 0
        agree_weight = 0

        for model_name, vote in votes.items():
            weight = config.ENSEMBLE_MODELS[model_name]['weight']
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
                # Calculate position size
                position_value = self.portfolio.calculate_position_size(
                    decision['position_size'],
                    price
                )

                if position_value < config.MIN_POSITION_SIZE_USD:
                    print(f"[SKIP] Position too small: ${position_value:.2f}")
                    return False

                # Execute buy
                success = self.portfolio.open_position(
                    token=token,
                    entry_price=price,
                    position_value=position_value,
                    stop_loss_pct=decision['stop_loss_pct'],
                    take_profit_pct=decision['take_profit_pct'],
                    reasoning=decision['reasoning']
                )

                if success:
                    self.daily_trade_count += 1
                    print(f"[BUY] {token} - ${position_value:.2f} at ${price:.4f}")

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

                    return success
                else:
                    print(f"[SKIP] No position to sell for {token}")
                    return False

        except Exception as e:
            print(f"[ERROR] Execution failed: {e}")
            return False

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