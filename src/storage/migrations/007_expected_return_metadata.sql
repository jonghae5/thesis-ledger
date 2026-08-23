ALTER TABLE investment_analysis ADD COLUMN IF NOT EXISTS expected_return_horizon_months INTEGER;
ALTER TABLE investment_analysis ADD COLUMN IF NOT EXISTS expected_return_method VARCHAR;
ALTER TABLE investment_analysis ADD COLUMN IF NOT EXISTS expected_return_annualized DOUBLE;
ALTER TABLE investment_analysis ADD COLUMN IF NOT EXISTS expected_return_basis VARCHAR;
