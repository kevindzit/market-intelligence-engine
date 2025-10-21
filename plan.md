# Trading Bot Project Plan

This document outlines the plan for building a fully autonomous, cost-free, locally-run trading bot.

---

## 1. Core Technology

### AI Agent Framework
- **CrewAI**

### Local AI Models (via Ollama)
- **phi3:mini** — For fast, simple tasks.  
- **llama3:8b** — For medium-difficulty tasks like research.  
- **deepseek-coder:33b** — For the main financial analysis.

### Databases
- **PostgreSQL** — Used for structured data.  
  - **Table:** `congressional_trades`  
- **ChromaDB** — Used for unstructured text data (news).  
  - **Collection:** `news_articles`

---

## 2. Data Ingestion Plan (“The Free Bloomberg”)

This is the status of the data collection scripts that feed the databases.

### Congressional Trades *(Status: COMPLETE)*
- **Senate Scraper:** Python + Selenium script scraping Senate trade disclosures. It works and saves data to PostgreSQL.  
- **House Scraper:** Python script with hybrid PDF/Selenium approach scraping House trade disclosures. It works and saves data to PostgreSQL.

### Real-Time News *(Status: IN PROGRESS)*
- **NewsAPI Reader:** Python script using NewsAPI.org free tier to fetch general business headlines. It works and saves data to ChromaDB.  
- **FMP News Reader:** Attempted to use Financial Modeling Prep API, but free-tier news endpoints are restricted. Currently paused.

### Economic Data *(Status: NEXT UP)*
- **FRED API:** Next step is to create a script to pull key macroeconomic data (interest rates, GDP, etc.) from the Federal Reserve Economic Data API. Data will likely be stored in PostgreSQL.

### Company Fundamentals *(Status: FUTURE STEP)*
- **FMP API:** Plan to use FMP API free tier to get company-specific data like profiles and basic financial statements.

### SEC Filings *(Status: FUTURE STEP)*
- **EDGAR RSS Monitor:** Plan to create a script to monitor SEC EDGAR RSS feeds for new company filings (10-K, 8-K, etc.).

---

## 3. AI Agent Workflow (CrewAI)

This is the planned structure for the AI agent chain that will analyze the data.

### Agent 1: Triage Agent
- **AI Model:** `phi3:mini` (fast and efficient)  
- **Job:** Reads headlines and snippets of new articles from ChromaDB. Decides if a news item is important and worth more analysis.  
- **Output:** “Ignore” or “Investigate” decision for each article.

### Agent 2: Research Agent
- **AI Model:** `llama3:8b`  
- **Job:** Activated when the Triage Agent flags an article as “Investigate.” It will:
  - Scrape the full text of the article from its URL.  
  - Perform a web search for 2–3 related news stories.  
- **Output:** A detailed, well-researched summary of the event.

### Agent 3: Master Reasoning Agent
- **AI Model:** `deepseek-coder:33b` (most powerful)  
- **Job:** Receives the summary from the Research Agent. Combines researched news with other data (congressional trades, FRED data, etc.) to form a complete trading hypothesis.  
- **Output:** A trading recommendation (e.g., “Buy AAPL due to strong earnings report and recent insider purchase”).

---

## 4. Trading Execution

- **Brokerage API:** Alpaca will be used for paper trading to execute the decisions made by the Master Reasoning Agent.

---
