

For Senate and house scraper tables

CREATE TABLE congressional_trades (
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





here is a table update for FREDapi im pretty sure from 10-20-25 chat llm2

CREATE TABLE IF NOT EXISTS economic_indicators (
    id SERIAL PRIMARY KEY,
    indicator_code VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    value NUMERIC NOT NULL,
    scraped_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(indicator_code, date)
);

2nd table update for SEC fillings 10-20-25 chat llm2

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


company profiles table 10-20-25 chat llm2

-- This table will store fundamental company data fetched from the FMP API.
-- The "symbol" column is the primary way to identify a company and must be unique.
CREATE TABLE company_profiles (
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



