---
date: 2026-05-11
agent: backend-api-engineer
phase: 13
status: completed
roadmap_step: "037"
roadmap_impact:
  - 10-q
  - 10-r
related_docs:
  - 상세설계/10_api_design.md
  - 상세설계/04_backtest_engine_design.md
---

# step 037 — 백테스트 cancel 엔진 전파 (H3) + 표준 카탈로그 정식화

## Plan

### 영향 체크박스 (완료 시 갱신 대상)
- `10-q`: BacktestEngine 취소 전파 (H3)
- `10-r`: NOT_FOUND / VALIDATION_ERROR / METHOD_NOT_ALLOWED / HTTP_ERROR 임시 코드 정식화 (10.7.1 갱신)

### 배경 및 목적
- 현재 POST /api/backtests/{id}/cancel 라우트는 DB 상태만 CANCELLED로 변경하지만 실제 실행 중인 BacktestEngine에 취소 신호를 전달하지 않음 (H3)
- 에러 코드 카탈로그에 임시(TEMP_*) 또는 일관성 없는 코드들이 존재 → 10번 7.1절 기준으로 정식화
- AppError 코드들이 상세설계 문서와 일치하는지 검증 + 불일치 수정

### 작업 범위

#### A. BacktestEngine cancel 전파 (10-q)
- [ ] A1. asyncio.Event 또는 threading.Event 기반 cancellation token 구현
- [ ] A2. BacktestEngine.run()에 cancel_token 파라미터 주입
- [ ] A3. 주요 루프(날짜 순회)에서 cancel_token.is_set() 체크 후 BacktestCancelledError raise
- [ ] A4. backtest_service에서 cancel 호출 시 token.set() 호출
- [ ] A5. 실행 중 취소 시 DB 상태 CANCELLED + partial result 영속화 (또는 빈 result)
- [ ] A6. 단위 테스트: cancel 중간 시점에서 상태 전환 + 재실행 가능 여부

#### B. 에러 코드 카탈로그 정식화 (10-r)
- [ ] B1. 현재 AppError 코드 목록 전수 조사 (core/exceptions.py 또는 유사)
- [ ] B2. 10번 설계서 §7.1 에러 코드 목록과 대조
- [ ] B3. TEMP_* 또는 비표준 코드 → 정식 코드로 교체
- [ ] B4. NOT_FOUND / VALIDATION_ERROR / METHOD_NOT_ALLOWED / HTTP_EXCEPTION 표준화
- [ ] B5. 변경된 코드 참조 테스트 업데이트
- [ ] B6. 단위 테스트: 각 코드별 HTTP 상태 코드 매핑 확인

### 완료 기준
- pytest backend/ — 전체 PASS (기존 961건 이상 유지 + 신규 건 추가)
- cancel 요청 시 실행 중 BacktestEngine이 중단됨
- 에러 코드 카탈로그가 10번 §7.1과 1:1 매핑

## Execution

### 적용 절번호
- 10번 §4.4 (비동기 cancel 전파)
- 10번 §7.1 (에러 코드 카탈로그 정식화)
- 10번 §7.2 (HTTP 상태 코드 매핑)

### 작성/수정 파일

**신규 생성:**
- `backend/app/core/cancellation.py` — CancellationToken, BacktestCancelledError, 레지스트리(register/get/cancel/unregister)
- `backend/alembic/versions/d9f3b2a7e041_add_cancelling_status.py` — CANCELLING 상태 마이그레이션 이력
- `backend/tests/api/test_cancel_propagation.py` — cancel 전파 단위/통합 테스트 (15건)
- `backend/tests/api/test_error_catalog.py` — 에러 코드 카탈로그 테스트 (60건)

**수정:**
- `backend/app/models/enums.py:8-17` — BacktestStatus에 CANCELLING 추가
- `backend/app/core/exceptions.py` — 전수 정리: DuplicateStrategyNameError, BacktestTimeoutError, UniversePreviewFailedError, UnauthorizedError, ForbiddenError, RateLimitExceededError, ExportFailedError, ExportTooLargeError 추가 (10번 §7.1 완전 커버)
- `backend/app/api/errors.py` — CODE_STATUS_MAP에 신규 코드 추가; VALIDATION_ERROR→INVALID_PARAMETER_VALUE, NOT_FOUND/METHOD_NOT_ALLOWED/HTTP_ERROR→APP_ERROR 정식화; _handle_request_validation_error에서 비표준 코드 제거
- `backend/app/backtest/engine.py:93-94,167-170,255-261` — CancellationToken import 추가; run() 시그니처에 cancel_token 파라미터 추가; 날짜 루프 상단에 check_cancelled() 호출
- `backend/app/services/backtest_service.py:21-22,107-110,168-177,213-226,232-237` — cancellation import; run_backtest에 CANCELLING 사전 체크; CancellationToken 등록/해제; BacktestCancelledError catch → CANCELLED 처리; finally 블록에 unregister_token
- `backend/app/api/routes_backtests.py:664-717` — cancel 라우트: DB→CANCELLING 후 token.cancel() 호출; 토큰 없으면 즉시 CANCELLED

### 새 에러 코드 (10번 §7.1 추가)
- `DUPLICATE_STRATEGY_NAME` (409) — 기존 enum에만 있었고 exceptions.py에 클래스 없었음
- `BACKTEST_TIMEOUT` (422) — 신규
- `UNIVERSE_PREVIEW_FAILED` (422) — 신규
- `UNAUTHORIZED` (401), `FORBIDDEN` (403), `RATE_LIMIT_EXCEEDED` (429) — 클래스 신규
- `EXPORT_FAILED` (500), `EXPORT_TOO_LARGE` (400) — 클래스 신규

## Tests

### 실행 명령
```
pytest backend/tests/api/test_cancel_propagation.py backend/tests/api/test_error_catalog.py -v
pytest backend/tests/ -q
```

### 결과
- 신규 75건 (`test_cancel_propagation` 15건 + `test_error_catalog` 60건): 모두 PASS
- 전체 1036건 PASS (기존 961건 + 신규 75건), 0건 FAIL
- 경고: FastAPI DeprecationWarning (HTTP_422_UNPROCESSABLE_ENTITY deprecated) — 기능 영향 없음

### 테스트 매핑
| 테스트 | 검증 항목 |
|--------|-----------|
| test_cancellation_token_* | CancellationToken 상태 전이 |
| test_registry_* | 레지스트리 등록/해제/취소 |
| test_engine_cancelled_before_start | 미리 취소된 토큰으로 run() 즉시 중단 |
| test_engine_cancelled_during_run | 실행 중 취소 신호 전파 확인 |
| test_cancel_already_completed_run_returns_409 | 완료된 run cancel → BACKTEST_NOT_RUNNING |
| test_code_status_map_covers_catalog | CODE_STATUS_MAP ⊇ §7.1 카탈로그 |
| test_banned_codes_not_in_status_map | VALIDATION_ERROR 등 비표준 코드 미존재 |
| test_route_404_uses_app_error_envelope | 라우트 없는 404 → APP_ERROR (NOT_FOUND 미사용) |
| test_strategy_not_found_uses_specific_code | 리소스 404 → STRATEGY_NOT_FOUND |

## Issues

1. **DeprecationWarning**: FastAPI가 `HTTP_422_UNPROCESSABLE_ENTITY` → `HTTP_422_UNPROCESSABLE_CONTENT`로 이름 변경 중. 현재 `status.HTTP_422_UNPROCESSABLE_ENTITY`를 사용하는 코드가 경고를 출력. 기능 영향 없으나 후속 step에서 일괄 교체 권장.

2. **CANCELLING 상태 지속 가능성**: BackgroundTasks가 완료 전에 프로세스가 종료되면 DB에 `cancelling` 상태가 남을 수 있음. 앱 재시작 시 `cancelling` → `cancelled` 정리 로직이 없음. 후속 step에서 startup hook 추가 고려.

3. **다중 프로세스 한계**: CancellationToken 레지스트리는 프로세스 내 싱글턴 (`threading.Lock`). Celery/RQ 등 다중 프로세스로 전환 시 Redis Pub/Sub 등으로 교체 필요. 현재 MVP BackgroundTasks 범위에서는 정상 동작.

4. **cancel 응답 스펙**: 10번 §4.4가 응답 status를 "cancelling"으로 명시했으나, 토큰이 없는 경우(PENDING 상태) 즉시 "cancelled"로 전환함. 실행 흐름상 합리적이나 스펙과 미세 불일치. 후속 문서 갱신 또는 클라이언트 양쪽 허용 처리 권장.

## Result

### 신규 라우트/스키마/클래스
| 항목 | 변경 내용 |
|------|-----------|
| `CancellationToken` | threading.Event 래퍼, cancel/is_cancelled/check_cancelled |
| `BacktestCancelledError` | cancel_token 트리거 시 BacktestEngine이 raise |
| `cancellation.py` 레지스트리 | register/get/cancel_run/unregister_token |
| `BacktestStatus.CANCELLING` | cancel 요청 접수 상태 |
| 신규 exceptions 클래스 8개 | §7.1 완전 커버 |

### 에러 코드 scope 매트릭스 (취소 관련)
| 상황 | 코드 | HTTP |
|------|------|------|
| cancel 대상 run 없음 | BACKTEST_RUN_NOT_FOUND | 404 |
| 이미 완료/실패/취소된 run | BACKTEST_NOT_RUNNING | 409 |
| cancel 성공 (엔진 취소 신호 전달) | — (200 OK, cancelling 상태) | 200 |
| cancel 성공 (토큰 없음, 즉시) | — (200 OK, cancelled 상태) | 200 |

### CODE_STATUS_MAP 최종 커버리지
- 10번 §7.1 카탈로그 25개 코드 전부 매핑 완료
- 비표준 임시 코드 (VALIDATION_ERROR, NOT_FOUND, METHOD_NOT_ALLOWED, HTTP_ERROR) 제거 완료

## Follow-ups

1. **FastAPI DeprecationWarning 해결** — `HTTP_422_UNPROCESSABLE_ENTITY` → `HTTP_422_UNPROCESSABLE_CONTENT` 전환 (후속 step)
2. **앱 시작 시 `cancelling` 상태 정리** — startup event에서 `cancelling` → `cancelled` 일괄 업데이트 추가
3. **10번 §7.1 문서 갱신** — `CANCELLING` 상태를 §4.3 status 목록에 명시 (현재 5개 → 6개)
4. **DuplicateStrategyNameError 실제 사용** — 현재 strategy_service.py에서 중복 이름 체크 로직에서 이 예외를 raise하고 있는지 확인 + 미사용 시 연결 필요
5. **EXPORT_FAILED/EXPORT_TOO_LARGE 실제 사용** — csv_exporter에서 해당 예외 raise 연결 필요 (현재 AppError 기본값)

## 메인 세션 마무리 체크

- [ ] status를 completed로 변경
- [ ] 작업로그/README.md "최근 작업" 표에 1행 추가
- [ ] Phase 상태가 변경되었으면 Phase 표 갱신
- [ ] Follow-ups 중 다음 작업 후보로 옮길 항목 정리
- [ ] **PM 에이전트 호출 → 로드맵.md 갱신** — "step 037 마무리" 지시. PM이 Phase 로드맵 step ✅ + 영향 체크박스 [x] + 진행률 표 손계산을 직접 Edit. (영향 체크박스 ID: 10-q, 10-r)
- [ ] `git commit` (단일 커밋)
- [ ] **Phase 마지막 step이 아님** (Phase 13은 034~039 총 6 step)
