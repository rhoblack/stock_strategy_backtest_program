"""add corporate_actions table (07번 §12-B / 14번 §15)

분할/병합/배당/유증 등 권리 이력 보존. 신규 corporate_action 수집 시 영향 종목의
수정주가를 과거 전체 재계산 (14.9, 13.7).

신규 테이블: corporate_actions
  - id (PK)
  - symbol (FK → symbols.symbol, ON DELETE CASCADE)
  - event_date
  - event_type (split/cash_dividend/bonus_issue/rights_issue/merger/spinoff/delisting/reverse_split)
  - ratio (분할/병합/유증 비율 — cash_dividend 외에 사용)
  - dividend_amount (cash_dividend 주당 배당금)
  - notes
  - created_at

UniqueConstraint(symbol, event_date, event_type) — 동일 일자에 split + cash_dividend 동시 가능.
인덱스 (symbol, event_date) — AdjustedPriceProcessor가 종목별 조회.

13.13 / 14.10 정합성: symbols.delisting_date가 단일 출처. corporate_actions의
event_type='delisting' row는 참고용.

NOTE — 9a4d2e1f6c10 / b5e8d3c1a924와 동일하게 SQLite alembic의 silent skip 회피를 위해
       raw DDL을 `bind.exec_driver_sql`로 실행. dev/test의 init_db는 ORM metadata가
       모든 테이블을 생성하므로 영향 없으며, 운용 alembic 적용 시에도 raw DDL이 결정적으로 실행된다.

Revision ID: c7f2a16d8b53
Revises: b5e8d3c1a924
Create Date: 2026-05-10 18:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c7f2a16d8b53"
down_revision: str | Sequence[str] | None = "b5e8d3c1a924"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()

    bind.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS corporate_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol VARCHAR(20) NOT NULL REFERENCES symbols(symbol) ON DELETE CASCADE,
            event_date DATE NOT NULL,
            event_type VARCHAR(30) NOT NULL,
            ratio FLOAT NOT NULL DEFAULT 0.0,
            dividend_amount FLOAT,
            notes VARCHAR(500),
            created_at DATETIME NOT NULL,
            CONSTRAINT uq_corporate_actions_symbol_date_type
                UNIQUE (symbol, event_date, event_type)
        )
        """
    )
    bind.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_corporate_actions_symbol_event_date "
        "ON corporate_actions(symbol, event_date)"
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.exec_driver_sql("DROP INDEX IF EXISTS ix_corporate_actions_symbol_event_date")
    bind.exec_driver_sql("DROP TABLE IF EXISTS corporate_actions")


# noqa: F401 — sa는 향후 컬럼 타입 명시를 위해 보존 (cash_events / market_data 마이그레이션 패턴 일치)
_ = sa
