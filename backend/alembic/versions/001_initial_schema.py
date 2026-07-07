"""initial_schema

Revision ID: 001
Revises: 
Create Date: 2024-01-01 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create all tables and indexes for the AI Email Agent system."""

    # --- Users ---
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )

    # --- Connected Accounts ---
    op.create_table(
        "connected_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("email_address", sa.String(255), nullable=False),
        sa.Column("encrypted_access_token", sa.LargeBinary(), nullable=True),
        sa.Column("encrypted_refresh_token", sa.LargeBinary(), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), server_default="connected"),
        sa.Column("connected_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("last_sync", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", "provider", "email_address"),
    )

    # --- Processed Emails ---
    op.create_table(
        "processed_emails",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider_message_id", sa.String(512), unique=True, nullable=False),
        sa.Column("sender", sa.String(255), nullable=False),
        sa.Column("subject", sa.Text(), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attachments", postgresql.JSONB(), server_default="[]"),
        sa.Column("thread_id", sa.String(255), nullable=True),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("processing_timestamp", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        # Classification
        sa.Column("category", sa.String(20), nullable=True),
        sa.Column("priority", sa.String(10), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("flagged_for_review", sa.Boolean(), server_default="FALSE"),
        # Summary
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("action_items", postgresql.JSONB(), server_default="[]"),
        sa.Column("summary_is_fallback", sa.Boolean(), server_default="FALSE"),
        # Workflow
        sa.Column("workflow_stage", sa.String(30), server_default="queued"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )

    # Indexes for processed_emails
    op.create_index(
        "idx_emails_user_timestamp",
        "processed_emails",
        ["user_id", sa.text("processing_timestamp DESC")],
    )
    op.create_index("idx_emails_category", "processed_emails", ["category"])
    op.create_index("idx_emails_priority", "processed_emails", ["priority"])
    op.create_index(
        "idx_emails_flagged",
        "processed_emails",
        ["flagged_for_review"],
        postgresql_where=sa.text("flagged_for_review = TRUE"),
    )
    op.create_index("idx_emails_provider_msg_id", "processed_emails", ["provider_message_id"])

    # --- Draft Replies ---
    op.create_table(
        "draft_replies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("processed_emails.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reply_body", sa.Text(), nullable=False),
        sa.Column("suggested_subject", sa.String(150), nullable=True),
        sa.Column("referenced_email_ids", postgresql.JSONB(), server_default="[]"),
        sa.Column("status", sa.String(20), server_default="pending"),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("actioned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("edited_body", sa.Text(), nullable=True),
        sa.Column("edited_subject", sa.String(255), nullable=True),
        sa.Column("send_error", sa.Text(), nullable=True),
    )

    # Indexes for draft_replies
    op.create_index("idx_drafts_status", "draft_replies", ["status"])
    op.create_index("idx_drafts_email", "draft_replies", ["email_id"])

    # --- Access Logs ---
    op.create_table(
        "access_logs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("requester_id", sa.String(255), nullable=False),
        sa.Column("endpoint", sa.String(255), nullable=False),
        sa.Column("method", sa.String(10), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("response_status", sa.Integer(), nullable=True),
    )

    # Index for access_logs
    op.create_index("idx_access_logs_timestamp", "access_logs", ["timestamp"])

    # --- Workflow Executions ---
    op.create_table(
        "workflow_executions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("processed_emails.id", ondelete="CASCADE"), nullable=False),
        sa.Column("current_stage", sa.String(30), nullable=False),
        sa.Column("retry_counts", postgresql.JSONB(), server_default="{}"),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Drop all tables."""
    op.drop_table("workflow_executions")
    op.drop_table("access_logs")
    op.drop_index("idx_drafts_email", table_name="draft_replies")
    op.drop_index("idx_drafts_status", table_name="draft_replies")
    op.drop_table("draft_replies")
    op.drop_index("idx_emails_provider_msg_id", table_name="processed_emails")
    op.drop_index("idx_emails_flagged", table_name="processed_emails")
    op.drop_index("idx_emails_priority", table_name="processed_emails")
    op.drop_index("idx_emails_category", table_name="processed_emails")
    op.drop_index("idx_emails_user_timestamp", table_name="processed_emails")
    op.drop_table("processed_emails")
    op.drop_table("connected_accounts")
    op.drop_table("users")
