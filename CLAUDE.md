# CLAUDE.md

This file tells Claude Code how this autonomous trading bot project works.

## Project Vision

Build a **100% free, fully autonomous trading bot** that:
1. Collects financial data from free sources (no paid APIs)
2. Uses local AI (Ollama) to analyze data and make decisions
3. Executes paper trades automatically via Alpaca API
4. **Goal: Beat S&P 500 by 5-10% annually** (alpha generation)
5. Runs 24/7 on a dedicated server with zero manual intervention

**Philosophy: Keep everything SIMPLE, ROBUST, and EFFICIENT.**

---

## System Architecture

### Two Main Components

**1. Data Collection (orchestrator.py)**
- Runs 24/7 collecting data from 8 free sources
- All scrapers managed by config file (`config/scrapers.yaml`)
- Auto-deduplicates and stores in databases
- No human intervention needed

**2. AI Analysis (ai_analysis.py)**
- CrewAI multi-agent system analyzes collected data
- Triage Agent (phi3:mini) → filters important news
- Research Agent (llama3:8b) → summarizes events
- Master Agent (planned, deepseek-coder:33b) → generates trading signals

**These run separately:** Orchestrator collects data continuously, AI analysis runs on-demand or scheduled.

---

## Data Sources (All Free Tier)

### News (ChromaDB)
- **NewsAPI**: 100 calls/day, US business headlines
- **RSS Aggregator**: Unlimited, 9 sources (MarketWatch, CNBC, Reuters via Google, Benzinga, Investing.com)
- Updates every 15 minutes
- ~500-700 articles/day

### Congressional Trades (PostgreSQL)
- **Senate Scraper**: Selenium-based, scrapes efdsearch.senate.gov
- **House Scraper**: PDF parsing + Selenium, clerk.house.gov
- Runs daily, processes new disclosures
- Tracks insider trading by politicians

### Economic Data (PostgreSQL)
- **FRED API**: GDP, unemployment, Fed funds rate, CPI
- Unlimited free tier
- Updates daily

### SEC Filings (PostgreSQL)
- **EDGAR RSS**: Monitors 8-K, 10-K, 10-Q, Form 4
- Unlimited free tier
- Updates every 10 minutes

### Company Fundamentals (PostgreSQL)
- **FMP API**: 250 calls/day, company profiles for 23 tickers
- **yfinance**: Unlimited, supplemental company data
- Updates daily

---

## Tech Stack

**AI & Analysis:**
- CrewAI for multi-agent workflows
- Ollama (local) with phi3:mini, llama3:8b, deepseek-coder:33b
- DuckDuckGo search + web scraping tools (available but not yet enabled)

**Databases:**
- PostgreSQL (port 54594, user/pass: postgres/postgres)
  - `congressional_trades` - Senate/House trade disclosures
  - `sec_filings` - SEC EDGAR filings
  - `economic_indicators` - FRED macroeconomic data
  - `company_profiles` - Company fundamentals
- ChromaDB (`chroma_db_news/`)
  - `news_articles` - News with metadata (URL-based deduplication)

**Web Scraping:**
- Selenium + ChromeDriver (congressional trades)
- BeautifulSoup4 (HTML parsing)
- feedparser (RSS feeds)
- pdfplumber (House PDF disclosures)

---

## Project Structure

```
pjx/
├── orchestrator.py          # Manages all 8 scrapers
├── ai_analysis.py           # CrewAI AI analysis
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
└── fundamentals_data/
    ├── fmp_fundamentals_reader.py
    └── yfinance_fundamentals_reader.py
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
    category: news|congressional|economic|sec|fundamentals
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
python ai_analysis.py
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

### Log Paths
All scrapers write to `logs/scraper_name.log` (relative to project root)

### CrewAI Settings
- Memory: **DISABLED** in ai_analysis.py (prevents OpenAI API errors)
- Tools available but not enabled: DuckDuckGo search, web scraper
- Output: `outputs/triage_results.txt`

---

## Development Guidelines

### CRITICAL Rules
1. **Everything must be FREE** - research API limits before adding anything
2. **Keep it SIMPLE** - easy to understand, maintain, and debug
3. **Build for AUTONOMY** - no manual intervention ever
4. **Avoid DATA BLOAT** - use deduplication everywhere
5. **Make it EXPANDABLE** - config-driven, not code-driven

### When Adding Features
- Can it run for free forever? If no, don't add it.
- Can it run without human intervention? If no, rethink it.
- Does it add real value for trading decisions? If no, skip it.

### Code Style
- Simple and readable over clever
- Log everything important
- Fail gracefully with error messages
- Test with free tier limits

---

## Current Status

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

**Trading:** ❌ Not yet implemented
- Paper trading via Alpaca API planned
- Need backtesting system first
- Risk management system needed

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

**Phase 2: Enhanced AI** 🚧 IN PROGRESS
- Enable web tools for Research Agent
- Add Master Reasoning Agent (deepseek-coder:33b)
- Build backtesting framework

**Phase 3: Paper Trading** 📋 PLANNED
- Integrate Alpaca API
- Implement position sizing
- Add risk management
- Track performance metrics

**Phase 4: Production** 📋 PLANNED
- Windows Task Scheduler automation
- Monitoring/alerting
- Performance dashboard
- Transition to live trading (if profitable)

---

## Important Context for Claude

### When User Asks for Changes
- Always research if new APIs are free tier
- Keep changes simple and maintainable
- Update `config/scrapers.yaml` for new scrapers (don't modify orchestrator code)
- Test that scrapers can run standalone before adding to orchestrator

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
- "Make it better" → Focus on data quality and AI analysis, not more scrapers

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
python ai_analysis.py
```

---

## Success Metrics

**Data Collection:**
- [ ] 500+ news articles/day
- [ ] Zero duplicate entries in databases
- [ ] <1% scraper failure rate

**AI Analysis:**
- [ ] Correctly identifies market-moving news (>80% accuracy)
- [ ] Generates actionable signals
- [ ] Low false positive rate

**Trading (when implemented):**
- [ ] 5-10% annual alpha vs S&P 500
- [ ] Sharpe ratio > 1.0
- [ ] Max drawdown < 15%
- [ ] Win rate > 55%

---

## Remember

This is a **long-term project** to build a profitable automated trading system. The user wants it to be:
- Completely free to operate
- Fully autonomous (set and forget)
- Actually profitable (not just a cool demo)
- Simple enough to maintain and debug
- Expandable as new data sources become available

**Always prioritize simplicity and robustness over complexity and features.**
