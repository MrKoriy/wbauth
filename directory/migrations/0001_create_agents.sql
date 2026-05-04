-- Per CONTEXT.md D-36
CREATE TABLE IF NOT EXISTS agents (
  kid                  TEXT PRIMARY KEY,
  client_name          TEXT NOT NULL,
  client_uri           TEXT,
  signature_agent_url  TEXT NOT NULL,
  expected_user_agent  TEXT,
  contacts             TEXT,
  purpose              TEXT,
  targeted_content     TEXT,
  rate_control         TEXT,
  keys                 TEXT NOT NULL,
  created_at           INTEGER NOT NULL,
  last_updated         INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_agents_created_at ON agents(created_at DESC);
