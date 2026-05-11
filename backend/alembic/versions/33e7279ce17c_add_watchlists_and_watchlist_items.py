"""add watchlists and watchlist_items

Revision ID: 33e7279ce17c
Revises: d9f3b2a7e041
Create Date: 2026-05-11 09:47:29.081444

07번 §13 watchlists 설계 / 10번 5-t절 관심종목 API.
watchlists (user_id FK → users.id) + watchlist_items (watchlist_id FK → watchlists.id) 추가.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "33e7279ce17c"
down_revision: str | Sequence[str] | None = "d9f3b2a7e041"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """watchlists + watchlist_items 테이블 생성."""
    op.create_table(
        "watchlists",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_watchlists_user_id", "watchlists", ["user_id"], unique=False)

    op.create_table(
        "watchlist_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("watchlist_id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["watchlist_id"], ["watchlists.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_watchlist_items_watchlist_id", "watchlist_items", ["watchlist_id"], unique=False
    )
    op.create_index(
        "ix_watchlist_items_wl_sym", "watchlist_items", ["watchlist_id", "symbol"], unique=True
    )


def downgrade() -> None:
    """watchlist_items + watchlists 테이블 제거."""
    op.drop_index("ix_watchlist_items_wl_sym", table_name="watchlist_items")
    op.drop_index("ix_watchlist_items_watchlist_id", table_name="watchlist_items")
    op.drop_table("watchlist_items")
    op.drop_index("ix_watchlists_user_id", table_name="watchlists")
    op.drop_table("watchlists")
