-- ============================================================
-- PJX DATABASE QUERIES
-- Quick reference for viewing all collected data
-- ============================================================

-- ============================================================
-- ALL TABLES OVERVIEW
-- ============================================================

-- ------------------------------------------------------------
-- CRYPTO MARKET DATA
-- ------------------------------------------------------------

-- Twitter Sentiment (37 tokens + 38 whale accounts)
SELECT * FROM twitter_sentiment ORDER BY scraped_at DESC LIMIT 50;
SELECT COUNT(*) as total_tweets FROM twitter_sentiment;

-- Price Data (OHLCV - 5-minute candles)
SELECT * FROM crypto_ohlcv ORDER BY timestamp DESC LIMIT 50;
SELECT COUNT(*) as total_candles FROM crypto_ohlcv;
SELECT token, COUNT(*) as candles FROM crypto_ohlcv GROUP BY token ORDER BY token;

-- Order Book Depth (bid/ask spreads)
SELECT * FROM order_book_depth ORDER BY timestamp DESC LIMIT 50;
SELECT COUNT(*) as total_snapshots FROM order_book_depth;
SELECT token, COUNT(*) as snapshots FROM order_book_depth GROUP BY token ORDER BY token;

-- Funding Rates (perpetual futures)
SELECT * FROM funding_rates ORDER BY scraped_at DESC LIMIT 50;
SELECT COUNT(*) as total_rates FROM funding_rates;
SELECT token, AVG(funding_rate) as avg_rate FROM funding_rates GROUP BY token ORDER BY token;

-- Fear & Greed Index (market psychology)
SELECT * FROM fear_greed_index ORDER BY timestamp DESC LIMIT 50;
SELECT COUNT(*) as total_readings FROM fear_greed_index;

-- Liquidations (flash crash signals)
SELECT * FROM liquidations ORDER BY timestamp DESC LIMIT 50;
SELECT COUNT(*) as total_liquidations FROM liquidations;
SELECT token, SUM(liquidation_value) as total_liq FROM liquidations GROUP BY token ORDER BY total_liq DESC;

-- Open Interest (futures leverage)
SELECT * FROM open_interest ORDER BY timestamp DESC LIMIT 50;
SELECT COUNT(*) as total_oi_records FROM open_interest;
SELECT token, AVG(open_interest_usd) as avg_oi FROM open_interest GROUP BY token ORDER BY avg_oi DESC;

-- Exchange Flows (whale movements)
SELECT * FROM exchange_flows ORDER BY timestamp DESC LIMIT 50;
SELECT COUNT(*) as total_flows FROM exchange_flows;
SELECT token, flow_type, SUM(usd_value) as total_value FROM exchange_flows GROUP BY token, flow_type ORDER BY token;


-- ------------------------------------------------------------
-- TRADITIONAL FINANCE DATA
-- ------------------------------------------------------------

-- News Articles (NewsAPI + RSS feeds)
SELECT * FROM news_articles ORDER BY published_at DESC LIMIT 50;
SELECT COUNT(*) as total_articles FROM news_articles;
SELECT source, COUNT(*) as articles FROM news_articles GROUP BY source ORDER BY articles DESC;

-- Congressional Trades (Senate + House)
SELECT * FROM congressional_trades ORDER BY transaction_date DESC LIMIT 50;
SELECT COUNT(*) as total_trades FROM congressional_trades;
SELECT politician_name, COUNT(*) as trades FROM congressional_trades GROUP BY politician_name ORDER BY trades DESC;

-- Economic Indicators (FRED API)
SELECT * FROM economic_indicators ORDER BY date DESC LIMIT 50;
SELECT COUNT(*) as total_indicators FROM economic_indicators;
SELECT indicator_name, COUNT(*) as readings FROM economic_indicators GROUP BY indicator_name ORDER BY indicator_name;

-- SEC Filings (EDGAR RSS)
SELECT * FROM sec_filings ORDER BY filing_date DESC LIMIT 50;
SELECT COUNT(*) as total_filings FROM sec_filings;
SELECT filing_type, COUNT(*) as filings FROM sec_filings GROUP BY filing_type ORDER BY filings DESC;

-- Company Fundamentals (FMP + yfinance)
SELECT * FROM company_profiles ORDER BY last_updated DESC LIMIT 50;
SELECT COUNT(*) as total_companies FROM company_profiles;


-- ------------------------------------------------------------
-- AI TRADING SYSTEM (Future Use)
-- ------------------------------------------------------------

-- Trading Decisions (AI model outputs)
SELECT * FROM trading_decisions ORDER BY decision_time DESC LIMIT 50;
SELECT COUNT(*) as total_decisions FROM trading_decisions;

-- Ensemble Votes (multi-model voting)
SELECT * FROM ensemble_votes ORDER BY vote_time DESC LIMIT 50;
SELECT COUNT(*) as total_votes FROM ensemble_votes;

-- Portfolio State (positions & P&L)
SELECT * FROM portfolio_state ORDER BY snapshot_time DESC LIMIT 50;
SELECT COUNT(*) as total_snapshots FROM portfolio_state;

-- Paper Trades (execution log)
SELECT * FROM paper_trades ORDER BY execution_time DESC LIMIT 50;
SELECT COUNT(*) as total_trades FROM paper_trades;
SELECT action, COUNT(*) as trades FROM paper_trades GROUP BY action;

-- Circuit Breaker Events (risk management)
SELECT * FROM circuit_breaker_events ORDER BY event_time DESC LIMIT 50;
SELECT COUNT(*) as total_events FROM circuit_breaker_events;


-- ============================================================
-- DETAILED TWITTER SENTIMENT QUERIES
-- ============================================================

-- ------------------------------------------------------------
-- BASIC VIEWING
-- ------------------------------------------------------------

-- View all tweets (most recent first)
SELECT * FROM twitter_sentiment ORDER BY scraped_at DESC;

-- View last 50 tweets
SELECT * FROM twitter_sentiment ORDER BY scraped_at DESC LIMIT 50;

-- View specific columns only (cleaner output)
SELECT token, tweet_text, sentiment_score, author_username, author_followers, scraped_at
FROM twitter_sentiment
ORDER BY scraped_at DESC LIMIT 50;

-- Count total tweets collected
SELECT COUNT(*) FROM twitter_sentiment;


-- ------------------------------------------------------------
-- FILTER BY TOKEN
-- ------------------------------------------------------------

-- All tweets for a specific token
SELECT * FROM twitter_sentiment WHERE token = 'PEPE' ORDER BY scraped_at DESC;

-- Recent tweets for DOGE
SELECT * FROM twitter_sentiment WHERE token = 'DOGE' ORDER BY scraped_at DESC LIMIT 20;

-- Tweet count per token
SELECT token, COUNT(*) as tweet_count
FROM twitter_sentiment
GROUP BY token
ORDER BY tweet_count DESC;


-- ------------------------------------------------------------
-- FILTER BY SOURCE
-- ------------------------------------------------------------

-- Only whale tracker tweets
SELECT * FROM twitter_sentiment WHERE source = 'whale_tracker' ORDER BY scraped_at DESC;

-- Only general sentiment tweets
SELECT * FROM twitter_sentiment WHERE source = 'general_search' ORDER BY scraped_at DESC;

-- Compare sources
SELECT source, COUNT(*) as tweets, AVG(sentiment_score) as avg_sentiment
FROM twitter_sentiment
GROUP BY source;


-- ------------------------------------------------------------
-- HIGH-SIGNAL TWEETS
-- ------------------------------------------------------------

-- Whale signals only
SELECT token, tweet_text, author_username, sentiment_score, weighted_score, scraped_at
FROM twitter_sentiment
WHERE is_whale = true
ORDER BY weighted_score DESC LIMIT 50;

-- High alert level tweets
SELECT token, tweet_text, author_username, alert_level, weighted_score, scraped_at
FROM twitter_sentiment
WHERE alert_level IN ('EXTREME', 'HIGH', 'WHALE_SIGNAL')
ORDER BY scraped_at DESC;

-- Volume spike alerts (2x+ baseline)
SELECT token, COUNT(*) as tweets, AVG(volume_spike) as avg_spike, MAX(volume_spike) as max_spike
FROM twitter_sentiment
WHERE volume_spike >= 2.0
GROUP BY token
ORDER BY max_spike DESC;


-- ------------------------------------------------------------
-- SENTIMENT ANALYSIS
-- ------------------------------------------------------------

-- Average sentiment per token
SELECT token,
       COUNT(*) as tweets,
       AVG(sentiment_score) as avg_sentiment,
       AVG(CASE WHEN bot_probability < 0.5 THEN sentiment_score END) as human_sentiment
FROM twitter_sentiment
GROUP BY token
ORDER BY avg_sentiment DESC;

-- Bullish tweets (positive sentiment > 0.5)
SELECT token, tweet_text, sentiment_score, author_username, author_followers
FROM twitter_sentiment
WHERE sentiment_score > 0.5
ORDER BY sentiment_score DESC LIMIT 50;

-- Bearish tweets (negative sentiment < -0.5)
SELECT token, tweet_text, sentiment_score, author_username, author_followers
FROM twitter_sentiment
WHERE sentiment_score < -0.5
ORDER BY sentiment_score ASC LIMIT 50;

-- Sentiment trend by hour (last 24 hours)
SELECT DATE_TRUNC('hour', scraped_at) as hour,
       token,
       COUNT(*) as tweets,
       AVG(sentiment_score) as avg_sentiment
FROM twitter_sentiment
WHERE scraped_at > NOW() - INTERVAL '24 hours'
GROUP BY hour, token
ORDER BY hour DESC;


-- ------------------------------------------------------------
-- TIME-BASED QUERIES
-- ------------------------------------------------------------

-- Last 5 minutes of tweets
SELECT * FROM twitter_sentiment WHERE scraped_at > NOW() - INTERVAL '5 minutes' ORDER BY scraped_at DESC;

-- Last 1 hour
SELECT * FROM twitter_sentiment WHERE scraped_at > NOW() - INTERVAL '1 hour' ORDER BY scraped_at DESC;

-- Last 24 hours
SELECT * FROM twitter_sentiment WHERE scraped_at > NOW() - INTERVAL '24 hours' ORDER BY scraped_at DESC;

-- Today's tweets
SELECT * FROM twitter_sentiment WHERE scraped_at::date = CURRENT_DATE ORDER BY scraped_at DESC;

-- Activity by time window
SELECT
    COUNT(*) FILTER (WHERE scraped_at > NOW() - INTERVAL '5 minutes') as last_5min,
    COUNT(*) FILTER (WHERE scraped_at > NOW() - INTERVAL '1 hour') as last_hour,
    COUNT(*) FILTER (WHERE scraped_at > NOW() - INTERVAL '24 hours') as last_24hr,
    COUNT(*) as total
FROM twitter_sentiment;


-- ------------------------------------------------------------
-- WHALE ACCOUNT TRACKING
-- ------------------------------------------------------------

-- Tweets from specific whale
SELECT * FROM twitter_sentiment WHERE author_username = 'blknoiz06' ORDER BY scraped_at DESC;

-- Most active whales
SELECT author_username, COUNT(*) as tweets
FROM twitter_sentiment
WHERE source = 'whale_tracker'
GROUP BY author_username
ORDER BY tweets DESC;

-- Whale tweets with high engagement
SELECT author_username, token, tweet_text, retweet_count, like_count, sentiment_score, scraped_at
FROM twitter_sentiment
WHERE is_whale = true
ORDER BY (retweet_count + like_count) DESC LIMIT 50;


-- ------------------------------------------------------------
-- BOT FILTERING
-- ------------------------------------------------------------

-- Only human tweets (bot probability < 50%)
SELECT * FROM twitter_sentiment WHERE bot_probability < 0.5 ORDER BY scraped_at DESC;

-- Likely bots (bot probability > 70%)
SELECT author_username, bot_probability, COUNT(*) as tweets
FROM twitter_sentiment
WHERE bot_probability > 0.7
GROUP BY author_username, bot_probability
ORDER BY tweets DESC;

-- Bot rate per token
SELECT token,
       COUNT(*) as total_tweets,
       AVG(bot_probability) as avg_bot_prob,
       COUNT(*) FILTER (WHERE bot_probability < 0.5) as human_tweets
FROM twitter_sentiment
GROUP BY token
ORDER BY avg_bot_prob ASC;


-- ------------------------------------------------------------
-- INFLUENCER TRACKING
-- ------------------------------------------------------------

-- Tweets from accounts with 100k+ followers
SELECT token, tweet_text, author_username, author_followers, sentiment_score, weighted_score, scraped_at
FROM twitter_sentiment
WHERE author_followers >= 100000
ORDER BY author_followers DESC;

-- Top influencers by follower count
SELECT author_username,
       MAX(author_followers) as followers,
       COUNT(*) as tweets,
       AVG(sentiment_score) as avg_sentiment
FROM twitter_sentiment
GROUP BY author_username
HAVING MAX(author_followers) > 10000
ORDER BY followers DESC LIMIT 50;


-- ------------------------------------------------------------
-- TRADING SIGNALS
-- ------------------------------------------------------------

-- Strong buy signals (high volume + positive sentiment)
SELECT token,
       COUNT(*) as tweets,
       AVG(volume_spike) as avg_spike,
       AVG(sentiment_score) as avg_sentiment,
       MAX(scraped_at) as last_update
FROM twitter_sentiment
WHERE volume_spike >= 2.0
  AND sentiment_score > 0.3
  AND scraped_at > NOW() - INTERVAL '1 hour'
GROUP BY token
ORDER BY avg_spike DESC;

-- Pump detection (high volume + many bot tweets)
SELECT token,
       COUNT(*) as tweets,
       AVG(bot_probability) as avg_bot_prob,
       AVG(pump_score) as avg_pump_score,
       AVG(volume_spike) as avg_spike
FROM twitter_sentiment
WHERE pump_score > 0.5 OR (bot_probability > 0.7 AND volume_spike > 2.0)
GROUP BY token
ORDER BY avg_pump_score DESC;


-- ------------------------------------------------------------
-- STATISTICS & SUMMARIES
-- ------------------------------------------------------------

-- Overall summary
SELECT
    COUNT(*) as total_tweets,
    COUNT(DISTINCT token) as tokens_tracked,
    COUNT(DISTINCT author_username) as unique_users,
    COUNT(*) FILTER (WHERE is_whale = true) as whale_tweets,
    COUNT(*) FILTER (WHERE alert_level IS NOT NULL) as high_alerts,
    AVG(sentiment_score) as avg_sentiment,
    MIN(scraped_at) as first_tweet,
    MAX(scraped_at) as last_tweet
FROM twitter_sentiment;

-- Daily summary
SELECT scraped_at::date as date,
       COUNT(*) as tweets,
       COUNT(DISTINCT token) as tokens,
       AVG(sentiment_score) as avg_sentiment,
       COUNT(*) FILTER (WHERE volume_spike >= 2.0) as volume_alerts
FROM twitter_sentiment
GROUP BY date
ORDER BY date DESC;


-- ------------------------------------------------------------
-- SEARCH & FILTER
-- ------------------------------------------------------------

-- Search tweet text for keyword
SELECT * FROM twitter_sentiment WHERE tweet_text ILIKE '%bitcoin%' ORDER BY scraped_at DESC;

-- Find tweets from specific user
SELECT * FROM twitter_sentiment WHERE author_username = 'elonmusk' ORDER BY scraped_at DESC;

-- Tweets with high engagement
SELECT token, tweet_text, author_username, retweet_count, like_count, sentiment_score
FROM twitter_sentiment
WHERE (retweet_count + like_count) > 100
ORDER BY (retweet_count + like_count) DESC;


-- ------------------------------------------------------------
-- DATA MANAGEMENT
-- ------------------------------------------------------------

-- Delete tweets older than 30 days
-- DELETE FROM twitter_sentiment WHERE scraped_at < NOW() - INTERVAL '30 days';

-- Delete all tweets for a specific token
-- DELETE FROM twitter_sentiment WHERE token = 'EXAMPLE';

-- Delete low-quality bot tweets (use carefully)
-- DELETE FROM twitter_sentiment WHERE bot_probability > 0.9 AND author_followers < 10;

-- Clear all data (DANGER - no undo!)
-- TRUNCATE TABLE twitter_sentiment;


-- ------------------------------------------------------------
-- TABLE INFORMATION
-- ------------------------------------------------------------

-- View table structure
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'twitter_sentiment'
ORDER BY ordinal_position;

-- Check database size
SELECT pg_size_pretty(pg_total_relation_size('twitter_sentiment')) as table_size;

-- Count of NULL values per column
SELECT
    COUNT(*) FILTER (WHERE alert_level IS NULL) as null_alerts,
    COUNT(*) FILTER (WHERE volume_spike IS NULL) as null_volume,
    COUNT(*) FILTER (WHERE pump_score IS NULL) as null_pump
FROM twitter_sentiment;