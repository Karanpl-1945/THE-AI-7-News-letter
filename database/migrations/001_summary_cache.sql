CREATE TABLE IF NOT EXISTS source_items (
    id UUID PRIMARY KEY,
    source_key TEXT NOT NULL UNIQUE,
    item_type TEXT NOT NULL,
    canonical_url TEXT,
    title TEXT NOT NULL DEFAULT '',
    content_hash CHAR(64) NOT NULL,
    raw_content TEXT NOT NULL DEFAULT '',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_source_items_type
    ON source_items (item_type);

CREATE INDEX IF NOT EXISTS idx_source_items_content_hash
    ON source_items (content_hash);

CREATE TABLE IF NOT EXISTS article_summaries (
    id UUID PRIMARY KEY,
    source_item_id UUID NOT NULL REFERENCES source_items(id) ON DELETE CASCADE,
    content_hash CHAR(64) NOT NULL,
    model_name TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    prompt_fingerprint CHAR(64) NOT NULL,
    summary_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_used_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_article_summary_cache
        UNIQUE (source_item_id, content_hash, model_name, prompt_fingerprint)
);

CREATE INDEX IF NOT EXISTS idx_article_summaries_source_item
    ON article_summaries (source_item_id);
