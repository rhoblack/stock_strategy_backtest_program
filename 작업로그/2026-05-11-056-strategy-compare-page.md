---
date: 2026-05-11
agent: frontend-developer
phase: 18
status: completed
roadmap_step: "056"
roadmap_impact:
  - 11-i   # StrategyComparePage
  - 11-j   # TanStack Table (전략 목록/비교 뷰 적용)
related_docs:
  - 상세설계/11_frontend_architecture_design.md
  - 상세설계/08_backtest_result_chart_design.md
---

# step 056 — StrategyComparePage 완성 + TanStack Table 전략 목록/비교 뷰

## Plan

> 영향 체크박스 (완료 시 PM이 [x]로 갱신):
> - 11-i: StrategyComparePage (골격 → 실제 비교 기능)
> - 11-j: TanStack Table (전략 목록 페이지 + 비교 뷰에 적용)

- [x] StrategyComparePage 골격 → 실 비교 기능 구현
  - [x] 복수 전략 선택 UI (최대 5개 드롭다운 슬롯 + 추가/제거 버튼)
  - [x] 선택된 전략들의 최근 백테스트 결과 지표 비교 테이블
  - [x] 비교 지표: 총수익률, 연환산수익률, MDD, 승률, 샤프지수, 평균보유일, 거래횟수, 초기자금, 최종자산
- [x] 전략 목록 페이지(StrategyListPage)에 TanStack Table 적용
  - [x] 컬럼: 전략명(+태그), 마지막 백테스트(날짜+수익률+MDD), 액션(실행/편집)
  - [x] 정렬(헤더 클릭) + 필터(전략명 텍스트 검색) 기능
- [x] 비교 뷰 TanStack Table 확장
  - [x] 지표 행 × 전략 열 피벗 형태 테이블 구현
- [x] vitest 단위 테스트 작성
  - [x] StrategyComparePage: 페이지 렌더, 비교 테이블 컬럼/행 수, summary 데이터 표시, 슬롯 추가
  - [x] StrategyListPage: 기존 8건 유지 + 정렬/필터 동작 4건 신규
- [x] npm test 전체 통과 확인 (227 → 236 PASS)
- [x] npm run build 통과 확인

## Execution

```text
frontend/src/api/backtests.ts:8-37      BacktestListItem, BacktestListResponse 타입 추가
frontend/src/api/backtests.ts:197-235   fetchBacktestList, useBacktestList, useLatestCompletedRunId 훅 추가

frontend/src/pages/StrategyComparePage.tsx   전체 재작성 (골격 → 실 비교 기능)
  - 최대 5슬롯 드롭다운 (슬롯 추가/제거 버튼)
  - useAllSummaries: 훅 규칙 준수를 위해 고정 5슬롯 항상 훅 등록 (조건부 훅 호출 회피)
  - CompareTable: TanStack Table, 지표 9개 × 전략 N개
  - 비교 지표: 총수익률, 연환산수익률, MDD, 승률, 샤프지수, 평균보유일, 거래횟수, 초기자금, 최종자산
  - 양수수익률 초록(#16a34a), 음수수익률 빨강(#dc2626) 색상 처리
  - 백테스트 없는 전략: "-" graceful 표시
  - 완료된 백테스트 결과 링크 (#run_id + "결과 보기")

frontend/src/pages/StrategyListPage.tsx     map() → TanStack Table 전환 (11-j)
  - 컬럼: 전략명(+태그), 마지막 백테스트(날짜+수익률+MDD), 액션(백테스트 실행/편집)
  - getSortedRowModel + getFilteredRowModel 적용
  - 전략명 텍스트 검색 (data-testid="strategy-name-filter")
  - 헤더 클릭 정렬 (⇅/▲/▼ 표시자), data-testid="th-{id}" 로 테스트 가능
  - 기존 data-testid (last-backtest-badge/empty/return) 테이블 셀 내 재현 → 기존 테스트 호환

frontend/src/pages/StrategyComparePage.test.tsx   4건 → 9건 (전체 재작성)
frontend/src/pages/StrategyListPage.test.tsx       8건 + TanStack Table 신규 4건 = 12건
```

사용 API 엔드포인트:
- GET /api/strategies
- GET /api/backtests?strategy_id={id}&status=completed&page_size=1  (useLatestCompletedRunId)
- GET /api/backtests/{run_id}/summary  (useBacktestSummary)

## Tests

```text
vitest run
→ Test Files: 31 passed (31)
→ Tests: 236 passed (236)  [기존 227 → 236, +9건]
→ Duration: 3.58s

vite build
→ 195 modules transformed
→ dist/index.html 0.38kB
→ 빌드 성공 (청크 크기 경고는 기존부터 존재하던 것, 에러 없음)
```

## Issues

없음. 훅 규칙(조건부 호출 금지) 준수를 위해 고정 5슬롯 패턴 채택
(useAllSummaries가 항상 5개의 useStrategySummary를 호출하고, null인 슬롯은 useLatestCompletedRunId 내부에서 비활성화).

## Result

```text
- 추가/수정 파일: backtests.ts, StrategyComparePage.tsx, StrategyListPage.tsx,
                 StrategyComparePage.test.tsx, StrategyListPage.test.tsx (5개)
- 메타데이터 자동화: 해당 없음 (비교 지표는 METRICS 배열로 정적 정의, 백엔드 summary 키 매핑)
- TanStack Table: StrategyComparePage(비교 테이블) + StrategyListPage(목록 테이블) 양쪽 적용
- 차트 UX 원칙 (08번 7절): 해당 없음 (비교 테이블 화면, 차트 없음)
- 비동기 처리: useLatestCompletedRunId → useBacktestSummary 순차 조회 (TanStack Query 캐싱)
- 타입 안전성: BacktestListItem, BacktestListResponse 신규 타입 추가
- 한국어 UI: 모든 라벨 한국어 (총수익률, 연환산수익률, MDD, 승률, 샤프지수 등)
```

## Follow-ups

- StrategyComparePage: 지표 비교 테이블 외 수익률 곡선 오버레이 차트 (ECharts) — 후속 step
- StrategyListPage: 즐겨찾기 필터, 태그 멀티 필터 추가 가능
- 청크 크기 경고 해소: vite manualChunks 설정 (별도 step 또는 Phase 19)

## 메인 세션 마무리 체크

- [ ] status를 completed로 변경
- [ ] 작업로그/README.md "최근 작업" 표에 1행 추가
- [ ] Phase 상태가 변경되었으면 Phase 표 갱신
- [ ] Follow-ups 중 다음 작업 후보로 옮길 항목 정리
- [ ] **PM 에이전트 호출 → 로드맵.md 갱신** — "step 056 마무리" 지시. PM이 Phase 로드맵 step ✅ + 영향 체크박스 11-i·11-j [x] + 진행률 표 손계산을 직접 Edit
- [ ] `git commit` (단일 커밋)
- [ ] **Phase 18 마지막 step이 아님** — step 057 (08-n·o·p) 남아 있음
