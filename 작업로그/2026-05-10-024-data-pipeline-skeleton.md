---
date: 2026-05-10
agent: market-data-engineer
phase: 11
status: completed
roadmap_step: 024
roadmap_impact:
  - 14-b  # data_pipeline 패키지 구조
  - 14-c  # collectors 골격
  - 14-d  # processors 골격
related_docs:
  - 상세설계/14_data_pipeline_design.md
  - 상세설계/06_market_data_universe_design.md
  - 작업로그/2026-05-10-016-market-data-models-skeleton.md
  - 작업로그/2026-05-10-018-local-csv-provider-and-price-loader.md
---

# Step 024 — data_pipeline 패키지 구조 + collectors/processors/jobs 골격 (Phase 11 첫 step)

Phase 11 첫 step. 데이터 파이프라인 본체의 패키지 구조와 ABC 인터페이스만 도입. 실제 구현체(pykrx collector / 수정주가 processor / jobs)는 025~028 후속.

## Plan

### A) 패키지 구조 (14-b)
- [ ] `상세설계/14_data_pipeline_design.md` §3·§4·§5·§6 정독
- [ ] `backend/app/data_pipeline/__init__.py` 신규 — 패키지 진입점 + 공개 export
- [ ] `backend/app/data_pipeline/collectors/__init__.py` 신규
- [ ] `backend/app/data_pipeline/processors/__init__.py` 신규
- [ ] `backend/app/data_pipeline/jobs/__init__.py` 신규
- [ ] `backend/app/data_pipeline/exceptions.py` 신규 — CollectorError / ProcessorError / JobError / DataValidationError 등 (14번 §11 정합)

### B) BaseCollector 인터페이스 (14-c)
- [ ] `backend/app/data_pipeline/collectors/base.py` 신규
- 추상 클래스 `BaseCollector(ABC)`:
  - `collect_symbols(as_of_date) -> RawSymbolsData` (종목 마스터 수집)
  - `collect_daily_prices(symbols, start_date, end_date) -> RawDailyPricesData` (일봉 수집)
  - `collect_trading_calendar(start_date, end_date, market) -> RawCalendarData` (거래일 수집)
  - 또는 단일 진입점 `collect(target, params) -> RawData` 형태로 단순화 (PM 결정 — Issues에 명시)
- `RawSymbolsData / RawDailyPricesData / RawCalendarData` dataclass (frozen) — collector 출력 표준화
- 결정론: 출력은 (symbol ASC, date ASC) 정렬 강제
- 외부 네트워크 호출 0건 — ABC만, 실제 collector는 025

### C) BaseProcessor 인터페이스 (14-d)
- [ ] `backend/app/data_pipeline/processors/base.py` 신규
- 추상 클래스 `BaseProcessor(ABC)`:
  - `process(input_data) -> ProcessedData`
  - 또는 더 구체적으로 `validate / transform / load` 3단계 분리 (ETL 패턴)
- `ProcessedData / ValidationResult` dataclass — processor 출력 표준화
- 결정론: 같은 입력 같은 출력
- 본 step에서는 ABC만, 실제 processor (수정주가 재계산 / corporate_actions / 시가총액)는 026~027

### D) BaseJob + Scheduler 골격
- [ ] `backend/app/data_pipeline/jobs/base.py` 신규
- 추상 클래스 `BaseJob(ABC)`:
  - `run() -> JobResult`
  - `name: str` (job 식별자)
  - `schedule: str | None` (cron string, 028에서 활용)
- `JobResult` dataclass — 성공/실패 + 통계 + warnings
- `backend/app/data_pipeline/scheduler.py` 신규 — Scheduler 인터페이스만 (실제 cron/락 구현은 028)
- 본 step에서는 ABC만

### E) data_pipeline/__init__.py 공개 API
- BaseCollector / BaseProcessor / BaseJob / Scheduler / 예외 클래스 명시 export
- 16번 016 repositories와 18번 018 BaseProvider는 import만 (활용 가능 명시)

### F) 테스트
- [ ] `backend/tests/data_pipeline/__init__.py` 신규
- [ ] `backend/tests/data_pipeline/test_skeleton.py` 신규:
  - 패키지 import 가능
  - BaseCollector / BaseProcessor / BaseJob ABC 강제 (subclass 누락 시 TypeError)
  - dataclass frozen 검증
  - 예외 클래스 계층 검증
- 외부 네트워크 호출 0건 — 모든 테스트 in-memory

### G) 회귀
- [ ] 전체 pytest (Phase 1~10 회귀)
- [ ] ruff (변경 파일)
- [ ] 016 자기-소유 head 가드 1건 알려진 무관 (본 step에서 fix 분리 권고만, 실제 fix는 별도 mini-step 또는 후속)

### 절대 금지
- BacktestEngine / Portfolio / StrategyEngine / ExecutionModel / CashManager 절대 수정 (backtest-engine-developer 영역)
- API / Pydantic schemas / services 추가/수정 (backend-api-engineer 영역)
- application 테이블 / 시장데이터 모델 수정 (016·017 산출물 — 활용만)
- conditions/* 수정 (condition-author 영역)
- **025·026·027·028 영역 도입 금지**:
  - pykrx collector / 외부 fetch — 025
  - 수정주가 재계산 / corporate_actions 모델 — 026
  - 시가총액 시계열 / market_indices / universe_history — 027
  - 실제 jobs/scheduler 구현 — 028
- 016 repositories.py 시그니처 변경 금지 — 활용만 (collector가 활용할 인터페이스)
- 018 Provider/PriceLoader 수정 금지 — 활용만
- 결정론 깨기

### 다음 step (025) 인계 정보
- BaseCollector 시그니처 + RawData dataclass 명세
- 실제 PykrxCollector 구현 시 따를 인터페이스
- 예외 계층 (CollectorError 하위 RetryableError / FatalError 등 — 025 재시도 정책)

## Execution

신규 9개 파일 작성 (외부 fetch 0건, application/engine/conditions 미수정):

- `backend/app/data_pipeline/__init__.py:1` — 패키지 진입점 + 공개 API export (BaseCollector / BaseProcessor / BaseJob / Scheduler / 예외 7종 + Raw* 7종 + Processed/Validation 3종 + JobResult)
- `backend/app/data_pipeline/exceptions.py:1` — 예외 계층 (DataPipelineError 루트 / Collector·Processor·Job 단계별 / Retryable·Fatal 정책 직교 / DataValidationError)
- `backend/app/data_pipeline/collectors/__init__.py:1` — collectors 서브패키지 export
- `backend/app/data_pipeline/collectors/base.py:1` — BaseCollector ABC (3-메서드 분할: collect_symbols / collect_daily_prices / collect_trading_calendar) + RawSymbol/DailyPrice/Calendar Row+Data dataclass (frozen, tuple 필드) + 결정론 헬퍼 3종
- `backend/app/data_pipeline/processors/__init__.py:1` — processors 서브패키지 export
- `backend/app/data_pipeline/processors/base.py:1` — BaseProcessor ABC (단일 process 진입점, Generic[_InputT, _OutputT]) + ProcessedResult/ValidationResult/ValidationIssue dataclass (frozen) + _stats_to_tuple/_context_to_tuple 결정론 헬퍼
- `backend/app/data_pipeline/jobs/__init__.py:1` — jobs 서브패키지 export
- `backend/app/data_pipeline/jobs/base.py:1` — BaseJob ABC (run() 단일 진입점, name + schedule 메타) + JobResult dataclass (frozen)
- `backend/app/data_pipeline/scheduler.py:1` — Scheduler in-process 레지스트리 (register / list_jobs / get_job / run_job, 중복 등록 방지)

테스트:
- `backend/tests/data_pipeline/__init__.py:1` (빈 marker)
- `backend/tests/data_pipeline/test_skeleton.py:1` — 26 테스트 (패키지 import / ABC 강제 / frozen 검증 / 예외 계층 / 결정론 헬퍼 / Scheduler / RawData 컬렉션)

적용 정책 절번호:
- 14번 §3 (수집 대상: 종목 마스터/일봉/거래일/지수/corporate_actions) → BaseCollector 3-메서드 분할 근거
- 14번 §4.4 (Provider 추상화) + 14번 §5 (파이프라인 구조 collectors/processors/jobs/scheduler.py) → 패키지 레이아웃 그대로 채택
- 14번 §6.3 (재시도/백오프 1s→5s→30s→큐) → RetryableError(retry_after_seconds=...) 시그니처
- 14번 §7.2 (HARD_FAIL / SOFT_FAIL) → ValidationIssue.severity 분류 + ValidationResult.passed
- 14번 §13 (데이터 결손 알림) → JobResult.warnings/errors 필드
- 13번 §7 (수정주가) + 14번 §10 (생존편향) + 14번 §9 (look-ahead) → RawSymbolRow.delisting_date Optional, BaseCollector.collect_symbols(as_of_date) 시그니처에 docstring으로 명시
- CLAUDE.md #8 + 13번 §12 결정론 → frozen dataclass + tuple 필드 + 정렬 헬퍼

BaseCollector 시그니처 결정 — **3-메서드 분할** (단일 collect 진입점이 아님):
- 근거: 14번 §3에서 수집 대상이 명확히 3종(symbols/prices/calendar)이며, 호출 빈도/rate-limit 부담/갱신 주기가 모두 다름. 진입점을 분리해 부분 재시도와 잡 단위 스케줄링을 자연스럽게 함.
- corporate_actions / market_indices는 027~ 후속 step에서 별도 메서드 추가 예정 (본 step에서 강제하지 않음).

BaseProcessor 시그니처 결정 — **단일 `process(input_data) -> ProcessedResult` 진입점** (validate/transform/load 3단계 분리하지 않음):
- 근거: load(=DB 쓰기)는 repositories가 일관되게 담당하므로 processor는 검증+변환만 수행. 검증과 변환이 종종 동시 발생(수정주가 재계산 중 corporate_action 누락 발견 → 즉시 DataValidationError). 더 세분화가 필요한 processor는 process 내부에서 자체 분할 가능.
- Generic[_InputT, _OutputT]로 입력/출력 타입을 구현체별 자유롭게 결정.

BaseJob + Scheduler — **단일 `run() -> JobResult` + in-process 레지스트리만**:
- BaseJob: name + schedule(cron string, 028에서 활용) 메타 + run() 단일 메서드. 결과는 항상 JobResult로 wrap (스케줄러 단일 분기점).
- Scheduler: 본 step에서는 register/list_jobs/get_job/run_job(=동기 즉시 실행)만. cron 파싱 / 락 / 비동기 실행은 028.

예외 계층:
- DataPipelineError (루트)
  - CollectorError (수집 단계)
  - ProcessorError (가공 단계)
    - DataValidationError (14번 §7 검증 위배)
  - JobError (잡 실행 단계)
  - RetryableError (재시도 가능, retry_after_seconds 캐리)
  - FatalError (재시도 불가)
- 다중상속 구체 예외(예: RetryableCollectorError)는 025에서 정의 (본 step은 베이스만).

## Tests

명령:
```bash
cd backend && py -3 -m pytest tests/data_pipeline/ -v
cd backend && py -3 -m pytest -q  # 전체 회귀
cd backend && py -3 -m ruff check app/data_pipeline tests/data_pipeline
```

결과:
- 신규: `tests/data_pipeline/test_skeleton.py` 26건 모두 PASS (0.06초)
- 전체 회귀: **642 passed, 1 failed** (failed는 016 자기-소유 head 가드 `tests/market_data/test_alembic_market_data.py::test_new_revision_is_current_head` 하나, Plan에서 본 step 무관 사전 명시)
  - 이전 baseline 616 passed → 본 step +26 신규 테스트 → 642 passed (정확히 일치)
- ruff: All checks passed (자동 수정 후)

검증 항목 매핑 (14번 정책):
| 테스트 | 14번 절 |
|--------|--------|
| ABC 강제 (collector/processor/job 인스턴스화 차단) | §5 파이프라인 구조 |
| frozen dataclass (RawSymbol/DailyPrice/...Row+Data, ProcessedResult, JobResult) | CLAUDE.md #8 결정론 + 13.12 |
| 정렬 헬퍼 (_to_sorted_*_tuple, _stats_to_tuple, _context_to_tuple) | CLAUDE.md #8 결정론 |
| 예외 계층 (단일 DataPipelineError 루트로 catch) | §13 결손 알림 (호출자 단일 분기점) |
| RetryableError.retry_after_seconds | §6.3 재시도/백오프 |
| Scheduler 중복 등록 방지 / 등록 순서 보존 | §5 scheduler.py + 결정론 |
| ValidationResult.hard_fail_count / soft_fail_count | §7.2 HARD/SOFT FAIL |

Phase 1 골든 fixture 영향: **0건**. 본 step은 신규 모듈만 작성, BacktestEngine / Portfolio / StrategyEngine / ExecutionModel / CashManager / conditions / market_data / models 모두 미수정. 9지표 baseline 그대로.

## Issues

1. **016 자기-소유 head 가드 1건 known-failure 유지** — `tests/market_data/test_alembic_market_data.py::test_new_revision_is_current_head`. NEW_REVISION='9a4d2e1f6c10'이 head여야 하나 현재 head는 'b5e8d3c1a924'. Plan에서 사전 명시된 무관 항목. Phase 11 별도 mini-step으로 fix 권고.

2. **14번 문서에 §11 절번호 부재** — Plan에서 "예외 계층 14번 §11 정합" 표현은 §11(캐시/저장 전략)이 아니라 본 step에서 새로 정의한 예외 계층의 의도였음. 작업 로그 헤더의 매핑은 정확하지만 본 step에서 14번 문서에 §11A "예외 계층" 절을 신설하지는 않음 (인터페이스 결정만 본 step 책임, 문서 갱신은 메인 세션 + PM 판단).
   - 권장: 14번 §6.3 / §7 / §13 사이에 §11A "예외 계층" 보조 섹션을 PM이 추가하면 추후 025~028이 참조 명확.

3. **외부 정책 충돌 없음** — 13/14번 정책 위배 0건, 결정론 위배 0건, 외부 fetch 0건. 다른 에이전트 영역 침범 없음.

## Result

추가 모듈:
- `app.data_pipeline` 패키지 (collectors / processors / jobs 서브패키지 + scheduler + exceptions)
- 공개 API: BaseCollector / BaseProcessor / BaseJob / Scheduler / DataPipelineError·6종 / Raw·7종 / Processed·Validation·3종 / JobResult

다른 에이전트에 노출되는 인터페이스 (다음 step 025~028이 그대로 따름):

```python
# 025 PykrxCollector가 따를 인터페이스
class BaseCollector(ABC):
    def collect_symbols(self, as_of_date: date) -> RawSymbolsData: ...
    def collect_daily_prices(
        self, symbols: tuple[str, ...] | list[str], start_date: date, end_date: date
    ) -> RawDailyPricesData: ...
    def collect_trading_calendar(
        self, start_date: date, end_date: date, market: str
    ) -> RawCalendarData: ...

# 026 AdjustedPriceProcessor가 따를 인터페이스
class BaseProcessor(ABC, Generic[_InputT, _OutputT]):
    def process(self, input_data: _InputT) -> ProcessedResult[_OutputT]: ...

# 028 DailyUpdateJob 등이 따를 인터페이스
class BaseJob(ABC):
    def __init__(self, name: str, *, schedule: str | None = None) -> None: ...
    def run(self) -> JobResult: ...
```

dataclass 명세 (frozen=True, tuple 필드):
- RawSymbolRow / RawDailyPriceRow / RawCalendarRow
- RawSymbolsData(rows, as_of_date, source, warnings)
- RawDailyPricesData(rows, start_date, end_date, source, warnings)
- RawCalendarData(rows, start_date, end_date, market, source, warnings)
- ProcessedResult[_OutputT](output, validation, stats, warnings)
- ValidationResult(issues, passed) + ValidationIssue(severity, code, message, context)
- JobResult(job_name, success, started_at, finished_at, stats, warnings, errors)

예외 계층:
- DataPipelineError → CollectorError / ProcessorError(→ DataValidationError) / JobError / RetryableError(retry_after_seconds) / FatalError

## Follow-ups

1. **025 (PykrxCollector + 재시도)**:
   - BaseCollector 3-메서드 모두 구현
   - `RetryableCollectorError(CollectorError, RetryableError)` 다중상속 구체 예외 정의
   - `FatalCollectorError(CollectorError, FatalError)` 정의
   - 14번 §6.3 백오프 (1s → 5s → 30s → 큐) 구현
   - source="pykrx", warnings에 부분 결손/일시 오류 누적

2. **026 (AdjustedPriceProcessor + corporate_actions)**:
   - BaseProcessor[tuple[RawDailyPriceRow, ...] + corporate_actions, tuple[RawDailyPriceRow, ...]] 구현
   - 13.7 / 14.9.1 수정주가 재계산
   - DataValidationError severity 분류 (high<low → hard_fail, market_cap=None → soft_fail)
   - corporate_actions 모델 + 마이그레이션 본 step에서는 미수행

3. **027 (MarketCapProcessor + market_indices + universe_history)**:
   - 14.8 시가총액 시계열 (방법 2: 종가 × 상장주식수)
   - market_indices / universe_history 모델 + 마이그레이션
   - UniverseSelector(019)가 universe_history를 활용하도록 후속 검토

4. **028 (DailyUpdateJob / HistoricalBackfillJob + ConcreteScheduler)**:
   - DailyUpdateJob (14.6.2) / HistoricalBackfillJob (14.6.1) / CorporateActionApplyJob 구현
   - ConcreteScheduler(Scheduler 상속): cron 파싱 + 락 + 타임아웃
   - 결손 알림 (14.13) 채널 연결

5. **14번 문서 갱신 권고** — §11A "예외 계층" 보조 섹션을 PM이 추가하면 025~028이 참조 명확:
   ```
   §11A. 예외 계층
     - DataPipelineError (루트)
     - CollectorError / ProcessorError / JobError (단계별)
     - RetryableError(retry_after_seconds) / FatalError (재시도 정책)
     - DataValidationError ⊂ ProcessorError (§7 검증 위배)
   ```

6. **016 자기-소유 head 가드 fix mini-step 분리 권고** (NEW_REVISION='9a4d2e1f6c10' vs 현재 head 'b5e8d3c1a924').

7. **018 BaseProvider와의 책임 분리 docs 명시 완료** (`app/data_pipeline/__init__.py` docstring + `app/data_pipeline/collectors/base.py` docstring) — Provider=ingest 단일 진입점, Collector=ETL의 E만. PykrxProvider(향후)는 PykrxCollector를 합성 가능.

## 메인 세션 마무리 체크

- [ ] status를 completed로 변경
- [ ] 작업로그/README.md 갱신
- [ ] PM 호출 → 로드맵.md 갱신 (14-b, 14-c, 14-d [x] / Phase 11 step 024 ✅)
- [ ] git commit (Phase 11 마지막 step 아니므로 push 보류)
