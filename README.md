# Autonomous Trading Bot

**Goal:** 100% free, locally-run trading bot that beats S&P 500 by 5-10% annually using AI analysis.

---

## Quick Start

### Prerequisites
- PostgreSQL on `localhost:54594` (user/pass: postgres/postgres)
- Ollama running: `ollama serve`
- Models installed: `ollama pull phi3:mini llama3:8b`

### Run Everything
```bash
# Terminal 1: Start data collection (runs all 8 scrapers)
python orchestrator.py

# Terminal 2: Run AI analysis (analyzes collected data)
python ai_analysis.py

# Stop everything: Press Ctrl+C in orchestrator terminal
```

---

## System Architecture

### Data Collection (orchestrator.py)
Manages 8 scrapers that collect data 24/7:
- **News**: NewsAPI (100/day) + RSS feeds (unlimited, 9 sources)
- **Congressional Trades**: Senate + House disclosure scrapers
- **Economic**: FRED macroeconomic indicators
- **SEC**: EDGAR filings (8-K, 10-K, 10-Q, Form 4)
- **Company Data**: FMP + yfinance fundamentals

All scrapers auto-deduplicate and save to databases.

### AI Analysis (ai_analysis.py)
CrewAI agents analyze the collected data:
1. **Triage Agent** (phi3:mini) - Classifies news as "Investigate" or "Ignore"
2. **Research Agent** (llama3:8b) - Summarizes important news
3. **Master Agent** (planned) - Generates trading signals

### Databases
- **PostgreSQL** (port 54594): Congressional trades, SEC filings, economic data, company profiles
- **ChromaDB**: News articles with metadata

---

## Adding New Data Sources

Edit `config/scrapers.yaml` and add:
```yaml
  - name: My New Scraper
    script: path/to/scraper.py
    category: news|congressional|economic|sec|fundamentals
    enabled: true
    free_tier: "API limit info"
    interval: "how often it runs"
```

Restart orchestrator. That's it!

---

## Project Structure

```
pjx/
├── orchestrator.py          # Manages all data scrapers
├── ai_analysis.py           # AI analysis with CrewAI
├── config/
│   └── scrapers.yaml        # Scraper configuration
├── outputs/
│   └── triage_results.txt   # AI analysis output
├── logs/                    # All scraper logs
├── senate_scraper/          # Senate trade scraper
├── house_scraper/           # House trade scraper
├── news_scrapers/           # News scrapers (NewsAPI, RSS)
├── data_api/                # Economic data (FRED)
├── sec_data/                # SEC filings scraper
└── fundamentals_data/       # Company data scrapers
```

---

## Tech Stack

- **AI**: CrewAI + Ollama (phi3:mini, llama3:8b, deepseek-coder:33b planned)
- **Databases**: PostgreSQL, ChromaDB
- **Scraping**: Selenium, BeautifulSoup, feedparser
- **APIs**: NewsAPI, FRED, FMP, yfinance (all free tiers)

---

## Configuration

### Database
- PostgreSQL port: `54594` (not default 5432)
- Credentials: postgres/postgres

### API Keys
Hardcoded in scraper files:
- NewsAPI: `news_scrapers/newsapi_reader.py` line 13
- FRED: `data_api/fred_data_reader.py` line 8
- FMP: `fundamentals_data/fmp_fundamentals_reader.py` line 9

### Scrapers
Edit `config/scrapers.yaml` to enable/disable scrapers.

---

## Testing

### Quick System Check
```bash
python quick_test.py
```
Verifies all files exist and config is correct.

### Full System Test
```bash
python system_test.py
```
Checks databases, connections, and data collection.

---

## Troubleshooting

**Orchestrator shows "[WARNING] scraper stopped unexpectedly"**
- For congressional/daily scrapers: This is normal! They run once and exit.
- For news scrapers: Check logs in `logs/` folder for actual errors.

**Scraper won't start**
- Check script exists: `ls path/to/scraper.py`
- Run directly to see error: `python path/to/scraper.py`
- Check log file in `logs/` folder

**No data being collected**
- Verify PostgreSQL is running: `python system_test.py`
- Check API keys are valid
- Look for ERROR messages in logs

**How to check database status**
```bash
python system_test.py
# Shows row counts and latest dates for all tables
```

---

## Development Guidelines

✅ **Always use free tier APIs** - research limits before adding
✅ **Keep it simple** - easy to understand and maintain
✅ **Auto-deduplicate** - prevent data bloat
✅ **Build for autonomy** - no manual intervention needed

---

## Roadmap

**Phase 1: Data Collection** ✅ COMPLETE
- All 8 scrapers operational

**Phase 2: Expand News** ✅ COMPLETE
- Added RSS aggregator (9 sources, unlimited)

**Phase 3: Enhanced AI** (In Progress)
- [ ] Enable web tools for Research Agent
- [ ] Add Master Reasoning Agent (deepseek-coder:33b)
- [ ] Build backtesting system

**Phase 4: Paper Trading** (Planned)
- [ ] Integrate Alpaca API
- [ ] Implement risk management
- [ ] Track performance metrics

---

## Current Status

**Databases (as of last check):**
- 2,822 congressional trades
- 340 news articles (growing every 15 min)
- 68 SEC filings
- 5 economic indicators
- 23 company profiles

**System:** Fully operational and collecting data 24/7.

---

## Files You Care About

- **README.md** ← You are here
- **TODO.txt** ← Next tasks
- **config/scrapers.yaml** ← Add/remove scrapers
- **orchestrator.py** ← Start this to collect data
- **ai_analysis.py** ← Run this to analyze data

That's it! Keep it simple.
