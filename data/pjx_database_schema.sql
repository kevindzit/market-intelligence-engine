-- ============================================================================
-- PJX CRYPTO TRADING SYSTEM - COMPLETE DATABASE SCHEMA
-- ============================================================================
-- This file contains the complete database schema for the PJX project
-- Use this to recreate the entire database structure from scratch
--
-- Run with: psql -h localhost -p 54594 -U postgres -d postgres -f data/pjx_database_schema.sql
-- ============================================================================

-- ============================================================================
-- TABLE: congressional_trades
-- Purpose: Tracks congressional stock trades from Senate and House
-- Scrapers: senate_scraper.py, house_scraper.py
-- ============================================================================

CREATE TABLE IF NOT EXISTS congressional_trades (
    id SERIAL PRIMARY KEY,
    source VARCHAR(10),
    filer_name VARCHAR(255),
    filing_date DATE,
    transaction_date DATE,
    ticker VARCHAR(50),
    transaction_type VARCHAR(50),
    amount_range VARCHAR(100),
    report_url TEXT,
    scraped_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_transaction UNIQUE (filer_name, transaction_date, ticker, transaction_type, amount_range)
);

-- ============================================================================
-- TABLE: economic_indicators
-- Purpose: Stores economic data from FRED API
-- Scraper: fred_scraper.py
-- ============================================================================

CREATE TABLE IF NOT EXISTS economic_indicators (
    id SERIAL PRIMARY KEY,
    indicator_code VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    value NUMERIC NOT NULL,
    scraped_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(indicator_code, date)
);

-- ============================================================================
-- TABLE: sec_filings
-- Purpose: Tracks SEC filings from EDGAR RSS feed
-- Scraper: sec_scraper.py
-- ============================================================================

CREATE TABLE IF NOT EXISTS sec_filings (
    id SERIAL PRIMARY KEY,
    cik VARCHAR(20) NOT NULL,
    company_name VARCHAR(255),
    form_type VARCHAR(20) NOT NULL,
    filing_date TIMESTAMP WITH TIME ZONE,
    filing_url TEXT NOT NULL,
    scraped_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(filing_url)
);

-- ============================================================================
-- TABLE: company_profiles
-- Purpose: Stores fundamental company data from FMP API
-- Scraper: company_fundamentals_scraper.py
-- ============================================================================

CREATE TABLE IF NOT EXISTS company_profiles (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) UNIQUE NOT NULL,
    company_name VARCHAR(255),
    exchange VARCHAR(50),
    industry VARCHAR(255),
    sector VARCHAR(255),
    market_cap BIGINT,
    beta NUMERIC(10, 4),
    pe_ratio NUMERIC(10, 4),
    eps NUMERIC(10, 4),
    website TEXT,
    last_updated TIMESTAMP WITH TIME ZONE
);

-- ============================================================================
-- TABLE: twitter_sentiment
-- Purpose: Stores Twitter sentiment data for crypto trading signals
-- Scrapers: twitter_sentiment.py, twitter_whales.py
-- Features: Volume tracking, bot detection, whale tracking, pump detection
-- ============================================================================

CREATE TABLE IF NOT EXISTS twitter_sentiment (
    id SERIAL PRIMARY KEY,
    tweet_id VARCHAR(50) NOT NULL,
    token VARCHAR(20) NOT NULL,
    tweet_text TEXT NOT NULL,
    sentiment_score NUMERIC(5,4),
    sentiment_label VARCHAR(20),
    author_username VARCHAR(100),
    author_followers INTEGER,
    retweet_count INTEGER DEFAULT 0,
    like_count INTEGER DEFAULT 0,
    tweet_created_at TIMESTAMP WITH TIME ZONE,
    scraped_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    weighted_score NUMERIC(10,4),
    alert_level VARCHAR(20),
    is_whale BOOLEAN DEFAULT false,
    volume_spike NUMERIC(5,2),
    bot_probability NUMERIC(4,3),
    pump_score NUMERIC(4,3),
    influence_weight NUMERIC(10,2),
    source VARCHAR(50) DEFAULT 'general_search',
    CONSTRAINT unique_tweet_token UNIQUE (tweet_id, token)
);

-- ============================================================================
-- INDEXES: twitter_sentiment
-- Optimized for fast queries on sentiment, volume, whales, and time ranges
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_twitter_token ON twitter_sentiment(token);
CREATE INDEX IF NOT EXISTS idx_twitter_scraped_at ON twitter_sentiment(scraped_at);
CREATE INDEX IF NOT EXISTS idx_twitter_sentiment_score ON twitter_sentiment(sentiment_score);
CREATE INDEX IF NOT EXISTS idx_twitter_created_at ON twitter_sentiment(tweet_created_at);
CREATE INDEX IF NOT EXISTS idx_alert_level ON twitter_sentiment(alert_level);
CREATE INDEX IF NOT EXISTS idx_weighted_score ON twitter_sentiment(weighted_score DESC);
CREATE INDEX IF NOT EXISTS idx_is_whale ON twitter_sentiment(is_whale);
CREATE INDEX IF NOT EXISTS idx_volume_spike ON twitter_sentiment(volume_spike DESC);
CREATE INDEX IF NOT EXISTS idx_bot_probability ON twitter_sentiment(bot_probability);
CREATE INDEX IF NOT EXISTS idx_pump_score ON twitter_sentiment(pump_score);
CREATE INDEX IF NOT EXISTS idx_source ON twitter_sentiment(source);

-- ============================================================================
-- MATERIALIZED VIEW: hourly_twitter_volume
-- Purpose: Efficiently calculates baseline volumes for spike detection
-- Refresh: Every hour via refresh_twitter_volume() function
-- ============================================================================

DROP MATERIALIZED VIEW IF EXISTS hourly_twitter_volume;
CREATE MATERIALIZED VIEW hourly_twitter_volume AS
SELECT
    DATE_TRUNC('hour', scraped_at) AS hour,
    token,
    COUNT(*) as tweet_count,
    COUNT(*) FILTER (WHERE bot_probability < 0.5) as human_tweets,
    AVG(sentiment_score) as avg_sentiment,
    AVG(CASE WHEN bot_probability < 0.5 THEN sentiment_score END) as human_sentiment,
    MAX(volume_spike) as max_volume_spike,
    AVG(weighted_score) as avg_weighted,
    MAX(weighted_score) as max_weighted,
    COUNT(*) FILTER (WHERE alert_level IN ('HIGH', 'EXTREME', 'WHALE_SIGNAL')) as high_impact_count
FROM twitter_sentiment
WHERE scraped_at > NOW() - INTERVAL '7 days'
GROUP BY hour, token;

CREATE INDEX IF NOT EXISTS idx_hourly_volume_token ON hourly_twitter_volume(token, hour DESC);

-- ============================================================================
-- VIEW: recent_volume_spikes
-- Purpose: Real-time volume spike detection (5-minute intervals)
-- Used by: Trading signal generation
-- ============================================================================

CREATE OR REPLACE VIEW recent_volume_spikes AS
SELECT
    token,
    DATE_TRUNC('minute', scraped_at) - (EXTRACT(minute FROM scraped_at)::integer % 5) * INTERVAL '1 minute' as interval_5min,
    COUNT(*) as tweet_count,
    MAX(volume_spike) as max_spike,
    AVG(sentiment_score) as avg_sentiment,
    AVG(CASE WHEN bot_probability < 0.5 THEN sentiment_score END) as human_sentiment,
    COUNT(*) FILTER (WHERE bot_probability >= 0.7) as bot_count,
    COUNT(*) FILTER (WHERE is_whale = true) as whale_count
FROM twitter_sentiment
WHERE scraped_at > NOW() - INTERVAL '1 hour'
GROUP BY token, interval_5min
HAVING COUNT(*) > 5
ORDER BY max_spike DESC NULLS LAST, interval_5min DESC;

-- ============================================================================
-- VIEW: twitter_trading_signals
-- Purpose: Generates BUY/SELL/HOLD signals from combined data
-- Used by: AI trading system decision making
-- ============================================================================

CREATE OR REPLACE VIEW twitter_trading_signals AS
SELECT
    token,
    MAX(volume_spike) as volume_signal,
    AVG(CASE WHEN bot_probability < 0.3 THEN sentiment_score END) as quality_sentiment,
    COUNT(*) FILTER (WHERE alert_level IN ('HIGH', 'EXTREME', 'WHALE_SIGNAL')) as high_impact_tweets,
    MAX(CASE WHEN pump_score IS NOT NULL THEN pump_score END) as pump_risk,
    CASE
        WHEN MAX(volume_spike) >= 3.0 AND AVG(CASE WHEN bot_probability < 0.3 THEN sentiment_score END) > 0.2
            THEN 'STRONG BUY'
        WHEN MAX(volume_spike) >= 2.0 AND AVG(CASE WHEN bot_probability < 0.3 THEN sentiment_score END) > 0.1
            THEN 'BUY'
        WHEN MAX(volume_spike) >= 2.0 AND AVG(CASE WHEN bot_probability < 0.3 THEN sentiment_score END) < -0.2
            THEN 'SELL'
        WHEN MAX(pump_score) >= 0.7
            THEN 'PUMP WARNING'
        ELSE 'HOLD'
    END as signal,
    COUNT(*) as total_tweets,
    NOW() as signal_time
FROM twitter_sentiment
WHERE scraped_at > NOW() - INTERVAL '15 minutes'
GROUP BY token
HAVING COUNT(*) >= 5;

-- ============================================================================
-- FUNCTION: refresh_twitter_volume()
-- Purpose: Refreshes the hourly_twitter_volume materialized view
-- Usage: Call every hour to keep baseline volumes up to date
-- Example: SELECT refresh_twitter_volume();
-- ============================================================================

CREATE OR REPLACE FUNCTION refresh_twitter_volume()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY hourly_twitter_volume;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- COMPLETE SCHEMA LOADED
-- ============================================================================
-- Tables created:
--   - congressional_trades (Senate & House stock trades)
--   - economic_indicators (FRED economic data)
--   - sec_filings (SEC EDGAR filings)
--   - company_profiles (FMP fundamental data)
--   - twitter_sentiment (Multi-scraper Twitter sentiment system)
--
-- Views created:
--   - recent_volume_spikes (5-min volume tracking)
--   - twitter_trading_signals (BUY/SELL/HOLD signals)
--
-- Materialized views:
--   - hourly_twitter_volume (Baseline volume calculations)
--
-- Functions:
--   - refresh_twitter_volume() (Refresh hourly baselines)
-- ============================================================================