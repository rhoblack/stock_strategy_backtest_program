"""Scheduler skeleton (14번 §5 / §6.2).

본 모듈은 BaseJob을 등록/실행하는 스케줄러의 추상 베이스만 정의한다.
실제 cron 파싱, 락(중복 실행 방지), 타임아웃 처리는 028에서 구현.

설계 결정 (인계 정보 — 028 구현체가 따라야 함):

    1. **`Scheduler`는 ABC가 아니라 단순 register/list 레지스트리**
        - 본 step에서는 잡 등록 + 조회만 (실행은 028의 ConcreteScheduler에서)
        - 등록 순서 보존을 위해 list 사용 (dict 순회 의존 금지)

    2. **잡 중복 등록 방지** — 같은 name 두 번 등록 시 ValueError
        - 결정론: 런타임에 같은 이름 잡이 둘 이상 존재할 수 없음

    3. **잡 실행 자체는 028에서**
        - 본 step에서는 `run_job(name)`을 즉시 실행하는 인터페이스만 (테스트 가능)
        - 락/타임아웃/cron parsing은 ConcreteScheduler에서 wrap

본 step에서는 외부 fetch / cron 파싱 / OS 락 0건 — 메모리 in-process 레지스트리만.
"""

from __future__ import annotations

from app.data_pipeline.jobs.base import BaseJob, JobResult


class Scheduler:
    """잡 레지스트리 + 즉시 실행 진입점 (14번 §5 scheduler.py).

    028에서 cron 파싱 / 락 / 비동기 실행을 추가할 ConcreteScheduler가 본 클래스를
    상속하거나 합성해 사용한다. 본 step에서는 in-process 동기 실행만.

    Attributes:
        jobs: 등록된 잡 리스트 — 등록 순서 보존 (결정론).

    사용 예 (028~):
        scheduler = Scheduler()
        scheduler.register(DailyUpdateJob(...))
        scheduler.register(CorporateActionApplyJob(...))
        result = scheduler.run_job("daily_update")  # 동기 실행
    """

    def __init__(self) -> None:
        # list: 등록 순서 보존 (dict 순회 의존 금지)
        self._jobs: list[BaseJob] = []

    def register(self, job: BaseJob) -> None:
        """잡 등록. 같은 name 중복 등록 시 ValueError."""
        if any(j.name == job.name for j in self._jobs):
            raise ValueError(f"잡 이름 중복 등록: {job.name!r}")
        self._jobs.append(job)

    def list_jobs(self) -> tuple[BaseJob, ...]:
        """등록된 잡 리스트 — 등록 순서 보존."""
        return tuple(self._jobs)

    def get_job(self, name: str) -> BaseJob:
        """이름으로 잡 조회. 없으면 KeyError."""
        for j in self._jobs:
            if j.name == name:
                return j
        raise KeyError(f"등록되지 않은 잡: {name!r}")

    def run_job(self, name: str) -> JobResult:
        """잡 동기 실행. 028에서 락/타임아웃 wrapping."""
        return self.get_job(name).run()


__all__ = ["Scheduler"]
