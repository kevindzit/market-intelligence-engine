# Twitter Intelligence System - Guide for AI Trading Bot

**Last Updated:** October 2025
**Purpose:** This document explains the Twitter sentiment data system for the AI trading bot making BUY/SELL/HOLD decisions.

---

## System Overview

**What This System Does:**
- Scrapes crypto Twitter in real-time (5-10 minute cycles)
- Analyzes sentiment using VADER + 150+ crypto-specific terms
- Tracks 38 high-signal whale accounts + filtered general sentiment
- Detects bots, pumps, and manipulative behavior
- Calculates momentum metrics (velocity, acceleration)
- Stores everything in PostgreSQL for AI analysis

**Data Sources:**
1. **General Sentiment** (`source = 'general_search'`): Public tweets mentioning tokens, filtered for MIN_FOLLOWERS ≥ 5000
2. **Whale Tracker** (`source = 'whale_tracker'`): 38 curated high-signal accounts (alpha callers, on-chain analysts, insiders)

---

## Database Schema: `twitter_sentiment` Table

### Core Identification Fields

| Field | Type | Description | AI Usage |
|-------|------|-------------|----------|
| `id` | SERIAL | Unique row ID | Internal only |
| `tweet_id` | VARCHAR(50) | Twitter's unique tweet ID | Deduplication across scrapers |
| `token` | VARCHAR(20) | Crypto token mentioned (BTC, PEPE, DOGE, etc.) | **PRIMARY FILTER** - Which asset to analyze |
| `source` | VARCHAR(50) | 'whale_tracker' or 'general_search' | **SIGNAL WEIGHTING** - Whales = 3x weight |

### Sentiment Analysis Fields

| Field | Type | Range | Description | AI Usage |
|-------|------|-------|-------------|----------|
| `sentiment_score` | NUMERIC(5,4) | -1.0 to +1.0 | VADER sentiment (negative to positive) | **PRIMARY SIGNAL** |
| `sentiment_label` | VARCHAR(20) | positive/negative/neutral | Text label (use score instead) | Human readability only |
| `weighted_score` | NUMERIC(10,4) | Varies | `sentiment_score × influence_weight` | **ADJUSTED SIGNAL** - Accounts for tweet impact |
| `alert_level` | VARCHAR(20) | NULL/LOW/MEDIUM/HIGH/EXTREME | Pre-calculated urgency level | Quick filtering for high-impact tweets |

**Interpretation:**
- `sentiment_score > 0.5` = Strong bullish
- `sentiment_score > 0.2` = Moderate bullish
- `sentiment_score < -0.2` = Moderate bearish
- `sentiment_score < -0.5` = Strong bearish
- `weighted_score > 100` = High influence bullish tweet
- `weighted_score < -100` = High influence bearish tweet

### Author & Engagement Fields

| Field | Type | Description | AI Usage |
|-------|------|-------------|----------|
| `author_username` | VARCHAR(100) | Twitter handle | Track whale consensus (multiple whales agreeing) |
| `author_followers` | INTEGER | Follower count | Influence calculation (already in weighted_score) |
| `following_count` | INTEGER | Accounts followed by author | Bot detection (high following/followers = bot) |
| `verified` | BOOLEAN | Blue checkmark status | Legitimacy signal (+10% trust) |
| `retweet_count` | INTEGER | Times retweeted | Engagement strength |
| `like_count` | INTEGER | Likes received | Engagement strength |
| `reply_count` | INTEGER | Replies received | Discussion indicator (74% accurate for pump detection) |
| `quote_count` | INTEGER | Quote tweets | Strong agreement/disagreement signal |

**Influence Weight Calculation (Yale Engagement Coefficient):**
```
influence_weight = (likes × 1.0 + retweets × 0.31) / (followers + 1)
Normalized to 0-1 range based on optimal thresholds (0.0001 to 0.001)
```

### Quality & Spam Detection Fields

| Field | Type | Range | Description | AI Usage |
|-------|------|-------|-------------|----------|
| `bot_probability` | NUMERIC(4,3) | 0.0 to 1.0 | Likelihood tweet is from bot | **FILTER** - Ignore if > 0.7 |
| `pump_score` | NUMERIC(4,3) | 0.0 to 1.0 (or NULL) | Coordinated pump scheme detection | **WARNING** - Sell signal if > 0.7 |
| `is_whale` | BOOLEAN | true/false | Follower count ≥ 100,000 | Quick whale filter (but use `source` instead) |
| `has_urls` | BOOLEAN | true/false | Tweet contains links | Spam indicator (56% of link-sharers are bots) |
| `hashtag_count` | INTEGER | 0-10+ | Number of hashtags | Spam indicator (>5 = likely spam) |

**Bot Detection Logic:**
- `bot_probability < 0.3` = Likely human (trust the signal)
- `bot_probability 0.3-0.7` = Uncertain (reduce weight by 50%)
- `bot_probability > 0.7` = Likely bot (ignore the tweet)

**Pump Detection Logic:**
- `pump_score > 0.7` = High coordination (SELL or avoid)
- `pump_score 0.5-0.7` = Suspicious activity (reduce confidence)
- `pump_score < 0.5` = Normal activity (or NULL = not detected)

### Momentum Metrics (MOST IMPORTANT FOR TRADING)

| Field | Type | Description | AI Usage |
|-------|------|-------------|----------|
| `sentiment_velocity` | NUMERIC(10,6) | Rate of sentiment change per minute | **#1 PREDICTOR** - Detect accelerating trends |
| `volume_acceleration` | NUMERIC(10,6) | Rate of volume change per minute | **#2 PREDICTOR** - Detect surging interest |
| `momentum_score` | NUMERIC(10,6) | `sentiment_velocity × volume_acceleration` | **COMBINED SIGNAL** - Both rising = strong buy |
| `volume_spike` | NUMERIC(5,2) | Current volume / baseline volume | General sentiment only (whale tracker = NULL) |

**Momentum Interpretation (Research-Backed):**
- `sentiment_velocity > 0.06/min` = Rapidly improving sentiment (10-15 min head start on price)
- `volume_acceleration > 0.2/min` = Surging tweet volume (early FOMO detection)
- `momentum_score > 0.05` = **STRONG BUY** - Both metrics accelerating together
- `momentum_score > 0.02` = **MODERATE BUY** - Positive momentum building
- `momentum_score < -0.05` = **STRONG SELL** - Negative momentum accelerating

**NULL Handling:**
- First cycle always has NULL (no previous data to compare)
- Treat NULL as 0 or skip momentum analysis for that token
- Wait for 2+ cycles before trusting momentum signals

### Timestamp Fields

| Field | Type | Description | AI Usage |
|-------|------|-------------|----------|
| `tweet_created_at` | TIMESTAMP WITH TIME ZONE | When tweet was posted | Signal freshness (older tweets = less weight) |
| `scraped_at` | TIMESTAMP WITH TIME ZONE | When we collected the tweet | Query filter (last 15-60 min) |

**Time Decay:**
- Tweets < 15 min old = Full weight
- Tweets 15-60 min old = 50% weight
- Tweets > 60 min old = Ignore (stale signal)

### Additional Metadata

| Field | Type | Description |
|-------|------|-------------|
| `tweet_text` | TEXT | Full tweet content (for context/debugging) |
| `word_count` | INTEGER | Number of words in tweet |

---

## How to Use This Data for Trading Decisions

### Step 1: Query Recent High-Quality Signals

```sql
SELECT
    token,
    COUNT(DISTINCT author_username) as unique_authors,
    COUNT(*) as total_tweets,
    AVG(sentiment_score) as avg_sentiment,
    AVG(weighted_score) as avg_weighted,
    AVG(momentum_score) as avg_momentum,
    MAX(volume_spike) as max_volume,
    COUNT(*) FILTER (WHERE is_whale = true) as whale_count,
    COUNT(*) FILTER (WHERE bot_probability > 0.7) as bot_count,
    MAX(pump_score) as max_pump_score
FROM twitter_sentiment
WHERE scraped_at > NOW() - INTERVAL '15 minutes'
  AND bot_probability < 0.5  -- Filter out likely bots
GROUP BY token
HAVING COUNT(*) >= 3  -- Need at least 3 tweets for confidence
ORDER BY avg_momentum DESC NULLS LAST;
```

### Step 2: Signal Weighting System

**Priority 1: Whale Consensus (Highest Confidence)**
```sql
-- 3+ whales agreeing = very strong signal
SELECT token,
       COUNT(DISTINCT author_username) as whale_count,
       AVG(sentiment_score) as consensus_sentiment
FROM twitter_sentiment
WHERE source = 'whale_tracker'
  AND scraped_at > NOW() - INTERVAL '30 minutes'
  AND bot_probability < 0.3
GROUP BY token
HAVING COUNT(DISTINCT author_username) >= 3
  AND AVG(sentiment_score) > 0.5;  -- Bullish consensus
```

**Priority 2: Momentum Acceleration (Early Entry)**
```sql
-- Rapidly improving sentiment = 10-15 min head start
SELECT token,
       AVG(sentiment_score) as sentiment,
       AVG(sentiment_velocity) as velocity,
       AVG(volume_acceleration) as acceleration,
       AVG(momentum_score) as momentum
FROM twitter_sentiment
WHERE scraped_at > NOW() - INTERVAL '15 minutes'
  AND momentum_score IS NOT NULL
  AND bot_probability < 0.5
GROUP BY token
HAVING AVG(momentum_score) > 0.05;  -- Strong positive momentum
```

**Priority 3: Volume Spike (FOMO Detection)**
```sql
-- Unusual volume = retail interest surging
SELECT token,
       MAX(volume_spike) as spike_ratio,
       AVG(sentiment_score) as sentiment,
       COUNT(*) as tweet_count
FROM twitter_sentiment
WHERE source = 'general_search'
  AND scraped_at > NOW() - INTERVAL '15 minutes'
  AND volume_spike > 2.0  -- 2x normal volume
  AND bot_probability < 0.5
GROUP BY token;
```

### Step 3: Decision Matrix

**STRONG BUY Signals (High Confidence):**
- ✅ 3+ whales bullish (avg sentiment > 0.5)
- ✅ Momentum score > 0.05 (accelerating)
- ✅ Volume spike > 3.0x baseline
- ✅ Low bot activity (< 20% bots)
- ✅ No pump warning (pump_score < 0.5)

**MODERATE BUY Signals (Medium Confidence):**
- ✅ 1-2 whales bullish OR strong momentum (> 0.02)
- ✅ Volume spike > 2.0x baseline
- ✅ Moderate bot activity (20-40% bots)
- ⚠️ Reduce position size by 50%

**HOLD Signals:**
- Mixed sentiment (neither clearly bullish nor bearish)
- Low volume, no momentum
- Conflicting whale opinions

**SELL Signals:**
- ❌ Pump score > 0.7 (coordinated scheme detected)
- ❌ Negative momentum score < -0.05 (sentiment deteriorating)
- ❌ 3+ whales bearish (avg sentiment < -0.5)
- ❌ High bot activity (> 70% bots)

**AVOID Completely:**
- ❌ Pump score > 0.8 (definitely a scam)
- ❌ Bot probability > 0.7 on all recent tweets
- ❌ Excessive spam indicators (hashtag_count > 8, has_urls + low followers)

### Step 4: Confidence Scoring

```python
# Pseudocode for AI bot confidence calculation
confidence_score = 0

# Whale consensus (0-40 points)
if whale_count >= 3:
    confidence_score += 40
elif whale_count >= 2:
    confidence_score += 25
elif whale_count >= 1:
    confidence_score += 10

# Momentum strength (0-30 points)
if momentum_score > 0.05:
    confidence_score += 30
elif momentum_score > 0.02:
    confidence_score += 15
elif momentum_score > 0:
    confidence_score += 5

# Volume surge (0-20 points)
if volume_spike > 3.0:
    confidence_score += 20
elif volume_spike > 2.0:
    confidence_score += 10

# Quality filters (0-10 points)
if bot_percentage < 20%:
    confidence_score += 10
elif bot_percentage < 40%:
    confidence_score += 5

# Penalties
if pump_score > 0.7:
    confidence_score -= 50  # Major red flag
if bot_percentage > 70%:
    confidence_score -= 30

# Final confidence levels
# 70-100 = HIGH confidence (2% position size)
# 40-69 = MEDIUM confidence (1% position size)
# 0-39 = LOW confidence (skip or 0.5% position)
# < 0 = DO NOT TRADE
```

---

## Research-Backed Best Practices

### 1. Source Weighting (CRITICAL)

**Whale Signals = 3x Weight**
- Whales have 6-24 hour price impact (proven in 2024 research)
- BUT: Many are paid shills (75% of 2024 launches had paid KOL rounds)
- **Use whale consensus** (3+ whales) to avoid single-shill traps

**General Sentiment = 1x Weight**
- Early retail volume (0-6 hours) predicts pumps
- BUT: 56% of link-sharers are bots
- **Use MIN_FOLLOWERS ≥ 5000** filter to reduce noise

**Combined Signal = Best Performance**
- Hybrid approach (whales + filtered retail) outperforms either alone
- Early retail volume + whale amplification = highest win rate

### 2. Momentum is #1 Predictor

**Research Finding (2025 SHAP Analysis):**
- Sentiment velocity and volume acceleration = top predictive features
- Provides 10-15 minute head start on price movements
- **Most important columns:** `sentiment_velocity`, `volume_acceleration`, `momentum_score`

**How to Use:**
- Wait for 2+ cycles before trusting momentum (avoid NULL values)
- Rising momentum + whale consensus = strongest signal
- Falling momentum + negative sentiment = early exit signal

### 3. Time Windows Matter

**Early Entry (0-6 hours):**
- Watch for retail volume spikes (`volume_spike > 2.0`)
- Momentum acceleration (`momentum_score > 0.02`)
- Low bot activity (`bot_probability < 0.3`)

**Confirmation (6-24 hours):**
- Whale tweets amplify the signal
- Multiple whales agreeing = strong confirmation
- Risk: You're later to the party (less profit potential)

**Exit Timing:**
- Pump detected (`pump_score > 0.7`) = Exit immediately
- Momentum reversal (`momentum_score < -0.02`) = Exit within 1 hour
- Whale consensus flips bearish = Exit within 2 hours

### 4. Bot & Spam Detection

**Bot Indicators (Already Calculated):**
- `bot_probability > 0.7` = Ignore completely
- `bot_probability 0.3-0.7` = Reduce weight by 50%
- High `following_count` / low `author_followers` = Bot farm

**Pump Scheme Indicators:**
- `pump_score > 0.7` = Coordinated manipulation (SELL)
- `reply_count` and `quote_count` spikes = 74% accurate pump detection
- Multiple tweets with identical text = Bot swarm (already detected in `pump_score`)

**Spam Indicators:**
- `hashtag_count > 5` = Likely spam
- `has_urls = true` + `author_followers < 10,000` = Likely spam
- `verified = false` + excessive emojis/caps = Likely spam

### 5. Risk Management (NON-NEGOTIABLE)

**Position Sizing Based on Confidence:**
```
HIGH confidence (70-100 score): 2% of capital
MEDIUM confidence (40-69 score): 1% of capital
LOW confidence (0-39 score): 0.5% of capital or skip
NEGATIVE confidence (< 0): DO NOT TRADE
```

**Stop Losses:**
- Set stop loss at -5% for all trades
- Exit immediately if pump detected mid-trade
- Don't average down on losing positions

**Daily Limits:**
- Max 10% of capital at risk simultaneously
- Stop trading if daily loss hits -10%
- Max 5 trades per day (avoid overtrading)

---

## Example Queries for AI Bot

### Query 1: Find Strong Buy Signals

```sql
WITH recent_signals AS (
    SELECT
        token,
        source,
        sentiment_score,
        weighted_score,
        momentum_score,
        bot_probability,
        pump_score,
        is_whale,
        author_username,
        scraped_at
    FROM twitter_sentiment
    WHERE scraped_at > NOW() - INTERVAL '15 minutes'
      AND bot_probability < 0.5
),
token_summary AS (
    SELECT
        token,
        COUNT(*) as total_tweets,
        COUNT(DISTINCT author_username) as unique_authors,
        COUNT(*) FILTER (WHERE source = 'whale_tracker') as whale_tweets,
        COUNT(DISTINCT author_username) FILTER (WHERE source = 'whale_tracker') as unique_whales,
        AVG(sentiment_score) as avg_sentiment,
        AVG(weighted_score) as avg_weighted,
        AVG(momentum_score) as avg_momentum,
        MAX(pump_score) as max_pump_score,
        AVG(bot_probability) as avg_bot_prob
    FROM recent_signals
    GROUP BY token
)
SELECT *
FROM token_summary
WHERE avg_sentiment > 0.5                -- Bullish
  AND unique_whales >= 2                 -- Multiple whales agree
  AND (avg_momentum > 0.02 OR avg_momentum IS NULL)  -- Positive or unknown momentum
  AND (max_pump_score < 0.5 OR max_pump_score IS NULL)  -- No pump detected
  AND avg_bot_prob < 0.4                 -- Low bot activity
ORDER BY
    unique_whales DESC,
    avg_momentum DESC NULLS LAST,
    avg_weighted DESC;
```

### Query 2: Detect Pump Warnings

```sql
SELECT
    token,
    COUNT(*) as tweet_count,
    MAX(pump_score) as pump_score,
    AVG(bot_probability) as avg_bot_prob,
    COUNT(*) FILTER (WHERE bot_probability > 0.7) as bot_count,
    ARRAY_AGG(DISTINCT author_username) as authors
FROM twitter_sentiment
WHERE scraped_at > NOW() - INTERVAL '15 minutes'
  AND (pump_score > 0.5 OR bot_probability > 0.7)
GROUP BY token
HAVING MAX(pump_score) > 0.7
    OR AVG(bot_probability) > 0.6
ORDER BY MAX(pump_score) DESC;
```

### Query 3: Track Whale Consensus Over Time

```sql
SELECT
    token,
    DATE_TRUNC('minute', scraped_at) -
        (EXTRACT(minute FROM scraped_at)::integer % 5) * INTERVAL '1 minute' as time_bucket,
    COUNT(DISTINCT author_username) as whale_count,
    AVG(sentiment_score) as avg_sentiment,
    STRING_AGG(DISTINCT author_username, ', ') as whales
FROM twitter_sentiment
WHERE source = 'whale_tracker'
  AND scraped_at > NOW() - INTERVAL '2 hours'
  AND bot_probability < 0.3
GROUP BY token, time_bucket
HAVING COUNT(DISTINCT author_username) >= 2
ORDER BY time_bucket DESC, whale_count DESC;
```

### Query 4: Momentum Trend Analysis

```sql
SELECT
    token,
    AVG(sentiment_score) as current_sentiment,
    AVG(sentiment_velocity) as velocity,
    AVG(volume_acceleration) as acceleration,
    AVG(momentum_score) as momentum,
    COUNT(*) as sample_size
FROM twitter_sentiment
WHERE scraped_at > NOW() - INTERVAL '15 minutes'
  AND momentum_score IS NOT NULL
  AND bot_probability < 0.5
GROUP BY token
HAVING COUNT(*) >= 5  -- Need adequate sample
ORDER BY AVG(momentum_score) DESC NULLS LAST;
```

---

## Common Pitfalls to Avoid

### ❌ Don't Do This:

1. **Ignore source field** - Whale tweets are 3x more important than general
2. **Trust single whale** - One whale could be paid shill (need 2-3 for consensus)
3. **Ignore bot_probability** - Bot tweets are worthless noise
4. **Chase pumps** - If pump_score > 0.7, you're exit liquidity
5. **Trade on stale data** - Use last 15-30 min only (older = less relevant)
6. **Ignore momentum** - It's the #1 predictor (when not NULL)
7. **Over-leverage** - Meme coins are volatile, use small position sizes
8. **Revenge trading** - One bad trade doesn't mean double down
9. **FOMO on volume alone** - Need sentiment + momentum + quality confirmation
10. **Trust verified accounts blindly** - Even verified accounts can be paid shills

### ✅ Do This Instead:

1. **Weight by source** - whale_tracker = 3x, general_search = 1x
2. **Require whale consensus** - 3+ whales for high confidence
3. **Filter bots aggressively** - bot_probability < 0.5 minimum
4. **Avoid obvious pumps** - pump_score > 0.7 = instant red flag
5. **Use recent data** - Last 15-30 min for entries, last 60 min for trends
6. **Wait for momentum** - 2+ cycles before trusting velocity metrics
7. **Size positions appropriately** - 0.5-2% max per trade
8. **Stick to strategy** - Don't deviate based on emotions
9. **Validate with multiple signals** - Sentiment + momentum + volume + whales
10. **Paper trade first** - Test strategy on historical data before risking real money

---

## System Limitations (Be Aware)

### Data Gaps

1. **First cycle has NULL momentum** - Need 2+ cycles for velocity data
2. **Low sample size with filters** - MIN_FOLLOWERS = 5000 means fewer tweets (0-4 per cycle)
3. **Whale accounts can be suspended** - Currently 38/45 active (7 removed for being suspended/deleted)
4. **Rate limits constrain coverage** - Can't track every token or account simultaneously

### Known Issues

1. **BenjaminCowen returns 'value' errors** - Kept in whale list but may not collect tweets
2. **Timezone mismatches** - Database uses UTC, ensure queries account for this
3. **Duplicate tweets across tokens** - Same tweet can appear multiple times if it mentions multiple tokens (this is correct behavior)
4. **GENERAL token** - Whale tweets without specific token mentions are tagged as GENERAL

### Market Manipulation

1. **75% of tokens have paid KOL rounds** - Whales are often paid shills
2. **Pump schemes are common** - pump_score helps but not foolproof
3. **Bot armies are sophisticated** - bot_probability catches most but not all
4. **Insider information** - Some whales are project insiders (good and bad)
5. **Delayed signals** - Twitter sentiment lags price action sometimes (HFT bots are faster)

---

## Recommended Decision Flow

```
1. Query recent tweets (last 15 min)
   ↓
2. Filter out bots (bot_probability < 0.5)
   ↓
3. Check for pump warnings (pump_score > 0.7)
   → If YES: SELL or AVOID
   → If NO: Continue
   ↓
4. Calculate confidence score
   - Whale consensus (3+ = high, 1-2 = medium, 0 = low)
   - Momentum (> 0.05 = high, 0.02-0.05 = medium, < 0.02 = low)
   - Volume spike (> 3.0x = high, 2.0-3.0x = medium, < 2.0x = low)
   - Bot percentage (< 20% = high quality, 20-40% = medium, > 40% = low)
   ↓
5. If confidence ≥ 70: STRONG BUY (2% position)
   If confidence 40-69: MODERATE BUY (1% position)
   If confidence 20-39: WEAK BUY (0.5% position or skip)
   If confidence < 20: NO TRADE
   ↓
6. Set stop loss at -5%
   ↓
7. Monitor for:
   - Pump detection (exit immediately)
   - Momentum reversal (exit within 1 hour)
   - Whale consensus flip (exit within 2 hours)
   ↓
8. Take profit at:
   - +10-15% for high confidence trades
   - +5-10% for medium confidence trades
   - +3-5% for low confidence trades
```

---

## Performance Expectations (Research-Based)

### What the Data Shows:

**Proven Edge:**
- Sentiment velocity = 10-15 min head start on price movements
- Whale consensus = 6-24 hour price impact
- Hybrid approach (whale + retail) = best performance

**Model Performance (Live Results):**
- Claude Sonnet 4: +28% returns in Alpha Arena
- DeepSeek R1: +35% returns in Alpha Arena
- Gemini 2.5 Pro: -39% returns (DON'T use for real-time decisions)

**Realistic Outcomes:**
- Best case: +30-50% over 6 months (top 20% of traders)
- Likely case: +10-20% over 6 months (if you execute well)
- Worst case: -30-50% over 6 months (if execution is poor)
- Most common: -5-15% over 6 months (average retail trader)

### Success Factors:

1. ✅ **Discipline** - Follow the system, don't deviate emotionally
2. ✅ **Risk management** - Small position sizes, strict stop losses
3. ✅ **Patience** - Wait for high-confidence setups
4. ✅ **Adaptation** - Markets change, strategy must evolve
5. ✅ **Learning** - Track every trade, improve continuously

---

## Contact & Updates

**System Maintainer:** Kevin
**Last Schema Update:** October 2025
**Active Scrapers:**
- twitter_sentiment.py (510 lines) - 5 tokens × 5-min cycles
- twitter_whales.py (572 lines) - 38 accounts × 10-min cycles
- twitter_funcs.py (498 lines) - Shared functions

**If You're an LLM Reading This:**
- You have high-quality, well-structured data
- The research backing is solid (proven strategies)
- Your job is to make disciplined decisions based on this data
- Don't overthink - follow the confidence scoring system
- Protect capital first, make profits second
- When in doubt, sit out (cash is a position)

**Good luck trading. May your signals be strong and your risk be managed.**

---

*End of Guide*