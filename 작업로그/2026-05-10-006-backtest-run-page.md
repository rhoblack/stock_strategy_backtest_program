---
date: 2026-05-10
agent: main
phase: 4
status: completed
related_docs:
  - 상세설계/11_frontend_architecture_design.md
  - 상세설계/10_api_design.md
---

# Phase 4 / Step 2 — BacktestRunPage + BacktestResultPage + StrategyListPage

## Plan / Execution

- [x] api/backtests.ts: useCreateBacktest / useBacktestStatus(자동 폴링) / useBacktestSummary / useBacktestTrades / useDailyEquity
- [x] pages/BacktestRunPage.tsx: 전략 셀렉트 + 폼 + 실행 → /backtests/:id
- [x] pages/BacktestResultPage.tsx: status 폴링 + 요약 8개 카드 + 거래 내역 표 + 일별 자산 요약
- [x] pages/StrategyListPage.tsx: useStrategies 실데이터 + 백테스트 실행 링크
- [x] router: /backtests/new + /backtests/:runId
- [x] 테스트 4건: BacktestRunPage (3) + BacktestResultPage (1)

## Tests

```text
frontend vitest: 43 passed (이전 39 + 신규 4)
frontend build: 314KB / 103KB gzip
```

## Result

- end-to-end: 빌더 → 저장 → 목록 → 백테스트 실행 → 진행률 → 요약/거래내역
- Phase 4 완료 (Phase 5는 차트로 별도)
