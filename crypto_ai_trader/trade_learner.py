"""
Advanced Trade Learning System with Self-Improvement Capabilities
Based on latest 2025 reinforcement learning and self-rewarding mechanisms
"""

import numpy as np
import json
import psycopg2
import psycopg2.extras
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from collections import defaultdict, deque
import pickle
import os
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
import warnings
warnings.filterwarnings('ignore')

# ============================================================================
# OVERFITTING PREVENTION CONSTANTS
# ============================================================================
# Adjust these to balance learning speed vs overfitting risk

# Minimum samples required before trusting a pattern
MIN_PATTERN_SAMPLES_HIGH_CONFIDENCE = 20  # For patterns claiming >70% success
MIN_PATTERN_SAMPLES_MEDIUM_CONFIDENCE = 15  # For patterns claiming 60-70% success
MIN_PATTERN_SAMPLES_LOW_CONFIDENCE = 10  # For patterns claiming 50-60% success

# Parameter drift limits (prevent wild swings)
MAX_PARAM_CHANGE_PER_GENERATION = 0.15  # Max 15% change per evolution
MIN_CONFIDENCE_THRESHOLD_FLOOR = 0.50  # Never go below 50% confidence
MAX_CONFIDENCE_THRESHOLD_CEILING = 0.85  # Never exceed 85% confidence

# Overfitting detection thresholds
OVERFITTING_DETECTION_WINDOW = 50  # Check last 50 trades vs previous 50
OVERFITTING_PERFORMANCE_DROP_THRESHOLD = 0.30  # Alert if performance drops >30%

# Strategy rollback settings
ENABLE_STRATEGY_ROLLBACK = True  # Rollback to previous generation if fitness drops
ROLLBACK_FITNESS_THRESHOLD = 0.70  # Rollback if fitness drops below 70% of best

# Statistical confidence for regime-specific patterns
MIN_TRADES_PER_REGIME = 30  # Need 30+ trades in a regime before trusting regime-specific patterns

class TradeLearner:
    """
    Self-improving trade learning system that continuously evolves strategies
    Based on Self-Rewarding Deep Reinforcement Learning (SRDRL) principles
    """

    def __init__(self, db_config: Dict):
        """Initialize the trade learning system"""
        self.db_config = db_config
        self.conn = psycopg2.connect(
            host=db_config['host'],
            port=db_config['port'],
            database=db_config['database'],
            user=db_config['user'],
            password=db_config['password']
        )

        # Experience replay buffer (stores trading experiences)
        self.experience_buffer = deque(maxlen=10000)

        # Strategy evolution tracking
        self.strategy_evolution = {
            'generations': [],
            'current_generation': 0,
            'best_strategies': []
        }

        # Performance metrics
        self.performance_metrics = {
            'sharpe_ratio': 0,
            'sortino_ratio': 0,
            'max_drawdown': 0,
            'win_rate': 0,
            'profit_factor': 0,
            'avg_trade_duration': 0,
            'total_trades': 0,
            'profitable_trades': 0
        }

        # Pattern recognition memory
        self.pattern_memory = {}
        self.successful_patterns = []
        self.failed_patterns = []

        # Self-rewarding network
        self.reward_network = {
            'expert_rewards': {},  # Expert-labeled rewards (from profitable trades)
            'predicted_rewards': {},  # Self-predicted rewards
            'reward_history': deque(maxlen=1000)
        }

        # Strategy parameters (will evolve over time)
        self.strategy_params = self._initialize_strategy_params()

        # Feature importance tracking
        self.feature_importance = defaultdict(float)

        # ===== OVERFITTING PREVENTION ADDITIONS =====

        # Regime-specific performance tracking
        self.regime_performance = {
            'BULL': {'trades': 0, 'wins': 0, 'total_pnl': 0},
            'BEAR': {'trades': 0, 'wins': 0, 'total_pnl': 0},
            'SIDEWAYS': {'trades': 0, 'wins': 0, 'total_pnl': 0},
            'HIGH_VOLATILITY': {'trades': 0, 'wins': 0, 'total_pnl': 0}
        }

        # Overfitting detection tracking
        self.overfitting_metrics = {
            'recent_window_performance': [],  # Last N trades performance
            'previous_window_performance': [],  # Previous N trades performance
            'overfitting_alerts': [],
            'last_validation_check': None
        }

        # Strategy rollback capability
        self.strategy_history = deque(maxlen=10)  # Keep last 10 strategy versions
        self.best_strategy_fitness = 0
        self.best_strategy_params = None

        # Load saved state if exists
        self.load_state()

        # Initialize database tables
        self._initialize_database()

        print("[TradeLearner] Initialized with self-improvement capabilities")
        print("[TradeLearner] Overfitting prevention: ENABLED")

    def _initialize_strategy_params(self) -> Dict:
        """Initialize evolving strategy parameters"""
        return {
            # Entry conditions
            'min_confidence_threshold': 0.60,
            'sentiment_weight': 0.25,
            'technical_weight': 0.25,
            'volume_weight': 0.20,
            'momentum_weight': 0.15,
            'liquidity_weight': 0.15,

            # Risk management
            'stop_loss_multiplier': 1.5,  # x ATR
            'take_profit_multiplier': 2.5,  # x risk
            'max_correlation': 0.7,
            'max_positions': 5,

            # Market regime adjustments
            'bull_confidence_adj': -0.05,  # Lower threshold in bull
            'bear_confidence_adj': 0.10,   # Higher threshold in bear
            'volatile_size_adj': 0.5,      # Reduce size in volatile

            # Pattern recognition
            'pattern_confidence_boost': 0.10,
            'whale_signal_weight': 0.30,
            'cascade_exit_threshold': 60,

            # Time-based rules
            'max_hold_hours': 48,
            'min_hold_minutes': 30,
            'news_blackout_minutes': 15,

            # Meta parameters
            'learning_rate': 0.01,
            'exploration_rate': 0.10,
            'adaptation_speed': 0.05
        }

    def _initialize_database(self):
        """Create tables for trade learning"""
        try:
            with self.conn.cursor() as cursor:
                # Trade experiences table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS trade_experiences (
                        id SERIAL PRIMARY KEY,
                        token VARCHAR(20),
                        entry_context JSONB,
                        decision JSONB,
                        outcome JSONB,
                        reward FLOAT,
                        self_reward FLOAT,
                        pattern_hash VARCHAR(64),
                        strategy_version INT,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # Strategy evolution table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS strategy_evolution (
                        generation INT PRIMARY KEY,
                        parameters JSONB,
                        performance JSONB,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        parent_generation INT
                    )
                """)

                # Pattern memory table (enhanced with regime tracking)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS pattern_memory (
                        pattern_hash VARCHAR(64) PRIMARY KEY,
                        pattern_features JSONB,
                        occurrences INT DEFAULT 1,
                        success_rate FLOAT,
                        avg_profit FLOAT,
                        last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        regime VARCHAR(20),
                        statistical_confidence FLOAT,
                        regime_occurrences JSONB DEFAULT '{}'::jsonb
                    )
                """)

                # Learning metrics table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS learning_metrics (
                        timestamp TIMESTAMP PRIMARY KEY,
                        sharpe_ratio FLOAT,
                        win_rate FLOAT,
                        avg_profit FLOAT,
                        exploration_rate FLOAT,
                        strategy_fitness FLOAT
                    )
                """)

                self.conn.commit()
                print("[TradeLearner] Database tables initialized")

        except Exception as e:
            print(f"[ERROR] Failed to initialize database: {e}")
            self.conn.rollback()

    def record_trade_experience(self, token: str, context: Dict, decision: Dict, outcome: Dict):
        """
        Record a complete trade experience for learning
        This is the core of the self-improvement system
        """
        try:
            # Calculate rewards
            actual_reward = self._calculate_actual_reward(outcome)
            predicted_reward = self._predict_reward(context, decision)

            # Self-rewarding mechanism: use higher of actual vs predicted
            # This is based on SRDRL (Self-Rewarding Deep RL) approach
            self_reward = max(actual_reward, predicted_reward)

            # Extract pattern hash for pattern recognition
            pattern_hash = self._extract_pattern_hash(context, decision)

            # Store experience
            experience = {
                'token': token,
                'context': context,
                'decision': decision,
                'outcome': outcome,
                'actual_reward': actual_reward,
                'predicted_reward': predicted_reward,
                'self_reward': self_reward,
                'pattern_hash': pattern_hash,
                'timestamp': datetime.now()
            }

            # Add to experience buffer
            self.experience_buffer.append(experience)

            # Store in database
            with self.conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO trade_experiences
                    (token, entry_context, decision, outcome, reward, self_reward, pattern_hash, strategy_version)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    token,
                    json.dumps(context),
                    json.dumps(decision),
                    json.dumps(outcome),
                    actual_reward,
                    self_reward,
                    pattern_hash,
                    self.strategy_evolution['current_generation']
                ))
                self.conn.commit()

            # Update pattern memory
            self._update_pattern_memory(pattern_hash, context, outcome)

            # Learn from experience immediately
            self._learn_from_experience(experience)

            # Update feature importance
            self._update_feature_importance(context, outcome)

            # Check if strategy evolution needed
            if len(self.experience_buffer) % 50 == 0:  # Every 50 trades
                self._evolve_strategy()

            print(f"[LEARN] Recorded experience - Reward: {actual_reward:.3f}, Self-reward: {self_reward:.3f}")

        except Exception as e:
            print(f"[ERROR] Failed to record experience: {e}")

    def _calculate_actual_reward(self, outcome: Dict) -> float:
        """
        Calculate actual reward from trade outcome
        Uses dynamic reward function based on Sharpe/Sortino ratios
        """
        if not outcome:
            return -1.0

        # Base reward from profit/loss
        pnl_pct = outcome.get('pnl_pct', 0)
        base_reward = pnl_pct / 100  # Normalize to [-1, 1] range

        # Risk-adjusted reward components
        risk_adjustment = 1.0

        # Sharpe ratio component (profit vs volatility)
        if 'volatility' in outcome and outcome['volatility'] > 0:
            sharpe_component = pnl_pct / outcome['volatility']
            risk_adjustment *= (1 + sharpe_component * 0.1)

        # Sortino ratio component (profit vs downside volatility)
        if 'max_drawdown' in outcome and outcome['max_drawdown'] < 0:
            sortino_component = pnl_pct / abs(outcome['max_drawdown'])
            risk_adjustment *= (1 + sortino_component * 0.1)

        # Time efficiency bonus
        hold_time = outcome.get('hold_time_hours', 24)
        if pnl_pct > 0:
            time_bonus = 1 + (24 / max(hold_time, 1)) * 0.1  # Bonus for quick profits
        else:
            time_bonus = 1 - (hold_time / 48) * 0.1  # Penalty for long losses

        # Calculate final reward
        reward = base_reward * risk_adjustment * time_bonus

        # Clip to reasonable range
        return np.clip(reward, -1.0, 1.0)

    def _predict_reward(self, context: Dict, decision: Dict) -> float:
        """
        Predict expected reward using self-learning network
        This creates the self-rewarding mechanism
        """
        # Extract key features
        features = self._extract_features(context, decision)

        # Look for similar past experiences
        similar_experiences = self._find_similar_experiences(features)

        if not similar_experiences:
            # No history, use confidence as proxy
            return (decision.get('confidence', 0.6) - 0.6) * 2  # Map [0.6, 1] to [0, 0.8]

        # Calculate weighted average of past rewards
        weights = []
        rewards = []

        for exp in similar_experiences:
            similarity = self._calculate_similarity(features, exp['features'])
            weights.append(similarity)
            rewards.append(exp['reward'])

        # Weighted average prediction
        if weights:
            predicted = np.average(rewards, weights=weights)
        else:
            predicted = 0

        # Add exploration bonus (encourage trying new things)
        exploration_bonus = self.strategy_params['exploration_rate'] * np.random.randn() * 0.1
        predicted += exploration_bonus

        return np.clip(predicted, -1.0, 1.0)

    def _extract_pattern_hash(self, context: Dict, decision: Dict) -> str:
        """Extract unique pattern identifier from context"""
        # Key features that define a pattern
        pattern_features = {
            'action': decision.get('action'),
            'confidence_range': int(decision.get('confidence', 0.6) * 10),
            'sentiment': int(context.get('sentiment', {}).get('avg_sentiment', 0) * 10),
            'volume_spike': context.get('quick_summary', {}).get('volume_spike', 1) > 2,
            'market_regime': context.get('market_regime', 'UNKNOWN'),
            'liquidation_risk': context.get('liquidation_cascade', {}).get('risk_score', 0) > 50
        }

        # Create hash
        import hashlib
        pattern_str = json.dumps(pattern_features, sort_keys=True)
        return hashlib.sha256(pattern_str.encode()).hexdigest()[:16]

    def _update_pattern_memory(self, pattern_hash: str, context: Dict, outcome: Dict):
        """Update pattern recognition memory WITH REGIME TRACKING"""
        try:
            # Get current market regime
            regime = context.get('market_regime', 'UNKNOWN')

            with self.conn.cursor() as cursor:
                # Check if pattern exists
                cursor.execute("""
                    SELECT occurrences, success_rate, avg_profit, regime_occurrences
                    FROM pattern_memory
                    WHERE pattern_hash = %s
                """, (pattern_hash,))

                result = cursor.fetchone()

                # Calculate if this trade was successful
                is_success = outcome.get('pnl_pct', 0) > 0

                if result:
                    # Update existing pattern
                    occurrences = result[0] + 1
                    old_success_rate = result[1]
                    old_avg_profit = result[2]
                    regime_occurrences = result[3] if result[3] else {}

                    # Parse regime_occurrences if it's a string
                    if isinstance(regime_occurrences, str):
                        regime_occurrences = json.loads(regime_occurrences)

                    # Update regime-specific counts
                    regime_occurrences[regime] = regime_occurrences.get(regime, 0) + 1

                    # Update with new outcome
                    new_success_rate = ((old_success_rate * result[0]) + (1 if is_success else 0)) / occurrences
                    new_avg_profit = ((old_avg_profit * result[0]) + outcome.get('pnl_pct', 0)) / occurrences

                    # Calculate statistical confidence (0-1 scale based on sample size)
                    # Higher confidence with more samples, capped at 1.0
                    stat_confidence = min(occurrences / 50, 1.0)  # Max confidence at 50+ samples

                    cursor.execute("""
                        UPDATE pattern_memory
                        SET occurrences = %s, success_rate = %s, avg_profit = %s, last_seen = %s,
                            regime = %s, statistical_confidence = %s, regime_occurrences = %s
                        WHERE pattern_hash = %s
                    """, (occurrences, new_success_rate, new_avg_profit, datetime.now(),
                          regime, stat_confidence, json.dumps(regime_occurrences), pattern_hash))

                else:
                    # New pattern - initialize with current regime
                    initial_regime_occurrences = {regime: 1}
                    initial_stat_confidence = 0.02  # Very low confidence with 1 sample

                    cursor.execute("""
                        INSERT INTO pattern_memory
                        (pattern_hash, pattern_features, occurrences, success_rate, avg_profit,
                         regime, statistical_confidence, regime_occurrences)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        pattern_hash,
                        json.dumps(self._extract_features(context, {})),
                        1,
                        1.0 if is_success else 0.0,
                        outcome.get('pnl_pct', 0),
                        regime,
                        initial_stat_confidence,
                        json.dumps(initial_regime_occurrences)
                    ))

                self.conn.commit()

                # === UPDATE REGIME PERFORMANCE TRACKING ===
                if regime in self.regime_performance:
                    self.regime_performance[regime]['trades'] += 1
                    if is_success:
                        self.regime_performance[regime]['wins'] += 1
                    self.regime_performance[regime]['total_pnl'] += outcome.get('pnl_pct', 0)

        except Exception as e:
            print(f"[ERROR] Failed to update pattern memory: {e}")
            self.conn.rollback()

    def _learn_from_experience(self, experience: Dict):
        """
        Core learning algorithm - updates strategy parameters
        Based on experience replay and gradient ascent
        """
        # Extract components
        context = experience['context']
        decision = experience['decision']
        outcome = experience['outcome']
        reward = experience['self_reward']

        # Learning rate decay
        lr = self.strategy_params['learning_rate'] * (0.99 ** (self.strategy_evolution['current_generation'] / 10))

        # Update confidence threshold based on outcome
        if reward > 0:
            # Good trade - slightly lower threshold for similar setups
            self.strategy_params['min_confidence_threshold'] *= (1 - lr * 0.1)
        else:
            # Bad trade - raise threshold
            self.strategy_params['min_confidence_threshold'] *= (1 + lr * 0.2)

        # Update feature weights based on reward
        if 'scores' in decision:
            scores = decision['scores']
            total_score = sum(scores.values())

            for feature, score in scores.items():
                weight_key = f"{feature}_weight"
                if weight_key in self.strategy_params:
                    # Increase weight if feature contributed to good trade
                    contribution = (score / total_score) if total_score > 0 else 0.2
                    adjustment = lr * reward * contribution
                    self.strategy_params[weight_key] *= (1 + adjustment)

        # Update risk parameters based on outcome
        if 'max_drawdown' in outcome:
            if abs(outcome['max_drawdown']) > 5:
                # Too much drawdown - tighten stops
                self.strategy_params['stop_loss_multiplier'] *= (1 - lr * 0.1)

        # Update hold time based on outcome
        if 'hold_time_hours' in outcome:
            if reward > 0 and outcome['hold_time_hours'] < 12:
                # Quick profitable trade - allow shorter holds
                self.strategy_params['min_hold_minutes'] *= (1 - lr * 0.1)
            elif reward < 0 and outcome['hold_time_hours'] > 36:
                # Long losing trade - reduce max hold
                self.strategy_params['max_hold_hours'] *= (1 - lr * 0.1)

        # Normalize weights
        self._normalize_strategy_weights()

        # Update exploration rate (decay over time)
        self.strategy_params['exploration_rate'] *= 0.995

        print(f"[LEARN] Strategy updated - Confidence threshold: {self.strategy_params['min_confidence_threshold']:.3f}")

    def _evolve_strategy(self):
        """
        Evolve strategy through genetic algorithm approach WITH OVERFITTING PROTECTION
        Creates new generation of parameters based on performance

        ENHANCED: Now includes parameter drift limits and strategy rollback
        """
        print("\n[EVOLUTION] Starting strategy evolution...")

        # Calculate current fitness
        current_fitness = self._calculate_strategy_fitness()

        # === STRATEGY ROLLBACK CHECK ===
        # Track best fitness and rollback if performance degrades significantly
        if current_fitness > self.best_strategy_fitness:
            # New best fitness - save this strategy
            self.best_strategy_fitness = current_fitness
            self.best_strategy_params = self.strategy_params.copy()
            print(f"[EVOLUTION] New best fitness: {current_fitness:.3f}")
        elif ENABLE_STRATEGY_ROLLBACK and self.best_strategy_params:
            # Check if we should rollback
            if current_fitness < self.best_strategy_fitness * ROLLBACK_FITNESS_THRESHOLD:
                print(f"[EVOLUTION] ⚠️ Fitness dropped to {current_fitness:.3f} (best: {self.best_strategy_fitness:.3f})")
                print(f"[EVOLUTION] 🔄 ROLLING BACK to previous best strategy")
                self.strategy_params = self.best_strategy_params.copy()
                # Skip evolution this time - just rollback
                self.save_state()
                return

        # Save current strategy to history before evolving
        self.strategy_history.append({
            'generation': self.strategy_evolution['current_generation'],
            'params': self.strategy_params.copy(),
            'fitness': current_fitness,
            'timestamp': datetime.now()
        })

        # Store current generation in database
        with self.conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO strategy_evolution (generation, parameters, performance)
                VALUES (%s, %s, %s)
            """, (
                self.strategy_evolution['current_generation'],
                json.dumps(self.strategy_params),
                json.dumps({
                    'fitness': current_fitness,
                    'sharpe_ratio': self.performance_metrics['sharpe_ratio'],
                    'win_rate': self.performance_metrics['win_rate']
                })
            ))
            self.conn.commit()

        # Save current params for drift comparison
        old_params = self.strategy_params.copy()

        # === MUTATION WITH DRIFT LIMITS ===
        for param, value in self.strategy_params.items():
            if isinstance(value, (int, float)) and not param.startswith('exploration'):
                # Small random mutation
                mutation = np.random.normal(0, 0.02)  # 2% standard deviation

                # Apply mutation
                new_value = value * (1 + mutation)

                # === ENFORCE DRIFT LIMITS ===
                max_change = abs(value * MAX_PARAM_CHANGE_PER_GENERATION)
                if abs(new_value - value) > max_change:
                    # Limit the change
                    if new_value > value:
                        new_value = value + max_change
                    else:
                        new_value = value - max_change

                # Special limits for confidence threshold
                if param == 'min_confidence_threshold':
                    new_value = np.clip(new_value, MIN_CONFIDENCE_THRESHOLD_FLOOR, MAX_CONFIDENCE_THRESHOLD_CEILING)

                # Special limits for weights (must be 0-1)
                if param.endswith('_weight'):
                    new_value = np.clip(new_value, 0.01, 0.99)

                self.strategy_params[param] = new_value

        # Crossover with best historical strategy
        best_strategy = self._get_best_historical_strategy()
        if best_strategy:
            # Mix current with best historical (genetic crossover)
            for param in self.strategy_params:
                if param in best_strategy and np.random.random() < 0.3:  # 30% chance
                    self.strategy_params[param] = best_strategy[param]

        # Report parameter changes
        significant_changes = []
        for param, old_val in old_params.items():
            if isinstance(old_val, (int, float)):
                new_val = self.strategy_params[param]
                pct_change = ((new_val - old_val) / old_val * 100) if old_val != 0 else 0
                if abs(pct_change) > 5:  # Report changes > 5%
                    significant_changes.append(f"{param}: {pct_change:+.1f}%")

        if significant_changes:
            print(f"[EVOLUTION] Significant parameter changes: {', '.join(significant_changes)}")

        # Increment generation
        self.strategy_evolution['current_generation'] += 1

        print(f"[EVOLUTION] Evolved to generation {self.strategy_evolution['current_generation']}")
        print(f"[EVOLUTION] Current fitness: {current_fitness:.3f} (best: {self.best_strategy_fitness:.3f})")

        # Save state
        self.save_state()

    def _calculate_strategy_fitness(self) -> float:
        """Calculate fitness score for current strategy"""
        # Multi-objective fitness function
        fitness = 0

        # Sharpe ratio component (risk-adjusted returns)
        fitness += self.performance_metrics['sharpe_ratio'] * 0.3

        # Win rate component
        fitness += self.performance_metrics['win_rate'] * 0.25

        # Profit factor component
        if self.performance_metrics['profit_factor'] > 0:
            fitness += min(self.performance_metrics['profit_factor'], 3.0) * 0.2

        # Drawdown penalty
        fitness -= abs(self.performance_metrics['max_drawdown']) * 0.15

        # Trade frequency bonus (not too few, not too many)
        ideal_trades_per_day = 5
        if self.performance_metrics['total_trades'] > 0:
            trade_frequency = self.performance_metrics['total_trades'] / max(1, self.strategy_evolution['current_generation'])
            frequency_score = 1 - abs(trade_frequency - ideal_trades_per_day) / ideal_trades_per_day
            fitness += frequency_score * 0.1

        return fitness

    def suggest_trade_adjustments(self, token: str, context: Dict) -> Dict:
        """
        Suggest adjustments based on learned patterns WITH OVERFITTING PREVENTION
        This is called before trades to improve decisions

        ENHANCED: Now includes sample size validation, regime awareness, and statistical confidence
        """
        suggestions = {
            'confidence_adjustment': 0,
            'position_size_multiplier': 1.0,
            'stop_loss_adjustment': 0,
            'take_profit_adjustment': 0,
            'action_override': None,
            'reasoning': [],
            'statistical_warnings': []  # NEW: Warnings about data quality
        }

        # Get current market regime
        regime = context.get('market_regime', 'UNKNOWN')

        # Check pattern memory WITH SAMPLE SIZE VALIDATION
        pattern_hash = self._extract_pattern_hash(context, {'action': 'BUY'})
        pattern_performance = self._get_pattern_performance_with_validation(pattern_hash, regime)

        if pattern_performance:
            success_rate = pattern_performance['success_rate']
            occurrences = pattern_performance['occurrences']

            # === SAMPLE SIZE VALIDATION ===
            # Determine minimum required samples based on claimed success rate
            if success_rate > 0.7:
                min_required = MIN_PATTERN_SAMPLES_HIGH_CONFIDENCE
                confidence_level = "high"
            elif success_rate > 0.6:
                min_required = MIN_PATTERN_SAMPLES_MEDIUM_CONFIDENCE
                confidence_level = "medium"
            else:
                min_required = MIN_PATTERN_SAMPLES_LOW_CONFIDENCE
                confidence_level = "low"

            # Check if we have enough samples
            if occurrences < min_required:
                # INSUFFICIENT DATA - Don't trust this pattern yet
                suggestions['statistical_warnings'].append(
                    f"Pattern only seen {occurrences} times (need {min_required}+ for {confidence_level} confidence)"
                )
                suggestions['reasoning'].append(
                    f"Pattern detected but insufficient data ({occurrences}/{min_required} samples)"
                )
                # Reduce any adjustments significantly
                pattern_trusted = False
            else:
                # SUFFICIENT DATA - Trust this pattern
                pattern_trusted = True

                # Calculate statistical confidence (0-1 scale)
                stat_confidence = min(occurrences / (min_required * 2), 1.0)  # Max out at 2x required samples

                if success_rate < 0.3:
                    # Bad pattern - avoid strongly
                    suggestions['action_override'] = 'HOLD'
                    suggestions['reasoning'].append(
                        f"Pattern has {success_rate:.1%} success rate ({occurrences} samples, {stat_confidence:.0%} confidence)"
                    )

                elif success_rate > 0.7:
                    # Great pattern - boost confidence (scaled by statistical confidence)
                    boost = 0.1 * stat_confidence  # Scale boost by statistical confidence
                    suggestions['confidence_adjustment'] = boost
                    suggestions['position_size_multiplier'] = 1.0 + (0.2 * stat_confidence)
                    suggestions['reasoning'].append(
                        f"Strong pattern: {success_rate:.1%} success ({occurrences} samples, {stat_confidence:.0%} statistical confidence)"
                    )

                elif success_rate > 0.6:
                    # Good pattern - modest boost
                    boost = 0.05 * stat_confidence
                    suggestions['confidence_adjustment'] = boost
                    suggestions['reasoning'].append(
                        f"Positive pattern: {success_rate:.1%} success ({occurrences} samples)"
                    )

            # === REGIME-SPECIFIC VALIDATION ===
            regime_trades = self.regime_performance.get(regime, {}).get('trades', 0)
            if regime_trades < MIN_TRADES_PER_REGIME and regime != 'UNKNOWN':
                suggestions['statistical_warnings'].append(
                    f"Limited experience in {regime} market ({regime_trades}/{MIN_TRADES_PER_REGIME} trades)"
                )
                # Reduce confidence in regime-specific adjustments
                suggestions['position_size_multiplier'] *= 0.9

        # Check recent performance for this token
        token_stats = self._get_token_statistics(token)
        if token_stats:
            if token_stats['recent_losses'] > 2:
                # Recent losses - be cautious
                suggestions['position_size_multiplier'] *= 0.7
                suggestions['stop_loss_adjustment'] = -1  # Tighter stop
                suggestions['reasoning'].append(f"Recent losses on {token} ({token_stats['recent_losses']} consecutive)")

            elif token_stats['recent_wins'] > 3:
                # Hot streak - increase position
                suggestions['position_size_multiplier'] *= 1.3
                suggestions['reasoning'].append(f"Winning streak on {token} ({token_stats['recent_wins']} consecutive)")

        # Check market regime adaptations
        if regime == 'BEAR':
            suggestions['confidence_adjustment'] += self.strategy_params['bear_confidence_adj']
            suggestions['reasoning'].append("Bear market adjustment (more conservative)")
        elif regime == 'BULL':
            suggestions['confidence_adjustment'] += self.strategy_params['bull_confidence_adj']
            suggestions['reasoning'].append("Bull market adjustment (more aggressive)")
        elif regime == 'HIGH_VOLATILITY':
            suggestions['position_size_multiplier'] *= 0.7  # Reduce size in high volatility
            suggestions['reasoning'].append("High volatility - reducing position size")

        # Feature importance adjustments (with total experience check)
        total_exp = len(self.experience_buffer)
        if self.feature_importance and total_exp > 50:  # Need 50+ trades before trusting feature importance
            top_features = sorted(self.feature_importance.items(), key=lambda x: x[1], reverse=True)[:3]
            for feature, importance in top_features:
                if feature in context and context[feature] > 0.7:
                    suggestions['confidence_adjustment'] += 0.05
                    suggestions['reasoning'].append(f"Strong {feature} signal (learned importance)")
        elif total_exp <= 50:
            suggestions['statistical_warnings'].append(
                f"Limited trading history ({total_exp}/50 trades) - feature importance not yet reliable"
            )

        return suggestions

    def _get_pattern_performance(self, pattern_hash: str) -> Optional[Dict]:
        """Get historical performance of a pattern (legacy method)"""
        try:
            with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT success_rate, avg_profit, occurrences
                    FROM pattern_memory
                    WHERE pattern_hash = %s
                """, (pattern_hash,))

                return cursor.fetchone()

        except Exception as e:
            print(f"[ERROR] Failed to get pattern performance: {e}")
            return None

    def _get_pattern_performance_with_validation(self, pattern_hash: str, current_regime: str) -> Optional[Dict]:
        """
        Get pattern performance WITH regime-specific validation
        Returns pattern data with statistical confidence and regime tracking
        """
        try:
            with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT
                        success_rate,
                        avg_profit,
                        occurrences,
                        regime,
                        statistical_confidence,
                        regime_occurrences
                    FROM pattern_memory
                    WHERE pattern_hash = %s
                """, (pattern_hash,))

                result = cursor.fetchone()

                if not result:
                    return None

                # Check if pattern was learned in same regime
                pattern_regime = result.get('regime', 'UNKNOWN')
                regime_occurrences = result.get('regime_occurrences', {})

                if isinstance(regime_occurrences, str):
                    import json
                    regime_occurrences = json.loads(regime_occurrences)

                # Get occurrences for current regime
                current_regime_count = regime_occurrences.get(current_regime, 0)

                # If pattern was learned in different regime, warn about it
                if pattern_regime != current_regime and pattern_regime != 'UNKNOWN':
                    # Pattern from different regime - use with caution
                    result['regime_mismatch'] = True
                    result['pattern_regime'] = pattern_regime
                    result['current_regime_occurrences'] = current_regime_count
                else:
                    result['regime_mismatch'] = False

                return dict(result)

        except Exception as e:
            print(f"[ERROR] Failed to get pattern performance with validation: {e}")
            # Fallback to legacy method
            return self._get_pattern_performance(pattern_hash)

    def _get_token_statistics(self, token: str) -> Optional[Dict]:
        """Get recent performance statistics for a token"""
        try:
            with self.conn.cursor() as cursor:
                cursor.execute("""
                    SELECT
                        COUNT(*) as total_trades,
                        SUM(CASE WHEN reward > 0 THEN 1 ELSE 0 END) as wins,
                        SUM(CASE WHEN reward < 0 THEN 1 ELSE 0 END) as losses,
                        AVG(reward) as avg_reward
                    FROM trade_experiences
                    WHERE token = %s
                    AND timestamp > NOW() - INTERVAL '7 days'
                """, (token,))

                result = cursor.fetchone()
                if result:
                    # Check recent streak
                    cursor.execute("""
                        SELECT reward
                        FROM trade_experiences
                        WHERE token = %s
                        ORDER BY timestamp DESC
                        LIMIT 5
                    """, (token,))

                    recent_trades = cursor.fetchall()
                    recent_wins = sum(1 for t in recent_trades if t[0] > 0)
                    recent_losses = sum(1 for t in recent_trades if t[0] < 0)

                    return {
                        'total_trades': result[0],
                        'wins': result[1],
                        'losses': result[2],
                        'avg_reward': float(result[3]) if result[3] else 0,
                        'recent_wins': recent_wins,
                        'recent_losses': recent_losses
                    }

                return None

        except Exception as e:
            print(f"[ERROR] Failed to get token statistics: {e}")
            return None

    def _update_feature_importance(self, context: Dict, outcome: Dict):
        """Track which features lead to successful trades"""
        reward = self._calculate_actual_reward(outcome)

        # Update importance scores
        if 'scores' in context:
            for feature, score in context['scores'].items():
                # Exponential moving average
                alpha = 0.1
                old_importance = self.feature_importance[feature]
                new_importance = score * reward
                self.feature_importance[feature] = (1 - alpha) * old_importance + alpha * new_importance

    def _extract_features(self, context: Dict, decision: Dict) -> Dict:
        """Extract normalized features for similarity comparison"""
        features = {
            'sentiment': context.get('sentiment', {}).get('avg_sentiment', 0),
            'volume_spike': context.get('quick_summary', {}).get('volume_spike', 1),
            'price_change': context.get('price_data', {}).get('price_change_24h', 0) / 100,
            'confidence': decision.get('confidence', 0.6),
            'liquidation_risk': context.get('liquidation_cascade', {}).get('risk_score', 0) / 100,
            'correlation': context.get('correlation', 0.5)
        }

        # Normalize features to [0, 1]
        for key, value in features.items():
            features[key] = np.clip(value, -1, 1)

        return features

    def _find_similar_experiences(self, features: Dict, limit: int = 10) -> List[Dict]:
        """Find similar past trading experiences"""
        similar = []

        for exp in list(self.experience_buffer)[-100:]:  # Check last 100 experiences
            exp_features = self._extract_features(exp['context'], exp['decision'])
            similarity = self._calculate_similarity(features, exp_features)

            if similarity > 0.7:  # 70% similarity threshold
                similar.append({
                    'features': exp_features,
                    'reward': exp['self_reward'],
                    'similarity': similarity
                })

        # Sort by similarity and return top matches
        similar.sort(key=lambda x: x['similarity'], reverse=True)
        return similar[:limit]

    def _calculate_similarity(self, features1: Dict, features2: Dict) -> float:
        """Calculate cosine similarity between feature sets"""
        # Convert to vectors
        keys = set(features1.keys()) | set(features2.keys())
        vec1 = np.array([features1.get(k, 0) for k in keys])
        vec2 = np.array([features2.get(k, 0) for k in keys])

        # Cosine similarity
        if np.linalg.norm(vec1) == 0 or np.linalg.norm(vec2) == 0:
            return 0

        similarity = np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2))
        return float(similarity)

    def _normalize_strategy_weights(self):
        """Ensure strategy weights sum to 1"""
        weight_keys = [k for k in self.strategy_params.keys() if k.endswith('_weight')]
        total_weight = sum(self.strategy_params[k] for k in weight_keys)

        if total_weight > 0:
            for key in weight_keys:
                self.strategy_params[key] /= total_weight

    def _get_best_historical_strategy(self) -> Optional[Dict]:
        """Retrieve best performing historical strategy"""
        try:
            with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT parameters
                    FROM strategy_evolution
                    WHERE performance->>'fitness' IS NOT NULL
                    ORDER BY (performance->>'fitness')::float DESC
                    LIMIT 1
                """)

                result = cursor.fetchone()
                if result:
                    return json.loads(result['parameters'])
                return None

        except Exception as e:
            print(f"[ERROR] Failed to get best strategy: {e}")
            return None

    def update_performance_metrics(self, trades: List[Dict]):
        """Update performance metrics based on recent trades"""
        if not trades:
            return

        # Calculate returns
        returns = [t['pnl_pct'] for t in trades if 'pnl_pct' in t]

        if returns:
            # Sharpe ratio (annualized)
            if len(returns) > 1:
                avg_return = np.mean(returns)
                std_return = np.std(returns)
                if std_return > 0:
                    self.performance_metrics['sharpe_ratio'] = (avg_return / std_return) * np.sqrt(365)

            # Sortino ratio (downside deviation)
            negative_returns = [r for r in returns if r < 0]
            if negative_returns:
                downside_std = np.std(negative_returns)
                if downside_std > 0:
                    self.performance_metrics['sortino_ratio'] = (np.mean(returns) / downside_std) * np.sqrt(365)

            # Win rate
            wins = sum(1 for r in returns if r > 0)
            self.performance_metrics['win_rate'] = wins / len(returns)

            # Profit factor
            gross_profit = sum(r for r in returns if r > 0)
            gross_loss = abs(sum(r for r in returns if r < 0))
            if gross_loss > 0:
                self.performance_metrics['profit_factor'] = gross_profit / gross_loss

            # Max drawdown
            cumulative = np.cumsum(returns)
            running_max = np.maximum.accumulate(cumulative)
            drawdown = cumulative - running_max
            self.performance_metrics['max_drawdown'] = np.min(drawdown)

        # Update trade statistics
        self.performance_metrics['total_trades'] = len(trades)
        self.performance_metrics['profitable_trades'] = sum(1 for t in trades if t.get('pnl_pct', 0) > 0)

        # Store metrics
        self._store_learning_metrics()

    def _store_learning_metrics(self):
        """Store current learning metrics to database"""
        try:
            with self.conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO learning_metrics
                    (timestamp, sharpe_ratio, win_rate, avg_profit, exploration_rate, strategy_fitness)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (timestamp) DO UPDATE SET
                        sharpe_ratio = EXCLUDED.sharpe_ratio,
                        win_rate = EXCLUDED.win_rate,
                        avg_profit = EXCLUDED.avg_profit,
                        exploration_rate = EXCLUDED.exploration_rate,
                        strategy_fitness = EXCLUDED.strategy_fitness
                """, (
                    datetime.now(),
                    self.performance_metrics['sharpe_ratio'],
                    self.performance_metrics['win_rate'],
                    self.performance_metrics.get('avg_profit', 0),
                    self.strategy_params['exploration_rate'],
                    self._calculate_strategy_fitness()
                ))
                self.conn.commit()

        except Exception as e:
            print(f"[ERROR] Failed to store learning metrics: {e}")
            self.conn.rollback()

    def get_learning_report(self) -> Dict:
        """Generate comprehensive learning report"""
        report = {
            'current_generation': self.strategy_evolution['current_generation'],
            'total_experiences': len(self.experience_buffer),
            'performance_metrics': self.performance_metrics,
            'strategy_parameters': self.strategy_params,
            'feature_importance': dict(self.feature_importance),
            'top_patterns': [],
            'learning_curve': []
        }

        # Get top performing patterns
        try:
            with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT pattern_hash, success_rate, avg_profit, occurrences
                    FROM pattern_memory
                    WHERE occurrences > 3
                    ORDER BY success_rate DESC
                    LIMIT 5
                """)

                report['top_patterns'] = cursor.fetchall()

                # Get learning curve
                cursor.execute("""
                    SELECT timestamp, sharpe_ratio, win_rate, strategy_fitness
                    FROM learning_metrics
                    ORDER BY timestamp DESC
                    LIMIT 100
                """)

                report['learning_curve'] = cursor.fetchall()

        except Exception as e:
            print(f"[ERROR] Failed to generate report: {e}")

        return report

    def save_state(self):
        """Save current state to disk (includes overfitting prevention data)"""
        try:
            state = {
                'strategy_params': self.strategy_params,
                'feature_importance': dict(self.feature_importance),
                'performance_metrics': self.performance_metrics,
                'strategy_evolution': self.strategy_evolution,
                'reward_network': self.reward_network,
                # NEW: Overfitting prevention state
                'regime_performance': self.regime_performance,
                'overfitting_metrics': self.overfitting_metrics,
                'best_strategy_fitness': self.best_strategy_fitness,
                'best_strategy_params': self.best_strategy_params,
                'strategy_history': list(self.strategy_history)  # Convert deque to list for pickle
            }

            with open('trade_learner_state.pkl', 'wb') as f:
                pickle.dump(state, f)

            print("[TradeLearner] State saved (with overfitting prevention data)")

        except Exception as e:
            print(f"[ERROR] Failed to save state: {e}")

    def load_state(self):
        """Load saved state from disk (with backward compatibility)"""
        try:
            if os.path.exists('trade_learner_state.pkl'):
                with open('trade_learner_state.pkl', 'rb') as f:
                    state = pickle.load(f)

                # Core state (always present)
                self.strategy_params = state['strategy_params']
                self.feature_importance = defaultdict(float, state['feature_importance'])
                self.performance_metrics = state['performance_metrics']
                self.strategy_evolution = state['strategy_evolution']
                self.reward_network = state['reward_network']

                # NEW: Overfitting prevention state (with fallback for legacy state files)
                if 'regime_performance' in state:
                    self.regime_performance = state['regime_performance']
                if 'overfitting_metrics' in state:
                    self.overfitting_metrics = state['overfitting_metrics']
                if 'best_strategy_fitness' in state:
                    self.best_strategy_fitness = state['best_strategy_fitness']
                if 'best_strategy_params' in state:
                    self.best_strategy_params = state['best_strategy_params']
                if 'strategy_history' in state:
                    self.strategy_history = deque(state['strategy_history'], maxlen=10)

                print(f"[TradeLearner] Loaded state from generation {self.strategy_evolution['current_generation']}")
                print(f"[TradeLearner] Overfitting prevention: {'ENABLED' if 'regime_performance' in state else 'NEW SESSION'}")

        except Exception as e:
            print(f"[ERROR] Failed to load state: {e}")

    def close(self):
        """Clean up resources"""
        self.save_state()
        if self.conn:
            self.conn.close()
        print("[TradeLearner] Closed")

    # ========================================================================
    # WRAPPER METHODS (for ai_trader.py compatibility)
    # ========================================================================

    def get_learned_adjustment(self, token: str, market_context: Dict) -> Dict:
        """Wrapper: Returns adjustments in expected format"""
        if len(self.experience_buffer) < 10:
            return {'should_adjust': False, 'confidence_modifier': 0.0, 'position_size_modifier': 1.0}

        s = self.suggest_trade_adjustments(token, market_context)
        return {
            'should_adjust': bool(s['reasoning']),
            'confidence_modifier': s['confidence_adjustment'],
            'position_size_modifier': s['position_size_multiplier'],
            'pattern_type': s['reasoning'][0] if s['reasoning'] else None,
            'recommendation': ' | '.join(s['reasoning']) if s['reasoning'] else None,
            'override_action': s['action_override']
        }

    def get_learning_statistics(self) -> Dict:
        """Wrapper: Returns learning stats"""
        return {
            'total_experiences': len(self.experience_buffer),
            'unique_patterns': len(self.pattern_memory),
            'evolution_count': self.strategy_evolution['current_generation'],
            'avg_reward': sum(self.reward_network['reward_history']) / max(len(self.reward_network['reward_history']), 1)
        }

    def get_top_patterns(self, limit: int = 3) -> List[Dict]:
        """Wrapper: Returns top patterns from DB"""
        try:
            with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute("SELECT pattern_hash, success_rate, occurrences FROM pattern_memory WHERE occurrences >= 3 ORDER BY success_rate DESC LIMIT %s", (limit,))
                return [{'pattern_type': p['pattern_hash'][:20], 'success_rate': p['success_rate'], 'count': p['occurrences']} for p in cursor.fetchall()]
        except:
            return []

    def get_evolved_parameters(self) -> Dict:
        """Wrapper: Returns evolved parameters"""
        return {
            'confidence_threshold': self.strategy_params['min_confidence_threshold'],
            'risk_tolerance': self.strategy_params['stop_loss_multiplier'],
            'position_sizing_factor': 1.0
        }

    def save_experience_buffer(self):
        """Wrapper: Saves state"""
        self.save_state()

    def record_experience(self, state: Dict = None, action: str = None, decision: Dict = None,
                         reward: float = None, outcome: Dict = None,
                         # Old signature for backwards compatibility
                         token: str = None, market_context: Dict = None):
        """Wrapper: Records trade experience"""
        # Handle new signature (from ai_trader.py)
        if state is not None:
            token = state.get('token')
            market_context = state.get('market_context', {})

        # Validate we have required data
        if not token or not decision or not outcome:
            print(f"[ERROR] Missing required parameters for record_experience")
            return

        self.record_trade_experience(token, market_context or {}, decision, outcome)

    def learn_from_recent_trades(self):
        """Wrapper: Triggers learning from recent trades"""
        for exp in list(self.experience_buffer)[-10:]:
            self._learn_from_experience(exp)
        self._store_learning_metrics()