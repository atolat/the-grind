CREATE TABLE IF NOT EXISTS store (
    key       VARCHAR(255) PRIMARY KEY,
    value     TEXT NOT NULL,
    expire_at BIGINT NOT NULL DEFAULT 0
);

-- Index on expire_at for efficient cleanup queries
CREATE INDEX IF NOT EXISTS idx_store_expire_at ON store (expire_at);
