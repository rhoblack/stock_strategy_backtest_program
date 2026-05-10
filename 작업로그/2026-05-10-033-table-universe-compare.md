---
date: 2026-05-10
agent: frontend-developer
phase: 12
status: completed
roadmap_step: 033
roadmap_impact:
  - 08-m  # 거래 클릭 시 차트 visible range 이동 + TanStack Table
  - 11-f  # components/layout / components/ui 분리
  - 11-g  # hooks/ / utils/
  - 11-h  # features/universe-selector
related_docs:
  - 상세설계/08_backtest_result_chart_design.md
  - 상세설계/11_frontend_architecture_design.md
  - 작업로그/2026-05-10-031-chart-data-from-daily-prices.md
  - 작업로그/2026-05-10-032-result-page-tabs-and-charts.md
---

# Step 033 — TanStack Table + UniverseSelector + Compare (Phase 12 마지막)

032에서 6 탭 + 5 차트 도입. 본 step에서:
1. TanStack Table 도입 (거래 탭) + 거래 클릭 → 차트 visible range 이동
2. UniverseSelector UI feature
3. StrategyComparePage 골격
4. components/layout, ui, hooks, utils 디렉토리 정합화

## Plan

### A) TanStack Table — 거래 탭 (08-m)
- [ ] `frontend/src/features/backtest-result/components/TradesTable.tsx` 신규 (TanStack Table 활용)
- 정렬 / 필터 / 페이징
- 행 클릭 → setSelectedSymbol(tg.symbol) + setActiveTab("summary") + 차트 visible range 이동
- 컬럼: trade_group_id / symbol / entry_date / exit_date / entry_price / exit_price / quantity / realized_profit / realized_profit_rate

### B) 거래 클릭 → 차트 이동 (08-m)
- [ ] BacktestResultPage에 selectedTradeGroup state 추가
- [ ] CandleTradeChart에 visibleRange prop 추가 (lightweight-charts timeScale().setVisibleRange)
- 행 클릭 → 해당 trade_group의 entry_date ~ exit_date로 zoom

### C) UniverseSelector UI (11-h)
- [ ] `frontend/src/features/universe-selector/UniverseSelector.tsx` 신규
- 019 백엔드 UniverseSelector config UI:
  - 시장 선택 (KOSPI/KOSDAQ)
  - 06번 §8 공통 필터 토글 (exclude_etf 등)
  - min_market_cap / min_avg_trading_value 입력
  - selection_method 선택
- BacktestRunPage에 통합 (synthetic 입력 대체)
- 시장데이터 API가 없으면 placeholder + 직접 종목 입력 fallback

### D) StrategyComparePage (11-h, 부분)
- [ ] `frontend/src/pages/StrategyComparePage.tsx` 신규 (골격)
- 라우팅 placeholder
- 본격적 비교 기능은 후속 — 본 step에서는 skeleton

### E) components/layout / ui / hooks / utils 정합화 (11-f, 11-g)
- [ ] `frontend/src/components/layout/` 신규 (PageHeader 등 공통 추출)
- [ ] `frontend/src/components/ui/` 신규 (Button / Input / Card / Tabs 공통)
- [ ] `frontend/src/hooks/` 신규 (useChartData 등 이미 있는 것은 그대로)
- [ ] `frontend/src/utils/` 신규 (formatDate / formatCurrency 등)
- 본 step에서는 디렉토리 신설 + 1~2개 컴포넌트 추출 (전면 리팩터는 후속)

### F) 테스트
- [ ] TradesTable 단위 테스트 (정렬/필터/행 클릭)
- [ ] UniverseSelector 단위 테스트
- [ ] StrategyComparePage 라우팅 테스트
- [ ] 거래 클릭 → 차트 이동 통합 테스트

### G) 회귀
- [ ] vitest + npm run build

### 절대 금지
- 백엔드 절대 수정 (UniverseSelector는 019 백엔드 활용만)
- 029/030/032 산출물 시그니처 변경
- 결정론 깨기

### Phase 12 완료 흐름 (033 마무리 후)
1. PM 호출 → 로드맵 갱신 (08-m, 11-f·g·h [x] / Phase 12 step 033 ✅)
2. **test-engineer 호출 "Phase 12 완료 검증"**
3. ship-go 시: PM "Phase 12 완료" → 진행률 추이 + Phase 13 ⏭ → push

## Execution

### A) TanStack Table — 거래 탭 (08-m)
- 신규: `frontend/src/features/backtest-result/components/TradesTable.tsx:1`
  - TanStack Table v8.21.3 (`npm i @tanstack/react-table`로 신규 설치)
  - 컬럼 9개: 종목 / 매수일 / 청산일 / 매수가 / 청산가 / 수량 / 실현 손익 / 수익률 / 매도 사유
  - 정렬: 모든 컬럼 sortable, 기본 `entry_date ASC` (CLAUDE.md #8 결정론)
  - 필터: `globalFilter` (종목/사유 등 전체 컬럼 includesString)
  - 페이지네이션: 기본 25, 옵션 10/25/50/100
  - 행 클릭: `onRowClick({ tradeGroup, entryDate, exitDate })` 콜백
  - 보유 중(매도 execution 없음) 행은 `청산일="보유 중"`, `exitDate=null`
  - 수익률 색상: 양수=#dc2626(빨강), 음수=#1d4ed8(파랑)

### B) 거래 클릭 → 차트 이동 (08-m)
- 수정: `frontend/src/features/backtest-result/components/CandleTradeChart.tsx:13`
  - `VisibleRange` 타입 export + `visibleRange?: VisibleRange | null` prop 추가
  - useEffect로 `chart.timeScale().setVisibleRange({from, to})` 호출
  - `to`가 null이면 마지막 봉 시간 사용 (보유 중 거래)
  - try/catch로 lightweight-charts 매칭 실패 시 fitContent로 fallback
- 수정: `frontend/src/pages/BacktestResultPage.tsx:48`
  - `tradeRange` state 추가 (VisibleRange | null)
  - `handleTradeRowClick(info)`: setSelectedSymbol + setActiveTab("summary") + setTradeRange
  - `handleSymbolChange`: 사용자 직접 종목 변경 시 tradeRange 해제 (전체 봉 보기)
  - `SummarySection`에 `visibleRange` prop 전파 → CandleTradeChart에 전달
  - 기존 inline TradesSection을 TradesTable로 교체 (동일 시그니처 유지)

### C) UniverseSelector UI (11-h)
- 신규: `frontend/src/features/universe-selector/UniverseSelector.tsx:1`
  - 019 백엔드 config schema 그대로 (DEFAULT_EXCLUDE_FLAGS / SUPPORTED_SELECTION_METHODS)
  - 시장 (KOSPI/KOSDAQ) + 6 공통 필터 토글 + min_market_cap/min_avg_trading_value
  - selection_method: ALL / MARKET_CAP_TOP_N / LIQUIDITY_TOP_N / MANUAL
  - MANUAL fallback: textarea로 종목 코드 직접 입력 (쉼표/공백 분리)
  - preview placeholder: "유니버스 미리보기 API는 후속 step에서 추가됩니다"
- 수정: `frontend/src/pages/BacktestRunPage.tsx`
  - `useSynthetic` 토글 + `universeConfig` state 추가
  - `universe-mode` selector ("합성 데이터 (dev)" / "실제 시장 (UniverseSelector)")
  - `universeConfigToPayload(cfg)` 헬퍼: null/빈값 키 생략, MANUAL은 symbols 전달
  - 백엔드 절대 미수정 (019 활용만)

### D) StrategyComparePage 골격 (11-h 부분)
- 신규: `frontend/src/pages/StrategyComparePage.tsx:1`
  - 두 selector(전략 A / 전략 B) + skeleton 비교 placeholder
  - "비교 기능 준비 중" 메시지 (서로 다른 전략 2개 선택 시)
- 수정: `frontend/src/app/router.tsx`
  - `/strategies/compare` 라우트 추가
  - 라우트 순서: `/strategies/compare`를 `:id`보다 위로 (매칭 우선순위)
- 수정: `frontend/src/pages/StrategyListPage.tsx`
  - 헤더에 "전략 비교" 링크 추가

### E) components/layout · ui · hooks · utils 정합화 (11-f, 11-g)
- 신규 디렉토리: `frontend/src/components/layout/`, `components/ui/`, `hooks/`, `utils/`
- 신규: `frontend/src/utils/formatters.ts:1` — formatKrw / formatInt / formatPct / formatSignedPct / formatDate
  (TradesTable이 즉시 사용; 다른 페이지는 후속 마이그레이션)
- 신규: `frontend/src/components/ui/Card.tsx:1` — 정의만 (호출부 마이그레이션은 후속)
- 신규: `frontend/src/components/layout/PageHeader.tsx:1` — 정의만
- 신규: `frontend/src/hooks/.gitkeep` — 디렉토리 존재 표시 + 마이그레이션 가이드
- 전면 리팩터 금지 정책 준수: 1~2개 컴포넌트만 추출

### F) 테스트
- 신규: `frontend/src/features/backtest-result/components/TradesTable.test.tsx` (9 tests)
- 신규: `frontend/src/features/universe-selector/UniverseSelector.test.tsx` (10 tests)
- 신규: `frontend/src/pages/StrategyComparePage.test.tsx` (4 tests)
- 신규: `frontend/src/pages/BacktestResultPage.tradeClick.test.tsx` (3 tests, 통합)
- 신규: `frontend/src/utils/formatters.test.ts` (5 tests)
- 합계 신규: 31 tests

## Tests

```text
$ npm test -- --reporter=basic
Test Files  25 passed (25)
     Tests  162 passed (162)   # baseline 131 → +31
   Duration 4.99s

$ npm run build
✓ 189 modules transformed.
dist/index.html                  0.38 kB │ gzip:   0.30 kB
dist/assets/index-B6_nRkqC.js  590.36 kB │ gzip: 185.98 kB
✓ built in 1.43s
```

회귀 0건. 기존 BacktestResultPage.test.tsx (8 tests)도 모두 통과 — 거래 탭 기존 검증
(`getByText("GOLDEN")`, `getByText("take_profit")`)이 새 TradesTable 셀에서도 매칭됨.

## Issues

- universe preview API 미구현 — UniverseSelector UI는 placeholder 메시지로 표시.
  실제 종목 결과 미리보기는 후속 step에서 백엔드 API와 함께 추가 필요.
- StrategyComparePage는 골격 (skeleton)만 — 실제 백테스트 결과 비교 차트/표는 후속.
- components/ui/Card, components/layout/PageHeader는 정의만 추가; 기존 페이지 호출부
  마이그레이션은 후속 step에서 점진적으로 진행 (전면 리팩터 금지 정책 준수).
- vite build에서 chunk 590kB 경고 — TanStack Table 추가로 늘어남. code-split은 후속.
- React Router future flag 경고는 기존 baseline에서 이미 있던 것으로 본 step과 무관.

## Result

- TanStack Table v8 도입 완료 — 정렬/필터/페이지네이션 기본 동작 확보
- 거래 클릭 → 차트 이동 흐름 완성:
  1. 거래 탭에서 행 클릭
  2. setSelectedSymbol(tg.symbol) → chart-data 재페치 (해당 종목)
  3. setActiveTab("summary") → 요약 탭으로 자동 전환
  4. setTradeRange({from: entry_date, to: exit_date}) → CandleTradeChart가 setVisibleRange로 줌
  5. 사용자가 종목 셀렉터로 다른 종목 선택 시 tradeRange 자동 해제
- UniverseSelector UI: 019 백엔드 config schema 그대로 + MANUAL fallback 제공
- StrategyComparePage 골격 + 라우팅 (`/strategies/compare`) + StrategyListPage 진입점
- frontend/ 디렉토리 구조 11번 문서 정합화: layout / ui / hooks / utils 신설
- 차트 UX 원칙(08번 §7) 유지: 마커만 / 수익률 라벨 X / 툴팁 기본
- 결정론 유지: TradesTable 기본 정렬 entry_date ASC, 동일 entry_date면 React 키(trade_group_id) 순서

새 TypeScript 타입:
- `TradesTable.TradeRowClickInfo`
- `CandleTradeChart.VisibleRange`
- `UniverseSelector.UniverseConfig` + `DEFAULT_UNIVERSE_CONFIG`

## Follow-ups

- universe preview API (백엔드) — 시장 + 필터 + selection_method를 받아 종목 리스트 반환
  → UniverseSelector에 종목 미리보기 표시
- StrategyCompare 본격 구현: 전략별 최신 백테스트 결과 fetch → summary/equity 차트 비교
- components/ui/Card, layout/PageHeader 점진적 마이그레이션 (BacktestResultPage 내부 Card,
  각 페이지 헤더)
- 거래 탭 컬럼 가시성 토글 (column visibility), CSV 다운로드 (TanStack Table util 활용)
- TradesTable 페이지 크기 사용자 영구 저장 (localStorage)
- vite build chunk split (lightweight-charts / TanStack 분리)

## 메인 세션 마무리 체크
- [ ] status를 completed로 변경
- [ ] 작업로그/README.md 갱신 (Phase 12 ✅ 완료 표기)
- [ ] PM 호출 → 로드맵.md 갱신 (08-m, 11-f·g·h [x] / Phase 12 step 033 ✅)
- [ ] **test-engineer 호출 → "Phase 12 완료 검증"**
- [ ] ship-go 시: PM "Phase 12 완료" → 진행률 추이 + Phase 13 ⏭
- [ ] git commit
- [ ] **Phase 12 마지막 step**: ship-go 받으면 `git push origin main`
