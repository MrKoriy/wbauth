-- Per CONTEXT.md D-40, D-48 (per-IP D1 small-row strategy)
CREATE TABLE IF NOT EXISTS ratelimit (
  ip          TEXT NOT NULL,
  day_bucket  INTEGER NOT NULL,
  count       INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (ip, day_bucket)
);
