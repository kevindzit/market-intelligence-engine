-- Bridge Flows Schema for Cross-Chain Capital Tracking
-- Created: 2025-11-14
-- Purpose: Track capital rotation between L1s and L2s via bridge flows

-- Main table for daily bridge flow data
CREATE TABLE IF NOT EXISTS bridge_flows (
    id SERIAL PRIMARY KEY,
    chain VARCHAR(50) NOT NULL,
    date DATE NOT NULL,
    deposits_usd DECIMAL(18, 2),
    withdrawals_usd DECIMAL(18, 2),
    net_flow_usd DECIMAL(18, 2) GENERATED ALWAYS AS (deposits_usd - withdrawals_usd) STORED,
    deposit_txs INTEGER,
    withdraw_txs INTEGER,
    total_txs INTEGER GENERATED ALWAYS AS (deposit_txs + withdraw_txs) STORED,
    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(chain, date)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_bridge_flows_chain ON bridge_flows(chain);
CREATE INDEX IF NOT EXISTS idx_bridge_flows_date ON bridge_flows(date DESC);
CREATE INDEX IF NOT EXISTS idx_bridge_flows_net_flow ON bridge_flows(net_flow_usd);
CREATE INDEX IF NOT EXISTS idx_bridge_flows_scraped_at ON bridge_flows(scraped_at DESC);

-- Table for processed signals and alerts
CREATE TABLE IF NOT EXISTS bridge_flow_signals (
    id SERIAL PRIMARY KEY,
    signal_type VARCHAR(50) NOT NULL, -- 'volume_spike', 'capital_rotation', 'outflow_warning'
    chain VARCHAR(50),
    timeframe VARCHAR(20), -- '24h', '7d', '30d'
    metric_name VARCHAR(50), -- 'net_flow', 'velocity', 'rank'
    metric_value DECIMAL(18, 2),
    threshold DECIMAL(18, 2),
    interpretation VARCHAR(200),
    alert_level VARCHAR(20), -- 'info', 'warning', 'critical'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for signals
CREATE INDEX IF NOT EXISTS idx_bridge_signals_type ON bridge_flow_signals(signal_type);
CREATE INDEX IF NOT EXISTS idx_bridge_signals_chain ON bridge_flow_signals(chain);
CREATE INDEX IF NOT EXISTS idx_bridge_signals_created ON bridge_flow_signals(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_bridge_signals_alert ON bridge_flow_signals(alert_level);

-- View for latest flows per chain
CREATE OR REPLACE VIEW bridge_flows_latest AS
SELECT
    chain,
    date,
    deposits_usd,
    withdrawals_usd,
    net_flow_usd,
    deposit_txs,
    withdraw_txs,
    CASE
        WHEN net_flow_usd > 10000000 THEN 'STRONG_INFLOW'
        WHEN net_flow_usd > 1000000 THEN 'MODERATE_INFLOW'
        WHEN net_flow_usd < -10000000 THEN 'STRONG_OUTFLOW'
        WHEN net_flow_usd < -1000000 THEN 'MODERATE_OUTFLOW'
        ELSE 'NEUTRAL'
    END as flow_status
FROM bridge_flows
WHERE (chain, date) IN (
    SELECT chain, MAX(date) as max_date
    FROM bridge_flows
    GROUP BY chain
)
ORDER BY net_flow_usd DESC;

-- View for 7-day aggregated flows
CREATE OR REPLACE VIEW bridge_flows_7d AS
SELECT
    chain,
    SUM(deposits_usd) as deposits_7d,
    SUM(withdrawals_usd) as withdrawals_7d,
    SUM(net_flow_usd) as net_flow_7d,
    AVG(net_flow_usd) as avg_daily_flow,
    COUNT(DISTINCT date) as days_tracked,
    MAX(date) as latest_date
FROM bridge_flows
WHERE date >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY chain
ORDER BY net_flow_7d DESC;

-- View for L2 rotation rankings
CREATE OR REPLACE VIEW l2_rotation_rankings AS
WITH flow_metrics AS (
    SELECT
        chain,
        -- 24h metrics
        SUM(CASE WHEN date = CURRENT_DATE - INTERVAL '1 day' THEN net_flow_usd ELSE 0 END) as flow_24h,
        -- 7d metrics
        SUM(CASE WHEN date >= CURRENT_DATE - INTERVAL '7 days' THEN net_flow_usd ELSE 0 END) as flow_7d,
        -- 30d metrics
        SUM(CASE WHEN date >= CURRENT_DATE - INTERVAL '30 days' THEN net_flow_usd ELSE 0 END) as flow_30d,
        -- Velocity (7d vs 30d average)
        CASE
            WHEN COUNT(CASE WHEN date >= CURRENT_DATE - INTERVAL '30 days' THEN 1 END) >= 7 THEN
                (SUM(CASE WHEN date >= CURRENT_DATE - INTERVAL '7 days' THEN net_flow_usd ELSE 0 END) / 7) /
                NULLIF((SUM(CASE WHEN date >= CURRENT_DATE - INTERVAL '30 days' THEN net_flow_usd ELSE 0 END) / 30), 0)
            ELSE NULL
        END as velocity_ratio
    FROM bridge_flows
    WHERE date >= CURRENT_DATE - INTERVAL '30 days'
    GROUP BY chain
)
SELECT
    chain,
    flow_24h,
    flow_7d,
    flow_30d,
    velocity_ratio,
    RANK() OVER (ORDER BY flow_7d DESC) as flow_rank_7d,
    CASE
        WHEN flow_7d > 50000000 THEN 'HOT'
        WHEN flow_7d > 10000000 THEN 'WARMING'
        WHEN flow_7d < -10000000 THEN 'COOLING'
        WHEN flow_7d < -50000000 THEN 'COLD'
        ELSE 'NEUTRAL'
    END as rotation_status
FROM flow_metrics
ORDER BY flow_7d DESC;

-- Function to calculate flow velocity
CREATE OR REPLACE FUNCTION calculate_flow_velocity(
    p_chain VARCHAR(50),
    p_days INTEGER DEFAULT 7
) RETURNS TABLE (
    velocity DECIMAL(18, 2),
    acceleration DECIMAL(18, 2),
    trend VARCHAR(20)
) AS $$
DECLARE
    current_period_flow DECIMAL(18, 2);
    previous_period_flow DECIMAL(18, 2);
    velocity_value DECIMAL(18, 2);
    acceleration_value DECIMAL(18, 2);
    trend_value VARCHAR(20);
BEGIN
    -- Calculate current period flow
    SELECT SUM(net_flow_usd) INTO current_period_flow
    FROM bridge_flows
    WHERE chain = p_chain
    AND date > CURRENT_DATE - INTERVAL '1 day' * p_days
    AND date <= CURRENT_DATE;

    -- Calculate previous period flow
    SELECT SUM(net_flow_usd) INTO previous_period_flow
    FROM bridge_flows
    WHERE chain = p_chain
    AND date > CURRENT_DATE - INTERVAL '1 day' * (p_days * 2)
    AND date <= CURRENT_DATE - INTERVAL '1 day' * p_days;

    -- Calculate velocity (rate of change)
    IF previous_period_flow IS NOT NULL AND previous_period_flow != 0 THEN
        velocity_value := ((current_period_flow - previous_period_flow) / ABS(previous_period_flow)) * 100;
    ELSE
        velocity_value := 0;
    END IF;

    -- Simple acceleration (change in velocity)
    acceleration_value := current_period_flow - COALESCE(previous_period_flow, 0);

    -- Determine trend
    IF velocity_value > 50 THEN
        trend_value := 'ACCELERATING';
    ELSIF velocity_value > 10 THEN
        trend_value := 'INCREASING';
    ELSIF velocity_value < -50 THEN
        trend_value := 'DECELERATING';
    ELSIF velocity_value < -10 THEN
        trend_value := 'DECREASING';
    ELSE
        trend_value := 'STABLE';
    END IF;

    RETURN QUERY SELECT velocity_value, acceleration_value, trend_value;
END;
$$ LANGUAGE plpgsql;

-- Function to detect rotation signals
CREATE OR REPLACE FUNCTION detect_rotation_signals()
RETURNS TABLE (
    chain VARCHAR(50),
    signal_strength VARCHAR(20),
    net_flow_7d DECIMAL(18, 2),
    velocity DECIMAL(18, 2),
    recommendation VARCHAR(200)
) AS $$
BEGIN
    RETURN QUERY
    WITH flow_analysis AS (
        SELECT
            bf.chain,
            SUM(CASE WHEN bf.date >= CURRENT_DATE - INTERVAL '7 days' THEN bf.net_flow_usd ELSE 0 END) as flow_7d,
            (SELECT velocity FROM calculate_flow_velocity(bf.chain, 7)) as vel
        FROM bridge_flows bf
        WHERE bf.date >= CURRENT_DATE - INTERVAL '7 days'
        GROUP BY bf.chain
    )
    SELECT
        fa.chain,
        CASE
            WHEN fa.flow_7d > 100000000 AND fa.vel > 50 THEN 'VERY_STRONG'
            WHEN fa.flow_7d > 50000000 AND fa.vel > 25 THEN 'STRONG'
            WHEN fa.flow_7d > 10000000 AND fa.vel > 0 THEN 'MODERATE'
            WHEN fa.flow_7d < -50000000 THEN 'NEGATIVE'
            ELSE 'WEAK'
        END as signal_strength,
        fa.flow_7d as net_flow_7d,
        fa.vel as velocity,
        CASE
            WHEN fa.flow_7d > 100000000 AND fa.vel > 50 THEN
                'Strong capital rotation into ' || fa.chain || '. Consider accumulating ecosystem tokens.'
            WHEN fa.flow_7d > 50000000 AND fa.vel > 25 THEN
                'Significant inflows to ' || fa.chain || '. Monitor for entry opportunities.'
            WHEN fa.flow_7d > 10000000 AND fa.vel > 0 THEN
                'Moderate inflows to ' || fa.chain || '. Watch for trend continuation.'
            WHEN fa.flow_7d < -50000000 THEN
                'Major outflows from ' || fa.chain || '. Consider reducing exposure.'
            ELSE
                'Neutral flow for ' || fa.chain || '. No immediate action required.'
        END as recommendation
    FROM flow_analysis fa
    WHERE fa.flow_7d IS NOT NULL
    ORDER BY fa.flow_7d DESC;
END;
$$ LANGUAGE plpgsql;

-- Sample queries for AI trader
COMMENT ON TABLE bridge_flows IS 'DeFiLlama bridge flow data for L1/L2 capital rotation tracking';
COMMENT ON VIEW l2_rotation_rankings IS 'Use this view to identify which L2s are gaining/losing capital';
COMMENT ON FUNCTION detect_rotation_signals() IS 'Returns actionable trading signals based on bridge flows';