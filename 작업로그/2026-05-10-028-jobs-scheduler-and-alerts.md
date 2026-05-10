---
date: 2026-05-10
agent: market-data-engineer
phase: 11
status: completed
roadmap_step: 028
roadmap_impact:
  - 14-j  # jobs / scheduler / 락
  - 14-k  # 결손 알림 + forward-fill 금지 검증
related_docs:
  - 상세설계/14_data_pipeline_design.md
  - 작업로그/2026-05-10-024-data-pipeline-skeleton.md
  - 작업로그/2026-05-10-025-pykrx-collector.md
  - 작업로그/2026-05-10-026-corporate-actions-and-adjusted-price.md
  - 작업로그/2026-05-10-027-market-indices-and-universe-history.md
---

# Step 028 — jobs/scheduler + 결손 알림 (Phase 11 마지막)

024 BaseJob + Scheduler 위에 실제 jobs 구현 + 락/결손 알림. Phase 11 마지막 step. 완료 후 test-engineer 검증 → ship-go → push.

## Plan

### A) 핵심 jobs 구현 (14-j)
- [ ] `상세설계/14_data_pipeline_design.md` §8·§9 정독
- [ ] `backend/app/data_pipeline/jobs/daily_update.py` 신규
  - DailyUpdateJob(BaseJob): collector → processor → repositories.upsert_*
  - 매일 collect_symbols + collect_daily_prices + collect_trading_calendar 후 영속화
  - 026 AdjustedPriceProcessor 적용 (corporate_actions 있으면)
- [ ] `backend/app/data_pipeline/jobs/historical_backfill.py` 신규
  - HistoricalBackfillJob(BaseJob): 과거 N일 일괄 수집 (initial setup 또는 결손 재수집)
- [ ] `backend/app/data_pipeline/jobs/corporate_action_apply.py` 신규
  - CorporateActionApplyJob(BaseJob): corporate_actions 변경 후 adj_* 재계산 + bulk_upsert_daily_prices
- [ ] `backend/app/data_pipeline/jobs/market_index_update.py` 신규
  - MarketIndexJob(BaseJob): KOSPI/KOSDAQ 지수 수집 (027 market_indices)
- [ ] `backend/app/data_pipeline/jobs/universe_snapshot.py` 신규
  - UniverseSnapshotJob(BaseJob): 019 UniverseSelector 결과를 027 universe_history에 영속화

### B) Scheduler 락 / cron (14-j)
- [ ] `backend/app/data_pipeline/scheduler.py` 확장 (024 인터페이스 위에)
- 본 step에서는:
  - 단일 프로세스 락 (filesystem lock 또는 in-memory) — 동일 잡 동시 실행 차단
  - cron 파싱은 외부 라이브러리(croniter) 또는 단순 시간대(daily) 지원
  - run_job(name) 시 락 + cron 검증
- 분산 락 (Redis/PostgreSQL advisory)은 후속

### C) 결손 알림 (14-k)
- [ ] `backend/app/data_pipeline/jobs/missing_data_check.py` 신규 또는 기존 jobs에 통합
- `is_trading_day=true`인데 daily_prices에 row 없음 → MissingDataAlert 생성
- forward-fill 금지 (14.10) — 결손은 그대로 보존, 알림만
- AlertResult dataclass: 결손 종목/일자 리스트
- 본 step에서는 logger 출력 또는 JobResult.warnings로 보고

### D) 테스트
- [ ] `backend/tests/data_pipeline/test_jobs_*.py` 신규 (각 job별)
- collector mock + processor mock + repositories in-memory SQLite
- 결정론: 동일 입력 5회 반복 동일 영속화 결과
- 락: 동일 잡 동시 실행 차단 검증

### E) 회귀
- [ ] 전체 pytest (Phase 1~10 + 024~027 회귀)
- [ ] ruff
- [ ] alembic 회귀

### 절대 금지
- BacktestEngine / Portfolio / StrategyEngine / ExecutionModel / CashManager 절대 수정
- API / Pydantic schemas / services 추가/수정
- application 테이블 / 시장데이터 모델 수정
- conditions/* 수정
- 016/018/019/024/025/026/027 산출물 시그니처 변경 금지 — 활용만
- 외부 fetch (실제 pykrx 호출 — 테스트는 mock)
- 결정론 깨기

### Phase 11 완료 흐름 (028 마무리 후)
1. PM 호출 → 로드맵 갱신 (14-j, 14-k [x] / Phase 11 step 028 ✅)
2. **test-engineer 호출 "Phase 11 완료 검증"** — 통합 회귀 + 13.17 acceptance + Phase 1 골든 + 시나리오 + ship-readiness
3. ship-go 시: PM "Phase 11 완료" → 진행률 추이 갱신 + Phase 12 첫 step ⏭ → push

## Execution

### A) 5개 jobs 신규 (14-j)

- `backend/app/data_pipeline/jobs/daily_update.py:1` 신규
  - `DailyUpdateJob(BaseJob)` + `DailyUpdateConfig` (frozen dataclass)
  - 흐름: collect_symbols → upsert_symbol → collect_trading_calendar(시장별) → upsert_trading_day → collect_daily_prices → (corporate_actions 있으면 AdjustedPriceProcessor) → bulk_upsert_daily_prices
  - 의존성 주입: collector (BaseCollector spec) / session_factory / processor / clock
  - schedule="0 18 * * 1-5" (KST 평일 18시 — 14 §6.2 권장)
  - 결정론: stats는 (key ASC) 정렬 tuple, dict 순회 의존 0건
  - 예외 normalize: collector raise → JobResult.success=False + errors 누적

- `backend/app/data_pipeline/jobs/historical_backfill.py:1` 신규
  - `HistoricalBackfillJob(BaseJob)` + `HistoricalBackfillConfig`
  - 흐름은 DailyUpdate와 동일하나 (start_date, end_date) 구간 처리
  - schedule=None (수동 실행 전용 — 백필 특성)
  - `__post_init__`로 start>end ValueError

- `backend/app/data_pipeline/jobs/corporate_action_apply.py:1` 신규
  - `CorporateActionApplyJob(BaseJob)` + `CorporateActionApplyConfig`
  - 흐름: get_price_range → adj_*=close로 reset (idempotent 보장!) → get_corporate_actions → AdjustedPriceProcessor → bulk_upsert_daily_prices
  - **collector 미사용** — DB 일봉을 입력으로 사용 (in-DB 재계산만)
  - **14.5 / 13.7 idempotent 보장**: 매 호출마다 adj_* = close로 reset해 누적 적용 차단
  - schedule=None (트리거 방식 — corporate_action 등록 후 호출)

- `backend/app/data_pipeline/jobs/market_index_update.py:1` 신규
  - `MarketIndexJob(BaseJob)` + `MarketIndexConfig` + `IndexFetcher` 타입 alias
  - 024 BaseCollector ABC가 시장 지수 수집 메서드를 강제하지 않으므로
    명시적 `index_fetcher` callable 주입 (`(code, start, end) -> Iterable[dict]`)
  - 흐름: sorted(index_codes) → fetcher 호출 → 각 row를 (date ASC, index_code ASC)로 정렬 → upsert_market_index
  - 단일 지수 fetch 실패는 errors에 누적 + 다른 지수 처리는 계속 (부분 실패 시 success=False)
  - 알 수 없는 index_code → upsert에서 ValueError → warnings에 누적 (success 유지)

- `backend/app/data_pipeline/jobs/universe_snapshot.py:1` 신규
  - `UniverseSnapshotJob(BaseJob)` + `UniverseSnapshotConfig` + `compute_config_hash` 헬퍼
  - 흐름: `selector_factory(session)` → `select_with_details(config, as_of_date)` → SHA-256 config_hash → upsert_universe_snapshot
  - `compute_config_hash`: `json.dumps(config, sort_keys=True, ensure_ascii=False, default=str)` → SHA-256
    (dict 순회 의존 0건, 동일 dict는 항상 동일 해시)
  - 빈 universe는 warnings 누적 + 영속화는 진행 (run_id=None preview 스냅샷도 보존)

### C) 결손 알림 (14-k)

- `backend/app/data_pipeline/jobs/missing_data_check.py:1` 신규
  - `MissingDataCheckJob(BaseJob)` + `MissingDataCheckConfig` + `MissingDataAlert` (frozen dataclass) + `MissingDataEntry` (frozen dataclass)
  - 흐름: get_trading_days → 종목별 get_price_range → 차집합 = 결손 (symbol, date)
  - **forward-fill 절대 금지** (14.10) — 본 잡은 결손을 감지만, DB 변경 0건 (test_missing_data_does_not_forward_fill로 검증)
  - schedule="30 18 * * 1-5" (KST 평일 18:30, DailyUpdate 직후)
  - `job.last_alert: MissingDataAlert` 캡처 — 호출자가 알림 채널 연결 가능
  - alert.entries는 (symbol ASC, date ASC) 정렬 보장

### B) Scheduler 락 확장 (14-j)

- `backend/app/data_pipeline/scheduler.py` 확장 (024 인터페이스 위에)
  - 신규 `LockError(JobError)` — 동일 잡 동시 실행 시
  - `_registry_lock: threading.Lock` + `_busy: set[str]` — 잡명별 단일 프로세스 락
  - `_acquire_lock(name)` 컨텍스트매니저: 즉시 LockError raise (대기 없음, fail-fast)
  - `try/finally`로 잡 내부 예외 raise 시에도 락 해제 보장
  - 신규 메서드: `is_running(name) -> bool` (외부 모니터링/테스트용)
  - 다른 잡은 동시 실행 가능 (잡명별 격리)
  - 분산 락 (Redis/PostgreSQL advisory)은 후속 — 본 step은 단일 프로세스만

### D) jobs/__init__.py + data_pipeline/__init__.py export 갱신

- `backend/app/data_pipeline/jobs/__init__.py` — 5 jobs + Config + helper export
- `backend/app/data_pipeline/__init__.py` — 패키지 최상위 export + LockError 추가

### E) 테스트 (Plan D)

- `backend/tests/data_pipeline/conftest.py` 신규 — `db_engine` / `db_session` / `session_factory` fixture
- `backend/tests/data_pipeline/test_jobs_daily_update.py` 신규 (11건)
- `backend/tests/data_pipeline/test_jobs_historical_backfill.py` 신규 (5건)
- `backend/tests/data_pipeline/test_jobs_corporate_action_apply.py` 신규 (5건)
- `backend/tests/data_pipeline/test_jobs_market_index_update.py` 신규 (6건)
- `backend/tests/data_pipeline/test_jobs_universe_snapshot.py` 신규 (6건)
- `backend/tests/data_pipeline/test_jobs_missing_data_check.py` 신규 (9건)
- `backend/tests/data_pipeline/test_scheduler_lock.py` 신규 (8건)

총 50 신규 테스트 (외부 fetch 0건 — collector mock + in-memory SQLite + processor wrap mock)

## Tests

```text
신규 테스트 (Phase 11 step 028):
  tests/data_pipeline/test_jobs_daily_update.py            11 passed
  tests/data_pipeline/test_jobs_historical_backfill.py      5 passed
  tests/data_pipeline/test_jobs_corporate_action_apply.py   5 passed
  tests/data_pipeline/test_jobs_market_index_update.py      6 passed
  tests/data_pipeline/test_jobs_universe_snapshot.py        6 passed
  tests/data_pipeline/test_jobs_missing_data_check.py       9 passed
  tests/data_pipeline/test_scheduler_lock.py                8 passed
  소계: 50 passed (0.5초 미만)

전체 테스트:
  baseline: 770 passed (Phase 11 step 027 종료 시점)
  본 step: 820 passed = 770 + 50 신규
  baseline 대비 신규 fail: 0건

Phase 1 골든 fixture (engine 변경 0건):
  tests/backtest/ 161 passed — 영향 없음 확인

ruff: All checks passed (변경 파일 14개)
```

14번 / 14-j / 14-k 정책 검증 항목 매핑:

| 정책 | 검증 테스트 |
|------|-----------|
| 14 §6.2 일일 증분 (DailyUpdate) | test_daily_update_persists_symbols_calendar_prices / test_daily_update_calls_collector_per_market |
| 14 §6.1 백필 (HistoricalBackfill) | test_backfill_persists_full_range / test_backfill_passes_full_range_to_collector |
| 14 §9 수정주가 재계산 | test_corporate_action_apply_split_recalculates_pre_event_prices / test_daily_update_applies_corporate_actions |
| 14 §3-4 시장 지수 | test_market_index_persists_multi_codes / test_market_index_invalid_code_warns |
| 14 §10 universe 영속화 (생존편향 보존) | test_universe_snapshot_persists_with_real_selector / test_universe_snapshot_idempotent_upsert |
| 14 §13 결손 알림 (14-k) | test_missing_data_detects_missing_days / test_missing_data_does_not_count_holidays |
| 14.10 forward-fill 금지 (14-k) | test_missing_data_does_not_forward_fill |
| 14-j 단일 프로세스 락 | test_scheduler_concurrent_same_job_raises_lock_error / test_scheduler_lock_releases_on_job_exception |
| 14.5 / 13.7 close 보존 | test_corporate_action_apply_split_recalculates_pre_event_prices (close 검증) |
| 14.5 idempotent 재실행 | test_corporate_action_apply_determinism / test_daily_update_determinism_repeated_runs_same_state |
| 13.12 / CLAUDE.md #8 결정론 | test_daily_update_jobresult_stats_are_sorted_tuple / test_market_index_processes_codes_in_sorted_order / test_missing_data_alert_entries_are_sorted / test_compute_config_hash_is_stable |
| 14 §13 결손 알림 — JobResult.warnings | test_missing_data_detects_missing_days (warnings 검증) |

## Issues

1. **CorporateActionApplyJob idempotent 보장 — adj_*를 close로 reset 후 재계산**
   - 처음 작성 시 ORM의 adj_*를 그대로 입력으로 사용 → 두 번 실행하면 누적 적용되어
     adj_close가 70_000 → 35_000 → 17_500이 되는 버그 발견
   - 수정: 매 호출마다 adj_open/high/low/close = open/high/low/close로 reset한
     RawDailyPriceRow를 만들어 입력
   - 14.5 "분할/배당 발생 시 과거 전체 재계산 (스냅샷 누적 금지)" 정신과 일치
   - test_corporate_action_apply_determinism으로 회귀 가드

2. **MarketIndexJob — BaseCollector에 시장 지수 수집 메서드 부재**
   - 024 BaseCollector는 3-메서드 분할(symbols/prices/calendar)이며 지수 메서드는 별도 추가 필요
   - 본 step에서는 명시적 `index_fetcher: Callable[(code, start, end), Iterable[dict]]` 주입으로 우회
   - 후속 step(또는 PykrxCollector 확장)에서 BaseCollector에 `collect_market_index` 메서드 추가
     검토 권고 (이 시점에서 본 잡 시그니처도 정합화)

3. **UniverseSnapshotJob — UniverseSelector 의존성 직접 import**
   - `from app.market_data.universe import UniverseSelector` (선택적 selector_factory로 mock 가능)
   - 019 UniverseSelector가 `select_with_details(config, as_of_date) -> UniverseSelectionResult` 인터페이스를
     변경하면 본 잡도 영향 받음 (단, 본 step에서 019 시그니처 변경 0건)

4. **Scheduler 락은 단일 프로세스만 (분산 락 미지원)**
   - threading.Lock + busy-set으로 동일 프로세스 내 동시 실행만 차단
   - 멀티 프로세스/멀티 머신에서는 Redis SETNX 또는 PostgreSQL advisory lock 필요
   - 후속 운용 단계에서 동일 인터페이스(`_acquire_lock` 컨텍스트매니저)로 교체 가능하게 설계됨

5. **schedule cron 자동 실행 미구현**
   - 본 step의 Scheduler는 `run_job(name)` 호출 시점에만 실행 (cron 파싱 없음)
   - cron 자동 트리거 (croniter + APScheduler 또는 systemd timer)는 후속 운용 단계
   - BaseJob.schedule 메타는 보존 — 추후 자동 실행 시 그대로 활용

6. **외부 fetch 0건 정책 준수**
   - 모든 jobs 테스트는 MagicMock collector + in-memory SQLite + (CorporateActionApply는 collector 미사용)
   - 실제 pykrx 호출은 025의 `@pytest.mark.network` 마커로 분리 (본 step도 동일 정책)

7. **Phase 1 골든 fixture 영향 0건 확인**
   - 본 step은 신규 모듈만 작성, BacktestEngine / Portfolio / StrategyEngine / ExecutionModel /
     CashManager / conditions / market_data 모델/repositories / 016~027 산출물 시그니처 모두 미수정
   - tests/backtest/ 161건 그대로 통과

## Result

### 적용 정책 절번호
- 14번 §3 (수집 대상 — symbols/prices/calendar/indices)
- 14번 §5 (jobs/scheduler 패키지 구조)
- 14번 §6.1 (HistoricalBackfill — 초기 백필)
- 14번 §6.2 (DailyUpdate — 일일 증분)
- 14번 §9 (CorporateActionApply — 수정주가 재계산)
- 14번 §10 (UniverseSnapshot — 생존편향 보존)
- 14번 §13 (MissingDataCheck — 결손 알림)
- 14번 §16.1 (일일 점검 체크리스트)
- 13번 §7 (수정주가 — close 보존, adj_*만 재계산)
- 13번 §12 (결정론)
- 13번 §13 (생존편향 — universe_history에 폐지 종목 보존)
- 13번 §15 (look-ahead — corporate_actions는 ≤ as_of_date)
- 14-j (jobs/scheduler/락)
- 14-k (결손 알림 + forward-fill 금지)
- CLAUDE.md #5 (수정주가 기본) / #8 (결정론) / #10 (생존편향)

### 5 Jobs 시그니처 (BaseJob 상속)

```python
# 1) DailyUpdateJob (14-j, 14 §6.2)
class DailyUpdateJob(BaseJob):
    def __init__(
        self,
        config: DailyUpdateConfig,            # as_of_date / markets / symbols / apply_adjusted_price
        collector: BaseCollector,
        session_factory: Callable[[], Session],
        *,
        processor: AdjustedPriceProcessor | None = None,
        name: str = "daily_update",
        schedule: str | None = "0 18 * * 1-5",
        clock: Callable[[], datetime] | None = None,
    ) -> None: ...
    def run(self) -> JobResult: ...
    # 흐름: collect_symbols → upsert_symbol → collect_trading_calendar(시장별)
    #      → upsert_trading_day → collect_daily_prices → (corporate_actions 있으면 Processor)
    #      → bulk_upsert_daily_prices → JobResult

# 2) HistoricalBackfillJob (14-j, 14 §6.1)
class HistoricalBackfillJob(BaseJob):
    def __init__(
        self,
        config: HistoricalBackfillConfig,    # start_date / end_date / markets / symbols / apply_adjusted_price
        collector: BaseCollector,
        session_factory: Callable[[], Session],
        *,
        processor: AdjustedPriceProcessor | None = None,
        name: str = "historical_backfill",
        schedule: str | None = None,         # 수동 실행
        clock: Callable[[], datetime] | None = None,
    ) -> None: ...
    # DailyUpdate와 동일 흐름, 단일 일자 → (start, end) 구간

# 3) CorporateActionApplyJob (14-j, 14 §9)
class CorporateActionApplyJob(BaseJob):
    def __init__(
        self,
        config: CorporateActionApplyConfig,  # symbols / start_date / end_date
        session_factory: Callable[[], Session],  # collector 미주입
        *,
        processor: AdjustedPriceProcessor | None = None,
        name: str = "corporate_action_apply",
        schedule: str | None = None,         # 트리거 방식
        clock: Callable[[], datetime] | None = None,
    ) -> None: ...
    # 흐름: get_price_range → adj_*=close reset → get_corporate_actions → Processor
    #      → bulk_upsert_daily_prices (idempotent 보장)

# 4) MarketIndexJob (14-j, 14 §3-4)
class MarketIndexJob(BaseJob):
    def __init__(
        self,
        config: MarketIndexConfig,           # index_codes / start_date / end_date
        index_fetcher: IndexFetcher,         # (code, start, end) -> Iterable[dict]
        session_factory: Callable[[], Session],
        *,
        name: str = "market_index_update",
        schedule: str | None = "0 18 * * 1-5",
        clock: Callable[[], datetime] | None = None,
    ) -> None: ...
    # 흐름: sorted(index_codes) → fetcher → upsert_market_index

# 5) UniverseSnapshotJob (14-j, 14 §10)
class UniverseSnapshotJob(BaseJob):
    def __init__(
        self,
        config: UniverseSnapshotConfig,      # as_of_date / selector_config / run_id
        session_factory: Callable[[], Session],
        *,
        selector_factory: Callable[[Session], UniverseSelector] | None = None,
        name: str = "universe_snapshot",
        schedule: str | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None: ...
    # 흐름: select_with_details → SHA-256 config_hash → upsert_universe_snapshot

# 6) MissingDataCheckJob (14-k, 14 §13)
class MissingDataCheckJob(BaseJob):
    def __init__(
        self,
        config: MissingDataCheckConfig,      # start_date / end_date / market / symbols
        session_factory: Callable[[], Session],
        *,
        name: str = "missing_data_check",
        schedule: str | None = "30 18 * * 1-5",
        clock: Callable[[], datetime] | None = None,
    ) -> None: ...
    last_alert: MissingDataAlert    # run() 후 캡처용
    # 흐름: get_trading_days → 종목별 get_price_range → 차집합 = 결손 → MissingDataAlert
    # forward-fill 금지 — DB 변경 0건
```

### Scheduler 락 메커니즘

```python
class LockError(JobError):
    """동일 잡이 이미 실행 중일 때 발생 (14-j 단일 프로세스 락)."""

class Scheduler:
    def __init__(self) -> None:
        self._jobs: list[BaseJob] = []
        self._registry_lock = threading.Lock()
        self._busy: set[str] = set()

    def register(self, job: BaseJob) -> None: ...   # 중복 이름 ValueError
    def list_jobs(self) -> tuple[BaseJob, ...]: ...
    def get_job(self, name: str) -> BaseJob: ...    # 미등록 KeyError
    def is_running(self, name: str) -> bool: ...
    def run_job(self, name: str) -> JobResult: ... # 락 획득 후 동기 실행

    @contextmanager
    def _acquire_lock(self, name: str):
        # busy면 즉시 LockError (대기 없음, fail-fast)
        # try/finally로 잡 예외 시에도 해제 보장
```

특성:
- 단일 프로세스 내 동일 잡 동시 실행 차단 (fail-fast, 대기 없음)
- 다른 잡은 동시 실행 가능 (잡명별 격리)
- 잡 내부 예외 raise 시에도 락 해제 보장 (try/finally)
- 분산 락 (Redis SETNX / PostgreSQL advisory)은 후속 — 동일 인터페이스로 교체 가능

### MissingDataAlert 구조

```python
@dataclass(frozen=True)
class MissingDataEntry:
    symbol: str
    date: date_type
    market: str

@dataclass(frozen=True)
class MissingDataAlert:
    entries: tuple[MissingDataEntry, ...] = ()  # (symbol ASC, date ASC) 정렬
    total_trading_days: int = 0
    total_symbols: int = 0
    as_of_market: str = ""

    @property
    def missing_count(self) -> int: ...

# 결손은 그대로 보존 — 본 잡은 DB 변경 0건 (14.10 forward-fill 금지)
# JobResult.warnings에는 "결손 감지: 총 N건 / M종목" 요약만, 상세는 alert.entries
```

### 모듈 경계 준수

- BacktestEngine / Portfolio / StrategyEngine / ExecutionModel / CashManager: **변경 없음**
- API / Pydantic schemas / services: **변경 없음**
- application 테이블 / 시장데이터 모델 / 016 repositories 시그니처: **변경 없음** (활용만)
- 018 BaseProvider / LocalCsvProvider / PriceLoader: **변경 없음**
- 019 UniverseSelector: **변경 없음** (UniverseSnapshotJob에서 호출만)
- conditions/*: **변경 없음**
- 024 BaseJob ABC / 025 PykrxCollector / 026 AdjustedPriceProcessor / 027 repositories: **변경 없음** (활용만)

### Phase 1 골든 fixture 영향: **0건**

본 step은 신규 모듈만 작성. tests/backtest/ 161건 baseline 그대로 통과.

## Follow-ups

1. **분산 락 도입 (운용 단계)**:
   - Redis SETNX 또는 PostgreSQL advisory lock으로 멀티 프로세스 차단
   - 본 step의 `Scheduler._acquire_lock` 인터페이스 그대로 교체 가능

2. **cron 자동 실행 (운용 단계)**:
   - croniter 또는 APScheduler로 BaseJob.schedule 파싱 + 자동 트리거
   - 본 step의 Scheduler에 `start()` / `stop()` 추가 (백그라운드 스레드)

3. **MarketIndexCollector 정식 도입**:
   - 024 BaseCollector에 `collect_market_index(code, start, end) -> RawMarketIndexData` 메서드 추가
   - PykrxCollector 또는 별도 IndexCollector로 구현
   - MarketIndexJob의 `index_fetcher` 인자를 `collector` 합성으로 자연스럽게 통합

4. **알림 채널 통합 (14 §13)**:
   - JobResult.warnings + MissingDataAlert를 logger / Slack / 이메일에 자동 전송
   - 본 step에서는 logger 미통합 (호출자가 result/last_alert를 직접 처리)

5. **shares_outstanding 컬럼 + MarketCapProcessor 도입**:
   - 027 follow-up과 동일 — symbols 또는 별도 모델에 상장주식수 시계열 추가
   - 종가 × 상장주식수로 시가총액 시계열 자동 계산
   - 본 step의 DailyUpdate/Backfill 잡에 자연스럽게 통합 가능

6. **14번 문서 갱신 권고**:
   - §11A "예외 계층"에 LockError 추가 (Scheduler 락 정책 명시)
   - §6.2 DailyUpdate 흐름에 "5단계: AdjustedPriceProcessor 적용 (corporate_actions 있으면)" 명시
   - §13 결손 알림에 "MissingDataCheckJob — forward-fill 금지" 한 줄 추가
   - §14-k 신설 또는 §13 확장: MissingDataAlert / MissingDataEntry dataclass 명세

7. **DailyUpdateJob을 idempotent하게 만들 추가 검토**:
   - CorporateActionApplyJob처럼 매 호출마다 adj_*=close로 reset할지 여부
   - 현재는 collector가 매번 같은 adj_*를 반환해야 idempotent
   - 운용 시 collector adj_* 정확성에 의존 — 더 엄격하게 만들려면 reset 정책 통일 검토

## 메인 세션 마무리 체크

- [ ] status를 completed로 변경
- [ ] 작업로그/README.md 갱신 (Phase 11 ✅ 완료 표기)
- [ ] PM 호출 → 로드맵.md 갱신 (14-j, 14-k [x] / Phase 11 step 028 ✅)
- [ ] **test-engineer 호출 → "Phase 11 완료 검증"**
- [ ] ship-go 시: PM "Phase 11 완료" → 진행률 추이 + Phase 12 첫 step ⏭
- [ ] git commit (단일)
- [ ] **Phase 11 마지막 step**: ship-go 받으면 `git push origin main` (의무)
