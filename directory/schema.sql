CREATE TABLE IF NOT EXISTS hello (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  message TEXT NOT NULL,
  created_at INTEGER NOT NULL DEFAULT (unixepoch())
);
INSERT INTO hello (message) VALUES ('Day 1 works');
