"""
Tier 2: Ensemble Verification System
3-model consensus voting for BUY signal verification
Models: Claude (40%), DeepSeek (35%), Gemini (25%) weighted voting
Only triggered for BUY signals to reduce costs
"""

import anthropic
import google.generativeai as genai
from openai import OpenAI  # DeepSeek uses OpenAI-compatible API
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import time
from typing import Dict, List, Optional
import config


class EnsembleVerifier:
    """Tier 2 ensemble verification for high-stakes trading decisions"""

    def __init__(self):
        """Initialize all model clients"""
        self.models = {}

        # Initialize Claude
        if config.ENSEMBLE_MODELS['claude']['api_key']:
            self.models['claude'] = anthropic.Anthropic(
                api_key=config.ENSEMBLE_MODELS['claude']['api_key']
            )

        # Initialize DeepSeek (uses OpenAI-compatible API)
        if config.ENSEMBLE_MODELS['deepseek']['api_key']:
            self.models['deepseek'] = OpenAI(
                api_key=config.ENSEMBLE_MODELS['deepseek']['api_key'],
                base_url="https://api.deepseek.com"
            )

        # Initialize Gemini
        if config.ENSEMBLE_MODELS['gemini']['api_key']:
            genai.configure(api_key=config.ENSEMBLE_MODELS['gemini']['api_key'])
            self.models['gemini'] = genai.GenerativeModel('gemini-2.0-flash-exp')

        if not self.models:
            raise ValueError("No ensemble models available - check API keys")

        print(f"[ENSEMBLE] Initialized {len(self.models)} models for verification")

    def verify_decision(self, token: str, market_summary: str, tier1_decision: Dict) -> Dict:
        """
        Verify a Tier 1 decision through ensemble voting

        Args:
            token: Token symbol
            market_summary: Formatted market data
            tier1_decision: Initial decision from Claude Tier 1

        Returns:
            Dict with consensus decision and individual votes
        """

        print(f"\n[TIER 2] Verifying {tier1_decision['action']} signal for {token}...")

        # Prepare prompt for all models
        verification_prompt = self._build_verification_prompt(token, market_summary, tier1_decision)

        # Collect votes from all models in parallel
        votes = self._collect_votes(verification_prompt, token)

        # Calculate weighted consensus
        consensus = self._calculate_consensus(votes)

        # Build final decision
        final_decision = {
            'token': token,
            'tier2_triggered': True,
            'tier2_action': consensus['action'],
            'tier2_confidence': consensus['confidence'],
            'tier2_consensus_score': consensus['consensus_score'],
            'votes': votes,
            'timestamp': datetime.now()
        }

        if config.VERBOSE_LOGGING:
            print(f"\n[TIER 2] Ensemble Verification Complete:")
            print(f"  Consensus Action: {consensus['action']}")
            print(f"  Consensus Score: {consensus['consensus_score']:.2%}")
            print(f"  Individual Votes:")
            for vote in votes:
                print(f"    - {vote['model']}: {vote['action']} ({vote['confidence']:.2%})")

        return final_decision

    def _build_verification_prompt(self, token: str, market_summary: str, tier1_decision: Dict) -> str:
        """Build verification prompt for ensemble models"""

        prompt = f"""You are a senior trading analyst reviewing a trading decision.

Another analyst has recommended: {tier1_decision['action']} for {token}
Their confidence: {tier1_decision['confidence']:.2%}
Their reasoning: {tier1_decision['reasoning']}

MARKET DATA:
{market_summary}

CRITICAL TASK:
Review this trading decision and provide your independent assessment.
Consider:
1. Is the market data supportive of a {tier1_decision['action']} signal?
2. Are there any red flags or risks that were overlooked?
3. Would you agree with this decision?

IMPORTANT RULES:
- Provide your own independent analysis
- Only recommend BUY if you have >70% confidence
- Be conservative - when in doubt, recommend HOLD
- Consider risk/reward carefully

Provide your decision in this exact format:
<verification>
<action>BUY or HOLD</action>
<confidence>0.0-1.0</confidence>
<reasoning>Your independent assessment in 2-3 sentences</reasoning>
</verification>"""

        return prompt

    def _collect_votes(self, prompt: str, token: str) -> List[Dict]:
        """Collect votes from all models in parallel"""
        votes = []

        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {}

            # Submit requests to all models
            if 'claude' in self.models:
                futures[executor.submit(self._get_claude_vote, prompt, token)] = 'claude'

            if 'deepseek' in self.models:
                futures[executor.submit(self._get_deepseek_vote, prompt, token)] = 'deepseek'

            if 'gemini' in self.models:
                futures[executor.submit(self._get_gemini_vote, prompt, token)] = 'gemini'

            # Collect results
            for future in as_completed(futures):
                model_name = futures[future]
                try:
                    vote = future.result(timeout=30)
                    vote['model'] = model_name
                    vote['weight'] = config.ENSEMBLE_MODELS[model_name]['weight']
                    votes.append(vote)
                except Exception as e:
                    print(f"[ERROR] {model_name} vote failed: {e}")
                    # Add default HOLD vote on error
                    votes.append({
                        'model': model_name,
                        'action': 'HOLD',
                        'confidence': 0.0,
                        'reasoning': f"Error: {str(e)}",
                        'weight': config.ENSEMBLE_MODELS[model_name]['weight'],
                        'error': True
                    })

        return votes

    def _get_claude_vote(self, prompt: str, token: str) -> Dict:
        """Get vote from Claude"""
        start_time = time.time()

        try:
            response = self.models['claude'].messages.create(
                model=config.ENSEMBLE_MODELS['claude']['name'],
                max_tokens=500,
                temperature=0.7,
                messages=[{"role": "user", "content": prompt}]
            )

            response_text = response.content[0].text
            vote = self._parse_verification_response(response_text)
            vote['response_time_ms'] = int((time.time() - start_time) * 1000)

            return vote

        except Exception as e:
            raise Exception(f"Claude vote failed: {e}")

    def _get_deepseek_vote(self, prompt: str, token: str) -> Dict:
        """Get vote from DeepSeek"""
        start_time = time.time()

        try:
            response = self.models['deepseek'].chat.completions.create(
                model=config.ENSEMBLE_MODELS['deepseek']['name'],
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=500
            )

            response_text = response.choices[0].message.content
            vote = self._parse_verification_response(response_text)
            vote['response_time_ms'] = int((time.time() - start_time) * 1000)

            return vote

        except Exception as e:
            raise Exception(f"DeepSeek vote failed: {e}")

    def _get_gemini_vote(self, prompt: str, token: str) -> Dict:
        """Get vote from Gemini"""
        start_time = time.time()

        try:
            response = self.models['gemini'].generate_content(prompt)
            response_text = response.text

            vote = self._parse_verification_response(response_text)
            vote['response_time_ms'] = int((time.time() - start_time) * 1000)

            return vote

        except Exception as e:
            raise Exception(f"Gemini vote failed: {e}")

    def _parse_verification_response(self, response_text: str) -> Dict:
        """Parse verification response from any model"""
        import re

        try:
            # Extract action
            action_match = re.search(r'<action>(BUY|HOLD)</action>', response_text)
            action = action_match.group(1) if action_match else 'HOLD'

            # Extract confidence
            conf_match = re.search(r'<confidence>([\d.]+)</confidence>', response_text)
            confidence = float(conf_match.group(1)) if conf_match else 0.0

            # Extract reasoning
            reasoning_match = re.search(r'<reasoning>(.*?)</reasoning>', response_text, re.DOTALL)
            reasoning = reasoning_match.group(1).strip() if reasoning_match else "No reasoning"

            return {
                'action': action,
                'confidence': confidence,
                'reasoning': reasoning,
                'error': False
            }

        except Exception as e:
            return {
                'action': 'HOLD',
                'confidence': 0.0,
                'reasoning': f"Parse error: {e}",
                'error': True
            }

    def _calculate_consensus(self, votes: List[Dict]) -> Dict:
        """
        Calculate weighted consensus from all votes

        Returns:
            Dict with consensus action, confidence, and score
        """

        if not votes:
            return {
                'action': 'HOLD',
                'confidence': 0.0,
                'consensus_score': 0.0
            }

        # Calculate weighted scores
        buy_score = 0.0
        hold_score = 0.0
        total_weight = 0.0

        for vote in votes:
            if vote.get('error', False):
                continue  # Skip error votes

            weight = vote['weight']
            confidence = vote['confidence']

            if vote['action'] == 'BUY':
                buy_score += weight * confidence
            else:  # HOLD
                hold_score += weight * (1.0 - confidence)

            total_weight += weight

        # Normalize scores
        if total_weight > 0:
            buy_score /= total_weight
            hold_score /= total_weight
        else:
            return {
                'action': 'HOLD',
                'confidence': 0.0,
                'consensus_score': 0.0
            }

        # Determine consensus
        if buy_score > config.MIN_TIER2_CONSENSUS:
            consensus_action = 'BUY'
            consensus_confidence = buy_score
        else:
            consensus_action = 'HOLD'
            consensus_confidence = hold_score

        # Calculate consensus strength (how much models agree)
        vote_actions = [v['action'] for v in votes if not v.get('error', False)]
        if vote_actions:
            agreement_rate = vote_actions.count(consensus_action) / len(vote_actions)
        else:
            agreement_rate = 0.0

        return {
            'action': consensus_action,
            'confidence': consensus_confidence,
            'consensus_score': agreement_rate
        }


# Test function
if __name__ == "__main__":
    print("Testing Ensemble Verifier...")
    print("\nNote: This requires valid API keys for Claude, DeepSeek, and Gemini")

    # Mock tier 1 decision
    tier1_decision = {
        'action': 'BUY',
        'confidence': 0.75,
        'reasoning': 'Test BUY signal for verification',
        'position_size': 3.0
    }

    # Mock market summary
    market_summary = """TOKEN: BTC
TIMESTAMP: 2025-10-30 23:00:00

=== TWITTER SENTIMENT (Last 6h) ===
Average Sentiment: +0.4523 (Bullish)
Tweet Volume: 523 tweets
Sentiment Velocity: +0.0821 (Accelerating)

=== PRICE ACTION (Last 24h) ===
Current Price: $109,044.00
24H Change: +2.5%
Support: $106,500
Resistance: $112,000
"""

    try:
        # Initialize verifier
        verifier = EnsembleVerifier()

        # Get ensemble verification
        result = verifier.verify_decision('BTC', market_summary, tier1_decision)

        print("\n" + "=" * 70)
        print("ENSEMBLE VERIFICATION RESULT")
        print("=" * 70)
        print(f"Tier 2 Action: {result['tier2_action']}")
        print(f"Consensus Score: {result['tier2_consensus_score']:.2%}")
        print(f"Confidence: {result['tier2_confidence']:.2%}")

    except Exception as e:
        print(f"\n[ERROR] Ensemble verification failed: {e}")
        print("Please check your API keys are correctly set in .env file")