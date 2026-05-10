"""data_pipeline — 시장데이터 ETL 파이프라인 (14번 §5).

본 패키지는 collector → processor → job 3단계 ETL을 추상화한다.

```
collectors/  외부 데이터 소스에서 raw 수집  (E - Extract)
processors/  raw → 정제/검증/재계산        (T - Transform)
jobs/        collector + processor + repositories 조합 운영 잡
scheduler.py 잡 레지스트리 + 동기 실행 (cron은 028에서 wrap)
exceptions.py 공통 예외 계층
```

본 step (024)은 ABC + dataclass + 예외 계층만 도입.
실제 구현체:
    - 025: pykrx PykrxCollector + 재시도/백오프
    - 026: AdjustedPriceProcessor + corporate_actions
    - 027: MarketCapProcessor + market_indices + universe_history
    - 028: DailyUpdateJob / HistoricalBackfillJob + ConcreteScheduler

기존 인프라와의 관계 (활용 대상, 본 패키지에서 수정 금지):
    - `app.market_data.repositories` (016): 저수준 CRUD — collector/processor 결과를 적재할 진입점
    - `app.market_data.provider.BaseProvider` (018): raw 수집 + DB 적재 단일 진입점
        * BaseProvider.ingest_into = "한 번에 끝내는" 외부 호출자 친화 인터페이스
        * BaseCollector.collect_*  = ETL의 E만 담당, DB 미터치 (테스트 용이성)
        * 두 추상화는 직교 — PykrxProvider(향후)는 내부에서 PykrxCollector를 합성 가능

타 모듈 사용법:
    from app.data_pipeline import (
        BaseCollector,
        BaseProcessor,
        BaseJob,
        Scheduler,
        DataPipelineError,
        CollectorError,
        ProcessorError,
        JobError,
        RetryableError,
        FatalError,
        DataValidationError,
    )
"""

from app.data_pipeline.collectors import (
    DEFAULT_BACKOFF_SECONDS,
    BaseCollector,
    FatalCollectorError,
    PykrxCollector,
    RawCalendarData,
    RawCalendarRow,
    RawDailyPriceRow,
    RawDailyPricesData,
    RawData,
    RawSymbolRow,
    RawSymbolsData,
    RetryableCollectorError,
    retry_call,
    retry_on_retryable,
    validate_calendar_data,
    validate_daily_price_row,
    validate_daily_prices_data,
    validate_symbol_row,
    validate_symbols_data,
)
from app.data_pipeline.exceptions import (
    CollectorError,
    DataPipelineError,
    DataValidationError,
    FatalError,
    JobError,
    ProcessorError,
    RetryableError,
)
from app.data_pipeline.jobs import (
    BaseJob,
    CorporateActionApplyConfig,
    CorporateActionApplyJob,
    DailyUpdateConfig,
    DailyUpdateJob,
    HistoricalBackfillConfig,
    HistoricalBackfillJob,
    IndexFetcher,
    JobResult,
    MarketIndexConfig,
    MarketIndexJob,
    MissingDataAlert,
    MissingDataCheckConfig,
    MissingDataCheckJob,
    MissingDataEntry,
    UniverseSnapshotConfig,
    UniverseSnapshotJob,
    compute_config_hash,
)
from app.data_pipeline.processors import (
    BaseProcessor,
    ProcessedResult,
    ValidationIssue,
    ValidationResult,
)
from app.data_pipeline.scheduler import LockError, Scheduler

__all__ = [
    # collectors (base)
    "BaseCollector",
    "RawCalendarData",
    "RawCalendarRow",
    "RawData",
    "RawDailyPriceRow",
    "RawDailyPricesData",
    "RawSymbolRow",
    "RawSymbolsData",
    # collectors (pykrx + retry + validators)
    "DEFAULT_BACKOFF_SECONDS",
    "FatalCollectorError",
    "PykrxCollector",
    "RetryableCollectorError",
    "retry_call",
    "retry_on_retryable",
    "validate_calendar_data",
    "validate_daily_price_row",
    "validate_daily_prices_data",
    "validate_symbol_row",
    "validate_symbols_data",
    # processors
    "BaseProcessor",
    "ProcessedResult",
    "ValidationIssue",
    "ValidationResult",
    # jobs / scheduler
    "BaseJob",
    "CorporateActionApplyConfig",
    "CorporateActionApplyJob",
    "DailyUpdateConfig",
    "DailyUpdateJob",
    "HistoricalBackfillConfig",
    "HistoricalBackfillJob",
    "IndexFetcher",
    "JobResult",
    "LockError",
    "MarketIndexConfig",
    "MarketIndexJob",
    "MissingDataAlert",
    "MissingDataCheckConfig",
    "MissingDataCheckJob",
    "MissingDataEntry",
    "Scheduler",
    "UniverseSnapshotConfig",
    "UniverseSnapshotJob",
    "compute_config_hash",
    # exceptions
    "CollectorError",
    "DataPipelineError",
    "DataValidationError",
    "FatalError",
    "JobError",
    "ProcessorError",
    "RetryableError",
]
