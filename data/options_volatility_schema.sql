-- Options Volatility Database Schema
-- Tracks BTC/ETH implied volatility and skew for risk management

-- Drop existing tables if they exist
DROP TABLE IF EXISTS options_volatility CASCADE;

-- Main options volatility table
CREATE TABLE options_volatility (
    id SERIAL PRIMARY KEY,

    -- BTC metrics
    btc_iv DECIMAL(10, 2),           -- BTC at-the-money implied volatility
    btc_dvol DECIMAL(10, 2),         -- BTC DVOL index (Deribit Volatility Index)
    btc_skew DECIMAL(10, 2),         -- BTC 25-delta skew (negative = put premium)
    btc_iv_rank DECIMAL(5, 2),       -- BTC IV rank (0-100, percentile in 30d range)

    -- ETH metrics
    eth_iv DECIMAL(10, 2),           -- ETH at-the-money implied volatility
    eth_dvol DECIMAL(10, 2),         -- ETH DVOL index
    eth_skew DECIMAL(10, 2),         -- ETH 25-delta skew
    eth_iv_rank DECIMAL(5, 2),       -- ETH IV rank (0-100)

    -- Aggregate metrics
    avg_iv DECIMAL(10, 2),           -- Average of BTC and ETH IV
    volatility_regime VARCHAR(20),    -- EXTREME, HIGH, MODERATE, LOW
    directional_bias VARCHAR(20),     -- BEARISH_EXTREME, BEARISH, NEUTRAL, BULLISH

    -- Risk signals
    risk_level VARCHAR(20),           -- HIGH, MODERATE, LOW
    position_adjustment DECIMAL(5, 3), -- Position size multiplier (0.5 = half size)

    -- Timestamp
    scraped_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    -- Indexes
    CONSTRAINT vol_regime_check CHECK (volatility_regime IN ('EXTREME', 'HIGH', 'MODERATE', 'LOW')),
    CONSTRAINT risk_level_check CHECK (risk_level IN ('HIGH', 'MODERATE', 'LOW', 'NORMAL'))
);

-- Indexes for fast queries
CREATE INDEX idx_options_vol_scraped_at ON options_volatility(scraped_at DESC);
CREATE INDEX idx_options_vol_risk_level ON options_volatility(risk_level);
CREATE INDEX idx_options_vol_avg_iv ON options_volatility(avg_iv);
CREATE INDEX idx_options_vol_btc_iv ON options_volatility(btc_iv);
CREATE INDEX idx_options_vol_eth_iv ON options_volatility(eth_iv);

-- View for latest volatility snapshot
CREATE OR REPLACE VIEW options_volatility_latest AS
SELECT
    btc_iv,
    btc_skew,
    btc_iv_rank,
    eth_iv,
    eth_skew,
    eth_iv_rank,
    avg_iv,
    volatility_regime,
    directional_bias,
    risk_level,
    position_adjustment,
    scraped_at
FROM options_volatility
ORDER BY scraped_at DESC
LIMIT 1;

-- View for volatility alerts (when risk is elevated)
CREATE OR REPLACE VIEW options_volatility_alerts AS
SELECT
    avg_iv,
    volatility_regime,
    directional_bias,
    risk_level,
    position_adjustment,
    CASE
        WHEN avg_iv > 80 THEN 'EXTREME: IV above 80, reduce all positions'
        WHEN avg_iv > 65 THEN 'HIGH: Elevated volatility, reduce position sizes'
        WHEN btc_skew < -8 OR eth_skew < -8 THEN 'SKEW: Heavy put buying detected'
        WHEN risk_level = 'HIGH' THEN 'RISK: High volatility risk conditions'
        ELSE NULL
    END as alert_message,
    scraped_at
FROM options_volatility
WHERE scraped_at > NOW() - INTERVAL '1 hour'
  AND (risk_level IN ('HIGH', 'MODERATE') OR avg_iv > 65 OR btc_skew < -8 OR eth_skew < -8)
ORDER BY scraped_at DESC;

-- Function to get volatility risk score (0-100)
CREATE OR REPLACE FUNCTION get_volatility_risk_score()
RETURNS TABLE(risk_score INTEGER, risk_components JSONB) AS $$
DECLARE
    latest_record RECORD;
    score INTEGER := 0;
    components JSONB := '{}';
BEGIN
    -- Get latest options data
    SELECT * INTO latest_record
    FROM options_volatility
    ORDER BY scraped_at DESC
    LIMIT 1;

    IF latest_record IS NULL THEN
        RETURN QUERY SELECT 0, '{}'::JSONB;
        RETURN;
    END IF;

    -- Score based on average IV (0-40 points)
    IF latest_record.avg_iv > 80 THEN
        score := score + 40;
        components := components || '{"iv_score": 40}';
    ELSIF latest_record.avg_iv > 65 THEN
        score := score + 25;
        components := components || '{"iv_score": 25}';
    ELSIF latest_record.avg_iv > 50 THEN
        score := score + 10;
        components := components || '{"iv_score": 10}';
    END IF;

    -- Score based on skew (0-30 points)
    IF latest_record.btc_skew < -10 OR latest_record.eth_skew < -10 THEN
        score := score + 30;
        components := components || '{"skew_score": 30}';
    ELSIF latest_record.btc_skew < -5 OR latest_record.eth_skew < -5 THEN
        score := score + 15;
        components := components || '{"skew_score": 15}';
    END IF;

    -- Score based on IV rank (0-30 points)
    IF latest_record.btc_iv_rank > 80 OR latest_record.eth_iv_rank > 80 THEN
        score := score + 30;
        components := components || '{"iv_rank_score": 30}';
    ELSIF latest_record.btc_iv_rank > 60 OR latest_record.eth_iv_rank > 60 THEN
        score := score + 15;
        components := components || '{"iv_rank_score": 15}';
    END IF;

    components := components || jsonb_build_object(
        'total_score', score,
        'btc_iv', latest_record.btc_iv,
        'eth_iv', latest_record.eth_iv,
        'avg_iv', latest_record.avg_iv,
        'btc_skew', latest_record.btc_skew,
        'eth_skew', latest_record.eth_skew
    );

    RETURN QUERY SELECT score, components;
END;
$$ LANGUAGE plpgsql;

-- Grant permissions
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO postgres;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO postgres;

-- Sample query to check if institutions are hedging (for AI trader)
-- SELECT
--     CASE
--         WHEN avg_iv > 70 AND (btc_skew < -5 OR eth_skew < -5) THEN 'INSTITUTIONS_HEDGING'
--         WHEN avg_iv > 80 THEN 'PANIC_MODE'
--         WHEN avg_iv < 35 THEN 'COMPLACENCY'
--         ELSE 'NORMAL'
--     END as market_state,
--     position_adjustment
-- FROM options_volatility_latest;