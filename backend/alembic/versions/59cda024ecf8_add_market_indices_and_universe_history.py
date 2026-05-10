"""add market_indices and universe_history tables (07번 §3·§14 / 14번 §3-4 / 06번 §6·§14)

KOSPI/KOSDAQ/KOSPI200 등 시장 지수 일봉 + 백테스트 시점별 universe 스냅샷.

신규 테이블:
1. market_indices (07번 §3, 14번 §3-4)
   - id (PK)
   - index_code (KOSPI/KOSDAQ/KOSPI200/KOSDAQ150/KRX100)
   - date
   - open / high / low / volume / change_pct (NULL 허용)
   - close (NOT NULL — 지수 자체값)
   - created_at
   UniqueConstraint(index_code, date)
   Index(index_code, date)

2. universe_history (07번 §14, 06번 §14)
   - id (PK)
   - as_of_date
   - market
   - selection_method (06번 §9 enum)
   - config_json (재현용)
   - config_hash (UniqueConstraint 키)
   - symbols_json (선정 종목 리스트 — symbol ASC)
   - run_id (FK → backtest_runs.id, ON DELETE SET NULL, NULL 허용 — preview 스냅샷용)
   - created_at
   UniqueConstraint(as_of_date, market, selection_method, config_hash)
   Index(as_of_date), Index(run_id)

13.13 / 14.10 정합:
   - universe_history는 그 시점에 살아있던 종목 리스트를 그대로 보존 → 생존편향 없는 재현.

13.15 정합:
   - universe 선정 시점 정보만 보존 → 미래 데이터 누설 0.

NOTE — 9a4d2e1f6c10 / c7f2a16d8b53과 동일하게 SQLite alembic의 silent skip 회피를 위해
       raw DDL을 `bind.exec_driver_sql`로 실행. dev/test의 init_db는 ORM metadata가
       모든 테이블을 생성하므로 영향 없음.

Revision ID: 59cda024ecf8
Revises: c7f2a16d8b53
Create Date: 2026-05-10 19:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "59cda024ecf8"
down_revision: str | Sequence[str] | None = "c7f2a16d8b53"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()

    # 1) market_indices
    bind.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS market_indices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            index_code VARCHAR(30) NOT NULL,
            date DATE NOT NULL,
            open FLOAT,
            high FLOAT,
            low FLOAT,
            close FLOAT NOT NULL,
            volume FLOAT,
            change_pct FLOAT,
            created_at DATETIME NOT NULL,
            CONSTRAINT uq_market_indices_code_date
                UNIQUE (index_code, date)
        )
        """
    )
    bind.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_market_indices_code_date "
        "ON market_indices(index_code, date)"
    )

    # 2) universe_history
    bind.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS universe_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            as_of_date DATE NOT NULL,
            market VARCHAR(20) NOT NULL,
            selection_method VARCHAR(40) NOT NULL,
            config_json JSON NOT NULL,
            config_hash VARCHAR(64),
            symbols_json JSON NOT NULL,
            run_id INTEGER REFERENCES backtest_runs(id) ON DELETE SET NULL,
            created_at DATETIME NOT NULL,
            CONSTRAINT uq_universe_history_date_market_method_hash
                UNIQUE (as_of_date, market, selection_method, config_hash)
        )
        """
    )
    bind.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_universe_history_as_of_date "
        "ON universe_history(as_of_date)"
    )
    bind.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_universe_history_run_id "
        "ON universe_history(run_id)"
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.exec_driver_sql("DROP INDEX IF EXISTS ix_universe_history_run_id")
    bind.exec_driver_sql("DROP INDEX IF EXISTS ix_universe_history_as_of_date")
    bind.exec_driver_sql("DROP TABLE IF EXISTS universe_history")
    bind.exec_driver_sql("DROP INDEX IF EXISTS ix_market_indices_code_date")
    bind.exec_driver_sql("DROP TABLE IF EXISTS market_indices")


# noqa: F401 — sa는 향후 컬럼 타입 명시를 위해 보존 (이전 마이그레이션 패턴 일치)
_ = sa
