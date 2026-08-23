ALTER TABLE estimate_snapshots ADD COLUMN IF NOT EXISTS eps_mean_7d_ago DOUBLE;
ALTER TABLE estimate_snapshots ADD COLUMN IF NOT EXISTS eps_mean_30d_ago DOUBLE;
ALTER TABLE estimate_snapshots ADD COLUMN IF NOT EXISTS eps_mean_90d_ago DOUBLE;
ALTER TABLE estimate_snapshots ADD COLUMN IF NOT EXISTS revenue_mean_7d_ago DOUBLE;
ALTER TABLE estimate_snapshots ADD COLUMN IF NOT EXISTS revenue_mean_30d_ago DOUBLE;
ALTER TABLE estimate_snapshots ADD COLUMN IF NOT EXISTS revenue_mean_90d_ago DOUBLE;
