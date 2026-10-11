-- 2026-10 audit: prove control of signature_agent_url before showing it as
-- trusted. Unverified registrations are still accepted (key ownership is
-- proven) but are flagged so verifiers/UIs never treat the claimed domain as
-- authoritative.
ALTER TABLE agents ADD COLUMN domain_verified INTEGER NOT NULL DEFAULT 0;
ALTER TABLE agents ADD COLUMN domain_verified_at INTEGER;
CREATE INDEX IF NOT EXISTS idx_agents_client_name ON agents(client_name);
