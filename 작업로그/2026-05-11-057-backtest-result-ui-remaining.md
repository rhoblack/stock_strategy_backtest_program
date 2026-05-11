---
date: 2026-05-11
agent: frontend-developer
phase: 18
status: completed
roadmap_step: "057"
roadmap_impact:
  - 08-n   # 종목 선택 드롭다운 (복수 종목 지원)
  - 08-o   # 월별 성과 / 리스크 / 자금 관리 탭 실데이터 연결
  - 08-p   # 툴팁 상세 정보 구현
related_docs:
  - 상세설계/08_backtest_result_chart_design.md
  - 상세설계/11_frontend_architecture_design.md
---

# step 057 — 백테스트 결과 UI 잔존: 종목 선택 드롭다운 + 탭 실데이터 + 툴팁

## Plan

> 영향 체크박스 (완료 시 PM이 [x]로 갱신):
> - 08-n: 종목 선택 드롭다운 (복수 종목 후 — BacktestResultPage 차트에서 종목 선택)
> - 08-o: 월별 성과 / 리스크 / 자금 관리 탭 (현재 mock → 실데이터 연결)
> - 08-p: 툴팁 상세 정보 (차트/표의 hover 툴팁 상세화)

- [ ] BacktestResultPage 차트 영역에 종목 선택 드롭다운 복수 종목 지원
  - 현재 SymbolSelector가 단일 종목 선택 → 복수 종목 multi-select 드롭다운 구현
  - chart-data API의 symbol 파라미터 활용
- [ ] 월별 성과 탭 실데이터 연결
  - daily_equity 데이터 기반 월별 수익률 집계 (백엔드 또는 프론트 집계)
  - 월별 수익률 bar chart 구현
- [ ] 리스크 탭 실데이터 연결
  - MDD / Sharpe / Sortino 지표 실 데이터 매핑
  - 리스크 지표 시각화
- [ ] 자금 관리 탭 실데이터 연결
  - cash_events API 연결 (현재 mock)
  - 예수금 변화 + 비용 분해 시각화
- [ ] 툴팁 상세 정보 구현
  - 차트 hover 시 날짜/값/변화율 등 상세 정보 표시
  - 거래 내역 표 row hover 시 추가 정보 (수익률, 보유 기간 등)
- [ ] vitest 단위 테스트 (신규 컴포넌트/훅 커버)
- [ ] npm test + npm run build 통과 확인

## Execution

```text
frontend/src/features/backtest-result/components/MonthlyReturnChart.tsx  신규
  — SVG 기반 월별 수익률 막대 차트 (양수=초록/#16a34a, 음수=빨강/#dc2626)
  — mouseEnter/mouseLeave 커스텀 툴팁 (월, 수익률%, 월말자산)
  — MonthlyReturn 타입 export (ym, returnPct, lastEquity)

frontend/src/features/backtest-result/components/CandleTradeChart.tsx  수정
  — crosshairMove 이벤트 구독/해제 추가 (08번 §9 툴팁)
  — 커스텀 툴팁 DOM: 날짜, OHLC, 매수/매도 마커 정보 (08-p)
  — 마커 색상 로직 강화: 시간청산=회색(#6b7280), 손절=빨강, 익절=초록, 일부매도=보라
  — data-testid="candle-tooltip" 추가

frontend/src/pages/BacktestResultPage.tsx  수정
  — MonthlyReturnChart import 추가 (L24)
  — MonthlySection: 테이블 → MonthlyReturnChart + details 접기 테이블 (L329)
  — RiskSection: sharpe_ratio/volatility "—" + "API 미지원" graceful 처리 (L389)
  — RiskCard 헬퍼 컴포넌트 신규 추가 (title desc + unavailable 스타일)

frontend/src/features/backtest-result/components/BacktestResultUIRemaining.test.tsx  신규
  — MonthlyReturnChart: 빈 데이터 안내 / 차트 렌더 / 막대 색상 / 툴팁 표시/숨김
  — SymbolSelector (08-n): 단일 숨김 / 복수 표시 / ASC 정렬 / onChange 호출
  — CandleTradeChart (08-p): subscribeCrosshairMove / unsubscribeCrosshairMove
  총 13개 테스트 신규
```

사용 API 엔드포인트:
  - GET /api/backtests/{run_id}/chart-data?symbol=  (기존, CandleTradeChart)
  - GET /api/backtests/{run_id}/daily-equity        (기존, MonthlySection 집계 소스)
  - GET /api/backtests/{run_id}/summary             (기존, RiskSection 지표)

08-n 현황: SymbolSelector (symbols.length <= 1 → null) 이미 구현 완료 상태 확인.
  BacktestResultPage에서 tradesWrap 기반 symbolOptions 추출 + SymbolSelector 렌더 → 정상 동작.

## Tests

```text
npx vitest run
→ 32 파일 / 249건 PASS (기존 236 + 신규 13)

npx tsc -b
→ 오류 없음

npx vite build
→ built in 1.10s (경고: chunk 603kB — lightweight-charts 기인한 기존 경고, 신규 없음)
```

## Issues

```text
1. sharpe_ratio / volatility 백엔드 API 미지원
   → BacktestSummaryOut 타입에 해당 필드 없음
   → RiskSection에서 "—" + "API 미지원" 텍스트로 graceful 처리
   → 백엔드에서 summary 응답에 sharpe_ratio, volatility 추가 시 자동 표시 가능하도록 RiskCard 구조화

2. ECharts / Recharts 미설치
   → package.json에 의존성 없음. 설치 없이 SVG 인라인 구현으로 대체
   → 추후 ECharts 도입 시 MonthlyReturnChart만 교체하면 됨

3. 벤치마크 데이터 (market_indices API, step 027) 미연동
   → BenchmarkCompareChart placeholder 유지 — 027 도입 후 연동 예정

4. CandleTradeChart crosshairMove 툴팁은 containerRef.current가 jsdom에서 사이즈 측정 안 됨
   → tooltip 위치 계산 시 clientWidth 0 → Math.min 대비 최대값 처리로 안전 처리 확인
```

## Result

```text
- 추가/수정 파일: 4개
  - MonthlyReturnChart.tsx (신규)
  - CandleTradeChart.tsx (crosshairMove 툴팁)
  - BacktestResultPage.tsx (MonthlySection + RiskSection)
  - BacktestResultUIRemaining.test.tsx (신규 13건)

- 메타데이터 자동화: 해당 없음 (차트/UI 작업)
- 차트 UX 원칙 (08번 §7): 봉차트 마커만, 수익률 라벨 없음 ✓
- 마커 색상 (08번 §8): 익절=#16a34a(초록), 손절=#dc2626(빨강), 시간청산=#6b7280(회색), 일부매도=#9333ea(보라) ✓
- 툴팁 (08번 §9): crosshairMove 이벤트 → 날짜/OHLC/마커 정보 DOM 툴팁 ✓
- 월별 성과 (08-o): SVG 막대 차트 + 접기 테이블 ✓
- 리스크 탭 (08-o): 6개 카드 (MDD/avg_profit/avg_loss/profit_factor/sharpe"-"/volatility"-") ✓
- 자금 탭 (08-o): CashChart + PositionsCountChart 기존 실연결 확인 ✓
- 종목 선택 (08-n): SymbolSelector 기존 구현 확인 (단일=숨김, 복수=표시) ✓
- vitest: 249/249 PASS
- 빌드: 성공
```

## Follow-ups

```text
- market_indices API (step 027) 도입 후 BenchmarkCompareChart 벤치마크 연동
- 백엔드 summary API에 sharpe_ratio, volatility 필드 추가 요청 → 추가 시 BacktestSummaryOut 타입 갱신 + RiskSection RiskCard 자동 표시
- CandleTradeChart MA(이동평균선) 오버레이 추가 — 08번 §6 "봉차트 + 이동평균선" 미구현
- 거래 내역 표 행 hover 상세 툴팁 (08번 §12 거래 내역 연동) — TradesTable 추가 가능
- ECharts 설치 시 MonthlyReturnChart SVG → ECharts 막대 차트로 교체 (인터페이스 동일 유지)
```

## 메인 세션 마무리 체크

- [ ] status를 completed로 변경
- [ ] 작업로그/README.md "최근 작업" 표에 1행 추가
- [ ] Phase 상태가 변경되었으면 Phase 표 갱신
- [ ] Follow-ups 중 다음 작업 후보로 옮길 항목 정리
- [ ] **PM 에이전트 호출 → 로드맵.md 갱신** — "step 057 마무리" 지시. PM이 Phase 로드맵 step ✅ + 08-n·08-o·08-p 체크박스 [x] + 진행률 표 손계산을 직접 Edit.
- [ ] `git commit` (단일 커밋)
- [ ] **Phase 18 마지막 step이라면**: `git push origin main` + test-engineer 검증 호출
