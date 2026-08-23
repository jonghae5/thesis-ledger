CREATE SEQUENCE IF NOT EXISTS fundamental_snapshots_id_seq;
CREATE TABLE IF NOT EXISTS fundamental_snapshots (
    id BIGINT PRIMARY KEY DEFAULT nextval('fundamental_snapshots_id_seq'),
    ticker VARCHAR NOT NULL,
    period VARCHAR NOT NULL,
    filed_at DATE NOT NULL,
    accession VARCHAR NOT NULL,
    form VARCHAR NOT NULL,
    fiscal_year INTEGER,
    fiscal_period VARCHAR,
    revenue DOUBLE,
    gross_profit DOUBLE,
    operating_income DOUBLE,
    net_income DOUBLE,
    operating_cashflow DOUBLE,
    capex DOUBLE,
    fcf DOUBLE,
    cash DOUBLE,
    debt DOUBLE,
    shares DOUBLE,
    currency VARCHAR,
    source VARCHAR NOT NULL,
    source_url VARCHAR,
    retrieved_at TIMESTAMP NOT NULL,
    UNIQUE (ticker, accession, period)
);

-- Preserve legacy data as explicitly-labelled snapshots. New readers can use
-- the point-in-time table immediately without destroying existing databases.
INSERT INTO fundamental_snapshots (
    ticker, period, filed_at, accession, form, revenue, gross_profit,
    operating_income, net_income, operating_cashflow, capex, fcf, cash, debt,
    shares, source, source_url, retrieved_at
)
SELECT
    ticker, period, reported_at, 'legacy:' || ticker || ':' || period, 'LEGACY',
    revenue, gross_profit, operating_income, net_income, operating_cashflow,
    capex, fcf, cash, debt, shares, source, source_url, retrieved_at
FROM fundamentals f
WHERE NOT EXISTS (
    SELECT 1 FROM fundamental_snapshots s
    WHERE s.ticker = f.ticker
      AND s.accession = 'legacy:' || f.ticker || ':' || f.period
      AND s.period = f.period
);

ALTER TABLE investment_analysis ADD COLUMN IF NOT EXISTS run_id VARCHAR;
ALTER TABLE investment_analysis ADD COLUMN IF NOT EXISTS model_name VARCHAR;
ALTER TABLE investment_analysis ADD COLUMN IF NOT EXISTS model_version VARCHAR;
ALTER TABLE investment_analysis ADD COLUMN IF NOT EXISTS prompt_version VARCHAR;
ALTER TABLE investment_analysis ADD COLUMN IF NOT EXISTS input_snapshot_json VARCHAR;
ALTER TABLE investment_analysis ADD COLUMN IF NOT EXISTS assumptions_json VARCHAR;
