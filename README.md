# Market Intelligence & Signal Engine

A modular, distributed system that collects crypto market and sentiment data from 25+ sources, stores it in PostgreSQL, and uses an LLM ensemble plus rule-based analysis to generate market signals.

## Overview

The system is built around four layers:

- **Data collection** — 25+ scrapers covering social sentiment (Twitter/X), Binance market data, DeFi metrics, and traditional finance (Senate/House trades, SEC EDGAR, FRED, news).
- **Storage** — a PostgreSQL warehouse (38 tables with indexes and signal-detection functions).
- **Intelligence** — a data-intelligence layer that aggregates and synthesizes signals.
- **Decision layer** — an LLM ensemble (Claude, Gemini, DeepSeek) plus rule-based analysis (VADER sentiment, engagement weighting, velocity tracking) that produces entry/exit signals and position sizing.

## Quick Start

```
# activate your virtual environment, then start all scrapers:
python orchestrators/main_orchestrator.py

# or run individual orchestrators:
python orchestrators/twitter_orchestrator.py            # social sentiment
python orchestrators/binance_vpn_orchestrator.py        # crypto market data
python orchestrators/news_fundamentals_orchestrator.py  # traditional finance
```

## Architecture

```
Raw data sources (25+ scrapers)
        |
Distributed scrapers (crypto_scrapers/, news_scrapers/, fundamentals_data/)
        |
PostgreSQL warehouse (38 tables, indexes, signal-detection functions)
        |
Data-intelligence layer (crypto_ai_trader/data_intelligence.py)
        |
LLM ensemble + analysis (crypto_ai_trader/)
        |
Signals (entry/exit, position sizing)
```

## Directory Structure

| Directory | Purpose |
|-----------|---------|
| crypto_scrapers/ | Crypto data collection (social sentiment, Binance, DeFi) |
| news_scrapers/ | News sentiment collection |
| fundamentals_data/ | Traditional-finance data (Senate/House, SEC, FRED, FMP) |
| crypto_ai_trader/ | Intelligence and LLM decision layer |
| nice_funcs/ | Shared utility functions |
| orchestrators/ | Process management and coordination |
| monitors/ | System health and data-quality monitoring |
| config/ | Central scraper configuration |
| data/ | Database schema and queries |

## Data Collection

**Social sentiment** — token- and account-based collectors featuring VADER sentiment tuned with a 150+ term crypto lexicon, engagement weighting and velocity tracking for early-signal detection, and bot / coordinated-pump detection.

**Crypto market data (Binance)** — OHLCV candles, order-book depth, funding rates, liquidations, and open interest, plus fear/greed, stablecoin flows, DEX liquidity, DeFi TVL, options IV, and bridge flows.

**Traditional finance** — Senate/House trades, SEC EDGAR filings, FRED macro data, company fundamentals (FMP), and news / RSS aggregation.

## Database

PostgreSQL with 38 tables, including twitter_sentiment, crypto_ohlcv, order_book_depth, funding_rates, liquidations, open_interest, fear_greed_index, and trading_decisions.

```
# recreate the schema
psql -h localhost -p <port> -U postgres -d postgres -f data/pjx_database_schema.sql
```

## Decision Layer (crypto_ai_trader/)

| Module | Purpose |
|--------|---------|
| ai_trader.py | Main orchestration with dynamic token discovery |
| ai_optimizer.py | Model-ensemble optimization |
| market_analyzer.py | Technical and fundamental analysis |
| data_intelligence.py | Data aggregation and synthesis |
| portfolio_manager.py | Position sizing and risk management |
| trade_learner.py | Learning from trade outcomes |
| macro_intelligence.py | Macroeconomic factor analysis |

The decision layer uses an LLM ensemble (Claude, Gemini, DeepSeek) for analysis, with cheaper models for high-volume processing.

## Tech Stack

- **Languages / DB:** Python, PostgreSQL (plus ChromaDB for article vectors)
- **Key libraries:** vaderSentiment, ccxt, psycopg2, anthropic, twikit
- **Data sources:** NewsAPI, FRED, FMP, CoinGecko, and others

## Configuration

Secrets and credentials are read from a local `.env` and are **not** committed. Scraper behavior — enable/disable, intervals, and rate limits — is defined in config/scrapers.yaml.

## Project Status

A working data-collection fleet (social + market + fundamentals), a PostgreSQL warehouse with signal-detection functions, and an LLM-ensemble decision layer. Signal validation via paper trading is in progress.

## Notes

Personal portfolio project — built to explore distributed data collection, NLP-based sentiment analysis, and LLM-driven decision systems. Live trade execution is intentionally out of scope.
