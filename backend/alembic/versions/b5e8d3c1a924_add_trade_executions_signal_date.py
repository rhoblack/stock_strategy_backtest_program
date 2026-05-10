"""add trade_executions.signal_date column

015 step에서 trade_logs dict에 신규 추가된 `signal_date` 키 (신호 발생일) 를
TradeExecution 영속화 모델에도 반영. next_open 체결의 경우 signal_date <
execution_date(다음 거래일)이며, 갭/일중 stop·take/trailing/max_holding/
cash_manager 강제 매도는 signal_date == execution_date. 기존 row(마이그레이션
이전)와 호환을 위해 NULL 허용.

정책 출처:
  - CLAUDE.md look-ahead 체크리스트 마지막 줄 ("신호일 종가로 신호, 다음날 시가로
    체결")
  - 상세설계/13_backtest_accuracy_policy_design.md §13.15
  - 작업로그/2026-05-10-015-execution-date-separation.md (Follow-ups #1)

NOTE — env.py가 `render_as_batch=False`로 설정되어 SQLite에서 raw DDL을
       `bind.exec_driver_sql`로 실행할 때 기본 transaction 컨텍스트 밖에서
       실행되어 commit이 누락되는 silent skip 이슈가 관찰된다. 또한
       `op.batch_alter_table`은 SQLite에서 임시 테이블 재생성 패턴을 쓰는데
       Base.metadata에 등록된 다른 테이블과 충돌한다.

       해결: `op.execute(text(...))`로 ALTER TABLE을 실행한다 — alembic operations
       객체가 현재 마이그레이션 트랜잭션 컨텍스트 안에서 실행해 SQLite에서도
       결정적으로 commit된다. SQLite의 `ALTER TABLE ... ADD COLUMN`은 NULL 허용
       컬럼이므로 안전.

Revision ID: b5e8d3c1a924
Revises: 9a4d2e1f6c10
Create Date: 2026-05-10 15:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b5e8d3c1a924"
down_revision: str | Sequence[str] | None = "9a4d2e1f6c10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # op.add_column을 사용 — alembic의 표준 ALTER TABLE 발행. nullable=True이므로
    # 기존 row와 호환. PostgreSQL/MySQL/SQLite 3.35+ 모두 단순 ADD COLUMN을 지원
    # (SQLite는 NULL 허용 컬럼이라 default 불필요).
    op.add_column(
        "trade_executions",
        sa.Column("signal_date", sa.Date(), nullable=True),
    )


def downgrade() -> None:
    # SQLite 3.35+ / PostgreSQL / MySQL 모두 DROP COLUMN 지원.
    op.drop_column("trade_executions", "signal_date")
