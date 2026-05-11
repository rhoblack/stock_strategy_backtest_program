---
date: 2026-05-11
agent: backtest-engine-developer
phase: 22
status: in_progress
roadmap_step: "066"
roadmap_impact:
  - 02-t
related_docs:
  - 상세설계/02_strategy_json_schema_design.md
  - 상세설계/05_portfolio_cash_management_design.md
---

# step 066 -- cash_below_threshold 트리거 구현

## Plan

- [ ] 02_strategy_json_schema_design.md 섹션 9 trigger.type 확인
- [ ] CashManager에 cash_below_threshold 트리거 지원 추가
  - shortage_rule.trigger.type = cash_below_threshold + threshold 값
  - handle_shortage 시 trigger 조건 평가 분기
- [ ] BacktestEngine에서 cash_below_threshold 트리거 처리
  - 매수 루프 직전: cash < threshold이면 CashManager 발동
  - trigger 타입에 따라 required_cash 계산 다르게
- [ ] 단위 테스트 작성
  - cash_below_threshold 발동 + 포지션 청산 검증
  - cash >= threshold이면 청산 미발동
  - cash_below_daily_buy_budget과 비교 테스트
- [ ] pytest 회귀 0 FAIL 유지
- [ ] ruff lint 통과

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
