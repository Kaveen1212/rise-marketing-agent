"""Chat sessions, chat messages, and poster images

Revision ID: 002_chat_and_images
Revises: 001_initial
Create Date: 2026-04-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002_chat_and_images"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'image_source_enum') THEN
                CREATE TYPE image_source_enum AS ENUM ('upload', 'generated', 'approved', 'rejected');
            END IF;
        END $$;
    """)

    op.create_table(
        "poster_images",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("filename", sa.String(300), nullable=False),
        sa.Column("storage_path", sa.String(500), nullable=False),
        sa.Column("url", sa.String(1000), nullable=False),
        sa.Column("size_bytes", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column(
            "source",
            postgresql.ENUM(
                "upload", "generated", "approved", "rejected",
                name="image_source_enum",
                create_type=False,
            ),
            nullable=False,
            index=True,
        ),
        sa.Column("caption", sa.Text, nullable=True),
        sa.Column("platform", sa.String(40), nullable=True),
        sa.Column("platforms", postgresql.ARRAY(sa.Text), nullable=True),
        sa.Column("scheduled_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("session_id", sa.String(100), nullable=True, index=True),
        sa.Column("prompt", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.String(100), primary_key=True),
        sa.Column("status", sa.String(40), nullable=False, server_default="chat"),
        sa.Column("brief", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "chat_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(100),
            sa.ForeignKey("chat_sessions.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("image_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("image_url", sa.String(1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("chat_messages")
    op.drop_table("chat_sessions")
    op.drop_table("poster_images")
    op.execute("DROP TYPE IF EXISTS image_source_enum")
