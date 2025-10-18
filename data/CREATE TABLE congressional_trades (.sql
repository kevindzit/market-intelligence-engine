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

ALTER TABLE congressional_trades ALTER COLUMN ticker TYPE VARCHAR(50);