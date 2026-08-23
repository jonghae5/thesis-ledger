CREATE TABLE IF NOT EXISTS holdings (
    ticker VARCHAR PRIMARY KEY,
    shares DOUBLE NOT NULL,
    avg_cost DOUBLE NOT NULL,
    opened_at DATE NOT NULL,
    sector VARCHAR
);
