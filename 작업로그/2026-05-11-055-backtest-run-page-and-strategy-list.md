---
date: 2026-05-11
agent: frontend-developer
phase: 18
status: completed
roadmap_step: "055"
roadmap_impact:
  - 11-k
  - 11-l
related_docs:
  - 상세설계/11_frontend_architecture_design.md
  - 상세설계/08_backtest_result_chart_design.md
  - 상세설계/01_strategy_builder_gui_design.md
---

# step 055 — BacktestRunPage 시장/종목군 선택 UI + 전략 목록 last_backtest 표시

## Plan

작업 시작 전 체크리스트.

- [ ] BacktestRunPage에서 synthetic 입력 제거 + 실 UniverseSelector 컴포넌트 연결 (11-l)
  - synthetic 하드코딩된 symbol/date range 입력 필드 제거
  - `features/universe-selector` 의 UniverseSelector 컴포넌트 임포트 + BacktestRunPage 내 배치
  - UniverseSelector 선택 결과를 백테스트 요청 payload 에 반영 (universe_config 필드)
- [ ] 전략 목록(StrategyListPage)에 last_backtest 날짜/수익률 표시 (11-k)
  - GET /api/strategies 응답에 last_backtest_at, last_backtest_return 필드가 있는지 확인
  - 없으면 GET /api/backtests?strategy_id=X (최신 1건) 추가 쿼리 또는 백엔드 응답 확장 검토
  - StrategyListPage 카드/행에 날짜 + 수익률 칸 추가
- [ ] vitest 단위 테스트 추가
  - BacktestRunPage: UniverseSelector 렌더링 + payload 전달 검증
  - StrategyListPage: last_backtest 필드 표시 검증
- [ ] npm test (vitest) 전체 통과 확인
- [ ] npm run build 성공 확인

## Execution

```text
frontend/src/api/strategies.ts:8-19
  StrategyLastBacktest 타입 신규 추가
  StrategyOut에 last_backtest?: StrategyLastBacktest | null 옵셔널 필드 추가

frontend/src/pages/BacktestRunPage.tsx (전면 재작성)
  - useSynthetic, syntheticSeed, syntheticN 상태 변수 제거
  - "유니버스 모드" select 드롭다운 + 합성 데이터 fieldset UI 제거
  - 개발용 안내 문구("Phase 14 데이터 파이프라인 미구현 ...") 제거
  - onRun: synthetic 분기 제거 → 항상 universeConfigToPayload(universeConfig) 사용
  - UniverseSelector 항상 렌더링 (조건부 렌더링 아님)

frontend/src/pages/StrategyListPage.tsx (수정)
  - StrategyLastBacktest import 추가
  - LastBacktestBadge 내부 컴포넌트 추가
    - last_backtest 없거나 null → data-testid="last-backtest-empty" + "최근 백테스트 없음"
    - last_backtest 있음 → data-testid="last-backtest-badge"
    - 수익률 양수=초록(#16a34a), 음수=빨강(#dc2626)
    - 날짜 포맷: formatDate() 함수 — "2026-05-11" → "2026.05.11"
    - MDD, win_rate, run_date 표시
  - 전략 카드 layout: flex gap 12, LastBacktestBadge 중앙 배치

frontend/src/pages/BacktestRunPage.test.tsx (수정)
  - "전략 선택 → 실행 → mutate 호출 + redirect" 테스트 변경
    - synthetic_seed 기대 제거 → universe_config.market 존재 + synthetic_seed undefined 확인
  - "UniverseSelector가 렌더링됨 (합성 데이터 UI 없음)" 테스트 추가
    - data-testid="universe-selector" 존재 확인
    - "합성 데이터" 텍스트 없음 확인

frontend/src/pages/StrategyListPage.test.tsx (신규)
  - 8개 테스트: 전략 목록 표시, last_backtest 있을 때/음수/null/undefined, 로딩, 빈 목록, 링크 URL
```

### 주요 결정 사항
- 기존 BacktestRunPage 테스트가 `payload.universe_config.synthetic_seed === 42`를 기대했으나
  synthetic 제거로 해당 단언을 `universe_config.market` 존재 + `synthetic_seed` undefined 확인으로 교체
- StrategyOut.last_backtest에 run_date 옵셔널 필드 추가 (API 10번 문서에는 없었으나
  날짜 표시를 위해 추가 — 백엔드가 반환하지 않으면 날짜 라벨만 숨김)

## Tests

```text
cd frontend && npm test -- --run

Test Files: 31 passed (31)
     Tests: 227 passed (227)
  Start at: 10:56:23
  Duration: 3.52s

npm run build
→ vite v5.4.21 building for production...
→ ✓ 195 modules transformed
→ ✓ built in 969ms
→ 빌드 성공 (청크 사이즈 경고는 기존과 동일, 오류 아님)
```

## Issues

```text
- 기존 BacktestRunPage.test.tsx의 3번 테스트가 payload.universe_config.synthetic_seed === 42를 기대함
  → synthetic 제거 후 테스트 단언을 universe_config.market 존재 확인으로 교체 (정상 해결)

- 10번 API 문서의 GET /api/strategies 응답 last_backtest에 run_date 필드가 명시되지 않음
  → StrategyLastBacktest 타입에 run_date?: string | null 옵셔널로 추가
  → 백엔드가 반환하지 않아도 날짜 라벨만 숨기므로 graceful 처리됨

- 백엔드에서 현재 last_backtest를 반환하지 않으면 프론트는 "최근 백테스트 없음"으로 표시
  → 백엔드 추가 작업으로 last_backtest 포함 응답 구현 필요 (Follow-ups 참조)
```

## Result

```text
- 추가/수정 파일 5개:
  frontend/src/api/strategies.ts           (StrategyLastBacktest 타입 + optional 필드)
  frontend/src/pages/BacktestRunPage.tsx   (synthetic 전면 제거, UniverseSelector만 사용)
  frontend/src/pages/StrategyListPage.tsx  (LastBacktestBadge + 날짜/수익률 표시)
  frontend/src/pages/BacktestRunPage.test.tsx  (synthetic 기대 제거, UniverseSelector 확인)
  frontend/src/pages/StrategyListPage.test.tsx (신규 — 8개 테스트)

- 사용 API 엔드포인트: GET /api/strategies (last_backtest 옵셔널)
- 메타데이터 자동화 적용: N/A (조건 폼 아님)
- 차트 UX 원칙 적용: N/A (차트 없음)
- 타입 안전성: StrategyOut.last_backtest optional, StrategyLastBacktest 타입 정의
- 11-k (BacktestRunPage synthetic 제거 + UniverseSelector 연결): 완료
- 11-l (StrategyListPage last_backtest 표시): 완료
- npm test: 227 PASS / 31 files
- npm run build: 성공
```

## Follow-ups

```text
- 백엔드 GET /api/strategies 응답에 last_backtest 필드 추가 필요
  현재 routes_strategies.py가 StrategyOut에 last_backtest를 포함하지 않으면 프론트는 "최근 백테스트 없음" 표시
  → 백엔드에서 backtest_runs 최신 1건을 JOIN하거나 별도 쿼리로 last_backtest 포함 응답 구현 필요
  → 포함 시: total_return, mdd, win_rate, run_date 필드를 반환해야 프론트 뱃지 자동 활성화

- UniverseSelector preview API 미구현 상태
  UniverseSelector.tsx 내 "유니버스 미리보기 API는 후속 step에서 추가됩니다" placeholder가 있음
  → 후속 step에서 GET /api/universe/preview 구현 시 placeholder 교체
```

## 메인 세션 마무리 체크

- [ ] status를 completed로 변경
- [ ] 작업로그/README.md "최근 작업" 표에 1행 추가
- [ ] Phase 상태가 변경되었으면 Phase 표 갱신
- [ ] Follow-ups 중 다음 작업 후보로 옮길 항목 정리
- [ ] **PM 에이전트 호출 → 로드맵.md 갱신** — "step 055 마무리" 지시. PM이 Phase 로드맵 step ✅ + 영향 체크박스 (11-k, 11-l) [x] + 진행률 표 손계산을 직접 Edit.
- [ ] `git commit` (단일 커밋)
- [ ] **Phase 마지막 step이 아님** — push 불필요 (Phase 18 완료 시 push)
