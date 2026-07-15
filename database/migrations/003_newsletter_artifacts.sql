CREATE TABLE IF NOT EXISTS newsletter_artifacts (
    id UUID PRIMARY KEY,
    issue_id UUID NOT NULL REFERENCES newsletter_issues(id) ON DELETE CASCADE,
    workflow_run_id UUID NOT NULL REFERENCES workflow_runs(id) ON DELETE CASCADE,
    artifact_type TEXT NOT NULL
        CHECK (artifact_type IN ('html', 'pdf', 'image')),
    storage_provider TEXT NOT NULL DEFAULT 'r2'
        CHECK (storage_provider = 'r2'),
    bucket_name TEXT NOT NULL,
    object_key TEXT NOT NULL,
    content_type TEXT NOT NULL,
    size_bytes BIGINT NOT NULL CHECK (size_bytes >= 0),
    sha256 CHAR(64) NOT NULL,
    etag TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_newsletter_artifact_run_type
        UNIQUE (workflow_run_id, artifact_type),
    CONSTRAINT uq_newsletter_artifact_object
        UNIQUE (bucket_name, object_key)
);

CREATE INDEX IF NOT EXISTS idx_newsletter_artifacts_issue_id
    ON newsletter_artifacts (issue_id);

CREATE INDEX IF NOT EXISTS idx_newsletter_artifacts_workflow_run_id
    ON newsletter_artifacts (workflow_run_id);
