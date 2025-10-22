# CLAUDE.md

This file tells Claude Code how this autonomous trading bot project works.

## Project Vision - UPDATED STRATEGY (Oct 22, 2025)

Build a **100% free, fully autonomous trading bot** that:
1. Collects financial data from free sources (no paid APIs)
2. Uses local AI (Ollama) to analyze data and make decisions
3. Executes paper trades automatically via Alpaca API
4. **PRIMARY GOAL: $500/month profit from crypto/meme coins**
5. Runs 24/7 on dedicated hardware (AFTER validation)

**Philosophy: Keep everything SIMPLE, ROBUST, and EFFICIENT.**

---

## CRITICAL: Realistic Expectations

### What WON'T Work (Efficient Markets)
- **Stock trading bot beating S&P 500** - Unlikely (5% chance)
  - Market is too efficient
  - Hedge funds have billions in infrastructure
  - Congressional trades already priced in when posted
  - News sentiment analyzed by every algo instantly

### What MIGHT Work (Inefficient Markets)
- **Crypto/meme coin Twitter scraping** - Possible (30-40% chance)
  - Markets are emotional, retail-dominated
  - Information spreads slower than stocks
  - Twitter sentiment moves prices FAST
  - Bots can beat manual traders on speed
  - Small edges compound quickly

### Role of Stock Data
**Stock/congressional/SEC data = CONTEXT for AI decisions, NOT the primary trading signal.**

Use this data to:
- Give AI broader market context
- Understand macro trends
- Inform risk-on vs risk-off sentiment
- Feed into master reasoning agent

**Don't trade directly on this data (it won't work).**

---

## Current Strategy: Test First, Buy Later

### Phase 1: Validation (Current - Next 3 Months)
**Goal:** Prove crypto bot can be profitable BEFORE buying expensive hardware

**Testing Plan:**
1. Use current hardware (laptop/desktop) for initial dev
2. Rent cloud GPU if needed ($50-100/month) for testing
3. Build crypto/meme coin Twitter scraper (PRIMARY FOCUS)
4. Paper trade for 3 months
5. Track metrics: Win rate, P&L, Sharpe ratio, max drawdown

**Investment:** $0-500 for cloud GPU testing

**Decision Point After 3 Months:**
- ✅ Profitable? → Buy RTX 5090 server ($5,000)
- ❌ Not profitable? → Saved $4,500, learned valuable skills

### Phase 2: Scale If Validated
**Only buy dedicated hardware if bots show consistent profitability**

---

## System Architecture

### Two Main Components

**1. Data Collection (orchestrator.py)**
- Runs 24/7 collecting data from 8 free sources
- All scrapers managed by config file (`config/scrapers.yaml`)
- Auto-deduplicates and stores in databases
- No human intervention needed

**2. AI Analysis (llm_analysis.py)**
- CrewAI multi-agent system analyzes collected data
- Triage Agent (0xroyce/plutus 8B or fallback to llama3:8b) → filters important news
- Research Agent (martain7r/finance-llama-8b or fallback to llama3:8b) → summarizes events
- Master Agent (planned, qwen2.5:32b) → generates trading signals

**3. Crypto Bot (TO BE BUILT - PRIMARY FOCUS)**
- Twitter scraper for meme coin mentions
- Multi-source sentiment (Twitter + Discord + Telegram + Reddit)
- Fast execution (beat manual traders)
- Risk management (stop losses, position sizing)

**These run separately:** Orchestrator collects data continuously, AI analysis runs on-demand or scheduled.

---

## Data Sources (All Free Tier)

### News (ChromaDB)
- **NewsAPI**: 100 calls/day, US business headlines
- **RSS Aggregator**: Unlimited, 9 sources (MarketWatch, CNBC, Reuters via Google, Benzinga, Investing.com)
- Updates every 15 minutes
- ~500-700 articles/day
- **PURPOSE: Context for AI, not trading signals**

### Congressional Trades (PostgreSQL)
- **Senate Scraper**: Selenium-based, scrapes efdsearch.senate.gov
- **House Scraper**: PDF parsing + Selenium, clerk.house.gov
- Runs daily, processes new disclosures
- Tracks insider trading by politicians
- **PURPOSE: Context for AI, not trading signals**

### Economic Data (PostgreSQL)
- **FRED API**: GDP, unemployment, Fed funds rate, CPI
- Unlimited free tier
- Updates daily
- **PURPOSE: Macro context for risk-on/risk-off decisions**

### SEC Filings (PostgreSQL)
- **EDGAR RSS**: Monitors 8-K, 10-K, 10-Q, Form 4
- Unlimited free tier
- Updates every 10 minutes
- **PURPOSE: Context for AI, correlation with crypto sentiment**

### Company Fundamentals (PostgreSQL)
- **FMP API**: 250 calls/day, company profiles for 23 tickers
- **yfinance**: Unlimited, supplemental company data
- Updates daily
- **PURPOSE: Context for AI decisions**

### Crypto Data (TO BE ADDED - PRIMARY FOCUS)
- **Twitter API** (free tier): Track meme coin mentions, influencer tweets
- **Pump.fun API**: Monitor new token launches
- **Solana DEX APIs**: Track volume, price movements
- **Discord/Telegram scrapers**: Community sentiment
- **PURPOSE: PRIMARY TRADING SIGNALS**

---

## Tech Stack

**AI & Analysis:**
- CrewAI for multi-agent workflows
- Ollama (local) with finance-specialized models:
  - 0xroyce/plutus (8B) - Triage
  - martain7r/finance-llama-8b (8B) - Research
  - qwen2.5:32b (32B) - Master reasoning (when hardware allows)
- DuckDuckGo search + web scraping tools (available but not yet enabled)

**Databases:**
- PostgreSQL (port 54594, user/pass: postgres/postgres)
  - `congressional_trades` - Senate/House trade disclosures
  - `sec_filings` - SEC EDGAR filings
  - `economic_indicators` - FRED macroeconomic data
  - `company_profiles` - Company fundamentals
  - `crypto_signals` (to be added) - Crypto trading signals
- ChromaDB (`chroma_db_news/`)
  - `news_articles` - News with metadata (URL-based deduplication)
  - `crypto_mentions` (to be added) - Twitter/social mentions

**Web Scraping:**
- Selenium + ChromeDriver (congressional trades, Twitter)
- BeautifulSoup4 (HTML parsing)
- feedparser (RSS feeds)
- pdfplumber (House PDF disclosures)

---

## Project Structure

```
pjx/
├── orchestrator.py          # Manages all scrapers
├── llm_analysis.py          # CrewAI AI analysis (renamed from ai_analysis.py)
├── config/
│   └── scrapers.yaml        # Scraper config (easy to add new ones!)
├── outputs/
│   └── triage_results.txt   # AI analysis output
├── logs/                    # All scraper logs
├── senate_scraper/
│   └── senate_scraper.py
├── house_scraper/
│   └── house_scraper.py
├── news_scrapers/
│   ├── newsapi_reader.py
│   └── rss_aggregator.py
├── data_api/
│   └── fred_data_reader.py
├── sec_data/
│   └── edgar_rss_reader.py
├── fundamentals_data/
│   ├── fmp_fundamentals_reader.py
│   └── yfinance_fundamentals_reader.py
└── crypto_scrapers/         # TO BE BUILT
    ├── twitter_scraper.py   # PRIMARY FOCUS
    ├── pumpfun_monitor.py
    └── sentiment_analyzer.py
```

---

## How It Works

### Orchestrator System (config-driven)
1. Reads `config/scrapers.yaml`
2. Starts all enabled scrapers as background processes
3. Monitors their health
4. Handles graceful shutdown (Ctrl+C)

**Key insight:** Congressional/daily scrapers run once and exit (normal behavior). News scrapers run continuously. Orchestrator warnings about "stopped unexpectedly" are harmless for daily scrapers.

### Adding New Scrapers
Edit `config/scrapers.yaml` - add 6 lines:
```yaml
  - name: My Scraper
    script: path/to/scraper.py
    category: news|congressional|economic|sec|fundamentals|crypto
    enabled: true
    free_tier: "API limit"
    interval: "frequency"
```
Restart orchestrator. Done! No code changes needed.

### Data Deduplication
- PostgreSQL: UNIQUE constraints on key columns
- ChromaDB: Uses URL as document ID
- Prevents bloat from continuous scraping

---

## Running the System

**Start data collection:**
```bash
python orchestrator.py
```

**Run AI analysis:**
```bash
python llm_analysis.py
```

**Test system health:**
```bash
python system_test.py
```

---

## Configuration Details

### Database Connection
- PostgreSQL port: **54594** (not default 5432!)
- Credentials: postgres/postgres
- All scrapers hardcoded to this port

### API Keys (Hardcoded)
- NewsAPI: `news_scrapers/newsapi_reader.py` line 13
- FRED: `data_api/fred_data_reader.py` line 8
- FMP: `fundamentals_data/fmp_fundamentals_reader.py` line 9
- Twitter API: (to be added)

### Log Paths
All scrapers write to `logs/scraper_name.log` (relative to project root)

### CrewAI Settings
- Memory: **DISABLED** in llm_analysis.py (prevents OpenAI API errors)
- Tools available but not enabled: DuckDuckGo search, web scraper
- Output: `outputs/triage_results.txt`

### Ollama Settings (VRAM Management)
```bash
OLLAMA_MAX_LOADED_MODELS=4        # Max models in VRAM at once
OLLAMA_NUM_PARALLEL=2             # Parallel requests per model
OLLAMA_MAX_QUEUE=512              # Max queued requests
OLLAMA_KEEP_ALIVE=30m             # Keep model in memory for 30 min
```

---

## Development Guidelines

### CRITICAL Rules
1. **Everything must be FREE** - research API limits before adding anything
2. **Keep it SIMPLE** - easy to understand, maintain, and debug
3. **Build for AUTONOMY** - no manual intervention ever
4. **Avoid DATA BLOAT** - use deduplication everywhere
5. **Make it EXPANDABLE** - config-driven, not code-driven
6. **VALIDATE FIRST** - test strategies before buying expensive hardware
7. **FOCUS ON EDGE** - crypto/meme coins, not stocks

### When Adding Features
- Can it run for free forever? If no, don't add it.
- Can it run without human intervention? If no, rethink it.
- Does it add real value for trading decisions? If no, skip it.
- Does it work in inefficient markets? If no, don't waste time.

### Code Style
- Simple and readable over clever
- Log everything important
- Fail gracefully with error messages
- Test with free tier limits

---

## Current Status (Oct 22, 2025)

**Data Collection:** ✅ Fully operational
- 8 scrapers running
- ~500-700 news articles/day
- 2,800+ congressional trades
- 70+ SEC filings
- All auto-deduplicating

**AI Analysis:** ✅ Basic system working
- Triage + Research agents functional
- Web tools coded but not enabled yet
- Master reasoning agent planned
- Updated to use finance-specialized models (Plutus, Finance-Llama)

**Crypto Bot:** ❌ Not yet built (NEXT PRIORITY)
- Twitter scraper needed
- Sentiment analysis needed
- Paper trading framework needed

**Trading:** ❌ Not yet implemented
- Paper trading via Alpaca API planned
- Need backtesting system first
- Risk management system needed

**Hardware:** Using current hardware for testing
- No dedicated server purchased yet
- Will rent cloud GPU if needed for heavier models
- RTX 5090 server purchase ONLY after validation

---

## Known Issues

1. **House scraper PDF parsing**: Some PDFs have weird formats, transactions fail to parse (non-critical, continues anyway)
2. **Senate scraper**: Skips some PDF formats (noted in TODO)
3. **FMP API**: Limited to 23 tickers (can expand with yfinance)
4. **Orchestrator warnings**: Shows "stopped unexpectedly" for daily scrapers that finish their job (harmless, expected behavior)

---

## Roadmap

**Phase 1: Data Infrastructure** ✅ COMPLETE
- All scrapers operational
- Databases stable
- Deduplication working

**Phase 2: Crypto Bot Development** 🚧 CURRENT FOCUS
- Build Twitter scraper for meme coins
- Add Pump.fun monitoring
- Multi-source sentiment analysis
- Paper trading framework
- Performance tracking (win rate, P&L, Sharpe ratio)

**Phase 3: Validation (3 months)** 📋 NEXT
- Paper trade crypto bot for 3 months
- Track all metrics
- Test different market conditions
- Validate profitability

**Phase 4: Hardware Investment** 📋 IF VALIDATED
- Buy RTX 5090 server ($5,000) ONLY if profitable
- Deploy all bots on dedicated hardware
- Scale to multiple strategies

**Phase 5: Production** 📋 PLANNED
- Monitoring/alerting
- Performance dashboard
- Transition to live trading (if profitable)
- Add more edge sources (NFTs, etc. if opportunities emerge)

---

## Success Metrics

**Data Collection:**
- [x] 500+ news articles/day
- [x] Zero duplicate entries in databases
- [x] <1% scraper failure rate

**Crypto Bot (TO BE MEASURED):**
- [ ] Win rate > 55%
- [ ] Average gain/loss ratio > 2:1
- [ ] Max drawdown < 20%
- [ ] $500+/month profit (paper trading)
- [ ] Sharpe ratio > 1.0

**Hardware Decision:**
- [ ] 3 months of consistent profitability
- [ ] $500+/month average profit
- [ ] Validated across different market conditions

---

## Important Context for Claude

### User Profile
- **Age:** 23 years old (just turned)
- **Education:** Completing software development degree
- **Goal:** Build AI systems that make money autonomously
- **Budget:** Limited (student), needs validation before big purchases
- **Interest:** Crypto/meme coins, NFTs if they return, "anywhere with edge"

### Strategy Philosophy
- Stock market = **Context only** (user already knows it won't beat S&P 500)
- Crypto/meme coins = **Primary edge** (inefficient markets, bot speed advantage)
- Congressional/SEC data = **Context for AI**, not direct trading signals
- Hardware = **Buy AFTER validation**, not before

### When User Asks for Changes
- Always research if new APIs are free tier
- Keep changes simple and maintainable
- Update `config/scrapers.yaml` for new scrapers (don't modify orchestrator code)
- Test that scrapers can run standalone before adding to orchestrator
- Focus on crypto/meme coin edge opportunities
- Validate strategies before suggesting expensive infrastructure

### File Naming & Organization
- Scrapers should have descriptive names (not "main.py" or "app.py")
- Logs go to `logs/` folder
- Outputs go to `outputs/` folder
- Config goes to `config/` folder
- Keep root directory clean

### Virtual Environment
- Located at `.venv/Scripts/python.exe`
- Has all packages installed
- User sometimes uses system Python, sometimes venv (both work)

### Common Requests
- "Add a new scraper" → Edit config/scrapers.yaml
- "Fix scraper" → Check logs first, then debug
- "Test everything" → Run system_test.py
- "Make it better" → Focus on crypto bot and validation metrics
- "Should I buy hardware?" → Not until validated!

---

## Testing Commands

```bash
# Pre-flight check
python quick_test.py

# Full system test
python system_test.py

# Start orchestrator
python orchestrator.py

# Run AI analysis
python llm_analysis.py
```

---

## Remember

This is a **learning project with profit potential**. The user wants it to be:
- Completely free to operate (or close to it)
- Fully autonomous (set and forget)
- Actually profitable in crypto/meme coins (realistic 30-40% chance)
- Simple enough to maintain and debug
- Expandable as new edge opportunities emerge
- **VALIDATED before expensive hardware purchase**

**Value even if it doesn't make money:**
- Skills learned = $80k-120k/year jobs
- Portfolio project for resume
- Deep understanding of AI, finance, system architecture
- Foundation for future opportunities

**Always prioritize:**
1. Crypto/meme coin edge (primary focus)
2. Validation before investment
3. Simplicity and robustness
4. Learning and skill development
