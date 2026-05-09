---
date: 2026-05-10
agent: main
phase: 3
status: completed
related_docs:
  - 상세설계/01_strategy_builder_gui_design.md
---

# Phase 3 / Step 6 — StrategyPreviewPanel + StrategyValidationPanel

## Plan / Execution

- [x] utils/buildPreviewText.ts: 섹션 헤더 + AND/OR 라벨 + 문장 list
- [x] utils/validateDraft.ts: ENTRY_REQUIRED / EXIT_MISSING / NO_STOP_LOSS / NO_LIQUIDITY_FILTER + hasErrors
- [x] StrategyPreviewPanel.tsx
- [x] StrategyValidationPanel.tsx (오류 빨강 / 경고 주황 / 모두 통과 시 ✓)
- [x] StrategyBuilderPage: 우측 column 3-row grid 분할
- [x] ConditionEditorPanel.borderLeft 제거 (중복 회피)
- [x] 테스트 10건 신규: validateDraft (5) + buildPreviewText (3) + 통합 (2)

## Tests

```text
frontend vitest: 33 passed (이전 23 + 신규 10)
backend pytest: 영향 없음
```

## Result / Follow-ups

- 다음: Step 7 (Phase 3 마지막) — 전략 저장 (POST /api/strategies + 프론트 연동) → Phase 3 push
