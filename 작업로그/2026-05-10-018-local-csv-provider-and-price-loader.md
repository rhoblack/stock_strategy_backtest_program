---
date: 2026-05-10
agent: market-data-engineer
phase: 9
status: completed
roadmap_step: 018
roadmap_impact:
  - 06-c  # BaseProvider 인터페이스
  - 06-d  # LocalCsvProvider 구현
  - 06-e  # PriceLoader (BacktestEngine에 DataFrame 공급)
related_docs:
  - 상세설계/06_market_data_universe_design.md
  - 상세설계/14_data_pipeline_design.md
  - 상세설계/13_backtest_accuracy_policy_design.md
  - 작업로그/2026-05-10-016-market-data-models-skeleton.md
---

# Step 018 — LocalCsvProvider + PriceLoader (016b)

016에서 시장데이터 DB 모델(symbols/daily_prices/trading_calendar) + repositories CRUD 10종을 구현. 본 step에서는 **데이터 공급 계층**을 도입:
- `BaseProvider`: provider 인터페이스 (LocalCsv / Pykrx 등 공통)
- `LocalCsvProvider`: CSV 파일을 읽어 repositories.upsert_*로 DB 적재 (개발/테스트용)
- `PriceLoader`: repositories.get_price_range를 BacktestEngine이 기대하는 pandas DataFrame 형식으로 변환

PykrxProvider / pykrx collector는 본 step 영역 밖 — Phase 11.

## Plan

### A) BaseProvider 인터페이스 (06-c)
- [ ] `상세설계/06_market_data_universe_design.md` Provider 절 정독
- [ ] `상세설계/14_data_pipeline_design.md` 수집 인터페이스 절 정독
- [ ] `backend/app/market_data/provider.py` 신규
  - 추상 클래스 또는 Protocol: `fetch_symbols`, `fetch_daily_prices`, `fetch_trading_calendar` (필요 시 시그니처 확정)
  - 또는 ingest 메서드 단일 진입점: `ingest_into(session, symbols=..., date_range=...)` — 실제 fetch 책임은 구현체로 위임
  - 결정론: 정렬 + tie-breaker (symbol ASC, date ASC)
  - 외부 fetch 0건 — 본 클래스는 인터페이스만

### B) LocalCsvProvider 구현 (06-d)
- [ ] `backend/app/market_data/providers/local_csv.py` 또는 `market_data/local_csv.py` 신규
- 입력 형식 (CSV):
  - `symbols.csv`: symbol, name, market, sector, listing_date, delisting_date, is_etf, is_etn, is_spac, is_preferred
  - `daily_prices.csv`: symbol, date, open, high, low, close, volume, adj_open, adj_high, adj_low, adj_close, adj_volume, market_cap
  - `trading_calendar.csv`: market, date, is_trading_day, holiday_name
- ingest:
  - pandas.read_csv로 읽기 → repositories.upsert_symbol / bulk_upsert_daily_prices / upsert_trading_day 호출
  - **adj_close + close 모두 NOT NULL** 검증 (13.7) — 결손 시 명확한 에러
  - 결손 봉(`is_trading_day=true`인데 daily_prices에 row 없음)은 forward-fill 금지 — 그대로 누락 보존 (14.10)
- 외부 네트워크 호출 0건 (pykrx import 금지)

### C) PriceLoader (06-e)
- [ ] `backend/app/market_data/price_loader.py` 신규
- 인터페이스:
  - `load(session, symbol, start_date, end_date) -> pd.DataFrame`
  - 컬럼: `date` (인덱스 또는 컬럼) + `open/high/low/close/volume + adj_open/adj_high/adj_low/adj_close/adj_volume + market_cap`
  - **next_open / next_close / next_volume / next_date 컬럼 자동 채움** (BacktestEngine이 기대하는 형식, 015 정합)
  - **마지막 row의 next_*는 NaN** (015 정합)
- 13.7: 가격 조건/체결은 adj_* 사용 — DataFrame이 둘 다 노출
- 14.10: 결손 봉은 row 없음 (forward-fill 금지)
- 결정론: date ASC 정렬

### D) 디렉토리 fixture (테스트용)
- [ ] `backend/tests/market_data/fixtures/csv/` 디렉토리 신규
- 작은 sample CSV 파일 3개 (10~30 row 정도): 회귀 테스트용 + LocalCsvProvider 검증용

### E) 테스트
- [ ] `backend/tests/market_data/test_provider.py` 신규 — BaseProvider 인터페이스 검증 (Protocol 호환 등)
- [ ] `backend/tests/market_data/test_local_csv_provider.py` 신규
  - 정상 ingest (3 종목, 10 거래일)
  - close + adj_close NOT NULL 위반 시 명확한 에러
  - delisting 종목 보존 (생존편향 차단)
  - bulk_upsert UniqueConstraint (symbol, date) 충돌 처리
  - trading_calendar의 비거래일은 daily_prices에 row 없음 검증
- [ ] `backend/tests/market_data/test_price_loader.py` 신규
  - load 시 컬럼 명세 (adj_* + next_* 포함)
  - 마지막 row next_* NaN
  - date ASC 정렬
  - 빈 결과 (해당 기간 데이터 없음) 처리
  - 015 BacktestEngine 호환: load 결과를 BacktestEngine 입력으로 사용 시 동작

### F) 회귀
- [ ] 전체 pytest (Phase 1 골든 영향 없음 — engine 변경 0건)
- [ ] ruff (변경 파일)
- [ ] alembic 회귀 (016 마이그레이션 영향 없음)

### 절대 금지
- BacktestEngine / Portfolio / StrategyEngine / ExecutionModel / CashManager 절대 수정 (backtest-engine-developer 영역)
- API 라우트 / Pydantic schemas / services 추가/수정 (backend-api-engineer 영역)
- application 테이블(strategies / backtest_runs / trade_groups / ...) 수정 금지
- conditions/* 수정 (condition-author 영역)
- **pykrx 또는 외부 데이터 fetch 코드 (네트워크 호출 0건)** — Phase 11에서
- **PykrxProvider / data_pipeline collectors / processors / jobs / scheduler 작성 금지** — Phase 11에서
- corporate_actions / market_indices / universe_history 모델 수정 (Phase 11)
- 수정주가 재계산 로직 (Phase 11 — adj_* 컬럼은 입력 CSV에서 그대로 받음)
- 결정론 깨기 (정렬 누락, dict 순회 의존)
- forward-fill (14.10 위반)

### 다음 step (019) 인계 정보 (필수 보고)
- BaseProvider / LocalCsvProvider / PriceLoader 시그니처
- DataFrame 컬럼 명세 (next_* 포함)
- get_universe_at_date를 UniverseSelector가 어떻게 위임할지

## Execution

### 신규 파일

| 파일 | 라인 | 역할 |
|---|---:|---|
| `backend/app/market_data/provider.py` | 134 | BaseProvider (ABC) + IngestResult dataclass + 결정론 헬퍼 (_sorted_*) |
| `backend/app/market_data/local_csv.py` | 343 | LocalCsvProvider — symbols.csv / daily_prices.csv / trading_calendar.csv → repositories.* 위임 |
| `backend/app/market_data/price_loader.py` | 194 | PriceLoader — repositories.get_price_range → BacktestEngine 호환 DataFrame 변환 |
| `backend/tests/market_data/fixtures/csv/sample/symbols.csv` | 5 | 4 종목 (3 활성 + 1 폐지) |
| `backend/tests/market_data/fixtures/csv/sample/daily_prices.csv` | 16 | 3 종목 × 5 거래일 = 15 row |
| `backend/tests/market_data/fixtures/csv/sample/trading_calendar.csv` | 9 | 8 캘린더 (5 거래일 + 3 휴장) |
| `backend/tests/market_data/fixtures/csv/with_missing/symbols.csv` | 2 | 005930만 |
| `backend/tests/market_data/fixtures/csv/with_missing/daily_prices.csv` | 5 | 4 거래일 (1/4 결손) |
| `backend/tests/market_data/fixtures/csv/with_missing/trading_calendar.csv` | 6 | 5 거래일 (1/4은 거래일이지만 daily_prices에 결손) |
| `backend/tests/market_data/fixtures/csv/bad_missing_adj/symbols.csv` | 2 | 005930 |
| `backend/tests/market_data/fixtures/csv/bad_missing_adj/daily_prices.csv` | 2 | adj_close 빈 칸 — 13.7 위반 케이스 |
| `backend/tests/market_data/test_provider.py` | 96 | BaseProvider ABC / IngestResult / 결정론 헬퍼 검증 (7건) |
| `backend/tests/market_data/test_local_csv_provider.py` | 244 | LocalCsvProvider 정상/생존편향/13.7/14.10/결정론/필터/에러 (14건) |
| `backend/tests/market_data/test_price_loader.py` | 215 | PriceLoader 컬럼 명세/next_*/15 정합/14.10/빈 결과/엔진 호환 (10건) |

### 수정 파일

| 파일 | 변경 |
|---|---|
| `backend/app/market_data/__init__.py` | 모듈 docstring을 2~4단계 진행 상황 반영하도록 갱신 (export는 그대로) |

### 적용 정책 절번호

- **06번** §3 (PriceLoader 위치), §4 (MarketDataProvider 인터페이스 — 본 step은 ingest 단일 진입점으로 단순화), §5 (LocalCsvProvider), §6 (종목 마스터 컬럼), §7 (일봉 adj_* 필드), §8 (UniverseSelector — 다음 step 위임 진입점만 마련)
- **13번** §7 (수정주가 — close + adj_close 모두 NOT NULL), §13.13 (생존편향 보존), §13.15 (look-ahead bias 차단), §13.12 (결정론 정렬)
- **14번** §3 (수집 대상 데이터 컬럼), §4.4 (Provider 추상화), §10 / §10.2 (생존편향 — delisting_date NULL 허용), §10 결손 정책 (forward-fill 금지), §12 (백테스트 실행 시 데이터 로드 — PriceLoader 책임), §14 (거래일 캘린더 구조), §17 (MVP 범위 — LocalCsvProvider 사용)
- **CLAUDE.md** #5 (수정주가 기본), #8 (결정론), #10 (생존편향)

### 핵심 설계 결정

1. **BaseProvider는 ABC + 단일 진입점 `ingest_into(session, ...)`**:
   - typing.Protocol도 후보였으나, ABC가 (a) 공통 헬퍼(_sorted_*) 보유 자리, (b) 누락 시 즉시 TypeError 발생으로 안전 — 두 이유로 채택.
   - 06번 §4의 fetch_*(get_symbols/get_daily_prices/...) 다중 메서드 시그니처는 본 step 범위 밖 — Phase 11 PykrxProvider 도입 시 함께 확정.
   - **`ingest_into` 단일 인터페이스로 호출자(서비스/CLI)가 provider 종류와 무관하게 동일하게 사용 가능**.
2. **`IngestResult` dataclass(frozen=True)**: 적재 통계(symbols/daily_prices/trading_days 카운트 + warnings)를 분리 노출. 호출자가 결과 검증/로깅에 활용.
3. **LocalCsvProvider의 결손/13.7 정책 강제**:
   - `_REQUIRED_PRICE_COLUMNS` 12개 명시 — adj_* 빈 칸 시 `_parse_float`가 ValueError(`adj_close` 메시지 포함).
   - 결손 봉을 자동 채우지 않음 — 14.10 강제.
   - `delisting_date` 빈 칸은 NULL로 보존 — 13.13 폐지 종목 보존.
4. **PriceLoader의 next_* 컬럼 명세** (015 정합):
   - `next_open / next_close / next_volume / next_date` 자동 채움 (단순 shift(-1)).
   - 마지막 row의 next_*는 NaN/NaT — BacktestEngine이 마지막 봉 매수/매도 자동 skip (015 검증 완료).
   - **`adj_next_open / adj_next_close`도 동일 값으로 추가 노출** — ExecutionModel.get_entry_price가 use_adjusted_price=True일 때 prefix=`adj_`로 컬럼명을 만드는 분기 호환 (현재 engine.py가 직접 row["next_open"]을 읽지만 잠재적 호환성 확보).
5. **빈 결과는 빈 DataFrame** (예외 안 던짐) — 호출자가 처리. 컬럼 명세는 동일 유지.
6. **CSV fixture를 3개 디렉토리로 분리** (sample / with_missing / bad_missing_adj) — 후속 step(019 UniverseSelector / 020+ Phase 11)에서도 sample을 재활용 가능.

## Tests

### 명령

```text
./.venv/Scripts/python.exe -m pytest tests/market_data/test_provider.py tests/market_data/test_local_csv_provider.py tests/market_data/test_price_loader.py
  → 31 passed
./.venv/Scripts/python.exe -m pytest tests/integration/test_phase1_golden.py
  → 6 passed (Phase 1 골든 영향 없음)
./.venv/Scripts/python.exe -m pytest
  → 496 passed, 1 failed (test_alembic_market_data::test_new_revision_is_current_head — 016 자기-소유 head 가드, 작업 지시에 의해 본 step 범위 밖)
./.venv/Scripts/python.exe -m ruff check <변경 파일 7개>
  → All checks passed!
```

### 신규 테스트 분포 (31건)

| 파일 | 건수 | 내용 |
|---|---:|---|
| test_provider.py | 7 | ABC 강제 / 인스턴스화 / IngestResult 기본값 + 합계 / 결정론 헬퍼 3종 |
| test_local_csv_provider.py | 14 | symbols/daily_prices/trading_calendar 적재 / 13.13 폐지 보존 / 13.15 look-ahead / 13.7 adj_close 누락 / 14.10 결손 보존 / 결정론(idempotent) / symbol+date 필터 / 에러 케이스 (root 없음/symbols 없음/optional 없음/필수 컬럼 없음) |
| test_price_loader.py | 10 | 컬럼 명세(11+6) / 13.7 raw+adj 둘 다 / next_* shift(-1) / 마지막 row NaN/NaT / adj_next_* 미러 / date ASC / 14.10 결손 / 빈 결과 2종 / 015 BacktestEngine 호환 smoke |

### 13/14 정책 검증 매핑

| 정책 | 테스트 케이스 |
|---|---|
| 13.7 (close + adj_close NOT NULL) | `test_missing_adj_close_raises_value_error` (LocalCsv) / `test_load_adj_and_raw_prices_both_present` (PriceLoader) |
| 13.13 / 14.10 (생존편향 — 폐지 종목 보존) | `test_delisting_date_preserved_for_delisted_symbol` / `test_active_symbol_has_null_delisting_date` |
| 13.15 (look-ahead — universe 시점별 필터) | `test_delisting_date_preserved_for_delisted_symbol` (universe_2024 vs universe_2023) |
| 14.10 (결손 봉 forward-fill 금지) | `test_missing_bar_not_filled` (LocalCsv) / `test_missing_bar_not_in_dataframe` (PriceLoader) |
| 015 정합 (BacktestEngine next_*) | `test_next_columns_are_shift_minus_one` / `test_last_row_next_columns_are_nan` / `test_loaded_df_runs_through_backtest_engine` |
| CLAUDE.md #8 (결정론) | `test_sorted_symbol_rows_alphabetical` / `test_sorted_price_rows_symbol_then_date` / `test_sorted_calendar_rows_market_then_date` / `test_load_sorted_by_date_asc` / `test_ingest_is_idempotent` |

### Phase 1 골든 fixture 회귀

영향 없음 — 본 step은 신규 모듈만 작성, BacktestEngine / Portfolio / StrategyEngine / ExecutionModel / CashManager / conditions / models / repositories 일체 미수정. 9지표 frozen expected 그대로, 6/6 통과.

## Issues

### 1. 016 head 가드 테스트 실패 (작업 지시에 명시 — 본 step 무관)

`tests/market_data/test_alembic_market_data.py::test_new_revision_is_current_head`가 016 head(`9a4d2e1f6c10`)를 검증하지만, 017 step(b1 — `b5e8d3c1a924_add_trade_executions_signal_date.py`)이 head를 옮겼다. 작업 지시에 명시적으로 "016 자기-소유 head 가드(...)는 본 step과 별개 — 손대지 말 것"이라 했으므로 본 step에서 손대지 않음. 016 작업 로그에 별도 follow-up으로 남길 것.

### 2. ExecutionModel.get_entry_price와 engine.py의 next_* 컬럼 접근 불일치

ExecutionModel.get_entry_price는 `use_adjusted_price=True`일 때 `adj_next_open`/`adj_next_close` 컬럼을 찾지만, engine.py:158/361은 직접 `row["next_open"]`을 읽는다. 즉 ExecutionModel 경로를 거치지 않는다. 본 step의 PriceLoader는 두 컬럼을 모두 채워(같은 값) 잠재적 호환성을 확보 — 향후 engine.py가 ExecutionModel 경로로 통합되면 전환 부담이 없어진다. 별도 step에서 정합화 권장 (Follow-up 항목).

### 3. CLAUDE.md의 market_cap NOT NULL 명시 vs 모델 NULL 허용

CLAUDE.md 016 인계 정보에 "market_cap (시가총액 시계열, NOT NULL)"이라 적혀있으나 실제 `DailyPrice.market_cap`은 `nullable=True` (016에서 명시: "NULL 허용 — 초기 백필 시 미수집 가능"). 본 step은 모델 정의를 따름 (CLAUDE.md를 권위 있는 문서로 보지 않음 — 코드/14.8.3 정책이 우선). 후속 step에서 CLAUDE.md를 모델과 일치시키는 것을 권장.

## Result

### BaseProvider 시그니처

```python
from abc import ABC, abstractmethod
from sqlalchemy.orm import Session
from app.market_data.provider import BaseProvider, IngestResult


class BaseProvider(ABC):
    def __init__(self, name: str) -> None: ...

    @abstractmethod
    def ingest_into(
        self,
        session: Session,
        *,
        symbols: Sequence[str] | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> IngestResult: ...

    # 정렬 헬퍼 (subclass가 결정론 보장에 사용)
    @staticmethod
    def _sorted_symbol_rows(rows) -> list: ...   # symbol ASC
    @staticmethod
    def _sorted_price_rows(rows) -> list: ...    # (symbol, date) ASC
    @staticmethod
    def _sorted_calendar_rows(rows) -> list: ... # (market, date) ASC


@dataclass(frozen=True)
class IngestResult:
    symbols_upserted: int = 0
    daily_prices_upserted: int = 0
    trading_days_upserted: int = 0
    warnings: list[str] = []

    @property
    def total_rows(self) -> int: ...
```

### LocalCsvProvider 사용 예시

```python
from pathlib import Path
from app.market_data.local_csv import LocalCsvProvider

provider = LocalCsvProvider(root=Path("data/sample"))
result = provider.ingest_into(
    session,
    symbols=["005930", "000660"],     # None이면 전체
    start_date=date(2024, 1, 1),       # None이면 전체
    end_date=date(2024, 12, 31),
)
session.commit()
print(result.symbols_upserted, result.daily_prices_upserted, result.trading_days_upserted)
```

CSV 형식 명세: 본 파일 상단 docstring 참조 (`local_csv.py:5-32`).

### PriceLoader DataFrame 컬럼 명세

```python
PRICE_LOADER_BASE_COLUMNS = (
    "date",                                                # date / datetime
    "open", "high", "low", "close", "volume",              # 원 가격 (거래대금 필터용)
    "adj_open", "adj_high", "adj_low", "adj_close",        # 수정 가격 (13.7 — 가격 조건/체결 기본)
    "adj_volume",
    "market_cap",                                          # NULL 허용
)
PRICE_LOADER_NEXT_COLUMNS = (
    "next_open", "next_close", "next_volume", "next_date", # adj_*의 shift(-1)
    "adj_next_open", "adj_next_close",                     # ExecutionModel.get_entry_price 호환
)
PRICE_LOADER_COLUMNS = PRICE_LOADER_BASE_COLUMNS + PRICE_LOADER_NEXT_COLUMNS
```

- 정렬: `date` ASC (인덱스는 RangeIndex, 컬럼으로 노출).
- **마지막 row의 next_*는 NaN, next_date는 NaT** — 015 정합 (BacktestEngine이 자동 skip).
- 빈 결과: 컬럼 명세 동일한 빈 DataFrame.
- 결손 봉(14.10): DataFrame에 row 없음 — forward-fill 금지.

### 다음 step (019 UniverseSelector) 인계 정보

#### 1. BaseProvider 시그니처
위 "BaseProvider 시그니처" 절 참조. UniverseSelector는 provider를 직접 호출하지 않고 `app.market_data.repositories.get_universe_at_date`를 위임할 가능성이 높다 (책임 분리).

#### 2. LocalCsvProvider 사용 예시
위 "LocalCsvProvider 사용 예시" 절 참조. UniverseSelector 테스트도 동일 fixture(`backend/tests/market_data/fixtures/csv/sample/`)를 활용 가능.

#### 3. PriceLoader DataFrame 컬럼 명세
위 "PriceLoader DataFrame 컬럼 명세" 절 참조. UniverseSelector 자체는 가격 데이터 없이 종목 마스터만 다루지만, 후속 step(시가총액 상위 N 등)에서는 daily_prices.market_cap 시계열을 PriceLoader로 조회할 수 있다.

#### 4. `repositories.get_universe_at_date` 위임 패턴

```python
from app.market_data import repositories

class UniverseSelector:
    def select(self, universe_config: dict, as_of_date: date) -> list[str]:
        # 1) repositories에서 시점별 활성 종목 조회 (13.13 / 13.15)
        active = repositories.get_universe_at_date(
            session, market=universe_config["market"], as_of_date=as_of_date
        )
        # 2) 06번 §8 공통 필터 적용 (exclude_etf / exclude_etn / ...)
        filtered = self._apply_common_filters(active, as_of_date, universe_config)
        # 3) 선택 방법 적용 (all / market_cap_top_n / ...)
        return self._apply_selection_method(filtered, universe_config, as_of_date)
```

`get_universe_at_date`는 `listing_date <= as_of_date AND (delisting_date IS NULL OR delisting_date > as_of_date)` 필터 + symbol ASC 정렬을 보장.

#### 5. CSV fixture 디렉토리 위치

```text
backend/tests/market_data/fixtures/csv/
├─ sample/                  # 4 종목 (3 활성 + 1 폐지 099999) × 5 거래일 + 8 캘린더
│   ├─ symbols.csv
│   ├─ daily_prices.csv
│   └─ trading_calendar.csv
├─ with_missing/            # 005930 1/4 결손 봉 (14.10 검증용)
│   ├─ symbols.csv
│   ├─ daily_prices.csv
│   └─ trading_calendar.csv
└─ bad_missing_adj/         # adj_close 빈 칸 (13.7 위반 케이스)
    ├─ symbols.csv
    └─ daily_prices.csv
```

UniverseSelector 테스트(test_universe.py)는 sample 디렉토리의 099999 폐지 종목으로 생존편향 회피 검증을 그대로 수행 가능.

## Follow-ups

1. **019 — UniverseSelector 구현** (06번 §8)
   - `app/market_data/universe.py` 신규
   - `repositories.get_universe_at_date` 위임 + 06번 §8 공통 필터 추가 적용
   - sample fixture로 폐지 종목 회피, exclude_etf 등 검증
2. **016의 head 가드 테스트 갱신** — 017에서 head가 옮겨졌으나 016 자기 head 가드가 미갱신. 016 자체의 후속으로 처리 권장.
3. **ExecutionModel + engine.py의 next_* 컬럼 접근 정합화** — 현재 engine.py는 row["next_open"]을 직접 읽지만 ExecutionModel.get_entry_price는 prefix=adj_로 분기. 향후 engine.py 통합 시 PriceLoader가 이미 adj_next_*도 채워두므로 마이그레이션 부담 없음.
4. **06번 / 14번 문서 갱신 권장**:
   - 06번 §3에 PriceLoader 위치는 있으나 컬럼 명세가 없음 — 본 step 결정 사항(adj_*/next_*/adj_next_*) 추가 권장.
   - 14번 §12에 PriceLoader 시그니처가 있으나 본 step의 컬럼 명세를 명시하면 향후 PykrxProvider/캐시 도입 시 일관성 유지.
5. **020+ Phase 11 — PykrxProvider** (14번 §6)
   - LocalCsvProvider와 동일한 BaseProvider.ingest_into 인터페이스 구현
   - pykrx fetch + 재시도/백오프 + 결정론 정렬
   - 본 step의 IngestResult 그대로 활용
6. **수정주가 재계산 (Phase 11 데이터 파이프라인)** — corporate_actions 적용 후 adj_* 전체 시계열 재계산. 본 step의 LocalCsvProvider는 입력 CSV의 adj_*를 그대로 신뢰하므로 재계산 책임 없음.

## 메인 세션 마무리 체크

- [ ] status를 completed로 변경
- [ ] 작업로그/README.md 갱신
- [ ] PM 호출 → 로드맵.md 갱신 (06-c, 06-d, 06-e [x] / Phase 9 step 018 ✅)
- [ ] git commit (Phase 9 마지막 step 아니므로 push 보류)
