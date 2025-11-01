"""
Tier 1: Claude Sonnet 4 Decision Engine
Fast screening of all trading signals (<1 second, $0.003/signal)
Uses prompt caching for 90% cost savings
Now enhanced with liquidation cascade awareness!
"""

import anthropic
import re
from datetime import datetime
from typing import Dict, Optional
import config
from liquidation_predictor import get_liquidation_predictor


class ClaudeEngine:
    """Tier 1 trading decision engine using Claude Sonnet 4"""

    def __init__(self):
        """Initialize Claude client"""
        if not config.CLAUDE_API_KEY:
            raise ValueError("CLAUDE_API_KEY not found in environment")

        self.client = anthropic.Anthropic(api_key=config.CLAUDE_API_KEY)
        self.model = config.CLAUDE_MODEL

    def analyze_market(self, token: str, market_summary: str) -> Dict:
        """
        Analyze market data and generate trading decision

        Args:
            token: Token symbol (e.g., 'BTC')
            market_summary: Formatted market data summary

        Returns:
            Dict with decision details
        """

        # Build user prompt
        user_prompt = f"""Analyze {token} and provide your trading decision.

{market_summary}

Provide your decision following the XML format specified in your instructions."""

        try:
            # Call Claude API with prompt caching
            # System prompt will be cached (90% cost reduction on subsequent calls)
            response = self.client.messages.create(
                model=self.model,
                max_tokens=config.CLAUDE_MAX_TOKENS,
                temperature=config.CLAUDE_TEMPERATURE,
                system=[
                    {
                        "type": "text",
                        "text": config.SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"}  # Cache this for 5 min
                    }
                ],
                messages=[
                    {"role": "user", "content": user_prompt}
                ]
            )

            # Extract response text
            response_text = response.content[0].text

            # Parse XML decision
            decision = self._parse_decision(response_text)

            # Add metadata
            decision['token'] = token
            decision['timestamp'] = datetime.now()
            decision['raw_response'] = response_text
            decision['model'] = self.model

            # Add usage stats for cost tracking
            decision['usage'] = {
                'input_tokens': response.usage.input_tokens,
                'output_tokens': response.usage.output_tokens,
                'cache_creation_tokens': getattr(response.usage, 'cache_creation_input_tokens', 0),
                'cache_read_tokens': getattr(response.usage, 'cache_read_input_tokens', 0)
            }

            # Enhance decision with liquidation awareness
            # Extract current price from market summary if available
            import re as price_re
            price_match = price_re.search(r'Current Price: \$([0-9,\.]+)', market_summary)
            if price_match:
                current_price = float(price_match.group(1).replace(',', ''))
                liquidation_predictor = get_liquidation_predictor()
                decision = liquidation_predictor.enhance_trading_decision(decision, token, current_price)

            if config.VERBOSE_LOGGING:
                print(f"\n[TIER 1] Claude Decision for {token}:")
                print(f"  Action: {decision['action']}")
                print(f"  Confidence: {decision['confidence']:.2%}")
                if decision['action'] != 'HOLD':
                    print(f"  Position Size: {decision['position_size']:.1f}%")
                if 'liquidation_risk' in decision:
                    print(f"  Liquidation Risk: {decision['liquidation_risk']}/100")
                    if decision['cascade_type'] != 'BALANCED':
                        print(f"  Cascade Type: {decision['cascade_type']}")
                print(f"  Tokens: {decision['usage']['input_tokens']} in, "
                      f"{decision['usage']['output_tokens']} out "
                      f"({decision['usage']['cache_read_tokens']} cached)")

            return decision

        except Exception as e:
            print(f"[ERROR] Claude API call failed for {token}: {e}")
            # Return safe default (HOLD) on error
            return {
                'token': token,
                'action': 'HOLD',
                'confidence': 0.0,
                'position_size': 0.0,
                'stop_loss_pct': config.DEFAULT_STOP_LOSS_PCT,
                'take_profit_pct': config.DEFAULT_TAKE_PROFIT_PCT,
                'reasoning': f"API error: {str(e)}",
                'risk_factors': "System error",
                'error': True,
                'timestamp': datetime.now()
            }

    def _parse_decision(self, response_text: str) -> Dict:
        """
        Parse XML-formatted decision from Claude response

        Expected format:
        <trading_decision>
          <action>BUY|SELL|HOLD</action>
          <confidence>0.75</confidence>
          <position_size>3.5</position_size>
          <stop_loss_pct>3.0</stop_loss_pct>
          <take_profit_pct>6.0</take_profit_pct>
          <reasoning>...</reasoning>
          <risk_factors>...</risk_factors>
        </trading_decision>
        """

        try:
            # Extract action
            action_match = re.search(r'<action>(BUY|SELL|HOLD)</action>', response_text)
            action = action_match.group(1) if action_match else 'HOLD'

            # Extract confidence
            conf_match = re.search(r'<confidence>([\d.]+)</confidence>', response_text)
            confidence = float(conf_match.group(1)) if conf_match else 0.0

            # Extract position size
            size_match = re.search(r'<position_size>([\d.]+)</position_size>', response_text)
            position_size = float(size_match.group(1)) if size_match else 0.0

            # Extract stop loss
            sl_match = re.search(r'<stop_loss_pct>([\d.]+)</stop_loss_pct>', response_text)
            stop_loss = float(sl_match.group(1)) if sl_match else config.DEFAULT_STOP_LOSS_PCT

            # Extract take profit
            tp_match = re.search(r'<take_profit_pct>([\d.]+)</take_profit_pct>', response_text)
            take_profit = float(tp_match.group(1)) if tp_match else config.DEFAULT_TAKE_PROFIT_PCT

            # Extract reasoning
            reasoning_match = re.search(r'<reasoning>(.*?)</reasoning>', response_text, re.DOTALL)
            reasoning = reasoning_match.group(1).strip() if reasoning_match else "No reasoning provided"

            # Extract risk factors
            risk_match = re.search(r'<risk_factors>(.*?)</risk_factors>', response_text, re.DOTALL)
            risk_factors = risk_match.group(1).strip() if risk_match else "None specified"

            # Validate and enforce constraints
            if confidence < config.MIN_TIER1_CONFIDENCE:
                action = 'HOLD'
                position_size = 0.0

            if action == 'HOLD':
                position_size = 0.0

            # Cap position size at maximum
            position_size = min(position_size, config.MAX_POSITION_SIZE_PCT)

            return {
                'action': action,
                'confidence': confidence,
                'position_size': position_size,
                'stop_loss_pct': stop_loss,
                'take_profit_pct': take_profit,
                'reasoning': reasoning,
                'risk_factors': risk_factors,
                'error': False
            }

        except Exception as e:
            print(f"[ERROR] Failed to parse Claude response: {e}")
            print(f"Response text: {response_text[:500]}...")

            # Return safe default
            return {
                'action': 'HOLD',
                'confidence': 0.0,
                'position_size': 0.0,
                'stop_loss_pct': config.DEFAULT_STOP_LOSS_PCT,
                'take_profit_pct': config.DEFAULT_TAKE_PROFIT_PCT,
                'reasoning': "Failed to parse response",
                'risk_factors': "Parse error",
                'error': True
            }


# Test function
if __name__ == "__main__":
    print("Testing Claude Engine...\n")

    # Import data aggregator
    import sys
    sys.path.insert(0, '..')
    from crypto_ai_trader import data_aggregator

    # Test with BTC
    token = 'BTC'
    print(f"Generating decision for {token}...")

    # Get market summary
    summary = data_aggregator.format_market_summary(token)

    # Initialize engine
    try:
        engine = ClaudeEngine()

        # Get decision
        decision = engine.analyze_market(token, summary)

        print("\n" + "=" * 70)
        print("TIER 1 DECISION")
        print("=" * 70)
        print(f"Token: {decision['token']}")
        print(f"Action: {decision['action']}")
        print(f"Confidence: {decision['confidence']:.2%}")
        print(f"Position Size: {decision['position_size']:.1f}%")
        print(f"Stop Loss: {decision['stop_loss_pct']:.1f}%")
        print(f"Take Profit: {decision['take_profit_pct']:.1f}%")
        print(f"\nReasoning: {decision['reasoning']}")
        print(f"\nRisk Factors: {decision['risk_factors']}")

        if 'usage' in decision:
            print(f"\nAPI Usage:")
            print(f"  Input tokens: {decision['usage']['input_tokens']}")
            print(f"  Output tokens: {decision['usage']['output_tokens']}")
            print(f"  Cache creation: {decision['usage']['cache_creation_tokens']}")
            print(f"  Cache read: {decision['usage']['cache_read_tokens']}")

    except ValueError as e:
        print(f"[ERROR] {e}")
        print("\nPlease add your CLAUDE_API_KEY to the .env file to test")
