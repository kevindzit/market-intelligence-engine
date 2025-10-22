# Project Roadmap

**Goal:** 100% free, autonomous trading bot that outperforms S&P 500

---

## ✅ Phase 1: Data Collection (COMPLETE)

**Status:** All 7 scrapers operational and saving to databases.

| Data Source | Status | Free Tier | Destination |
|-------------|--------|-----------|-------------|
| Senate Trades | ✅ Live | Unlimited | PostgreSQL |
| House Trades | ✅ Live | Unlimited | PostgreSQL |
| NewsAPI | ✅ Live | 100/day | ChromaDB |
| FRED Economic | ✅ Live | Unlimited | PostgreSQL |
| SEC EDGAR | ✅ Live | Unlimited | PostgreSQL |
| FMP Fundamentals | ✅ Live | 250/day | PostgreSQL |
| yfinance Fundamentals | ✅ Live | Unlimited | PostgreSQL |

---

## 🚧 Phase 2: Expand News Sources (IN PROGRESS)

**Goal:** Increase news coverage beyond 96 articles/day from NewsAPI.

**New Sources to Add:**
- [ ] **Alpha Vantage** - 500 calls/day + AI sentiment scores (PRIORITY)
- [ ] **RSS Aggregator** - Unlimited (Benzinga, MarketWatch, Nasdaq, CNBC)
- [ ] **Finnhub** - Generous free tier for market news
- [ ] **Deduplication System** - Remove redundant articles across sources

**Expected Result:** 500+ unique articles/day with sentiment analysis.

---

## 📋 Phase 3: Upgrade AI Agents (PLANNED)

**Current (app.py):**
1. Triage Agent (`phi3:mini`) - Classify news → `outputs/triage_results.txt`
2. Research Agent (`llama3:8b`) - Summarize top 5 items (no web tools)

**Upgrades Needed:**
- [ ] Enable web tools for Research Agent (DuckDuckGo + web scraper)
- [ ] Add Master Reasoning Agent (`deepseek-coder:33b`)
  - Input: All data sources (news, congressional trades, FRED, SEC, fundamentals)
  - Output: Trading signals with confidence scores
- [ ] Build signal validation system (backtest on historical data)

---

## 🎯 Phase 4: Paper Trading (FUTURE)

- [ ] Integrate Alpaca API (free paper trading account)
- [ ] Implement position sizing and risk management
- [ ] Build performance tracking dashboard
- [ ] Run live for 3-6 months to validate edge

**Success Metrics:**
- Win rate > 55%
- Sharpe ratio > 1.0
- Max drawdown < 15%
- Annual alpha > 5% vs S&P 500

---

## 🔧 Phase 5: Production Deployment (FUTURE)

- [ ] Set up dedicated server for 24/7 operation
- [ ] Implement data retention policies (avoid bloat)
- [ ] Add monitoring and alerting
- [ ] Create master orchestration script to manage all scrapers
- [ ] Automated error recovery and logging

---
