---
date: 2026-05-10
agent: frontend-developer
phase: 12
status: completed
roadmap_step: 029
roadmap_impact:
  - 01-h  # 6섹션 폼 (position_sizing/cash_management/risk_management/execution/priority/metadata)
  - 01-i  # StrategyDraft에 6섹션 상태 추가
  - 02-f  # 프론트 GROUP 직렬화
  - 02-g  # 프론트 position_sizing 직렬화
  - 02-h  # 프론트 cash_management 직렬화
  - 02-i  # 프론트 risk_management / execution / priority 직렬화
  - 02-j  # 프론트 metadata.schema_version / random_seed 직렬화
  - 02-k  # execution.tax_rate 시계열 GUI 통합
related_docs:
  - 상세설계/01_strategy_builder_gui_design.md
  - 상세설계/02_strategy_json_schema_design.md
  - 상세설계/11_frontend_architecture_design.md
---

# Step 029 — 02 schema GUI 정합화 (Phase 12 첫 step, 가장 invasive)

리뷰 011 H6 핵심 — 현재 프론트 serializeDraft가 entry/exit_signal/exit_position/filters 4섹션 + name만 직렬화. position_sizing/cash_management/risk_management/execution/priority/metadata 6섹션이 GUI에 없고 직렬화도 없음 → 백엔드 validator(C4)가 받아도 사용자가 GUI로 설정 불가.

본 step에서 6섹션 폼 + StrategyDraft 확장 + serializeDraft 6섹션 추가 + GROUP/tax_rate 시계열 GUI 통합.

## Plan

### A) StrategyDraft 6섹션 상태 (01-i)
- [ ] `상세설계/02_strategy_json_schema_design.md` 11절(execution) + 6섹션 명세 정독
- [ ] `frontend/src/features/strategy-builder/types/strategyDraft.ts` (또는 동등 위치)에 6섹션 추가:
  - `position_sizing: { method, amount, max_positions }`
  - `cash_management: { enabled, action, repeat_until_cash_sufficient }`
  - `risk_management: { ... }` (02번 schema 명세)
  - `execution: { fee_rate, slippage, tick_rounding, tax_rate (단일 또는 시계열) }`
  - `priority: { method, tie_breaker }`
  - `metadata: { schema_version, random_seed, ... }`
- [ ] reducer에 6섹션 액션 추가 (각 필드 set / reset / 기본값)
- [ ] 기존 4섹션(entry/exit_signal/exit_position/filters)과 호환 유지

### B) 6섹션 폼 컴포넌트 (01-h)
- [ ] `frontend/src/features/strategy-builder/components/StrategyConfigPanel/` 신규 디렉토리
  - `PositionSizingForm.tsx`: method radio + amount input + max_positions input
  - `CashManagementForm.tsx`: enabled toggle + action select + repeat_until_cash_sufficient
  - `RiskManagementForm.tsx`: 02번 §10 필드
  - `ExecutionForm.tsx`: fee_rate / slippage / tick_rounding select + tax_rate 시계열 (배열 입력 — 02-k)
  - `PriorityForm.tsx`: method select(none/trading_value_desc/market_cap_desc/random) + tie_breaker
  - `MetadataForm.tsx`: schema_version (read-only) / random_seed input
- [ ] `StrategyConfigPanel.tsx`: 6 폼을 탭 또는 collapse로 묶음
- [ ] 기존 StrategyBuilderPage에 통합

### C) serializeDraft 6섹션 직렬화 (02-g·h·i·j·k)
- [ ] `frontend/src/features/strategy-builder/utils/serializeDraft.ts`:
  - 기존 entry/exit_signal/exit_position/filters 직렬화 유지
  - 6섹션 추가: position_sizing / cash_management / risk_management / execution / priority / metadata
  - tax_rate 시계열은 array 형태 (`[{from, rate}]`)로 직렬화 (02번 11절 + 13.6 정합)
- [ ] schema_version은 fixed value (예: "1.0") + random_seed는 사용자 입력

### D) GROUP 직렬화 (02-f)
- [ ] `serializeDraft.ts`에 GROUP 노드 처리 추가 (1단계 중첩)
- [ ] 백엔드 validator(C4)는 이미 GROUP 검증 — 프론트가 그것을 만들 수 있어야 함
- [ ] StrategyDraft에 GROUP 노드 타입 + reducer 액션 추가

### E) 백엔드 validator 통합 (이미 백엔드 있음)
- [ ] save 시 백엔드가 4xx + 표준 envelope 반환 → GUI 에러 표시 (StrategyValidationPanel 활용)
- [ ] 신규 에러 코드(EXIT_POSITION_IN_EXIT_SIGNAL 등)는 한국어 메시지 매핑

### F) 테스트
- [ ] `frontend/src/features/strategy-builder/__tests__/strategyDraft.test.ts` 확장 — 6섹션 reducer
- [ ] `frontend/src/features/strategy-builder/__tests__/serializeDraft.test.ts` 확장 — 6섹션 + GROUP + tax_rate 시계열 직렬화
- [ ] 컴포넌트 단위 테스트 (vitest + @testing-library/react)

### G) 회귀
- [ ] `npm test -- --run` (vitest)
- [ ] `npm run build` (tsc + vite)
- [ ] 백엔드 회귀: 영향 없어야 함 (frontend 변경만)

### 절대 금지
- BacktestEngine / Portfolio / StrategyEngine / API / services / market_data / models / conditions 절대 수정 (frontend-developer 영역 외)
- 백엔드 validator C4 수정 — 활용만
- 백엔드 schemas 수정 — 활용만
- 02번 schema 정책 변경 (정책 변경 필요 시 사용자 확인 후 02번 문서 먼저 갱신)
- 결정론 깨기 (랜덤 default seed 등)
- StrategyDraft 기존 4섹션 호환성 깨기

### 다음 step (030) 인계 정보
- StrategyDraft 확장 형식 (StrategyHeader가 활용)
- StrategyConfigPanel 통합 패턴 (template 적용 시)

## Execution

### A) StrategyDraft 6섹션 상태 (01-i)

신규:
- `frontend/src/features/strategy-builder/state/strategySections.ts:1` — 02번 §7~§12, §17 매핑. 각 섹션의 state interface + default 함수 + 옵션 카탈로그(POSITION_SIZING_METHODS / CASH_TRIGGER_TYPES / EXECUTION_PRICE_FIELDS / PRIORITY_METHODS / TIE_BREAKERS / TICK_ROUNDING_MODES). `STRATEGY_SCHEMA_VERSION = "1.0"` 고정 export.

수정:
- `frontend/src/features/strategy-builder/state/types.ts:1` — `StrategyDraft`에 6 비조건 섹션(`position_sizing`, `cash_management`, `risk_management`, `execution`, `priority`, `metadata`) 추가. `Logic` 타입에 `"GROUP"` 추가. `SectionState`에 `group_operator: GroupOperator` + `groups: GroupNode[]` 추가. `GroupNode` 타입 신규 (1단계 중첩 정책 — `logic: "AND" | "OR"`만 허용).
- `frontend/src/features/strategy-builder/state/reducer.ts:1` — DraftAction 확장:
  - GROUP: `ADD_GROUP`, `REMOVE_GROUP`, `SET_GROUP_LOGIC`, `SET_GROUP_OPERATOR` + 기존 `ADD_CONDITION`/`REMOVE_CONDITION`/`UPDATE_VALUE`에 `group_id?` 추가
  - 6 비조건 섹션: `POSITION_SIZING_SET`, `CASH_MGMT_SET`, `RISK_MGMT_SET`, `EXECUTION_SET`, `EXECUTION_TAX_ADD`/`REMOVE`/`UPDATE`, `PRIORITY_SET`, `METADATA_SET`/`ADD_TAG`/`REMOVE_TAG`
  - `mapConditions(sec, group_id, fn)` 헬퍼로 AND/OR 모드와 GROUP 모드를 통합 처리

### B) 6 폼 컴포넌트 (01-h)

신규 디렉토리 `frontend/src/features/strategy-builder/components/StrategyConfigPanel/`:
- `formControls.tsx:1` — `NumberField` / `TextField` / `SelectField` / `CheckboxField` / `FormSection`. 빈 문자열("")을 "미입력"으로 보존하는 NumberField가 핵심.
- `PositionSizingForm.tsx:1` — 02번 §8. 활성화 + method + amount/ratio + max_positions + max_daily_entries + daily_buy_budget + allow_pyramiding.
- `CashManagementForm.tsx:1` — 02번 §9. trigger(2종) + threshold(조건부) + sell_fraction + target_method + repeat_until_cash_sufficient.
- `RiskManagementForm.tsx:1` — 02번 §10. drawdown_pct / max_position_ratio / max_daily_loss_pct.
- `ExecutionForm.tsx:1` — 02번 §11 + 정책 13.6/13.7. entry/exit_price + fee_rate + slippage + use_adjusted_price + max_gap + tick_rounding + 거래세 모드 토글(single/timeseries) + `TaxTimeseriesTable` (행 추가/삭제, date 입력, rate 입력, 한국 거래세 4행 default).
- `PriorityForm.tsx:1` — 02번 §7. method(6종) + tie_breaker(2종). random 선택 시 metadata.random_seed 안내 메시지.
- `MetadataForm.tsx:1` — 02번 §12, §17. schema_version read-only 표시 + random_seed(빈 문자열 허용 — 자동 생성 금지) + 즐겨찾기 + 태그 chip(중복 무시 + trim).
- `StrategyConfigPanel.tsx:1` — 6 폼을 탭으로 묶음. 각 탭 라벨에 활성화 dot 표시.
- `index.ts:1` — re-export.

수정:
- `frontend/src/features/strategy-builder/components/StrategyCanvas.tsx:3` — `<SectionPlaceholder label="자금 관리" />` 제거하고 `<StrategyConfigPanel />` 통합. unused `SectionPlaceholder` 함수 삭제.

### C/D) serializeDraft 6섹션 + GROUP (02-f, g, h, i, j, k)

수정:
- `frontend/src/features/strategy-builder/utils/serializeDraft.ts:1` — 전면 재작성:
  - `SerializedSection = SerializedConditionsBlock | SerializedGroupBlock` union
  - GROUP 모드 직렬화: `{ logic: "GROUP", operator, groups: [{ logic, conditions }] }` (02번 §4 — 1단계 중첩)
  - 빈 그룹 자동 제외 — 모든 그룹이 비면 섹션 자체 제외
  - 6 비조건 섹션 직렬화 함수: `serializePositionSizing` / `serializeCashManagement` / `serializeRiskManagement` / `serializeExecution` / `serializePriority` / `serializeMetadata`
  - 각 섹션 `enabled === false` 시 출력 제외 (백엔드 default 활용 정책)
  - `num()` 헬퍼로 `number | ""` → `number | undefined` 정규화 (빈 문자열은 직렬화 제외)
  - tax_rate: mode=single → float 단일, mode=timeseries → `[{from, rate}]` 배열. 빈 행 자동 필터링
  - metadata.schema_version은 항상 `STRATEGY_SCHEMA_VERSION` ("1.0") 고정
  - metadata.random_seed는 사용자 입력 시에만 직렬화 (자동 생성 금지)

### E) 백엔드 validator 통합

본 step에서는 직렬화 형식만 백엔드 validator(C4)와 정합화. 에러 메시지 한국어 매핑은 다음 step (StrategyHeader 저장 흐름 + 에러 envelope 표시)에서 작업.

### F/G) 테스트 + 회귀

- `frontend/src/features/strategy-builder/state/reducer.test.ts:1` — 기존 8건 + GROUP(4건) + 6 비조건 섹션(5건) → 17 tests
- `frontend/src/features/strategy-builder/utils/serializeDraft.test.ts:1` — 기존 3건 + GROUP(2건) + 6 비조건 섹션(10건) → 15 tests. union narrowing helper(`asAndOr`/`asGroup`) 추가
- `frontend/src/features/strategy-builder/components/StrategyConfigPanel/StrategyConfigPanel.test.tsx:1` — 신규 12 tests (탭 전환 3 + position_sizing 2 + execution tax 3 + priority/metadata 3 + cash_management 1)

## Tests

```
npm test
Test Files  13 passed (13)
     Tests  77 passed (77)
   Duration ~2.9s
```

신규 테스트 34건 / 전체 77건 통과 (baseline 12 files / 43 tests).

```
npm run build
✓ tsc -b && vite build
✓ 171 modules transformed
✓ built in 1.20s
```

TS 타입체크 + Vite 프로덕션 빌드 모두 성공.

## Issues

- `SET_LOGIC` select가 `StrategyCanvas.tsx`에서 여전히 `"AND" | "OR"`만 다룸 — 본 step은 직렬화/reducer만 GROUP을 지원하고, GROUP 토글 UI는 다음 step(030 또는 후속)에서 별도 처리. 현재 GROUP 모드는 reducer 액션을 직접 디스패치해야 진입 가능 (e.g. 템플릿 적용으로 진입).
- 백엔드 에러 envelope (`EXIT_POSITION_IN_EXIT_SIGNAL` 등) 한국어 매핑은 본 step 범위 밖. 다음 step에서 StrategyValidationPanel 또는 신규 ServerErrorPanel에 매핑 추가 필요.
- 6 폼이 모두 `enabled` 토글을 가지지만 `StrategyValidationPanel`(클라이언트 검증)은 6섹션을 평가하지 않음 — 현재는 백엔드 validator C4에 의존. 클라이언트 검증 보강은 향후 작업.

## Result

### 신규 TypeScript 타입

`frontend/src/features/strategy-builder/state/strategySections.ts`:
- `PositionSizingState` — method / amount | "" / ratio | "" / max_positions | "" / max_daily_entries | "" / daily_buy_budget | "" / allow_pyramiding / enabled
- `CashManagementState` — enabled / trigger_type / trigger_threshold | "" / action_type / sell_fraction | "" / target_method / repeat_until_cash_sufficient
- `RiskManagementState` — enabled / stop_trading_on_drawdown_pct | "" / max_position_ratio | "" / max_daily_loss_pct | ""
- `ExecutionState` — enabled / entry_price / exit_price / fee_rate | "" / slippage | "" / tax_rate_mode("single"|"timeseries") / tax_rate_single | "" / tax_rate_timeseries: TaxRateBracket[] / use_adjusted_price / max_gap_pct_for_entry | "" / allow_buy_limit_up / allow_sell_limit_down / tick_rounding
- `PriorityState` — enabled / method (6종) / tie_breaker (2종)
- `MetadataState` — enabled / random_seed | "" / tags / favorite
- `TaxRateBracket` — { from: string; rate: number | "" }
- `STRATEGY_SCHEMA_VERSION = "1.0"` 고정 상수

`frontend/src/features/strategy-builder/state/types.ts`:
- `StrategyDraft`에 6 비조건 섹션 + `GroupNode` 추가
- `Logic = "AND" | "OR" | "GROUP"`

`frontend/src/features/strategy-builder/utils/serializeDraft.ts`:
- `SerializedConditionsBlock` / `SerializedGroupBlock` union
- `SerializedExecution` / `SerializedPositionSizing` / `SerializedCashManagement` / `SerializedRiskManagement` / `SerializedPriority` / `SerializedMetadata` / `SerializedTaxRateBracket`

### 메타데이터 자동화 적용 여부

- 4 조건 섹션(BlockPalette / ConditionEditorPanel)은 기존 `GET /api/conditions` 메타데이터 자동 생성 패턴 유지.
- 6 비조건 섹션은 schema 자체가 02번에 명시된 fixed shape이라 직접 폼 작성. 단, 옵션 카탈로그(POSITION_SIZING_METHODS 등)를 `strategySections.ts`에 export하여 향후 schema 변경 시 단일 출처로 관리.

### 차트 UX 원칙 적용 여부

본 step은 차트 영역 미터치. 차트 UX 원칙 적용은 다음 step(BacktestResult 영역) 책임.

### 02번/01번 문서 갱신 필요 여부

- 02번 schema 정책은 변경 없음 — frontend가 정책에 맞춰 정합화한 것이라 문서 갱신 불필요.
- 01번 GUI 설계서 §10(검증 규칙)와 §3(레이아웃)에 6섹션 통합 패턴(StrategyConfigPanel 탭) 반영을 옵션으로 고려 — 본 step에서는 미수정 (범위 외).

## Follow-ups

- **다음 step (030) 인계 — StrategyHeader / 백테스트 실행 데이터**:
  1. **StrategyDraft 확장 형식**: `serializeDraft(draft)` 출력이 02번 schema 그대로 (6섹션 enabled=true인 것만 포함). StrategyHeader의 "JSON 보기" / "백테스트 실행" 버튼은 `serializeDraft(draft)` 결과를 그대로 백엔드에 보내면 됨. `StrategyCreatePayload.strategy_json`에 `{ name 제외, 나머지 모두 }` 분리 패턴(`StrategyBuilderPage.tsx:38` 기존 코드)을 그대로 적용 가능.
  2. **StrategyConfigPanel 통합 위치**: `StrategyCanvas.tsx` 내부, 4 조건 섹션 아래에 배치됨. **template 적용 시 reset 액션**은 메인 reducer(`draftReducer`)에 새 액션(`APPLY_TEMPLATE`)을 추가하여 6섹션을 한 번에 set하는 방식 권장. 현재 `RESET` 액션은 기본값으로 초기화하므로 템플릿용으로 부적합 — 새로 정의 필요.
- 백엔드 에러 envelope 한국어 매핑 — `INVALID_STRATEGY_JSON`, `EXIT_POSITION_IN_EXIT_SIGNAL`, `EXIT_SIGNAL_IN_EXIT_POSITION`, `INVALID_OPERATOR`, `INVALID_PARAMETER_VALUE`, `MISSING_REQUIRED_PARAMETER`, `UNKNOWN_CONDITION_TYPE` (10.7.1) → StrategyValidationPanel 또는 새 ServerErrorPanel.
- GROUP 토글 UI — `SET_LOGIC` select에 GROUP 옵션 추가 + GROUP 모드 시 그룹 추가/그룹 내 조건 추가/그룹 logic 토글 UI. (현재 reducer는 지원, UI만 미노출.)
- 클라이언트 검증 확장 — `validateDraft`가 6섹션 enabled 시 정합성을 검사하도록 (예: priority.random + metadata.random_seed 미입력 → warning).
- StrategyConfigPanel 디자인 폴리싱 — 현재 inline style. design-review 통과 후 향후 일괄 토큰화.

## 메인 세션 마무리 체크

- [ ] status를 completed로 변경
- [ ] 작업로그/README.md 갱신
- [ ] PM 호출 → 로드맵.md 갱신 (01-h, 01-i, 02-f·g·h·i·j·k [x] / Phase 12 step 029 ✅)
- [ ] git commit (Phase 12 마지막 step 아니므로 push 보류)

## 메인 세션 마무리 체크

- [ ] status를 completed로 변경
- [ ] 작업로그/README.md 갱신
- [ ] PM 호출 → 로드맵.md 갱신 (01-h, 01-i, 02-f·g·h·i·j·k [x] / Phase 12 step 029 ✅)
- [ ] git commit (Phase 12 마지막 step 아니므로 push 보류)
