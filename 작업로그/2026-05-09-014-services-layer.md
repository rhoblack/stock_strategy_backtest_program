---
date: 2026-05-09
agent: main
phase: 2
status: completed
related_docs:
  - 상세설계/04_backtest_engine_design.md
  - 상세설계/07_database_design.md
  - 상세설계/02_strategy_json_schema_design.md
---

# Phase 2 / Step 5 — services 레이어 (strategy_service + backtest_service)

## Plan

Phase 1 (BacktestEngine) ↔ Phase 2 (DB 모델)을 잇는 통합 레이어.

### strategy_service

- `create_strategy(session, user_id, name, strategy_json, ...)` → Strategy + 첫 StrategyVersion(version=1)
- `update_strategy(session, strategy_id, strategy_json, change_note=...)` → 자동 StrategyVersion(version=max+1) 추가
- `duplicate_strategy(session, strategy_id, new_name)` → deep copy
- `soft_delete_strategy(session, strategy_id)` → deleted_at 설정
- `list_strategies(session, user_id, include_deleted=False)`
- `get_strategy(session, strategy_id, *, allow_deleted=False)` → 없으면 StrategyNotFoundError

### backtest_service

- `create_backtest_run(session, user_id, strategy_id, *, run_name, universe_config, start_date, end_date, initial_cash, fee_rate, tax_rate, slippage, ...)` → BacktestRun (status=PENDING, snapshot 저장)
- `run_backtest(session, run_id, df)` → BacktestResult
  - 엔진 조립 (StrategyEngine + ExecutionModel + Portfolio + BacktestEngine)
  - status RUNNING + started_at
  - run() → result + metrics
  - persist (BacktestResult + trade_groups + trade_executions + daily_equity)
  - status COMPLETED + finished_at
  - 예외 시 status FAILED + error_message
- `get_backtest_summary(session, run_id) -> dict`

### 매핑 헬퍼 (backtest_service 내부)

- `_persist_summary(session, run, metrics)`
- `_persist_trade_groups_and_executions(session, run, trade_logs)`
  - trade_logs를 trade_group_id로 그룹화
  - in-memory tg_id → DB pk 매핑 dict 사용
  - BUY 메타에서 entry_date/price/quantity 추출
  - 청산 여부 판단 (sells.quantity 합 == buy.quantity)
- `_persist_daily_equity(session, run, daily_equities)`

### 작업

- [ ] `app/services/__init__.py`
- [ ] `app/services/strategy_service.py`
- [ ] `app/services/backtest_service.py`
- [ ] `tests/services/__init__.py`, `tests/services/conftest.py` (db_session 재사용)
- [ ] `tests/services/test_strategy_service.py`
- [ ] `tests/services/test_backtest_service.py` (end-to-end 시나리오 1~2개)

## Execution

```text
backend/app/services/__init__.py             strategy_service / backtest_service 노출
backend/app/services/strategy_service.py     CRUD + 자동 버전 관리 (~150줄)
  - create_strategy: 첫 StrategyVersion(version=1) 자동 추가
  - update_strategy: strategy_json 변경 감지 → max+1 버전 자동 추가
  - duplicate_strategy: deep copy + version=1 초기화
  - soft_delete_strategy: deleted_at 설정
  - list_strategies: deleted_at IS NULL 필터, updated_at desc 정렬
  - get_strategy: StrategyNotFoundError on missing
  - list_strategy_versions: version asc

backend/app/services/backtest_service.py     실행 + 영속화 (~250줄)
  - create_backtest_run: snapshot 저장 (strategy_json + 정확성 정책)
  - run_backtest(run_id, df): 엔진 조립 → run() → metrics → 영속화
    - 상태 전이 PENDING → RUNNING → COMPLETED/FAILED
    - 예외 시 error_message 저장 후 재발생
  - get_backtest_summary: dict 반환
  - 내부 헬퍼:
    - _persist_summary: BacktestResult insert (math.inf → None 처리)
    - _persist_trade_groups_and_executions: in-memory tg_id → DB pk 매핑
    - _persist_daily_equity: DailyEquity dataclass list → DB 행

backend/tests/services/conftest.py           db_engine + db_session + user + sample_strategy_json
backend/tests/services/test_strategy_service.py  8건
backend/tests/services/test_backtest_service.py  7건 (end-to-end 영속화 + 실패 시나리오)
```

설계 결정:
- **JSON 변경 시 자동 버전 추가**: name/description/tags만 바뀌면 버전 추가 안 함 (불필요한 노이즈 회피).
- **deep copy로 strategy_snapshot 저장**: 원본 전략 수정해도 백테스트 run의 snapshot은 불변.
- **`run_backtest` 동기 실행**: MVP. 비동기 큐는 Phase 4 API 단계 (10번 문서 4.1).
- **예외 처리**: 엔진 예외 발생 시 status=FAILED + error_message에 traceback 저장 (4000자 제한). 그 후 재발생 — 호출자가 재시도/알림 결정.
- **profit_factor inf → None**: DB Float에 inf 저장 회피.
- **trade_group_id 매핑**: in-memory ID와 DB PK가 다르므로 BUY 먼저 flush() → PK 발급 → executions에 매핑 dict로 연결.

## Tests

```text
============== 263 passed in 2.06s ==============
ruff: All checks passed
```

신규 15건:
- strategy_service (8): 생성+첫 버전, JSON 변경 시 버전 추가, 메타만 변경 시 버전 안 추가, 복제, soft delete, 정렬, not found, 버전 목록
- backtest_service (7): snapshot 저장, end-to-end 영속화 (Phase 1 골든 결과와 일치 확인), 예외 시 FAILED, 요약 조회, 미존재 run, 두 run 독립

회귀: 기존 248건 모두 통과.

## Issues

- ruff B017: blanket Exception → KeyError로 좁힘.
- next_volume이 NaN인 행(마지막 봉)에 대해 _maybe_buy가 row.get("next_volume") 사용 → 타입 처리 OK.

## Result

- 추가/수정 파일: 7개
- Phase 1 BacktestEngine + Phase 2 모델이 처음으로 실제 통합 동작 (end-to-end 영속화 검증)
- Golden 시나리오의 frozen 결과 (trade_count=8, win_rate=37.5%, final_equity=10,188,570)가 DB 영속화 후에도 동일
- pytest 263/263, ruff All checks passed

## Follow-ups

- **Step 6 (다음, Phase 2 마지막)**: Alembic 도입 + 첫 마이그레이션 (baseline). `init_db` (create_all) → alembic upgrade head로 전환.
- **TradeExecution.fee/tax 분해**: 현재는 0으로 저장. ExecutionModel에서 fee/tax/gross/net를 분해해서 반환하도록 보강하면 분리 가능. 정확성 정책에는 영향 없음 (총비용은 동일).
- **CashEvent 모델**: Phase 6 CashManager 시 추가.
- **TradeGroup 메모리 모델 ID 일관성**: Phase 1의 portfolio가 부여한 1, 2, 3... ID는 단일 백테스트 안에서만 의미. 영속화 후에는 DB PK로 대체. trade_group_id의 의미 차이를 services 레이어가 추상화.
- **Strategy soft delete 헬퍼 (쿼리 자동 필터)**: 현재는 호출자가 명시적으로 deleted_at 필터. SQLAlchemy event listener나 BaseQuery 패턴 검토.
- **schema validator** (별도 작업): pydantic으로 strategy_json validate. 현재는 free-form dict.

## 메인 세션 마무리 체크

- [x] status를 completed
- [x] 작업로그/README.md 갱신
