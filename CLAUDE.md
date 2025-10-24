# CLAUDE.md

Instructions for Claude Code on the PJX Crypto Trading System.

---

## Current Project Focus

**PRIMARY GOAL: Build a robust data collection system**

We are building a **data scraping infrastructure** to collect market data, then use **AI (Claude API) to analyze and make trading decisions**.

Trading execution comes MUCH LATER.

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
- **Keep files under 800 lines** - if longer, split into new files
- **DO NOT move files without asking** - you can create new files but no moving
- **NEVER create new virtual environments** - use existing setup
- **Update requirements.txt** after adding any new package

### Code Style
- **No fake/synthetic data** - always use real data or fail the script
- **Minimal error handling** - user wants to see errors, not over-engineered try/except blocks
- **Minimal comments** - code should be self-explanatory, don't over-comment
- **Simple over clever** - readable code beats clever optimizations

---

## Current System (8 Active Scrapers)

### Data Collection
1. **News** - NewsAPI + RSS → ChromaDB
2. **Congressional Trades** - Senate + House → PostgreSQL
3. **SEC Filings** - EDGAR RSS → PostgreSQL
4. **Economic Data** - FRED API → PostgreSQL
5. **Company Fundamentals** - FMP + yfinance → PostgreSQL

### Infrastructure
- **PostgreSQL** (Docker, port 54594) - Structured data
- **ChromaDB** (chroma_db_news/) - News vectors
- **Orchestrator** - Manages all scrapers via config/scrapers.yaml
- **.env file** - All API keys in one place

---

## Next to Build

### 1. Twitter/X Sentiment Scraper
- Use **twikit** library (FREE, no $100/month API)
- Search by keywords: BTC, ETH, SOL, PEPE, DOGE
- Analyze sentiment with HuggingFace model
- Store in PostgreSQL

### 2. Crypto Price Data
- CoinGecko API (free tier: 10k calls/month)
- Track BTC, ETH, SOL, PEPE, DOGE prices
- Store in PostgreSQL

### 3. AI Decision Layer (Later)
- Pull data from PostgreSQL
- Send to Claude API for analysis
- Get BUY/SELL/HOLD decision + reasoning
- Log decisions to database

---

## Tech Stack

### Databases
- **PostgreSQL** (port 54594) - All structured data
- **ChromaDB** - News article vectors

### Free/Cheap APIs
- **NewsAPI** - 100 calls/day (free)
- **FRED** - Unlimited (free)
- **FMP** - 250 calls/day (free)
- **CoinGecko** - 10k calls/month (free)
- **TwiKit** - Unlimited (free, no API key)
- **Claude Sonnet 4** - $10-15/month (when we build AI layer)

### Key Libraries
- `psycopg2-binary` - PostgreSQL
- `chromadb` - Vector database
- `twikit` - Twitter scraping (free!)
- `transformers` - Sentiment analysis
- `anthropic` - Claude API (later)
- `requests` - HTTP calls
- `python-dotenv` - Environment variables

---

## How to Add a Scraper

### 1. Create the scraper file
```bash
# Example: crypto_scrapers/twitter_sentiment.py
```

### 2. Add to config/scrapers.yaml
```yaml
- name: Twitter Sentiment
  script: crypto_scrapers/twitter_sentiment.py
  category: crypto
  description: Analyzes Twitter sentiment for crypto
  enabled: true
  free_tier: "Free (twikit)"
  interval: "15 minutes"
```

### 3. Add API keys to .env (if needed)
```bash
TWITTER_USERNAME=your_username
TWITTER_EMAIL=your_email
TWITTER_PASSWORD=your_password
```

### 4. Update requirements.txt
```bash
pip freeze > requirements.txt
```

---

## Database Tables

### Current Tables
1. `congressional_trades` - Senate + House trade data
2. `economic_indicators` - FRED economic data
3. `sec_filings` - SEC filing data
4. `company_profiles` - Company fundamentals

### To Add
- `crypto_prices` - BTC/ETH/SOL price data
- `twitter_sentiment` - Crypto sentiment from Twitter

Create new tables in `data/` folder, then run:
```bash
psql -h localhost -p 54594 -U postgres -d postgres -f data/new_table.sql
```

---

## Running the System

### Start all scrapers
```bash
python orchestrator.py
```

### View logs
```bash
# Check outputs/ and logs/ folders
```

---

## Guidelines for Claude Code

### DO:
- ✅ Ask before creating multiple files
- ✅ Build one component at a time
- ✅ Use real data (no synthetic/fake data)
- ✅ Keep code simple and readable
- ✅ Update requirements.txt when adding packages

### DON'T:
- ❌ Move files without asking
- ❌ Build complex multi-agent systems
- ❌ Use local LLMs (APIs are cheaper)
- ❌ Create 5+ files at once
- ❌ Build trading execution until data + AI validated

---

## Project Goal

**Build a learning-first crypto trading system:**
- Learn AI/data systems
- Build portfolio project
- Gain real-world skills
- (Eventually) Target $500/month profit

**Keep it simple. Build step-by-step. Test everything.**


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