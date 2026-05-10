"""add cash_events cost breakdown columns

CashEvent 모델에 강제 매도 비용 분해 컬럼 추가 (014 / 리뷰 011 C2 영속화):
exec_price, raw_price, gross_amount, fee, tax, net_amount.

기존 sell_amount는 호환을 위해 유지하되, net_amount과 동일한 값을 채운다.

Revision ID: 7c1e5a2b9d40
Revises: 3b7a97e6378c
Create Date: 2026-05-10 09:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "7c1e5a2b9d40"
down_revision: str | Sequence[str] | None = "3b7a97e6378c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    # SQLite는 ADD COLUMN을 지원 (NULL 허용 컬럼이므로 기본값 불필요).
    bind.exec_driver_sql("ALTER TABLE cash_events ADD COLUMN exec_price FLOAT")
    bind.exec_driver_sql("ALTER TABLE cash_events ADD COLUMN raw_price FLOAT")
    bind.exec_driver_sql("ALTER TABLE cash_events ADD COLUMN gross_amount FLOAT")
    bind.exec_driver_sql("ALTER TABLE cash_events ADD COLUMN fee FLOAT")
    bind.exec_driver_sql("ALTER TABLE cash_events ADD COLUMN tax FLOAT")
    bind.exec_driver_sql("ALTER TABLE cash_events ADD COLUMN net_amount FLOAT")


def downgrade() -> None:
    # SQLite는 DROP COLUMN을 3.35+에서만 지원. batch_alter_table로 안전하게 제거.
    with op.batch_alter_table("cash_events", schema=None) as batch_op:
        batch_op.drop_column("net_amount")
        batch_op.drop_column("tax")
        batch_op.drop_column("fee")
        batch_op.drop_column("gross_amount")
        batch_op.drop_column("raw_price")
        batch_op.drop_column("exec_price")


# noqa: F401 — sa는 향후 컬럼 타입 명시를 위해 보존
_ = sa
