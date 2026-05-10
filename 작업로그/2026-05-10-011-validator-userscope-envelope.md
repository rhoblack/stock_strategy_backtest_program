---
date: 2026-05-10
agent: backend-api-engineer
phase: 8 (리뷰 011 후속)
status: completed
related_docs:
  - 상세설계/10_api_design.md
  - 상세설계/02_strategy_json_schema_design.md
  - 상세설계/03_condition_registry_engine_design.md
  - 상세설계/13_backtest_accuracy_policy_design.md
  - 리뷰/2026-05-10-011-설계서기반-PM주관-코드리뷰.md
---

# strategy_json validator (C4) + user_id scope 강제 (C3) + 표준 error envelope (H7)

리뷰 011의 Critical 3건을 한 에이전트가 한 번에 처리. 셋 다 backend-api-engineer 단일 책임 영역(api/ + schemas/ + middleware/) 안이고, 모두 routes_strategies.py에 손이 가야 해서 분리 시 충돌 위험이 큼.

## Plan

### A) strategy_json validator (C4 — 02번 5절, 03번 4절, 10번 7.1절)
- [ ] `상세설계/02_strategy_json_schema_design.md` 전체 정독 (3절 최상위, 4절 logic, 5절 섹션 라우팅, 6절 filters default, 11절 execution, 12절 metadata)
- [ ] `상세설계/03_condition_registry_engine_design.md` 4절 (requires_position 라우팅) 정독
- [ ] `상세설계/10_api_design.md` 7.1 에러 카탈로그 (`UNKNOWN_CONDITION_TYPE` / `EXIT_POSITION_IN_EXIT_SIGNAL` / `INVALID_STRATEGY_JSON` 등) 정독
- [ ] `backend/app/schemas/strategy_json.py` 신규 — 검증 함수 `validate_strategy_json(payload, registry)`:
  - 등록 type만 허용 (미등록 → `UNKNOWN_CONDITION_TYPE`)
  - `requires_position=True` 조건이 entry/exit_signal/filters → `EXIT_POSITION_IN_EXIT_SIGNAL`
  - `requires_position=False` 조건이 exit_position → 동일 패턴으로 거부
  - AND/OR/GROUP, logic 형식 검증
  - position_sizing / cash_management / risk_management / execution / priority / metadata 섹션 schema 검증
- [ ] `backend/app/api/routes_strategies.py`의 create / update에서 검증 호출 → 실패 시 4xx + 표준 envelope
- [ ] `backend/app/api/routes_backtests.py`의 백테스트 생성 전에도 동일 호출

### B) user_id scope 강제 (C3 — 10번 9절)
- [ ] `routes_strategies.py`의 `get_strategy` / `update_strategy` / `delete_strategy` / `duplicate_strategy` 4개 모두 `user_id = Depends(get_current_user_id)` 주입
- [ ] service 레이어에서 `Strategy.user_id == user_id` 강제 — 미일치 시 404 (정보 누설 방지) 또는 403 — 10번 9절 따름
- [ ] duplicate는 `src.user_id == 호출자 user_id` 검증을 명시적으로 (그렇지 않으면 권한 escalation)
- [ ] backtest 관련 엔드포인트에도 동일한 scope 매트릭스 점검

### C) 표준 error envelope + X-Request-ID (H7 — 10번 7·8절)
- [ ] `backend/app/api/errors.py`에 AppError → `{ "error": { "code", "message", "details" } }` 변환하는 FastAPI exception_handler 등록
- [ ] 기존 `HTTPException(detail=exc.to_dict()["error"])` 패턴 모두 AppError raise로 교체
- [ ] `backend/app/api/middleware.py`에 X-Request-ID middleware (incoming 보존 또는 신규 발급, 응답 헤더 + 로그 컨텍스트)

### 공통
- [ ] pytest:
  - validator 음성 테스트 (UNKNOWN_CONDITION_TYPE / EXIT_POSITION_IN_EXIT_SIGNAL / INVALID_STRATEGY_JSON 각각 4xx + 정확한 코드)
  - scope 위반 테스트 (user A가 user B의 strategy 조회/수정/삭제/duplicate 시도 → 4xx)
  - envelope 통일 테스트 (모든 에러 응답이 `{"error": {...}}` 형식, X-Request-ID 헤더 존재)
- [ ] 기존 pytest 회귀 (300건 이상 유지) + ruff
- [ ] **절대 금지**: BacktestEngine / Portfolio 내부 로직 수정, 시장데이터 테이블 작성, fee/tax=0 하드코드 영속화, 동기 백테스트 호출 추가

## Execution

### A) StrategyJsonValidator (C4)

```text
backend/app/schemas/strategy_json.py:1                신규 — validate_strategy_json + 섹션별 검증 함수
backend/app/schemas/strategy.py:14-50                 StrategyCreate/StrategyUpdate에 model_validator 부착
backend/app/services/backtest_service.py:65-82        백테스트 큐 진입 전 strategy.strategy_json 재검증
```

핵심 동작:
- `validate_strategy_json(payload)`이 dict 타입 / entry 필수 / exit_signal 또는 exit_position 최소 1개 / logic 화이트리스트 / GROUP 1단계 중첩 / condition.type registry 등록 여부 / requires_position 라우팅 / operator 화이트리스트 / position_sizing.method+amount+max_positions / execution.fee_rate/slippage/tick_rounding/tax_rate(시계열 from 오름차순) / priority.method+tie_breaker 모두 검사.
- 실패 시 AppError 하위(`InvalidStrategyJsonError` / `UnknownConditionTypeError` / `ExitPositionInExitSignalError` / `ExitSignalInExitPositionError` / `InvalidOperatorError` / `MissingRequiredParameterError` / `InvalidParameterValueError`) raise.
- 결정론: registry 화이트리스트는 sorted 출력, 호출 순서/내부 dict 순회에 무관.
- registry import는 함수 내부 지연 — schemas 모듈 import만으로 strategy 도메인 로딩 강제하지 않음.

### B) user_id scope 강제 (C3)

```text
backend/app/services/strategy_service.py:142-167      get_strategy에 user_id 매개변수 추가, 미일치=NOT_FOUND
backend/app/services/strategy_service.py:62-78        update_strategy에 user_id 필수
backend/app/services/strategy_service.py:108-126      duplicate_strategy 에 user_id 필수, 사본 owner는 호출자 (escalation 방지)
backend/app/services/strategy_service.py:130-148      soft_delete_strategy에 user_id 필수
backend/app/services/strategy_service.py:171-184      list_strategy_versions에 user_id 옵션 추가
backend/app/services/backtest_service.py:175-189      get_backtest_summary에 user_id 옵션, _get_run에 user_id 강제
backend/app/api/routes_strategies.py                  6개 엔드포인트 모두 Depends(get_current_user_id) 받고 service에 전달
backend/app/api/routes_backtests.py                   _get_run_or_raise 헬퍼 + 8개 단일자원 엔드포인트(status/summary/trades/chart-data/daily-equity/cash-events/export/cancel) 모두 user_id 스코프
```

scope 매트릭스:

```text
GET    /api/strategies                   user_id 필요 ✓ (본인 것만 list)
POST   /api/strategies                   user_id 필요 ✓ (사본 owner = 호출자)
GET    /api/strategies/{id}              user_id 필요 ✓ (미소유=404)
PUT    /api/strategies/{id}              user_id 필요 ✓
DELETE /api/strategies/{id}              user_id 필요 ✓
POST   /api/strategies/{id}/duplicate    user_id 필요 ✓ (escalation 방지)

POST   /api/backtests                     user_id 필요 ✓
GET    /api/backtests/{id}/status         user_id 필요 ✓
GET    /api/backtests/{id}/summary        user_id 필요 ✓
GET    /api/backtests/{id}/trades         user_id 필요 ✓
GET    /api/backtests/{id}/chart-data     user_id 필요 ✓
GET    /api/backtests/{id}/daily-equity   user_id 필요 ✓
GET    /api/backtests/{id}/cash-events    user_id 필요 ✓
GET    /api/backtests/{id}/export/{kind}  user_id 필요 ✓
POST   /api/backtests/{id}/cancel         user_id 필요 ✓
```

미소유 자원은 모두 404 NOT_FOUND (정보 누설 방지 — 존재 여부조차 노출 안 함).

### C) 표준 error envelope + X-Request-ID (H7)

```text
backend/app/api/errors.py:1                    신규 — register_exception_handlers, CODE_STATUS_MAP, 핸들러 4종
backend/app/api/middleware.py:1                신규 — RequestIdMiddleware (incoming 보존 또는 uuid4 발급)
backend/app/main.py:11-46                      app 생성 직후 register_exception_handlers + add_middleware(RequestIdMiddleware)
backend/app/core/exceptions.py:91-103          BacktestNotRunningError / BacktestAlreadyRunningError 추가 (10.7.1 카탈로그)
backend/app/api/routes_strategies.py           HTTPException 직접 raise 모두 제거 → AppError raise로 통일
backend/app/api/routes_backtests.py            HTTPException 직접 raise 모두 제거 → BacktestRunNotFoundError / BacktestNotRunningError / InvalidParameterValueError raise
```

handler 4종:
- `AppError` → 표준 envelope + CODE_STATUS_MAP으로 HTTP 상태 결정
- `RequestValidationError` → INVALID_STRATEGY_JSON 또는 generic VALIDATION_ERROR (FastAPI 기본 `{"detail": [...]}` 차단)
- `StarletteHTTPException` → 남은 raw HTTPException(라우트 미존재 404 등)도 envelope으로
- `Exception` → 미처리 예외도 envelope (500 APP_ERROR)

X-Request-ID는 RequestIdMiddleware가 가장 outer로 등록되어 정상 응답·에러 응답·미처리 예외 응답 모두에 부착.

### 사용된 에러 코드 (모두 10.7.1 카탈로그)

```text
INVALID_STRATEGY_JSON                400  (entry 누락, dict 타입 위반, GROUP 형식, logic 위반 등)
UNKNOWN_CONDITION_TYPE               422  (registry 미등록 type)
EXIT_POSITION_IN_EXIT_SIGNAL         422  (포지션 조건이 entry/exit_signal/filters에)
EXIT_SIGNAL_IN_EXIT_POSITION         422  (시계열 조건이 exit_position에)
INVALID_OPERATOR                     400  (operator 화이트리스트 위반)
INVALID_PARAMETER_VALUE              400  (position_sizing.amount<=0, tax_rate.from desc 등)
MISSING_REQUIRED_PARAMETER           400  (condition.type 누락 등)
STRATEGY_NOT_FOUND                   404  (미존재 또는 미소유)
BACKTEST_RUN_NOT_FOUND               404  (미존재 또는 미소유)
BACKTEST_NOT_RUNNING                 409  (이미 종료된 run cancel)
```

신규 카탈로그 코드: 0건 (모두 10.7.1에 이미 존재).

## Tests

```text
신규 테스트 파일:
  backend/tests/schemas/__init__.py                   신규
  backend/tests/schemas/test_strategy_json_validator.py  34건 (validator 음성/정상/결정론)
  backend/tests/api/test_scope_and_envelope.py        21건 (scope 위반 + envelope + X-Request-ID)

수정 테스트 파일:
  backend/tests/api/test_strategies.py                _payload에 exit_position 추가, envelope 포맷에 맞춰 검증 갱신
  backend/tests/services/test_strategy_service.py     update/duplicate/soft_delete 호출 시 user_id 인자 추가

검증 명령:
  py -3.12 -m pytest -q       → 390 passed (baseline 335 + 신규 55)
  py -3.12 -m ruff check       → All checks passed
```

각 테스트가 잡는 것:

```text
schema validator (test_strategy_json_validator.py):
  test_minimal_valid_passes / test_full_strategy_passes / test_group_logic_valid
  test_payload_must_be_dict / test_entry_section_required
  test_either_exit_signal_or_exit_position_required
  test_entry_conditions_must_have_at_least_one
  test_logic_value_must_be_allowed
  test_group_must_have_operator_and_groups
  test_group_nested_group_rejected            (1단계만 허용)
  test_unknown_condition_type_in_entry/in_filters
  test_take_profit_in_exit_signal_rejected     (EXIT_POSITION_IN_EXIT_SIGNAL)
  test_stop_loss_in_entry_rejected
  test_max_holding_days_in_filters_rejected
  test_trailing_stop_in_exit_signal_rejected
  test_price_vs_ma_in_exit_position_rejected   (EXIT_SIGNAL_IN_EXIT_POSITION)
  test_rsi_level_in_exit_position_rejected
  test_invalid_operator
  test_missing_condition_type
  test_position_sizing_unknown_method/_zero_amount/_max_positions_zero
  test_execution_negative_fee/_invalid_tick_rounding
  test_tax_rate_array_descending/_negative_rate/_invalid_date_format/_scalar_float
  test_priority_unknown_method/_unknown_tie_breaker
  test_validation_is_deterministic
  test_unknown_type_error_message_lists_allowed_sorted
  test_all_validator_errors_are_app_errors

scope + envelope (test_scope_and_envelope.py):
  test_user2_cannot_get/_update/_delete/_duplicate_user1_strategy
  test_list_strategies_only_returns_own
  test_user2_cannot_get_user1_backtest_status/_summary/_trades/_chart_data/_daily_equity/_cash_events
  test_user2_cannot_export_user1_backtest
  test_user2_cannot_cancel_user1_backtest
  test_all_error_responses_use_envelope         (404/422/400 모두 검증)
  test_x_request_id_present_on_success/_on_error
  test_x_request_id_preserves_incoming_value/_on_error
  test_x_request_id_generated_when_absent
  test_invalid_json_body_returns_envelope
  test_backtest_create_with_invalid_existing_strategy  (큐 진입 전 재검증)
```

## Issues

1. **Pydantic v2 model_validator 안 AppError 동작**: 테스트 결과 AppError가 그대로 보존되어 우리 핸들러가 잡을 수 있음을 확인 (Pydantic이 `ValidationError`로 wrap하지 않음). 만약 Pydantic 버전 업에서 동작이 바뀌면 model_validator 안에서 raise를 직접 raise from으로 묶어주거나 service 레이어에서 한번 더 호출하는 방식으로 보강 필요.

2. **`get_current_user_id` MVP 기본값**: 여전히 항상 1을 반환. 실제 인증 도입(Phase 4 후속)은 본 작업 범위 밖이지만, scope 강제 코드 자체는 향후 인증 시스템과 그대로 호환됨 — 의존성만 교체하면 됨.

3. **fee/tax=0 하드코드 영속화**: backtest_service의 `_persist_trade_groups_and_executions`(`fee=0.0, tax=0.0`)는 본 작업 scope 밖 (backtest-engine-developer 영역). 새 코드에 추가하지 않았음.

4. **`VALIDATION_ERROR` generic 코드**: errors.py의 `_handle_request_validation_error`에서 strategy/backtest 경로가 아닌 라우트의 schema 위반에 임시 코드 `VALIDATION_ERROR`를 사용했는데, 이는 10.7.1 카탈로그에 없음. 현재는 strategy/backtest 외 라우트가 사실상 conditions(GET) / health 정도라 도달 가능성이 매우 낮지만, Follow-ups에서 10번 문서에 추가 또는 제거하기로.

5. **카탈로그 외 코드 `NOT_FOUND` / `METHOD_NOT_ALLOWED` / `HTTP_ERROR`**: errors.py의 `_handle_starlette_http_exception`이 raw HTTPException(예: 라우트 자체 미존재) 처리에 사용. 이건 우리가 던지지 않는 코드(FastAPI 기본 동작)이므로 카탈로그 위반은 아니지만, 일관성을 위해 10.7.1에 명시 추가하면 좋음 (Follow-ups).

## Result

### 작성/수정 파일

신규 7개:
```text
backend/app/api/errors.py                                  표준 envelope handler
backend/app/api/middleware.py                              X-Request-ID
backend/app/schemas/strategy_json.py                       validate_strategy_json
backend/tests/schemas/__init__.py
backend/tests/schemas/test_strategy_json_validator.py      34건
backend/tests/api/test_scope_and_envelope.py               21건
```

수정 7개:
```text
backend/app/main.py                                        middleware + handler 등록
backend/app/core/exceptions.py                             BacktestNotRunningError / BacktestAlreadyRunningError 추가
backend/app/api/routes_strategies.py                       전부 재작성 (user_id 6개 + AppError raise)
backend/app/api/routes_backtests.py                        전부 재작성 (user_id 8개 + AppError raise + InvalidParameterValueError)
backend/app/services/strategy_service.py                   user_id scope 강제
backend/app/services/backtest_service.py                   _get_run user_id, validator 호출
backend/app/schemas/strategy.py                            model_validator → validate_strategy_json
backend/tests/api/test_strategies.py                       envelope 포맷에 맞춰 갱신
backend/tests/services/test_strategy_service.py            user_id 인자 추가
```

### 정책 근거

- 10번 7절 (에러 envelope) + 7.1 (코드 카탈로그) + 7.2 (HTTP status 매핑)
- 10번 8절 (X-Request-ID)
- 10번 9절 (user_id scope)
- 02번 4절 (logic AND/OR/GROUP 1단계)
- 02번 5절 (exit_signal vs exit_position 분리, requires_position 라우팅)
- 02번 7절 (priority method/tie_breaker)
- 02번 8절 (position_sizing method)
- 02번 11절 (execution fee/tax/slippage/tick_rounding, tax_rate 시계열 from 오름차순)
- 02번 15절 (validation 규칙 전반)
- 03번 4절 (ConditionRegistry requires_position 분기)

### 영속화 스냅샷 영향

본 작업은 strategy_json validation만 영향. 컬럼 변경 없음:
- `BacktestRun.strategy_snapshot_json`: 그대로 (validator는 read-only)
- `BacktestRun.tax_rate_json` / `priority_method` / `priority_tie_breaker` / `random_seed` / `tick_rounding` / `use_adjusted_price`: 그대로
- `TradeExecution.fee` / `tax`: 본 작업 scope 밖 (여전히 0.0 하드코드 — Step 6에서 보강 예정 주석 그대로 유지)
- `BacktestRun.user_id`: 모델에 이미 존재, 신규 컬럼 아님

### pytest 결과

```text
신규: 55건 (validator 34 + scope/envelope 21)
전체: 390건 통과 (baseline 335 + 신규 55)
ruff: All checks passed
```

## Follow-ups

1. **fee/tax=0 하드코드 해소**: `backend/app/services/backtest_service.py:316-330`의 `_persist_trade_groups_and_executions`가 fee=0.0/tax=0.0으로 영속화. ExecutionModel이 ExecutionResult dataclass(gross/fee/tax/net)를 반환하도록 backtest-engine-developer에 요청 필요. 본 에이전트는 그 dataclass를 받으면 영속화 매핑만 한다.

2. **strategy_versions 라우트 노출**: `GET /api/strategies/{id}/versions` (10번 2절)가 라우트로 노출되지 않음 — service의 `list_strategy_versions`만 존재. 별도 작업 분리 권장.

3. **10번 7.1 카탈로그 보완 검토**:
   - `VALIDATION_ERROR` (Pydantic schema 일반 위반) — 추가 또는 INVALID_STRATEGY_JSON으로 통일
   - `NOT_FOUND` / `METHOD_NOT_ALLOWED` / `HTTP_ERROR` — Starlette 기본 응답을 envelope으로 감쌀 때 사용하는 코드, 명시 추가 검토
   현재 코드에는 임시로 사용 중이지만 카탈로그 외 코드라 정책 갱신 필요.

4. **인증 시스템 도입 (Phase 4)**: `get_current_user_id`가 항상 1 반환. 본 작업의 scope 코드는 그대로 동작하므로, 의존성만 교체하면 멀티유저 지원 즉시 가능.

5. **BACKTEST_NOT_RUNNING 매핑 확인**: cancel 라우트는 PENDING/RUNNING이 아닌 status에서만 BACKTEST_NOT_RUNNING(409)으로 응답. 13번 정책 문서와 별도 정합 확인 필요는 없으나, 사용자가 이미 cancelled된 run을 다시 cancel 시도 케이스 등 엣지 케이스 추가 테스트 권장.

6. **list 엔드포인트 페이지네이션**: 본 작업 외 — 10번 10절은 page/page_size를 명시하지만 현재 list_strategies / list_trades / list_daily_equity / list_cash_events는 모두 미구현. 별도 작업 분리.

7. **GET /api/conditions의 X-Request-ID 검증 추가**: 본 작업의 `test_x_request_id_present_on_success`가 conditions 라우트로 검증하므로 회귀 안전망 있음. CORS preflight(OPTIONS)에서도 X-Request-ID expose됐는지 추가 검증 가능.

## 메인 세션 마무리 체크

- [ ] status를 completed로 변경
- [ ] 작업로그/README.md 갱신
- [ ] `git commit`
