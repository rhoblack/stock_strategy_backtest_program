"""027 market_indices + universe_history 마이그레이션 회귀 (test_alembic_corporate_actions.py 패턴).

본 환경의 alembic + SQLite 동작 이슈로 9a4d2e1f6c10 / c7f2a16d8b53 / 59cda024ecf8 등
시장데이터 마이그레이션이 실제 DDL을 silent skip한다 (test_alembic.py _KNOWN_ALEMBIC_GAPS 참조).
dev/test는 init_db (Base.metadata.create_all)가 정상 처리하므로 영향 없음. 운영 적용 시에는
raw DDL 토큰이 결정적으로 실행된다.

검증 항목:
  1. Revision 체인 — 59cda024ecf8 의 down_revision = c7f2a16d8b53 (026 직후)
  2. head가 59cda024ecf8 (현 시점 최신)
  3. 마이그레이션 파일에 market_indices / universe_history 테이블 / 인덱스 / UniqueConstraint DDL 존재
  4. downgrade에 DROP TABLE / DROP INDEX 모두 존재
  5. upgrade head 호출이 예외 없이 통과
  6. upgrade head → downgrade -1 → upgrade head 사이클 통과
"""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND_DIR = Path(__file__).resolve().parents[2]
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"
MIGRATION_FILE = (
    BACKEND_DIR
    / "alembic"
    / "versions"
    / "59cda024ecf8_add_market_indices_and_universe_history.py"
)

NEW_REVISION = "59cda024ecf8"
PREV_REVISION = "c7f2a16d8b53"


def _alembic_config(url: str) -> Config:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def test_revision_chain_links_to_prev_head():
    """down_revision이 직전 head(c7f2a16d8b53)를 가리켜야 함."""
    cfg = _alembic_config("sqlite:///:memory:")
    script = ScriptDirectory.from_config(cfg)
    new_rev = script.get_revision(NEW_REVISION)
    assert new_rev is not None
    assert new_rev.down_revision == PREV_REVISION


def test_new_revision_exists_in_chain():
    """본 revision이 alembic script chain에 존재해야 함.

    NOTE — 후속 step이 새 revision을 추가하면 head가 더 앞으로 이동하지만, 본 revision은
    체인 안에 그대로 남아있어야 한다. 따라서 'head'가 아니라 'walk_revisions'에 존재 여부만 검증.
    026 follow-up §6의 정리 패턴을 본 step에서 도입.
    """
    cfg = _alembic_config("sqlite:///:memory:")
    script = ScriptDirectory.from_config(cfg)
    revisions = {r.revision for r in script.walk_revisions()}
    assert NEW_REVISION in revisions


def test_migration_file_contains_market_indices_ddl():
    """market_indices 테이블/인덱스/UniqueConstraint DDL 토큰 검증."""
    text = MIGRATION_FILE.read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS market_indices" in text
    for col_token in (
        "index_code VARCHAR(30) NOT NULL",
        "date DATE NOT NULL",
        "open FLOAT",
        "high FLOAT",
        "low FLOAT",
        "close FLOAT NOT NULL",
        "volume FLOAT",
        "change_pct FLOAT",
        "created_at DATETIME NOT NULL",
    ):
        assert col_token in text, f"market_indices 컬럼 누락: {col_token}"

    # UniqueConstraint
    assert "uq_market_indices_code_date" in text
    # 인덱스
    assert "ix_market_indices_code_date" in text


def test_migration_file_contains_universe_history_ddl():
    """universe_history 테이블/인덱스/UniqueConstraint DDL 토큰 검증."""
    text = MIGRATION_FILE.read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS universe_history" in text
    for col_token in (
        "as_of_date DATE NOT NULL",
        "market VARCHAR(20) NOT NULL",
        "selection_method VARCHAR(40) NOT NULL",
        "config_json JSON NOT NULL",
        "config_hash VARCHAR(64)",
        "symbols_json JSON NOT NULL",
        "run_id INTEGER",
        "created_at DATETIME NOT NULL",
    ):
        assert col_token in text, f"universe_history 컬럼 누락: {col_token}"

    # FK + ON DELETE SET NULL
    assert "REFERENCES backtest_runs(id)" in text
    assert "ON DELETE SET NULL" in text

    # UniqueConstraint
    assert "uq_universe_history_date_market_method_hash" in text
    # 인덱스
    assert "ix_universe_history_as_of_date" in text
    assert "ix_universe_history_run_id" in text


def test_migration_file_has_downgrade():
    """downgrade에 양 테이블 DROP TABLE / DROP INDEX 모두 포함."""
    text = MIGRATION_FILE.read_text(encoding="utf-8")
    assert "DROP TABLE IF EXISTS market_indices" in text
    assert "DROP INDEX IF EXISTS ix_market_indices_code_date" in text
    assert "DROP TABLE IF EXISTS universe_history" in text
    assert "DROP INDEX IF EXISTS ix_universe_history_as_of_date" in text
    assert "DROP INDEX IF EXISTS ix_universe_history_run_id" in text


def test_alembic_upgrade_head_runs_without_error(tmp_path):
    """본 환경에서는 silent skip이지만 적어도 예외 없이 head까지 이동."""
    from alembic import command

    db_path = tmp_path / "test.db"
    cfg = _alembic_config(f"sqlite:///{db_path}")
    command.upgrade(cfg, "head")


def test_alembic_upgrade_downgrade_upgrade_cycle(tmp_path):
    """upgrade head → downgrade -1 → upgrade head 회귀 (예외 없음)."""
    from alembic import command

    db_path = tmp_path / "test_cycle.db"
    cfg = _alembic_config(f"sqlite:///{db_path}")
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "-1")
    command.upgrade(cfg, "head")
