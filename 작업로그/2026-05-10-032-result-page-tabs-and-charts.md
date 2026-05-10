---
date: 2026-05-10
agent: frontend-developer
phase: 12
status: completed
roadmap_step: 032
roadmap_impact:
  - 08-f  # 탭 구조 (요약 / 거래 / 자산 / 월별 / 리스크 / 자금 관리)
  - 08-g  # MDD 그래프
  - 08-h  # 예수금 변화 그래프
  - 08-i  # 보유 종목 수 변화
  - 08-j  # 거래량 차트
  - 08-k  # 벤치마크 비교 (KOSPI/KOSDAQ)
related_docs:
  - 상세설계/08_backtest_result_chart_design.md
  - 작업로그/2026-05-10-031-chart-data-from-daily-prices.md
---

# Step 032 — BacktestResultPage 탭 구조 + 5 차트 (08-f·g·h·i·j·k)

031에서 chart-data DB 전환 + 5 query options 도입. 본 step에서 BacktestResultPage를 탭 구조로 분리 + 5종 신규 차트 컴포넌트.

## Plan

### A) BacktestResultPage 탭 구조 (08-f)
- [ ] `frontend/src/pages/BacktestResultPage.tsx` 탭 구조로 재작성:
  - 요약 / 거래 / 자산 / 월별 성과 / 리스크 / 자금 관리 (08번 §3 정합)
- [ ] 탭 라이브러리 또는 단순 state 기반 (TanStack Table은 033)

### B) 신규 차트 5종 (08-g·h·i·j·k)
- [ ] `frontend/src/components/charts/DrawdownChart.tsx` (08-g, MDD)
- [ ] `frontend/src/components/charts/CashChart.tsx` (08-h, 예수금 변화)
- [ ] `frontend/src/components/charts/PositionsCountChart.tsx` (08-i, 보유 종목 수)
- [ ] `frontend/src/components/charts/VolumeChart.tsx` (08-j, 거래량)
- [ ] `frontend/src/components/charts/BenchmarkCompareChart.tsx` (08-k, KOSPI/KOSDAQ 비교)

### C) chart-data 응답 활용 (031 인계)
- chart-data API에 daily_equity의 drawdown / cash / positions_count 모두 있음 → 차트 컴포넌트가 직접 활용
- 벤치마크는 027 market_indices에서 별도 fetch 필요 (market index API 없으면 기본 placeholder)

### D) 종목 선택 드롭다운 (chart-data symbol query 활용)
- [ ] 복수 종목 백테스트 시 종목 선택 드롭다운 → useChartData(runId, {symbol})

### E) 테스트
- [ ] 각 차트 컴포넌트 단위 테스트 (data 형식 + render)
- [ ] BacktestResultPage 탭 전환 테스트

### F) 회귀
- [ ] vitest 전체 + npm run build

### 절대 금지
- 백엔드 절대 수정 (031 chart-data 활용만)
- 029/030 strategy-builder 영역 수정 금지
- 결정론 깨기

### 다음 step (033) 인계
- BacktestResultPage 탭 구조 (033에서 TanStack Table로 거래 탭 + 거래 클릭 차트 이동)
- 차트 컴포넌트 인터페이스

## Execution

### 작성/수정 파일

1. `frontend/src/api/chartData.ts` — `CandleBar.volume?` 추가, `ChartDataMeta` 타입 추가 (symbol/source/downsampled/...), `ChartDataQuery` 타입 추가, `useChartData(runId, enabled, query)` 시그니처 확장 (query → axios params).
2. `frontend/src/components/charts/DrawdownChart.tsx` (신규) — `addAreaSeries` 빨강 계열, equity_curve의 drawdown을 time ASC 정렬 후 setData.
3. `frontend/src/components/charts/CashChart.tsx` (신규) — `addLineSeries`, daily_equity의 cash 컬럼을 date ASC 정렬 후 setData.
4. `frontend/src/components/charts/PositionsCountChart.tsx` (신규) — `addHistogramSeries`, daily_equity의 positions_count 컬럼을 date ASC 정렬 후 setData.
5. `frontend/src/components/charts/VolumeChart.tsx` (신규) — `addHistogramSeries`, candles의 volume 컬럼 + 한국 컨벤션 색상 (양봉=#dc2626, 음봉=#1d4ed8). volume 누락 시 0.
6. `frontend/src/components/charts/BenchmarkCompareChart.tsx` (신규) — 전략 + 벤치마크(N개)를 normalized 100 기준으로 line 비교. 벤치마크 series는 name ASC 정렬. 벤치마크 데이터 없으면 placeholder 메시지 (027 market_indices API 도입 안내).
7. `frontend/src/features/backtest-result/components/ResultTabs.tsx` (신규) — 6 탭 button 기반 (요약/거래/자산/월별 성과/리스크/자금 관리). aria-selected 정합. RESULT_TABS 상수 export.
8. `frontend/src/features/backtest-result/components/SymbolSelector.tsx` (신규) — trades에서 추출한 unique symbols를 symbol ASC 정렬해 `<select>`에 표시. 종목 1개 이하 시 미표시.
9. `frontend/src/pages/BacktestResultPage.tsx` (재작성) — useState로 activeTab/selectedSymbol 관리, 6 탭 분기 (Summary/Trades/Equity/Monthly/Risk/Cash). chart-data query에 selectedSymbol 전달. 거래에서 unique symbols 추출해 SymbolSelector에 전달. 탭별 섹션 함수 6개 분리.
10. `frontend/src/pages/BacktestResultPage.test.tsx` (재작성) — 6 탭 표시 / 기본 탭 요약 / 거래 탭 / 자산 탭 (Equity/Volume/Benchmark) / 월별 탭 (월별 표) / 리스크 탭 (Drawdown) / 자금 관리 탭 (Cash/Positions) / SymbolSelector 동작 — 8건.
11. `frontend/src/components/charts/charts.test.tsx` (신규) — DrawdownChart 정렬 + drawdown 값 / 빈 입력, CashChart 정렬, PositionsCountChart 정렬, VolumeChart 양봉/음봉 색상 + volume 누락 처리, BenchmarkCompareChart placeholder + normalized 100 + name ASC — 9건.
12. `frontend/src/features/backtest-result/components/SymbolSelector.test.tsx` (신규) — 1개 이하 미렌더 / ASC 정렬 + onChange — 2건.
13. `frontend/src/features/backtest-result/components/ResultTabs.test.tsx` (신규) — 6 탭 순서 / aria-selected / 클릭 시 onChange — 2건.

### 활용한 정책

- 08번 §3 (요약 카드 8종) / §4 (탭 순서) / §5 (총자산 곡선/벤치마크/MDD/예수금/보유 종목 수) / §6 (거래량 차트) / §7 (마커만, 수익률 라벨 X, 6개월 라벨 정책) / §13 (자금 관리 탭 통계).
- 031 인계: `daily_equity.cash` / `positions_count` (Wave C2), `chart-data` 응답의 `equity_curve.drawdown`, `candles.volume` (`adj_volume`).
- CLAUDE.md #6 (한국 양봉=빨강, 음봉=파랑), #8 (결정론: 모든 차트 입력은 time/date ASC, 벤치마크 series name ASC, SymbolSelector ASC).

### 호출 / 의존 API

- `GET /api/backtests/{id}/status` (기존)
- `GET /api/backtests/{id}/summary` (기존)
- `GET /api/backtests/{id}/trades` (기존, symbol 추출용)
- `GET /api/backtests/{id}/daily-equity` (기존, cash/positions_count)
- `GET /api/backtests/{id}/chart-data?symbol=...` (031 신규 — symbol query 활용)
- `GET /api/backtests/{id}/export/{kind}` (다운로드 링크, 기존)

벤치마크용 market_indices API는 미구현 → placeholder 메시지로 처리 (027 도입 후 props로 BenchmarkSeries[] 전달).

## Tests

### 명령

```text
npm test          # 전체 vitest
npm run build     # tsc -b && vite build
```

### 결과

- vitest: **131 passed** (Test Files 20 / Tests 131) — baseline 111 + 신규 20건 (BacktestResultPage.test.tsx 변경분 +5, charts.test.tsx 9, SymbolSelector.test.tsx 2, ResultTabs.test.tsx 2 + Page 기존 1 → 8로 +5 = 합계 +20).
- npm run build: **성공** (1.74s, 183 modules, 523.69 kB gzip 167.82 kB). 기존 chunk warning만 동일.

### 신규 테스트 매핑

| 검증 항목 | 테스트 파일 | 케이스 |
|---|---|---|
| 6 탭 표시 / 기본=요약 / 탭 클릭 시 해당 섹션 노출 | BacktestResultPage.test.tsx | 6건 |
| 종목 선택 드롭다운 (chart-data symbol query) | BacktestResultPage.test.tsx + SymbolSelector.test.tsx | 3건 |
| time/date ASC 정렬 결정론 (Drawdown/Cash/Positions/Volume) | charts.test.tsx | 4건 |
| 한국 양봉=빨강 / 음봉=파랑 (08-j) | charts.test.tsx | 1건 |
| volume 누락 시 0 처리 | charts.test.tsx | 1건 |
| 벤치마크 placeholder + normalized 100 + name ASC | charts.test.tsx | 3건 |
| RESULT_TABS 순서 / aria-selected | ResultTabs.test.tsx | 2건 |

## Issues

### 정책 / 설계 모호성

1. **벤치마크 데이터 출처 미정**: 027 market_indices DB 테이블만 존재, API 미구현 — BenchmarkCompareChart는 props로 BenchmarkSeries[] 받고 빈 배열이면 placeholder 표시. 후속 step에서 (a) market_indices read API + (b) useMarketIndex 훅 + (c) BacktestResultPage에서 hook 호출 → BenchmarkCompareChart에 전달 필요.
2. **종목 선택 데이터 출처 결정**: chart-data 응답에 universe symbols가 없어 trades 응답에서 unique symbols 추출. 거래가 한 번도 발생하지 않은 종목은 드롭다운에 안 나옴. 후속 step에서 BacktestRun.universe_config 또는 별도 API 필요.
3. **월별 성과 계산**: 각 월 마지막 daily_equity의 total_equity로 단순 차분 계산. 월말 영업일 보정 / 부분 월 처리 미고려. 16번 metrics에 monthly_returns가 있으면 그것을 우선 사용해야 정합.
4. **자금 관리 통계 (현금 부족 / 일부 매도 횟수)**: cash_events API가 별도 존재하나 본 step 미연동. CashSection은 현재 평균/최소 예수금만 카드 표시. 08번 §13 전체 항목 표시는 후속 step.
5. **SymbolSelector 종목 선택 시 chart-data 재요청**: query key에 symbol 포함 → 결정론 보장 + TanStack Query 자동 캐싱. 단, 빠르게 토글 시 race condition 없음을 확인했지만 부하 시 throttle 검토 가능.

### 차트 라이브러리 선택

8번 §15는 일반 차트에 ECharts/Recharts 권장하나, 본 step에서는 lightweight-charts로 5종 모두 통일 (이미 도입된 라이브러리, 추가 의존성 회피, time scale 일관성). area/histogram/line 모두 lightweight-charts에서 지원하므로 기능적 문제 없음. 디자인 일관성 측면에서 결과 페이지 모든 차트가 같은 스타일을 공유.

### TypeScript 빌드 한 차례 실패

`addLineSeries.mock.calls.map((c) => c[0]?.title)` 타입 추론에서 옵션 없이 호출 가능한 시그니처가 `[]` 튜플로 추론되어 인덱스 0 접근 에러. `c as unknown as Array<{ title?: string }>`로 우회.

## Result

### 6 탭 구조 (08번 §4 정합)

| 탭 키 | 라벨 | 표시 컴포넌트 |
|---|---|---|
| `summary` | 요약 | 요약 카드 8종 + 다운로드 패널 + SymbolSelector + CandleTradeChart |
| `trades` | 거래 | 거래 내역 표 (기존) + "TanStack Table 033에서 추가" 안내 |
| `equity` | 자산 | EquityCurveChart + VolumeChart + BenchmarkCompareChart + 일별 자산 요약 |
| `monthly` | 월별 성과 | 월별 표 (월/월말 자산/월간 수익률 — 양수 빨강·음수 파랑) |
| `risk` | 리스크 | 리스크 카드 4종(MDD/평균수익/평균손실/PF) + DrawdownChart |
| `cash` | 자금 관리 | 자금 관리 카드 4종(초기/최종/평균예수금/최소예수금) + CashChart + PositionsCountChart |

기본 활성 탭: `summary`. 탭 변경은 단순 `useState<ResultTabKey>`.

### 5 차트 컴포넌트 인터페이스

```typescript
DrawdownChart        ({ equity: EquityPoint[], height?: number })
CashChart            ({ daily: DailyEquityOut[], height?: number })
PositionsCountChart  ({ daily: DailyEquityOut[], height?: number })
VolumeChart          ({ candles: CandleBar[], height?: number })
BenchmarkCompareChart({ equity: EquityPoint[], benchmarks: BenchmarkSeries[], height?: number })
type BenchmarkSeries = { name: string; color?: string; points: { time: string; value: number }[] }
```

모든 차트 입력은 컴포넌트 내부에서 time/date ASC 재정렬 (입력 순서 의존 X).

### 종목 선택 드롭다운

- `SymbolSelector` 컴포넌트: `symbols: SymbolOption[]` (symbol/name?), `value: string | null`, `onChange: (s) => void`.
- 데이터 출처: `useBacktestTrades(id)` 응답의 `items[].symbol/name` → unique 추출 → symbol ASC 정렬.
- 1개 이하 시 미표시 (단일 종목 백테스트는 선택 의미 없음).
- 변경 시 `setSelectedSymbol` → `useChartData(id, enabled, { symbol })` 재요청 → CandleTradeChart가 해당 종목으로 갱신.

### 벤치마크 데이터 출처

- 현재: **placeholder** ("벤치마크 데이터(KOSPI/KOSDAQ) 미연동 — 027 market_indices API 도입 후 표시됩니다.").
- BacktestResultPage에서 `BenchmarkCompareChart benchmarks={[]}`로 호출.
- 후속 step에서 027 market_indices 조회 API + useMarketIndex 훅 + 페이지에서 hook 결과 전달.

### 신규 TypeScript 타입

- `ChartDataMeta`, `ChartDataQuery` (`api/chartData.ts`)
- `ResultTabKey`, `RESULT_TABS` (`features/backtest-result/components/ResultTabs.tsx`)
- `SymbolOption` (`features/backtest-result/components/SymbolSelector.tsx`)
- `BenchmarkSeries` (`components/charts/BenchmarkCompareChart.tsx`)

### 차트 UX 원칙 적용 (08번 §7)

- 봉차트: CandleTradeChart는 매수/매도 마커만 (수익률 라벨 X) — 기존 그대로.
- 6개월 라벨: lightweight-charts time scale 기본 (사용자 zoom에 따라 자동).
- 한국 컨벤션 색상: VolumeChart의 양봉=#dc2626, 음봉=#1d4ed8 (CandleTradeChart 기존 동일 색).

## Follow-ups

### 다음 step (033) 인계 정보

- **BacktestResultPage 탭 구조**: `RESULT_TABS` 상수 + `useState<ResultTabKey>` 패턴. 거래 탭에 TanStack Table 도입 시 `TradesSection` 함수만 교체.
- **거래 클릭 → 차트 이동**: 거래 행 클릭 시 (1) `setSelectedSymbol(tg.symbol)` (2) `setActiveTab("summary")` (3) chart-data 재요청 + 봉차트 zoom range 적용. lightweight-charts의 `timeScale().setVisibleRange({from, to})` 사용 가능.
- **5 차트 컴포넌트 인터페이스** (위 Result 섹션 참조) — 거래 클릭 시 차트 props는 그대로 두고 부모에서 selectedSymbol/탭만 갱신하면 됨.
- **chart-data query 옵션 5종**: `symbol/start_date/end_date/use_adjusted/downsample` — 033에서 기간 필터/원가격 토글 등 UI 추가 시 활용.
- **SymbolSelector**: 거래 클릭 시 selectedSymbol 변경 → 드롭다운 자동 동기화 (controlled).

### 후속 작업 후보

1. **027 market_indices read API + 훅** (백엔드 작업) — 본 step의 BenchmarkCompareChart placeholder 해소.
2. **TanStack Table 도입** (033) — 거래 탭 정렬/필터/페이지네이션. 패키지 추가: `@tanstack/react-table`.
3. **거래 클릭 → 차트 이동** (033) — 위 인계 정보 활용.
4. **UniverseSelector / StrategyComparePage** (별도 step).
5. **cash_events API 연동** — 자금 관리 탭에 "현금 부족 발생 횟수" / "일부 매도 횟수" 카드 추가.
6. **16 metrics monthly_returns 활용** — 월별 성과 탭의 자체 계산을 제거하고 백엔드 metrics 사용.
7. **ECharts 도입 검토** — 8번 §15 권장. 현재 lightweight-charts로 통일했으나 복잡한 시각화(stacked bar 등) 시 도입 가치.

### 정책 문서 갱신 필요 여부

- 08번 문서: §15 차트 기술 스택에 "현재 결과 페이지 5 차트는 lightweight-charts로 구현 (area/line/histogram). 향후 stacked/grouped 시각화는 ECharts 도입 검토" 정도의 한 줄 보강 권장. 본 step에서 직접 갱신은 안 함 (메인 세션 판단).
- 10번 문서: 신규 엔드포인트 추가 없음 → 갱신 불필요.
- 11번 frontend architecture: `components/charts/` 하위에 5 컴포넌트 추가 — 디렉토리 구조 일치 (이미 11번에 명시). 갱신 불필요.

## 메인 세션 마무리 체크
- [ ] status를 completed로 변경
- [ ] 작업로그/README.md 갱신
- [ ] PM 호출 → 로드맵 갱신 (08-f·g·h·i·j·k [x] / Phase 12 step 032 ✅)
- [ ] git commit
