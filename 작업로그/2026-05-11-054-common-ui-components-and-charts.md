---
date: 2026-05-11
agent: frontend-developer
phase: 18
status: completed
roadmap_step: "054"
roadmap_impact:
  - 11-m
  - 11-n
related_docs:
  - 상세설계/11_frontend_architecture_design.md
  - 상세설계/08_backtest_result_chart_design.md
---

# 공통 UI 컴포넌트 정비 + 차트 컴포넌트 분리 (Phase 18 첫 step)

## Plan

PM 사전 기록 — 영향 체크박스: 11-m (공통 Button/Input/Card/Tabs), 11-n (차트 컴포넌트 분리)

- [x] 11-m: 공통 UI 컴포넌트 정비
  - [x] `frontend/src/components/ui/Button.tsx` — variant(primary/secondary/danger/ghost), size(sm/md/lg), disabled/loading 상태
  - [x] `frontend/src/components/ui/Input.tsx` — label, error message, type(text/number/select), 기본 스타일
  - [x] `frontend/src/components/ui/Card.tsx` — title, padding 옵션, 이미 존재하면 확장 (ContainerCard 추가, SummaryCard 호환)
  - [x] `frontend/src/components/ui/Tabs.tsx` — items(label+value), activeTab, onChange, role=tablist/tab
  - [x] 기존 컴포넌트들(BacktestResultPage 등)에서 인라인 스타일/중복 로직을 공통 컴포넌트로 교체
  - [x] vitest 단위 테스트 (각 컴포넌트 렌더 + props + 인터랙션) — 41건 신규

- [x] 11-n: 차트 컴포넌트 분리
  - [x] `frontend/src/components/charts/DrawdownChart.tsx` — 이미 독립 파일 (확인)
  - [x] `frontend/src/components/charts/VolumeChart.tsx` — 이미 독립 파일 (확인)
  - [x] `frontend/src/components/charts/CashChart.tsx` — 이미 독립 파일 (확인)
  - [x] `frontend/src/components/charts/BenchmarkCompareChart.tsx` — 이미 독립 파일 (확인)
  - [x] `frontend/src/components/charts/index.ts` — re-export (신규)
  - [x] BacktestResultPage에서 차트 import를 barrel(index.ts)로 교체
  - [x] vitest 단위 테스트 (각 차트 컴포넌트 렌더 + props 반영) — 15건 신규

- [x] 회귀 검증
  - [x] `npm run test` — 30 files / 218 tests PASS (기존 162 + 신규 56)
  - [x] `npm run build` — 빌드 오류 없음 (청크 경고는 정상)
  - [x] BacktestResultPage 차트 6 탭 기존 테스트 회귀 없음 (8건 + tradeClick 3건 PASS)

## Execution

### 작성/수정 파일

**신규 생성 (11-m)**
- `frontend/src/components/ui/Button.tsx` — variant(primary/secondary/danger/ghost), size(sm/md/lg), loading 스피너, disabled 지원
- `frontend/src/components/ui/Input.tsx` — label, error(role=alert), type(text/number), onChange 콜백, disabled
- `frontend/src/components/ui/Tabs.tsx` — role=tablist, aria-selected, items/active/onChange props
- `frontend/src/components/ui/index.ts` — Button, Input, Tabs, Card (SummaryCard/ContainerCard) re-export

**확장 (11-m)**
- `frontend/src/components/ui/Card.tsx` — 기존 SummaryCard(label+value) 유지 + ContainerCard(title+children+padding) 추가. 기존 default export 호환 유지.

**신규 생성 (11-n)**
- `frontend/src/components/charts/index.ts` — DrawdownChart, VolumeChart, CashChart, BenchmarkCompareChart, PositionsCountChart re-export

**신규 생성 (테스트)**
- `frontend/src/components/ui/__tests__/Button.test.tsx` — 12 테스트
- `frontend/src/components/ui/__tests__/Input.test.tsx` — 10 테스트
- `frontend/src/components/ui/__tests__/Card.test.tsx` — 11 테스트
- `frontend/src/components/ui/__tests__/Tabs.test.tsx` — 8 테스트
- `frontend/src/components/charts/charts.extra.test.tsx` — 15 테스트 (빈 데이터 렌더, props 재렌더, index.ts re-export)

**수정 (리팩토링)**
- `frontend/src/pages/BacktestResultPage.tsx:1-29` — 개별 차트 import를 `charts/index` barrel로 교체, 인라인 Card 함수 제거 후 `SummaryCard as Card` 공통 컴포넌트로 교체

### 사용 API 엔드포인트

없음 (순수 프론트엔드 컴포넌트 작업)

## Tests

```
npm test -- --run
→ Test Files: 30 passed (30)
→ Tests:      218 passed (218)  (기존 162 + 신규 56)

npm run build
→ tsc -b 통과 (타입 오류 없음)
→ vite build 성공 (590 kB, 청크 크기 경고는 lightweight-charts 특성상 정상)
```

## Issues

1. **`cleanup` import 오류**: `@testing-library/react`에서 named export `cleanup`을 직접 destructuring해 import했으나 vitest globals 환경에서 `cleanup is not a function` 오류 발생. → Card.test.tsx / Tabs.test.tsx 를 `unmount()` 또는 globals 자동 cleanup 방식으로 수정해 해결.

2. **charts 파일 이미 분리됨**: DrawdownChart, VolumeChart, CashChart, BenchmarkCompareChart, PositionsCountChart 는 이전 step(031/032)에서 이미 `components/charts/`에 분리 완료. 이번 step에서는 `index.ts` re-export 추가와 추가 테스트(빈 데이터, 재렌더) 작성만 진행.

3. **BacktestResultPage 인라인 Card**: 파일 하단에 `function Card`가 인라인 정의되어 있었음. `SummaryCard as Card`로 교체 후 인라인 정의 제거. BacktestResultPage 기존 테스트 8건 모두 회귀 없이 PASS 확인.

## Result

- **새 TypeScript 타입**: `ButtonProps`, `InputProps`, `TabItem`, `TabsProps`, `ContainerCardProps` (ui/index.ts 통해 export)
- **메타데이터 자동화**: 해당 없음 (공통 UI 컴포넌트 정비)
- **차트 UX 원칙 (08번 7절)**: 차트 컴포넌트는 기존 구현 유지. index.ts re-export로 import 경로 단순화.
- **BacktestResultPage 6탭 차트**: 차트 import가 barrel로 변경되었으나 동일 컴포넌트 참조이므로 렌더 동작 동일. 기존 8건 + tradeClick 3건 회귀 없음.
- **공통 ui/index.ts**: Button/Input/Tabs/Card를 단일 진입점에서 import 가능.

## Follow-ups

- `components/ui/` 컴포넌트를 StrategyBuilderPage, BacktestRunPage 등 다른 페이지에서 점진적으로 교체 (현재는 BacktestResultPage만 Card 교체 완료)
- Button 컴포넌트를 StrategyHeader, ConditionEditorPanel 등 기존 `<button>` 인라인 스타일 교체
- Input 컴포넌트를 StrategyConfigPanel 숫자 입력 필드에 교체
- Tabs 컴포넌트를 ResultTabs(현재 자체 구현)와 통합 검토
- 차트 청크 분리: lightweight-charts를 dynamic import()로 lazy load하면 빌드 청크 경고 해소 가능 (성능 개선 follow-up)

## 메인 세션 마무리 체크

- [ ] status를 completed로 변경
- [ ] 작업로그/README.md "최근 작업" 표에 1행 추가
- [ ] Phase 상태가 변경되었으면 Phase 표 갱신
- [ ] Follow-ups 중 다음 작업 후보로 옮길 항목 정리
- [ ] **PM 에이전트 호출 → 로드맵.md 갱신** — "step 054 마무리" 지시. PM이 Phase 로드맵 step ✅ + 영향 체크박스 [x] + 진행률 표 손계산을 직접 Edit. (영향 체크박스: 11-m, 11-n)
- [ ] `git commit` (단일 커밋)
