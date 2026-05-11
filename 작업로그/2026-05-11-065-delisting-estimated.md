---
date: 2026-05-11
agent: backtest-engine-developer
phase: 22
status: in_progress
roadmap_step: "065"
roadmap_impact:
  - 13-u
related_docs:
  - 상세설계/13_backtest_accuracy_policy_design.md
  - 상세설계/04_backtest_engine_design.md
---

# step 065 -- delisting_estimated 처리 (종가x0.5 강제매도)

## Plan

- [ ] 13_backtest_accuracy_policy_design.md 섹션 4.5 확인
- [ ] BacktestEngine.run에 delisting_estimated_dates 인자 추가
  - {symbol: date} 매핑 (delisting_dates와 유사한 구조)
- [ ] _force_sell_delisted_estimated_today 메서드 구현
  - 체결가 = adj_close * 0.5 (정리매매 데이터 없는 경우 보수적 추정)
  - exit_reason = "delisting_estimated"
  - event_log에 force_sell_delisting_estimated 기록
- [ ] 날짜 루프에서 delisting_dates 처리 직후 (또는 직전)에 배치
- [ ] 단위 테스트 작성
  - 강제매도 발동 + 가격 50% 검증
  - event_log reason 확인
  - delisting_dates (100%)와 delisting_estimated_dates (50%) 비교 테스트
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
