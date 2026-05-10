---
date: 2026-05-10
agent: backtest-engine-developer
phase: 10
status: completed
roadmap_step: 020
roadmap_impact:
  - 04-i  # 복수 종목 (dict[symbol, DataFrame] 또는 MarketDataContext)
  - 04-j  # 날짜별 active universe + final_entry_signal 후보 수집
related_docs:
  - 상세설계/04_backtest_engine_design.md
  - 상세설계/05_portfolio_cash_management_design.md
  - 상세설계/13_backtest_accuracy_policy_design.md
  - 작업로그/2026-05-10-015-execution-date-separation.md
  - 작업로그/2026-05-10-019-universe-selector.md
---

# Step 020 — BacktestEngine 복수 종목 확장 (04-i + 04-j)

외부 리뷰 CR-003의 핵심 — BacktestEngine이 단일 종목 한정에서 복수 종목으로 확장. 본 step은 Phase 10 첫 step이며 **가장 invasive**. priority(021), max_positions(022), event_log(023)는 본 step의 시그니처 위에 추가될 것.

## Plan

### A) BacktestEngine 입력 시그니처 변경 (04-i)
- [x] `상세설계/04_backtest_engine_design.md`의 복수 종목 처리 절 정독 — §6 (날짜별 루프) / §11 (priority — 021 영역) / §17 (MVP 범위 — 복수 종목 포함)
- [x] `상세설계/05_portfolio_cash_management_design.md` Portfolio 다종목 절 — Portfolio.positions가 이미 `dict[str, Position]`로 다종목 호환됨 확인
- [x] `backend/app/backtest/engine.py:run`:
  - 기존: `run(self, df: pd.DataFrame) -> BacktestResult`
  - 신규: `run(self, prices: dict[str, pd.DataFrame] | pd.DataFrame, universe_resolver: Callable[[date], list[str]] | None = None) -> BacktestResult`
  - **호환성 유지**: 단일 `pd.DataFrame` 입력 시 `_normalize_prices`가 `{config.symbol: df}`로 자동 wrap → 기존 골든 fixture 그대로 통과 ✅
  - `universe_resolver(today)` 옵션 — 미지정 시 `sorted(prices.keys())` 전체 사용
- [x] `_ensure_next_date`는 각 symbol df에 개별 적용 (입력 정규화 직후 종목별 신호 생성 + next_date 채움)

### B) 일별 루프 재구조화 (04-j)
- [x] 전체 trading_dates 산출: `all_dates = ⋃ row_map.keys()` 후 `sorted(...)`
- [x] 각 거래일 today에:
  1. **보유 포지션 평가** (today 시작 시점 보유 종목만): `held_at_open = sorted(portfolio.positions.keys())` → `_evaluate_held_symbol`
     - 각 보유 symbol에 대해 `update_market_price` + `_evaluate_exit_position` + exit_signal 평가 + `update_peak_price` (Wave B1 정책) — 015 흐름과 의미 동일
  2. **신규 매수 후보 수집**: `_resolve_active_universe(today, ...)` → `_collect_entry_candidates(today, ...)`
     - active_universe = universe_resolver(today) 또는 `sorted(prices.keys())`
     - 후보: active_universe × today row 존재 × volume > 0 × `final_entry_signal=True`
     - 정렬: **symbol ASC** (active_universe가 sorted된 채로 들어와 그대로 유지)
  3. **매수 처리** (모든 후보 매수 — max_positions 미적용 / step 022 영역):
     - `held_at_open_set`에 있는 종목은 같은 today에 청산되었어도 매수 후보에서 제외 (015 호환의 핵심 — 같은 봉 회전 매매 방지)
     - 각 후보에 대해 `_maybe_buy` 호출 — cash 부족 시 그 후보부터 skip
  4. **일별 자산 기록** (`_record_daily_equity` — Portfolio 전체 기준)
- [x] config.symbol은 단일 종목 호환을 위해 유지 (`_normalize_prices`에서 단일 df의 wrap key로 사용)

### C) Portfolio 다종목 호환 확인
- [x] Portfolio.update_market_price / update_peak_price는 이미 symbol 인자 받음 — 변경 없음
- [x] `total_stock_value()` = `sum(p.market_value for p in self.positions.values())` — 다종목 합산 ✅
- [x] `total_equity()` = cash + total_stock_value — 다종목 동작 ✅
- [x] `positions_count()` = `len(self.positions)` — 다종목 동작 ✅
- [x] sell_symbol_fifo / sell_trade_group은 symbol별 동작 — 변경 없음
- [x] 새 종목 매수도 `Portfolio.buy(symbol=...)`로 자연 동작 (이미 `if symbol in self.positions: ...` 분기 존재)

### D) 결정론
- [x] dict 순회 모두 제거: `sorted(prices_dict.keys())` / `sorted(portfolio.positions.keys())` 명시
- [x] 후보 정렬: `_resolve_active_universe`가 `sorted(...)` 강제, `_collect_entry_candidates`가 그 순서를 그대로 유지 → symbol ASC tie-breaker 보장
- [x] 보유 포지션 순회: `held_at_open = sorted(...)` 명시
- [x] 결정론 5회 반복 테스트 통과 (`test_multi_symbol_determinism_5_runs`)

### E) Phase 1 골든 fixture 호환 검증 (필수)
- [x] 단일 df 입력 시 자동 wrap 동작 → 9지표 frozen expected 그대로 ✅:
  - final_equity 10,188,570 / total_return 1.8857 / mdd -4.9032 / trade_count 8 / open_position_count 1 / win_rate 37.5 / **avg_holding_days 6.5** / profit_factor 1.2252
  - 첫 거래 entry_date 2024-01-13 (signal_date 2024-01-12)
- [x] 결정론 10회 반복 (`test_golden_03_full_determinism_10_runs`) PASSED 유지
- [x] **결정적 의존**: `held_at_open_set`로 같은 today 청산 후 즉시 재진입 차단 — 015 흐름의 `if/elif` 의미를 보존하지 않으면 골든 final_equity가 10,132,580으로 변동했음. 본 step의 핵심 정합성 결정이며 priority(021) / max_positions(022) 도입 시에도 유지되어야 한다.

### F) 신규 단위 테스트 (15건 신규 / 신규 파일)
- [x] `backend/tests/backtest/test_backtest_engine_multi_symbol.py` 신규 — 15건:
  - **A) 단일 DataFrame 자동 wrap** (2건): `test_single_dataframe_input_auto_wraps_to_dict`, `test_single_symbol_dict_equivalent_to_single_dataframe`
  - **B) 복수 종목 동시 매수** (2건): `test_two_symbols_simultaneous_entry_both_buy_when_cash_sufficient`, `test_existing_position_plus_new_entry_added_for_other_symbol`
  - **C) 후보 정렬 (symbol ASC + cash 부족 skip)** (2건): `test_simultaneous_entries_processed_in_symbol_asc_order_when_cash_partial`, `test_cash_shortage_skips_remaining_candidates_but_not_earlier_ones`
  - **D) universe_resolver** (3건): `test_universe_resolver_excludes_symbol_from_buy_candidates`, `test_universe_resolver_changes_per_day`, `test_universe_resolver_does_not_block_held_position_evaluation`
  - **E) 결정론 5회 반복** (1건): `test_multi_symbol_determinism_5_runs`
  - **F) 입력 정규화** (3건): `test_empty_prices_dict_raises`, `test_invalid_prices_value_type_raises`, `test_invalid_prices_top_type_raises`
  - **G) 같은 today 청산+매수** (1건): `test_same_day_exit_a_and_buy_b`
  - **H) 종목별 거래정지** (1건): `test_per_symbol_no_volume_skips_only_that_symbol`
- [x] e2e 통합 테스트 신규 파일은 본 step에서는 보류 — 023 (event_log) 또는 Phase 10 마지막 시나리오 step에서 통합 테스트가 더 의미 있음 (priority/max_positions 동시 검증)

### G) 회귀
- [x] 전체 pytest: **551 passed / 1 failed** (016 자기-소유 head 가드, 알려진 무관)
  - 신규 15건 모두 PASSED
  - Phase 1 골든 fixture 6건 모두 PASSED (frozen expected 그대로)
  - 015 회귀 (signal_date / execution_date) 모두 PASSED
  - 결정론 회귀 모두 PASSED
- [x] ruff: 본 step 변경 파일(`app/backtest/engine.py`, 신규 multi-symbol 테스트) **All checks passed**
  - 전체 ruff 11건은 alembic 자동생성 파일 (UP007 / UP035 / I001 / W291) — 본 step과 완전히 무관
- [x] 016 자기-소유 head 가드 1건은 알려진 무관 fail로 그대로 둠

### 절대 금지
- StrategyEngine, ExecutionModel, conditions/* 절대 수정 (다른 에이전트 영역)
- API 라우트 / Pydantic schemas / services 추가/수정 금지 (backend-api-engineer 영역)
- 시장데이터 모델 / market_data/* 수정 금지 (016~019 산출물 — 활용만)
- application 모델 수정 금지 (017까지 완료)
- conditions/* 수정 금지
- BacktestEngine에 신호 생성 / 가격 계산 / 자금 관리 로직 직접 추가 금지 (오케스트레이터 유지)
- **priority 알고리즘 도입 금지** — step 021 영역
- **max_positions / max_daily_entries / daily_buy_budget 도입 금지** — step 022 영역
- **event_log / 거래정지·상한가·하한가·상장폐지 강제 매도 도입 금지** — step 023 영역
- 015 호환성 유지: signal_date / execution_date 정합 그대로
- Wave B1 호환성 유지: peak_price prev-high 갱신 시점
- Wave C1 호환성 유지: ExecutionResult dataclass 흐름 그대로
- 결정론 깨기 (dict 순회, 시드 없는 random)
- look-ahead bias

### 다음 step (021) 인계 정보
- 후보 정렬 부분(_collect_entry_candidates 또는 동등)이 어디 있는지 — 021이 priority 알고리즘으로 교체
- universe_resolver 시그니처
- 일별 루프 흐름

## Execution

### A) 입력 시그니처 변경 + 정규화 (`backend/app/backtest/engine.py`)
- `engine.py:1-65` (모듈 docstring): Phase 10 step 020 — 복수 종목 입력 명세 + 일별 루프 흐름 + 015 호환성 + scope 한계(priority/max_positions/event_log는 후속) 명시
- `engine.py:108-115`: `run` 시그니처 변경 — `run(self, prices: dict[str, pd.DataFrame] | pd.DataFrame, universe_resolver: Callable[[date], list[str]] | None = None) -> BacktestResult`
- `engine.py:148-167`: `run` 본체 — `_normalize_prices` 호출 + 종목별 `generate_signals` + `_ensure_next_date` + 종목별 `rows_by_date` 인덱스 구축
- `engine.py:178-184`: `trading_dates = sorted(⋃ row_map.keys())` — 모든 symbol df의 date 합집합
- `engine.py:259-280` 신규 `_normalize_prices`: 단일 DataFrame → `{config.symbol: df}` wrap, dict는 그대로 (빈 dict / 잘못된 type은 명시적 에러)

### B) 일별 루프 재구조화
- `engine.py:194-225` (보유 평가): `held_at_open = sorted(self.portfolio.positions.keys())` 후 종목별 `_evaluate_held_symbol` — universe와 무관하게 보유 평가 진행 (04번 §6 Step 2 준수)
- `engine.py:227-254` (매수 후보 + 처리): `_resolve_active_universe` → `_collect_entry_candidates` → 후보 순회 매수
  - `held_at_open_set` 가드: 같은 today 청산된 종목은 매수 후보에서 제외 — **Phase 1 골든 fixture 호환의 핵심**
- `engine.py:256-258`: `_record_daily_equity` (Portfolio 전체 기준)

### B-1) 신규 헬퍼 메서드
- `engine.py:285-329` `_evaluate_held_symbol`: 보유 종목 1개 평가 — update_market_price → exit_position → exit_signal → update_peak_price (015 단일 종목 흐름의 의미를 종목 단위로 추출)
- `engine.py:331-350` `_resolve_active_universe`: universe_resolver 호출 또는 prices.keys() — 결정론 위해 sorted 강제
- `engine.py:352-381` `_collect_entry_candidates`: active_universe × today row × volume>0 × final_entry_signal → (symbol, row) 리스트. **본 step에서는 symbol ASC만, priority 알고리즘은 step 021이 본 메서드를 교체**

### C) 결정론
- 모든 dict 순회 제거: `sorted(prices_dict.keys())` (signaled 구축), `sorted(portfolio.positions.keys())` (보유 평가), `sorted(...)` (universe 정렬)
- 후보 정렬: symbol ASC tie-breaker (priority 알고리즘 도입은 021)

### D) 신규 테스트 (`backend/tests/backtest/test_backtest_engine_multi_symbol.py`)
- 15건 신규 — 단일 wrap 호환 / 동시 매수 / 후보 정렬 / universe_resolver / 결정론 / 입력 정규화 / 같은 today 청산+매수 / 종목별 거래정지

### E) Portfolio / CashManager / StrategyEngine / Conditions / Models
- **변경 0건** — Portfolio.positions는 이미 `dict[str, Position]`로 다종목 호환됨. 본 step은 활용만.
- API / schemas / services / market_data / models 모두 변경 0건 — scope 외 (다른 에이전트 영역)

## Tests

```
cd backend && ./.venv/Scripts/python.exe -m pytest
```
- **551 passed / 1 failed** (016 자기-소유 head 가드, 알려진 무관 — 본 step과 완전 별개)
  - 신규 15건 모두 PASSED
  - Phase 1 골든 6건 모두 PASSED (frozen 9지표 변동 0)
  - 015 회귀 (signal_date / execution_date 분리) 모두 PASSED
  - 결정론 10회 반복 (`test_golden_03_full_determinism_10_runs`) PASSED
  - C1·C2·B1 (Wave A/B/C) 회귀 모두 PASSED
- ruff (변경 파일): All checks passed

### 정확성 정책 13.17 검증 항목 매핑
- "다음날 시가 체결이 정확한지" (13.17.4): `test_two_symbols_simultaneous_entry_both_buy_when_cash_sufficient` (execution_date == next_date 검증)
- "현금 부족 시 매수가 차단되는지" (13.17.17): `test_simultaneous_entries_processed_in_symbol_asc_order_when_cash_partial`, `test_cash_shortage_skips_remaining_candidates_but_not_earlier_ones`
- "동시 신호 우선순위 결정론" (13.17.10): `test_multi_symbol_determinism_5_runs` + `test_simultaneous_entries_processed_in_symbol_asc_order_when_cash_partial` (symbol ASC tie-breaker)
- "거래정지 종목 매수/매도 차단" (13.17.5): `test_per_symbol_no_volume_skips_only_that_symbol`
- "listing_date 기반 생존편향 완화" (04번 §17): `test_universe_resolver_changes_per_day`, `test_universe_resolver_does_not_block_held_position_evaluation` (universe 동적 필터의 unit-level 검증; 실제 `listing_date`/`delisting_date` 필터는 019 UniverseSelector가 담당)

## Issues

### 정책 명시 권장 (04번 / 13번 갱신 후속)
- **04번 §6 (날짜별 루프)** + **04번 §11 (priority)** 갱신 권장:
  - "보유 포지션 평가는 today 시작 시점 보유 종목 기준 — 같은 today에 청산된 종목은 매수 후보에서 제외 (같은 봉 회전 매매 방지)" 명시
  - "단일 종목 호환: `run(df)` 또는 `run({symbol: df})` 모두 동작" 명시
- **04번 §6 Step 1**: "현재 날짜의 유니버스 결정"은 매수 후보에만 적용, 보유 평가는 universe와 독립 — 본 step에서 강제했으나 04번에 명시되지 않음
- **본 step은 priority 알고리즘을 도입하지 않음** — 004번 §11 (priority) 자체는 step 021의 단일 출처. 본 step에서는 §11의 후보 정렬 자리에 symbol ASC tie-breaker만 들어가 있음 (021이 trading_value_desc / market_cap_desc / random으로 교체)

### scope 외 후속 step 인계
- **step 021 (priority 알고리즘)**: `_collect_entry_candidates` 메서드(`engine.py:352-381`)가 priority 알고리즘으로 교체될 자리. 현재는 `active_universe`(이미 sorted) 순회 + final_entry_signal 필터만. 021은 scoring + tie-breaker 정렬이 그 자리에 들어감.
- **step 022 (max_positions / max_daily_entries / daily_buy_budget)**: `run` 메서드의 매수 처리 루프(`engine.py:240-254`)에 limit 체크 추가 자리. 현재는 cash 부족 시만 skip, max 한도는 미적용.
- **step 023 (event_log / 거래정지·상한가·상장폐지 강제 매도)**: 보유 평가 + 매수 후보 수집 두 곳 모두 event_log 추가 자리. 현재는 `cash_events`만 누적.

### 알려진 무관 실패
- `tests/market_data/test_alembic_market_data.py::test_new_revision_is_current_head` 1건 — 016 작업의 후속 alembic head 가드. 본 step과 완전히 무관 (Phase 10 별도 fix step 또는 Phase 마지막에).

## Result

### 적용 정확성 정책
- **13.3 (일중 익절/손절)**: 종목별로 동일 평가 — 변경 없음
- **13.3.5 + 13.15 (peak 전일까지 high)**: 종목별로 update_peak_price — Wave B1 그대로
- **13.4 (갭/거래정지)**: 종목별 적용 — 같은 today 일부 종목 거래정지여도 다른 종목 정상 처리
- **13.6 (거래세 시계열)**: 변경 없음 (ExecutionModel 그대로)
- **13.12 (결정론)**: dict 순회 모두 제거, 후보 정렬에 symbol ASC tie-breaker 강제
- **13.13 (생존편향)**: universe_resolver 옵션으로 19 UniverseSelector와 연결될 자리 마련 — 본 step은 unit-level 검증만
- **13.15 (look-ahead)**: 매일 today를 기준으로 그 시점의 universe만 매수 후보. 015 호환성 유지 (signal_date / execution_date)
- **13.16 (이벤트 우선순위)**: 종목별로 동일 우선순위 — 변경 없음
- **04.6 (날짜별 루프)**: 다종목으로 일반화. 보유 평가 → 매수 후보 → 매수 → 일별 자산 순서 보존
- **04.10.3 (exit_position vs exit_signal 우선순위)**: 종목별로 동일 — 변경 없음
- **04.17 (MVP 범위)**: 복수 종목 백테스트 ✅, priority 알고리즘 (021), 최대 보유 종목 수 (022), event_log (023)는 후속

### 신규 시그니처

```python
# 단일 종목 호환 (015 이전과 동일)
result = engine.run(df)

# 복수 종목 신규
result = engine.run({"000001": df_a, "000002": df_b})

# universe_resolver — 일별 active universe 동적 변경
def resolver(today: date) -> list[str]:
    return [...]  # 그 거래일의 매수 후보 종목 코드 (보유 평가는 universe와 독립)

result = engine.run({"000001": df_a, "000002": df_b}, universe_resolver=resolver)
```

### 일별 루프 흐름 (04번 §6 정합)
1. **보유 평가** (`held_at_open = sorted(portfolio.positions.keys())`):
   - row_map / today row / volume > 0 가드
   - `_evaluate_held_symbol`: update_market_price → exit_position → exit_signal → update_peak_price
2. **매수 후보 수집** (`_resolve_active_universe(today, ...)` → `_collect_entry_candidates(today, ...)`):
   - active_universe = universe_resolver(today) 또는 sorted(prices.keys())
   - 후보: active × today row 존재 × volume > 0 × final_entry_signal
3. **매수 처리** (`held_at_open_set` 가드 + `_maybe_buy`):
   - 같은 today 청산된 종목 제외 (회전 매매 방지 — 015 호환)
   - 후보 순회, cash 부족 시 그 후보부터 skip
4. **일별 자산 기록**: `_record_daily_equity` (Portfolio 전체)

### 후보 정렬 정책
- **본 step**: `_resolve_active_universe`가 sorted 강제 → `_collect_entry_candidates`가 그 순서를 보존 → **symbol ASC tie-breaker만**
- **step 021 인계**: `_collect_entry_candidates` 메서드가 priority 알고리즘 적용 자리. trading_value_desc / market_cap_desc / random 모드를 추가하면서 symbol ASC tie-breaker를 항상 정렬 키 마지막 요소로 유지해야 결정론 보존 (04번 §11.2)

### Phase 1 골든 fixture 9지표 frozen 회귀 결과 (단일 df 호환)
| 지표 | 015 baseline | 본 step | 일치 여부 |
|---|---|---|---|
| initial_cash | 10,000,000 | 10,000,000 | ✅ |
| final_equity | 10,188,570 | 10,188,570 | ✅ |
| total_return_pct | 1.8857 | 1.8857 | ✅ |
| mdd_pct | -4.9032 | -4.9032 | ✅ |
| trade_count | 8 | 8 | ✅ |
| open_position_count | 1 | 1 | ✅ |
| win_rate | 37.5 | 37.5 | ✅ |
| avg_holding_days | 6.5 | 6.5 | ✅ |
| profit_factor | 1.2252 | 1.2252 | ✅ |
| 첫 거래 entry_date | 2024-01-13 | 2024-01-13 | ✅ |
| 첫 거래 signal_date | 2024-01-12 | 2024-01-12 | ✅ |

> **결정적 정합성 결정**: `held_at_open_set` 가드 없이 단순 종목 루프로 다종목으로 일반화하면 final_equity가 10,132,580으로 변동했음 (같은 today 청산 후 즉시 재진입 발생). 015 흐름의 `if/elif` 의미 보존 = `held_at_open_set` 가드 = 본 step의 핵심 정합성 결정.

### 결정론 보장 방법
- `sorted(prices_dict.keys())` / `sorted(portfolio.positions.keys())` / `sorted(active_universe)` — dict 순회 의존 0건
- `_collect_entry_candidates`가 input 순서 보존 → priority 알고리즘 도입(021) 시에도 symbol ASC tie-breaker 자리 명확
- 5회 반복 결정론 테스트 (`test_multi_symbol_determinism_5_runs`) PASSED

### look-ahead bias 검증
- universe_resolver는 today 기준 호출 — 미래 데이터 미사용
- 015 정책 그대로: next_date는 미리 채우지만 본 row 평가에 next 가격/조건 미사용
- universe에서 제외된 종목도 보유 평가는 진행 (04번 §6 Step 2 준수) — 미래 데이터 영향 0

## Follow-ups

1. **step 021 — priority 알고리즘 (외부 CR-003 후속)**:
   - `_collect_entry_candidates` 메서드(`engine.py:352-381`)에 priority 적용
   - `strategy.priority.method`: trading_value_desc / market_cap_desc / random
   - tie_breaker: symbol_asc / symbol_desc (기본 symbol_asc 그대로)
   - random_seed는 `strategy.metadata.random_seed`에서 — 04번 §11.2
2. **step 022 — max_positions / max_daily_entries / daily_buy_budget**:
   - `run` 매수 처리 루프(`engine.py:240-254`)에 limit 체크
   - position_sizing.method 적용 (현재는 fixed_amount만)
   - daily_buy_budget 한도, risk_management.stop_trading_on_drawdown_pct 추가
3. **step 023 — event_log / 거래정지·상한가·상장폐지 강제 매도**:
   - EventLogger 모듈 신설 또는 Portfolio.event_logs로 누적
   - 거래정지(volume==0) / 상한가/하한가 / 상장폐지 강제 매도 추가
   - DB 영속화 매핑 (event_log 테이블) — backend-api-engineer 협업
4. **04번 / 13번 문서 갱신 (정책 명시)**:
   - 04번 §6 Step 1: "유니버스는 매수 후보에만 적용, 보유 평가는 universe와 독립" 명시
   - 04번 §6 Step 4-5 사이: "같은 today에 청산된 종목은 매수 후보에서 제외 (같은 봉 회전 매매 방지)" 명시
   - 04번 §17: "단일 종목 호환: `run(df)` 또는 `run({symbol: df})` 모두 동작" 명시
5. **services/backtest_service의 다종목 통합**:
   - 현재 backtest_service는 단일 종목 전용 (PriceLoader가 1종목 df만 반환). 본 step의 다종목 인터페이스를 활용하려면 strategy.universe 섹션을 읽어 PriceLoader가 dict 반환 + UniverseSelector 통합 필요. **별도 step**.
6. **016 자기-소유 head 가드 1건 fix** — Phase 10 별도 fix step 또는 마지막에. 본 step과 무관.

## 메인 세션 마무리 체크

- [ ] status를 completed로 변경
- [ ] 작업로그/README.md 갱신
- [ ] PM 호출 → 로드맵.md 갱신 (04-i, 04-j [x] / Phase 10 step 020 ✅)
- [ ] git commit (Phase 10 마지막 step 아니므로 push 보류)
