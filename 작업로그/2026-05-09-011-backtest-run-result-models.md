---
date: 2026-05-09
agent: main
phase: 2
status: completed
related_docs:
  - 상세설계/07_database_design.md
  - 상세설계/13_backtest_accuracy_policy_design.md
---

# Phase 2 / Step 2 — backtest_runs + backtest_results 모델

## Plan

설계서 07번 7~8절. 정확성 정책 스냅샷 필수 컬럼들을 모두 포함 (재현성 보장).

### backtest_runs 컬럼

- id, user_id FK, strategy_id FK
- strategy_snapshot_json (필수, 02번 schema)
- run_name, universe_config_json
- start_date, end_date
- initial_cash, fee_rate, tax_rate_json (시계열), slippage
- execution_price_type, use_adjusted_price, tick_rounding
- priority_method, priority_tie_breaker, random_seed (정확성 정책 13.8/13.12)
- status (enum: pending/running/completed/failed/cancelled)
- progress_pct, error_message
- created_at, started_at, finished_at

### backtest_results 컬럼

- id, run_id FK (unique 1:1)
- total_return, annual_return, final_equity
- mdd, win_rate, trade_count, open_position_count
- avg_holding_days, avg_profit_rate, avg_loss_rate, profit_factor
- created_at

### 작업

- [ ] `app/models/enums.py`: `BacktestStatus` enum
- [ ] `app/models/backtest.py`: BacktestRun, BacktestResult
- [ ] `app/models/__init__.py` import 등록
- [ ] `tests/db/test_models_backtest_run.py`
- [ ] `tests/db/test_models_backtest_result.py`

## Execution

```text
backend/app/models/enums.py              BacktestStatus + TradeExecutionType (StrEnum)
backend/app/models/backtest.py           BacktestRun + BacktestResult (~140줄)
backend/app/models/__init__.py           등록 추가
backend/tests/db/test_models_backtest.py 9건
```

설계 결정:
- **정확성 정책 스냅샷 컬럼 모두 포함**: tax_rate_json (시계열), priority_method, priority_tie_breaker, random_seed, tick_rounding, use_adjusted_price. 재현성 보장.
- **status는 SAEnum(native_enum=False)**: SQLite 호환을 위해 String으로 저장. PostgreSQL로 가도 동작.
- **strategy_id ON DELETE RESTRICT**: 백테스트 결과가 있는 전략 물리 삭제 차단. soft delete 사용 권장.
- **BacktestResult.run_id unique**: 1:1 관계 명시.
- **TimestampMixin은 BacktestResult만 사용**. BacktestRun은 created_at/started_at/finished_at을 직접 컨트롤 (서비스 레이어가 시점별로 채움).

## Tests

```text
============== 236 passed in 1.30s ==============
ruff: All checks passed
```

신규 9건:
- 생성/JSON round-trip/status 전이/relationship/result 1:1/unique/cascade/RESTRICT 메타/repr

## Issues

- ruff UP042: `class X(str, Enum)` → `StrEnum` 사용으로 변경.

## Result

- 추가/수정 파일: 4개
- 정확성 정책 13.6/13.8/13.12 모든 스냅샷 컬럼 영속화 가능
- pytest 236/236, ruff All checks passed

## Follow-ups

- **Step 3 (다음)**: trade_groups + trade_executions (07번 9~10절)
- 서비스 레이어 (Step 5)에서 BacktestEngine 결과를 BacktestRun + BacktestResult로 매핑

## 메인 세션 마무리 체크

- [x] status를 completed
- [x] 작업로그/README.md 갱신
