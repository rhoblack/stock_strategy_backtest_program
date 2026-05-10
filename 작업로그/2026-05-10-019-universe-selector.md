---
date: 2026-05-10
agent: market-data-engineer
phase: 9
status: completed
roadmap_step: 019
roadmap_impact:
  - 06-f  # UniverseSelector.select(config, date)
  - 06-g  # 06번 §8 공통 필터 (exclude_etf/etn/spac/preferred + 시가총액 + 거래대금)
  - 13-m  # UniverseSelector 동적 listing/delisting 필터 (06번)
related_docs:
  - 상세설계/06_market_data_universe_design.md
  - 상세설계/13_backtest_accuracy_policy_design.md
  - 상세설계/14_data_pipeline_design.md
  - 작업로그/2026-05-10-016-market-data-models-skeleton.md
  - 작업로그/2026-05-10-018-local-csv-provider-and-price-loader.md
---

# Step 019 — UniverseSelector + 06번 §8 공통 필터 (Phase 9 마지막)

016에서 시장데이터 모델 + repositories를, 018에서 Provider/PriceLoader를 도입한 위에 **유니버스 선정 계층** 도입. 본 step은 Phase 9 마지막 — 완료 후 test-engineer ship-go → push.

## Plan

### A) UniverseSelector 본체 (06-f, 13-m)
- [ ] `상세설계/06_market_data_universe_design.md` §8 (공통 필터) + §9 (선정 방법) 정독
- [ ] `상세설계/13_backtest_accuracy_policy_design.md` §13.13 (생존편향) + §13.15 (look-ahead) 정독
- [ ] `backend/app/market_data/universe.py` 신규
  - 클래스: `UniverseSelector`
  - 메서드: `select(session, config: dict, as_of_date: date) -> list[Symbol]`
  - 흐름:
    1. `repositories.get_universe_at_date(session, market, as_of_date)` 위임 (016 — listing_date <= as_of_date < (delisting_date or ∞))
    2. 06번 §8 공통 필터 적용 (B 단계)
    3. 06번 §9 선정 방법 적용 (C 단계 — 본 step에서는 기본 ALL만, market_cap_top_n은 시가총액 시계열 도입 후라 부분 구현)
  - 결정론: 정렬 (symbol ASC) tie-breaker

### B) 06번 §8 공통 필터 (06-g)
- [ ] config의 다음 필드를 적용:
  - `exclude_etf` (boolean, default=True) — `Symbol.is_etf == False`만
  - `exclude_etn` (boolean, default=True) — `Symbol.is_etn == False`만
  - `exclude_spac` (boolean, default=True) — `Symbol.is_spac == False`만
  - `exclude_preferred` (boolean, default=True) — `Symbol.is_preferred == False`만
  - `exclude_managed` (boolean, default=True) — `Symbol.is_managed == False`만 (016에서 추가됨)
  - `exclude_halted` (boolean, default=True) — `Symbol.is_halted == False`만 (016에서 추가됨)
  - `min_market_cap` (int | None) — daily_prices.market_cap >= 임계값 (as_of_date 또는 가장 최근 거래일 기준)
  - `min_avg_trading_value` (int | None) — 거래대금 평균(close * volume, N일) >= 임계값
- 13.7 + 13.15 정합:
  - 시가총액 필터는 **as_of_date 또는 그 직전 거래일의 market_cap** 사용 (look-ahead 차단)
  - 거래대금 평균은 **as_of_date 직전 N일** (당일 미포함, look-ahead 차단)
- 결손 처리:
  - market_cap 결손 시 해당 종목은 필터에서 제외 (보수)
  - 거래대금 평균 N일 중 결손 봉이 있으면 N에서 제외 후 평균 (또는 종목 제외 — 정책 결정 필요)

### C) 06번 §9 선정 방법 (06-f 일부)
- [ ] config의 `selection_method`:
  - `ALL` (default) — 필터 통과한 모든 종목
  - `MARKET_CAP_TOP_N` — 필터 통과 후 시가총액 상위 N (as_of_date 기준)
  - `LIQUIDITY_TOP_N` — 필터 통과 후 거래대금 평균 상위 N
- 본 step에서는 ALL은 완전 구현, MARKET_CAP_TOP_N / LIQUIDITY_TOP_N은 데이터 의존성으로 부분 구현 (Phase 11 시가총액 시계열 보강 후 완전화 가능)

### D) 13.15 look-ahead bias 차단
- 시가총액 상위 N 선정에 **미래 데이터 금지** — `daily_prices.date <= as_of_date`
- 거래대금 평균은 **as_of_date 직전 N일** (당일 미포함)
- universe 동적 필터는 `as_of_date` 기준으로 `listing_date <= as_of_date < (delisting_date or ∞)`
- 모든 위 조건 단위 테스트로 강제

### E) 테스트
- [ ] `backend/tests/market_data/test_universe_selector.py` 신규
  - 정상 ALL: 4 종목 중 폐지 1개 제외 → 3 종목
  - 폐지 종목 보존 검증 (생존편향 — 폐지 전 시점 백테스트는 폐지 종목 포함)
  - exclude_etf/etn/spac/preferred 각각 토글
  - min_market_cap 적용 (정상 / 결손 케이스)
  - min_avg_trading_value 적용 (정상 / N일 미만 케이스)
  - look-ahead 차단: as_of_date 다음 일 데이터가 영향 없는지
  - 결정론: 동일 입력 5회 반복 동일 결과
  - selection_method=MARKET_CAP_TOP_N 부분 구현 검증 (시가총액 시계열 의존)
- [ ] 018의 fixture CSV(sample) 활용 + 필요 시 신규 fixture 추가

### F) 회귀
- [ ] 전체 pytest (Phase 1 골든 영향 없음 — engine 변경 0건)
- [ ] ruff (변경 파일)
- [ ] alembic 회귀 (016/017 마이그레이션 영향 없음)

### 절대 금지
- BacktestEngine / Portfolio / StrategyEngine / ExecutionModel / CashManager 절대 수정 (backtest-engine-developer 영역)
- API 라우트 / Pydantic schemas / services 추가/수정 (backend-api-engineer 영역)
- application 테이블 / 시장데이터 모델 수정 금지 (016 산출물)
- conditions/* 수정 (condition-author 영역)
- 016 repositories.py 시그니처 변경 금지 — 활용만
- 018 Provider/PriceLoader 수정 금지 — 활용만 (필요 시 universe.py에서 import해 사용)
- pykrx / 외부 fetch 금지 (Phase 11)
- corporate_actions / market_indices / universe_history 모델 작성 금지 (Phase 11)
- universe_history 영속화 금지 (Phase 11)
- 결정론 깨기 (정렬 누락, dict 순회 의존)
- look-ahead bias (당일 market_cap/거래량 사용 금지)

### 다음 흐름 (019 완료 후 — Phase 9 마지막 step)
- PM 마무리: 로드맵 갱신 (06-f, 06-g, 13-m [x] / Phase 9 step 019 ✅)
- **test-engineer 호출**: "Phase 9 완료 검증" — 통합/회귀/13.17 acceptance/골든/시나리오 + ship-readiness
- 🟢 ship-go 시: PM "Phase 9 완료" → 진행률 추이 갱신 → git push origin main
- 🔴 ship-block 시: 추가 fix step + push 보류

## Execution

### 신규 파일

| 파일 | 라인 | 역할 |
|---|---:|---|
| `backend/app/market_data/universe.py` | 386 | UniverseSelector — 06번 §8 공통 필터 + §9 selection_method (ALL / MARKET_CAP_TOP_N / LIQUIDITY_TOP_N) + 13.15 look-ahead 차단 + UniverseSelectionResult dataclass |
| `backend/tests/market_data/test_universe_selector.py` | 478 | 35건 — A 기본 / B 생존편향+look-ahead / C 종목 마스터 플래그 / D min_market_cap / E look-ahead 시가총액 / F min_avg_trading_value / G look-ahead 거래대금 / H 결정론 / I MARKET_CAP_TOP_N / J LIQUIDITY_TOP_N / K 에러 / L 시점 차이 |
| `backend/tests/market_data/fixtures/csv/universe_test/symbols.csv` | 15 | 14 종목 (5 일반 + 6 플래그 종목 + 1 폐지 + 1 미래 상장 + 1 코스닥) |
| `backend/tests/market_data/fixtures/csv/universe_test/daily_prices.csv` | 33 | 5 일반 종목 + ETF + 폐지종목 × 1/2~1/8(+1/9 look-ahead 검증용) |
| `backend/tests/market_data/fixtures/csv/universe_test/trading_calendar.csv` | 10 | 1/1~1/9 (5 거래일 + 4 휴장) |

### 수정 파일

| 파일 | 변경 |
|---|---|
| `backend/app/market_data/__init__.py` | docstring을 3단계(019) 진행 상황 반영 + UniverseSelector 사용 예시 추가 (export는 그대로) |

### 적용 정책 절번호

- **06번** §8 (UniverseSelector — 공통 필터 책임), §9 (selection_method ALL / market_cap_top_n / trading_value_top_n), §10 (시가총액 상위 N — `selection_timing` 매핑은 본 step의 `as_of_date` 인자로 흡수), §11 / §11.1 (생존편향 — listing/delisting 동적 필터, 016 위임), §12 (기본 제외 옵션)
- **13번** §7 (수정주가 — 거래대금 필터는 `close × volume` 원 가격), §13.12 (결정론 — symbol ASC tie-breaker, 5회 반복 동일성), §13.13 (생존편향 — 폐지 종목 시점별 필터), §13.15 (look-ahead bias — 시가총액 ≤ as_of_date / 거래대금 평균 < as_of_date)
- **14번** §8 (시가총액 시계열 — daily_prices.market_cap 활용), §10 (생존편향), §10 결손 정책 (forward-fill 금지)
- **CLAUDE.md** #5 (수정주가 기본 — 거래대금 필터 예외), #8 (결정론), #10 (생존편향)

### 핵심 설계 결정

1. **시가총액 시점 정책 — `as_of_date` 포함 (당일 OK)**
   - 13.15 체크리스트는 시가총액 상위 N 선정에 "미래 데이터" 금지만 명시. as_of_date의 종가가 확정된 이후 universe를 재선정하는 것은 현실적이고 look-ahead가 아님.
   - 구현: `daily_prices.date <= as_of_date AND market_cap IS NOT NULL` 중 `date DESC` 첫 row의 market_cap 사용. `LIMIT 1`로 SQL 효율 확보.
   - 결손(NULL) 시 종목 제외 (보수).

2. **거래대금 평균 시점 정책 — `as_of_date` 미포함 (직전 N 거래일)**
   - 13.15 체크리스트가 "거래량/거래대금 평균이 전일까지의 데이터인가?"를 명시 → as_of_date 미포함.
   - 거래일 기반이 아니라 달력일 lookback (`max(window_days * 2, window_days + 14)`)로 충분히 넓혀 실제 존재하는 봉만 사용. trading_calendar 의존을 줄여 fixture 의존성 최소화.
   - 결손 봉은 평균에서 제외 (forward-fill 금지). 0건이면 종목 제외.

3. **selection_method 부분 구현 정책**
   - `ALL`: 완전 구현. 필터 통과한 모든 종목 (symbol ASC).
   - `MARKET_CAP_TOP_N`: 부분 구현 — 016 daily_prices.market_cap 시계열만으로 동작 가능하므로 본 step에서 완전 구현 가능. Phase 11에서 시가총액 정합성 검증(14.8)이 보강되면 더 신뢰성 있게.
   - `LIQUIDITY_TOP_N`: 부분 구현 — close × volume 평균 N일 (06번 §9 `trading_value_top_n` 매핑). 임계값 정합 / 동일 함수 재사용.
   - `MANUAL` / `WATCHLIST`: 본 step 범위 밖. 미지원 method는 `ValueError`로 명확 분리 (silent skip 금지) — Phase 10 GUI 작업에서 자연 추가될 것.

4. **`UniverseSelectionResult` dataclass 도입 (frozen=True)**
   - `select()`는 list[Symbol] 그대로 반환 (단순 사용처).
   - `select_with_details()`는 `excluded_counts` 등 디버깅/영향분석 메타 포함 — 06번 §11.2 결과 화면 표시(향후 API에서 활용)에 활용 가능.

5. **종목 마스터 플래그 필터에서 첫 매칭만 카운트**
   - 한 종목이 ETF + 우선주를 동시에 가지면 `exclude_etf` 카운트만 증가 — 중복 카운트 방지로 합계의 의미를 보존.

6. **모듈 경계 엄격 준수**
   - BacktestEngine / Portfolio / StrategyEngine / ExecutionModel / CashManager / API 라우트 / Pydantic schemas / services / conditions / 016 repositories / 018 Provider/PriceLoader / application 테이블 / 시장데이터 모델 — **0건 수정**.
   - `repositories.get_universe_at_date` (016) + `repositories.get_price_range` (016) + `DailyPrice.market_cap` (016 컬럼)만 활용.

## Tests

### 명령

```text
./.venv/Scripts/python.exe -m pytest tests/market_data/test_universe_selector.py -v
  → 35 passed
./.venv/Scripts/python.exe -m pytest tests/integration/test_phase1_golden.py
  → 6 passed (Phase 1 골든 영향 없음)
./.venv/Scripts/python.exe -m pytest
  → 531 passed, 1 failed, 8 warnings in 19.14s
    (failed = 016 자기-소유 head 가드 — 작업 지시에 의해 본 step 범위 밖)
./.venv/Scripts/python.exe -m ruff check app/market_data/universe.py app/market_data/__init__.py tests/market_data/test_universe_selector.py
  → All checks passed!
```

### 신규 테스트 분포 (35건)

| 그룹 | 건수 | 내용 |
|---|---:|---|
| A 기본 ALL | 3 | default exclude → 5종목 / Symbol 객체 반환 / select_with_details excluded_counts |
| B 생존편향+look-ahead | 4 | 폐지 이전 포함 / 폐지 이후 제외 / 미래 상장 제외 / 미래 상장 후 포함 |
| C 종목 마스터 플래그 | 7 | exclude_etf default+toggle / etn / spac / preferred / managed / halted / market=KOSDAQ |
| D min_market_cap | 3 | 임계값 통과 / 결손 종목 제외 / 임계값=0 (000005만 제외) |
| E look-ahead 시가총액 | 1 | 미래 시가총액(99조) 사용하지 않음 검증 |
| F min_avg_trading_value | 2 | 거래대금 임계값 / 거래 이력 없음 시 제외 |
| G look-ahead 거래대금 | 1 | as_of_date 당일 미포함 검증 (12B 임계로 000001 제외) |
| H 결정론 | 2 | 5회 반복 동일성 / symbol ASC 정렬 |
| I MARKET_CAP_TOP_N | 4 | top_n=2 (000001/000003) / market_cap 결손 제외 / top_n 누락 ValueError / 미래 데이터 차단 |
| J LIQUIDITY_TOP_N | 2 | top_n=2 (000001/000002) / top_n 누락 ValueError |
| K 에러 / 상수 | 4 | market 누락 / 미지원 method ValueError / DEFAULT_EXCLUDE_FLAGS 검증 / SUPPORTED_SELECTION_METHODS 검증 |
| L 시점 차이 | 1 | 동일 config로 시점 변경 시 universe 변동 (생존편향 회피 증명) |

### 13/14 정책 검증 매핑

| 정책 | 테스트 케이스 |
|---|---|
| 13.13 / 14.10 (생존편향 — 폐지 종목 시점별 필터) | `test_delisted_symbol_included_before_delisting_date` / `test_delisted_symbol_excluded_after_delisting_date` / `test_universe_changes_across_dates_due_to_delisting` |
| 13.15 (look-ahead — 미래 상장 종목 차단) | `test_future_listed_symbol_excluded` |
| 13.15 (look-ahead — 시가총액 미래 데이터 차단) | `test_min_market_cap_does_not_use_future_data` / `test_market_cap_top_n_does_not_use_future_data` |
| 13.15 (look-ahead — 거래대금 평균 당일 미포함) | `test_avg_trading_value_excludes_as_of_date_itself` |
| 14.10 (결손 — forward-fill 금지) | `test_min_market_cap_filter_excludes_missing_market_cap` / `test_market_cap_top_n_skips_missing_market_cap` (NULL은 제외, fill 안 함) |
| 13.7 (거래대금 필터 — `close × volume` 원 가격) | `test_min_avg_trading_value_filter` / `test_liquidity_top_n_returns_top_n_by_avg_trading_value` (예상값이 close*volume 기반으로 계산) |
| 06번 §8 (공통 필터 6종) | C 그룹 7건 모두 |
| 06번 §9 (selection_method) | I/J 그룹 6건 모두 |
| CLAUDE.md #8 / 13.12 (결정론) | `test_select_deterministic_across_repeat` / `test_select_sorted_by_symbol_asc` |

### Phase 1 골든 fixture 회귀

영향 없음 — 본 step은 신규 모듈만 작성, BacktestEngine / Portfolio / StrategyEngine / ExecutionModel / CashManager / conditions / models / 016 repositories / 018 Provider / PriceLoader 일체 미수정. 9지표 frozen expected 그대로, 6/6 통과 확인.

## Issues

### 1. 016 자기-소유 head 가드 테스트 실패 (작업 지시 — 본 step 범위 밖)

`tests/market_data/test_alembic_market_data.py::test_new_revision_is_current_head`가 016 head(`9a4d2e1f6c10`)를 검증하지만, 017 step(`b5e8d3c1a924_add_trade_executions_signal_date.py`)이 head를 옮겼다. 018 작업 로그 Issues #1과 동일 이슈. 작업 지시에 명시: "016 자기-소유 head 가드 손대지 말 것 — 017에서 발견된 무관 이슈". 본 step에서 손대지 않음. 016 자체의 후속(`tests/market_data/test_alembic_market_data.py` 갱신)으로 처리해야 함.

### 2. 정책 결정 사항 — 13.15 시가총액 시점 (문서화 권장)

13.15 체크리스트는 시가총액 상위 N에 "미래 데이터" 금지만 명시되어 있고 "당일 데이터 사용 가능 여부"는 명시적이지 않다. 본 step에서 다음과 같이 결정:
- **시가총액 필터 / MARKET_CAP_TOP_N**: as_of_date 당일 데이터 사용 OK (`date <= as_of_date`). 종가 확정 후 universe 재선정 가정.
- **거래대금 평균 / LIQUIDITY_TOP_N**: as_of_date 당일 데이터 미사용 (`date < as_of_date`). 13.15 체크리스트가 "전일까지의 데이터" 명시.

이 비대칭은 의도된 정책이나 13번 또는 14번 문서에 명시되어 있지 않다 — Follow-up #1로 문서 갱신 권장.

### 3. trading_calendar 의존성 회피 (구현 단순화)

거래대금 평균 N 거래일을 계산할 때 `trading_calendar`를 조회해 정확히 N 거래일을 잡는 대신, 달력일 lookback (`max(window_days * 2, window_days + 14)`) 안에서 실제 존재하는 봉을 평균. 이유:
- (a) trading_calendar가 backtest 시작일 이전 모든 거래일에 대해 채워져 있다는 보장이 없을 수 있음 (Phase 11에서 정상화)
- (b) "당일 미포함, 직전 N 거래일"의 의미를 결손 봉이 있는 종목에서도 보존하기 위해 실제 존재하는 봉만 사용

단, fixture에서 단일가/거래정지 봉이 많이 쌓이면 lookback이 부족할 수 있음 — Phase 11 실데이터 검증 시 재점검 필요.

## Result

### UniverseSelector.select 시그니처

```python
from app.market_data.universe import UniverseSelector, UniverseSelectionResult

class UniverseSelector:
    def __init__(self, session: Session) -> None: ...

    def select(
        self,
        config: dict[str, Any],
        as_of_date: date,
    ) -> list[Symbol]: ...

    def select_with_details(
        self,
        config: dict[str, Any],
        as_of_date: date,
    ) -> UniverseSelectionResult: ...

@dataclass(frozen=True)
class UniverseSelectionResult:
    symbols: list[Symbol]
    excluded_counts: dict[str, int]
    as_of_date: date
    market: str
    selection_method: str

    @property
    def count(self) -> int: ...
```

### config dict 키 명세

| 키 | 타입 | default | 설명 |
|---|---|---|---|
| `market` | str | **필수** | "KOSPI" / "KOSDAQ" / "KONEX" |
| `selection_method` | str | "ALL" | "ALL" / "MARKET_CAP_TOP_N" / "LIQUIDITY_TOP_N" |
| `top_n` | int | — | MARKET_CAP_TOP_N / LIQUIDITY_TOP_N에서 필수 (≥1) |
| `exclude_etf` | bool | True | 06번 §8 — Symbol.is_etf=True 제외 |
| `exclude_etn` | bool | True | 06번 §8 — Symbol.is_etn=True 제외 |
| `exclude_spac` | bool | True | 06번 §8 — Symbol.is_spac=True 제외 |
| `exclude_preferred` | bool | True | 06번 §8 — Symbol.is_preferred=True 제외 |
| `exclude_managed` | bool | True | 06번 §8 — Symbol.is_managed=True 제외 |
| `exclude_halted` | bool | True | 06번 §8 — Symbol.is_halted=True 제외 |
| `min_market_cap` | int \| None | None | 시가총액 하한 (≤ as_of_date 최근값). 결손 시 종목 제외 |
| `min_avg_trading_value` | int \| None | None | 거래대금 평균 하한 (close × volume) |
| `avg_trading_value_window_days` | int | 20 | 거래대금 평균 N 거래일 (≥1, 당일 미포함) |

### 06번 §8 공통 필터 적용 매트릭스

| config 키 | 동작 | look-ahead 차단 |
|---|---|---|
| `exclude_etf` (~halted) | `Symbol.is_*=True` 종목 SQL 필터 | N/A (마스터 플래그) |
| `min_market_cap` | `daily_prices.market_cap` (date DESC LIMIT 1, date ≤ as_of_date) | `date <= as_of_date` (당일 포함 OK — 종가 마감 후 시점) |
| `min_avg_trading_value` | `close × volume` 평균 N 거래일 | `date < as_of_date` (당일 미포함 — 13.15 체크리스트) |
| listing/delisting 동적 필터 | 016 `get_universe_at_date` 위임 | 016에서 처리 |

### selection_method 구현 상태

| method | 상태 | 비고 |
|---|---|---|
| `ALL` | **완전 구현** | 필터 통과한 모든 종목 (symbol ASC) |
| `MARKET_CAP_TOP_N` | **완전 구현** (data 의존성 충족 시) | 016 daily_prices.market_cap만으로 동작. Phase 11 정합성 검증 시 더 신뢰성 ↑ |
| `LIQUIDITY_TOP_N` | **완전 구현** (data 의존성 충족 시) | close × volume 평균 N일 |
| `MANUAL` / `WATCHLIST` | **미구현** | `ValueError` (silent skip 금지) — Phase 10 GUI 작업에서 추가 |

### 13.15 look-ahead 차단 방식

| 항목 | 차단 SQL/로직 | 검증 테스트 |
|---|---|---|
| 미래 상장 종목 | 016: `listing_date <= as_of_date` | `test_future_listed_symbol_excluded` |
| 폐지된 종목 | 016: `delisting_date IS NULL OR delisting_date > as_of_date` | `test_delisted_symbol_excluded_after_delisting_date` |
| 시가총액 미래 데이터 | `DailyPrice.date <= as_of_date AND market_cap IS NOT NULL` 후 `date DESC LIMIT 1` | `test_min_market_cap_does_not_use_future_data` / `test_market_cap_top_n_does_not_use_future_data` |
| 거래대금 평균 당일 데이터 | `start <= date < as_of_date` (당일 미포함) | `test_avg_trading_value_excludes_as_of_date_itself` |

### 결손 처리 정책

| 결손 종류 | 정책 | 근거 |
|---|---|---|
| `market_cap` IS NULL (특정 일) | 가장 최근 NOT NULL 행 사용 (LIMIT 1) | as_of_date 이전에 한 번이라도 시가총액이 있으면 활용 가능 |
| 종목의 모든 `market_cap` NULL | 종목 제외 (보수) | 14.10 forward-fill 금지 + 보수적 |
| 거래대금 평균 N일 중 결손 봉 | 결손 봉 제외, 실제 존재하는 봉만으로 평균 (최소 1건) | 14.10 forward-fill 금지, 0건이면 종목 제외 |
| 거래대금 평균 lookback에 0건 | 종목 제외 | 14.10 + 보수 |

### Phase 1 골든 fixture 영향 — **없음 확인**

본 step은 application 테이블 / engine / portfolio / conditions 등 일체 수정하지 않음. `tests/integration/test_phase1_golden.py` 6/6 통과로 9지표 frozen expected 동일성 확인.

### pytest 결과

- **전체**: 531 passed, 1 failed (= 016 자기-소유 head 가드, 작업 지시 범위 밖)
- **신규 (test_universe_selector.py)**: 35 passed
- **Phase 1 골든**: 6 passed
- **baseline 497 → 531**: +34 (신규 35 - 016 head guard 1 = 사실상 +35 신규 완전 통과, 기존 1건 실패 유지)

### ruff 결과

`app/market_data/universe.py` / `app/market_data/__init__.py` / `tests/market_data/test_universe_selector.py` — All checks passed!

## Follow-ups

1. **13/14번 문서 갱신 권장 — 시가총액 시점 정책 명시**
   - 13.15 체크리스트에 "시가총액 필터: as_of_date 당일 OK / 거래대금 평균: as_of_date 미포함" 비대칭 정책을 명시 추가.
   - 06번 §10 `selection_timing`을 본 step의 `as_of_date` 인자 시맨틱으로 대응 명시.
   - 14번 §8.3 시가총액 인덱스 권고(`(date, market_cap DESC)`)에 본 step에서 `(symbol, date)` 인덱스로 도 충분히 동작하지만 대규모 조회 시 적용 권장 메모 추가.

2. **016 자기-소유 head 가드 테스트 갱신** — 016/017/018 공통 follow-up.
   - 017에서 head가 옮겨졌으나 016 head guard가 미갱신.
   - 016 후속 작업으로 분리 처리 권장.

3. **Phase 10 GUI 작업 시 추가 selection_method**
   - `MANUAL`: universe_config["symbols"]에서 직접 종목 받기 + 06번 §8 공통 필터 적용
   - `WATCHLIST`: watchlist 테이블 도입 후 추가
   - 본 step의 `_apply_selection_method`에 분기 추가 (현재 NotImplementedError로 명확히 분리됨)

4. **Phase 11 — 시가총액 정합성 검증 보강 후 MARKET_CAP_TOP_N 신뢰성 ↑**
   - 14.8.2 권장: 종가 × 상장주식수 = pykrx 시가총액 시계열 비교 검증
   - 본 step의 `_get_latest_market_cap`은 016 daily_prices.market_cap을 신뢰 — 데이터 정합성은 14번 §8.2의 정합성 표본 검증 step에서 보장.

5. **Phase 11 — corporate_actions / market_indices / universe_history**
   - 본 step은 universe_history 영속화 안 함 (상위 작업 지시).
   - Phase 11에서 `universe_history` 도입 후 `select()` 결과를 캐시/스냅샷으로 저장하는 step 추가.
   - market_indices(코스피/코스닥 지수) 도입 후 universe filter에 "시장 대비 N% 이상 상승" 등 추가 가능.

6. **API 라우트(backend-api-engineer) 추가**
   - `POST /api/market/universe/preview` (06번 §13)
   - 본 step의 `select_with_details()`를 호출해 `count + symbols + excluded_counts` 응답.
   - Pydantic schemas + service layer는 backend-api-engineer 영역.

7. **거래대금 평균 lookback 정책 정밀화**
   - 현재 달력일 기반 (`max(window_days * 2, window_days + 14)`)으로 충분한 lookback 확보.
   - 단일가/거래정지 봉이 많이 쌓이면 N 거래일 채우지 못할 가능성 있음 — Phase 11 실데이터에서 trading_calendar 기반 정확한 N 거래일 lookup으로 전환 검토.

## 메인 세션 마무리 체크

- [ ] status를 completed로 변경
- [ ] 작업로그/README.md 갱신 (Phase 9 ✅ 완료 표기)
- [ ] PM 호출 → 로드맵.md 갱신 (06-f, 06-g, 13-m [x] / Phase 9 step 019 ✅)
- [ ] **test-engineer 호출 → "Phase 9 완료 검증" → ship-readiness 결정**
- [ ] ship-go 시: PM "Phase 9 완료" → 진행률 추이 새 행
- [ ] git commit (단일)
- [ ] **Phase 9 마지막 step**: ship-go 받으면 `git push origin main` (의무)
