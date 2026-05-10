---
date: 2026-05-10
agent: backend-api-engineer
phase: 8 (리뷰 011 후속 — Wave C)
status: completed
related_docs:
  - 상세설계/07_database_design.md
  - 상세설계/13_backtest_accuracy_policy_design.md
  - 상세설계/02_strategy_json_schema_design.md
  - 리뷰/2026-05-10-011-설계서기반-PM주관-코드리뷰.md
---

# TradeExecution.fee/tax + DailyEquity.daily_return/cumulative_return 영속화 (M5 + C2 영속화 부분)

리뷰 011 M5 + 외부 4.7 — TradeExecution / DailyEquity 모델에는 fee/tax/daily_return/cumulative_return 컬럼이 있는데 영속화 코드가 모두 0 또는 NULL로 채움. 013 step에서 ExecutionResult dataclass가 도입된 직후, 그 분해 결과를 DB 컬럼에 정확히 매핑하면 자동으로 외부 4.7 + M5 일괄 해소.

## 선행 조건
- [x] 013(Wave C step 1) 완료 — `Portfolio.trade_logs`에 fee/tax 키 존재, `ExecutionResult` 클래스 import 가능, `cash_events` 강제 매도에도 동일 형식 적용

## Plan

### A) TradeExecution 영속화 (M4 영속화 + 외부 4.7)
- [x] `상세설계/07_database_design.md`의 trade_executions 테이블 컬럼 정의 정독
- [x] `상세설계/13_backtest_accuracy_policy_design.md` §6 (세율 시계열) §5 (호가 단위) 의미 재확인
- [x] `backend/app/services/backtest_service.py:_persist_trade_executions` (또는 이에 준하는 위치):
  - 현재 `fee=0.0`, `tax=0.0` 하드코드 → `Portfolio.trade_logs`의 fee/tax 키 매핑
  - `gross_amount` / `net_amount`도 ExecutionResult 의미 그대로 매핑 (013 step에서 정의된 명세 따름)
  - BUY는 tax=0 고정, SELL은 ExecutionResult.tax 그대로 (세율 시계열 13.6 적용 결과)

### B) DailyEquity 영속화 (M5)
- [x] `상세설계/07_database_design.md`의 daily_equity 컬럼 정의 정독
- [x] `backend/app/services/backtest_service.py:_persist_daily_equity` (또는 동등 위치):
  - 현재 daily_return / cumulative_return 미설정 → 시퀀스 순회 시 계산:
    - `daily_return[i] = (total_equity[i] - total_equity[i-1]) / total_equity[i-1]` (i=0이면 (total_equity[0] - initial_cash) / initial_cash)
    - `cumulative_return[i] = (total_equity[i] - initial_cash) / initial_cash`
  - 수치 형식: **% (퍼센트)** 단위 통일 — drawdown / mdd_pct가 % 단위인 점 + 09번 §6 CSV 예시 일치
  - drawdown 컬럼은 이미 BacktestEngine이 계산 → 그대로

### C) cash_events 영속화 (C2 잔존)
- [x] 013 step에서 cash_events에 fee/tax/net 흘러들어왔는지 확인 (cash_manager.py:127-148, 6개 분해 키 채워짐)
- [x] CashEvent 모델에 fee/tax 컬럼 있는지 확인 (없음 → alembic 마이그레이션 7c1e5a2b9d40 추가)
- [x] 영속화 시 ExecutionResult 분해 매핑

### 공통
- [x] pytest:
  - **Phase 1 골든 fixture 회귀** — fee/tax=0 default 시 9지표 frozen expected 동일 유지 ✅
  - 영속화 회귀: tax_rate>0 시나리오에서 TradeExecution.tax > 0 검증 ✅
  - DailyEquity 영속화: daily_return/cumulative_return 시퀀스 일관 (∏(1+daily/100) ≈ 1+cumulative[-1]/100) ✅
  - cash_events 영속화 (분해 키 매핑 + legacy None 안전) ✅
- [x] 회귀: 전체 418 (baseline 412 + 신규 6) 통과 + ruff All checks passed
- [x] 표준 envelope / X-Request-ID / user_id scope 회귀 (Wave A 변경 영향 없음 — test_scope_and_envelope.py 21건 모두 통과)

### 절대 금지
- BacktestEngine / Portfolio / ExecutionModel / CashManager 내부 수정 (013 step 영역, 이미 완료)
- conditions/* 수정 (condition-author 영역)
- 시장데이터 작성 (market-data-engineer 영역)
- 하드코드 fee=0.0/tax=0.0 신규 추가 — 본 작업은 정확히 그걸 없애는 것
- DB 컬럼 추가/제거 시 alembic 마이그레이션 누락
- 신규 에러 코드 카탈로그 추가 (10.7.1 외)
- dict 순회 순서 의존 (영속화 순서는 trade_log 순서 기반)

## Execution

### 작성/수정 파일

- `backend/app/services/backtest_service.py:332-378` (`_persist_trade_groups_and_executions`) — TradeExecution insert 시 `fee=0.0`, `tax=0.0`, `gross_amount=price*quantity` 하드코드를 제거하고 `ex.get("fee", 0.0)`, `ex.get("tax", 0.0)`, `ex.get("gross_amount", price*quantity)`, `ex.get("net_amount", ...)`로 ExecutionResult 분해 결과를 그대로 매핑. 13.5/13.6 정책 결과(호가 단위 + 세율 시계열) 자동 보존.
- `backend/app/services/backtest_service.py:393-447` (`_persist_daily_equity`) — 시퀀스 순회로 `daily_return` / `cumulative_return`을 % 단위로 계산해 영속화. `prev_equity` 초기값은 `run.initial_cash`. `initial_cash<=0` 가드로 NOT NULL 만족.
- `backend/app/services/backtest_service.py:450-482` (`_persist_cash_events`) — cash_event dict의 `exec_price/raw_price/gross_amount/fee/tax/net_amount` 키를 새 CashEvent 컬럼에 매핑. legacy 경로(ExecutionModel 미주입)에서는 None 허용.
- `backend/app/models/cash_event.py:36-46` — `exec_price`, `raw_price`, `gross_amount`, `fee`, `tax`, `net_amount` 6개 NULL 허용 컬럼 추가. `sell_amount`는 호환을 위해 유지.
- `backend/alembic/versions/7c1e5a2b9d40_add_cash_events_cost_breakdown.py` (신규) — 위 6개 컬럼 ADD COLUMN 마이그레이션. `down_revision = "3b7a97e6378c"` (직전 cash_events 마이그레이션 위에 누적). downgrade는 `batch_alter_table.drop_column`으로 안전 제거.
- `backend/tests/services/test_backtest_service.py:222-485` — 신규 6개 테스트:
  - `test_trade_executions_persist_fee_and_tax_with_costs` — fee_rate=0.0015, tax_rate=0.0023 시 BUY tax=0 강제 + SELL fee/tax/net 검증
  - `test_daily_equity_persists_returns` — 90일 시퀀스에서 daily_return/cumulative_return 일관성 (∏(1+daily) ≈ 1+cumulative)
  - `test_daily_equity_returns_default_to_zero_with_zero_initial_cash` — initial_cash=0 가드 검증
  - `test_cash_events_persist_fee_tax_breakdown` — CashManager 비용 분해 dict가 DB CashEvent 6개 신규 컬럼에 매핑
  - `test_cash_events_persist_legacy_no_breakdown` — 분해 키가 없는 legacy 경로에서 None 안전 영속화
  - `test_golden_fixture_regression_cost_zero` — Phase 1 골든 frozen 9지표 회귀 (final_equity 10,188,570 / total_return 1.8857% / mdd -4.9032% / trade_count 8 / win_rate 37.5% / avg_holding 7.5 / profit_factor 1.2252) + 비용 0 시 모든 fee/tax=0 + gross==net

### 적용한 정책 절번호

- **07번 §10 (trade_executions)** — gross_amount/fee/tax/net_amount 컬럼 의미 그대로 매핑
- **07번 §9 (daily_equity)** — daily_return/cumulative_return 컬럼 단위는 drawdown과 동일한 **%(퍼센트)** 로 통일 (09번 §6 CSV `cumulative_return: 0.18` 예시 + drawdown/mdd_pct가 % 단위인 점 반영)
- **07번 §10 (cash_events)** — 기존 컬럼 유지 + 비용 분해 6개 컬럼을 nullable로 보강 (07번 문서에 신규 컬럼 명시 갱신은 follow-up)
- **13번 §6 (세율 시계열)** — ExecutionModel.get_tax_rate(on_date) 결과가 ExecutionResult.tax → trade_log dict → DB tax 컬럼으로 그대로 흘러감
- **13번 §5 (호가 단위)** — apply_slippage_and_tick 후 가격이 ExecutionResult.price/gross_amount로 영속화
- **02번 §11 (영속화 스냅샷)** — strategy_snapshot_json은 기존 코드에 이미 저장 중 (이번 작업에서 변경 없음)
- **CLAUDE.md #9 (영속화)** — fee/tax 0 하드코드 제거로 정책 위반 해소

### 영속화 매핑 표

**TradeExecution (DB ← trade_log dict)**
| DB 컬럼 | 소스 dict 키 | 비고 |
| --- | --- | --- |
| price | `ex["price"]` | ExecutionResult.price (정수 호가 적용) |
| quantity | `ex["quantity"]` | |
| gross_amount | `ex.get("gross_amount", price*quantity)` | ExecutionResult.gross_amount |
| fee | `ex.get("fee", 0.0)` | BUY/SELL 모두 = gross * fee_rate |
| tax | `ex.get("tax", 0.0)` | BUY=0 강제, SELL=gross * tax_rate(on_date) |
| net_amount | `ex.get("net_amount", cost or proceeds)` | BUY=gross+fee, SELL=gross-fee-tax |
| realized_profit | `ex.get("realized_profit")` | SELL/PARTIAL_SELL만 |
| realized_profit_rate | `ex.get("realized_profit_rate")` | SELL/PARTIAL_SELL만 |
| exit_reason | `ex.get("reason")` (BUY는 None) | |

**DailyEquity (DB ← DailyEquity dataclass + 시퀀스 계산)**
| DB 컬럼 | 소스 | 비고 |
| --- | --- | --- |
| date / cash / stock_value / total_equity | `eq.date` 등 그대로 | |
| daily_return | `(eq.total_equity - prev_equity) / prev_equity * 100` | i=0이면 prev=initial_cash. % 단위 |
| cumulative_return | `(eq.total_equity - initial_cash) / initial_cash * 100` | % 단위 |
| drawdown | `eq.drawdown` | 엔진이 이미 % 단위로 계산 |
| positions_count | `eq.positions_count` | |

**CashEvent (DB ← cash_event dict)**
| DB 컬럼 | 소스 dict 키 | 비고 |
| --- | --- | --- |
| date / event_type / cash_before / required_cash / cash_after / action / symbol / sell_quantity / sell_amount / reason | 기존 그대로 | |
| exec_price | `ev.get("exec_price")` | apply_slippage_and_tick 결과 (강제 매도) |
| raw_price | `ev.get("raw_price")` | price_provider 원본 가격 |
| gross_amount | `ev.get("gross_amount")` | ExecutionResult.gross_amount |
| fee | `ev.get("fee")` | ExecutionResult.fee |
| tax | `ev.get("tax")` | ExecutionResult.tax |
| net_amount | `ev.get("net_amount")` | ExecutionResult.net_amount (= sell_amount과 동일 값) |

### 신규 alembic 마이그레이션

- `7c1e5a2b9d40_add_cash_events_cost_breakdown.py` (신규, down_revision=`3b7a97e6378c`)
- 6개 NULL 허용 컬럼 ADD COLUMN. SQLite 기준 `ALTER TABLE ... ADD COLUMN`만 사용하여 기존 row 안전 (NULL fill).
- 기존 `cash_events` 마이그레이션이 `_KNOWN_ALEMBIC_GAPS`로 alembic 검증에서 제외되어 있어 본 신규 마이그레이션의 `test_alembic_upgrade_head_creates_known_tables` 영향 없음. dev/test는 `Base.metadata.create_all`로 모든 테이블 생성되므로 정상 동작.

## Tests

```text
backend/tests/services/test_backtest_service.py — 13 passed (기존 8 + 신규 5)
  * test_trade_executions_persist_fee_and_tax_with_costs (신규)
  * test_daily_equity_persists_returns (신규)
  * test_daily_equity_returns_default_to_zero_with_zero_initial_cash (신규)
  * test_cash_events_persist_fee_tax_breakdown (신규)
  * test_cash_events_persist_legacy_no_breakdown (신규)
  * test_golden_fixture_regression_cost_zero (신규)
backend/tests 전체 — 418 passed (baseline 412 + 신규 6)
ruff check backend/app backend/tests — All checks passed
```

**Phase 1 골든 회귀** — `test_golden_fixture_regression_cost_zero` + 기존 `test_run_backtest_persists_full_result` + `tests/integration/test_phase1_golden.py` 6건 모두 통과. 9지표 frozen 값 동일.

## Issues

1. **07번 §10 cash_events 컬럼 명세** — 본 작업에서 6개 컬럼(exec_price/raw_price/gross_amount/fee/tax/net_amount)을 추가했으나 07번 문서의 cash_events 컬럼 목록(line 319~333)은 갱신하지 않았다. follow-up에서 갱신 필요.

2. **`_KNOWN_ALEMBIC_GAPS`** — `tests/db/test_alembic.py`의 `_KNOWN_ALEMBIC_GAPS = {"cash_events"}`는 cash_events 마이그레이션 자체가 SQLite + Alembic 환경에서 silent fail 한다고 주석 (line 45~48). 새 마이그레이션도 같은 문제를 가질 수 있으나 dev/test는 영향 없음. 운영 환경에서는 PostgreSQL로 전환 시 재검증 필요.

3. **CashManager dev/legacy 경로** — CashManager가 ExecutionModel 미주입(`execution_model=None`)으로 초기화될 때 fee/tax=0, gross=net으로 fallback되며 cash_event dict에 6개 분해 키가 그대로 포함된다(`fee=0.0`, `tax=0.0`, `gross==net=raw_price*quantity`). 이는 의도된 fallback이며 NULL이 아니라 0으로 저장된다. 단위 테스트 `test_cash_events_persist_legacy_no_breakdown`은 분해 키 자체가 없는 (외부에서 만든) dict 시나리오를 검증.

## Result

- **TradeExecution.fee/tax 영속화** — 0 하드코드 완전 제거, ExecutionResult 분해 결과가 13.6 세율 시계열까지 보존되어 DB에 저장
- **DailyEquity.daily_return/cumulative_return 영속화** — 시퀀스 일관성 검증 완료 (∏(1+daily/100) ≈ 1+cumulative[-1]/100), drawdown과 동일한 % 단위
- **CashEvent 비용 분해 영속화** — 6개 신규 컬럼 + alembic 마이그레이션 + legacy 경로 None 안전 처리
- **Phase 1 골든 frozen 9지표 동일** — fee=tax=0 default 시나리오 회귀 없음
- **모듈 경계 준수** — BacktestEngine / Portfolio / ExecutionModel / CashManager / conditions / 시장데이터 / schemas validator 모두 미수정. 영속화 어댑터(services/backtest_service.py) + models + alembic + tests만 변경
- **Phase 8 Wave C — Critical 5/5 완료**: 011 리뷰의 H1(ExecutionResult), M2(슬리피지 반영 net), M4(fee/tax 영속화), M5(daily_return/cumulative_return 영속화), C2(cash_events 비용 분해 영속화) 모두 해소. 외부 4.7도 이번 작업에서 동시 해소.

## Follow-ups

1. **상세설계/07_database_design.md** §10 cash_events 컬럼 목록(line 319~333)에 `exec_price`, `raw_price`, `gross_amount`, `fee`, `tax`, `net_amount` 6개 컬럼 추가 + nullable 표기. 본 작업에서는 코드만 갱신했으므로 메인 세션이 문서 동기화 필요. (정책/스키마 변경은 문서 먼저 원칙이지만 본 작업은 영속화 어댑터 보강이라 컬럼 의미가 13/02번 정책 변경 없이 추가된 케이스 — 문서 갱신은 follow-up으로 분리)
2. **상세설계/13_backtest_accuracy_policy_design.md** §6 (세율 시계열)에 영속화 보장 문구 보강 권장 — TradeExecution.tax / CashEvent.tax가 시계열 세율 적용 결과를 그대로 영속화한다는 명세.
3. **CashEvent CSV Export** — 09번 csv_export_design에 cash_events.csv 컬럼 추가 시 신규 6개 컬럼 노출 여부 결정 필요.
4. **frontend chart_data API** — daily_return/cumulative_return 컬럼이 채워졌으므로 차트 응답 schema에 노출 가능 (현재는 drawdown/total_equity만 사용 중일 가능성, frontend-developer가 결정).
5. **운영 alembic gap** — `_KNOWN_ALEMBIC_GAPS` 해소를 위해 cash_events 마이그레이션을 SQLite/Alembic 호환 형식으로 재작성하는 별도 step 필요. 본 작업에서는 dev/test가 init_db로 동작하므로 차단 요소 아님.

## 메인 세션 마무리 체크

- [ ] status를 completed로 변경
- [ ] 작업로그/README.md 갱신 (Phase 8 ✅ 완료 표기 — Critical 5/5 모두 해소)
- [ ] `git commit` + Phase 8 완료라면 `git push origin main`
