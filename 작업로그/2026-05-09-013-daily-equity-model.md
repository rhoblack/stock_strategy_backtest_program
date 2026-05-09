---
date: 2026-05-09
agent: main
phase: 2
status: completed
related_docs:
  - 상세설계/07_database_design.md
  - 상세설계/04_backtest_engine_design.md
---

# Phase 2 / Step 4 — daily_equity 모델

## Plan

설계서 07번 9절. Phase 1의 DailyEquity dataclass를 영속화. (run_id, date) 복합 인덱스로 시계열 조회 최적화.

### 컬럼

- id, run_id FK
- date
- cash, stock_value, total_equity
- daily_return (%, 전일 대비)
- cumulative_return (%, 초기 자본 대비)
- drawdown (%)
- positions_count
- created_at

### 작업

- [ ] `app/models/daily_equity.py`
- [ ] `app/models/__init__.py` 등록
- [ ] `tests/db/test_models_daily_equity.py`

## Execution

```text
backend/app/models/daily_equity.py     DailyEquity (UniqueConstraint(run_id, date), 복합 인덱스)
backend/app/models/__init__.py         등록
backend/tests/db/test_models_daily_equity.py  5건
```

설계 결정:
- **(run_id, date) UniqueConstraint**: 한 run의 같은 날짜 중복 방지.
- **복합 인덱스**: 한 백테스트의 시계열 조회 성능.
- **컬럼**: cash/stock_value/total_equity + daily_return/cumulative_return/drawdown + positions_count.

## Tests

```text
============== 248 passed in 1.69s ==============
ruff: All checks passed
```

신규 5건: 생성/unique constraint/다중 날짜/cascade/repr.

## Result

- 추가/수정 파일: 3개
- pytest 248/248, ruff All checks passed
- DailyEquity dataclass ↔ DailyEquity 모델 매핑 준비 완료 (services 레이어에서 변환)

## Follow-ups

- **Step 5 (다음)**: services 레이어 — strategy_service / backtest_service. BacktestEngine 결과 → DB 저장 매퍼 포함.
- daily_return / cumulative_return은 BacktestEngine에서 현재 계산하지 않음. services 레이어가 daily_equity 저장 시 계산해서 채움 (또는 BacktestEngine에 추가).

## 메인 세션 마무리 체크

- [x] status를 completed
- [x] 작업로그/README.md 갱신
