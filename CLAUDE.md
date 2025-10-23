# CLAUDE.md

Instructions for Claude Code on the PJX Crypto Trading System.

---

## Current Project Focus (Updated Oct 23, 2025)

**PRIMARY GOAL: Build a robust data collection and AI decision system**

We are NOT focused on trading execution yet. We are building:
1. **Data scraping infrastructure** - Collect all relevant data
2. **Database architecture** - Store data optimally for AI analysis
3. **AI decision chain** - Use Claude API to analyze data and make decisions

Trading on exchanges (HyperLiquid, Extended, etc.) comes MUCH LATER.

---

## Development Philosophy

### Work Step-by-Step
- **Build ONE thing at a time** - No big complex systems
- **Test each component** before moving to the next
- **Keep iterations small** - A few files at a time, not 10+ files
- **Simple and clean** over clever and complex

### Use APIs, Not Local Models
- **Claude Sonnet 4** for trading decisions (~$10-15/month)
- **Gemini Flash** for data processing (~$1-2/month)
- **DeepSeek** for strategic analysis (~$5-10/month)
- **NO local LLMs** - APIs are cheaper than $5k GPU server

---

## Development Rules

### File Management
- **Keep files under 800 lines** - if longer, split into new files and update README
- **DO NOT move files without asking** - you can create new files but no moving
- **NEVER create new virtual environments** - use existing setup
- **Update requirements.txt** after adding any new package

### Code Style
- **No fake/synthetic data** - always use real data or fail the script
- **Minimal error handling** - user wants to see errors, not over-engineered try/except blocks
- **Minimal comments** - code should be self-explanatory, don't over-comment
- **Simple over clever** - readable code beats clever optimizations

---

## Current System Status

### ✅ What's Working (Your Existing System)
**Data Collection (8 scrapers):**
- News scrapers (NewsAPI + RSS) → ChromaDB (340+ articles)
- Congressional trades (Senate + House) → PostgreSQL (2,822 trades)
- SEC filings → PostgreSQL (68 filings)
- Economic data (FRED) → PostgreSQL (5 indicators)
- Company fundamentals (FMP + yfinance) → PostgreSQL (23 profiles)

**Infrastructure:**
- PostgreSQL database (Docker, port 54594)
- ChromaDB for news vectors
- Orchestrator manages all scrapers
- CrewAI for news triage/research
- All API keys in single `.env` file

### ❌ What's NOT Built Yet
- Crypto price data scraper (simple CoinGecko API)
- AI trading decision system (Claude API integration)
- Decision logging/tracking
- Paper trading validation (LATER)
- Exchange connections (MUCH LATER)

---

## System Architecture

### Phase 1: DATA LAYER (Current Focus)
```
Data Sources → Scrapers → PostgreSQL/ChromaDB
```

**Existing Sources:**
- News (business headlines, RSS feeds)
- Congressional trades (Senate, House)
- SEC filings (8-K, 10-K, insider trades)
- Economic data (GDP, unemployment, rates)
- Fundamentals (market cap, P/E, sector)

**To Add:**
- Crypto prices (BTC, ETH, SOL, PEPE, DOGE)
- Crypto volume/liquidity data
- (Maybe later) Social sentiment

### Phase 2: AI DECISION LAYER (Next Step)
```
PostgreSQL Data → Claude API → Trading Decisions → Log to DB
```

**How it works:**
1. Pull all relevant data from database
2. Format into prompt for Claude
3. Claude analyzes and returns: BUY/SELL/HOLD + confidence + reasoning
4. Log decision to `trading_decisions` table
5. Review decisions manually to validate AI is working

### Phase 3: VALIDATION LAYER (Later)
```
Track AI decisions → Compare to actual prices → Calculate if profitable
```

### Phase 4: EXECUTION LAYER (Much Later)
```
Connect to exchange → Execute validated strategies → Monitor performance

## Tech Stack

### Databases
- **PostgreSQL** (port 54594) - Structured data
- **ChromaDB** (chroma_db_news/) - News vectors

### APIs (Pay-as-you-go)
- **Claude Sonnet 4** - Trading decisions (~$10-15/month)
- **Gemini Flash** - Data processing (~$1-2/month)
- **CoinGecko** - Crypto prices (free tier: 10k calls/month)
- **NewsAPI** - Business news (free tier: 100 calls/day)
- **FRED** - Economic data (free, unlimited)
- **FMP** - Company fundamentals (free tier: 250 calls/day)

### Python Libraries
- `psycopg2-binary` - PostgreSQL
- `chromadb` - Vector database
- `anthropic` - Claude API
- `requests` - HTTP calls
- `selenium` - Web scraping
- `crewai` - Multi-agent orchestration
- `python-dotenv` - Environment variables

---

## Adding New Components

### 1. Add a New Scraper
Edit `config/scrapers.yaml`:
```yaml
- name: Crypto Prices
  script: crypto_prices.py
  category: crypto
  description: Fetches BTC/ETH/SOL prices from CoinGecko
  enabled: true
  free_tier: "10,000 calls/month"
  interval: "15 minutes"
```

### 2. Add a New API Key
Add to `.env`:
```
COINGECKO_API_KEY=your_key_here
```

### 3. Add a New Database Table
Create SQL file in `data/` folder, then run:
```bash
psql -h localhost -p 54594 -U postgres -d postgres -f data/new_table.sql
```

---

## Current Workflow

### Daily Data Collection
```bash
# Start orchestrator (runs all scrapers)
python orchestrator.py

# Scrapers run every 15 minutes (news, crypto prices)
# Or daily (congressional, economic)
# Data flows into PostgreSQL/ChromaDB automatically
```

### AI Analysis (When Ready)
```bash
# Run Claude decision maker
python trading_decision.py

# Reviews all data, makes decision, logs to database
# You manually review decisions to validate
```

---

## What We're Building Toward (Long-term Vision)

**Eventually**, this system will:
1. Collect data from multiple sources (✅ mostly done)
2. AI analyzes data and suggests trades (← building this next)
3. Paper trade to validate strategies (← later)
4. Execute real trades on HyperLiquid/Extended (← much later)
5. Target: $500/month profit from crypto trading

**But for now**: Just focus on data + AI decisions, nothing else.

---

## User Context

**Profile:**
- Age: 23, completing software dev degree
- Budget: Limited (student) - prefer free/cheap APIs over hardware
- Experience: Building this to learn AI/trading/systems
- Goal: $500/month profit eventually, but skills/portfolio are valuable too

**Strategy:**
- Use APIs instead of buying GPU hardware
- Start simple, add complexity only when needed
- Validate with data before spending money
- Build for learning first, profit second

---

## Guidelines for Claude Code

### When Building Features
1. **Ask first** - Don't create 10 files without asking
2. **One file at a time** - Build incrementally
3. **Test immediately** - Don't build untested code
4. **Keep it simple** - Readable > clever
5. **Real data only** - No synthetic/fake data

### When User Asks for Changes
1. **Understand the goal** - Ask clarifying questions
2. **Propose simple solution** - Not complex multi-file systems
3. **Check API costs** - Prefer free tiers
4. **Update requirements.txt** - Keep dependencies tracked
5. **Don't move files** - Only create new ones

### What NOT to Do
- ❌ Don't build complex multi-agent systems
- ❌ Don't create 5+ files at once
- ❌ Don't suggest buying hardware
- ❌ Don't use local LLMs (APIs are cheaper)
- ❌ Don't write papers trading code until data works
- ❌ Don't connect to exchanges until AI is validated

---

## Next Steps (Immediate)

1. **Get Claude API key** - console.anthropic.com ($5 free credit)
2. **Build crypto_prices.py** - Simple CoinGecko scraper
3. **Build trading_decision.py** - Claude integration for decisions
4. **Test the full flow** - Data → AI → Decisions → Log
5. **Review decisions** - Validate AI makes sense

---

## Remember

**This is a learning project first, profit second.**

Even if it never makes $500/month:
- You're learning AI systems
- You're building a portfolio project
- You're gaining skills worth $80-120k/year jobs
- You're understanding markets/trading/data

**Keep it simple. Build step-by-step. Test everything.**
