"""Scheduler — BaseJob 레지스트리 + 단일 프로세스 락 (14번 §5 / §6.2 / 14-j).

본 모듈은 BaseJob을 등록/실행하는 인-프로세스 스케줄러를 제공한다. 028에서
다음 기능을 추가했다:

    1. **단일 프로세스 락** — 동일 잡 동시 실행 차단
        - 동일 잡(name 일치)이 이미 실행 중이면 즉시 LockError raise
        - 메커니즘: 잡명별 threading.RLock + busy-set
        - 분산 락(Redis / PostgreSQL advisory)은 후속 — 본 step은 단일 프로세스만

    2. **cron 메타 보존** — 본 step은 BaseJob.schedule을 그대로 보존만 함
        - cron 파싱(croniter 등)은 후속 운용 단계에서 추가
        - run_job(name)은 cron 검증 없이 즉시 실행 (스케줄러 진입점)

    3. **결정론** (CLAUDE.md #8 / 13.12)
        - 잡 등록 순서 보존 (list)
        - 잡 이름 중복 등록 차단 (ValueError)
        - dict 순회 의존 0건

설계 결정:

    - 본 step에서는 cron 자동 실행 / 비동기 dispatch는 미구현. 호출자가 명시적으로
      `run_job(name)`을 호출 → 락 획득 → 즉시 실행.
    - 락 해제는 try/finally로 보장.
    - 잡 내부에서 raise된 예외는 그대로 전파 (BaseJob.run의 의도).
      단, BaseJob.run() 자체가 JobResult.success=False로 normalize하는 것이 권장 패턴
      (DailyUpdateJob/HistoricalBackfillJob/... 모두 그렇게 작성됨).

사용 예 (운용):

    scheduler = Scheduler()
    scheduler.register(DailyUpdateJob(...))
    scheduler.register(MissingDataCheckJob(...))
    result = scheduler.run_job("daily_update")  # 락 + 동기 실행

사용 예 (테스트 — 락 검증):

    scheduler = Scheduler()
    scheduler.register(_SlowJob("slow"))
    # thread1: scheduler.run_job("slow") — 락 획득
    # thread2: scheduler.run_job("slow") → LockError raise 즉시
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager

from app.data_pipeline.exceptions import JobError
from app.data_pipeline.jobs.base import BaseJob, JobResult


class LockError(JobError):
    """동일 잡이 이미 실행 중일 때 발생 (14-j 단일 프로세스 락)."""


class Scheduler:
    """잡 레지스트리 + 단일 프로세스 락 + 동기 실행 진입점 (14번 §5 scheduler.py).

    Attributes:
        jobs: 등록된 잡 리스트 — 등록 순서 보존 (결정론).
    """

    def __init__(self) -> None:
        # list: 등록 순서 보존 (dict 순회 의존 금지)
        self._jobs: list[BaseJob] = []
        # 락 관리: 잡명별 RLock + busy 집합 (스레드 안전성)
        self._registry_lock = threading.Lock()
        self._busy: set[str] = set()

    def register(self, job: BaseJob) -> None:
        """잡 등록. 같은 name 중복 등록 시 ValueError."""
        with self._registry_lock:
            if any(j.name == job.name for j in self._jobs):
                raise ValueError(f"잡 이름 중복 등록: {job.name!r}")
            self._jobs.append(job)

    def list_jobs(self) -> tuple[BaseJob, ...]:
        """등록된 잡 리스트 — 등록 순서 보존."""
        with self._registry_lock:
            return tuple(self._jobs)

    def get_job(self, name: str) -> BaseJob:
        """이름으로 잡 조회. 없으면 KeyError."""
        with self._registry_lock:
            for j in self._jobs:
                if j.name == name:
                    return j
        raise KeyError(f"등록되지 않은 잡: {name!r}")

    def is_running(self, name: str) -> bool:
        """잡 실행 중 여부 (동시성 검증용)."""
        with self._registry_lock:
            return name in self._busy

    def run_job(self, name: str) -> JobResult:
        """잡 동기 실행 — 단일 프로세스 락 획득 후 실행 (14-j).

        같은 name의 잡이 이미 실행 중이면 즉시 LockError raise (대기하지 않음).
        잡 내부에서 raise된 예외는 그대로 전파한다 (BaseJob.run의 의도).

        Args:
            name: 등록된 잡 이름.

        Returns:
            JobResult — 잡이 반환한 결과.

        Raises:
            KeyError: 미등록 잡.
            LockError: 동일 잡이 이미 실행 중.
            Exception: 잡 내부에서 raise된 예외 (BaseJob.run() 정책 위배 시).
        """
        job = self.get_job(name)
        with self._acquire_lock(name):
            return job.run()

    @contextmanager
    def _acquire_lock(self, name: str) -> Iterator[None]:
        """단일 프로세스 락 — busy-set 기반.

        동시 실행 차단 정책: 같은 name이 busy면 즉시 LockError (대기 없음).
        분산 락은 후속 step에서 동일 인터페이스로 교체 가능.
        """
        with self._registry_lock:
            if name in self._busy:
                raise LockError(f"잡이 이미 실행 중: {name!r}")
            self._busy.add(name)
        try:
            yield
        finally:
            with self._registry_lock:
                self._busy.discard(name)


__all__ = ["LockError", "Scheduler"]
