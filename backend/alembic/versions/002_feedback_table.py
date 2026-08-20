"""Adiciona tabela de feedback para aprendizado por approve/reject.

Revision ID: 002_feedback
Revises: 001_initial_schema
Create Date: 2026-07-14
"""
from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "classification_feedback",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        # E-mail que gerou o feedback
        sa.Column("email_subject", sa.Text(), nullable=False),
        sa.Column("email_body_snippet", sa.Text(), nullable=True),  # primeiros 500 chars
        sa.Column("email_sender", sa.String(255), nullable=True),
        # Classificação que a IA produziu
        sa.Column("predicted_category", sa.String(30), nullable=False),
        sa.Column("predicted_priority", sa.String(10), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        # Feedback do humano: "approved" ou "rejected"
        sa.Column("feedback", sa.String(20), nullable=False),
        # Se rejeitou e corrigiu manualmente
        sa.Column("correct_category", sa.String(30), nullable=True),
        sa.Column("correct_priority", sa.String(10), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("idx_feedback_category", "classification_feedback", ["predicted_category"])
    op.create_index("idx_feedback_feedback", "classification_feedback", ["feedback"])


def downgrade() -> None:
    op.drop_index("idx_feedback_feedback", table_name="classification_feedback")
    op.drop_index("idx_feedback_category", table_name="classification_feedback")
    op.drop_table("classification_feedback")
