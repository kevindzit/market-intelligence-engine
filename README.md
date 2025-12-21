# PJX Crypto Trading System

A production-ready crypto market intelligence and AI-driven trading platform that collects data from 27+ sources, analyzes with AI models, and generates trading signals.

## Overview

PJX is a modular, distributed crypto trading system built around:
- **Data Collection**: 27+ scrapers covering Twitter sentiment, Binance market data, DeFi metrics, and traditional finance
- **AI Decision Layer**: Claude Sonnet 4 + ensemble voting for trading signals
- **Research-Backed Analysis**: VADER sentiment, Yale engagement coefficient, velocity tracking

## Quick Start

```bash
# Activate virtual environment
C:\venvs\pjxvenv\Scripts\activate

# Start all scrapers via main orchestrator
python orchestrators/main_orchestrator.py

# Or run individual orchestrators:
python orchestrators/twitter_orchestrator.py      # Twitter sentiment fleet
python orchestrators/binance_vpn_orchestrator.py  # Crypto market data
python orchestrators/news_fundamentals_orchestrator.py  # TradFi data
```

## System Architecture

```
Raw Data Sources (27 scraper types)
    ↓
Distributed Scrapers (crypto_scrapers/, news_scrapers/, fundamentals_data/)
    ↓
PostgreSQL Database (38 tables with indexes & signal detection functions)
    ↓
Data Intelligence Layer (crypto_ai_trader/data_intelligence.py)
    ↓
AI Analysis Layer (Claude Sonnet 4 + Gemini + DeepSeek ensemble)
    ↓
Trading Decisions (Entry/exit signals, position sizing)
```

## Directory Structure

| Directory | Files | Purpose |
|-----------|-------|---------|
| `crypto_scrapers/` | 21 | Crypto data collection (Twitter, Binance, DeFi) |
| `nice_funcs/` | 8 | Shared utility functions |
| `crypto_ai_trader/` | 14 | AI trading logic & decision layer |
| `orchestrators/` | 4 | Process management & coordination |
| `monitors/` | 5 | System health & data quality |
| `fundamentals_data/` | 6 | Traditional finance data |
| `news_scrapers/` | 3 | News sentiment collection |
| `config/` | 1 | Central scraper configuration |
| `data/` | 6 | Database schema & queries |

## Data Collection

### Twitter Sentiment Fleet (Production-Ready)

**Token-Based Scrapers** (5-minute cycles, 37 tokens):
| Scraper | Tokens |
|---------|--------|
| `twitter_memecoins.py` | PEPE, DOGE, SHIB, BONK, WIF |
| `twitter_largecaps.py` | BTC, ETH, SOL, BNB, XRP, ADA, TRX |
| `twitter_defi.py` | UNI, AAVE, LDO, MKR, CRV, GMX, SNX |
| `twitter_layer1s.py` | AVAX, DOT, NEAR, ATOM, ICP, ALGO, FTM |
| `twitter_layer2s.py` | ARB, OP, MATIC, METIS, IMX |
| `twitter_ai.py` | RENDER, FET, GRT, OCEAN, AGIX, TAO |

**Account-Based Scraper** (10-minute cycles):
- `twitter_whales.py` - 38 whale accounts (Alpha Callers, Insiders, On-Chain analysts, TA experts)

**Features:**
- VADER sentiment + 150+ crypto lexicon terms
- Yale engagement coefficient (normalized 0-1)
- Velocity tracking (10-15 min pump signal lead)
- Bot detection & pump pattern detection
- 4-account pool with automatic cookie refresh

### Crypto Market Scrapers

| Scraper | Data | Interval |
|---------|------|----------|
| `binance_ohlcv.py` | 5-min price candles (42 tokens) | 5 min |
| `binance_orderbook.py` | Order book depth | 30 sec |
| `binance_funding.py` | Funding rates | 5 min |
| `binance_liquidations.py` | Liquidation events | Real-time |
| `binance_oi.py` | Open interest | 5 min |
| `fear_greed_scraper.py` | Market psychology (0-100) | 1 hour |
| `stablecoin_flow_scraper.py` | USDT/USDC/DAI velocity | 1 hour |
| `exchange_flows.py` | Whale movements | 1 hour |
| `dex_liquidity_monitor.py` | DEX liquidity & volume | 15 min |
| `defi_tvl_monitor.py` | DeFi protocol TVL | 1 hour |
| `options_volatility_monitor.py` | BTC/ETH options IV | 15 min |
| `bridge_flows_monitor.py` | L1/L2 capital rotation | 1 hour |

### Traditional Finance Scrapers

| Scraper | Source | Interval |
|---------|--------|----------|
| `senate_scraper.py` | US Senate trades | 6 hours |
| `house_scraper.py` | US House trades | 6 hours |
| `edgar_rss_reader.py` | SEC EDGAR filings | 6 hours |
| `fred_data_reader.py` | Federal Reserve data | 6 hours |
| `fmp_fundamentals_reader.py` | Company fundamentals | 6 hours |
| `newsapi_reader.py` | News headlines | 15 min |
| `rss_aggregator.py` | RSS feeds (9 sources) | 15 min |

## Database

**PostgreSQL** (Docker, port 54594) with 38 tables:

Key tables:
- `twitter_sentiment` - Core sentiment data with bot/pump detection
- `crypto_ohlcv` - 5-minute price candles
- `order_book_depth` - Order book snapshots
- `funding_rates` - Perpetual futures funding
- `liquidations` - Liquidation events
- `open_interest` - Total leverage
- `fear_greed_index` - Market psychology
- `trading_decisions` - AI decision logs

```bash
# Recreate database schema
psql -h localhost -p 54594 -U postgres -d postgres -f data/pjx_database_schema.sql
```

## AI Decision Layer

Located in `crypto_ai_trader/`:

| Module | Purpose |
|--------|---------|
| `ai_trader.py` | Main orchestration with dynamic token discovery |
| `ai_optimizer.py` | Model ensemble optimization |
| `market_analyzer.py` | Technical & fundamental analysis |
| `data_intelligence.py` | Data aggregation & synthesis |
| `portfolio_manager.py` | Position sizing & risk management |
| `trade_learner.py` | ML from trade outcomes |
| `macro_intelligence.py` | Macroeconomic factor analysis |

**AI Models Used:**
- **Claude Sonnet 4** (Primary) - Trading decisions, +28% Alpha Arena returns
- **Gemini 2.5 Flash-Lite** - High-volume data processing ($0.10/M tokens)
- **DeepSeek R1** - Strategic analysis (+35% Alpha Arena returns)

## Shared Utilities

`nice_funcs/twitter_funcs.py` provides:
- `init_vader_with_crypto_lexicon()` - 150+ crypto terms
- `calculate_influence_weight()` - Yale engagement coefficient
- `calculate_bot_probability()` - Bot detection
- `detect_pump_pattern()` - Coordinated pump detection
- `auto_refresh_cookies()` - Auth error handling
- `get_db_connection()` - PostgreSQL pooling

## Configuration

**Environment Variables** (`.env`):
- Database credentials
- API keys (NewsAPI, FRED, FMP, Anthropic, etc.)
- Twitter credentials

**Scraper Config** (`config/scrapers.yaml`):
- 28 scraper definitions
- Enable/disable flags
- Intervals and rate limits

## Monitoring

```bash
# Twitter system dashboard
python monitors/monitor_twitter_system.py

# Health monitoring
python monitors/health_monitor.py

# Refresh Twitter cookies
python monitors/refresh_cookies.py
```

## Tech Stack

**Databases:**
- PostgreSQL (port 54594) - Structured data
- ChromaDB - News article vectors

**Key Libraries:**
- `twikit` - Free Twitter scraping
- `vaderSentiment` - Crypto sentiment analysis
- `ccxt` - Multi-exchange integration
- `anthropic` - Claude API
- `psycopg2-binary` - PostgreSQL driver

**Free/Cheap APIs:**
- NewsAPI (100 calls/day)
- FRED (unlimited)
- FMP (250 calls/day)
- CoinGecko (10k calls/month)
- TwiKit (unlimited, free)

## Development Philosophy

- **Build ONE thing at a time** - No big complex systems
- **Keep files under 3000 lines** - Split if longer
- **Use real data only** - No synthetic data
- **Simple and clean** over clever and complex
- **Test each component** before moving to the next

## Project Status

**Completed:**
- Twitter sentiment scraper fleet (37 tokens + 38 whale accounts)
- Binance market data collection
- DeFi & options monitoring
- AI decision layer with ensemble voting
- Database with 38 tables & signal detection

**In Progress:**
- Testing scraper fleet for 24-48 hours
- Validating trading signals with paper trading

**Future:**
- Live execution on exchange APIs
- Profitability optimization ($500/month target)

## License

Private project - not for redistribution.
