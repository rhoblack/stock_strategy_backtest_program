"""UniverseSnapshotJob 테스트 (Phase 11 step 028 / 14-j).

UniverseSelector mock 또는 실제 selector + 합성 universe 데이터.
영속화 검증, config_hash 결정론, 빈 universe 경고.
"""

from __future__ import annotations

from datetime import date

from app.data_pipeline.jobs.universe_snapshot import (
    UniverseSnapshotConfig,
    UniverseSnapshotJob,
    compute_config_hash,
)
from app.market_data import repositories
from app.market_data.universe import (
    SELECTION_METHOD_ALL,
    UniverseSelectionResult,
    UniverseSelector,
)
from app.models.universe_history import UniverseHistory


def _seed_symbols(session, symbols: list[tuple[str, str]]) -> None:
    """symbols: list of (code, market) — 본 테스트는 listing_date=2020-01-01 고정."""
    for code, market in symbols:
        repositories.upsert_symbol(
            session,
            {
                "symbol": code, "name": f"종목{code}",
                "market": market, "listing_date": date(2020, 1, 1),
            },
        )


def test_universe_snapshot_persists_with_real_selector(session_factory, db_session) -> None:
    """실제 UniverseSelector + 합성 데이터로 universe_history 영속화."""
    _seed_symbols(db_session, [
        ("000020", "KOSPI"), ("005930", "KOSPI"), ("000660", "KOSPI"),
    ])
    db_session.commit()

    job = UniverseSnapshotJob(
        config=UniverseSnapshotConfig(
            as_of_date=date(2024, 1, 2),
            selector_config={"market": "KOSPI", "selection_method": SELECTION_METHOD_ALL},
            run_id=None,
        ),
        session_factory=session_factory,
    )
    result = job.run()

    assert result.success is True
    stats = dict(result.stats)
    assert stats["symbols_selected"] == 3
    assert stats["snapshots_upserted"] == 1

    session = session_factory()
    try:
        snaps = session.query(UniverseHistory).all()
        assert len(snaps) == 1
        snap = snaps[0]
        assert snap.as_of_date == date(2024, 1, 2)
        assert snap.market == "KOSPI"
        assert snap.selection_method == SELECTION_METHOD_ALL
        assert snap.symbols_json == ["000020", "000660", "005930"]  # symbol ASC
        assert snap.config_hash is not None
    finally:
        session.close()


def test_universe_snapshot_empty_universe_warns(session_factory) -> None:
    """universe 0건 → warnings 누적."""
    job = UniverseSnapshotJob(
        config=UniverseSnapshotConfig(
            as_of_date=date(2024, 1, 2),
            selector_config={"market": "KOSPI", "selection_method": SELECTION_METHOD_ALL},
        ),
        session_factory=session_factory,
    )
    result = job.run()

    assert result.success is True
    assert dict(result.stats)["symbols_selected"] == 0
    assert any("universe 0건" in w for w in result.warnings)


def test_universe_snapshot_with_mock_selector(session_factory) -> None:
    """selector_factory 주입으로 mock selector 사용."""
    mock_result = UniverseSelectionResult(
        symbols=[],  # symbol 객체 없이도 길이 0이면 OK
        excluded_counts={},
        as_of_date=date(2024, 1, 2),
        market="KOSPI",
        selection_method="ALL",
    )

    class _MockSelector(UniverseSelector):
        def __init__(self, session) -> None:
            self.session = session

        def select_with_details(self, config, as_of_date):  # type: ignore[override]
            return mock_result

    job = UniverseSnapshotJob(
        config=UniverseSnapshotConfig(
            as_of_date=date(2024, 1, 2),
            selector_config={"market": "KOSPI"},
        ),
        session_factory=session_factory,
        selector_factory=_MockSelector,
    )
    result = job.run()

    assert result.success is True
    assert dict(result.stats)["snapshots_upserted"] == 1


def test_compute_config_hash_is_stable() -> None:
    """동일 dict (key 순서 다름)은 동일 해시."""
    h1 = compute_config_hash({"market": "KOSPI", "method": "ALL"})
    h2 = compute_config_hash({"method": "ALL", "market": "KOSPI"})
    assert h1 == h2

    # 값이 다르면 다른 해시
    h3 = compute_config_hash({"market": "KOSDAQ", "method": "ALL"})
    assert h1 != h3


def test_universe_snapshot_idempotent_upsert(session_factory, db_session) -> None:
    """동일 잡 두 번 호출 → universe_history 1개만 (UniqueConstraint 갱신)."""
    _seed_symbols(db_session, [("005930", "KOSPI")])
    db_session.commit()

    job = UniverseSnapshotJob(
        config=UniverseSnapshotConfig(
            as_of_date=date(2024, 1, 2),
            selector_config={"market": "KOSPI", "selection_method": "ALL"},
        ),
        session_factory=session_factory,
    )
    job.run()
    job.run()

    session = session_factory()
    try:
        count = session.query(UniverseHistory).count()
        assert count == 1
    finally:
        session.close()


def test_universe_snapshot_failure_normalizes(session_factory) -> None:
    """selector raise → JobResult.success=False."""

    class _FailingSelector(UniverseSelector):
        def __init__(self, session) -> None:
            self.session = session

        def select_with_details(self, config, as_of_date):  # type: ignore[override]
            raise RuntimeError("DB 오류")

    job = UniverseSnapshotJob(
        config=UniverseSnapshotConfig(
            as_of_date=date(2024, 1, 2),
            selector_config={"market": "KOSPI"},
        ),
        session_factory=session_factory,
        selector_factory=_FailingSelector,
    )
    result = job.run()
    assert result.success is False
    assert any("DB 오류" in e for e in result.errors)
