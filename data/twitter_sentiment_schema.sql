-- Add new columns for Twitter Sentiment V2 improvements
-- Volume tracking (PRIMARY signal), bot detection, pump detection
-- Run: psql -h localhost -p 54594 -U postgres -d postgres -f data/twitter_sentiment_v2_schema.sql

-- Add new columns if they don't exist
ALTER TABLE twitter_sentiment
ADD COLUMN IF NOT EXISTS volume_spike NUMERIC(5,2),
ADD COLUMN IF NOT EXISTS bot_probability NUMERIC(4,3),
ADD COLUMN IF NOT EXISTS pump_score NUMERIC(4,3),
ADD COLUMN IF NOT EXISTS influence_weight NUMERIC(10,2);

-- Create indexes for new columns
CREATE INDEX IF NOT EXISTS idx_volume_spike ON twitter_sentiment(volume_spike DESC);
CREATE INDEX IF NOT EXISTS idx_bot_probability ON twitter_sentiment(bot_probability);
CREATE INDEX IF NOT EXISTS idx_pump_score ON twitter_sentiment(pump_score);

-- Create materialized view for hourly volume tracking
-- This helps calculate baseline volumes efficiently
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
    COUNT(*) FILTER (WHERE alert_level IN ('HIGH', 'EXTREME')) as high_impact_count
FROM twitter_sentiment
WHERE scraped_at > NOW() - INTERVAL '7 days'
GROUP BY hour, token;

-- Create index on materialized view
CREATE INDEX idx_hourly_volume_token ON hourly_twitter_volume(token, hour DESC);

-- Create view for volume spike detection (5-minute intervals)
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
HAVING COUNT(*) > 5  -- Minimum tweets for signal
ORDER BY max_spike DESC NULLS LAST, interval_5min DESC;

-- Create alert view for trading signals
CREATE OR REPLACE VIEW twitter_trading_signals AS
SELECT
    token,
    MAX(volume_spike) as volume_signal,
    AVG(CASE WHEN bot_probability < 0.3 THEN sentiment_score END) as quality_sentiment,
    COUNT(*) FILTER (WHERE alert_level IN ('HIGH', 'EXTREME')) as high_impact_tweets,
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
HAVING COUNT(*) >= 5;  -- Minimum tweets for valid signal

-- Function to refresh materialized view (call every hour)
CREATE OR REPLACE FUNCTION refresh_twitter_volume()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY hourly_twitter_volume;
END;
$$ LANGUAGE plpgsql;

-- Query to show current trading opportunities
-- SELECT * FROM twitter_trading_signals WHERE signal IN ('BUY', 'STRONG BUY') ORDER BY volume_signal DESC;