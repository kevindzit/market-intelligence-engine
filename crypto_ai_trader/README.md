# PJX AI Trading System

## Overview
A high-quality crypto trading bot with tiered AI verification:
- **Tier 1**: Claude Sonnet 4 screens all signals (<1s, $0.003/signal)
- **Tier 2**: 3-model ensemble verifies BUY signals (2-3s, $0.015/signal)
- **Paper Trading**: $10,000 simulated capital with realistic fees/slippage
- **Risk Management**: Position limits, circuit breakers, stop-loss/take-profit

## Architecture
```
PostgreSQL Database
    ↓ (aggregates 6h sentiment, 24h price, OI, funding)
Data Aggregation (500 tokens)
    ↓
Tier 1: Claude Screening → BUY/SELL/HOLD
    ↓ (if BUY signal)
Tier 2: Ensemble Verification (Claude + DeepSeek + Gemini)
    ↓
Risk Management (position sizing, circuit breakers)
    ↓
Paper Trading Engine (simulated execution)
```

## Quick Start

### 1. Prerequisites
- PostgreSQL running on port 54594 ✅ (you have this)
- Python 3.8+ with packages: anthropic, google-generativeai, openai
- API keys in .env ✅ (you have these)

### 2. Install Required Packages
```bash
pip install anthropic google-generativeai openai
```

### 3. Run the System
```bash
# From pjx folder
cd crypto_ai_trader
python main.py
```

## Configuration (config.py)

### Key Settings
- `TOKENS_TO_TRADE`: ['BTC', 'ETH', 'SOL'] (start with 3)
- `DECISION_INTERVAL`: 15 minutes
- `MAX_POSITION_SIZE_PCT`: 5% of portfolio
- `ENABLE_TIER2_VERIFICATION`: True (ensemble for BUY signals)

### Risk Parameters
- Max position: 5% of portfolio
- Cash reserve: 20% minimum
- Stop loss: 3% default
- Take profit: 6% default
- Circuit breakers: 10% daily drawdown, 5 consecutive losses

## Database Tables

| Table | Purpose |
|-------|---------|
| trading_decisions | Logs all AI decisions |
| ensemble_votes | Individual model votes |
| portfolio_state | Current positions & P&L |
| paper_trades | Execution history |
| circuit_breaker_events | Risk events |

## Components

### 1. data_aggregator.py
Queries PostgreSQL and generates ~500 token summaries:
- Twitter sentiment (6h lookback)
- Price action (24h lookback)
- Open Interest, funding, liquidations
- Fear & Greed Index

### 2. claude_engine.py
Tier 1 decision engine:
- Analyzes market summary
- Returns BUY/SELL/HOLD + confidence
- Uses prompt caching (90% cost savings)

### 3. ensemble_verifier.py
Tier 2 verification (BUY signals only):
- Claude (40% weight)
- DeepSeek (35% weight)
- Gemini (25% weight)
- Requires >70% consensus to execute

### 4. risk_manager.py
Validates all trades:
- Position sizing (confidence-based)
- Circuit breaker checks
- Portfolio constraints
- Stop-loss/take-profit calculation

### 5. paper_trading.py
Simulates execution:
- Realistic fees (0.1%)
- Slippage simulation (0.05%)
- P&L tracking
- Updates portfolio state

### 6. main.py
Orchestrates everything:
- 15-minute decision cycles
- Processes 3 tokens (BTC, ETH, SOL)
- Performance reporting every 24h
- Clean shutdown with Ctrl+C

## Performance Metrics

### Success Criteria (30-day paper trading)
- Win rate: >55%
- Total return: >10%
- Max drawdown: <15%
- Sharpe ratio: >1.0

### Expected Costs
- Tier 1 only: ~$13.50/month
- With Tier 2: ~$18/month
- Expected benefit: $50+/month in prevented bad trades

## Monitoring

The system prints detailed logs:
```
[BTC] Processing...
  Tier 1: BUY (75% confidence)
  Triggering Tier 2 verification...
  Tier 2: BUY (80% consensus)
  ✅ Risk approved: $500.00
  ✅ Trade executed: BUY at $109,044.00
```

Performance reports every 24 hours show:
- Portfolio value & P&L
- Win rate
- Recent trades
- System uptime

## Next Steps

### Phase 1: Paper Trading (Weeks 1-4)
Run continuously and monitor:
- Win rate
- Average win vs loss
- Maximum drawdown
- API costs

### Phase 2: Optimization (Weeks 5-6)
If win rate >55%:
- Tune confidence thresholds
- Adjust position sizing
- Add more tokens

### Phase 3: Live Trading (Week 7+)
Start with $100-500:
- Keep paper trading parallel
- Scale gradually (+25% each profitable week)
- Never risk more than you can afford to lose

## Troubleshooting

### "No sentiment data available"
- Twitter scrapers need to run for a few hours first
- Check if twitter_sentiment table has recent data

### "Circuit breaker triggered"
- System protecting you from losses
- Will auto-resume next day
- Check circuit_breaker_events table for details

### API errors
- Check .env file has correct keys
- Monitor rate limits
- Verify internet connection

## Safety Features

✅ Paper trading mode (no real money)
✅ Circuit breakers (stop catastrophic losses)
✅ Position limits (max 5% per trade)
✅ Cash reserve (always keep 20%)
✅ Ensemble verification (reduce false positives)
✅ Conservative defaults (3% stop loss)

## Support

- Database issues: Check PostgreSQL is running on port 54594
- API issues: Verify keys in .env file
- Trading logic: Review config.py settings
- Logs: Check console output for detailed errors

---

**IMPORTANT**: This is PAPER TRADING. Always validate for 30+ days before using real money. Crypto trading is high-risk. Never trade more than you can afford to lose.