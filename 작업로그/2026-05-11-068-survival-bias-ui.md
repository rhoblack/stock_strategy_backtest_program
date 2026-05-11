---
date: 2026-05-11
agent: frontend-developer
phase: 22
status: completed
roadmap_step: "068"
roadmap_impact:
  - 06-l
related_docs:
  - 상세설계/06_market_data_universe_design.md
---

# step 068: 생존편향 영향 분석 UI (06-l)

## Plan

- [x] SurvivalBiasPanel.tsx 컴포넌트 생성 (설계서 §11.2 명세)
- [x] SurvivalBiasPanel.test.tsx 테스트 작성 (8건)
- [x] BacktestResultPage.tsx 요약 탭에 SurvivalBiasPanel 통합
- [x] trades 데이터에서 delisting/delisting_estimated 건수 집계 (survivalBiasInfo useMemo)
- [x] vitest 전체 회귀 통과 확인

## Execution

```text
frontend/src/features/backtest-result/components/SurvivalBiasPanel.tsx  (신규)
  - props: delistingCount, estimatedCount, newListingCount
  - 상장폐지 강제매도 건수 표시
  - estimatedCount > 0이면 경고 문구 (종가×0.5 적용 안내)
  - newListingCount null이면 신규 상장 항목 미표시
  - delistingCount=0 + newListingCount=0이면 "영향 없음" 메시지

frontend/src/features/backtest-result/components/SurvivalBiasPanel.test.tsx  (신규)
  - 8건 테스트: aria-label 렌더 / 상장폐지 건수 / 신규 상장 / null 미표시 /
    경고 문구 / 경고 없음 / 영향없음 / estimatedCount 건수 표시

frontend/src/pages/BacktestResultPage.tsx  (수정)
  - SurvivalBiasPanel import 추가
  - survivalBiasInfo useMemo: trades.executions에서 delisting/delisting_estimated 집계
  - SummarySection props에 survivalBias 추가
  - SummarySection 내 요약 카드 아래 SurvivalBiasPanel 렌더
```

## Tests

```text
vitest run (frontend)
  SurvivalBiasPanel.test.tsx: 8/8 PASS (신규)
  전체: 266 passed / 0 failed (33 test files)
```

## Issues

없음.

## Result

```text
- 추가/수정 파일:
  frontend/src/features/backtest-result/components/SurvivalBiasPanel.tsx (신규)
  frontend/src/features/backtest-result/components/SurvivalBiasPanel.test.tsx (신규)
  frontend/src/pages/BacktestResultPage.tsx (수정)
- 06-l 체크박스 해소 (생존편향 영향 분석 UI)
- 설계서 06번 §11.2 명세 구현: 상장폐지 건수 + 경고 문구 표시
- vitest 266 PASS / 0 FAIL
```

## Follow-ups

```text
- 신규 상장 건수(newListingCount)는 현재 API에서 제공하지 않아 null 전달 (미표시)
  향후 backend summary API에 new_listing_count 필드 추가 시 연동 가능
- 실 delisting API 데이터와 연동 후 통합 테스트 추가 권장
```
