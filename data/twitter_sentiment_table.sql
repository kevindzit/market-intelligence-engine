-- Twitter Sentiment Data Table
-- Stores crypto sentiment data from Twitter/X using twikit
-- Run: psql -h localhost -p 54594 -U postgres -d postgres -f data/twitter_sentiment_table.sql

CREATE TABLE IF NOT EXISTS twitter_sentiment (
    id SERIAL PRIMARY KEY,
    tweet_id VARCHAR(50) UNIQUE NOT NULL,
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
    CONSTRAINT unique_tweet_token UNIQUE (tweet_id, token)
);

CREATE INDEX IF NOT EXISTS idx_twitter_token ON twitter_sentiment(token);
CREATE INDEX IF NOT EXISTS idx_twitter_scraped_at ON twitter_sentiment(scraped_at);
CREATE INDEX IF NOT EXISTS idx_twitter_sentiment_score ON twitter_sentiment(sentiment_score);
CREATE INDEX IF NOT EXISTS idx_twitter_created_at ON twitter_sentiment(tweet_created_at);

-- Query examples:

-- Get average sentiment by token (last 24 hours)
-- SELECT token, AVG(sentiment_score) as avg_sentiment, COUNT(*) as tweet_count
-- FROM twitter_sentiment
-- WHERE scraped_at > NOW() - INTERVAL '24 hours'
-- GROUP BY token
-- ORDER BY avg_sentiment DESC;

-- Get most influential tweets (high engagement)
-- SELECT token, tweet_text, sentiment_score, (retweet_count + like_count) as engagement
-- FROM twitter_sentiment
-- WHERE scraped_at > NOW() - INTERVAL '6 hours'
-- ORDER BY engagement DESC
-- LIMIT 20;

-- Sentiment trend over time
-- SELECT DATE_TRUNC('hour', scraped_at) as hour, token, AVG(sentiment_score) as avg_sentiment
-- FROM twitter_sentiment
-- WHERE scraped_at > NOW() - INTERVAL '24 hours'
-- GROUP BY hour, token
-- ORDER BY hour DESC, token;


i later did this

ALTER TABLE twitter_sentiment 
ADD COLUMN IF NOT EXISTS weighted_score NUMERIC(10,4),
ADD COLUMN IF NOT EXISTS alert_level VARCHAR(20),
ADD COLUMN IF NOT EXISTS is_whale BOOLEAN DEFAULT FALSE;

-- Create index for fast whale queries
CREATE INDEX IF NOT EXISTS idx_alert_level ON twitter_sentiment(alert_level);
CREATE INDEX IF NOT EXISTS idx_weighted_score ON twitter_sentiment(weighted_score DESC);
CREATE INDEX IF NOT EXISTS idx_is_whale ON twitter_sentiment(is_whale);