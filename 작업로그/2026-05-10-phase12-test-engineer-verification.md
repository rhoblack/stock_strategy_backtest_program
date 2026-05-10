---
date: 2026-05-10
agent: test-engineer
phase: 12
status: completed
roadmap_step: phase12-verification
roadmap_impact:
  - phase12-ship-readiness
related_docs:
  - 상세설계/12_testing_validation_design.md
  - 상세설계/13_backtest_accuracy_policy_design.md
  - 상세설계/02_strategy_json_schema_design.md
  - 상세설계/08_backtest_result_chart_design.md
  - 상세설계/10_api_design.md
  - 상세설계/11_frontend_architecture_design.md
  - 작업로그/2026-05-10-029-strategy-schema-gui.md
  - 작업로그/2026-05-10-030-strategy-header-and-templates.md
  - 작업로그/2026-05-10-031-chart-data-from-daily-prices.md
  - 작업로그/2026-05-10-032-result-page-tabs-and-charts.md
  - 작업로그/2026-05-10-033-table-universe-compare.md
---

# Phase 12 완료 검증 (test-engineer)

Phase 12 = UI 확장 (02 schema GUI 정합화 + StrategyHeader + 4 템플릿 + 6 탭 / 5 차트 +
TanStack Table + UniverseSelector + chart-data DB 전환).

## Plan

- [x] 1. Phase 변경 영역 파악 (703488f..HEAD)
- [x] 2. 정량 회귀 (백엔드 pytest+ruff / 프론트 vitest+build)
- [x] 3. 정확성 정책 13.17 + 02 schema acceptance 매핑
- [x] 4. Phase 1 골든 fixture 회귀
- [x] 5. 신규 e2e 시나리오 5건 작성 (`tests/integration/test_phase12_ui_extension_e2e.py`)
- [x] 6. ship-readiness 결정

## Execution

신규 작성:

```text
backend/tests/integration/test_phase12_ui_extension_e2e.py    e2e 시나리오 5건
```

본 보고서는 코드 / 기존 테스트 / 설계서 / 작업 로그 본문 / 로드맵 / git push를 일절 수정하지 않음 (test-engineer 권한 영역 준수).

## Phase 12 테스트 결과 (test-engineer)

### 1. 변경 영역 파악

```text
Phase 12 첫 commit:    86283af (029 02 schema GUI 정합화)
Phase 12 마지막 commit: 0c9eae8 (033 TanStack Table + UniverseSelector + Compare)
직전 베이스라인:        703488f (Phase 11 종료, 825 PASS)

git log --oneline 703488f..HEAD
0c9eae8 Phase 12-5 (033): TanStack Table + UniverseSelector + Compare (08-m + 11-f·g·h) — 75% 돌파
064099a Phase 12-4 (032): BacktestResultPage 6 탭 + 5 차트 + SymbolSelector (08-f·g·h·i·j·k) — 74%
68be096 Phase 12-3 (031): chart-data DB 전환 + ChartDataQuery (08-l + 10-l, H2 / 외부 4.8) — 71%
0ea240c Phase 12-2 (030): StrategyHeader + 4 templates + 초보/전문 모드 — 01 카테고리 100% / 70% 돌파
86283af Phase 12-1 (029): 02 schema GUI 정합화 — 02 schema 100% / 69%
```

변경 통계: **5 commit / 72 file 변경 / +9,094 / -387 라인**

신규 모듈 (frontend):
- `frontend/src/features/strategy-builder/components/StrategyConfigPanel/` — 6 폼 + formControls + index
- `frontend/src/features/strategy-builder/components/StrategyHeader/` — 액션 버튼 (복사/JSON/실행/모드 토글)
- `frontend/src/features/strategy-builder/templates/` — 4 템플릿 + TemplateSelector
- `frontend/src/features/strategy-builder/state/strategySections.ts` — 6 비조건 섹션 state + 옵션 카탈로그
- `frontend/src/features/strategy-builder/state/useBuilderMode.ts` — 초보자/전문가 모드 hook
- `frontend/src/features/backtest-result/components/` — ResultTabs / SymbolSelector / TradesTable / CandleTradeChart visibleRange
- `frontend/src/components/charts/` — DrawdownChart / CashChart / PositionsCountChart / VolumeChart / BenchmarkCompareChart
- `frontend/src/features/universe-selector/` — UniverseSelector UI (019 백엔드 활용 + MANUAL fallback)
- `frontend/src/components/layout/` + `components/ui/` + `hooks/` + `utils/` — 11번 디렉토리 정합화 (1~2개 컴포넌트 추출)
- `frontend/src/pages/StrategyComparePage.tsx` — 비교 페이지 골격 + `/strategies/compare` 라우트

신규 모듈 (backend, 031에 한정):
- `backend/app/services/backtest_service.py:447-678` — chart-data 헬퍼 5종 (`is_dev_mode`, `_resolve_chart_range`, `_stride_downsample`, `build_chart_data_from_db`, `build_chart_data_synthetic_fallback`)
- `backend/app/schemas/backtest.py:55-79` — `ChartDataQuery` 5 옵션 (symbol/start_date/end_date/use_adjusted/downsample)
- `backend/app/api/routes_backtests.py:163-258` — chart-data 핸들러 재작성 (DB 우선 → dev fallback → 운영 404)

신규 테스트 파일:
- 백엔드: `tests/api/test_chart_data.py` (14건, step 031에서 추가)
- 프론트엔드 vitest: 31건 신규 (templates 10 / TemplateSelector 5 / StrategyHeader 12 / useBuilderMode 4 / TradesTable 9 / UniverseSelector 10 / StrategyComparePage 4 / BacktestResultPage tradeClick 3 / formatters 5 / charts 9 / SymbolSelector 2 / ResultTabs 2 / StrategyConfigPanel 13 / serializeDraft + reducer 확장 — 합계 +119)

### 2. 정량 회귀

| 검증 | 결과 | baseline 대비 |
|---|---|---|
| pytest 백엔드 (전체) | **844 passed in 33.23s** | +19 (Phase 11 종료 825 → 844: 031 +14, 본 e2e +5) |
| ruff app + tests | **All checks passed** | — |
| vitest 프론트엔드 | **162 passed (25 files)** | +119 (Phase 11 종료 43 → 162: 029 +34, 030 +34, 032 +20, 033 +31) |
| vite build | **success (1.40s, 189 modules, 590kB / gzip 186kB)** | chunk 590kB 경고 (TanStack Table 추가, code-split은 후속 권고) |

**회귀 깊이 점검**: `pytest tests/integration/ -v` → 25 passed (phase1 6 + phase9 5 + phase10 4 + phase11 5 + phase12 5).

### 3. 정확성 정책 13.17 + 02 schema acceptance

Phase 12는 주로 UI 변경 — 정확성 정책 영향은 13.7 / 13.12 / 02.x로 한정.

| 정책 절 | 영향 | 검증 테스트 | 결과 |
|---|---|---|---|
| **13.7 수정주가 사용 일관성** (use_adjusted toggle) | 031 chart-data | `test_chart_data_use_adjusted_toggle` (단위) + **e2e 시나리오 4** (adj_diff=500 라운드트립) | ✅ |
| **13.12 결정론** (chart-data 정렬, TanStack Table 정렬, UniverseSelector 정렬) | 031 / 032 / 033 | `test_chart_data_*` (단위) + **e2e 시나리오 3** (두 번 호출 byte-equal) | ✅ |
| **02.4 GROUP 1단계 중첩** (frontend 직렬화) | 029 | `serializeDraft.test.ts` GROUP 케이스 + **e2e 시나리오 1** (라운드트립 보존) | ✅ |
| **02.7 priority method/tie_breaker** | 029 | `serializeDraft.test.ts` priority 케이스 + e2e 시나리오 1 | ✅ |
| **02.8 position_sizing method/amount/max_positions** | 029 | `StrategyConfigPanel.test.tsx` PositionSizing + e2e 시나리오 1 | ✅ |
| **02.11 execution + tick_rounding** | 029 | `StrategyConfigPanel.test.tsx` Execution + e2e 시나리오 1 | ✅ |
| **02.12 metadata.schema_version 고정** ("1.0") | 029 | `serializeDraft.test.ts` metadata 케이스 + **e2e 시나리오 1** (라운드트립 schema_version 검증) | ✅ |
| **02.15 tax_rate 시계열 (from 오름차순 + rate>=0)** | 029 | `serializeDraft.test.ts` tax 케이스 + **e2e 시나리오 1·2** (4개 bracket 라운드트립 + 정렬 위반 → 400) | ✅ |
| **13.6 거래세 시계열 (한국 0.23%→0.15% 변동)** | 029 GUI | **e2e 시나리오 2** (4 bracket 시나리오 1과 동일) | ✅ |
| **10.7 표준 envelope + X-Request-ID** (Phase 8 H7) | 회귀 | **e2e 시나리오 2** (INVALID_PARAMETER_VALUE 400 + envelope 키 보존) + 시나리오 5 (MARKET_DATA_NOT_FOUND 404) | ✅ |
| **10.4 chart-data API spec** (symbol/start_date/end_date/use_adjusted/downsample) | 031 | `test_chart_data_*` 14건 + e2e 3·4·5 | ✅ |
| **10.9 user_id scope** (다른 사용자 backtest 접근 차단) | 031 회귀 | `test_chart_data_other_user_run_returns_404` + `_get_run_or_raise` 재사용 | ✅ |
| CLAUDE.md #1 (JSON 데이터, eval 금지) | 029 직렬화 | e2e 시나리오 1 — strategy_json이 dict로 라운드트립 (Python 문자열 코드 0건) | ✅ |
| CLAUDE.md #6 (한국 양봉=빨강, 음봉=파랑) | 032 VolumeChart | `charts.test.tsx` VolumeChart 색상 케이스 | ✅ |
| CLAUDE.md #8 (결정론 sorted) | 031~033 | e2e 시나리오 3 + 단위 테스트 정렬 케이스 | ✅ |

13.17 acceptance 항목 중 Phase 12 변경 무관한 항목 (13.17.1 일중 stop/take, 13.17.4 next_open 체결, 13.17.10 priority 결정론, 13.17.3 갭다운 시가 체결, 13.17.5 거래정지 차단 등) → Phase 8/9/10에서 이미 acceptance 통과. Phase 12에서 BacktestEngine / Portfolio / ExecutionModel / CashManager / conditions 영역 변경 0건이므로 회귀 위험 없음 (골든 fixture가 frozen 9지표로 보호).

### 4. Phase 1 골든 회귀

```text
pytest tests/integration/test_phase1_golden.py -v
→ 6 passed in 0.49s
```

검증 항목:
- ✅ 9지표 frozen expected (final_equity / total_return / mdd / trade_count / win_rate / avg_holding_days / profit_factor / 첫 거래 entry_date)
- ✅ 결정론 10회 반복 동일 결과 (`test_golden_03_full_determinism_10_runs`)
- ✅ Phase 12는 engine 변경 0건 → expected 그대로 (변경 없음)

### 5. 신규 시나리오

신규 작성: `backend/tests/integration/test_phase12_ui_extension_e2e.py` — **5건 모두 PASS**

| # | 시나리오 | 정책 매핑 | 결과 |
|---|---|---|---|
| 1 | 02 schema 6섹션 + GROUP 1단계 + tax_rate 시계열 4 bracket — POST → DB → GET 라운드트립 | 02.4 / 02.7 / 02.8 / 02.11 / 02.12 / 02.15 / CLAUDE.md #1 | ✅ |
| 2 | tax_rate 시계열 정렬 위반 → 400 INVALID_PARAMETER_VALUE 표준 envelope (X-Request-ID 보존) | 02.15 / 13.6 / 10.7 (H7) | ✅ |
| 3 | chart-data 두 번 호출 byte-equal (candles + markers + equity_curve 시퀀스 동일) | 13.12 / CLAUDE.md #8 | ✅ |
| 4 | chart-data use_adjusted toggle (adj_close = close + 500 라운드트립) | **13.7 핵심** | ✅ |
| 5 | chart-data fallback chain (DB 우선 → dev synthetic → 운영 404 + envelope) | 10.4 / 10.7 / 14.10 | ✅ |

각 시나리오는 독립 file-based SQLite + TestClient. 외부 fetch 0건.

검증 정확도:
- 시나리오 1 — 4 bracket 시계열의 from/rate 4개씩 모두 명시 검증 (보존 깨지면 fail).
- 시나리오 3 — `body1["candles"] == body2["candles"]`로 list 동등성 (순서 + 값 모두) 검증 + 단조 증가 가드.
- 시나리오 4 — adj_diff=500.0 시드로 두 컬럼 분기를 명확히 검증 (시드 같으면 통과해도 의미 없음).
- 시나리오 5 — DB 시드 전후로 source 변경 ("synthetic" → "daily_prices") 확인 + 다른 run에 대해 production 모드로 404.

### 6. 회귀 발견

**없음.** 

- 기존 825 PASS (Phase 11) + 14 (031 chart-data 단위) + 5 (본 e2e) = 844/844 PASS — 모두 유지
- Phase 1 골든 9지표 frozen 유지 — engine 변경 0건
- 프론트엔드 vitest 162/162 PASS — baseline 43 → +119 (29~33 step의 단위 테스트 추가)
- vite build 성공 (chunk 경고는 사전부터 존재 — TanStack Table 추가로 590kB로 증가, code-split은 Follow-up)
- ruff app+tests All checks passed
- 표준 error envelope (Phase 8 H7) 보존 — INVALID_PARAMETER_VALUE / MARKET_DATA_NOT_FOUND 둘 다 envelope 키 정합

### 7. ship-readiness 결정

## **🟢 ship-go**

근거:
1. **회귀 100% 통과** — 백엔드 844/844 PASS, baseline 825 → +19 (단위 14 + e2e 5). 프론트엔드 162/162 PASS, baseline 43 → +119.
2. **02 schema 6섹션 + GROUP + tax_rate 시계열 e2e 라운드트립이 frontend↔backend contract 보호** — 029 frontend serializeDraft 산출물 형식이 백엔드 validator(C4) + 영속화 + 재조회를 통과해 보존. 두 계층의 schema 정합화가 e2e로 검증.
3. **031 chart-data DB 전환의 3-단계 fallback chain이 e2e로 동작** — DB 우선 / dev synthetic / 운영 404 분기가 한 시나리오에서 모두 검증. 13.7 use_adjusted toggle도 adj_diff=500 시드로 명확한 컬럼 분기 검증.
4. **결정론(13.12) 회귀 보호** — chart-data 두 번 호출 byte-equal 시나리오로 31~33 step의 정렬 정합성을 e2e 보호. CLAUDE.md #8 (Python dict/set 순서 비의존)도 cross-component 보장.
5. **Phase 1 골든 fixture frozen** — engine 영역 변경 0건이라 9지표 / 결정론 10회 모두 회귀 0건.
6. **표준 error envelope 보존** — Phase 8 H7 정책이 Phase 12에서도 깨지지 않음 (e2e 시나리오 2·5).

핵심 강조:
- **시나리오 1 (6섹션 + GROUP + tax_rate 4 bracket 라운드트립)** — Phase 12의 가장 invasive한 변경(029)이 frontend serializeDraft → 백엔드 validator → DB persistence → GET response까지 dict shape 그대로 보존됨을 확인. 029 작업 로그가 명시한 "02 schema 100% 정합화" 주장이 e2e로 검증됨.
- **시나리오 4 (use_adjusted toggle)** — 031의 13.7 정책 진입점이 adj_close ≠ close 시드에서도 정확한 컬럼을 선택. 단위 테스트는 시드가 동일 값이라 분기를 검증하지 못했으나(test_chart_data_use_adjusted_toggle 자체 주석에 "현재 시드는 동일 값이라 형식만 검증"), 본 e2e가 adj_diff=500으로 분기를 실데이터 차이로 검증.
- **시나리오 5 (3-단계 fallback chain)** — Phase 12 H2 (외부 4.8) 핵심 정책. 단위 테스트는 분기별 격리되어 있으나 본 e2e는 같은 run에 대해 daily_prices 시드 전후로 source가 동적으로 바뀜을 검증.

권고: 메인 세션은 PM 호출(로드맵 Phase 12 ✅) + `git push origin main` 진행.

### 8. Follow-up

향후 권고 (Phase 13 진입 전 또는 별도 step):

1. **vite build chunk 590kB 경고** — TanStack Table 도입으로 chunk 한도(500kB) 초과. 033 작업 로그가 Issues로 명시. Phase 13에서 lightweight-charts / TanStack을 별도 chunk로 split 권고.
2. **시나리오 1의 cash_management 검증 깊이 강화** — 본 e2e는 `cash_management.enabled is True`만 검증. shortage_rule 트리거/액션 dict 구조 라운드트립도 명시 검증을 추가하면 향후 02 schema 정합 깨짐을 더 빨리 잡을 수 있음. 현재는 strategy_json 전체 dict가 보존되므로 깨지면 다른 단언이 fail하긴 함.
3. **027 market_indices read API 도입** — 032 BenchmarkCompareChart가 placeholder로 남음. Phase 13에서 백엔드 API 추가 후 KOSPI/KOSDAQ 비교 가능.
4. **universe preview API 도입** — 033 UniverseSelector가 placeholder. Phase 13에서 백엔드 미리보기 API 추가 후 selection 결과 시각화.
5. **TradesTable 거래 클릭 → 차트 이동 backend 통합 e2e** — 현재 frontend 단위 테스트(`BacktestResultPage.tradeClick.test.tsx`)로 검증. mock chart-data가 아닌 실 chart-data + 실 trades API로 e2e 검증은 Playwright 등 별도 도입 필요. ship 차단 사유 아님 (frontend 단위 검증 충분).
6. **APP_ENV 정책 문서화** — 031에서 도입된 `APP_ENV` 환경변수가 10번 또는 별도 운영 가이드에 명시되지 않음. 031 작업 로그 Follow-up에 이미 명시되어 있으니 Phase 13 진입 시 문서 갱신 권고.
7. **GROUP 토글 UI** — 029 작업 로그가 명시한 잔존 — `SET_LOGIC` select에 GROUP 옵션 추가 필요. 현재 reducer는 지원, UI만 미노출. e2e 시나리오 1에서 GROUP shape는 검증되지만 UI 사용성은 부족.
8. **백엔드 에러 envelope 한국어 매핑** — 029/030 Issues가 명시한 잔존 (StrategyValidationPanel 또는 새 ServerErrorPanel). 본 e2e 시나리오 2에서 envelope 형식은 보존 확인.

## Result

```text
- 추가/수정 파일: backend/tests/integration/test_phase12_ui_extension_e2e.py (신규 5건)
- 적용된 정책: 02.4 / 02.7 / 02.8 / 02.11 / 02.12 / 02.15 / 13.6 / 13.7 / 13.12 /
  10.4 / 10.7 / 10.9 / CLAUDE.md #1 / #6 / #8
- 정량 회귀 (백엔드): 844 PASS (Phase 11 종료 825 → +19, 신규 e2e 5 + 031 단위 14)
- 정량 회귀 (프론트): 162 PASS (Phase 11 종료 43 → +119, 029~033 step 단위)
- ruff: All checks passed (app + tests)
- vite build: 성공 (chunk 590kB 경고는 follow-up)
- Phase 1 골든: 6/6 PASS, 9지표 frozen 유지
- 신규 e2e: 5/5 PASS
- ship-readiness: 🟢 ship-go
```

## 메인 세션 마무리 체크

- [ ] status를 completed로 변경 (이미 frontmatter에 completed)
- [ ] 작업로그/README.md "최근 작업" 표에 1행 추가
- [ ] Phase 12 표 ✅ 갱신 (Phase 13 ⏭ 다음)
- [ ] **PM 에이전트 호출** → 로드맵 Phase 12 ✅ + 진행률 추이 새 행 + Phase 13 ⏭
- [ ] `git commit` (단일 커밋)
- [ ] **Phase 12 마지막 단계** → `git push origin main` 자동 실행 (의무)
