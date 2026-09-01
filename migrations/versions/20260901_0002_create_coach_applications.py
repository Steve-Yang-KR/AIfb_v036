"""Create coach applications table.

Revision ID: 20260901_0002
Revises: 20260901_0001
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260901_0002"
down_revision: Union[str, Sequence[str], None] = "20260901_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("coach_applications"):
        return
    op.create_table(
        "coach_applications",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("full_name", sa.String(length=120), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("country", sa.String(length=120), nullable=False),
        sa.Column("home_address", sa.String(length=500), nullable=False),
        sa.Column("native_language", sa.String(length=120), nullable=False),
        sa.Column("coaching_languages", sa.String(length=300), nullable=False),
        sa.Column("qualification", sa.String(length=300), nullable=False),
        sa.Column("years_coaching", sa.Integer(), nullable=False),
        sa.Column("coaching_context", sa.Text(), nullable=False),
        sa.Column("development_example", sa.Text(), nullable=False),
        sa.Column("triadic_mindset", sa.Text(), nullable=False),
        sa.Column("readiness", sa.Text(), nullable=False),
        sa.Column("pilot_availability", sa.String(length=80), nullable=False),
        sa.Column("primary_region", sa.String(length=80), nullable=False),
        sa.Column("evidence_links", sa.Text(), nullable=False),
        sa.Column("consent_ready", sa.Boolean(), nullable=False),
        sa.Column("credential_filename", sa.String(length=255), nullable=True),
        sa.Column("credential_content_type", sa.String(length=120), nullable=True),
        sa.Column("credential_size", sa.Integer(), nullable=True),
        sa.Column("credential_data", sa.LargeBinary(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_coach_applications_status"), "coach_applications", ["status"], unique=False)
    op.create_index(op.f("ix_coach_applications_user_id"), "coach_applications", ["user_id"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_coach_applications_user_id"), table_name="coach_applications")
    op.drop_index(op.f("ix_coach_applications_status"), table_name="coach_applications")
    op.drop_table("coach_applications")
