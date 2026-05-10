"""data_pipeline.jobs — collector + processor + repositories 조합 잡 (14번 §5 / §6).

본 패키지는 BaseJob 추상 베이스만 제공한다.
실제 DailyUpdateJob / HistoricalBackfillJob / CorporateActionApplyJob은 028.

타 모듈 사용법:
    from app.data_pipeline.jobs import BaseJob, JobResult
"""

from app.data_pipeline.jobs.base import BaseJob, JobResult

__all__ = ["BaseJob", "JobResult"]
