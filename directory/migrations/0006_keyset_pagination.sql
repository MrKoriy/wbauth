-- Audit #21: keyset pagination on (created_at DESC, kid DESC).
CREATE INDEX IF NOT EXISTS idx_agents_created_kid ON agents(created_at DESC, kid DESC);
