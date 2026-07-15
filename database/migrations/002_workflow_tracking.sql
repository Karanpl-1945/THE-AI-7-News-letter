CREATE TABLE IF NOT EXISTS newsletter_issues (
    id UUID PRIMARY KEY,
    issue_key TEXT NOT NULL UNIQUE,
    issue_date DATE NOT NULL,
    iso_year SMALLINT NOT NULL,
    iso_week SMALLINT NOT NULL CHECK (iso_week BETWEEN 1 AND 53),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'generated', 'sent', 'failed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    CONSTRAINT uq_newsletter_issue_week UNIQUE (iso_year, iso_week)
);

CREATE INDEX IF NOT EXISTS idx_newsletter_issues_status
    ON newsletter_issues (status);

CREATE TABLE IF NOT EXISTS workflow_runs (
    id UUID PRIMARY KEY,
    issue_id UUID NOT NULL REFERENCES newsletter_issues(id) ON DELETE CASCADE,
    thread_id TEXT NOT NULL UNIQUE,
    trigger_type TEXT NOT NULL
        CHECK (trigger_type IN ('local', 'github_manual', 'github_schedule')),
    dry_run BOOLEAN NOT NULL DEFAULT FALSE,
    status TEXT NOT NULL DEFAULT 'running'
        CHECK (status IN ('running', 'completed', 'failed')),
    attempt_count INTEGER NOT NULL DEFAULT 1 CHECK (attempt_count > 0),
    run_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    last_error TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_workflow_runs_issue_id
    ON workflow_runs (issue_id);

CREATE INDEX IF NOT EXISTS idx_workflow_runs_status
    ON workflow_runs (status);
