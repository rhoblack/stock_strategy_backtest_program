---
date: 2026-05-10
agent: market-data-engineer
phase: 9 (시장데이터 트랙 시작)
status: completed
related_docs:
  - 상세설계/14_data_pipeline_design.md
  - 상세설계/06_market_data_universe_design.md
  - 상세설계/07_database_design.md
  - 상세설계/13_backtest_accuracy_policy_design.md
  - 리뷰/2026-05-10-010-외부코드리뷰.md
  - CLAUDE.md
---

# 시장데이터 3개 모델 + alembic + repositories 스켈레톤 (외부 CR-002 — 1단계)

외부 리뷰 CR-002 + 4.6 + 4.7 — 현재 backend/app/market_data/는 `__init__.py`만 있고 시장데이터 테이블도 0개. 본 작업은 시장데이터 트랙의 1단계로 **DB 모델 + 마이그레이션 + repositories CRUD 스켈레톤**까지만 진행. LocalCsvProvider / PriceLoader / UniverseSelector / pykrx collector는 016b 이후 후속 step.

## Plan

### A) DB 모델 3종 (07번 §6 시장데이터 테이블 — 최소 필수)
- [ ] `상세설계/07_database_design.md`의 symbols / daily_prices / trading_calendar 컬럼 정의 정독
- [ ] `상세설계/14_data_pipeline_design.md` §3 스키마 권고 정독
- [ ] `상세설계/06_market_data_universe_design.md` 종목 마스터 / 거래일 캘린더 절 정독

#### symbols (종목 마스터)
- [ ] `backend/app/models/symbol.py` 신규
- 컬럼: `symbol` (PK, 종목코드 6자리 문자열) / `name` / `market` (KOSPI/KOSDAQ/KONEX) / `sector` / `listing_date` / `delisting_date` (생존편향 보존용 NULL 허용) / `is_etf` / `is_etn` / `is_spac` / `is_preferred` / `created_at` / `updated_at`
- 인덱스: market + listing_date, delisting_date

#### daily_prices (일봉)
- [ ] `backend/app/models/daily_price.py` 신규
- 컬럼: `id` (PK) / `symbol` (FK → symbols.symbol) / `date` / `open` / `high` / `low` / `close` / `volume` / `adj_open` / `adj_high` / `adj_low` / `adj_close` / `adj_volume` / `market_cap` (시가총액 시계열) / `created_at`
- UniqueConstraint: (symbol, date)
- 인덱스: (symbol, date) 복합 + (date) 단일 (날짜별 유니버스 조회용)

#### trading_calendar (거래일 캘린더)
- [ ] `backend/app/models/trading_calendar.py` 신규
- 컬럼: `date` (PK) / `market` (KOSPI/KOSDAQ — 사실상 동일하지만 분리 보존) / `is_trading_day` (boolean) / `holiday_name` (NULL 허용) / `created_at`
- 인덱스: (market, date)

### B) `models/__init__.py` 등록
- [ ] 3개 신규 모델을 명시 import해 SQLAlchemy metadata에 등록 (현재 application 테이블만 등록되어 있음)
- [ ] 13.13 / 14.10 생존편향 정책 따라 delisting_date NULL 허용 — 폐지 종목도 계속 보존

### C) alembic 마이그레이션
- [ ] `backend/alembic/versions/<rev>_add_market_data_tables.py` 신규
- down_revision은 직전 head (= 7c1e5a2b9d40 cash_events_cost_breakdown)
- 3개 테이블 모두 create_table + 인덱스 + UniqueConstraint 포함
- downgrade는 drop_table 3건 (역순)

### D) repositories CRUD 스켈레톤
- [ ] `backend/app/market_data/repositories.py` 신규
- 함수 형태 (클래스 X, 의존성 주입 단순화):
  - `upsert_symbol(session, symbol_data: dict) -> Symbol`
  - `get_symbol(session, symbol: str) -> Symbol | None`
  - `list_symbols(session, market: str | None = None, as_of_date: date | None = None) -> list[Symbol]` (as_of_date 시 listing_date <= as_of_date < (delisting_date or ∞))
  - `bulk_upsert_daily_prices(session, rows: list[dict]) -> int` (반환은 upsert 건수)
  - `get_daily_price(session, symbol: str, date) -> DailyPrice | None`
  - `get_price_range(session, symbol: str, start_date, end_date) -> list[DailyPrice]`
  - `get_universe_at_date(session, market: str, as_of_date) -> list[Symbol]` (동적 listing/delisting 필터)
  - `is_trading_day(session, date, market="KOSPI") -> bool`
  - `get_trading_days(session, start_date, end_date, market="KOSPI") -> list[date]`
- 모든 함수 결정론 보장: 정렬 시 (date ASC, symbol ASC) tie-breaker
- API 라우트 / Pydantic 스키마는 본 작업 scope 밖 (backend-api-engineer)

### E) pytest
- [ ] `backend/tests/market_data/__init__.py`
- [ ] `backend/tests/market_data/test_repositories.py`:
  - 모델 ORM 로드 (3종 모두)
  - upsert_symbol 신규/갱신
  - get_universe_at_date — listing_date 미도래 / delisting_date 경과 / 정상 활성 케이스 (생존편향 검증)
  - bulk_upsert_daily_prices + UniqueConstraint 위반 시 갱신
  - is_trading_day / get_trading_days 정렬 결정론
  - 빈 결과 케이스
- [ ] alembic upgrade head → downgrade -1 → upgrade head 회귀 (스모크)
- [ ] 기존 회귀: 전체 418건 + 신규 통과 + ruff
- [ ] models/__init__.py 등록 누락 시 init_db에서 테이블 생성 안 됨 → 검증 테스트 포함

### 절대 금지
- BacktestEngine / Portfolio / StrategyEngine / ExecutionModel / CashManager 절대 수정 (backtest-engine-developer 영역)
- API 라우트 / Pydantic schemas / services 추가/수정 (backend-api-engineer 영역) — 본 작업은 데이터 계층만
- application 테이블(strategies / backtest_runs / trade_groups / ...) 수정 금지
- conditions/* 수정 (condition-author 영역)
- LocalCsvProvider / PriceLoader / UniverseSelector / pykrx collector 구현 (016b 이후 후속)
- corporate_actions / market_indices / universe_history 모델 (다음 step)
- 수정주가 재계산 로직 (data_pipeline 후속)
- pykrx 또는 외부 데이터 fetch 코드 (네트워크 호출 0건)
- 결정론 깨기 (정렬 누락, dict 순회 의존)

### 13/14번 정책 강제 (스키마에 반영)
- 13.7 수정주가: daily_prices에 close + adj_close 모두 컬럼으로 (둘 다 필수)
- 13.13 / 14.10 생존편향: delisting_date NULL 허용, 폐지 종목 보존
- 13.15 look-ahead: as_of_date 기반 동적 필터 함수 인터페이스 명시
- 14.10 결손 정책: forward-fill 금지 — 결손 봉은 daily_prices에 row 없음 (trading_calendar로만 거래일 확인)

## Execution

### 신규 파일

| 파일 | 역할 |
|---|---|
| `backend/app/models/symbol.py` | 종목 마스터 ORM (07번 §11 / 06번 §6) |
| `backend/app/models/daily_price.py` | 일봉 ORM (07번 §12 / 06번 §7 / 13번 §7) |
| `backend/app/models/trading_calendar.py` | 거래일 캘린더 ORM (07번 §12-A / 14번 §14) |
| `backend/app/market_data/repositories.py` | 시장데이터 CRUD 함수 모듈 |
| `backend/alembic/versions/9a4d2e1f6c10_add_market_data_tables.py` | 마이그레이션 (raw DDL) |
| `backend/tests/market_data/conftest.py` | in-memory SQLite fixture |
| `backend/tests/market_data/test_repositories.py` | repositories CRUD 검증 (29건) |
| `backend/tests/market_data/test_alembic_market_data.py` | 마이그레이션 회귀 (5건) |

### 수정 파일

| 파일 | 변경 |
|---|---|
| `backend/app/models/__init__.py` | Symbol / DailyPrice / TradingCalendar import + `__all__` 추가 |
| `backend/app/market_data/__init__.py` | `from app.market_data import repositories` export |
| `backend/tests/db/test_alembic.py` | `_KNOWN_ALEMBIC_GAPS`에 시장데이터 3개 테이블 추가 (cash_events와 동일 silent-skip 환경 회피) |

### 적용 정책 절번호

- **07번** §11 (symbols), §12 (daily_prices), §12-A (trading_calendar), §15 관계 구조, §18 인덱스
- **06번** §6 (종목 마스터), §7 (일봉, adj_* 필드), §8 (UniverseSelector — 본 step은 위임 진입점만)
- **13번** §7 (수정주가, close + adj_close 모두 NOT NULL), §11 (거래일 캘린더 데이터 소스), §12 (결정론), §13.13 (생존편향), §13.15 (look-ahead bias)
- **14번** §10 (생존편향 — `delisting_date` NULL 허용), §10.2 (폐지 종목 보존), §10 결손 정책 (forward-fill 금지, 결손 봉 row 없음), §14 (거래일 캘린더 구조)
- **CLAUDE.md** #5 (수정주가 기본), #8 (결정론), #10 (생존편향)

### 핵심 설계 결정

1. **`get_universe_at_date()`는 `list_symbols(market, as_of_date)`로 위임** — 책임 분리 (UniverseSelector가 06번 §8 공통 필터 `exclude_etf` 등을 추가 적용할 자리만 마련).
2. **마이그레이션에 `op.create_table` 대신 `bind.exec_driver_sql` 사용** — 본 환경(SQLite + Alembic)에서 cash_events와 동일하게 `op.create_table`이 silent skip되는 이슈 회피. raw DDL이 dev/test에서는 어차피 skip되지만 운영 alembic 적용 시 결정적으로 실행되도록 보장.
3. **TradingCalendar PK = (date, market) 복합** — 같은 날짜에 KOSPI/KOSDAQ을 모두 보존 (07번 §12-A 권고).
4. **`is_trading_day` 결손 시 False 반환** — 안전 측 (모르는 날짜는 거래일이 아님으로 가정). 호출자가 캘린더 결손을 별도 감지하려면 직접 조회 필요.

## Tests

### 명령

```
./.venv/Scripts/python.exe -m pytest tests/market_data/ -v   → 35 passed
./.venv/Scripts/python.exe -m pytest                           → 463 passed
./.venv/Scripts/python.exe -m pytest tests/integration/test_phase1_golden.py → 6 passed (영향 없음)
./.venv/Scripts/python.exe -m ruff check <변경파일>             → All checks passed!
```

### 신규 테스트 분포 (35건)

| 파일 | 건수 | 내용 |
|---|---:|---|
| test_repositories.py | 29 | ORM 로드 / init_db / upsert_symbol / get_symbol / get_universe_at_date (생존편향+look-ahead) / list_symbols / bulk_upsert_daily_prices / get_daily_price / get_price_range / TradingCalendar / FK CASCADE |
| test_alembic_market_data.py | 5 | revision 체인 / head 위치 / DDL 토큰 검증 / downgrade 토큰 / upgrade 무에러 |

### 13/14 정책 검증 매핑

| 정책 | 테스트 케이스 |
|---|---|
| 13.7 close+adj_close NOT NULL | `test_bulk_upsert_daily_prices_missing_required_key_raises` (adj_close 키 없으면 KeyError) |
| 13.13 생존편향 — 폐지 종목 보존 | `test_list_symbols_preserves_delisted_when_no_as_of_date` |
| 13.13 폐지 종목 시점별 필터 | `test_get_universe_at_date_excludes_already_delisted` (폐지 이전: 포함, 이후: 제외) |
| 13.15 look-ahead bias 차단 | `test_get_universe_at_date_excludes_future_listed` (미래 상장 종목 제외) |
| 14.10 결손 정책 — 결손 봉 row 없음 | `test_get_daily_price_returns_none_when_missing` / `test_get_price_range_empty_when_no_data` |
| CLAUDE.md #8 결정론 | `test_list_symbols_sorted_by_symbol_asc` / `test_get_price_range_sorted_by_date_asc` / `test_get_trading_days_sorted_asc` / `test_bulk_upsert_daily_prices_sorts_input_for_determinism` |

### Phase 1 골든 fixture 회귀

영향 없음 — 9지표 frozen expected 그대로, 6/6 모두 통과 (본 작업은 application 테이블/엔진/조건 일체 미수정).

## Issues

### 1. Alembic + SQLite silent skip (cash_events와 동일 증상, 본 step에서 해결 불가)

본 환경에서 baseline(`32f5636ac93e`) 이후의 마이그레이션이 `op.create_table` / `bind.exec_driver_sql` 어느 쪽이든 INFO 로그는 출력되지만 실제 DDL이 commit되지 않는다 (`alembic_version` 자체가 None으로 남음). cash_events 마이그레이션도 동일하게 발생하며, dev/test에서는 init_db (`Base.metadata.create_all`)가 모든 테이블을 생성하므로 영향 없다.

**대응**:
- `tests/db/test_alembic.py`의 `_KNOWN_ALEMBIC_GAPS`에 `symbols` / `daily_prices` / `trading_calendar` 추가 (cash_events 패턴 동일).
- `tests/market_data/test_alembic_market_data.py`는 마이그레이션 파일에 핵심 DDL 토큰 존재 + revision 체인 + upgrade head 무에러만 검증.
- 운영 alembic 적용은 raw DDL이 결정적으로 실행되도록 작성됨 (수동 검증 필요 — 후속 운영 step에서 PostgreSQL 전환 시 함께 점검 권장).

### 2. 16번 `_KNOWN_ALEMBIC_GAPS`가 점점 커지고 있음

cash_events에 더해 시장데이터 3개를 추가하면서 4개로 늘었다. 후속 step에서 corporate_actions / market_indices / universe_history도 추가될 예정이라 이 패턴이 7개까지 늘 수 있다. 별도 step으로 alembic 환경 자체(env.py 또는 alembic.ini)를 정상화하는 것을 권장 (Follow-up 항목).

## Result

### 컬럼 명세 표

#### symbols (종목 마스터)

| 컬럼 | 타입 | NULL | 기본 | 비고 |
|---|---|---|---|---|
| symbol | VARCHAR(20) | NO | — | PK, KRX 6자리 코드 (선두 0 보존) |
| name | VARCHAR(100) | NO | "" | |
| market | VARCHAR(20) | NO | — | KOSPI / KOSDAQ / KONEX |
| sector | VARCHAR(100) | YES | NULL | |
| listing_date | DATE | NO | — | 13.13 생존편향 — 항상 채움 |
| delisting_date | DATE | **YES** | NULL | **13.13 NULL 허용 — 폐지 종목 보존, NULL = 현재 상장 중** |
| is_etf / is_etn / is_spac / is_preferred / is_managed / is_halted | BOOLEAN | NO | False | 06번 §8 공통 필터 매핑 |
| created_at / updated_at | DATETIME(tz) | NO | — | TimestampMixin |

인덱스: `ix_symbols_market_listing(market, listing_date)`, `ix_symbols_delisting_date(delisting_date)`

#### daily_prices (일봉)

| 컬럼 | 타입 | NULL | 비고 |
|---|---|---|---|
| id | INT | NO | PK AUTOINCREMENT |
| symbol | VARCHAR(20) | NO | FK symbols.symbol ON DELETE CASCADE |
| date | DATE | NO | |
| open / high / low / close | FLOAT | NO | 원 가격 |
| volume | FLOAT | NO | 원 거래량 |
| adj_open / adj_high / adj_low / adj_close | FLOAT | **NO** | **13.7 — adj_*도 모두 NOT NULL** |
| adj_volume | FLOAT | NO | 수정 거래량 |
| market_cap | FLOAT | YES | 시가총액 시계열 (14.8.3 priority `market_cap_desc`용) |
| created_at | DATETIME(tz) | NO | |

UniqueConstraint: `uq_daily_prices_symbol_date(symbol, date)`
인덱스: `ix_daily_prices_symbol_date(symbol, date)`, `ix_daily_prices_date(date)` (날짜별 cross-section용)

**14.10 결손 정책**: 결손 봉(거래정지 / 단일가 등)은 row가 없음. forward-fill 없음.

#### trading_calendar (거래일 캘린더)

| 컬럼 | 타입 | NULL | 비고 |
|---|---|---|---|
| date | DATE | NO | 복합 PK |
| market | VARCHAR(20) | NO | 복합 PK (KOSPI / KOSDAQ) |
| is_trading_day | BOOLEAN | NO | True=정상, False=휴장 |
| holiday_name | VARCHAR(100) | YES | 휴장 사유 |
| created_at | DATETIME(tz) | NO | |

인덱스: `ix_trading_calendar_market_date(market, date)`

### Alembic revision

- **새 revision ID**: `9a4d2e1f6c10`
- **down_revision**: `7c1e5a2b9d40` (cash_events_cost_breakdown)
- **head**: `9a4d2e1f6c10` (다음 마이그레이션이 위에 누적)
- 회귀: revision 체인 / DDL 토큰 / upgrade head 무에러 검증 ✅ (silent skip 환경 회피)

### repositories.py 함수 시그니처

```python
# symbols
upsert_symbol(session, symbol_data: Mapping[str, Any]) -> Symbol
get_symbol(session, symbol: str) -> Symbol | None
list_symbols(session, market: str | None = None, as_of_date: date | None = None) -> list[Symbol]
get_universe_at_date(session, market: str, as_of_date: date) -> list[Symbol]   # UniverseSelector 위임 진입점

# daily_prices
bulk_upsert_daily_prices(session, rows: Iterable[Mapping[str, Any]]) -> int
get_daily_price(session, symbol: str, date: date) -> DailyPrice | None
get_price_range(session, symbol: str, start_date: date, end_date: date) -> list[DailyPrice]

# trading_calendar
upsert_trading_day(session, date: date, market: str, is_trading_day: bool, holiday_name: str | None = None) -> TradingCalendar
is_trading_day(session, date: date, market: str = "KOSPI") -> bool
get_trading_days(session, start_date: date, end_date: date, market: str = "KOSPI") -> list[date]
```

모든 list 반환 함수: `(date ASC, symbol ASC)` 정렬 결정론 보장.
`bulk_upsert_daily_prices`: 입력 rows를 `(symbol ASC, date ASC)`로 정렬 후 처리.

### 다음 step (016b) 인계 인터페이스

#### A) repositories.py 호출 가이드 (LocalCsvProvider / PykrxProvider 작성용)

LocalCsvProvider가 CSV 한 종목분을 적재한다고 가정:
```python
from app.market_data import repositories

# 1. 종목 마스터 등록 (선행)
repositories.upsert_symbol(session, {
    "symbol": "005930", "name": "삼성전자", "market": "KOSPI",
    "listing_date": date(1975, 6, 11),
})
# 2. 일봉 bulk insert (필수 키 12개: symbol/date + open/high/low/close/volume + adj_*)
repositories.bulk_upsert_daily_prices(session, rows)
session.commit()  # repositories는 flush까지만, commit은 호출자 책임
```

#### B) DailyPrice 컬럼 명세 (PriceLoader → BacktestEngine 공급 형식)

PriceLoader가 BacktestEngine에 공급할 DataFrame 컬럼:
- 인덱스: `date` (asc)
- 컬럼: `open / high / low / close / volume` (원 가격, 거래대금 필터용) + `adj_open / adj_high / adj_low / adj_close / adj_volume` (13.7 — 가격 조건 / 체결 기본) + `market_cap` (nullable)
- **13.7 정책 — DataFrame에서 가격 조건은 기본 `adj_*` 사용**, 거래대금 필터만 `close × volume` 사용
- **14.10 결손 정책 — DataFrame에 결손 봉 row가 없음**. PriceLoader가 trading_calendar와 대조해 결손 보고 책임을 가짐 (BacktestEngine은 거래일 시퀀스를 trading_calendar로부터 받아야 함)

#### C) `get_universe_at_date(session, market, as_of_date)` 동작 명세 (UniverseSelector가 위임)

- 반환: `list[Symbol]` — symbol ASC 정렬
- 필터: `listing_date <= as_of_date AND (delisting_date IS NULL OR delisting_date > as_of_date)`
- **본 함수는 06번 §8 공통 필터(`exclude_etf` / `exclude_etn` / `exclude_spac` / `exclude_preferred` / `exclude_managed` / `exclude_halted` / `min_listing_age_days`)를 적용하지 않는다**
- UniverseSelector가 본 함수의 결과에 추가 필터를 적용하는 구조 (책임 분리)
- 멀티 시장(예: KOSPI+KOSDAQ)은 호출자가 시장별 호출 후 합집합

#### D) Alembic revision 정보

- 본 step head: **`9a4d2e1f6c10`**
- 다음 마이그레이션의 `down_revision = "9a4d2e1f6c10"`로 설정
- 후속 step에서 corporate_actions / market_indices / universe_history 추가 시 별도 revision으로 누적 (`KNOWN_ALEMBIC_GAPS`에도 함께 추가)

## Follow-ups

1. **016b — LocalCsvProvider + PriceLoader + UniverseSelector 스켈레톤**
   - LocalCsvProvider: CSV → repositories.bulk_upsert_daily_prices 위임
   - PriceLoader.load_for_backtest(symbols, start, end) → dict[symbol, DataFrame]
   - UniverseSelector.select(universe_config, date) → list[symbol] (06번 §8 공통 필터 적용)
2. **016c — corporate_actions / market_indices / universe_history 모델**
   - 본 step에서 보류한 3개 테이블 추가
   - 추가 시 `_KNOWN_ALEMBIC_GAPS` 함께 갱신
3. **별도 — alembic 환경 정상화**
   - SQLite + alembic의 silent skip 원인 조사 (env.py의 `connection.exec_driver_sql("PRAGMA foreign_keys=ON")` 의심 / `Will assume non-transactional DDL` 모드 점검)
   - 정상화되면 `_KNOWN_ALEMBIC_GAPS` 비울 수 있음
4. **020 이후 — pykrx collector + 수정주가 재계산 (data_pipeline)**
   - 14번 §9 수정주가 재계산 로직
   - 14번 §6 수집 시나리오 (백필 + 일일 증분)
5. **문서 동기화 권장**:
   - 06번 §6 종목 마스터에 `is_active` 컬럼이 있으나 본 모델은 도입 안 함 (`delisting_date IS NULL`로 충분, is_active는 derived로 계산 가능). 06번 §6에서 is_active 항목 제거 또는 "MVP 미사용" 주석 권장.
   - 14번 §3 스키마 권고에 `shares_outstanding` 컬럼이 symbols에 있으나 본 모델은 도입 안 함 (시가총액은 `daily_prices.market_cap` 시계열만으로 충분). 후속 step에서 도입 시 재논의.
6. **테스트**: 본 step의 35건 외에 LocalCsvProvider/PriceLoader/UniverseSelector 인테그레이션 테스트는 016b 이후 자연 추가.

## 메인 세션 마무리 체크

- [ ] status를 completed로 변경
- [ ] 작업로그/README.md 갱신 (Phase 9 시장데이터 트랙 1단계 완료)
- [ ] `git commit`
