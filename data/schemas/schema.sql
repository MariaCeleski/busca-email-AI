-- =============================================================================
-- AI Email Agent System — Reference SQL Schema
-- =============================================================================
-- This file is for documentation purposes. Actual migrations are managed by
-- Alembic in backend/alembic/versions/.

-- Users
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Connected Accounts (OAuth email providers)
CREATE TABLE connected_accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider VARCHAR(20) NOT NULL,
    email_address VARCHAR(255) NOT NULL,
    encrypted_access_token BYTEA,
    encrypted_refresh_token BYTEA,
    token_expires_at TIMESTAMPTZ,
    status VARCHAR(20) DEFAULT 'connected',
    connected_at TIMESTAMPTZ DEFAULT NOW(),
    last_sync TIMESTAMPTZ,
    UNIQUE(user_id, provider, email_address)
);

-- Processed Emails
CREATE TABLE processed_emails (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider_message_id VARCHAR(512) UNIQUE NOT NULL,
    sender VARCHAR(255) NOT NULL,
    subject TEXT,
    body TEXT,
    timestamp TIMESTAMPTZ NOT NULL,
    attachments JSONB DEFAULT '[]',
    thread_id VARCHAR(255),
    provider VARCHAR(20) NOT NULL,
    processing_timestamp TIMESTAMPTZ DEFAULT NOW(),
    -- Classification
    category VARCHAR(20),
    priority VARCHAR(10),
    confidence FLOAT,
    flagged_for_review BOOLEAN DEFAULT FALSE,
    -- Summary
    summary TEXT,
    action_items JSONB DEFAULT '[]',
    summary_is_fallback BOOLEAN DEFAULT FALSE,
    -- Workflow
    workflow_stage VARCHAR(30) DEFAULT 'queued',
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_emails_user_timestamp ON processed_emails (user_id, processing_timestamp DESC);
CREATE INDEX idx_emails_category ON processed_emails (category);
CREATE INDEX idx_emails_priority ON processed_emails (priority);
CREATE INDEX idx_emails_flagged ON processed_emails (flagged_for_review) WHERE flagged_for_review = TRUE;
CREATE INDEX idx_emails_provider_msg_id ON processed_emails (provider_message_id);

-- Draft Replies
CREATE TABLE draft_replies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email_id UUID NOT NULL REFERENCES processed_emails(id) ON DELETE CASCADE,
    reply_body TEXT NOT NULL,
    suggested_subject VARCHAR(150),
    referenced_email_ids JSONB DEFAULT '[]',
    status VARCHAR(20) DEFAULT 'pending',
    generated_at TIMESTAMPTZ DEFAULT NOW(),
    actioned_at TIMESTAMPTZ,
    edited_body TEXT,
    edited_subject VARCHAR(255),
    send_error TEXT
);

CREATE INDEX idx_drafts_status ON draft_replies (status);
CREATE INDEX idx_drafts_email ON draft_replies (email_id);

-- Access Logs
CREATE TABLE access_logs (
    id BIGSERIAL PRIMARY KEY,
    requester_id VARCHAR(255) NOT NULL,
    endpoint VARCHAR(255) NOT NULL,
    method VARCHAR(10) NOT NULL,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    response_status INTEGER
);

CREATE INDEX idx_access_logs_timestamp ON access_logs (timestamp);

-- Workflow Executions
CREATE TABLE workflow_executions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email_id UUID NOT NULL REFERENCES processed_emails(id) ON DELETE CASCADE,
    current_stage VARCHAR(30) NOT NULL,
    retry_counts JSONB DEFAULT '{}',
    started_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    error_message TEXT
);
