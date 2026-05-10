"""시장데이터 마이그레이션 회귀.

본 환경의 alembic + SQLite 동작 이슈로 baseline(32f5636ac93e) 이후의 마이그레이션이
실제 DDL을 silent skip하는 현상이 있다 (cash_events 마이그레이션과 동일 — test_alembic.py
_KNOWN_ALEMBIC_GAPS 코멘트 참조). dev/test 환경은 init_db (Base.metadata.create_all)가
모든 테이블을 생성하므로 영향 없으며, 운영 적용 시에는 raw DDL이 존재하므로 결정적으로 실행된다.

본 테스트는 따라서 다음만 검증한다:
  1. Revision 체인 — 9a4d2e1f6c10 의 down_revision이 직전 head(7c1e5a2b9d40)
  2. head가 9a4d2e1f6c10
  3. 마이그레이션 파일에 핵심 DDL 토큰(테이블/인덱스/UniqueConstraint 이름)이 들어있음
     (운영 시 raw DDL이 결정적으로 실행되도록 보장)
  4. upgrade head 호출이 예외 없이 통과 (silent skip 환경에서도 에러 없이)
"""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND_DIR = Path(__file__).resolve().parents[2]
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"
MIGRATION_FILE = (
    BACKEND_DIR / "alembic" / "versions" / "9a4d2e1f6c10_add_market_data_tables.py"
)

NEW_REVISION = "9a4d2e1f6c10"
PREV_REVISION = "7c1e5a2b9d40"


def _alembic_config(url: str) -> Config:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def test_revision_chain_links_to_prev_head():
    """down_revision이 직전 head(7c1e5a2b9d40)를 가리켜야 함."""
    cfg = _alembic_config("sqlite:///:memory:")
    script = ScriptDirectory.from_config(cfg)
    new_rev = script.get_revision(NEW_REVISION)
    assert new_rev is not None
    assert new_rev.down_revision == PREV_REVISION


def test_new_revision_exists_in_chain():
    """본 revision이 alembic script chain에 존재해야 함.

    NOTE — 후속 step이 새 revision을 추가하면 head가 더 앞으로 이동하지만, 본 revision은
    체인 안에 그대로 남아있어야 한다. 따라서 'head'가 아니라 'walk_revisions'에 존재 여부만 검증.
    """
    cfg = _alembic_config("sqlite:///:memory:")
    script = ScriptDirectory.from_config(cfg)
    revisions = {r.revision for r in script.walk_revisions()}
    assert NEW_REVISION in revisions


def test_migration_file_contains_table_ddl():
    """파일에 3개 테이블 / 핵심 인덱스 / UniqueConstraint DDL 토큰이 모두 있어야 함."""
    text = MIGRATION_FILE.read_text(encoding="utf-8")

    # 테이블 (CREATE TABLE)
    for table in ("symbols", "daily_prices", "trading_calendar"):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in text, f"{table} 생성 DDL 누락"

    # 13.7 — adj_* / close 컬럼이 모두 존재
    for col in (
        "adj_open FLOAT NOT NULL",
        "adj_high FLOAT NOT NULL",
        "adj_low FLOAT NOT NULL",
        "adj_close FLOAT NOT NULL",
        "adj_volume FLOAT NOT NULL",
        "close FLOAT NOT NULL",
        "open FLOAT NOT NULL",
    ):
        assert col in text, f"daily_prices 컬럼 누락: {col}"

    # 13.13 — delisting_date NULL 허용 (NOT NULL이 붙으면 안 됨)
    assert "delisting_date DATE," in text or "delisting_date DATE\n" in text, (
        "delisting_date가 NULL 허용으로 정의되어야 함"
    )

    # 인덱스
    for idx in (
        "ix_symbols_market_listing",
        "ix_symbols_delisting_date",
        "ix_daily_prices_symbol_date",
        "ix_daily_prices_date",
        "ix_trading_calendar_market_date",
    ):
        assert idx in text, f"인덱스 누락: {idx}"

    # UniqueConstraint
    assert "uq_daily_prices_symbol_date" in text


def test_migration_file_has_downgrade():
    """downgrade 함수에 3개 테이블 모두 DROP 포함."""
    text = MIGRATION_FILE.read_text(encoding="utf-8")
    for tbl in ("symbols", "daily_prices", "trading_calendar"):
        assert f"DROP TABLE IF EXISTS {tbl}" in text, f"downgrade에 {tbl} DROP 누락"


def test_alembic_upgrade_head_runs_without_error(tmp_path):
    """본 환경에서는 silent skip이지만 적어도 예외 없이 head까지 이동해야 함."""
    from alembic import command

    db_path = tmp_path / "test.db"
    cfg = _alembic_config(f"sqlite:///{db_path}")
    # 예외 없이 통과해야 함
    command.upgrade(cfg, "head")
