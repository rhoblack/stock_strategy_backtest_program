---
date: 2026-05-10
agent: market-data-engineer
phase: 11
status: completed
roadmap_step: 025
roadmap_impact:
  - 14-e  # pykrx collector
  - 14-f  # 재시도 / 백오프
  - 14-g  # 데이터 검증
related_docs:
  - 상세설계/14_data_pipeline_design.md
  - 상세설계/06_market_data_universe_design.md
  - 작업로그/2026-05-10-024-data-pipeline-skeleton.md
---

# Step 025 — pykrx collector + 재시도/백오프 + 데이터 검증 (14-e·f·g)

024에서 도입한 BaseCollector ABC 위에 PykrxCollector 구현. 외부 fetch (pykrx 라이브러리) 사용 + 14 §6.3 재시도/백오프 정책 + 14 §7 데이터 검증.

## Plan

### A) PykrxCollector 구현 (14-e)
- [x] `상세설계/14_data_pipeline_design.md` §6 정독
- [x] `backend/app/data_pipeline/collectors/pykrx.py` 신규
- BaseCollector(024) 상속:
  - collect_symbols(as_of_date) → pykrx.stock.get_market_ticker_list / get_market_ticker_name
  - collect_daily_prices(symbols, start_date, end_date) → pykrx.stock.get_market_ohlcv_by_date(adjusted=True/False) + get_market_cap_by_date
  - collect_trading_calendar(start_date, end_date, market) → pykrx.stock.get_previous_business_days
- pykrx 출력을 RawSymbolsData / RawDailyPricesData / RawCalendarData로 정규화
- 결정론: 출력 정렬은 BaseCollector `_to_sorted_*` 헬퍼 사용

### B) 재시도/백오프 정책 (14-f, 14 §6.3)
- [x] `backend/app/data_pipeline/collectors/retry.py` 신규 — `retry_call(fn, ...)` 함수 + `@retry_on_retryable()` 데코레이터
- 정책: 1s → 5s → 30s → 큐 (마지막 재시도 후 RetryableError raise)
- [x] `RetryableCollectorError(CollectorError, RetryableError)` 다중상속 구체 예외 정의 (retry.py)
- [x] `FatalCollectorError(CollectorError, FatalError)` 다중상속 구체 예외 정의 (retry.py)
- 재시도 대상: RetryableError (그리고 RetryableCollectorError)
- 재시도 비대상: FatalError (그리고 FatalCollectorError) / 일반 Exception
- jitter 없음 (CLAUDE.md #8 결정론). retry_after_seconds 명시 시 backoff 단계 override 허용

### C) 데이터 검증 (14-g, 14 §7)
- [x] `backend/app/data_pipeline/collectors/validators.py` 신규
- 14 §7.2 HARD_FAIL / SOFT_FAIL 정책 (024 ValidationIssue.severity)
- HARD_FAIL: SYMBOL_FORMAT_INVALID / SYMBOL_NAME_EMPTY / SYMBOL_MARKET_INVALID / SYMBOL_DELISTED_BEFORE_LISTED / PRICE_CLOSE_NULL_OR_NONPOSITIVE / PRICE_ADJ_CLOSE_NULL_OR_NONPOSITIVE / PRICE_SYMBOL_FORMAT_INVALID / OHLC_NEGATIVE / OHLC_INCONSISTENT_HIGH_LT_LOW / CALENDAR_EMPTY / CALENDAR_MARKET_INVALID
- SOFT_FAIL: MARKET_CAP_MISSING / VOLUME_ZERO / HIGH_EQ_LOW
- ValidationResult.issues는 (code ASC, severity ASC) 정렬 보장
- raise_on_hard_fail 옵션 (PykrxCollector는 True 기본)

### D) 외부 fetch 격리 (테스트 용이성)
- [x] pykrx 호출은 PykrxCollector 내부 `_fetch_*` 헬퍼 5종으로 격리:
  - `_fetch_ticker_list / _fetch_ticker_name / _fetch_ohlcv / _fetch_market_cap / _fetch_business_days`
- [x] pykrx import는 `_import_stock()` lazy import — 모듈 import 자체는 pykrx 미설치여도 무관
- [x] 테스트는 `_fetch_*` 메서드를 MagicMock으로 교체 → 외부 호출 0건
- [x] `pyproject.toml`에 `network` 마커 등록 + 기본 실행에서 제외 (`addopts = "-ra --strict-markers -m 'not network'"`)
- pykrx 일반 Exception은 RetryableCollectorError로 분류, ImportError는 FatalCollectorError로 분류 (`_classify_exception`)

### E) 테스트
- [x] `backend/tests/data_pipeline/test_pykrx_collector.py` 신규 (34건)
  - 헬퍼 (_format_date / _parse_date) 단위
  - collect_symbols 정상 흐름 + HARD/SOFT 분기 + validate=False 우회
  - collect_daily_prices 정상 흐름 + 정렬 결정론 + close=0 HARD raise + market_cap 결손 SOFT 통과 + 빈 결과 row 미생성 + start>end FatalCollectorError
  - collect_trading_calendar 정상 + 잘못된 market FatalCollectorError + 빈 결과 CALENDAR_EMPTY HARD
  - retry 적용 — RetryableCollectorError 재시도 / FatalCollectorError 재시도 없음
  - lazy import — pykrx 미설치 시 FatalCollectorError (monkeypatch builtins.__import__)
  - 생성자 검증 (default name / 잘못된 markets)
  - validators 단위 (HARD/SOFT 매핑 모두)
  - 결정론 — 동일 mock 입력 두 번 호출 결과 동일
- [x] `backend/tests/data_pipeline/test_retry.py` 신규 (17건)
  - DEFAULT_BACKOFF_SECONDS == (1.0, 5.0, 30.0) 정책 일치
  - 정상 1회 호출
  - RetryableError 부분 재시도 (sleep 시퀀스 검증)
  - 모든 재시도 소진 후 raise (= 큐 보류 신호)
  - retry_after_seconds override
  - FatalError / 일반 Exception 즉시 raise
  - RetryableCollectorError / FatalCollectorError 다중상속 동작
  - 데코레이터 (@retry_on_retryable) 동등성 + functools.wraps 유지
  - 빈 backoff 시퀀스 (재시도 0회)
  - sleep_fn 시그니처 (Callable[[float], None])
  - 결정론 (jitter 없음 — 동일 시나리오 반복 시 sleep 시퀀스 동일)

### F) 회귀
- [x] 전체 pytest 통과 (alembic 사전 회귀 1건은 본 step과 무관 — baseline에서도 동일하게 실패)
- [x] ruff clean (변경 파일 모두)

### 절대 금지
- BacktestEngine / Portfolio / StrategyEngine / ExecutionModel / CashManager 절대 수정
- API / Pydantic schemas / services 추가/수정
- application 테이블 / 시장데이터 모델 / 016 repositories.py / 018 BaseProvider 시그니처 변경
- conditions/* 수정
- **026·027·028 영역 도입 금지**:
  - 수정주가 재계산 / corporate_actions 모델 — 026
  - 시가총액 시계열 / market_indices / universe_history — 027
  - jobs/scheduler 실제 구현 — 028
- 024 BaseCollector / BaseProcessor / BaseJob ABC 시그니처 변경 금지 — 활용만
- pykrx 호출 시 결정론 깨기 (jitter random.random() 직접 사용 금지)

### 다음 step (026) 인계 정보
- PykrxCollector 인터페이스 (026 BaseProcessor가 collector 결과를 입력으로 받음)
- ValidationResult 활용 패턴
- corporate_actions 데이터 collector 추가 필요 여부 (026이 corporate_actions 모델 정의 후 별도)

## Execution

신규 파일 (5건):

- `backend/app/data_pipeline/collectors/retry.py` (전체 ~210행)
  - `DEFAULT_BACKOFF_SECONDS = (1.0, 5.0, 30.0)` (14 §6.3)
  - `retry_call(fn, *args, backoff, sleep_fn, **kwargs) -> _R` (line 53~)
  - `retry_on_retryable(backoff, sleep_fn) -> Decorator` (line 110~)
  - `RetryableCollectorError(CollectorError, RetryableError)` 다중상속 (line 152~)
  - `FatalCollectorError(CollectorError, FatalError)` 다중상속 (line 175~)
- `backend/app/data_pipeline/collectors/validators.py` (전체 ~290행)
  - `validate_symbol_row(row) -> list[ValidationIssue]`
  - `validate_daily_price_row(row) -> list[ValidationIssue]` (14 §7.1)
  - `validate_symbols_data(data, raise_on_hard_fail) -> ValidationResult`
  - `validate_daily_prices_data(data, raise_on_hard_fail) -> ValidationResult`
  - `validate_calendar_data(data, raise_on_hard_fail) -> ValidationResult`
  - `_finalize_result` 내부 헬퍼 — issues를 (code ASC, severity ASC) 정렬
- `backend/app/data_pipeline/collectors/pykrx.py` (전체 ~510행)
  - `PykrxCollector(BaseCollector)` 본체
  - `_fetch_*` 5종 (lazy import + pykrx 호출)
  - `_classify_exception` — pykrx 일반 Exception → RetryableCollectorError
  - `_merge_price_frames` — raw + adjusted + market_cap → RawDailyPriceRow 변환
  - `_format_date / _parse_date` 모듈 함수
- `backend/tests/data_pipeline/test_retry.py` (17 테스트)
- `backend/tests/data_pipeline/test_pykrx_collector.py` (34 테스트)

수정 파일 (3건):

- `backend/app/data_pipeline/collectors/__init__.py` — 신규 export 추가 (PykrxCollector / retry / validators)
- `backend/app/data_pipeline/__init__.py` — 신규 export 패키지 최상위 노출
- `backend/pyproject.toml` — `network` 마커 등록 + 기본 실행에서 제외

## Tests

```text
$ pytest tests/data_pipeline/ -q
77 passed in 0.46s

$ pytest -q  (전체)
1 failed, 693 passed, 8 warnings in 21.19s
  - failed: tests/market_data/test_alembic_market_data.py::test_new_revision_is_current_head
  - 사전 존재 회귀 (baseline 642 + 알렘빅 1 fail 동일) — 본 step과 무관

$ ruff check (변경 파일)
All checks passed!
```

신규 51건 (17 retry + 34 pykrx) 모두 통과.

검증 항목 매핑 (14 §7.1 / §7.2):

| ValidationIssue.code | severity | 14 §7 매핑 | 테스트 |
|---|---|---|---|
| SYMBOL_FORMAT_INVALID | hard_fail | §7.2 (스키마 위반) | test_validate_symbol_row_format_violation_is_hard / test_collect_symbols_validates_symbol_format |
| SYMBOL_MARKET_INVALID | hard_fail | §7.2 | test_validate_symbol_row_invalid_market_is_hard |
| SYMBOL_DELISTED_BEFORE_LISTED | hard_fail | §7.2 + 14.10 | test_validate_symbol_row_delisted_before_listed_is_hard |
| PRICE_CLOSE_NULL_OR_NONPOSITIVE | hard_fail | §7.2 (사용자 종목 일봉 결손) | test_validate_daily_price_row_close_zero_is_hard / test_collect_daily_prices_raises_on_hard_fail_close |
| OHLC_INCONSISTENT_HIGH_LT_LOW | hard_fail | §7.1 OHLC 정합성 | test_validate_daily_price_row_high_lt_low_is_hard |
| MARKET_CAP_MISSING | soft_fail | §7.2 (시가총액 결손) | test_validate_daily_price_row_market_cap_missing_is_soft / test_collect_daily_prices_soft_fail_market_cap_missing |
| VOLUME_ZERO | soft_fail | 14.10 / 13.4.4 (거래정지) | test_validate_daily_price_row_volume_zero_is_soft |
| HIGH_EQ_LOW | soft_fail | 13.4.4 (한가) | test_validate_daily_price_row_high_eq_low_is_soft |
| CALENDAR_EMPTY | hard_fail | §7.2 (거래일 캘린더 결손) | test_collect_trading_calendar_empty_raises_hard_fail / test_validate_calendar_data_empty_is_hard_fail |

## Issues

1. **사전 존재 회귀 (본 step 무관)**: `tests/market_data/test_alembic_market_data.py::test_new_revision_is_current_head`가 NEW_REVISION을 `9a4d2e1f6c10`로 기대하지만 실제 head는 `b5e8d3c1a924`. 누군가 마이그레이션을 추가했지만 본 테스트의 NEW_REVISION 상수를 갱신하지 않은 것으로 보임. baseline(우리 변경 stash 후)에서도 동일하게 실패하므로 본 step과 무관 — alembic은 본 step 수정 금지 영역.

2. **pykrx 미설치**: 본 환경에 pykrx가 설치돼 있지 않지만 lazy import로 격리해 모듈 import / 단위 테스트는 모두 동작. 운용 환경에서는 별도로 `pip install pykrx` 필요. (pyproject.toml의 dependencies에 추가는 보류 — pykrx는 KRX 스크래핑 기반이므로 안정성 운영 정책을 026 이후 jobs/scheduler 도입 시 결정하는 게 자연스러움.)

3. **listing_date 폴백**: 본 collector는 `as_of_date`를 종목 마스터의 `listing_date` 폴백으로 사용. 정확한 listing_date는 별도 KRX 메타 호출이 필요하지만 본 step 범위 밖 (027 이후 보강). 검증 로직(SYMBOL_DELISTED_BEFORE_LISTED)은 동작하지만 실 데이터 정확성은 026 이후 보강 필요.

4. **delisting_date / 플래그 미수집**: `is_etf` / `is_etn` / `is_managed` 등은 별도 pykrx 호출 또는 KRX 페이지 파싱이 필요. 본 step에서는 기본값 False로 둠. 027 이후 보강.

5. **pykrx 예외 타입 광범위**: `_classify_exception`은 보수적으로 모두 RetryableCollectorError로 분류. 운용 데이터 수집 후 실제 예외 패턴이 모이면 028 이후 정교화 필요.

## Result

### 적용 정책 절번호
- 14 §3.1 / §3.2 / §3.3 — 수집 대상 데이터 (종목 마스터 / 일봉 / 거래일)
- 14 §4.1 — pykrx 1차 소스
- 14 §6 — 수집 시나리오 (collect_symbols/prices/calendar 진입점)
- 14 §6.3 — 재시도 / 백오프 (1s → 5s → 30s → 큐)
- 14 §6.4 — KRX 차단 대응의 retry 토대
- 14 §7.1 / §7.2 — 자동 검증 + HARD/SOFT 분류
- 14 §10 — 결손 정책 (forward-fill 금지, row 미생성)
- 13.4.4 — 거래정지 / 한가 SOFT 분류
- 13.7 — close + adj_close 둘 다 NOT NULL (HARD)
- CLAUDE.md #5 (수정주가) / #8 (결정론) / #10 (생존편향)

### 인터페이스 시그니처 (다른 에이전트 사용 진입점)

```python
# backend/app/data_pipeline/collectors/pykrx.py
class PykrxCollector(BaseCollector):
    def __init__(
        self,
        name: str = "pykrx",
        *,
        backoff: tuple[float, ...] = (1.0, 5.0, 30.0),
        sleep_fn: Callable[[float], None] | None = None,
        validate: bool = True,
        markets: tuple[str, ...] = ("KOSPI", "KOSDAQ"),
    ) -> None: ...

    def collect_symbols(self, as_of_date: date) -> RawSymbolsData: ...
    def collect_daily_prices(
        self, symbols: tuple[str, ...] | list[str],
        start_date: date, end_date: date,
    ) -> RawDailyPricesData: ...
    def collect_trading_calendar(
        self, start_date: date, end_date: date, market: str,
    ) -> RawCalendarData: ...
```

```python
# backend/app/data_pipeline/collectors/retry.py
DEFAULT_BACKOFF_SECONDS: tuple[float, ...] = (1.0, 5.0, 30.0)

def retry_call(
    fn: Callable[..., R],
    *args,
    backoff: tuple[float, ...] = DEFAULT_BACKOFF_SECONDS,
    sleep_fn: Callable[[float], None] = time.sleep,
    **kwargs,
) -> R: ...

def retry_on_retryable(
    backoff: tuple[float, ...] = DEFAULT_BACKOFF_SECONDS,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> Callable[[Callable], Callable]: ...

class RetryableCollectorError(CollectorError, RetryableError):
    def __init__(self, message: str = "", *, retry_after_seconds: float | None = None): ...

class FatalCollectorError(CollectorError, FatalError): ...
```

```python
# backend/app/data_pipeline/collectors/validators.py
def validate_symbol_row(row: RawSymbolRow) -> list[ValidationIssue]: ...
def validate_daily_price_row(row: RawDailyPriceRow) -> list[ValidationIssue]: ...
def validate_symbols_data(data: RawSymbolsData, *, raise_on_hard_fail: bool = False) -> ValidationResult: ...
def validate_daily_prices_data(data: RawDailyPricesData, *, raise_on_hard_fail: bool = False) -> ValidationResult: ...
def validate_calendar_data(data: RawCalendarData, *, raise_on_hard_fail: bool = False) -> ValidationResult: ...
```

### 모듈 경계 준수

- BacktestEngine / Portfolio / StrategyEngine / ExecutionModel / CashManager: **변경 없음**
- API / Pydantic schemas / services: **변경 없음**
- application 테이블 / 시장데이터 모델 / repositories: **변경 없음**
- 018 BaseProvider / LocalCsvProvider / PriceLoader: **변경 없음**
- 019 UniverseSelector: **변경 없음**
- conditions/*: **변경 없음**
- 024 ABC 시그니처: **변경 없음** (활용만)
- 026/027/028 영역 (수정주가 재계산 / corporate_actions / market_indices / jobs/scheduler 실제 구현): **도입 없음**

### Phase 1 골든 fixture 영향

엔진 변경 0건이므로 9지표 frozen expected 일치 유지. backtest 테스트는 본 step과 무관하게 통과.

## Follow-ups

다음 step (026)에서 사용할 인계 정보:

1. **PykrxCollector 결과를 026 BaseProcessor 입력으로 사용**
   - 026 `AdjustedPriceProcessor`는 `RawDailyPricesData` + `corporate_actions`를 입력으로 받아 adj_* 재계산
   - 본 collector의 adj_*는 pykrx의 `adjusted=True` 기본 값 — 026에서 정밀 재계산으로 덮어씀

2. **corporate_actions collector 추가 검토**
   - 본 step은 corporate_actions를 수집하지 않음
   - 026이 corporate_actions 모델 정의 후, 별도 `_fetch_corporate_actions` 메서드를 PykrxCollector에 추가하거나 별도 collector로 분리 결정

3. **listing_date / delisting_date / 플래그 보강**
   - 027 시가총액 / universe_history 작업 시 정확한 listing_date 보강 필요

4. **pyproject.toml 의존성**
   - 운용 환경 도입 시 `pykrx` 의존성을 `[project.optional-dependencies].data` 그룹으로 분리 검토 (028 jobs/scheduler 도입 시점)

5. **14번 문서 갱신 필요 여부**
   - 본 step은 14 §6 / §7 정책을 그대로 구현 — 문서 갱신 불필요
   - 다만 §7.2 SOFT_FAIL에 `HIGH_EQ_LOW`(한가) 코드를 명시적으로 추가하면 정교 — Follow-up 후보

6. **알렘빅 사전 회귀 후속 처리**
   - `tests/market_data/test_alembic_market_data.py`의 NEW_REVISION 상수가 head와 불일치 (`9a4d2e1f6c10` vs `b5e8d3c1a924`)
   - 별도 step으로 정정 필요 (본 step 영역 아님)

## 메인 세션 마무리 체크

- [ ] status를 completed로 변경
- [ ] 작업로그/README.md 갱신
- [ ] PM 호출 → 로드맵.md 갱신 (14-e, 14-f, 14-g [x] / Phase 11 step 025 ✅)
- [ ] git commit (Phase 11 마지막 step 아니므로 push 보류)
