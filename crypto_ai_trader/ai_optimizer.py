"""
AI Model Optimization and Performance Tracking System
Dynamically adjusts model weights, prompts, and strategies based on performance
"""

import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
import psycopg2
import psycopg2.extras

class AIOptimizer:
    """
    Advanced AI optimization system that:
    1. Tracks model performance
    2. Adjusts weights dynamically
    3. Selects optimal prompts for market conditions
    4. Learns from past decisions
    """

    def __init__(self, db_config: Dict):
        """Initialize AI optimizer"""
        self.db_config = db_config
        self.conn = psycopg2.connect(
            host=db_config['host'],
            port=db_config['port'],
            database=db_config['database'],
            user=db_config['user'],
            password=db_config['password']
        )

        # Performance tracking
        self.model_performance = defaultdict(lambda: {
            'trades': 0,
            'wins': 0,
            'total_pnl': 0,
            'avg_confidence': 0,
            'false_positives': 0,
            'false_negatives': 0,
            'last_30_days': []
        })

        # Load historical performance
        self.load_model_performance()

        # Market-specific prompt templates
        self.prompt_templates = self._initialize_prompt_templates()

        # Model specializations based on performance
        self.model_specializations = {
            'claude': {'strengths': ['sentiment', 'patterns'], 'weaknesses': []},
            'deepseek': {'strengths': ['technical', 'volatility'], 'weaknesses': []},
            'gemini': {'strengths': ['macro', 'correlation'], 'weaknesses': []}
        }

    def _initialize_prompt_templates(self) -> Dict:
        """Initialize advanced prompt templates for different market conditions"""
        return {
            'BULL_MARKET': """You are analyzing {token} in a STRONG BULL MARKET environment.

BULL MARKET CONTEXT:
- Markets trending UP strongly (BTC +{btc_change:.1f}% today)
- Risk appetite is HIGH
- Dips are buying opportunities
- Momentum is your friend
- BUT: Watch for overextension and profit-taking zones

ENHANCED DECISION FRAMEWORK FOR BULL MARKETS:
1. FAVOR momentum plays - trends persist longer than expected
2. BUY dips aggressively when sentiment remains positive
3. USE wider stop-losses (5-7%) to avoid premature exits
4. TARGET higher profits (10-15%) as trends extend
5. WATCH for exhaustion signals (extreme RSI, volume divergence)
6. Position size can be LARGER (3-5%) with strong trends

{data_context}

BULL MARKET TRADING RULES:
- Confidence threshold: 55% (lower than normal due to trend strength)
- Prefer LONG positions strongly
- Quick entries on pullbacks to support
- Trail stops aggressively once in profit
- Scale out at resistance levels

Provide your decision with bull market optimizations applied.""",

            'BEAR_MARKET': """You are analyzing {token} in a SEVERE BEAR MARKET environment.

BEAR MARKET CONTEXT:
- Markets in DECLINE (BTC {btc_change:.1f}% today)
- Risk OFF sentiment dominates
- Rallies are selling opportunities
- Capital preservation is CRITICAL
- Counter-trend trades are dangerous

DEFENSIVE FRAMEWORK FOR BEAR MARKETS:
1. EXTREME selectivity - only A+ setups
2. SMALLER positions (1-2% max)
3. TIGHTER stops (2-3%)
4. QUICK profit taking (3-5%)
5. AVOID catching falling knives
6. CASH is a position

{data_context}

BEAR MARKET RULES:
- Confidence threshold: 75% (much higher than normal)
- Prefer SHORT positions or HOLD
- Exit longs at first sign of weakness
- No averaging down
- Respect all resistance levels

Provide ultra-conservative decision appropriate for bear market.""",

            'HIGH_VOLATILITY': """You are analyzing {token} in EXTREME VOLATILITY conditions.

VOLATILITY CONTEXT:
- ATR is {atr:.1f}% (extremely high)
- Whipsaw risk is SEVERE
- False breakouts common
- Liquidation cascades active
- Wide bid-ask spreads

VOLATILITY MANAGEMENT FRAMEWORK:
1. REDUCE position sizes by 50%
2. WIDER stops to avoid whipsaws (2x ATR)
3. ENTER only at extremes (oversold/overbought)
4. USE limit orders to avoid slippage
5. MONITOR liquidation levels closely
6. EXPECT 2-3x normal movement

{data_context}

HIGH VOLATILITY RULES:
- Confidence threshold: 70%
- Position size: 1-2% MAX
- Stop loss: {suggested_stop:.1f}% (volatility-adjusted)
- Take profit: {suggested_tp:.1f}% (volatility-adjusted)
- Avoid mid-range entries
- Wait for volatility exhaustion

Provide volatility-adjusted decision with extra risk management.""",

            'LIQUIDATION_CASCADE': """You are analyzing {token} during an ACTIVE LIQUIDATION CASCADE.

CASCADE EMERGENCY CONTEXT:
- Liquidation velocity: {liq_velocity} per minute
- Total liquidated: ${liq_total:,.0f}
- Cascade type: {cascade_type}
- Price is in FREEFALL/SQUEEZE mode

CRISIS MANAGEMENT PROTOCOL:
1. DO NOT try to catch the knife
2. WAIT for cascade exhaustion (velocity <2/min)
3. LOOK for capitulation volume
4. MONITOR order book refill
5. ENTER only after stabilization
6. USE small test positions first

{data_context}

CASCADE RULES:
- BUY: Only after 10min of stability
- SELL: Exit immediately if holding
- Position size: 0.5-1% test positions only
- Stop loss: MANDATORY tight stops
- Confirmation: Need 3+ stability signals

Provide cascade-aware emergency decision.""",

            'WHALE_ACCUMULATION': """You are analyzing {token} with WHALE ACCUMULATION detected.

WHALE ACTIVITY CONTEXT:
- Large buyers detected: {whale_count}
- Accumulation volume: ${whale_volume:,.0f}
- Smart money is BUYING
- Potential major move incoming

WHALE-FOLLOWING STRATEGY:
1. FOLLOW smart money direction
2. ENTER on pullbacks to whale buy zones
3. LARGER positions justified (3-5%)
4. PATIENT holds for whale targets
5. EXIT if whales start distributing

{data_context}

WHALE RULES:
- Trust whale direction
- Buy similar levels to whales
- Hold through minor volatility
- Watch for distribution signals
- Size up with conviction

Provide whale-informed strategic decision.""",

            'LOW_LIQUIDITY': """You are analyzing {token} in LOW LIQUIDITY conditions.

LIQUIDITY WARNING:
- Thin order books detected
- Spread is {spread:.2f}% (very wide)
- Slippage risk: {slippage:.1f}%
- Manipulation risk HIGH

LOW LIQUIDITY FRAMEWORK:
1. REDUCE position size by 75%
2. USE limit orders only
3. AVOID market orders
4. WIDER stops for spread
5. EXPECT erratic moves
6. PLAN exits carefully

{data_context}

LOW LIQUIDITY RULES:
- Max position: 1% of portfolio
- Entry: Limit orders only
- Patience required
- Factor in 2x expected slippage
- Have exit strategy ready

Provide liquidity-aware careful decision.""",

            'SENTIMENT_EXTREME': """You are analyzing {token} with EXTREME SENTIMENT detected.

SENTIMENT CONTEXT:
- Sentiment score: {sentiment:.3f} ({sentiment_label})
- Tweet volume: {tweet_volume}x normal
- Emotion: {dominant_emotion}
- Potential sentiment trap

SENTIMENT EXTREMES FRAMEWORK:
1. EXTREME bullish = Potential TOP
2. EXTREME bearish = Potential BOTTOM
3. FADE extreme sentiment after climax
4. WAIT for sentiment exhaustion
5. CONTRARIAN opportunities exist

{data_context}

SENTIMENT RULES:
- Extreme bullish (>0.8): Consider SELLING
- Extreme bearish (<-0.8): Consider BUYING
- Peak emotion = Reversal signal
- Volume confirms sentiment
- Fade the crowd at extremes

Provide sentiment-contrarian informed decision.""",

            'CORRELATION_BREAK': """You are analyzing {token} showing CORRELATION BREAKDOWN.

DECORRELATION CONTEXT:
- Normal correlation: {normal_corr:.2f}
- Current correlation: {current_corr:.2f}
- Deviation: {corr_deviation:.1f} sigma
- Potential independent move

DECORRELATION STRATEGY:
1. TOKEN acting independently
2. IGNORE market direction
3. FOCUS on token-specific signals
4. LARGER positions possible
5. UNIQUE opportunity window

{data_context}

DECORRELATION RULES:
- Trade token on its own merits
- Ignore BTC/ETH movements
- Size based on setup quality
- Expect mean reversion eventually
- Take profits on re-correlation

Provide correlation-independent analysis.""",

            'STANDARD': """You are analyzing {token} in NORMAL MARKET conditions.

MARKET CONTEXT:
- Standard volatility
- Normal liquidity
- Balanced sentiment
- No extreme signals

STANDARD FRAMEWORK:
1. Follow technical levels
2. Respect support/resistance
3. Normal position sizing (2-3%)
4. Standard stops (3-5%)
5. Typical targets (5-10%)

{data_context}

STANDARD RULES:
- Confidence threshold: 60%
- Balanced analysis
- Risk/reward > 2:1
- Follow trend direction
- Normal risk management

Provide balanced standard analysis."""
        }

    def get_optimal_prompt(self, token: str, market_conditions: Dict, data_context: str) -> str:
        """Select and customize the optimal prompt for current conditions"""

        # Determine market scenario
        scenario = self._determine_scenario(market_conditions)

        # Get base template
        template = self.prompt_templates.get(scenario, self.prompt_templates['STANDARD'])

        # Prepare context variables
        context_vars = {
            'token': token,
            'data_context': data_context,
            'btc_change': market_conditions.get('btc_change', 0),
            'atr': market_conditions.get('atr', 3),
            'suggested_stop': market_conditions.get('atr', 3) * 1.5,
            'suggested_tp': market_conditions.get('atr', 3) * 2.5,
            'liq_velocity': market_conditions.get('liquidation_velocity', 0),
            'liq_total': market_conditions.get('liquidation_total', 0),
            'cascade_type': market_conditions.get('cascade_type', 'NONE'),
            'whale_count': market_conditions.get('whale_count', 0),
            'whale_volume': market_conditions.get('whale_volume', 0),
            'spread': market_conditions.get('spread', 0.1),
            'slippage': market_conditions.get('slippage', 0.1),
            'sentiment': market_conditions.get('sentiment', 0),
            'sentiment_label': market_conditions.get('sentiment_label', 'neutral'),
            'tweet_volume': market_conditions.get('tweet_volume_spike', 1),
            'dominant_emotion': market_conditions.get('dominant_emotion', 'neutral'),
            'normal_corr': market_conditions.get('normal_correlation', 0.7),
            'current_corr': market_conditions.get('current_correlation', 0.7),
            'corr_deviation': abs(market_conditions.get('correlation_deviation', 0))
        }

        # Format template with context
        prompt = template.format(**context_vars)

        # Add performance-based adjustments
        prompt += self._add_performance_insights(token, scenario)

        return prompt

    def _determine_scenario(self, conditions: Dict) -> str:
        """Determine the market scenario from conditions"""

        # Check for crisis conditions first
        if conditions.get('liquidation_velocity', 0) > 5:
            return 'LIQUIDATION_CASCADE'

        if conditions.get('crash_probability', 0) > 50:
            return 'BEAR_MARKET'

        # Check for high volatility
        if conditions.get('atr', 3) > 7:
            return 'HIGH_VOLATILITY'

        # Check for low liquidity
        if conditions.get('spread', 0) > 0.5:
            return 'LOW_LIQUIDITY'

        # Check for whale activity
        if conditions.get('whale_volume', 0) > 1000000:
            return 'WHALE_ACCUMULATION'

        # Check for sentiment extremes
        if abs(conditions.get('sentiment', 0)) > 0.8:
            return 'SENTIMENT_EXTREME'

        # Check for correlation breakdown
        if abs(conditions.get('correlation_deviation', 0)) > 2:
            return 'CORRELATION_BREAK'

        # Market regime
        btc_change = conditions.get('btc_change', 0)
        if btc_change > 5:
            return 'BULL_MARKET'
        elif btc_change < -5:
            return 'BEAR_MARKET'

        return 'STANDARD'

    def _add_performance_insights(self, token: str, scenario: str) -> str:
        """
        Add performance-based insights to prompt
        ENHANCED: Now includes sample sizes and statistical confidence warnings
        """

        insights = "\n\nPERFORMANCE INSIGHTS (with statistical confidence):\n"

        # Get model performance for this scenario
        best_model = self.get_best_model_for_scenario(scenario)
        if best_model:
            sample_size = best_model.get('total_trades', 0)
            insights += f"- Best model for {scenario}: {best_model['name']} (win rate: {best_model['win_rate']:.1f}%, {sample_size} trades)\n"

            # Add statistical warning if sample size is small
            if sample_size < 20:
                insights += f"  ⚠️ WARNING: Small sample size ({sample_size} trades) - treat with caution\n"
            elif sample_size < 50:
                insights += f"  ℹ️ NOTE: Moderate sample size ({sample_size} trades) - some uncertainty remains\n"

        # Add token-specific insights with sample size
        token_performance = self.get_token_performance(token)
        if token_performance:
            token_trades = token_performance.get('total_trades', 0)
            insights += f"- {token} historical win rate: {token_performance['win_rate']:.1f}% ({token_trades} trades)\n"

            # Statistical confidence indicator
            if token_trades >= 30:
                confidence = "HIGH confidence"
            elif token_trades >= 15:
                confidence = "MODERATE confidence"
            else:
                confidence = "LOW confidence - insufficient data"

            insights += f"  Statistical confidence: {confidence}\n"

            if token_trades > 0:
                insights += f"- Best entry pattern: {token_performance.get('best_pattern', 'Unknown')}\n"
                insights += f"- Average winning trade: +{token_performance.get('avg_win', 5):.1f}%\n"

            # Warn if sample size is very small
            if token_trades < 10:
                insights += f"  ⚠️ CRITICAL: Only {token_trades} historical trades - predictions highly uncertain\n"

        # Add recent performance with sample size
        recent = self.get_recent_performance(hours=24)
        if recent:
            recent_count = recent.get('total_trades', 0)
            insights += f"- Last 24h: {recent['success_rate']:.1f}% success rate ({recent_count} trades)\n"
            insights += f"- Recent bias: {recent.get('bias', 'Neutral')}\n"

            if recent_count < 5:
                insights += f"  ℹ️ NOTE: Limited recent activity ({recent_count} trades in 24h)\n"

        # Add overall statistical health check
        insights += "\nSTATISTICAL HEALTH:\n"
        if token_performance and token_performance.get('total_trades', 0) >= 30:
            insights += "- ✅ Sufficient historical data for reliable predictions\n"
        elif token_performance and token_performance.get('total_trades', 0) >= 10:
            insights += "- ⚠️ Moderate data available - predictions have some uncertainty\n"
        else:
            insights += "- 🚨 INSUFFICIENT DATA - high prediction uncertainty, use extreme caution\n"

        return insights

    def calculate_dynamic_weights(self, scenario: str) -> Dict[str, float]:
        """Calculate optimal model weights based on performance"""

        weights = {
            'claude': 0.40,  # Default
            'deepseek': 0.35,
            'gemini': 0.25
        }

        # Adjust based on recent performance
        for model in weights.keys():
            perf = self.model_performance.get(model, {})

            # Recent performance (last 30 days)
            if perf.get('last_30_days'):
                recent_wins = sum(1 for t in perf['last_30_days'] if t['profitable'])
                recent_total = len(perf['last_30_days'])

                if recent_total > 10:  # Enough data
                    win_rate = recent_wins / recent_total

                    # Adjust weight based on performance
                    if win_rate > 0.6:  # Good performance
                        weights[model] *= 1.2
                    elif win_rate < 0.4:  # Poor performance
                        weights[model] *= 0.8

        # Normalize weights
        total = sum(weights.values())
        return {k: v/total for k, v in weights.items()}

    def track_decision(self, model: str, token: str, decision: Dict, outcome: Optional[Dict] = None):
        """Track model decision for performance analysis"""

        try:
            with self.conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO model_performance
                    (model_name, token, decision_action, confidence, position_size,
                     scenario, timestamp, outcome, pnl, profitable)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    model, token, decision.get('action'),
                    decision.get('confidence'), decision.get('position_size'),
                    decision.get('scenario'), datetime.now(),
                    json.dumps(outcome) if outcome else None,
                    outcome.get('pnl') if outcome else None,
                    outcome.get('profitable') if outcome else None
                ))
                self.conn.commit()

                # Update in-memory tracking
                if outcome:
                    perf = self.model_performance[model]
                    perf['trades'] += 1
                    if outcome.get('profitable'):
                        perf['wins'] += 1
                    perf['total_pnl'] += outcome.get('pnl', 0)

                    # Track last 30 days
                    perf['last_30_days'].append({
                        'timestamp': datetime.now(),
                        'profitable': outcome.get('profitable', False),
                        'pnl': outcome.get('pnl', 0)
                    })

                    # Keep only last 30 days
                    cutoff = datetime.now() - timedelta(days=30)
                    perf['last_30_days'] = [
                        t for t in perf['last_30_days']
                        if t['timestamp'] > cutoff
                    ]

        except Exception as e:
            print(f"[ERROR] Failed to track decision: {e}")

    def get_best_model_for_scenario(self, scenario: str) -> Optional[Dict]:
        """Get the best performing model for a specific scenario"""

        try:
            with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT
                        model_name,
                        COUNT(*) as total_trades,
                        SUM(CASE WHEN profitable THEN 1 ELSE 0 END) as wins,
                        AVG(pnl) as avg_pnl,
                        SUM(CASE WHEN profitable THEN 1 ELSE 0 END)::float / COUNT(*) * 100 as win_rate
                    FROM model_performance
                    WHERE scenario = %s
                    AND timestamp > NOW() - INTERVAL '30 days'
                    GROUP BY model_name
                    HAVING COUNT(*) > 5
                    ORDER BY win_rate DESC
                    LIMIT 1
                """, (scenario,))

                result = cursor.fetchone()
                if result:
                    return {
                        'name': result['model_name'],
                        'win_rate': float(result['win_rate']),
                        'avg_pnl': float(result['avg_pnl']),
                        'total_trades': int(result['total_trades'])
                    }
                return None

        except Exception as e:
            print(f"[ERROR] Failed to get best model: {e}")
            return None

    def get_token_performance(self, token: str) -> Optional[Dict]:
        """Get historical performance for a specific token"""

        try:
            with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT
                        COUNT(*) as total_trades,
                        SUM(CASE WHEN profitable THEN 1 ELSE 0 END) as wins,
                        AVG(CASE WHEN profitable THEN pnl ELSE 0 END) as avg_win,
                        AVG(CASE WHEN NOT profitable THEN pnl ELSE 0 END) as avg_loss,
                        SUM(CASE WHEN profitable THEN 1 ELSE 0 END)::float / COUNT(*) * 100 as win_rate
                    FROM model_performance
                    WHERE token = %s
                    AND timestamp > NOW() - INTERVAL '30 days'
                    HAVING COUNT(*) > 3
                """, (token,))

                result = cursor.fetchone()
                if result:
                    return {
                        'win_rate': float(result['win_rate']) if result['win_rate'] else 50,
                        'avg_win': abs(float(result['avg_win'])) if result['avg_win'] else 5,
                        'avg_loss': abs(float(result['avg_loss'])) if result['avg_loss'] else 3,
                        'total_trades': int(result['total_trades'])
                    }
                return None

        except Exception as e:
            print(f"[ERROR] Failed to get token performance: {e}")
            return None

    def get_recent_performance(self, hours: int = 24) -> Optional[Dict]:
        """Get recent overall performance"""

        try:
            with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT
                        COUNT(*) as total,
                        SUM(CASE WHEN profitable THEN 1 ELSE 0 END) as wins,
                        AVG(confidence) as avg_confidence,
                        SUM(pnl) as total_pnl
                    FROM model_performance
                    WHERE timestamp > NOW() - INTERVAL '1 hour' * %s
                """, (hours,))

                result = cursor.fetchone()
                if result and result['total'] > 0:
                    success_rate = (result['wins'] / result['total']) * 100

                    # Determine bias
                    bias = 'Neutral'
                    if success_rate > 60:
                        bias = 'Bullish (winning)'
                    elif success_rate < 40:
                        bias = 'Bearish (losing)'

                    return {
                        'success_rate': success_rate,
                        'total_trades': int(result['total']),
                        'avg_confidence': float(result['avg_confidence']) if result['avg_confidence'] else 0.7,
                        'total_pnl': float(result['total_pnl']) if result['total_pnl'] else 0,
                        'bias': bias
                    }
                return None

        except Exception as e:
            print(f"[ERROR] Failed to get recent performance: {e}")
            return None

    def suggest_improvements(self) -> List[str]:
        """Suggest improvements based on performance analysis"""

        suggestions = []

        # Analyze each model
        for model, perf in self.model_performance.items():
            if perf['trades'] > 20:
                win_rate = (perf['wins'] / perf['trades']) * 100

                if win_rate < 45:
                    suggestions.append(f"Consider reducing {model} weight (win rate: {win_rate:.1f}%)")
                elif win_rate > 55:
                    suggestions.append(f"Consider increasing {model} weight (win rate: {win_rate:.1f}%)")

                # Check for false positives
                if perf['false_positives'] > perf['trades'] * 0.3:
                    suggestions.append(f"{model} has high false positives - increase confidence threshold")

        # Check overall performance
        recent = self.get_recent_performance(hours=168)  # Last week
        if recent:
            if recent['success_rate'] < 45:
                suggestions.append("Overall performance is poor - consider more conservative thresholds")

            if recent['avg_confidence'] > 0.8 and recent['success_rate'] < 50:
                suggestions.append("High confidence but low success - models may be overconfident")

        return suggestions

    def load_model_performance(self):
        """Load historical model performance from database"""

        try:
            # Create table if not exists
            with self.conn.cursor() as cursor:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS model_performance (
                        id SERIAL PRIMARY KEY,
                        model_name VARCHAR(50),
                        token VARCHAR(20),
                        decision_action VARCHAR(10),
                        confidence FLOAT,
                        position_size FLOAT,
                        scenario VARCHAR(50),
                        timestamp TIMESTAMP,
                        outcome JSONB,
                        pnl FLOAT,
                        profitable BOOLEAN,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # Create indexes
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_model_performance_model ON model_performance(model_name);
                    CREATE INDEX IF NOT EXISTS idx_model_performance_token ON model_performance(token);
                    CREATE INDEX IF NOT EXISTS idx_model_performance_scenario ON model_performance(scenario);
                    CREATE INDEX IF NOT EXISTS idx_model_performance_timestamp ON model_performance(timestamp);
                """)

                self.conn.commit()

                # Load recent performance
                cursor.execute("""
                    SELECT
                        model_name,
                        COUNT(*) as trades,
                        SUM(CASE WHEN profitable THEN 1 ELSE 0 END) as wins,
                        SUM(pnl) as total_pnl
                    FROM model_performance
                    WHERE timestamp > NOW() - INTERVAL '30 days'
                    GROUP BY model_name
                """)

                for row in cursor.fetchall():
                    model = row[0]
                    self.model_performance[model]['trades'] = row[1]
                    self.model_performance[model]['wins'] = row[2]
                    self.model_performance[model]['total_pnl'] = float(row[3]) if row[3] else 0

        except Exception as e:
            print(f"[ERROR] Failed to load model performance: {e}")

    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()