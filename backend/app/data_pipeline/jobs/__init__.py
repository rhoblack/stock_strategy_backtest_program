"""data_pipeline.jobs — collector + processor + repositories 조합 잡 (14번 §5 / §6).

- BaseJob / JobResult: 추상 베이스 (024)
- DailyUpdateJob: 일일 증분 수집 (028, 14번 §6.2)
- HistoricalBackfillJob: 과거 N일 일괄 수집 (028, 14번 §6.1)
- CorporateActionApplyJob: 수정주가 일괄 재계산 (028, 14번 §9)
- MarketIndexJob: 시장 지수 일봉 수집 (028, 14번 §3-4)
- UniverseSnapshotJob: universe 스냅샷 영속화 (028, 14번 §10)
- MissingDataCheckJob: 결손 알림 (028, 14번 §13 / 14-k)

타 모듈 사용법:
    from app.data_pipeline.jobs import (
        BaseJob,
        JobResult,
        DailyUpdateJob, DailyUpdateConfig,
        HistoricalBackfillJob, HistoricalBackfillConfig,
        CorporateActionApplyJob, CorporateActionApplyConfig,
        MarketIndexJob, MarketIndexConfig, IndexFetcher,
        UniverseSnapshotJob, UniverseSnapshotConfig, compute_config_hash,
        MissingDataCheckJob, MissingDataCheckConfig, MissingDataAlert, MissingDataEntry,
    )
"""

from app.data_pipeline.jobs.base import BaseJob, JobResult
from app.data_pipeline.jobs.corporate_action_apply import (
    CorporateActionApplyConfig,
    CorporateActionApplyJob,
)
from app.data_pipeline.jobs.daily_update import (
    DailyUpdateConfig,
    DailyUpdateJob,
)
from app.data_pipeline.jobs.historical_backfill import (
    HistoricalBackfillConfig,
    HistoricalBackfillJob,
)
from app.data_pipeline.jobs.market_index_update import (
    IndexFetcher,
    MarketIndexConfig,
    MarketIndexJob,
)
from app.data_pipeline.jobs.missing_data_check import (
    MissingDataAlert,
    MissingDataCheckConfig,
    MissingDataCheckJob,
    MissingDataEntry,
)
from app.data_pipeline.jobs.universe_snapshot import (
    UniverseSnapshotConfig,
    UniverseSnapshotJob,
    compute_config_hash,
)

__all__ = [
    "BaseJob",
    "CorporateActionApplyConfig",
    "CorporateActionApplyJob",
    "DailyUpdateConfig",
    "DailyUpdateJob",
    "HistoricalBackfillConfig",
    "HistoricalBackfillJob",
    "IndexFetcher",
    "JobResult",
    "MarketIndexConfig",
    "MarketIndexJob",
    "MissingDataAlert",
    "MissingDataCheckConfig",
    "MissingDataCheckJob",
    "MissingDataEntry",
    "UniverseSnapshotConfig",
    "UniverseSnapshotJob",
    "compute_config_hash",
]
