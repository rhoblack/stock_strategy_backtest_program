# 작업 로그 인덱스

이 폴더는 프로젝트 진행 중 수행한 모든 코딩 작업의 로그를 보관합니다.

**모든 새 세션은 이 파일을 가장 먼저 읽고 시작합니다.**

---

## 사용 규칙

### 새 작업 시작 시
1. 이 README.md를 읽어 현재 Phase 상태와 최근 작업을 파악
2. `_TEMPLATE.md`를 복사해 새 로그 파일 생성
   - 명명 규칙: `YYYY-MM-DD-NNN-짧은-설명.md` (예: `2026-05-09-001-rsi-condition.md`)
   - NNN은 그 날의 작업 일련번호 (001부터)
3. Plan 섹션을 먼저 작성 (체크리스트 형태)
4. 실행 (직접 또는 에이전트 호출)
5. 완료 시 본 README.md의 "최근 작업"과 "현재 Phase 상태" 갱신
6. **각 step 완료 시**: 단일 `git commit`
7. **Phase 완료 시 (의무)**: `git push origin main` 자동 실행 — push 누락 시 다음 세션이 GitHub에서 동기화 못 함

### 에이전트 호출 시
메인 세션이 에이전트를 호출할 때 작업 로그 파일 경로를 전달:
> "작업로그/2026-05-09-001-rsi-condition.md를 참고해서 작업하고, Execution/Tests/Result 섹션을 채워줘"

에이전트는 `status` 변경과 본 README.md 갱신은 하지 않습니다 (메인 세션 담당).

### 다음 세션이 참고할 정보
- 어떤 작업이 끝났는지 (completed)
- 어떤 작업이 진행 중인지 (in_progress)
- 어떤 작업이 블록되었는지 (blocked) — 이유 함께 기록
- 다음에 할 작업의 후보 (Follow-ups에 적힌 항목들)

---

## 현재 Phase 상태

설계서 (`stock_strategy_lab_program_introduction.md` 12절) 기준 MVP Phase 진행 현황.

| Phase | 내용 | 상태 |
|---:|---|---|
| 0 | 설계 문서 작성 + 리뷰 반영 | ✅ 완료 |
| 0 | CLAUDE.md + 코딩 에이전트 + 작업 로그 시스템 | ✅ 완료 |
| 1 | 백엔드 핵심 엔진 (조건 5개 + StrategyEngine + 단일종목 백테스트 + Metrics) | ✅ 완료 (9/9) |
| 2 | SQLite 저장 (users/strategies/backtest_runs/trade_groups/...) | ✅ 완료 (6/6) |
| 3 | GUI 전략 빌더 | 🔄 진행 중 (6/7) |
| 4 | 백테스트 실행/결과 화면 | ⬜ 미시작 |
| 5 | 종목 봉차트 + 매수/매도 마커 | ⬜ 미시작 |
| 6 | Portfolio + CashManager (예수금 부족 시 일부 매도) | ⬜ 미시작 |
| 7 | CSV/ZIP Export | ⬜ 미시작 |

**현재 작업 중**: 없음 (Phase 3 / Step 2 — 프론트엔드 골격 — 다음에 시작).

**환경 셋업 완료**: `backend/.venv/` 활성화 후 `./.venv/Scripts/python.exe -m pytest` 로 검증 가능. **272/272 통과** + ruff All checks passed. Node v24 + npm 11 사용 가능.

**MVP end-to-end 백엔드 완성**: 전략 생성 → 백테스트 실행 → 영속화 → 요약 조회까지 동작. Alembic 마이그레이션으로 운영 환경 준비.

**에이전트 시스템 메모**: `.claude/agents/` 정의가 현재 세션에 hot reload되지 않음. 새 세션 시작 시 정상 인식 여부 확인 필요. 안 되면 메인 세션이 에이전트의 system prompt를 따라 직접 작업 가능.

---

## 최근 작업 (최신 순)

아직 코딩 작업 로그 없음. 첫 작업이 추가되면 아래에 항목으로 기록합니다.

```text
| 날짜 | 파일 | Phase | 에이전트 | 상태 | 한줄 요약 |
|---|---|---|---|---|---|
| 2026-05-09 | 001-... | 1 | condition-author | ✅ | RSI 조건 함수 추가 |
```

| 날짜 | 파일 | Phase | 에이전트 | 상태 | 한줄 요약 |
|---|---|---|---|---|---|
| 2026-05-10 | [003-preview-validation](./2026-05-10-003-preview-validation.md) | 3 | main | ✅ | StrategyPreviewPanel + StrategyValidationPanel + 10건 |
| 2026-05-10 | [002-condition-editor-panel](./2026-05-10-002-condition-editor-panel.md) | 3 | main | ✅ | ConditionEditorPanel parameters 자동 폼 + 즉시 반영 + 4건 |
| 2026-05-10 | [001-strategy-draft-state](./2026-05-10-001-strategy-draft-state.md) | 3 | main | ✅ | StrategyDraft reducer + Canvas 카드 + 추가/삭제 인터랙션 + 19건 |
| 2026-05-09 | [018-strategy-builder-page-skeleton](./2026-05-09-018-strategy-builder-page-skeleton.md) | 3 | main | ✅ | StrategyBuilderPage 3열 레이아웃 + Router + BlockPalette(실제 데이터) + 6건 |
| 2026-05-09 | [017-frontend-skeleton](./2026-05-09-017-frontend-skeleton.md) | 3 | main | ✅ | 프론트엔드 골격 (Vite + React + TS + TanStack Query) + 빌드/테스트 통과 |
| 2026-05-09 | [016-fastapi-conditions-api](./2026-05-09-016-fastapi-conditions-api.md) | 3 | main | ✅ | FastAPI 도입 + GET /api/conditions (메타데이터 자동 노출) + 6건 |
| 2026-05-09 | [015-alembic](./2026-05-09-015-alembic.md) | 2 | main | ✅ | **Phase 2 완료**: Alembic 도입 + baseline 마이그레이션 + 회귀 검증 3건 |
| 2026-05-09 | [014-services-layer](./2026-05-09-014-services-layer.md) | 2 | main | ✅ | strategy_service + backtest_service (Phase 1↔Phase 2 통합 + end-to-end 영속화) + 15건 |
| 2026-05-09 | [013-daily-equity-model](./2026-05-09-013-daily-equity-model.md) | 2 | main | ✅ | DailyEquity 모델 (UniqueConstraint + 복합 인덱스) + 5건 |
| 2026-05-09 | [012-trade-models](./2026-05-09-012-trade-models.md) | 2 | main | ✅ | TradeGroup + TradeExecution 모델 + SQLite PRAGMA foreign_keys 자동화 + 7건 |
| 2026-05-09 | [011-backtest-run-result-models](./2026-05-09-011-backtest-run-result-models.md) | 2 | main | ✅ | BacktestRun + BacktestResult 모델 (정확성 정책 스냅샷 모두 영속화) + 9건 |
| 2026-05-09 | [010-db-and-strategy-models](./2026-05-09-010-db-and-strategy-models.md) | 2 | main | ✅ | SQLAlchemy 인프라 + User/Strategy/StrategyVersion 모델 + DB 테스트 11건 |
| 2026-05-09 | [009-golden-test](./2026-05-09-009-golden-test.md) | 1 | main | ✅ | **Phase 1 완료**: Golden test fixture 4종 (frozen expected 9지표 + 결정론 10회) |
| 2026-05-09 | [008-metrics](./2026-05-09-008-metrics.md) | 1 | main | ✅ | calculate_metrics (12개 지표, trade_group 단위 집계) + 13건 테스트 |
| 2026-05-09 | [007-backtest-engine](./2026-05-09-007-backtest-engine.md) | 1 | main (backtest-engine-developer 대행) | ✅ | 단일 종목 BacktestEngine (정확성 정책 13.3/13.4/13.16 적용) + 13건 테스트 |
| 2026-05-09 | [006-execution-portfolio](./2026-05-09-006-execution-portfolio.md) | 1 | main (backtest-engine-developer 대행) | ✅ | ExecutionModel (호가/세율 시계열) + Portfolio (trade_groups 부분매도 + FIFO) + 70건 테스트 |
| 2026-05-09 | [005-strategy-engine](./2026-05-09-005-strategy-engine.md) | 1 | main | ✅ | StrategyEngine (entry/exit_signal/filters + AND/OR/GROUP) + 17건 테스트 |
| 2026-05-09 | [004-basic-conditions-5](./2026-05-09-004-basic-conditions-5.md) | 1 | main (condition-author 대행) | ✅ | 5개 기본 조건 (price_vs_ma / ma_cross / volume_ratio / rsi_level / take_profit) + 메타 카탈로그 + 44건 테스트 |
| 2026-05-09 | [003-indicators-and-compare](./2026-05-09-003-indicators-and-compare.md) | 1 | main | ✅ | venv 셋업 + indicators (MA/EMA/RSI/MACD) + compare 유틸 + 31건 테스트 |
| 2026-05-09 | [002-condition-registry](./2026-05-09-002-condition-registry.md) | 1 | main | ✅ | ConditionRegistry 코어 (라우팅 분기 + 메타데이터 + 16건 테스트) |
| 2026-05-09 | [001-project-skeleton](./2026-05-09-001-project-skeleton.md) | 1 | main | ✅ | 백엔드 패키지 골격 + 13개 모듈 디렉토리 + core (config/exceptions/logging) + smoke test 5건 |

---

## Phase 1 완료 ✅

모든 9단계 완료. 단일 종목 백테스트 end-to-end 동작 + Golden test 회귀 보증.

1. ✅ 프로젝트 골격 셋업 — 2026-05-09-001
2. ✅ ConditionRegistry 코어 구현 — 2026-05-09-002
3. ✅ indicators.py + compare 유틸리티 — 2026-05-09-003
4. ✅ 기본 조건 5개 — 2026-05-09-004
5. ✅ StrategyEngine 구현 — 2026-05-09-005
6. ✅ ExecutionModel + Portfolio (TradeGroup) — 2026-05-09-006
7. ✅ 단일 종목 BacktestEngine — 2026-05-09-007
8. ✅ Metrics — 2026-05-09-008
9. ✅ Golden test — 2026-05-09-009

## Phase 2 완료 ✅

모든 6단계 완료. SQLite 영속화 + 서비스 레이어 + 마이그레이션 시스템.

1. ✅ SQLAlchemy 모델 — users / strategies / strategy_versions — 2026-05-09-010
2. ✅ backtest_runs + backtest_results — 2026-05-09-011
3. ✅ trade_groups + trade_executions — 2026-05-09-012
4. ✅ daily_equity 모델 — 2026-05-09-013
5. ✅ services 레이어 (strategy_service + backtest_service) — 2026-05-09-014
6. ✅ Alembic 도입 + baseline 마이그레이션 — 2026-05-09-015

(cash_events는 Phase 6 CashManager 도입 시 추가)

## Phase 3 다음 작업 후보 (GUI 전략 빌더)

1. ✅ FastAPI + GET /api/conditions — 2026-05-09-016
2. ✅ 프론트엔드 골격 (Vite + React + TS) — 2026-05-09-017
3. ✅ StrategyBuilderPage 골격 + Router — 2026-05-09-018
4. ✅ StrategyDraft 상태 + Canvas 카드 + 추가/삭제 — 2026-05-10-001
5. ✅ ConditionEditorPanel 자동 폼 — 2026-05-10-002
6. ✅ StrategyPreviewPanel + StrategyValidationPanel — 2026-05-10-003
7. ⏭ **다음 (Phase 3 마지막)**: 전략 저장 (POST /api/strategies + 프론트 연동)
4. BlockPalette (메타데이터 기반 자동 생성)
5. ConditionEditorPanel (parameters 메타로 폼 자동)
6. StrategyPreviewPanel + StrategyValidationPanel
7. 전략 저장 (POST /api/strategies + 프론트 연동) — Phase 3 마지막 step에서 push

각 단계는 별도 작업 로그 파일을 만들어 진행합니다.

---

## 블록된 작업

(없음)
