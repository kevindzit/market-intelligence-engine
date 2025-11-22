-- ============================================================================
-- DEFI TVL MONITORING TABLES
-- Purpose: Track DeFi protocol TVL and capital flows
-- Scraper: defi_tvl_monitor.py (DeFiLlama API - free, no key needed)
-- ============================================================================

-- ============================================================================
-- TABLE: defi_tvl_chains
-- Purpose: Stores TVL data per blockchain
-- Features: Track where DeFi capital is concentrated
-- ============================================================================

CREATE TABLE IF NOT EXISTS defi_tvl_chains (
    id SERIAL PRIMARY KEY,
    chain_name VARCHAR(50) NOT NULL,
    tvl_usd NUMERIC(20,2) NOT NULL,
    scraped_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_defi_chains_name ON defi_tvl_chains(chain_name);
CREATE INDEX IF NOT EXISTS idx_defi_chains_scraped ON defi_tvl_chains(scraped_at DESC);
CREATE INDEX IF NOT EXISTS idx_defi_chains_tvl ON defi_tvl_chains(tvl_usd DESC);

-- ============================================================================
-- TABLE: defi_protocols
-- Purpose: Stores top DeFi protocols with TVL and changes
-- Features: Track individual protocol health and capital flows
-- ============================================================================

CREATE TABLE IF NOT EXISTS defi_protocols (
    id SERIAL PRIMARY KEY,
    protocol_name VARCHAR(100) NOT NULL,
    symbol VARCHAR(20),
    tvl_usd NUMERIC(20,2) NOT NULL,
    change_1d_pct NUMERIC(8,2),
    change_7d_pct NUMERIC(8,2),
    category VARCHAR(50),
    main_chain VARCHAR(50),
    all_chains JSONB,
    market_cap NUMERIC(20,2),
    tvl_to_mcap_ratio NUMERIC(8,4),
    scraped_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_defi_protocols_name ON defi_protocols(protocol_name);
CREATE INDEX IF NOT EXISTS idx_defi_protocols_tvl ON defi_protocols(tvl_usd DESC);
CREATE INDEX IF NOT EXISTS idx_defi_protocols_scraped ON defi_protocols(scraped_at DESC);
CREATE INDEX IF NOT EXISTS idx_defi_protocols_category ON defi_protocols(category);
CREATE INDEX IF NOT EXISTS idx_defi_protocols_change_1d ON defi_protocols(change_1d_pct DESC);

-- ============================================================================
-- TABLE: defi_flow_signals
-- Purpose: Stores analyzed capital flow signals
-- Features: Biggest gainers/losers, category flows, risk indicators
-- ============================================================================

CREATE TABLE IF NOT EXISTS defi_flow_signals (
    id SERIAL PRIMARY KEY,
    biggest_gainers JSONB,
    biggest_losers JSONB,
    category_flows JSONB,
    risk_indicator VARCHAR(50),
    scraped_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_defi_signals_scraped ON defi_flow_signals(scraped_at DESC);
CREATE INDEX IF NOT EXISTS idx_defi_signals_risk ON defi_flow_signals(risk_indicator);

-- ============================================================================
-- VIEW: defi_tvl_latest
-- Purpose: Quick access to latest TVL data for AI trader
-- ============================================================================

CREATE OR REPLACE VIEW defi_tvl_latest AS
WITH latest_chains AS (
    SELECT DISTINCT ON (chain_name)
        chain_name,
        tvl_usd,
        scraped_at
    FROM defi_tvl_chains
    ORDER BY chain_name, scraped_at DESC
),
latest_protocols AS (
    SELECT DISTINCT ON (protocol_name)
        protocol_name,
        symbol,
        tvl_usd,
        change_1d_pct,
        change_7d_pct,
        category,
        main_chain,
        scraped_at
    FROM defi_protocols
    ORDER BY protocol_name, scraped_at DESC
)
SELECT
    (SELECT SUM(tvl_usd) FROM latest_chains) as total_tvl,
    (SELECT json_object_agg(chain_name, tvl_usd) FROM latest_chains) as chain_breakdown,
    (SELECT COUNT(*) FROM latest_protocols WHERE change_1d_pct > 5) as protocols_gaining,
    (SELECT COUNT(*) FROM latest_protocols WHERE change_1d_pct < -5) as protocols_losing,
    (SELECT MAX(scraped_at) FROM latest_chains) as last_updated;

-- ============================================================================
-- VIEW: defi_flow_alerts
-- Purpose: Generate alerts for significant TVL movements
-- Used by: AI trader for detecting capital rotation
-- ============================================================================

CREATE OR REPLACE VIEW defi_flow_alerts AS
WITH recent_data AS (
    SELECT
        protocol_name,
        tvl_usd,
        change_1d_pct,
        category,
        scraped_at
    FROM defi_protocols
    WHERE scraped_at > NOW() - INTERVAL '1 hour'
)
SELECT
    protocol_name,
    tvl_usd,
    change_1d_pct,
    category,
    CASE
        WHEN change_1d_pct > 20 AND tvl_usd > 100000000 THEN 'MASSIVE_INFLOW'
        WHEN change_1d_pct > 10 AND tvl_usd > 500000000 THEN 'LARGE_INFLOW'
        WHEN change_1d_pct < -20 AND tvl_usd > 100000000 THEN 'MASSIVE_OUTFLOW'
        WHEN change_1d_pct < -10 AND tvl_usd > 500000000 THEN 'LARGE_OUTFLOW'
        ELSE 'NORMAL'
    END as alert_type,
    scraped_at
FROM recent_data
WHERE ABS(change_1d_pct) > 10
ORDER BY ABS(change_1d_pct) DESC;

-- ============================================================================
-- INTEGRATION NOTES
-- ============================================================================
-- To apply these tables to your existing database:
-- psql -h localhost -p 54594 -U postgres -d pjx -f data/defi_tvl_schema.sql
--
-- The scraper will:
-- 1. Run every 30 minutes (configurable)
-- 2. Track top 20 protocols by TVL
-- 3. Monitor 8 major chains
-- 4. Calculate flow signals for AI trader
-- 5. No API key required (DeFiLlama is free)
-- ============================================================================