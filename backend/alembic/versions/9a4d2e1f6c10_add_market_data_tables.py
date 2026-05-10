"""add market_data tables (symbols / daily_prices / trading_calendar)

시장데이터 트랙 1단계 (외부 CR-002 + 4.6 + 4.7).

신규 테이블 3종:
  - symbols              : 종목 마스터 (07번 §11 / 06번 §6)
  - daily_prices         : 일봉 (07번 §12 / 06번 §7 / 13번 §7 수정주가 정책)
  - trading_calendar     : 거래일 캘린더 (07번 §12-A / 14번 §14 / 13번 §11)

13.13 / 14.10 생존편향 정책: symbols.delisting_date NULL 허용 (폐지 종목도 보존).
13.7 수정주가 정책: daily_prices.close + adj_close 모두 NOT NULL.
14.10 결손 정책: daily_prices에 결손 봉 row를 만들지 않음 (forward-fill 금지).
                 거래일 여부는 trading_calendar로만 판단.

NOTE — env.py가 `render_as_batch=False`로 동작하면서 `op.create_table`이
       SQLite + 일부 환경에서 silent skip되는 이슈가 있다 (cash_events와 동일 증상).
       cash_events 마이그레이션 패턴을 따라 `bind.exec_driver_sql`로 raw DDL을 직접 실행.
       Base.metadata는 정상이므로 dev/test의 init_db는 영향 없으며,
       프로덕션 alembic 적용 시에도 raw DDL이 결정적으로 실행된다.

Revision ID: 9a4d2e1f6c10
Revises: 7c1e5a2b9d40
Create Date: 2026-05-10 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "9a4d2e1f6c10"
down_revision: str | Sequence[str] | None = "7c1e5a2b9d40"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()

    # 1) symbols (종목 마스터)
    bind.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS symbols (
            symbol VARCHAR(20) PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            market VARCHAR(20) NOT NULL,
            sector VARCHAR(100),
            listing_date DATE NOT NULL,
            delisting_date DATE,
            is_etf BOOLEAN NOT NULL,
            is_etn BOOLEAN NOT NULL,
            is_spac BOOLEAN NOT NULL,
            is_preferred BOOLEAN NOT NULL,
            is_managed BOOLEAN NOT NULL,
            is_halted BOOLEAN NOT NULL,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL
        )
        """
    )
    bind.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_symbols_market_listing "
        "ON symbols(market, listing_date)"
    )
    bind.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_symbols_delisting_date "
        "ON symbols(delisting_date)"
    )

    # 2) daily_prices (일봉) — FK symbols.symbol, ON DELETE CASCADE
    bind.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS daily_prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol VARCHAR(20) NOT NULL REFERENCES symbols(symbol) ON DELETE CASCADE,
            date DATE NOT NULL,
            open FLOAT NOT NULL,
            high FLOAT NOT NULL,
            low FLOAT NOT NULL,
            close FLOAT NOT NULL,
            volume FLOAT NOT NULL,
            adj_open FLOAT NOT NULL,
            adj_high FLOAT NOT NULL,
            adj_low FLOAT NOT NULL,
            adj_close FLOAT NOT NULL,
            adj_volume FLOAT NOT NULL,
            market_cap FLOAT,
            created_at DATETIME NOT NULL,
            CONSTRAINT uq_daily_prices_symbol_date UNIQUE (symbol, date)
        )
        """
    )
    bind.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_daily_prices_symbol_date "
        "ON daily_prices(symbol, date)"
    )
    bind.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_daily_prices_date ON daily_prices(date)"
    )

    # 3) trading_calendar — 복합 PK (date, market)
    bind.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS trading_calendar (
            date DATE NOT NULL,
            market VARCHAR(20) NOT NULL,
            is_trading_day BOOLEAN NOT NULL,
            holiday_name VARCHAR(100),
            created_at DATETIME NOT NULL,
            PRIMARY KEY (date, market)
        )
        """
    )
    bind.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_trading_calendar_market_date "
        "ON trading_calendar(market, date)"
    )


def downgrade() -> None:
    bind = op.get_bind()
    # 역순 drop (FK 의존: daily_prices → symbols)
    bind.exec_driver_sql("DROP INDEX IF EXISTS ix_trading_calendar_market_date")
    bind.exec_driver_sql("DROP TABLE IF EXISTS trading_calendar")

    bind.exec_driver_sql("DROP INDEX IF EXISTS ix_daily_prices_date")
    bind.exec_driver_sql("DROP INDEX IF EXISTS ix_daily_prices_symbol_date")
    bind.exec_driver_sql("DROP TABLE IF EXISTS daily_prices")

    bind.exec_driver_sql("DROP INDEX IF EXISTS ix_symbols_delisting_date")
    bind.exec_driver_sql("DROP INDEX IF EXISTS ix_symbols_market_listing")
    bind.exec_driver_sql("DROP TABLE IF EXISTS symbols")


# noqa: F401 — sa는 향후 컬럼 타입 명시를 위해 보존
_ = sa
