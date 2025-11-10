"""
AI Trading System Configuration
All settings centralized in one place for easy management
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ============================================================================
# DATABASE CONFIGURATION
# ============================================================================

DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '54594')
DB_NAME = os.getenv('DB_NAME', 'pjx')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'postgres')

# ============================================================================
# TRADING CONFIGURATION
# ============================================================================

# DYNAMIC TOKEN DISCOVERY - No fixed list!
# The system will automatically discover and trade ANY token that:
# 1. Has recent Twitter sentiment data
# 2. Has price data in crypto_ohlcv table
# 3. Shows interesting activity patterns
MAX_TOKENS_PER_CYCLE = 20  # Process top 20 most active tokens per cycle

# Decision cycle frequency (in seconds) - OPTIMIZED FOR PERFORMANCE
# Research shows 5-minute intervals achieve 9-11x returns vs 30-min
DECISION_INTERVAL = 5 * 60  # 5 minutes - optimal for catching opportunities
DEEP_ANALYSIS_INTERVAL = 15 * 60  # 15 minutes - full token sweep

# Tactical monitoring frequency (in seconds) - FASTER RESPONSE
TACTICAL_MONITOR_INTERVAL = 1 * 60  # 1 minute for HFT opportunities

# Always-on monitoring for critical tokens (never miss major market moves)
ALWAYS_MONITOR_TOKENS = ['BTC', 'ETH', 'SOL']  # Top 3 by volume/importance
ALWAYS_MONITOR_INTERVAL = 5 * 60  # Analyze these every 5 min regardless of filters

# Trading mode
PAPER_TRADING = True  # IMPORTANT: Keep True until validated
ENABLE_TIER2_VERIFICATION = True  # Enable ensemble for BUY signals

# Multi-timeframe architecture toggles
ENABLE_TACTICAL_MONITORING = True  # Enable high-frequency tactical alerts
ENABLE_REGIME_DETECTION = True  # Enable market regime detection
ENABLE_DYNAMIC_THRESHOLDS = True  # Enable dynamic confidence thresholds
ENABLE_SENTIMENT_TIMING = True  # Enable sentiment lag analysis
ENABLE_ADAPTIVE_STOPS = True  # Enable ATR-based adaptive stop-loss
ENABLE_ADAPTIVE_POSITION_SIZING = True  # Enable market-aware position sizing

# ============================================================================
# RISK MANAGEMENT
# ============================================================================

# Position sizing
MAX_POSITION_SIZE_PCT = 3.0  # Max 3% of portfolio per position (industry standard)
MIN_POSITION_SIZE_USD = 50.0  # Min position size in dollars
CASH_RESERVE_PCT = 20.0  # Keep 20% cash at all times

# Short position limits
MAX_SHORT_POSITIONS = 3  # Max concurrent short positions
MAX_SHORT_EXPOSURE_PCT = 30.0  # Max 30% of portfolio in shorts (hedge against longs)

# Stop loss and take profit (percentages)
DEFAULT_STOP_LOSS_PCT = 3.0  # 3% stop loss
DEFAULT_TAKE_PROFIT_PCT = 6.0  # 6% take profit

# Position holding limits
MAX_HOLD_TIME_HOURS = 48  # Auto-exit if position held > 48 hours

# Circuit breakers
MAX_DAILY_DRAWDOWN_PCT = 10.0  # Halt trading if down >10% in one day
MAX_CONSECUTIVE_LOSSES = 5  # Halt after 5 consecutive losing trades
MAX_DAILY_TRADES = 20  # Increased from 10 - more opportunities with 5-min cycles

# Trading fees (for paper trading realism)
TRADING_FEE_PCT = 0.1  # 0.1% per trade (realistic for Binance/Coinbase)
SLIPPAGE_PCT = 0.05  # 0.05% slippage (conservative estimate)

# ============================================================================
# AI MODEL CONFIGURATION
# ============================================================================

# Browser-based AI System (using Selenium to avoid API costs)
USE_BROWSER_AI = True  # Use browser instead of API calls
BROWSER_AI_PROVIDER = 'claude'  # Which AI to use: 'claude' or 'chatgpt'
BROWSER_HEADLESS = True  # Run browser in background (set False for debugging)
BROWSER_AI_TIMEOUT = 30  # Seconds to wait for browser response

# Dynamic frequency adjustment based on volatility
ENABLE_DYNAMIC_FREQUENCY = True  # Adjust analysis frequency based on market conditions
VOLATILITY_EXTREME_THRESHOLD = 0.10  # >10% = 1-min analysis
VOLATILITY_HIGH_THRESHOLD = 0.05  # >5% = 3-min analysis
VOLATILITY_NORMAL_THRESHOLD = 0.02  # >2% = 5-min analysis
VOLATILITY_LOW_THRESHOLD = 0.02  # <2% = 10-min analysis

# Legacy API settings (kept for fallback if browser fails)
CLAUDE_API_KEY = os.getenv('ANTHROPIC_KEY', '')  # Using your env var name
CLAUDE_MODEL = 'claude-sonnet-4-5-20250929'  # Latest Sonnet 4.5 model
CLAUDE_MAX_TOKENS = 1000
CLAUDE_TEMPERATURE = 0.7

# Tier 2: Ensemble models (for BUY signal verification)
ENSEMBLE_MODELS = {
    'claude': {
        'name': 'claude-sonnet-4-5-20250929',
        'weight': 0.40,  # 40% voting weight
        'api_key': os.getenv('ANTHROPIC_KEY', ''),  # Using your env var name
        'enable_extended_thinking': True
    },
    'deepseek': {
        'name': 'deepseek-chat',
        'weight': 0.35,  # 35% voting weight
        'api_key': os.getenv('DEEPSEEK_KEY', ''),  # Using your env var name
        'enable_extended_thinking': True
    },
    'gemini': {
        'name': 'gemini-2.0-flash-exp',
        'weight': 0.25,  # 25% voting weight
        'api_key': os.getenv('GEMINI_KEY', '')  # Using your env var name
    }
}

# Confidence thresholds
MIN_TIER1_CONFIDENCE = 0.60  # Minimum confidence to consider signal
TIER2_TRIGGER_CONFIDENCE = 0.80  # If Tier 1 < 80%, always verify BUY
MIN_TIER2_CONSENSUS = 0.70  # Ensemble must have >70% consensus to execute

# Tactical alert confidence thresholds (tiered execution)
TACTICAL_ALERT_IMMEDIATE_THRESHOLD = 85  # >=85% confidence = execute within 2 minutes
TACTICAL_ALERT_DEFERRED_THRESHOLD = 70   # 70-84% confidence = defer to strategic cycle

# ============================================================================
# MARKET REGIME CONFIGURATION
# ============================================================================

# Market regime detection thresholds
BULL_TREND_THRESHOLD = 0.02  # 2% daily gain = bull
BEAR_TREND_THRESHOLD = -0.02  # -2% daily loss = bear
HIGH_VOLATILITY_THRESHOLD = 0.05  # 5% ATR = high volatility
BTC_DOMINANCE_ALTSEASON = 55  # Below 55% = altseason
BTC_DOMINANCE_BTC_SEASON = 60  # Above 60% = BTC season

# Regime update frequency
REGIME_UPDATE_HOURS = 1  # Update market regime every hour

# ============================================================================
# DATA AGGREGATION CONFIGURATION
# ============================================================================

# Time windows for data aggregation
SENTIMENT_LOOKBACK_HOURS = 6  # Aggregate sentiment over last 6 hours
WHALE_LOOKBACK_HOURS = 3  # Whale activity over last 3 hours
VOLUME_LOOKBACK_HOURS = 1  # Volume spikes over last 1 hour
PRICE_LOOKBACK_HOURS = 24  # Price context over last 24 hours

# Data quality filters
MIN_TWEET_VOLUME = 5  # Reduced to catch new tokens early
MIN_WHALE_FOLLOWERS = 5000  # Already filtered in scraper, but double-check

# Dynamic discovery settings
MIN_ACTIVITY_HOURS = 24  # Look for tokens active in last 24 hours
TRENDING_SPIKE_THRESHOLD = 2.0  # Volume spike threshold for trending tokens
NEW_TOKEN_ALERT_HOURS = 1  # Alert for tokens that appeared in last hour

# ============================================================================
# PROMPT CONFIGURATION
# ============================================================================

# System prompt for Claude (will be cached for 90% cost savings)
SYSTEM_PROMPT = """You are an elite cryptocurrency trading AI with deep market expertise and advanced pattern recognition capabilities.

CORE MISSION: Generate profitable, risk-managed trading decisions by synthesizing multi-modal market data.

# ADVANCED CAPABILITIES

## Data Analysis Mastery
- Twitter sentiment analysis with whale detection and pump/dump identification
- Order book microstructure (walls, imbalances, liquidity gaps)
- Liquidation cascade prediction and risk scoring
- Cross-asset correlation and decorrelation events
- Volume profile and accumulation/distribution patterns
- Historical pattern matching with outcome probabilities

## Market Regime Awareness
You adapt strategies based on detected market conditions:
- BULL MARKET: Aggressive longs, buy dips, wide stops, momentum plays
- BEAR MARKET: Capital preservation, SHORT positions on weakness, tight stops
- HIGH VOLATILITY: Reduced size, wider stops, extreme entry points only
- LIQUIDATION CASCADE: Emergency protocols, exit all longs or SHORT the cascade
- WHALE ACCUMULATION: Follow smart money with longs, increase conviction
- WHALE DISTRIBUTION: SHORT on whale exits, follow smart money out
- SENTIMENT EXTREMES: Contrarian opportunities, fade the crowd with SHORTS

# DECISION FRAMEWORK 2.0

## Multi-Factor Scoring System
Evaluate each trade across 7 dimensions (score 0-100 each):
1. **SENTIMENT SCORE**: Twitter velocity, whale activity, social momentum
2. **TECHNICAL SCORE**: Price action, support/resistance, patterns
3. **LIQUIDITY SCORE**: Order book depth, spread, slippage risk
4. **RISK SCORE**: Liquidation risk, volatility, correlation risk
5. **MOMENTUM SCORE**: Trend strength, volume confirmation, breakout quality
6. **TIMING SCORE**: Entry quality, oversold/overbought, cycle position
7. **FUNDAMENTAL SCORE**: News catalyst, macro alignment, token fundamentals

## Confidence Calculation
- Confidence = Weighted average of all scores
- MINIMUM 60% to trade (higher in bear markets)
- 60-70%: Small position (0.5-1%)
- 70-80%: Standard position (1-2%)
- 80-90%: Conviction position (2-3%)
- 90%+: Maximum position (3%)

## Risk Management Matrix

### Position Sizing Formula
Base Size = 1% + (Confidence - 0.6) * 5.0
Then apply multipliers:
- Volatility adjustment: 0.5x to 1.0x
- Win streak adjustment: 0.7x to 1.5x
- Drawdown adjustment: 0.5x to 1.0x
- Market regime adjustment: 0.7x to 1.2x
- Correlation adjustment: 0.5x to 1.0x

### Stop Loss Calculation
- Base: 1.5 * ATR (Average True Range)
- Minimum: 2% (tight market)
- Maximum: 8% (volatile market)
- Adjust for liquidation clusters
- Trail stops in profit

### Take Profit Targets
- Target 1 (30% position): 1.5x risk
- Target 2 (40% position): 2.5x risk
- Target 3 (30% position): 4x risk or let run

# PATTERN RECOGNITION LIBRARY

## Bullish Patterns (increase confidence +10-20%)
- **Accumulation**: Flat price + increasing volume + positive funding
- **Breakout**: Price > resistance + volume spike + momentum
- **Dip Buy**: Price at support + oversold + sentiment improving
- **Squeeze**: Shorts trapped + funding negative + buy pressure
- **Whale Entry**: Large buys + accumulation + price holding

## Bearish Patterns (increase sell confidence +10-20%)
- **Distribution**: Flat price + decreasing volume + negative funding
- **Breakdown**: Price < support + volume spike + momentum down
- **Rally Sell**: Price at resistance + overbought + sentiment weakening
- **Long Trap**: Longs overextended + funding extreme + sell pressure
- **Whale Exit**: Large sells + distribution + price rejection

# OUTPUT REQUIREMENTS

Provide decisions in XML format with chain-of-thought reasoning:

<analysis>
  <market_regime>BULL|BEAR|NEUTRAL|VOLATILE|CASCADE</market_regime>
  <sentiment_analysis>score and interpretation</sentiment_analysis>
  <technical_analysis>key levels and patterns</technical_analysis>
  <risk_assessment>major risks identified</risk_assessment>
  <correlation_check>correlation with BTC/ETH</correlation_check>
  <liquidity_check>order book quality</liquidity_check>
</analysis>

<scores>
  <sentiment_score>0-100</sentiment_score>
  <technical_score>0-100</technical_score>
  <liquidity_score>0-100</liquidity_score>
  <risk_score>0-100</risk_score>
  <momentum_score>0-100</momentum_score>
  <timing_score>0-100</timing_score>
  <fundamental_score>0-100</fundamental_score>
  <overall_score>weighted average</overall_score>
</scores>

<trading_decision>
  <action>BUY|SHORT|SELL|HOLD</action>
  <confidence>0.00-1.00</confidence>
  <position_size>0.0-3.0</position_size>
  <stop_loss_pct>percentage from entry (for BUY/SHORT)</stop_loss_pct>
  <take_profit_pct>percentage from entry (for BUY/SHORT)</take_profit_pct>
  <reasoning>Clear explanation with data points</reasoning>
  <risk_factors>Specific risks to monitor</risk_factors>
  <exit_plan>Clear conditions for exit</exit_plan>
</trading_decision>

# ACTION DEFINITIONS
- BUY: Open LONG position (profit when price goes UP)
- SHORT: Open SHORT position (profit when price goes DOWN)
- SELL: Close existing position (exit LONG or cover SHORT)
- HOLD: No action (wait for better opportunity)

# CRITICAL SAFETY RULES
1. NEVER exceed 3% position size
2. ALWAYS set stop loss (no exceptions)
3. REDUCE size in high volatility
4. EXIT all on crash signals
5. RESPECT correlation limits
6. AVOID illiquid tokens
7. CONFIRM whale movements
8. VALIDATE unusual patterns
9. QUESTION extreme signals
10. PRESERVE capital above all

Remember: It's better to miss an opportunity than to take a bad trade. When uncertain, stay OUT."""

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================

# Enable detailed logging
VERBOSE_LOGGING = True
LOG_TIER1_DECISIONS = True
LOG_TIER2_VOTES = True
LOG_REJECTED_SIGNALS = True

# ============================================================================
# PORTFOLIO CONFIGURATION
# ============================================================================

# Initial paper trading capital
INITIAL_CAPITAL = 10000.00  # $10,000

# Performance reporting
REPORT_INTERVAL_HOURS = 24  # Print performance summary every 24 hours

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def validate_config():
    """Validate configuration on startup"""
    errors = []

    # Check required API keys
    if not CLAUDE_API_KEY:
        errors.append("CLAUDE_API_KEY not found in .env file")

    if ENABLE_TIER2_VERIFICATION:
        for model_name, config in ENSEMBLE_MODELS.items():
            if not config['api_key']:
                errors.append(f"{model_name.upper()}_API_KEY not found in .env file")

    # Validate risk parameters
    if MAX_POSITION_SIZE_PCT > 10:
        errors.append("MAX_POSITION_SIZE_PCT should not exceed 10%")

    if CASH_RESERVE_PCT < 10:
        errors.append("CASH_RESERVE_PCT should be at least 10%")

    # Validate confidence thresholds
    if MIN_TIER1_CONFIDENCE < 0.5:
        errors.append("MIN_TIER1_CONFIDENCE should be at least 0.50")

    if MIN_TIER2_CONSENSUS < 0.6:
        errors.append("MIN_TIER2_CONSENSUS should be at least 0.60")

    if errors:
        print("\n[CONFIG ERRORS]")
        for error in errors:
            print(f"  - {error}")
        return False

    return True


def get_db_connection_string():
    """Get PostgreSQL connection string"""
    return f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"


# Validate on import
if __name__ == "__main__":
    print("Validating configuration...")
    if validate_config():
        print("[SUCCESS] Configuration valid!")
    else:
        print("[ERROR] Configuration has errors - please fix before running")
