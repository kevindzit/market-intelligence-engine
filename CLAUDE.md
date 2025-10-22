# CLAUDE.md

Claude Code instructions for this autonomous trading bot project.

## Project Goal

Build a **100% free, locally-run** trading bot that:
1. Collects financial data from free sources
2. Uses local AI (Ollama) to analyze data
3. Generates trading signals for paper trading
4. Aims to outperform S&P 500 (5-10% alpha target)

## Tech Stack

- **AI**: CrewAI + Ollama (`phi3:mini`, `llama3:8b`, `deepseek-coder:33b`)
- **Databases**: PostgreSQL (port 54594), ChromaDB
- **Data**: Free APIs only (NewsAPI, FRED, FMP, yfinance) + web scraping

## Quick Start

**Prerequisites:**
- PostgreSQL on `localhost:54594` (user/pass: postgres/postgres)
- Ollama running: `ollama serve`
- Models: `ollama pull phi3:mini llama3:8b`

**Run Analysis:**
```bash
python app.py  # Triage + research latest news → outputs/triage_results.txt
```

## Data Scrapers

All scrapers run independently. Data auto-deduplicates via unique constraints.

| Scraper | Command | Destination | Free Tier Limit |
|---------|---------|-------------|-----------------|
| **NewsAPI** | `python news_scrapers/newsapi_reader.py` | ChromaDB | 100 calls/day |
| **RSS Aggregator** | `python news_scrapers/rss_aggregator.py` | ChromaDB | Unlimited (9 sources) |
| **Senate Trades** | `python senate_scraper/senate_scraper.py` | PostgreSQL | Unlimited |
| **House Trades** | `python house_scraper/house_scraper.py` | PostgreSQL | Unlimited |
| **FRED Economic** | `python data_api/fred_data_reader.py` | PostgreSQL | Unlimited |
| **SEC Filings** | `python sec_data/edgar_rss_reader.py` | PostgreSQL | Unlimited |
| **FMP Fundamentals** | `python fundamentals_data/fmp_fundamentals_reader.py` | PostgreSQL | 250 calls/day |
| **yfinance Fundamentals** | `python fundamentals_data/yfinance_fundamentals_reader.py` | PostgreSQL | Unlimited |

## Database Schema

**PostgreSQL (port 54594):**
- `congressional_trades` - Senate/House disclosures | Unique: (filer_name, transaction_date, ticker, transaction_type, amount_range)
- `economic_indicators` - FRED macroeconomic data | Unique: (indicator_code, date)
- `sec_filings` - EDGAR filings (8-K, 10-K, 10-Q, Form 4) | Unique: (filing_url)
- `company_profiles` - Company fundamentals (FMP + yfinance) | Unique: (symbol)

**ChromaDB (`chroma_db_news/`):**
- `news_articles` - News headlines + snippets | Unique: URL as document ID

## CrewAI Agents (app.py)

**Current Implementation:**
1. **Triage Agent** (`phi3:mini`) - Classifies 25 latest news as "Investigate" or "Ignore" → `outputs/triage_results.txt`
2. **Research Agent** (`llama3:8b`) - Summarizes first 5 investigated items (no web tools yet)

**Planned:**
- Research Agent with web scraping (DuckDuckGo search + ScrapeWebsiteTool available but not enabled)
- Master Reasoning Agent (`deepseek-coder:33b`) - synthesize all data sources
- Alpaca API integration for paper trading

## Configuration

- **Database**: Port `54594` (not default 5432) | Credentials: postgres/postgres
- **API Keys**: Hardcoded in scraper files (NewsAPI, FRED, FMP)
- **CrewAI Memory**: DISABLED (line 182 in app.py) - prevents OpenAI embedding errors
- **Selenium**: Can run headless (uncomment `--headless=new` in congressional scrapers)

## Development Guidelines

**CRITICAL:**
- Every API must be free tier - research limits before implementation
- Keep architecture simple and maintainable for long-term server deployment
- Avoid data bloat - use deduplication and cleanup strategies
- Build for autonomous operation (no manual intervention needed)
- Keep it simple but efficient and robust
- always do research on stuff you dont know and think you should know if it means making stuff better