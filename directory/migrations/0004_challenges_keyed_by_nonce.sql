-- Audit fix (2026-10): challenges were keyed by kid, so anyone could reset a
-- victim's pending challenge (POST /register/challenge is unauthenticated)
-- and break their registration. Key by nonce instead; several outstanding
-- challenges per kid may coexist and each is single-use.
-- Pending challenges live ≤5 minutes, so dropping them is safe.
DROP TABLE IF EXISTS registration_challenges;

CREATE TABLE registration_challenges (
  nonce       TEXT PRIMARY KEY,
  kid         TEXT NOT NULL,
  expires_at  INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_challenges_kid ON registration_challenges(kid);
CREATE INDEX IF NOT EXISTS idx_challenges_expires ON registration_challenges(expires_at);
