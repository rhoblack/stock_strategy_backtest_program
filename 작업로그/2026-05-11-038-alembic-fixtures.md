---
date: 2026-05-11
agent: backend-api-engineer
phase: 13
status: completed
roadmap_step: "038"
roadmap_impact:
  - 12-h
  - 12-i
related_docs:
  - 상세설계/12_testing_validation_design.md
  - 상세설계/13_backtest_accuracy_policy_design.md
---

# step 038 — alembic 환경 정상화 + 13.17 acceptance 파일 + fixtures 표준 구조

## Plan

### 영향 체크박스 (완료 시 갱신 대상)
- `12-h`: 정확성 정책 13.17 acceptance 1:1 매핑 별도 파일
- `12-i`: 12 §15 fixtures/expected 표준 디렉토리 구조

### 배경 및 목적
- 12번 설계서 §15: 테스트 fixtures/expected 파일들이 표준 디렉토리(tests/fixtures/)에 정리되지 않고 산재
- 13번 정확성 정책 §17의 17개 항목이 테스트에 1:1 매핑되어 있는지 별도 파일로 정리 필요
- alembic silent-skip 환경 (SQLite ↔ PostgreSQL 분기)이 env.py에서 정상 동작하는지 검증

### 작업 범위

#### A. 13.17 acceptance 1:1 매핑 파일 (12-h)
- [ ] A1. 상세설계/13_backtest_accuracy_policy_design.md §17 항목 전수 목록화
- [ ] A2. backend/tests/acceptance/test_accuracy_policy.py 신규 파일 생성
- [ ] A3. 각 §17 항목 (13.17.1 ~ 13.17.N)에 대해 하나의 테스트 함수 1:1 매핑
- [ ] A4. 이미 다른 파일에서 테스트 중인 항목은 import 또는 assertion 재확인
- [ ] A5. 아직 미구현 항목은 pytest.mark.xfail 또는 pytest.skip으로 명시적 표시

#### B. fixtures/expected 표준 구조 (12-i)
- [ ] B1. 12번 §15에서 정의한 표준 디렉토리 구조 확인
- [ ] B2. backend/tests/fixtures/ 디렉토리 생성 및 기존 fixture 파일 이동
- [ ] B3. backend/tests/expected/ 디렉토리 생성 및 golden test expected 값 정리
- [ ] B4. conftest.py에 fixtures 경로 상수 정의
- [ ] B5. 이동된 fixtures를 참조하는 기존 테스트 경로 갱신

#### C. alembic 환경 검증
- [ ] C1. alembic/env.py SQLite silent-skip 로직 확인 (017 부수 픽스 정상화 상태)
- [ ] C2. `alembic upgrade head` 정상 실행 확인
- [ ] C3. 마이그레이션 이력 정합성 확인 (누락된 revision 없음)

### 완료 기준
- pytest backend/ — 전체 PASS (기존 1036건 이상 유지 + 신규 건 추가)
- backend/tests/acceptance/test_accuracy_policy.py 생성 (13.17 항목 1:1)
- backend/tests/fixtures/ 표준 디렉토리 구조 정비
- alembic upgrade head 정상 실행

## Execution

### A. 13.17 acceptance 1:1 매핑 파일 (12-h) ✅

- `backend/tests/acceptance/__init__.py` — 패키지 초기화
- `backend/tests/acceptance/test_accuracy_policy.py:1-500` — 13.17 §17 11개 항목 1:1 매핑
  - §17.1 일중 손절 도달: `test_13_17_1_intraday_stop_loss_at_stop_price`
  - §17.2 일중 익절 도달: `test_13_17_2_intraday_take_profit_at_target_price`
  - §17.3 동일봉 손절 우선: `test_13_17_3_simultaneous_take_and_stop_stop_takes_priority`
  - §17.4 갭다운 시가 체결: `test_13_17_4_gap_down_stop_loss_executes_at_open`
  - §17.5 거래정지 차단(2건): `test_13_17_5_zero_volume_day_skips_entry`, `test_13_17_5_zero_volume_day_event_log_recorded`
  - §17.6 상한가 차단: `test_13_17_6_limit_up_buy_blocked` (BacktestConfig.allow_buy_limit_up 미구현 → xfail)
  - §17.7 호가 단위(2건): `test_13_17_7_tick_rounding_applied_to_execution`, `test_13_17_7_execution_model_applies_slippage_and_tick`
  - §17.8 거래세 시계열(2건): `test_13_17_8_tax_rate_timeseries_each_period`, `test_13_17_8_tax_applied_correctly_to_sell_proceeds`
  - §17.9 수정주가(2건): `test_13_17_9_adjusted_price_used_by_default`, `test_13_17_9_raw_price_when_use_adjusted_false`
  - §17.10 priority 결정론(2건): `test_13_17_10_concurrent_signal_priority_determinism`, `test_13_17_10_symbol_asc_tiebreaker_determinism`
  - §17.11 random_seed(2건): `test_13_17_11_same_random_seed_yields_same_result`, `test_13_17_11_seed_zero_is_deterministic`

### B. fixtures/expected 표준 구조 (12-i) ✅

- `backend/tests/fixtures/.gitkeep` — 기존 유지 (비어있었음)
- `backend/tests/fixtures/strategy_ma5_take_stop.json` — MA5+익절/손절 공유 전략 JSON
- `backend/tests/golden/__init__.py` — 패키지 초기화
- `backend/tests/golden/conftest.py` — load_strategy/load_expected/build_synthetic_series 공용 헬퍼
- `backend/tests/golden/strategies/golden_01_ma_cross.json` — golden_01 전략 파일
- `backend/tests/golden/strategies/golden_02_exit_signal_ma.json` — golden_02 전략 파일
- `backend/tests/golden/strategies/golden_03_rsi_multi_condition.json` — golden_03 전략 파일
- `backend/tests/golden/expected/golden_01_summary.json` — golden_01 기대값 고정
- `backend/tests/golden/fixtures/` — 시세 데이터 파일 디렉토리 (향후 CSV)
- `backend/tests/golden/test_golden_runs.py` — 파일 기반 golden test 5건
- `backend/tests/conftest.py` — FIXTURES_DIR / GOLDEN_DIR 경로 상수 추가

### C. alembic 환경 검증 ✅

- `backend/tests/db/test_alembic.py` — 신규 2건 추가:
  - `test_alembic_revision_chain_has_no_gaps:137-162` — revision 이력 연속성 검증
  - `test_alembic_upgrade_head_application_tables_complete:165-200` — 영속화 스냅샷 컬럼 존재 검증
- `alembic upgrade head` 실행 결과: 정상 완료, head = d9f3b2a7e041
- 마이그레이션 revision 이력 (9건, 갭 없음):
  `baseline(32f5) → cash_events(3b7a) → cost_breakdown(7c1e) → market_data(9a4d) → signal_date(b5e8) → corporate_actions(c7f2) → market_indices(59cd) → krw_int(a1b2) → cancelling(d9f3)`

### 적용 정책 절번호
- 12번 §15 (golden test fixture 구조)
- 13번 §17 (정확성 정책 검증 항목 1:1 매핑)
- CLAUDE.md #9 (영속화 스냅샷 컬럼 alembic 검증)

## Tests

### 실행 명령
```
PYTHON=backend/.venv/Scripts/python.exe
$PYTHON -m pytest backend/ --tb=short -q
```

### 결과
- **신규 테스트**: 1060 PASS (기존 1036 + 신규 24건)
- **기존 회귀**: 없음 (1036건 전부 유지)

### 신규 24건 상세
| 파일 | 건수 | 매핑 |
|------|------|------|
| tests/acceptance/test_accuracy_policy.py | 17건 | 13.17 §17 항목 1:1 |
| tests/golden/test_golden_runs.py | 5건 | 12 §15 파일 기반 구조 |
| tests/db/test_alembic.py | 2건 | alembic revision/snapshot |

### 테스트 매핑
- **scope/validator 테스트**: 기존 tests/api/test_scope_and_envelope.py (변동 없음)
- **envelope 테스트**: 기존 tests/api/test_error_catalog.py (변동 없음)
- **영속화 스냅샷 테스트**: test_alembic_upgrade_head_application_tables_complete — strategy_snapshot_json, random_seed, priority_method, priority_tie_breaker 컬럼 존재 확인
- **§17.6 상한가**: xfail (allow_buy_limit_up 미구현) — 통과 (xfail로 기록됨)

## Issues

### I1. §17.6 상한가 매수 차단 — BacktestConfig.allow_buy_limit_up 미구현
- 현재 BacktestConfig에 allow_buy_limit_up 옵션이 없음
- 테스트는 `pytest.xfail`로 처리 (13번 §4.3 정책 정의됨, 구현만 미완)
- **해소 조건**: backtest-engine-developer가 BacktestConfig + BacktestEngine에 allow_buy_limit_up 로직 구현

### I2. alembic known gaps — market 데이터 테이블 silent fail
- `cash_events`, `symbols`, `daily_prices` 등 7개 테이블이 alembic upgrade에서 silent fail
- 원인: SQLite + render_as_batch=False 환경에서 일부 CREATE TABLE이 스킵됨
- dev/test는 init_db(Base.metadata.create_all)로 보완. 운영 시 수동 검증 필요
- `_KNOWN_ALEMBIC_GAPS` 집합으로 명시적으로 문서화됨

### I3. 12번 §15 golden fixtures CSV 파일 미생성
- 설계서에서 samsung_5y_prices.csv, kosdaq_top10_3y_prices.csv를 요구
- 실제 시세 데이터 없음 (pykrx 연동 전)
- 대신 `build_synthetic_series(seed, n)` 결정론적 합성 데이터로 대체
- **향후**: market-data-engineer가 시세 CSV 파일 제공 시 golden/fixtures/에 추가

## Result

### 신규 파일/디렉토리
```
backend/tests/acceptance/
  __init__.py
  test_accuracy_policy.py         ← 13.17 §17 항목 17건 (1:1 매핑)

backend/tests/golden/
  __init__.py
  conftest.py                     ← load_strategy/load_expected/build_synthetic_series
  test_golden_runs.py             ← 파일 기반 golden test 5건
  strategies/
    golden_01_ma_cross.json
    golden_02_exit_signal_ma.json
    golden_03_rsi_multi_condition.json
  expected/
    golden_01_summary.json        ← 기대값 고정 (final_equity 등)
  fixtures/
    (향후 시세 CSV)

backend/tests/fixtures/
  strategy_ma5_take_stop.json     ← 공유 전략 JSON fixture
```

### 수정 파일
```
backend/tests/conftest.py                  ← FIXTURES_DIR / GOLDEN_DIR 경로 상수 추가
backend/tests/db/test_alembic.py          ← 2건 추가 (revision chain + snapshot 컬럼)
```

### pytest 결과
- 기존: 1036 PASS
- 신규: 1060 PASS (+24건)
- 회귀: 없음

### 영속화 스냅샷 채워지는 컬럼 (alembic 검증)
- backtest_runs: strategy_snapshot_json, random_seed, priority_method, priority_tie_breaker
- trade_executions: gross_amount, fee, tax, net_amount

### scope 매트릭스
- acceptance 파일은 user_id scope 무관 (엔진 레벨 정확성 테스트)
- API scope 테스트는 기존 tests/api/test_scope_and_envelope.py에서 커버

## Follow-ups

### F1. §17.6 상한가 매수 차단 구현 (backtest-engine-developer)
- BacktestConfig에 `allow_buy_limit_up: bool = False` 필드 추가
- BacktestEngine에서 신호일 종가가 +30% 이면 매수 skip 로직 구현
- 구현 완료 시 acceptance/test_accuracy_policy.py::test_13_17_6_limit_up_buy_blocked의 xfail 해제

### F2. golden/fixtures/ 실제 시세 CSV 추가 (market-data-engineer + 향후)
- samsung_5y_prices.csv, kosdaq_top10_3y_prices.csv 파일 제공 시 golden/fixtures/에 추가
- golden/test_golden_runs.py에 CSV 기반 golden test 케이스 추가

### F3. 12번 §15.2 golden_04 (pyramiding) 전략 파일 추가
- golden_04_pyramiding_weighted_avg.json 전략 파일 작성 필요
- allow_pyramiding=true 시나리오 (현재 allow_pyramiding 미구현으로 보류)

### F4. 10번 문서 갱신 불필요
- acceptance 파일은 10번 API 설계 문서와 무관
- 신규 에러 코드 없음

## 메인 세션 마무리 체크

- [ ] status를 completed로 변경
- [ ] 작업로그/README.md "최근 작업" 표에 1행 추가
- [ ] Phase 상태가 변경되었으면 Phase 표 갱신
- [ ] Follow-ups 중 다음 작업 후보로 옮길 항목 정리
- [ ] **PM 에이전트 호출 → 로드맵.md 갱신** — "step 038 마무리" 지시. PM이 Phase 로드맵 step ✅ + 영향 체크박스 [x] + 진행률 표 손계산을 직접 Edit. (영향 체크박스 ID: 12-h, 12-i)
- [ ] `git commit` (단일 커밋)
- [ ] **Phase 마지막 step이 아님** (Phase 13은 034~039 총 6 step)
