"""026 corporate_actions 마이그레이션 회귀 (test_alembic_market_data.py와 동일 패턴).

본 환경의 alembic + SQLite 동작 이슈로 9a4d2e1f6c10 / c7f2a16d8b53 마이그레이션이
실제 DDL을 silent skip한다 (test_alembic.py _KNOWN_ALEMBIC_GAPS 참조). dev/test는
init_db (Base.metadata.create_all)가 정상 처리하므로 영향 없음. 운영 적용 시에는
raw DDL 토큰이 결정적으로 실행된다.

검증 항목:
  1. Revision 체인 — c7f2a16d8b53 의 down_revision = b5e8d3c1a924 (017 직후)
  2. head가 c7f2a16d8b53 (현 시점 최신)
  3. 마이그레이션 파일에 corporate_actions 테이블/인덱스/UniqueConstraint DDL 존재
  4. downgrade에 DROP TABLE corporate_actions 존재
  5. upgrade head 호출이 예외 없이 통과 (silent skip 환경에서도 예외 없음)
"""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND_DIR = Path(__file__).resolve().parents[2]
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"
MIGRATION_FILE = (
    BACKEND_DIR / "alembic" / "versions" / "c7f2a16d8b53_add_corporate_actions.py"
)

NEW_REVISION = "c7f2a16d8b53"
PREV_REVISION = "b5e8d3c1a924"


def _alembic_config(url: str) -> Config:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def test_revision_chain_links_to_prev_head():
    """down_revision이 직전 head(b5e8d3c1a924)를 가리켜야 함."""
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
    """corporate_actions 테이블/인덱스/UniqueConstraint DDL 토큰 검증."""
    text = MIGRATION_FILE.read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS corporate_actions" in text
    # 컬럼 (07번 §12-B / 14번 §15)
    for col_token in (
        "symbol VARCHAR(20) NOT NULL",
        "event_date DATE NOT NULL",
        "event_type VARCHAR(30) NOT NULL",
        "ratio FLOAT NOT NULL",
        "dividend_amount FLOAT",
        "notes VARCHAR(500)",
        "created_at DATETIME NOT NULL",
    ):
        assert col_token in text, f"corporate_actions 컬럼 누락: {col_token}"

    # FK
    assert "REFERENCES symbols(symbol)" in text
    assert "ON DELETE CASCADE" in text

    # UniqueConstraint
    assert "uq_corporate_actions_symbol_date_type" in text
    # 인덱스
    assert "ix_corporate_actions_symbol_event_date" in text


def test_migration_file_has_downgrade():
    """downgrade에 DROP TABLE / DROP INDEX 모두 포함."""
    text = MIGRATION_FILE.read_text(encoding="utf-8")
    assert "DROP TABLE IF EXISTS corporate_actions" in text
    assert "DROP INDEX IF EXISTS ix_corporate_actions_symbol_event_date" in text


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
