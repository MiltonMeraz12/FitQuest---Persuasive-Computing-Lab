CREATE TABLE IF NOT EXISTS wearable_latest (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  payload TEXT NOT NULL,
  received_at INTEGER NOT NULL
);
