---
date: 2026-05-11
agent: backtest-engine-developer
phase: 22
status: in_progress
roadmap_step: "063"
roadmap_impact:
  - 02-r
related_docs:
  - 상세설계/02_data_schema_design.md
  - 상세설계/04_backtest_engine_design.md
  - 상세설계/13_backtest_accuracy_policy_design.md
---

# step 063 — stop_trading_on_drawdown_pct MDD 거래 중단 구현

## Plan

- [ ] 02_data_schema_design.md §10 risk_management 확인
- [ ] BacktestEngine에서 포트폴리오 전체 MDD 계산 로직 파악
- [ ] risk_management.stop_trading_on_drawdown_pct 설정 시 MDD 초과 시 신규 매수 중단 구현
  - MDD = (current_value - peak_value) / peak_value (음수, 절댓값 비교)
  - look-ahead bias 없어야 함: 당일 시가 기준 평가 후 당일 매수 차단
  - 구현 위치: BacktestEngine 날짜 루프 내, 매수 처리 직전
- [ ] 단위 테스트 작성
  - MDD 초과 시 신규 매수 0건 검증
  - MDD 미초과 시 정상 매수 검증
  - 경계값 테스트 (정확히 임계값 = 차단)
- [ ] pytest 회귀 0 FAIL 유지 확인
- [ ] ruff lint 통과 확인

## Execution

에이전트가 채움.

## Tests

에이전트가 채움.

## Issues

에이전트가 채움.

## Result

에이전트가 채움.

## Follow-ups

에이전트가 채움.
