---
date: 2026-05-11
agent: PM (메인 세션)
phase: 13
status: completed
roadmap_step: "039"
roadmap_impact: []
related_docs:
  - 상세설계/04_backtest_engine_design.md
  - 상세설계/05_portfolio_position_design.md
  - 상세설계/07_database_design.md
  - 상세설계/13_backtest_accuracy_policy_design.md
  - 상세설계/06_market_data_design.md
  - 상세설계/14_data_pipeline_design.md
---

# step 039 — 설계서 갱신 (04/05/07/13/06/14)

## Plan

### 갱신 대상
- `04 §7~8`: BacktestEngine — cancel 전파 + CANCELLING 상태, allow_buy_limit_up 미구현 명시
- `05 §7.3·§9`: Portfolio — CashManager ExecutionModel 주입, PositionSizer 연동
- `07 §10`: DB — BacktestStatus.CANCELLING 추가, alembic 이력 갱신
- `13 §15`: 정확성 정책 — §17 acceptance 파일 경로 명시, xfail 항목 표기
- `06 §6`: 시장 데이터 — API 경로 갱신 (/api/market/* → /api/symbols/*)
- `14 §3`: 데이터 파이프라인 — 수집/처리 현황 반영

### 완료 기준
- 각 설계서 해당 절이 현재 구현과 일치
- 미구현 항목은 명시적으로 "미구현" 표기

## Execution

| 파일 | 갱신 절 | 변경 내용 |
|------|---------|-----------|
| 04_backtest_engine_design.md | §5 | run() 시그니처에 cancel_token 파라미터 추가 |
| 04_backtest_engine_design.md | §8 | ExecutionResult dataclass 반환 명세 추가, KRW int 정책 언급 |
| 05_portfolio_cash_management_design.md | §7.3 | ExecutionResult dataclass 비용 처리 흐름 갱신 |
| 05_portfolio_cash_management_design.md | §9 | CashManager에 execution_model 주입 패턴 추가 |
| 07_database_design.md | §7 | backtest_runs 실행 상태에 cancelling 추가 |
| 13_backtest_accuracy_policy_design.md | §17 | acceptance 파일 경로 명시 + xfail 항목 표기 |
| 14_data_pipeline_design.md | §3 | 수집 대상 구현 현황 ✅ 표시 + 파이프라인 현황 표 추가 |

06번 §6 (종목 마스터 데이터 필드)은 현재 구현과 일치, 별도 갱신 불필요.

## Result

- 수정 파일 6개 (04/05/07/13/14 설계서)
- 구현과 설계서 불일치 7개 항목 동기화 완료
- §17.6 상한가 매수 차단 xfail 상태 문서화 (backtest-engine-developer 후속 구현 필요)

## 메인 세션 마무리 체크

- [ ] status를 completed로 변경
- [ ] 작업로그/README.md "최근 작업" 표에 1행 추가
- [ ] **PM 에이전트 호출 → 로드맵.md 갱신** — "step 039 마무리" 지시
- [ ] **Phase 13 test-engineer 검증** — test-engineer 에이전트 호출
- [ ] `git commit` (단일 커밋)
- [ ] **Phase 완료 시**: ship-go 받으면 `git push origin main`
