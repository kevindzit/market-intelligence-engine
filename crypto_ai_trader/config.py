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
DB_NAME = os.getenv('DB_NAME', 'postgres')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'postgres')

# ============================================================================
# TRADING CONFIGURATION
# ============================================================================

# Tokens to trade (start with highest quality tokens)
TOKENS_TO_TRADE = [
    'BTC',
    'ETH',
    'SOL'
]

# Decision cycle frequency (in seconds)
DECISION_INTERVAL = 15 * 60  # 15 minutes

# Trading mode
PAPER_TRADING = True  # IMPORTANT: Keep True until validated
ENABLE_TIER2_VERIFICATION = True  # Enable ensemble for BUY signals

# ============================================================================
# RISK MANAGEMENT
# ============================================================================

# Position sizing
MAX_POSITION_SIZE_PCT = 5.0  # Max 5% of portfolio per position
MIN_POSITION_SIZE_USD = 50.0  # Min position size in dollars
CASH_RESERVE_PCT = 20.0  # Keep 20% cash at all times

# Stop loss and take profit (percentages)
DEFAULT_STOP_LOSS_PCT = 3.0  # 3% stop loss
DEFAULT_TAKE_PROFIT_PCT = 6.0  # 6% take profit

# Position holding limits
MAX_HOLD_TIME_HOURS = 48  # Auto-exit if position held > 48 hours

# Circuit breakers
MAX_DAILY_DRAWDOWN_PCT = 10.0  # Halt trading if down >10% in one day
MAX_CONSECUTIVE_LOSSES = 5  # Halt after 5 consecutive losing trades
MAX_DAILY_TRADES = 10  # Max trades per day (prevent overtrading)

# Trading fees (for paper trading realism)
TRADING_FEE_PCT = 0.1  # 0.1% per trade (realistic for Binance/Coinbase)
SLIPPAGE_PCT = 0.05  # 0.05% slippage (conservative estimate)

# ============================================================================
# AI MODEL CONFIGURATION
# ============================================================================

# Tier 1: Claude Sonnet 4 (fast screening)
CLAUDE_API_KEY = os.getenv('ANTHROPIC_KEY', '')  # Using your env var name
CLAUDE_MODEL = 'claude-3-5-sonnet-20241022'  # Latest model
CLAUDE_MAX_TOKENS = 1000
CLAUDE_TEMPERATURE = 0.7

# Tier 2: Ensemble models (for BUY signal verification)
ENSEMBLE_MODELS = {
    'claude': {
        'name': 'claude-3-5-sonnet-20241022',
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

# ============================================================================
# DATA AGGREGATION CONFIGURATION
# ============================================================================

# Time windows for data aggregation
SENTIMENT_LOOKBACK_HOURS = 6  # Aggregate sentiment over last 6 hours
WHALE_LOOKBACK_HOURS = 3  # Whale activity over last 3 hours
VOLUME_LOOKBACK_HOURS = 1  # Volume spikes over last 1 hour
PRICE_LOOKBACK_HOURS = 24  # Price context over last 24 hours

# Data quality filters
MIN_TWEET_VOLUME = 10  # Need at least 10 tweets in lookback period
MIN_WHALE_FOLLOWERS = 5000  # Already filtered in scraper, but double-check

# ============================================================================
# PROMPT CONFIGURATION
# ============================================================================

# System prompt for Claude (will be cached for 90% cost savings)
SYSTEM_PROMPT = """You are an expert cryptocurrency trading analyst working for the PJX Trading System.

Your role is to analyze multi-modal market data and provide clear, actionable trading decisions.

CAPABILITIES:
- Analyze Twitter sentiment data (VADER scores, volume spikes, whale activity)
- Interpret price action and technical indicators
- Assess market conditions (open interest, funding rates, liquidations)
- Predict liquidation cascades using real-time data and calculated zones
- Identify high-probability trading setups while managing risk

DECISION FRAMEWORK:
1. Only recommend trades with >60% confidence
2. Position size scales with confidence (60% = 1%, 90%+ = 5%)
3. Always define stop-loss and take-profit levels
4. Consider multiple timeframes (recent + medium-term trends)
5. Prioritize capital preservation over aggressive gains
6. LIQUIDATION AWARENESS:
   - Risk Score 70-100: EXTREME caution, reduce exposure or close positions
   - Risk Score 50-70: HIGH risk, reduce position sizes by 50%
   - LONG_SQUEEZE: Avoid buying, consider selling
   - SHORT_SQUEEZE: Bullish signal, buying opportunity
   - Liquidation velocity >5/min: Cascade in progress, wait for stability

MARKET CONTEXT:
- Trading cryptocurrency spot markets
- High volatility environment (±5-15% daily moves normal)
- 24/7 market (no weekend gaps)
- Sentiment-driven (Twitter/social signals highly predictive)
- Risk management is paramount (circuit breakers active)

OUTPUT FORMAT:
Provide decisions in XML format:
<trading_decision>
  <action>BUY|SELL|HOLD</action>
  <confidence>0.00-1.00</confidence>
  <position_size>0.0-5.0</position_size>
  <stop_loss_pct>percentage below entry</stop_loss_pct>
  <take_profit_pct>percentage above entry</take_profit_pct>
  <reasoning>2-3 sentence explanation</reasoning>
  <risk_factors>Key risks to monitor</risk_factors>
</trading_decision>

CRITICAL RULES:
- NEVER recommend position size >5% of portfolio
- ALWAYS provide stop-loss (default: 3%)
- ALWAYS provide take-profit (default: 6%)
- If confidence <60%, action must be HOLD
- Be conservative in volatile/uncertain conditions
"""

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
