---
date: 2026-05-11
agent: backtest-engine-developer
phase: 22
status: in_progress
roadmap_step: "064"
roadmap_impact:
  - 02-s
related_docs:
  - 상세설계/02_strategy_json_schema_design.md
  - 상세설계/04_backtest_engine_design.md
  - 상세설계/13_backtest_accuracy_policy_design.md
---

# step 064 -- priority 3종 엔진 구현

## Plan

- [ ] 02_strategy_json_schema_design.md 섹션 7 확인
- [ ] config.py SUPPORTED_PRIORITY_METHODS에 market_cap_asc, volume_ratio_desc, price_change_desc 추가
- [ ] engine.py _apply_priority에 3가지 알고리즘 구현
  - market_cap_asc: market_cap 오름차순 + symbol ASC
  - volume_ratio_desc: volume / avg_volume 내림차순 + symbol ASC
  - price_change_desc: (close - prev_close) / prev_close 내림차순 + symbol ASC
- [ ] 결정론: 모든 method 마지막 정렬 키 = symbol ASC (CLAUDE.md #8)
- [ ] look-ahead bias: 모든 점수는 today row 컬럼만 사용
- [ ] 단위 테스트 작성 (3종 + symbol_asc tie-breaker 검증)
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
