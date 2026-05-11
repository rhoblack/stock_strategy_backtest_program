---
date: 2026-05-11
agent: backtest-engine-developer
phase: 21
status: in_progress
roadmap_step: "062"
roadmap_impact:
  - 12-l
related_docs:
  - 상세설계/12_testing_validation_design.md
---

# Golden 실제 시세 fixture 구비 + golden_02~04 시나리오 재정비

## Plan

- [ ] `backend/tests/golden/fixtures/` 디렉토리에 실제 시세 CSV 파일 생성
  - samsung_5y_prices.csv — 결정론적 합성 데이터 (실제 pykrx 없이 생성 가능, 설계서 §15.2)
  - kosdaq_top10_3y_prices.csv — 결정론적 합성 데이터
  - trading_calendar.csv — 거래일 목록
- [ ] golden_02 시나리오 재정비: 거래량 돌파 + 다종목 + priority=trading_value_desc (파일 기반)
- [ ] golden_03 시나리오 재정비: 부분 매도 + cash_shortage_rule lowest_return (파일 기반)
- [ ] golden_04 시나리오 재정비: allow_pyramiding=true + weighted_average (파일 기반)
- [ ] 기존 test_phase1_golden.py 회귀 유지 (합성 데이터 기반 6건 PASS)
- [ ] 신규 파일 기반 golden 테스트: test_phase21_golden_real_fixture.py
- [ ] pytest 전체 회귀 1399 PASS 기준 유지
- [ ] ruff All checks passed

## Execution

실행 중 또는 완료 후 작성. 어떤 파일을 어떻게 수정했는지, 어떤 결정을 내렸는지.

```text
(작업 에이전트가 채움)
```

## Tests

```text
(작업 에이전트가 채움)
```

## Issues

```text
(작업 에이전트가 채움)
```

## Result

```text
(작업 에이전트가 채움)
```

## Follow-ups

```text
(작업 에이전트가 채움)
```

## 메인 세션 마무리 체크

- [ ] status를 completed로 변경
- [ ] 작업로그/README.md "최근 작업" 표에 1행 추가
- [ ] Phase 상태가 변경되었으면 Phase 표 갱신
- [ ] Follow-ups 중 다음 작업 후보로 옮길 항목 정리
- [ ] **PM 에이전트 호출 → 로드맵.md 갱신** — "step 062 마무리" 지시. PM이 Phase 로드맵 step ✅ + 12-l [x] + 진행률 표 손계산을 직접 Edit.
- [ ] `git commit` (단일 커밋)
- [ ] **Phase 21 마지막 step이라면**: `test-engineer` 에이전트 호출 후 ship-go 받으면 `git push origin main` 실행 (의무)
