---
date: 2026-05-10
agent: main
phase: 3
status: completed
related_docs:
  - 상세설계/10_api_design.md
  - 상세설계/02_strategy_json_schema_design.md
---

# Phase 3 / Step 7 (Phase 3 마지막) — 전략 저장

## Plan / Execution

### 백엔드

- [x] app/schemas/strategy.py: StrategyCreate / StrategyUpdate / StrategyOut (Pydantic)
- [x] app/api/dependencies.py: get_db_session + get_current_user_id (MVP id=1)
- [x] app/main_state.py: get_engine 싱글턴 + reset_engine_for_tests + 시스템 유저 보장
- [x] app/api/routes_strategies.py: POST/GET/GET-by-id/PUT/DELETE/duplicate
- [x] app/main.py: strategies_router include
- [x] tests/api/test_strategies.py: 5건 (CRUD + duplicate + soft-delete + 404)
- [x] tests/api/conftest.py: file-based SQLite (in-memory는 connection별 독립이라 dependency가 새 session 만들 때 테이블이 안 보임)
- [x] pyproject.toml: ruff B008 ignore (FastAPI Depends() 표준 패턴)

### 프론트엔드

- [x] utils/serializeDraft.ts: StrategyDraft → strategy_json (instance_id/meta 제거 + 평탄화)
- [x] api/strategies.ts: useCreateStrategy mutation + useStrategies
- [x] StrategyBuilderPage: 이름 입력 + Save 버튼 활성화/비활성화 + isPending 표시 + 실패 안내
- [x] 클릭 → mutate → onSuccess 시 navigate("/strategies")
- [x] 테스트 4건: serializeDraft (3) + 저장 흐름 (3 — disabled/활성화/저장+redirect)

## Tests

```text
backend pytest: 277/277 (이전 272 + 신규 5)
frontend vitest: 39 passed (이전 33 + 신규 6)
backend ruff: All checks passed
frontend build: 304KB / 100KB gzip
```

## Issues

- in-memory SQLite는 dependency가 새 session을 만들면 테이블 안 보임 → file-based로 전환.
- vi.spyOn(strategiesApi, "createStrategy")가 useMutation 클로저에 capture된 함수를 가로채지 못함 → vi.mock("../api/strategies")로 useCreateStrategy 자체 mock.
- 기존 StrategyBuilderPage 테스트 button name "저장" → "전략 저장" (aria-label 변경) 갱신.

## Result

- end-to-end 흐름 동작: 빌더 → 이름 입력 → 조건 추가 → 저장 → API 호출 → DB 영속화 → /strategies redirect
- StrategyVersion v1 자동 생성 (services 레이어가 Phase 2/Step 5에서 처리)
- 백엔드 Strategy CRUD API 완성 — Phase 4 백테스트 실행 화면이 곧바로 사용 가능

## Phase 3 완료 ✅

7단계 / 9 commits / 코드 ~3,000줄 (frontend ~1,400 + backend ~600 + 테스트)
- FastAPI 도입 + GET /api/conditions / Strategy CRUD
- Vite + React + TypeScript + TanStack Query + Router
- 메타데이터 기반 자동 폼 (BlockPalette, ConditionEditorPanel)
- StrategyDraft useReducer + Context 상태 관리
- 자연어 미리보기 + 검증 (오류/경고)
- 전략 저장 → DB 영속화 → 목록 redirect

## Follow-ups

- StrategyListPage 실제 데이터 연동 (Phase 4 또는 후속 step)
- 전략 편집 (PUT /api/strategies/:id)
- 자금 관리 섹션 UI (cash_management)
- ESLint config 누락 — npm run lint 동작 안 함

## 메인 세션 마무리 체크
- [x] status completed
- [x] 작업로그/README.md 갱신 (Phase 3 완료)
- [x] Phase 마지막 step → git push 의무
