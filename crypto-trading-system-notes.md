# Crypto Trading System - Project Notes

## Chosen Configuration: BALANCED

**Why Balanced:**
- Proven in live trading (+28% returns with real $10K)
- Hybrid reasoning adapts to complexity automatically
- Best starting point for most traders
- Cost: ~$33/month (with optimization)

---

## API Models - What to Use Where

### Data Collection Layer (Continuous Monitoring)
**Primary: Gemini 2.5 Flash-Lite**
- Pricing: $0.10/$0.40 per million tokens
- Context: 1M tokens (can process entire order books, news feeds, history)
- Speed: Sub-second latency
- Best for: High-volume data processing, rapid pattern detection, news summarization
- Cost: ~$1/month with caching

**Backup: DeepSeek V3.2-Exp**
- Pricing: $0.028/$0.28 per million tokens
- Context: 128K tokens
- Best for: Cost-sensitive bulk preprocessing
- Warning: Experimental status, use as secondary only

### Trading Decision Layer (Real-Time Signals)
**Primary: Claude Sonnet 4**
- Pricing: $3/$15 per million tokens (effectively $1.80/$15 with 90% caching)
- Context: 200K tokens
- Live results: +28% returns in Alpha Arena
- Special feature: Hybrid reasoning (fast OR deep thinking as needed)
- Best for: Entry/exit signals, position sizing, multi-factor analysis, real-time tactical decisions
- Latency: Fast in standard mode, slower in deep thinking mode

**Alternative for Strategic Analysis: DeepSeek R1**
- Pricing: $0.55/$2.19 per million tokens
- Live results: +35% returns in Alpha Arena
- Best for: Strategic planning, portfolio rebalancing, deep market analysis
- Note: Always does extended reasoning (slower), not ideal for real-time trades

### Deep Analysis Layer (Historical Patterns)
**Use: Gemini 2.5 Pro**
- Pricing: $1.25/$10 per million tokens
- Context: 1M-2M tokens
- Best for: Multi-factor synthesis, historical pattern analysis
- Warning: Lost 39% in live trading when used for real-time decisions (use for research only)

---

## System Architecture (5-Agent Hierarchical)

### Agent Structure
1. **Data Collection Agents** (Parallel)
   - Technical Analysis Agent (Gemini Flash-Lite)
   - Sentiment Analysis Agent (Gemini Flash-Lite)
   - Fundamental Analysis Agent (Gemini Flash-Lite)

2. **Decision Agents** (Sequential)
   - Risk Manager Agent (Claude Sonnet 4) - veto authority
   - Portfolio Manager Agent (Claude Sonnet 4) - final execution

### Communication Flow
```
Parallel Analysis → Risk Manager → Portfolio Manager → Exchange
```

### Framework Choice
- **Development**: CrewAI (rapid prototyping)
- **Production**: LangGraph (enterprise-grade, better observability)

---

## Cost Breakdown (Balanced Configuration)

### Conservative Setup (~$8-15/month)
- Data collection: $1/month (Gemini Flash-Lite with caching)
- Decision making: $2-3/month (Claude Sonnet 4, 5-10 decisions/day)
- Analysis: $5-10/month (periodic deep analysis)

### Active Trading (~$33/month)
- Data collection: $1-2/month
- Real-time decisions: $10-15/month (20-50 decisions/day)
- Deep analysis: $15-20/month (weekly strategic reviews)

### Cost Optimization Strategies
- **Prompt caching**: 75-90% savings on repeated contexts
- **Intelligent routing**: Use cheap models for simple tasks, expensive for complex
- **Batch processing**: 50% discount for non-urgent analysis
- **Cache system prompts**: Trading rules, risk parameters (update weekly)

---

## Intelligent Routing Logic

```python
IF signal_confidence > 0.8 AND volatility < low_threshold:
    Use Gemini Flash-Lite (fast, cheap)
ELIF signal_confidence < 0.5 OR conflicting_indicators:
    Use Claude Sonnet 4 (deep reasoning)
ELSE:
    Use DeepSeek R1 (balanced for strategic)
```

---

## Risk Management Rules

### Position Sizing
- 1-2% capital risk per trade
- Maximum 20% per asset
- Daily loss limit: 5% portfolio value

### Safety Features
- VaR calculations
- Drawdown circuit breakers (pause at 25% drawdown)
- Human confirmation for large trades (>$5K)
- Risk Manager has veto authority over all trades

---

## Development Phases

### Phase 1: Infrastructure (Weeks 1-2)
- Exchange API integration (Binance/Coinbase)
- Data pipeline (price, volume, order book)
- Database setup (TimescaleDB/InfluxDB)
- Cost: ~$0 (dev environment, free tiers)

### Phase 2: Basic agents (Weeks 3-4)
- Technical Analysis Agent
- Basic Portfolio Manager
- Sequential coordination layer
- Cost: $5-15/month

### Phase 3: Risk management (Weeks 5-6)
- Risk Manager Agent (Claude Sonnet 4)
- Position sizing, VaR, drawdown limits
- Safety features and circuit breakers
- Cost: $20-40/month

### Phase 4: Backtesting & paper trading (Weeks 7-10)
- 6-12 months historical backtesting
- 2-4 weeks paper trading (minimum)
- Success criteria: Positive returns, Sharpe > 0.5, latency < 500ms

### Phase 5: Live deployment (Week 11+)
- Start with 10-25% of intended capital
- Monitor closely for 2 weeks
- Scale gradually

---

## Critical Success Factors

### Before Going Live
- Minimum 2-4 weeks paper trading
- Positive returns in paper trading
- No critical errors or downtime
- Sharpe ratio > 0.5 (ideally > 1.0)

### Production Best Practices
- API keys in environment variables (never hardcode)
- Exponential backoff for rate limits
- Fallback models if primary unavailable
- Circuit breakers for cascading failures
- Daily review of all trades and reasoning

---

## Key Insights from Live Trading

### What Works (Alpha Arena Validated)
- **DeepSeek**: +35% (quantitative hedge fund backing, disciplined risk)
- **Claude Sonnet**: +28% (conservative risk, hybrid reasoning)
- Specialized small models for data collection
- Hierarchical supervisor-collaborator architecture

### What Failed
- **Gemini 2.5 Pro**: -39% (erratic high-frequency trading, no discipline)
- **GPT-5**: -27% (excessive caution, operational errors)

### The Reasoning Paradox
- High benchmark scores ≠ trading success
- Risk management and strategic consistency > raw reasoning ability
- Specialized training (DeepSeek hedge fund, Claude careful reasoning) beats general-purpose models

---

## Next Steps for Implementation

1. Set up exchange API accounts
2. Build basic data collection with Gemini Flash-Lite
3. Implement single Technical Analysis Agent
4. Add Claude Sonnet 4 for decision-making
5. Paper trade for minimum 2-4 weeks
6. Start live with small capital (10-25%)

---

## Important Notes

- **Never go straight to live trading** - always paper trade first
- **Trust the system but maintain kill switches**
- **Monitor daily** and adjust based on performance
- **Start conservative** (1% risk per trade)
- **The cost difference between models is negligible** compared to trading gains ($2-3/month)
- **Use both fast and slow thinking** - Claude for real-time, DeepSeek for strategic

---

## Questions to Answer During Development

1. Which exchange API? (Binance vs Coinbase vs others)
2. Trading pairs? (BTC/ETH only or broader?)
3. Time intervals? (15 min suggested for data collection)
4. Initial capital allocation?
5. Risk tolerance? (Conservative 1% or aggressive 2%+)
6. Framework preference? (CrewAI for speed or LangGraph for production?)

---

**Last Updated:** October 22, 2025
**Configuration:** Balanced (Gemini Flash-Lite + Claude Sonnet 4)
**Expected Cost:** $33/month with optimization
**Target:** Professional-grade AI trading system
