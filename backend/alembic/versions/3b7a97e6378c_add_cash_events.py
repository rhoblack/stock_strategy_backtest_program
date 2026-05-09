"""add cash_events

Revision ID: 3b7a97e6378c
Revises: 32f5636ac93e
Create Date: 2026-05-10 06:03:09.955623

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "3b7a97e6378c"
down_revision: Union[str, Sequence[str], None] = "32f5636ac93e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.exec_driver_sql("""
        CREATE TABLE IF NOT EXISTS cash_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL REFERENCES backtest_runs(id) ON DELETE CASCADE,
            date DATE NOT NULL,
            event_type VARCHAR(50) NOT NULL,
            cash_before FLOAT NOT NULL,
            required_cash FLOAT,
            cash_after FLOAT NOT NULL,
            action VARCHAR(50),
            symbol VARCHAR(20),
            sell_quantity INTEGER,
            sell_amount FLOAT,
            reason TEXT,
            created_at DATETIME NOT NULL
        )
    """)
    bind.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_cash_events_run_id ON cash_events(run_id)")
    bind.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_cash_events_date ON cash_events(date)")


def downgrade() -> None:
    bind = op.get_bind()
    bind.exec_driver_sql("DROP INDEX IF EXISTS ix_cash_events_date")
    bind.exec_driver_sql("DROP INDEX IF EXISTS ix_cash_events_run_id")
    bind.exec_driver_sql("DROP TABLE IF EXISTS cash_events")


# noqa: F401 — sa는 향후 컬럼 타입 명시를 위해 보존
_ = sa
