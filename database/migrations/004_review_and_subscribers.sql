ALTER TABLE newsletter_issues
    DROP CONSTRAINT IF EXISTS newsletter_issues_status_check;

ALTER TABLE newsletter_issues
    ADD CONSTRAINT newsletter_issues_status_check
    CHECK (status IN (
        'pending', 'running', 'generated', 'reviewing',
        'changes_requested', 'approved', 'sent', 'failed'
    ));

CREATE TABLE IF NOT EXISTS approvals (
    id UUID PRIMARY KEY,
    issue_id UUID NOT NULL REFERENCES newsletter_issues(id) ON DELETE CASCADE,
    workflow_run_id UUID NOT NULL REFERENCES workflow_runs(id) ON DELETE CASCADE,
    decision TEXT NOT NULL
        CHECK (decision IN ('approved', 'changes_requested')),
    feedback TEXT,
    revision_number INTEGER NOT NULL DEFAULT 1 CHECK (revision_number > 0),
    decided_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_approvals_issue_id
    ON approvals (issue_id);

CREATE TABLE IF NOT EXISTS subscribers (
    id UUID PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'unsubscribed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_subscribers_status
    ON subscribers (status);

CREATE TABLE IF NOT EXISTS email_deliveries (
    id UUID PRIMARY KEY,
    issue_id UUID NOT NULL REFERENCES newsletter_issues(id) ON DELETE CASCADE,
    subscriber_id UUID NOT NULL REFERENCES subscribers(id) ON DELETE CASCADE,
    status TEXT NOT NULL
        CHECK (status IN ('sent', 'failed')),
    error_message TEXT,
    sent_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_email_delivery_issue_subscriber
        UNIQUE (issue_id, subscriber_id)
);

CREATE INDEX IF NOT EXISTS idx_email_deliveries_issue_id
    ON email_deliveries (issue_id);
