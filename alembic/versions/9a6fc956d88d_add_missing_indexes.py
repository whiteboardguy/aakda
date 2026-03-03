"""add_missing_indexes

Revision ID: 9a6fc956d88d
Revises: 0e1c3ee7bed0
Create Date: 2026-03-03 17:23:21.360254

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9a6fc956d88d"
down_revision: Union[str, Sequence[str], None] = "0e1c3ee7bed0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # conversations(user_uid) — speeds up all per-user conversation queries
    op.create_index("ix_conversations_user_uid", "conversations", ["user_uid"])

    # conversations(shared_link) partial — speeds up shared-link lookups
    op.create_index(
        "ix_conversations_shared_link",
        "conversations",
        ["shared_link"],
        postgresql_where=sa.text("shared_link IS NOT NULL"),
    )

    # sessions(user_uid) — speeds up session validation and purge queries
    op.create_index("ix_sessions_user_uid", "sessions", ["user_uid"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_sessions_user_uid", table_name="sessions")
    op.drop_index("ix_conversations_shared_link", table_name="conversations")
    op.drop_index("ix_conversations_user_uid", table_name="conversations")
