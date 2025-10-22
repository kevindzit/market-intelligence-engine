# Autonomous Trading Bot

**Goal:** Make $500/month profit from crypto/meme coin trading using AI + Twitter scraping.

---

## Quick Start

### Prerequisites
- PostgreSQL on `localhost:54594` (user/pass: postgres/postgres)
- Ollama running: `ollama serve`

### Run System
```bash
# Start data collection (all 8 scrapers)
python orchestrator.py

# Run AI analysis
python llm_analysis.py

# Test everything
python system_test.py
```

---

## What Works Now

### Data Collection ✅
8 scrapers running 24/7:
- News (NewsAPI + RSS feeds)
- Congressional trades (Senate + House)
- SEC filings (EDGAR RSS)
- Economic data (FRED)
- Company fundamentals (FMP + yfinance)

All data auto-deduplicates and saves to PostgreSQL + ChromaDB.

### AI Analysis ✅
CrewAI agents analyze news:
- Triage Agent (Plutus 8B or llama3:8b) - Filters important news
- Research Agent (Finance-Llama 8B or llama3:8b) - Summarizes events

---

## What to Build Next

### Crypto Twitter Scraper (PRIORITY)
Your real edge is crypto/meme coins, not stocks.

**Why:** Inefficient markets + speed advantage over humans = profit potential

**What you need:**
1. Twitter API or Selenium scraper
2. Track meme coin mentions ($SOL, $PEPE, pump.fun, etc.)
3. Store in PostgreSQL
4. Sentiment analysis with AI

**Goal:** Catch pumps before manual traders (20-500% gains in minutes)

### Paper Trading Framework
Track all signals without risking money:
- Log entry/exit prices
- Calculate P&L, win rate, Sharpe ratio
- Measure max drawdown

**Goal:** Prove profitability before investing in hardware

---

## System Architecture

### Orchestrator (orchestrator.py)
Manages all scrapers via `config/scrapers.yaml`

**Add new scraper:** Edit yaml file (6 lines), no code changes.

### Databases
- **PostgreSQL (port 54594):** Congressional trades, SEC filings, economic data, fundamentals
- **ChromaDB:** News articles with metadata

### AI Models (Ollama)
- **Current:** phi3:mini, llama3:8b
- **Recommended:** 0xroyce/plutus, martain7r/finance-llama-8b (finance-trained)
- **Advanced:** qwen2.5:32b (needs better hardware)

---

## Strategy

### What WON'T Work
**Stock trading bot** - Market too efficient, can't compete with hedge funds

**Role of stock data:** Context for AI decisions (macro trends, risk sentiment)

### What MIGHT Work (30-40% chance)
**Crypto/meme coin bot** - Inefficient markets, retail-dominated, speed matters

**Edge:** Twitter scraping + AI sentiment + fast execution

---

## Adding Scrapers

Edit `config/scrapers.yaml`:
```yaml
- name: My Scraper
  script: path/to/scraper.py
  category: news|congressional|economic|sec|fundamentals|crypto
  enabled: true
  free_tier: "API limit"
  interval: "frequency"
```

Restart orchestrator. Done.

---

## Database Config

**PostgreSQL:**
- Port: 54594 (not default 5432)
- User/pass: postgres/postgres
- Tables: congressional_trades, sec_filings, economic_indicators, company_profiles

**ChromaDB:**
- Path: `chroma_db_news/`
- Collection: news_articles

---

## File Structure

```
pjx/
├── orchestrator.py          # Manages all scrapers
├── llm_analysis.py          # AI analysis
├── config/
│   └── scrapers.yaml        # Scraper config
├── logs/                    # All logs
├── outputs/                 # AI outputs
├── senate_scraper/
├── house_scraper/
├── news_scrapers/
├── data_api/
├── sec_data/
├── fundamentals_data/
└── crypto_scrapers/         # TO BE BUILT
    ├── twitter_scraper.py
    ├── sentiment_analyzer.py
    └── paper_trading.py
```

---

## Validation Plan

**Phase 1 (3 months):** Test on current hardware
- Build crypto Twitter scraper
- Paper trade all signals
- Track metrics daily
- Iterate on what works

**Phase 2 (After validation):** Buy hardware IF profitable
- RTX 5090 server ($5k) only if making $500+/month
- Deploy 24/7 autonomous system

---

## Reference Docs

Additional guides in `docs/` folder (read later if needed):
- Hardware setup (RTX 4090/5090)
- Cloud GPU testing
- Model installation

---

## Remember

**This project is valuable even if it doesn't make money:**
- Skills learned = $80k-120k/year jobs
- Portfolio project for resume
- Deep understanding of AI + finance + systems

**Focus on:** Crypto bot (where real edge is)
**Avoid:** Expecting stock bot to beat S&P 500 (it won't)
