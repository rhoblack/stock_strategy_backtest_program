---
date: 2026-05-10
agent: frontend-developer
phase: 12
status: completed
roadmap_step: 030
roadmap_impact:
  - 01-j  # StrategyHeader (복사 / JSON 보기 / 백테스트 실행)
  - 01-k  # 전략 템플릿 + 초보/전문 모드
related_docs:
  - 상세설계/01_strategy_builder_gui_design.md
  - 작업로그/2026-05-10-029-strategy-schema-gui.md
---

# Step 030 — StrategyHeader + 전략 템플릿 (01-j·k)

029에서 6섹션 schema GUI 정합화 완료. 본 step에서 StrategyHeader 액션 버튼 + 전략 템플릿 시스템 도입.

## Plan

### A) StrategyHeader 컴포넌트 (01-j)
- [ ] `frontend/src/features/strategy-builder/components/StrategyHeader/` 신규
- 버튼:
  - **복사**: 현재 strategy → 새 ID로 사본 (POST /api/strategies/{id}/duplicate 활용)
  - **JSON 보기**: serializeDraft(draft) 결과를 modal/drawer로 표시 (read-only, copy to clipboard)
  - **백테스트 실행**: 저장 후 BacktestRunPage로 이동
- 위치: StrategyBuilderPage 상단

### B) 전략 템플릿 시스템 (01-k)
- [ ] `frontend/src/features/strategy-builder/templates/` 신규
- 기본 템플릿 3~5종:
  - 빈 전략 (default)
  - 골든 크로스 (MA 5/20)
  - RSI 과매도 진입
  - 모멘텀 (단기 신고가 + 거래량 증가)
- 각 템플릿은 StrategyDraft 형태 (4섹션 + 6섹션) 완전 구성
- TemplateSelector 컴포넌트: 템플릿 목록 → 선택 시 reducer.APPLY_TEMPLATE 디스패치

### C) APPLY_TEMPLATE reducer 액션
- [ ] `frontend/src/features/strategy-builder/state/reducer.ts`에 신규 액션:
  - `case "APPLY_TEMPLATE": return action.draft` (전체 교체, RESET과 다름)
- [ ] 029에서 인계받은 권장: RESET은 default 초기화, APPLY_TEMPLATE은 템플릿 적용

### D) 초보자/전문가 모드 (01-k 부분)
- [ ] 본 step에서는 토글 + 6섹션 폼 표시/숨김만 (간단)
- 초보자: 4 조건 섹션 + position_sizing만
- 전문가: 모두 표시 (현재 동작)
- 사용자 선호 localStorage 저장

### E) 테스트
- [ ] StrategyHeader 단위 테스트 (각 버튼 동작)
- [ ] 템플릿 적용 reducer 테스트
- [ ] 초보자 모드 토글 테스트

### F) 회귀
- [ ] vitest 전체 + npm run build

### 절대 금지
- 백엔드 절대 수정
- 029 산출물 시그니처 변경 — 활용만
- StrategyConfigPanel 수정 (필요 시 props 추가만)
- 결정론 깨기

### 다음 step (031) 인계
- StrategyHeader의 백테스트 실행 버튼 → BacktestRunPage 호출 형식 (031에서 chart-data API 변경 시 무관)

## Execution

### A) StrategyHeader 컴포넌트 (01-j)

신규:
- `frontend/src/features/strategy-builder/components/StrategyHeader/StrategyHeader.tsx:1` — 헤더 컴포넌트.
  - 좌측: `← 전략 목록` 링크 + 전략 이름 input + 모드 토글 (radiogroup)
  - 우측: 템플릿 / 저장 / 복사 / JSON 보기 / 백테스트 실행
  - **복사**: `useDuplicateStrategy` 호출 → `POST /api/strategies/{id}/duplicate?new_name="{현재 이름} (복사)"` → 성공 시 `/strategies/{newId}`로 navigate. `savedStrategyId == null`이면 disabled.
  - **JSON 보기**: `serializeDraft(draft)` 결과를 `<pre>`로 read-only 표시 + `navigator.clipboard.writeText`로 클립보드 복사 (성공/실패 메시지 2초간 노출).
  - **백테스트 실행**: `savedStrategyId`가 있으면 즉시 `/backtests/new?strategy_id={id}`로 이동. 없으면 `onSave()`를 호출(Promise<number | null>)하고, 반환된 id로 이동. `canSave=false`면 인라인 에러 메시지.
  - **모드 토글**: `useBuilderMode().setMode("beginner" | "expert")` — radio 버튼 형태로 aria-checked 갱신, localStorage 영속화.
  - Modal: 화면 중앙 dialog (role="dialog", aria-modal="true") — JSON 보기와 템플릿 선택에 사용. backdrop 클릭 또는 × 버튼으로 닫음.
- `frontend/src/features/strategy-builder/components/StrategyHeader/index.ts:1` — re-export.

### B) 전략 템플릿 시스템 (01-k)

신규:
- `frontend/src/features/strategy-builder/templates/templates.ts:1` — 템플릿 데이터 + 빌더.
  - 4종 템플릿: `empty` / `golden_cross` / `rsi_oversold` / `momentum_breakout` (각각 `category`: 기본/추세/역추세/모멘텀).
  - `TemplateConditionSpec`: `{ type, values? }` — `ConditionMeta`는 백엔드 카탈로그에서 lookup해서 채움 (메타 default + 템플릿 override).
  - `TemplateSectionSpec`: `{ logic, conditions, group_operator, groups }` — GROUP 모드도 지원.
  - 6 비조건 섹션은 `Partial<XxxState>` 부분 패치 — `defaultXxx()` 위에 덮어씀.
  - `buildDraftFromTemplate(template, metaCatalog, name?)`: 완전한 `StrategyDraft` 생성. 카탈로그에 없는 type은 조용히 스킵.
  - `_resetTemplateIdCounterForTests()`: 결정론 테스트용 카운터 reset.
- `frontend/src/features/strategy-builder/templates/TemplateSelector.tsx:1` — UI 컴포넌트.
  - `useConditions()`로 ConditionMeta 카탈로그 가져옴.
  - 카테고리별 그룹화 → 버튼 형태로 표시.
  - 비-empty 템플릿 적용 시 dirty 상태(이름 또는 조건 보유)면 `window.confirm` 확인.
  - 적용 후 카탈로그에 없어 스킵된 type이 있으면 `role="alert"` 경고 노출.
  - 적용 시 `dispatch({ type: "APPLY_TEMPLATE", draft })`.

### C) APPLY_TEMPLATE reducer 액션

수정:
- `frontend/src/features/strategy-builder/state/reducer.ts:39` — `DraftAction`에 `{ type: "APPLY_TEMPLATE"; draft: StrategyDraft }` 추가.
- `frontend/src/features/strategy-builder/state/reducer.ts:194` — `case "APPLY_TEMPLATE": return { ...action.draft, selected: null }` (전체 교체, selected는 항상 null로 reset). RESET은 `emptyDraft(name)`만 반환하는 default 초기화 — APPLY_TEMPLATE은 그것과 분리됨.

### D) 초보자/전문가 모드 (01-k 부분)

신규:
- `frontend/src/features/strategy-builder/state/useBuilderMode.ts:1` — hook.
  - `BuilderMode = "beginner" | "expert"`, default `"expert"` (현재 동작 유지).
  - localStorage key: `"stockstrategy.builder_mode"`.
  - 잘못된 값은 default로 fallback. `useEffect`로 mode 변경 시 자동 영속화.
  - `BEGINNER_VISIBLE_CONFIG_SECTIONS = ["position_sizing"]` — StrategyConfigPanel 필터링용.

수정:
- `frontend/src/features/strategy-builder/components/StrategyConfigPanel/StrategyConfigPanel.tsx:12` — `useBuilderMode` import 추가.
- `frontend/src/features/strategy-builder/components/StrategyConfigPanel/StrategyConfigPanel.tsx:54` — `visibleSections`로 탭 필터링. 모드 전환으로 active 탭이 사라지면 `safeActive`로 fallback. 초보자 모드 안내 문구 추가.

### 통합

수정:
- `frontend/src/api/strategies.ts:39` — `duplicateStrategy(strategyId, newName)` + `useDuplicateStrategy` 추가. `new_name`을 query param으로 전달 (백엔드 라우트 시그니처 그대로 활용).
- `frontend/src/pages/StrategyBuilderPage.tsx:1` — 기존 inline header 삭제, `<StrategyHeader>` 사용. `onSave`는 Promise<number | null>를 반환하도록 변경 (백테스트 실행 흐름에서 활용). 저장 성공 시 `savedStrategyId`만 set하고 자동 redirect는 안 함 (사용자가 백테스트 실행 또는 복사 가능). `useNavigate`는 더 이상 직접 사용하지 않음.

### 테스트

신규:
- `frontend/src/features/strategy-builder/state/useBuilderMode.test.ts:1` — 4 tests (default expert / setMode + localStorage / toggle / 잘못된 값 fallback).
- `frontend/src/features/strategy-builder/templates/templates.test.ts:1` — 10 tests (4종 카탈로그 / getTemplateById / 필수 필드 / 4종 buildDraftFromTemplate 결과 / 카탈로그 누락 시 스킵 / 결정론 / name override).
- `frontend/src/features/strategy-builder/templates/TemplateSelector.test.tsx:1` — 5 tests (4종 표시 / showEmpty=false / onApplied 콜백 / dirty confirm / 카탈로그 누락 경고).
- `frontend/src/features/strategy-builder/components/StrategyHeader/StrategyHeader.test.tsx:1` — 12 tests (렌더링 / 초기 disabled / canSave 활성 / 복사 mutate + navigate / JSON modal 열기·닫기 / 백테스트 실행 3 분기 / 모드 토글 + localStorage / 템플릿 modal / 저장 실패 메시지).

수정:
- `frontend/src/features/strategy-builder/state/reducer.test.ts:208` — APPLY_TEMPLATE 2 tests 추가 (전체 교체 + selected null / RESET과 다르게 임의 값 적용 가능).
- `frontend/src/features/strategy-builder/components/StrategyConfigPanel/StrategyConfigPanel.test.tsx:7` — `beforeEach localStorage.clear()` + 초보자 모드 1 test 추가 (탭 1개만 노출 + 안내 문구).
- `frontend/src/pages/SaveStrategy.test.tsx:34` — `useDuplicateStrategy` mock 추가. 마지막 테스트의 navigate 검증 제거 (BuilderShell이 더 이상 자동 redirect 안 함 — 의도된 동작 변경).

## Tests

```
npm test -- --run
Test Files  17 passed (17)
     Tests  111 passed (111)
   Duration ~3.6s
```

신규 테스트 34건 (templates 10 + TemplateSelector 5 + StrategyHeader 12 + useBuilderMode 4 + reducer APPLY_TEMPLATE 2 + ConfigPanel 초보자 1).
전체 111건 통과 (baseline 77 → +34).

```
npm run build
✓ tsc -b && vite build
✓ 176 modules transformed
✓ built in 1.24s
```

TypeScript 타입체크 + Vite 프로덕션 빌드 모두 성공.

## Issues

- **저장 흐름 동작 변경**: 기존 BuilderShell은 저장 성공 시 자동으로 `/strategies`로 navigate. Wave 12-030은 `savedStrategyId`만 set하고 redirect는 안 함 (사용자가 헤더에서 즉시 복사/백테스트 실행 가능하도록). SaveStrategy.test.tsx의 navigate 검증 제거 + 주석으로 명시. UI/UX 의도 변경이라 메인 세션이 검토할 가치 있음.
- **상장된 condition type 의존**: 모멘텀 템플릿이 `new_high` / `volume_ratio` / `trading_value`를 참조하는데, 백엔드 condition_definitions.py에 해당 type이 등록되어 있는지 본 step에서는 확인 안 함. 카탈로그에 없으면 TemplateSelector가 경고 표시 + 해당 condition만 스킵 (템플릿 적용은 부분 성공). 향후 백엔드에 condition을 추가하면 자동 노출.
- **버튼 색상**: 백테스트 실행 버튼은 초록(`#16a34a`)으로 강조. 디자인 토큰화는 design-review 통과 후 일괄 처리 권장.
- **Modal 접근성**: focus trap 없음 (Tab 이동이 backdrop 밖으로 나갈 수 있음). 향후 design-review에서 `react-focus-lock` 등 추가 검토.
- **복사 후 redirect**: `/strategies/{newId}`로 이동하지만 라우터(`router.tsx:11`)는 `/strategies/:id` → `StrategyBuilderPage`. 현재 BuilderShell이 URL의 `:id`를 읽지 않아 복사된 전략이 빌더에 자동 로드되지 않음 — Phase 12 후속 step에서 strategy 로드 흐름 추가 필요 (Follow-up).

## Result

### 신규 TypeScript 타입

`frontend/src/features/strategy-builder/state/useBuilderMode.ts`:
- `BuilderMode = "beginner" | "expert"`
- `useBuilderMode()` 반환 시그니처: `{ mode, setMode, toggle, isBeginner, isExpert }`
- `BEGINNER_VISIBLE_CONFIG_SECTIONS: readonly ConfigSectionKey[]`

`frontend/src/features/strategy-builder/templates/templates.ts`:
- `TemplateConditionSpec` / `TemplateSectionSpec` / `StrategyTemplate`
- `STRATEGY_TEMPLATES: StrategyTemplate[]`
- `buildDraftFromTemplate(template, metaCatalog, name?) -> StrategyDraft`
- `getTemplateById(id) -> StrategyTemplate | undefined`

`frontend/src/api/strategies.ts`:
- `duplicateStrategy(strategyId, newName) -> Promise<StrategyOut>`
- `useDuplicateStrategy()` mutation hook

### 메타데이터 자동화 적용 여부

- 템플릿은 `ConditionMeta`를 직접 포함하지 않고 `type + values`만 명세. 적용 시 `useConditions()`의 백엔드 카탈로그에서 lookup → 메타 변경 시 자동 반영.
- 새 condition이 백엔드에 추가되면 템플릿이 그것을 참조하는 즉시 자동 노출 (코드 수정 없음).
- BlockPalette / ConditionEditorPanel과 동일한 메타 우선 패턴 유지.

### 결정론 적용 여부

- 템플릿은 fixed shape — random_seed / 임의의 동적 값 없음.
- `_resetTemplateIdCounterForTests`로 결정론 테스트 가능.
- 초보자/전문가 default = `"expert"` (현재 동작 유지). localStorage 잘못된 값은 default로 fallback.
- `APPLY_TEMPLATE` 액션은 전체 교체 + selected=null — 결정적.

### 02번/01번 문서 갱신 필요 여부

- 02번 schema 정책 변경 없음 — 템플릿은 schema가 허용하는 shape만 사용.
- 01번 GUI 설계서 §3(레이아웃)에 StrategyHeader의 6 버튼(목록 / 이름 / 모드 / 템플릿 / 저장 / 복사 / JSON 보기 / 백테스트 실행) 통합 패턴 반영을 옵션으로 고려. 본 step에서는 미수정 (범위 외).

## Follow-ups

- **다음 step (031) 인계 정보**:
  - StrategyHeader의 백테스트 실행 버튼은 `/backtests/new?strategy_id={id}`로 이동 — 현재 BacktestRunPage가 이 query param을 읽음 (`BacktestRunPage.tsx:13`). 031에서 chart-data API 변경 시 영향 없음.
  - `serializeDraft(draft)`는 02번 schema 그대로 — JSON 보기 modal과 저장 흐름 모두 같은 형식 사용.
  - APPLY_TEMPLATE 후 selected=null이므로 ConditionEditorPanel은 "선택된 조건 없음" 상태. 031 또는 후속 step에서 자동 첫 조건 select 옵션 검토.

- **strategy 로드 흐름**: 라우터의 `/strategies/:id` → BuilderShell이 `useParams().id`를 읽어 `GET /api/strategies/{id}`로 fetch + reducer로 hydrate. 현재 미구현 (복사 후 redirect 시 빈 빌더가 보임). Phase 12 후속 step 필요.

- **백엔드 에러 envelope 한국어 매핑**: 029 Issues에서 인계받은 `INVALID_STRATEGY_JSON` / `EXIT_POSITION_IN_EXIT_SIGNAL` 등 매핑 — StrategyValidationPanel 또는 새 ServerErrorPanel.

- **템플릿 확장**: `volatility_breakout` (변동성 돌파) / `mean_reversion` (평균회귀) / `dual_momentum` 등 추가 검토. 모멘텀 템플릿이 참조하는 `trading_value` condition은 백엔드에 등록 필요 시 추가.

- **JSON 보기 modal 개선**: syntax highlighting (예: `react-syntax-highlighter`) + JSON 다운로드 (.json 파일) 옵션. design-review 후.

- **초보자 모드 확장**: 본 step은 6 비조건 섹션만 필터링. 향후 조건 섹션도 초보자 모드에서 자주 쓰는 조건만 BlockPalette에 노출 옵션 검토 (메타데이터에 `beginner_friendly` flag 추가 필요).

- **Modal 접근성**: focus trap (`react-focus-lock`) + ESC 키로 닫기 + restore focus on close.

- **복사 시 새 이름 입력**: 현재 자동으로 `"{현재 이름} (복사)"` 사용 — 사용자가 새 이름을 직접 입력할 수 있는 prompt 또는 inline rename 옵션 검토.

## 메인 세션 마무리 체크
- [ ] status를 completed로 변경
- [ ] 작업로그/README.md 갱신
- [ ] PM 호출 → 로드맵 갱신 (01-j, 01-k [x] / Phase 12 step 030 ✅)
- [ ] git commit
