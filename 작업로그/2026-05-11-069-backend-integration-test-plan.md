---
date: 2026-05-11
agent: test-engineer (step 069/070/071)
phase: 23
status: completed
roadmap_step: "069"
roadmap_impact:
  - 12-m   # step 069 — 백테스트 end-to-end 통합 (전략→실행→결과→export)
  - 12-n   # step 070 — Phase 22 신기능 복합 시나리오 (MDD+delisting+cash_below_threshold)
  - 12-o   # step 071 — pykrx 실데이터 smoke test
related_docs:
  - 상세설계/04_backtest_engine_design.md
  - 상세설계/07_database_design.md
  - 상세설계/10_api_design.md
  - 상세설계/12_testing_validation_design.md
  - 상세설계/13_backtest_accuracy_policy_design.md
  - 상세설계/14_data_pipeline_design.md
---

# Phase 23: 백엔드 통합 테스트 계획

## 통합 테스트 범위 및 목표

### 배경

Phase 22까지 모든 설계서 체크리스트 217/217 = 100% 달성.
백엔드 pytest 1,116 PASS / 프론트엔드 vitest 266 PASS.
기존 integration/ 디렉토리에 9개 통합 테스트 파일이 존재하나,
Phase 22 신규 기능(MDD 거래중단·delisting_estimated·cash_below_threshold·priority 3종)을 포함하는
복합 end-to-end 시나리오 및 실데이터 smoke test가 부재.

### 목표

1. **step 069**: 전략 생성 → 백테스트 실행 → 결과 조회 → export 전 흐름의 API 수준 e2e 통합 테스트
2. **step 070**: Phase 22 신기능(MDD·delisting_estimated·cash_below_threshold·priority 신종) 복합 시나리오 통합 테스트
3. **step 071**: pykrx 실데이터 smoke test (기본 실행에서 분리, @pytest.mark.realdata)

### 기술 제약

- httpx + pytest-asyncio 사용 (requirements 확인 후 없으면 추가)
- 실 SQLite in-memory DB 사용 (`:memory:` 또는 tmpdir fixture)
- FastAPI app을 직접 임포트해 TestClient(동기) 또는 httpx AsyncClient(비동기)로 테스트
- 각 테스트는 독립적 (DB 초기화 fixture로 격리)
- pykrx 실데이터 테스트는 반드시 @pytest.mark.realdata로 분리
- ruff All checks passed 유지
- CLAUDE.md 모든 원칙 준수

---

## 테스트 시나리오 목록

### step 069 — 백테스트 end-to-end (파일: test_phase23_backtest_e2e.py)

- [ ] E23-01: 전략 생성(POST /api/strategies) → 백테스트 실행(POST /api/backtests/run) → 결과 조회(GET /api/backtests/{id}/summary) 전 흐름 — 실 SQLite in-memory DB + 실 BacktestEngine + httpx AsyncClient
- [ ] E23-02: 거래 내역 조회 (GET /api/backtests/{id}/trades) → 결과 CSV export (GET /api/backtests/{id}/export/trades)
- [ ] E23-03: 전략 버전 저장 → 동일 strategy_snapshot_json으로 결과 재현성 확인 (2회 실행 → 동일 메트릭)
- [ ] E23-04: 백테스트 취소(CancellationToken) end-to-end (POST /api/backtests/{id}/cancel)
- [ ] E23-05: 잘못된 전략 JSON → API 에러 응답 확인 (422 Unprocessable Entity)

### step 070 — Phase 22 신기능 복합 시나리오 (파일: test_phase23_advanced_risk_e2e.py)

- [ ] E23-06: MDD 거래중단(stop_trading_on_drawdown_pct=0.1) + priority=market_cap_asc 복합 — 드로우다운 10% 초과 시 신규 매수 중단 확인
- [ ] E23-07: delisting_estimated 종목 보유 중 최종 거래일 → 종가×0.5 강제매도 → trade_executions 영속화 확인
- [ ] E23-08: cash_below_threshold 트리거 → 포지션 강제 청산 → cash_events 기록 확인
- [ ] E23-09: priority=volume_ratio_desc 다종목 동시 매수 신호 → 정렬 결정론 검증 (동일 입력 2회 실행 → 동일 순서)
- [ ] E23-10: MDD + cash_below_threshold 동시 발동 시 처리 순서 확인

### step 071 — pykrx 실데이터 smoke test (파일: test_phase23_realdata_smoke.py)

- [ ] E23-11: (@pytest.mark.realdata) pykrx로 삼성전자(005930) 최근 60일 시세 수집 → daily_prices 저장 → PriceLoader 로드 성공
- [ ] E23-12: (@pytest.mark.realdata) 수집된 데이터로 BacktestEngine 실행 (단순 이동평균 전략) → 결과 비어있지 않음 확인
- [ ] E23-13: (@pytest.mark.realdata) pykrx 응답 컬럼 형식 확인 (필수 컬럼: date, open, high, low, close, volume, adj_close)

---

## 진행률 추적 표

| 시나리오 ID | 설명 | 담당 에이전트 | 상태 | step |
|---|---|---|---|---|
| E23-01 | 전략 생성→실행→결과 전 흐름 | test-engineer | 계획 | 069 |
| E23-02 | 거래내역 조회 + CSV export | test-engineer | 계획 | 069 |
| E23-03 | strategy_snapshot 재현성 | test-engineer | 계획 | 069 |
| E23-04 | 취소 e2e | test-engineer | 계획 | 069 |
| E23-05 | 잘못된 JSON 422 에러 | test-engineer | 계획 | 069 |
| E23-06 | MDD+priority 복합 | test-engineer | 계획 | 070 |
| E23-07 | delisting_estimated 강제매도 영속화 | test-engineer | 계획 | 070 |
| E23-08 | cash_below_threshold + cash_events | test-engineer | 계획 | 070 |
| E23-09 | volume_ratio_desc 결정론 | test-engineer | 계획 | 070 |
| E23-10 | MDD+cash_below_threshold 동시 처리순서 | test-engineer | 계획 | 070 |
| E23-11 | pykrx 삼성 60일 수집·저장·로드 | test-engineer | 계획 (realdata) | 071 |
| E23-12 | 실데이터 BacktestEngine 실행 | test-engineer | 계획 (realdata) | 071 |
| E23-13 | pykrx 컬럼 형식 확인 | test-engineer | 계획 (realdata) | 071 |

---

## 완료 기준 (Definition of Done)

### step 069 완료 조건
- [ ] test_phase23_backtest_e2e.py 5개 시나리오 모두 PASS
- [ ] 기존 pytest 1,116 PASS 이상 유지 (회귀 없음)
- [ ] ruff All checks passed

### step 070 완료 조건
- [ ] test_phase23_advanced_risk_e2e.py 5개 시나리오 모두 PASS
- [ ] 기존 pytest PASS 수 유지 (회귀 없음)
- [ ] ruff All checks passed

### step 071 완료 조건
- [ ] test_phase23_realdata_smoke.py 3개 시나리오 @pytest.mark.realdata 마커 적용 확인
- [ ] 기본 pytest 실행 시 realdata 테스트 자동 제외 확인
- [ ] conftest.py에 --realdata 플래그 또는 PYTEST_REALDATA=1 환경변수 활성화 설정 추가

### Phase 23 전체 완료 조건
- [ ] 13개 시나리오 중 10개(E23-01~10) PASS — realdata 3개(E23-11~13)는 분리 실행
- [ ] 전체 pytest PASS 수 ≥ 1,126 (신규 10건 이상 추가)
- [ ] 로드맵.md 체크박스 12-m, 12-n, 12-o 갱신
- [ ] 분모 217 → 220 갱신, 진행률 220/220 = 100%
- [ ] test-engineer ship-go 획득
- [ ] git commit + git push origin main

---

## Execution

### step 069 — test_phase23_backtest_e2e.py

사전 조사:
- `backend/tests/api/conftest.py` — TestClient + tmpdir SQLite fixture 패턴 파악
- `backend/app/api/routes_backtests.py` — 엔드포인트 경로 및 export/{kind} 구조 확인
- `backend/tests/api/test_backtests.py` — 기존 payload 패턴 확인 (synthetic_seed=42, synthetic_n=90)
- `backend/app/backtest/result.py` — `trade_executions`는 dict 리스트, `win_rate`는 0~100% 스케일 확인

구현:
- `test_phase23_backtest_e2e.py` 신규 작성 (5개 시나리오)
- 로컬 fixture (db_engine, client) 인라인으로 선언 — tests/api/conftest.py 패턴 동일
- win_rate 범위 검증: 0.0~100.0 스케일로 수정 (초기 0~1.0으로 작성 후 실행 실패 → 수정)
- ruff --fix 으로 import 정렬 자동 수정

### step 070 — test_phase23_advanced_risk_e2e.py

사전 조사:
- `backend/app/backtest/engine.py` — EVENT_REASON_DRAWDOWN_LIMIT, EVENT_REASON_FORCE_SELL_DELISTED_ESTIMATED, EVENT_TYPE_FORCE_SELL 상수 확인
- `backend/tests/backtest/test_drawdown_limit.py` — MDD 테스트 패턴 확인
- `backend/tests/backtest/test_delisting_estimated.py` — delisting_estimated 패턴 확인
- `backend/app/portfolio/cash_manager.py` — CashManager 생성자 시그니처 확인

구현:
- `test_phase23_advanced_risk_e2e.py` 신규 작성 (5개 시나리오)
- trade_executions가 dict 리스트임을 실행 중 발견 → e.symbol이 아닌 e.get("symbol")로 수정
- 미사용 변수(portfolio, engine) 및 EVENT_TYPE_SKIP import 제거
- ruff --fix 으로 import 정렬 자동 수정

### step 071 — test_phase23_realdata_smoke.py + conftest.py 수정

구현:
- `backend/tests/conftest.py` 수정:
  - `pytest_configure`: realdata 마커 등록
  - `pytest_addoption`: --realdata 플래그 (`contextlib.suppress(ValueError)` 방어)
  - `pytest_collection_modifyitems`: realdata 마커 없으면 자동 skip
- `test_phase23_realdata_smoke.py` 신규 작성 (3개 @pytest.mark.realdata 시나리오)
- `app.data_pipeline.collectors.pykrx.PykrxCollector` 사용, `collect_daily_prices` 메서드

## Tests

### 신규 파일별 PASS 수

| 파일 | PASS | SKIP | FAIL |
|---|---|---|---|
| test_phase23_backtest_e2e.py | 5 | 0 | 0 |
| test_phase23_advanced_risk_e2e.py | 5 | 0 | 0 |
| test_phase23_realdata_smoke.py | 0 | 3 (realdata skip) | 0 |

### 전체 회귀 결과

- 기준선: 1,458 PASS (Phase 22까지)
- 신규: 1,468 PASS + 3 SKIPPED (realdata 자동 skip)
- 증가: +10 PASS (회귀 없음)
- 시간: 약 41초

### ruff 결과

```
All checks passed!
```

초기 오류:
- SIM105: `try/except/pass` → `contextlib.suppress(ValueError)` (conftest.py)
- I001: import 정렬 (2개 파일) → `ruff --fix` 자동 수정
- F401: `EVENT_TYPE_SKIP` 미사용 import 제거
- F841: 미사용 변수 제거 (portfolio, engine in E23-07, _make_engine)

### @pytest.mark.realdata skip 확인 결과

```
tests/integration/test_phase23_realdata_smoke.py::test_pykrx_samsung_60days_ingest SKIPPED
tests/integration/test_phase23_realdata_smoke.py::test_backtest_with_real_data SKIPPED
tests/integration/test_phase23_realdata_smoke.py::test_pykrx_response_columns SKIPPED
3 skipped — 실데이터 테스트 비활성화 (PYTEST_REALDATA=1 또는 --realdata 필요)
```

## Issues

### I1: win_rate 범위 오류 (즉시 해소)

- 증상: `test_full_e2e_flow` - `AssertionError: win_rate 범위 이탈` (37.5 > 1.0)
- 원인: win_rate API 응답이 0~100% 스케일이므로 0~1.0 검증 부적절
- 해소: `assert 0.0 <= s.get("win_rate", 0.0) <= 100.0`으로 수정

### I2: trade_executions dict 접근 오류 (즉시 해소)

- 증상: `test_mdd_stop_trading_with_market_cap_asc` - `AttributeError: 'dict' object has no attribute 'symbol'`
- 원인: `result.trade_executions`는 dict 리스트 (속성 접근 불가)
- 해소: `e.symbol` → `e.get("symbol")`로 수정

## Result

신규 통합 테스트 3개 파일 작성 완료.

| 지표 | 결과 |
|---|---|
| pytest 전체 | 1,468 PASS + 3 SKIPPED |
| 기준선 대비 | +10 PASS (기준선 1,458) |
| ruff | All checks passed |
| realdata skip | 3건 자동 skip 확인 |

### 13.17 acceptance 매핑

| 13.17 항목 | 영향 | 검증 파일 | 결과 |
|---|---|---|---|
| 13.17.1 일중 stop/take | n/a (기존 파일이 검증) | — | n/a |
| 13.4.5 delisting_estimated 강제매도 | E23-07 | test_phase23_advanced_risk_e2e.py | PASS |
| 13.8 priority 알고리즘 | E23-06 / E23-09 | test_phase23_advanced_risk_e2e.py | PASS |
| 13.12 결정론 | E23-03 / E23-09 / E23-10 | test_phase23_backtest_e2e.py + advanced_risk | PASS |
| CLAUDE.md #9 snapshot 재현성 | E23-03 | test_phase23_backtest_e2e.py | PASS |
| 02-r MDD 거래중단 | E23-06 / E23-10 | test_phase23_advanced_risk_e2e.py | PASS |
| 02-t cash_below_threshold | E23-08 / E23-10 | test_phase23_advanced_risk_e2e.py | PASS |

## Follow-ups

(완료 후 작성)

## 메인 세션 마무리 체크

- [x] status를 completed로 변경
- [x] 작업로그/README.md "최근 작업" 표에 3행 추가 (069/070/071)
- [x] Phase 23을 Phase 표에 추가 (완료 행)
- [x] PM 에이전트 호출 → "step 069/070/071 마무리" → 로드맵.md 갱신
- [x] git commit (신규 통합 테스트 파일 3개)
- [x] git push origin main (Phase 23 마지막 step)
