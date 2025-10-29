# CLAUDE.md

Instructions for Claude Code on the PJX Crypto Trading System.

---

## Current Project Focus

**PRIMARY GOAL: Collect the richest possible crypto market data**

We have built **production-ready Twitter sentiment scrapers** using research-backed strategies. Now duplicating these working systems to cover all parts of the crypto market.

**Current Phase**: Scaling Twitter scrapers across different crypto sectors (meme coins, DeFi, Layer 1s, etc.)

---

## Development Philosophy

### Work Step-by-Step
- **Build ONE thing at a time** - No big complex systems
- **Test each component** before moving to the next
- **Keep iterations small** - A few files at a time, not 10+ files
- **Simple and clean** over clever and complex

### Use APIs, Not Local Models
- **Claude Sonnet 4** for trading decisions (~$10-15/month)
- **Gemini Flash** for data processing (~$1-2/month)
- **DeepSeek** for strategic analysis (~$5-10/month)
- **NO local LLMs** - APIs are cheaper than $5k GPU server

---

## Development Rules

### DO:
- ✅ **Keep files under 800 lines** - if longer, split into new files
- ✅ **Ask before creating multiple files** - build one component at a time
- ✅ **Use real data only** - no fake/synthetic data, fail the script if data unavailable
- ✅ **Keep code simple and readable** - simple over clever, self-explanatory code
- ✅ **Update requirements.txt** after adding any new package

### DON'T:
- ❌ **Move files without asking** - you can create new files but no moving
- ❌ **Create new virtual environments** - use existing setup
- ❌ **Over-engineer error handling** - user wants to see errors, not excessive try/except blocks
- ❌ **Over-comment code** - code should be self-explanatory
- ❌ **Build complex multi-agent systems** - keep iterations small
- ❌ **Use local LLMs** - APIs are cheaper than $5k GPU server
- ❌ **Create 5+ files at once** - build incrementally
- ❌ **Build trading execution** until data + AI validated
- ❌ **Create .md documentation files** - no TEST_RESULTS.md, SUMMARY.md, CHANGES.md, etc. Just explain things in chat

---

## Current System (15 Active Scrapers)

### Traditional Finance Data
1. **News** - NewsAPI + RSS → ChromaDB
2. **Congressional Trades** - Senate + House → PostgreSQL
3. **SEC Filings** - EDGAR RSS → PostgreSQL
4. **Economic Data** - FRED API → PostgreSQL
5. **Company Fundamentals** - FMP + yfinance → PostgreSQL

### Crypto Twitter Intelligence Fleet (Production-Ready)

**Shared Infrastructure:**
- **[nice_funcs/twitter_funcs.py](nice_funcs/twitter_funcs.py)** - 498 lines
  - VADER + 150+ crypto lexicon, Yale engagement coefficient
  - Bot detection & pump pattern detection
  - Twitter client initialization & cookie management
  - All common functions imported by scrapers

**Token-Based Scrapers (5-min cycles):**

6. **Twitter Meme Coins** ([crypto_scrapers/twitter_memecoins.py](crypto_scrapers/twitter_memecoins.py)) - ~500 lines
   - Tokens: PEPE, DOGE, SHIB, BONK, WIF
   - Source ID: `general_search`

7. **Twitter Large Caps** ([crypto_scrapers/twitter_largecaps.py](crypto_scrapers/twitter_largecaps.py)) - ~500 lines
   - Tokens: BTC, ETH, SOL, BNB, XRP, ADA, TRX
   - Source ID: `largecaps`

8. **Twitter DeFi** ([crypto_scrapers/twitter_defi.py](crypto_scrapers/twitter_defi.py)) - ~500 lines
   - Tokens: UNI, AAVE, LDO, MKR, CRV, GMX, SNX
   - Source ID: `defi`

9. **Twitter Layer 1s** ([crypto_scrapers/twitter_layer1s.py](crypto_scrapers/twitter_layer1s.py)) - ~500 lines
   - Tokens: AVAX, DOT, NEAR, ATOM, ICP, ALGO, FTM
   - Source ID: `layer1s`

10. **Twitter Layer 2s** ([crypto_scrapers/twitter_layer2s.py](crypto_scrapers/twitter_layer2s.py)) - ~500 lines
    - Tokens: ARB, OP, MATIC, METIS, IMX
    - Source ID: `layer2s`

11. **Twitter AI/ML** ([crypto_scrapers/twitter_ai.py](crypto_scrapers/twitter_ai.py)) - ~500 lines
    - Tokens: RENDER, FET, GRT, OCEAN, AGIX, TAO, RNDR
    - Source ID: `ai`

**Account-Based Scrapers (10-min cycles):**

12. **Twitter Whales** ([crypto_scrapers/twitter_whales.py](crypto_scrapers/twitter_whales.py)) - 572 lines
    - Accounts: 38 whale accounts (7 slots available, MAX = 45)
    - Categories: Alpha Callers (13), Insiders (2), On-Chain (8), TA (3), High-Profile (6), Platform (6)
    - Source ID: `whale_tracker`

**Common Features (All Twitter Scrapers):**
- VADER + 150+ crypto lexicon terms
- Yale engagement coefficient (0-1 normalized)
- Velocity tracking (sentiment + volume acceleration)
- Reply/quote count metadata
- Bot swarm detection
- MIN_FOLLOWERS = 5000 quality filter
- Auto-refresh cookies (10 retry attempts)

### Infrastructure
- **PostgreSQL** (Docker, port 54594) - All structured data
- **ChromaDB** (chroma_db_news/) - News article vectors
- **Orchestrator** - Manages all scrapers via config/scrapers.yaml
- **.env file** - All API keys (includes Twitter credentials)

---

## Twitter Scraper Strategy (Proven & Production-Ready)

### Core Technology Stack
- **twikit** - Free Twitter scraping (no $100/month API needed)
- **VADER** - Outperforms FinBERT/CryptoBERT for crypto Twitter (research-backed)
- **Custom Lexicon** - 150+ crypto terms (bullish/bearish, meme slang, scam signals)
- **Yale Engagement Coefficient** - Formula: (likes × 1.0 + retweets × 0.31) / followers
  - Optimal range: 0.0001 to 0.001 (200% returns in Yale study)
  - Normalized to 0-1 scale (prevents single-tweet domination)
  - Bot swarm detection when > 0.001

### Advanced Features
- **Velocity Tracking** - Detects sentiment_velocity + volume_acceleration (10-15 min earlier pump signals)
- **Momentum Score** - sentiment_velocity × volume_acceleration (both rising = strong buy)
- **Reply/Quote Metadata** - Genuine engagement metrics (74% accurate pump detection)
- **In-Memory History** - Last 3 cycles per token for per-minute velocity calculations
- **Bot Probability** - Flags likely bot activity
- **Pump Score** - Detects artificial pump schemes
- **Influence Weight** - 0-1 normalized engagement coefficient

### Current Deployment (41 Tokens Tracked)
- **Meme Coins**: PEPE, DOGE, SHIB, BONK, WIF (5 tokens)
- **Large Caps**: BTC, ETH, SOL, BNB, XRP, ADA, TRX (7 tokens)
- **DeFi**: UNI, AAVE, LDO, MKR, CRV, GMX, SNX (7 tokens)
- **Layer 1s**: AVAX, DOT, NEAR, ATOM, ICP, ALGO, FTM (7 tokens)
- **Layer 2s**: ARB, OP, MATIC, METIS, IMX (5 tokens)
- **AI/ML**: RENDER, FET, GRT, OCEAN, AGIX, TAO, RNDR (7 tokens)
- **Whale Tracking**: 38 active accounts × 10-min cycles (7 slots available, MAX = 45)
- **Rate Limits**: 50 calls/15min per endpoint - fleet designed to stay safely under limits

### Research Backing
- **VADER > FinBERT** for crypto Twitter (multiple studies)
- **Yale engagement coefficient** - 200% returns in live study
- **Reply/quote counts** - 74% accurate pump detection
- **Velocity tracking** - 10-15 min earlier signal detection
- **150+ crypto lexicon** - From GitHub PR #81 + 2025 crypto slang research
- **38 whale accounts** - October 2025 (removed 7 suspended/deleted accounts)

---

## Creating New Twitter Scrapers - Quick Start Guide

When creating ANY new Twitter scraper, follow this guide:

### Step 1: Review Reference Files

**ALWAYS review these files first:**
1. **[crypto_scrapers/twitter_memecoins.py](crypto_scrapers/twitter_memecoins.py)** - Reference implementation for token-based scraping (~500 lines)
2. **[crypto_scrapers/twitter_whales.py](crypto_scrapers/twitter_whales.py)** - Reference implementation for account-based scraping (572 lines)
3. **[nice_funcs/twitter_funcs.py](nice_funcs/twitter_funcs.py)** - Shared functions you MUST import (498 lines)
4. **[data/pjx_database_schema.sql](data/pjx_database_schema.sql)** - Database schema (all scrapers use `twitter_sentiment` table)
5. **[ratelimits.md](ratelimits.md)** - Twitter API rate limits (50 calls/15min for search, 50 for user tweets)
6. **[cookies.json](cookies.json)** - Twitter authentication (already configured, don't modify)

### Step 2: Import Shared Functions

**ALWAYS import from nice_funcs/twitter_funcs.py:**

```python
from nice_funcs.twitter_funcs import (
    setup_httpx_patching,              # Must call before importing twikit
    init_vader_with_crypto_lexicon,    # 150+ crypto terms pre-loaded
    init_twitter_client,               # Handles cookies.json automatically
    auto_refresh_cookies,              # Auto-refresh on auth errors
    get_db_connection,                 # PostgreSQL connection
    calculate_bot_probability,         # Bot detection (0-1 score)
    calculate_influence_weight,        # Yale engagement coefficient (0-1 normalized)
    detect_pump_pattern,               # Coordinated pump detection
    analyze_sentiment,                 # VADER sentiment analysis wrapper
    SPAM_KEYWORDS                      # Pre-defined spam filter list
)

# MUST call this before importing twikit!
setup_httpx_patching()

from twikit import TooManyRequests
```

### Step 3: Database Integration

**All Twitter scrapers use the SAME table:** `twitter_sentiment`

**Required columns in INSERT:**
```sql
INSERT INTO twitter_sentiment
(tweet_id, token, tweet_text, sentiment_score, sentiment_label,
 author_username, author_followers, retweet_count, like_count,
 reply_count, quote_count,
 tweet_created_at, scraped_at, weighted_score, alert_level,
 is_whale, volume_spike, bot_probability, pump_score, influence_weight, source)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (tweet_id, token) DO NOTHING  -- Prevents duplicates across ALL scrapers
```

**Key points:**
- `source` field identifies which scraper created the record (e.g., 'general_search', 'whale_tracker', 'defi_tracker')
- `ON CONFLICT DO NOTHING` ensures no duplicates even if multiple scrapers find the same tweet
- All scrapers contribute to unified dataset for AI analysis

### Step 4: Rate Limits to Follow

**From [ratelimits.md](ratelimits.md) - Reset every 15 minutes:**
- `search_tweet` (SearchTimeline): **50 calls/15min**
- `get_user_tweets` (UserTweets): **50 calls/15min**
- `get_user_by_screen_name`: **95 calls/15min**

**Best practices:**
- Keep token lists to 5-7 tokens max (twitter_memecoins.py tracks 5 tokens × 5min cycles = ~30 searches per 15min)
- Whale tracker: 38 accounts × 10min cycles = safe under 50 limit (7 slots available for new whales)
- Add `time.sleep(randint(1, 3))` between API calls
- Use `TooManyRequests` exception handling with `e.rate_limit_reset`

### Step 5: Script Template

**Choose your base template:**

**Option A: Token-Based Scraper** (like twitter_memecoins.py)
```python
TOKENS_TO_TRACK = ["TOKEN1", "TOKEN2", "TOKEN3"]  # 5-10 max
POLLING_INTERVAL = 5 * 60  # 5 minutes
TWEETS_PER_TOKEN = 30

# Search for $TOKEN mentions
tweets = await self.client.search_tweet(f"${token}", product='Latest')
```

**Option B: Account-Based Scraper** (like twitter_whales.py)
```python
ACCOUNTS_TO_TRACK = {
    'username1': 'Description',
    'username2': 'Description'
}
POLLING_INTERVAL = 10 * 60  # 10 minutes
TWEETS_PER_ACCOUNT = 20

# Get user timeline
user = await self.client.get_user_by_screen_name(username)
tweets = await self.client.get_user_tweets(user.id, tweet_type='Tweets', count=20)
```

### Step 6: Required Features

**Every new scraper MUST include:**
1. ✅ Sentiment analysis via `analyze_sentiment(self.vader, text)`
2. ✅ Bot detection via `calculate_bot_probability(user_data)`
3. ✅ Yale engagement coefficient via `calculate_influence_weight(user_data, engagement_data)`
4. ✅ Reply/quote count collection (`reply_count`, `quote_count`)
5. ✅ Spam filtering using `SPAM_KEYWORDS`
6. ✅ Auto-refresh cookies on auth errors via `auto_refresh_cookies(self.client)`
7. ✅ Rate limit handling with `TooManyRequests` exception
8. ✅ Proper `source` field in database (unique identifier for your scraper)

### Step 7: File Structure

**Keep it simple:**
- **One file per scraper** (under 800 lines)
- **Location**: `crypto_scrapers/twitter_[category].py`
- **Examples**: `twitter_defi.py`, `twitter_layer1.py`, `twitter_ai_tokens.py`

**Naming convention:**
- Token-based: `twitter_[category].py` (e.g., `twitter_defi.py` for DeFi tokens)
- Account-based: `twitter_[category]_whales.py` (e.g., `twitter_defi_whales.py` for DeFi influencers)

### Step 8: Configuration

**Add to [config/scrapers.yaml](config/scrapers.yaml):**
```yaml
- name: Twitter DeFi
  script: crypto_scrapers/twitter_defi.py
  category: crypto
  description: Tracks DeFi token sentiment (AAVE, UNI, COMP, etc.)
  enabled: true
  free_tier: "Free (twikit)"
  interval: "5 minutes"
```

### Step 9: Testing

**Before deploying:**
1. ✅ Syntax check: `python -m py_compile crypto_scrapers/twitter_[name].py`
2. ✅ Test run: `python crypto_scrapers/twitter_[name].py` (watch for rate limits)
3. ✅ Database check: Query `twitter_sentiment` table to verify `source` field is unique
4. ✅ Check duplicate prevention: Run multiple scrapers simultaneously, verify no duplicate tweets

### Common Patterns

**Velocity tracking** (optional but recommended):
```python
self.sentiment_history = defaultdict(list)
velocity = self.calculate_velocity_metrics(token, current_sentiment, current_volume)
if velocity and velocity['momentum'] > 0.05:
    print(f"🚀 MOMENTUM ALERT: {token}")
```

**Volume spike detection** (for token scrapers):
```python
volume_spike = self.calculate_volume_spike(token, tweet_count)
if volume_spike >= 2.0:
    print(f"🚨 VOLUME SPIKE: {token} at {volume_spike:.1f}x normal")
```

**Pump detection** (for token scrapers):
```python
pump_score = detect_pump_pattern(tweets, SPAM_KEYWORDS)
if pump_score > 0.7:
    print(f"⚠️ PUMP WARNING: {token}")
```

### Summary Checklist

When creating a new Twitter scraper:
- [ ] Reviewed reference files (twitter_sentiment.py, twitter_whales.py, twitter_funcs.py)
- [ ] Checked database schema (data/pjx_database_schema.sql)
- [ ] Verified rate limits (ratelimits.md)
- [ ] Imported all required functions from nice_funcs/twitter_funcs.py
- [ ] Called setup_httpx_patching() before importing twikit
- [ ] Set unique `source` identifier in database inserts
- [ ] Added `ON CONFLICT (tweet_id, token) DO NOTHING` to prevent duplicates
- [ ] Included bot detection, Yale coefficient, reply/quote counts
- [ ] Handled rate limits with TooManyRequests exception
- [ ] Added auto-refresh cookies on auth errors
- [ ] Kept file under 800 lines
- [ ] Added to config/scrapers.yaml
- [ ] Tested for duplicates and rate limit compliance

---

## Tech Stack

### Databases
- **PostgreSQL** (port 54594) - All structured data
- **ChromaDB** - News article vectors

### Free/Cheap APIs
- **NewsAPI** - 100 calls/day (free)
- **FRED** - Unlimited (free)
- **FMP** - 250 calls/day (free)
- **CoinGecko** - 10k calls/month (free)
- **TwiKit** - Unlimited (free, no API key)
- **Claude Sonnet 4** - $10-15/month (when we build AI layer)

### Key Libraries
- `psycopg2-binary` - PostgreSQL
- `chromadb` - Vector database
- `twikit` - Twitter scraping (free!)
- `vaderSentiment` - Crypto Twitter sentiment (outperforms FinBERT/BERT models)
- `anthropic` - Claude API (for AI decision layer)
- `requests` - HTTP calls
- `python-dotenv` - Environment variables


## Database Schema

### Current Tables
1. `congressional_trades` - Senate + House trade data
2. `economic_indicators` - FRED economic data
3. `sec_filings` - SEC filing data
4. `company_profiles` - Company fundamentals
5. **`twitter_sentiment`** - Crypto Twitter data (with velocity, engagement, bot detection)
   - Columns: tweet_id, token, sentiment_score, weighted_score, alert_level, is_whale, volume_spike, bot_probability, pump_score, influence_weight, reply_count, quote_count, source
   - Indexes: token, scraped_at, sentiment_score, alert_level, weighted_score, is_whale, volume_spike
   - Views: recent_volume_spikes, twitter_trading_signals
   - Materialized View: hourly_twitter_volume

### Full Schema
See [data/pjx_database_schema.sql](data/pjx_database_schema.sql) for complete schema including views and functions.

To recreate database:
```bash
psql -h localhost -p 54594 -U postgres -d postgres -f data/pjx_database_schema.sql
```

---

## Running the System

### Start all scrapers
```bash
python orchestrator.py
```

### View logs
```bash
# Check outputs/ and logs/ folders
```


## Project Status & Goals

### Current Work ✅ COMPLETE
**Twitter Intelligence Fleet - Production Ready**
- Built 6 token-based scrapers covering 41 tokens across all major crypto sectors
- Built 1 whale tracker covering 38 high-signal accounts
- All using proven strategy: VADER + Yale + velocity + MIN_FOLLOWERS = 5000 filter
- All data → single twitter_sentiment table for unified AI analysis
- Total coverage: Meme coins, Large caps, DeFi, Layer 1s, Layer 2s, AI/ML + Whales

### Next Phase
**Testing & AI Integration**
1. Test scraper fleet for 24-48 hours
2. Monitor rate limits, data quality, and cookie refresh stability
3. Build AI decision layer using Claude Sonnet 4
4. Validate trading signals with paper trading
5. Only enable live execution after proven profitability

### Project Goals
1. **Learn by doing** - Build real systems with real data ✅
2. **Portfolio project** - Production-quality code and architecture ✅
3. **Real-world skills** - APIs, databases, scrapers, AI integration (in progress)
4. **Future profitability** - Target $500/month once AI decision layer is validated

**Philosophy**: Keep it simple. Build step-by-step. Test everything. No premature optimization.


## API Models - What to Use Where

### Data Collection Layer (Continuous Monitoring)
**Primary: Gemini 2.5 Flash-Lite**
- Pricing: $0.10/$0.40 per million tokens
- Context: 1M tokens (can process entire order books, news feeds, history)
- Speed: Sub-second latency
- Best for: High-volume data processing, rapid pattern detection, news summarization
- Cost: ~$1/month with caching

**Backup: DeepSeek V3.2-Exp**
- Pricing: $0.028/$0.28 per million tokens
- Context: 128K tokens
- Best for: Cost-sensitive bulk preprocessing
- Warning: Experimental status, use as secondary only

### Trading Decision Layer (Real-Time Signals)
**Primary: Claude Sonnet 4**
- Pricing: $3/$15 per million tokens (effectively $1.80/$15 with 90% caching)
- Context: 200K tokens
- Live results: +28% returns in Alpha Arena
- Special feature: Hybrid reasoning (fast OR deep thinking as needed)
- Best for: Entry/exit signals, position sizing, multi-factor analysis, real-time tactical decisions
- Latency: Fast in standard mode, slower in deep thinking mode

**Alternative for Strategic Analysis: DeepSeek R1**
- Pricing: $0.55/$2.19 per million tokens
- Live results: +35% returns in Alpha Arena
- Best for: Strategic planning, portfolio rebalancing, deep market analysis
- Note: Always does extended reasoning (slower), not ideal for real-time trades

### Deep Analysis Layer (Historical Patterns)
**Use: Gemini 2.5 Pro**
- Pricing: $1.25/$10 per million tokens
- Context: 1M-2M tokens
- Best for: Multi-factor synthesis, historical pattern analysis
- Warning: Lost 39% in live trading when used for real-time decisions (use for research only)