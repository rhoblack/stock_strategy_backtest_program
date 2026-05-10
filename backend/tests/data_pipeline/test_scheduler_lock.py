"""Scheduler 락 테스트 (Phase 11 step 028 / 14-j).

단일 프로세스 락: 동일 잡 동시 실행 차단 (LockError).
threading으로 두 스레드가 동시에 같은 잡을 호출하는 시나리오 검증.
"""

from __future__ import annotations

import threading
import time
from datetime import UTC, datetime

import pytest

from app.data_pipeline.exceptions import JobError
from app.data_pipeline.jobs.base import BaseJob, JobResult
from app.data_pipeline.scheduler import LockError, Scheduler


class _SlowJob(BaseJob):
    """run() 시작 시 barrier로 동기화, 그 후 hold_seconds 만큼 sleep."""

    def __init__(self, name: str, *, hold_seconds: float = 0.1) -> None:
        super().__init__(name)
        self.hold_seconds = hold_seconds
        self.entered = threading.Event()
        self.allow_exit = threading.Event()

    def run(self) -> JobResult:
        now = datetime.now(UTC)
        self.entered.set()
        # 외부 신호 또는 timeout
        self.allow_exit.wait(self.hold_seconds)
        return JobResult(
            job_name=self.name, success=True, started_at=now, finished_at=datetime.now(UTC)
        )


class _NoopJob(BaseJob):
    def run(self) -> JobResult:
        now = datetime.now(UTC)
        return JobResult(job_name=self.name, success=True, started_at=now, finished_at=now)


def test_scheduler_concurrent_same_job_raises_lock_error() -> None:
    """동일 잡 동시 실행 → 두 번째 호출 즉시 LockError."""
    sch = Scheduler()
    job = _SlowJob("daily_update", hold_seconds=0.5)
    sch.register(job)

    results: dict[str, BaseException | JobResult] = {}

    def _t1() -> None:
        try:
            results["t1"] = sch.run_job("daily_update")
        except BaseException as exc:  # noqa: BLE001
            results["t1"] = exc

    def _t2() -> None:
        # t1이 잡 안에 진입할 때까지 기다린다
        job.entered.wait(timeout=1.0)
        try:
            results["t2"] = sch.run_job("daily_update")
        except BaseException as exc:  # noqa: BLE001
            results["t2"] = exc

    th1 = threading.Thread(target=_t1)
    th2 = threading.Thread(target=_t2)
    th1.start()
    th2.start()
    # t1을 빠르게 끝내기 위해 신호 (단, t2가 LockError를 본 후)
    time.sleep(0.05)
    job.allow_exit.set()
    th1.join(timeout=2.0)
    th2.join(timeout=2.0)

    # t1은 성공 / t2는 LockError
    assert isinstance(results["t1"], JobResult)
    assert results["t1"].success is True
    assert isinstance(results["t2"], LockError)


def test_scheduler_lock_releases_after_run() -> None:
    """잡 종료 후 같은 잡 재실행 가능."""
    sch = Scheduler()
    sch.register(_NoopJob("daily_update"))

    r1 = sch.run_job("daily_update")
    r2 = sch.run_job("daily_update")
    assert r1.success and r2.success
    assert sch.is_running("daily_update") is False


def test_scheduler_different_jobs_can_run_concurrently() -> None:
    """다른 잡은 동시 실행 가능."""
    sch = Scheduler()
    job_a = _SlowJob("a", hold_seconds=0.5)
    job_b = _SlowJob("b", hold_seconds=0.5)
    sch.register(job_a)
    sch.register(job_b)

    results: dict[str, JobResult | BaseException] = {}

    def _run(name: str) -> None:
        try:
            results[name] = sch.run_job(name)
        except BaseException as exc:  # noqa: BLE001
            results[name] = exc

    th1 = threading.Thread(target=_run, args=("a",))
    th2 = threading.Thread(target=_run, args=("b",))
    th1.start()
    th2.start()
    # 둘 다 진입할 때까지 대기
    job_a.entered.wait(timeout=1.0)
    job_b.entered.wait(timeout=1.0)
    # 그 시점에 두 잡이 모두 busy 상태여야 함
    assert sch.is_running("a") is True
    assert sch.is_running("b") is True
    # 신호 → 종료
    job_a.allow_exit.set()
    job_b.allow_exit.set()
    th1.join(timeout=2.0)
    th2.join(timeout=2.0)

    assert isinstance(results["a"], JobResult)
    assert isinstance(results["b"], JobResult)


def test_scheduler_lock_releases_on_job_exception() -> None:
    """잡 내부 예외 raise → 락 해제 (try/finally)."""
    sch = Scheduler()

    class _RaisingJob(BaseJob):
        def run(self) -> JobResult:
            raise RuntimeError("boom")

    sch.register(_RaisingJob("crashy"))

    with pytest.raises(RuntimeError, match="boom"):
        sch.run_job("crashy")

    # 락 해제 확인 — 다시 호출 가능해야 함 (LockError 아님)
    assert sch.is_running("crashy") is False
    with pytest.raises(RuntimeError, match="boom"):
        sch.run_job("crashy")


def test_lock_error_is_subclass_of_job_error() -> None:
    """LockError는 JobError 하위 → 호출자가 JobError로 잡을 수 있음."""
    assert issubclass(LockError, JobError)


def test_scheduler_register_still_blocks_duplicates() -> None:
    sch = Scheduler()
    sch.register(_NoopJob("x"))
    with pytest.raises(ValueError, match="중복 등록"):
        sch.register(_NoopJob("x"))


def test_scheduler_get_unknown_raises_keyerror() -> None:
    sch = Scheduler()
    with pytest.raises(KeyError):
        sch.run_job("missing")


def test_scheduler_list_jobs_preserves_registration_order() -> None:
    sch = Scheduler()
    sch.register(_NoopJob("c"))
    sch.register(_NoopJob("a"))
    sch.register(_NoopJob("b"))
    assert [j.name for j in sch.list_jobs()] == ["c", "a", "b"]
