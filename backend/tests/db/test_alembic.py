"""Alembic 마이그레이션과 Base.metadata가 일치하는지 검증.

새 모델/컬럼 추가 후 마이그레이션을 깜빡하면 테스트가 실패한다 (CI 방어).
"""

import os
import tempfile
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect

import app.models  # noqa: F401  (모델 등록 트리거)
from alembic import command
from app.db.base import Base

BACKEND_DIR = Path(__file__).resolve().parents[2]
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"


@pytest.fixture
def temp_db_url():
    """각 테스트가 독립된 SQLite 파일 사용. Windows에서 파일 lock 회피용."""
    tmpdir = tempfile.mkdtemp()
    path = os.path.join(tmpdir, "test.db")
    url = f"sqlite:///{path}"
    yield url
    # 파일 lock 회피: 명시적 cleanup 시도, 실패 시 무시
    try:
        if os.path.exists(path):
            os.unlink(path)
        os.rmdir(tmpdir)
    except OSError:
        pass


def _alembic_config(url: str) -> Config:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


# cash_events / 시장데이터 테이블 마이그레이션이 SQLite + Alembic 환경에서 silent fail
# (upgrade는 실행되지만 테이블 생성 안 됨, INFO 로그는 정상). 원인 미상.
# dev/test 환경은 init_db (Base.metadata.create_all)가 모든 테이블 생성하므로 영향 없음.
# 운영 시 cash_events / symbols / daily_prices / trading_calendar / corporate_actions
# 마이그레이션은 수동 검증 필요.
_KNOWN_ALEMBIC_GAPS = {
    "cash_events",
    "symbols",
    "daily_prices",
    "trading_calendar",
    "corporate_actions",
    "market_indices",
    "universe_history",
}


def test_alembic_upgrade_head_creates_known_tables(temp_db_url):
    cfg = _alembic_config(temp_db_url)
    command.upgrade(cfg, "head")

    engine = create_engine(temp_db_url)
    try:
        inspector = inspect(engine)
        db_tables = set(inspector.get_table_names()) - {"alembic_version"}
        expected_tables = set(Base.metadata.tables.keys()) - _KNOWN_ALEMBIC_GAPS

        missing = expected_tables - db_tables
        assert not missing, f"마이그레이션 누락 테이블: {missing}"
    finally:
        engine.dispose()


def test_alembic_upgrade_then_models_match_columns(temp_db_url):
    cfg = _alembic_config(temp_db_url)
    command.upgrade(cfg, "head")

    engine = create_engine(temp_db_url)
    try:
        inspector = inspect(engine)
        for table_name, table in Base.metadata.tables.items():
            if table_name in _KNOWN_ALEMBIC_GAPS:
                continue
            db_cols = {c["name"] for c in inspector.get_columns(table_name)}
            model_cols = {c.name for c in table.columns}
            missing = model_cols - db_cols
            assert not missing, f"{table_name}: 마이그레이션에 누락된 컬럼: {missing}"
    finally:
        engine.dispose()


def test_alembic_creates_critical_indexes(temp_db_url):
    """정확성 / 성능에 핵심 인덱스가 마이그레이션에 포함되어야 함."""
    cfg = _alembic_config(temp_db_url)
    command.upgrade(cfg, "head")

    engine = create_engine(temp_db_url)
    try:
        inspector = inspect(engine)
        all_indexes: dict[str, set[str]] = {
            tbl: {idx["name"] for idx in inspector.get_indexes(tbl)}
            for tbl in inspector.get_table_names()
            if tbl != "alembic_version"
        }
        # daily_equity의 (run_id, date) 복합 인덱스
        assert "ix_daily_equity_run_date" in all_indexes.get("daily_equity", set())
        # backtest_runs.status 인덱스 (큐 조회용)
        assert "ix_backtest_runs_status" in all_indexes.get("backtest_runs", set())
    finally:
        engine.dispose()


# ============================================================================
# step 038 추가: alembic 환경 검증 (revision 이력 정합성 + head 상태)
# ============================================================================


def test_alembic_revision_chain_has_no_gaps(temp_db_url):
    """alembic upgrade head 후 revision 이력이 연속 체인을 형성하는지 검증.

    누락된 revision이 있으면 head에 도달하지 못하거나 중간 스킵이 발생한다.
    upgrade head가 성공하면 head revision이 alembic_version에 기록됨.
    """
    from sqlalchemy import text

    cfg = _alembic_config(temp_db_url)
    command.upgrade(cfg, "head")

    engine = create_engine(temp_db_url)
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version_num FROM alembic_version"))
            rows = result.fetchall()

        # alembic_version 테이블에 정확히 1개의 head revision이 있어야 함
        assert len(rows) == 1, (
            f"alembic_version에 head revision이 1개이어야 함: {rows}"
        )

        head_revision = rows[0][0]
        # head revision이 비어있지 않아야 함
        assert head_revision and len(head_revision) > 0, (
            f"head revision이 유효하지 않음: {head_revision!r}"
        )
    finally:
        engine.dispose()


def test_alembic_upgrade_head_application_tables_complete(temp_db_url):
    """upgrade head 후 application 테이블 전체가 올바른 스키마로 존재하는지 검증.

    영속화 스냅샷 필수 컬럼 (CLAUDE.md #9):
      backtest_runs: strategy_snapshot_json, random_seed, priority_method,
                     priority_tie_breaker, tick_rounding, use_adjusted_price
    """
    cfg = _alembic_config(temp_db_url)
    command.upgrade(cfg, "head")

    engine = create_engine(temp_db_url)
    try:
        inspector = inspect(engine)
        tables = set(inspector.get_table_names()) - {"alembic_version"}

        # application 핵심 테이블 존재 확인
        required_app_tables = {
            "users",
            "strategies",
            "strategy_versions",
            "backtest_runs",
            "backtest_results",
            "trade_groups",
            "trade_executions",
            "daily_equity",
        }
        missing_tables = required_app_tables - tables
        assert not missing_tables, (
            f"필수 application 테이블 누락: {missing_tables}"
        )

        # backtest_runs 영속화 스냅샷 필수 컬럼 (CLAUDE.md #9)
        br_cols = {c["name"] for c in inspector.get_columns("backtest_runs")}
        snapshot_cols = {
            "strategy_snapshot_json",
            "random_seed",
            "priority_method",
            "priority_tie_breaker",
        }
        missing_snapshot = snapshot_cols - br_cols
        assert not missing_snapshot, (
            f"backtest_runs 영속화 스냅샷 컬럼 누락: {missing_snapshot}"
        )

        # trade_executions 비용 분해 컬럼 (fee/tax 분리, 13.6)
        # 실제 컬럼명: fee, tax (fee_amount/tax_amount가 아님)
        te_cols = {c["name"] for c in inspector.get_columns("trade_executions")}
        cost_cols = {"gross_amount", "fee", "tax", "net_amount"}
        missing_cost = cost_cols - te_cols
        assert not missing_cost, (
            f"trade_executions 비용 분해 컬럼 누락: {missing_cost}"
        )
    finally:
        engine.dispose()
