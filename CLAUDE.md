# CLAUDE.md

Instructions for Claude Code on this autonomous trading bot project.

---

## Project Goal

**Make $500/month profit from crypto/meme coin trading using AI + Twitter scraping.**

---

## Strategy (Updated Oct 22, 2025)

### What WON'T Work
**Stock trading bot** - Market too efficient (5% chance to beat S&P 500)
- Hedge funds have billions in infrastructure
- Congressional trades already priced in
- News analyzed by every algo instantly

### What MIGHT Work (30-40% chance)
**Crypto/meme coin bot** - Inefficient markets, retail-dominated
- Twitter sentiment moves prices FAST
- Bots beat human traders on speed
- Small edges compound quickly

### Role of Stock Data
**Stock/congressional/SEC data = CONTEXT only, NOT trading signals**

Use for:
- Macro trends
- Risk-on vs risk-off sentiment
- Broader market context for AI

**Don't trade directly on this data.**

---

## Current Status

### Working ✅
- 8 scrapers running (news, congressional, SEC, economic, fundamentals)
- PostgreSQL: 2,800+ trades, 70+ SEC filings
- ChromaDB: 340+ news articles
- AI analysis: Triage + Research agents

### Not Built Yet ❌
- Crypto Twitter scraper (PRIORITY)
- Paper trading framework
- Performance tracking
- Sentiment analysis

### Hardware
- Using current hardware for testing
- Buy RTX 5090 server ($5k) ONLY after 3 months validation + proven profitability

---

## Tech Stack

**AI:** CrewAI + Ollama (local)
- Models: phi3:mini, llama3:8b (current)
- Recommended: 0xroyce/plutus, martain7r/finance-llama-8b (finance-trained)

**Databases:**
- PostgreSQL (port 54594, postgres/postgres)
- ChromaDB (chroma_db_news/)

**Scrapers:**
- Selenium (congressional trades, Twitter)
- BeautifulSoup (HTML parsing)
- feedparser (RSS)

---

## File Structure

```
pjx/
├── orchestrator.py          # Manages scrapers
├── llm_analysis.py          # AI analysis
├── config/scrapers.yaml     # Scraper config
├── senate_scraper/
├── house_scraper/
├── news_scrapers/
├── data_api/
├── sec_data/
├── fundamentals_data/
└── crypto_scrapers/         # TO BE BUILT
    ├── twitter_scraper.py   # PRIORITY
    ├── sentiment_analyzer.py
    └── paper_trading.py
```

---

## Adding Scrapers

Edit `config/scrapers.yaml` (6 lines):
```yaml
- name: Scraper Name
  script: path/to/scraper.py
  category: news|congressional|economic|sec|fundamentals|crypto
  enabled: true
  free_tier: "API limit"
  interval: "frequency"
```

---

## User Context

**Age:** 23, completing software dev degree
**Budget:** Limited (student)
**Goal:** Build AI systems that make money autonomously
**Interest:** Crypto/meme coins, anywhere with edge

**Strategy:** Validate first (3 months, $0-500 spent), buy hardware later (only if profitable)

---

## Guidelines for Claude

1. **Everything must be FREE** - research API limits first
2. **Keep it SIMPLE** - maintainable, debuggable
3. **Build for AUTONOMY** - no manual intervention
4. **VALIDATE FIRST** - test before suggesting expensive hardware
5. **FOCUS ON EDGE** - crypto/meme coins, not stocks

### When User Asks for Changes
- Research free tier limits
- Keep changes simple
- Update config/scrapers.yaml for new scrapers
- Focus on crypto bot opportunities
- Don't suggest hardware purchases until validated

---

## Validation Plan

**Phase 1 (3 months):** Test on current hardware
- Build crypto Twitter scraper
- Paper trade all signals
- Track metrics (win rate, P&L, Sharpe ratio)
- Iterate on what works

**Phase 2:** Buy hardware ONLY if profitable
- RTX 5090 server ($5k) if making $500+/month
- Deploy 24/7 system

---

## Running Commands

```bash
python orchestrator.py    # Start all scrapers
python llm_analysis.py    # Run AI analysis
python system_test.py     # Test everything
```

---

## Remember

**Value even if not profitable:**
- Skills = $80k-120k/year jobs
- Portfolio project for resume
- Learning in AI/finance/systems

**Always prioritize:**
1. Crypto/meme coin edge (primary focus)
2. Validation before investment
3. Simplicity and robustness
4. Learning and skill development
