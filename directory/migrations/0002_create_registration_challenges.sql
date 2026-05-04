-- Per CONTEXT.md D-38 (two-step proof-of-key-ownership)
CREATE TABLE IF NOT EXISTS registration_challenges (
  kid         TEXT PRIMARY KEY,
  nonce       TEXT NOT NULL,
  expires_at  INTEGER NOT NULL
);
