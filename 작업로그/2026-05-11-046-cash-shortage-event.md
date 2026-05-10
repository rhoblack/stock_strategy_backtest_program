---
date: 2026-05-11
agent: backtest-engine-developer
phase: 15
status: in_progress
roadmap_step: "046"
roadmap_impact:
  - 05-j
  - 05-k
related_docs:
  - 상세설계/05_portfolio_cash_management_design.md
  - 상세설계/04_backtest_engine_design.md
  - 상세설계/13_backtest_accuracy_policy_design.md
---

# step 046 — buy_skipped_cash_shortage 이벤트 + update_market_price/update_peak_price 정합 검증

## Plan

- [ ] `backend/app/backtest/engine.py` — `_maybe_buy`에서 CashManager 강제 매도 후에도 예산 부족하면 `EVENT_REASON_CASH_SHORTAGE` event_log 추가 (05-j)
- [ ] `backend/app/backtest/engine.py` — `update_market_price` / `update_peak_price` 호출 순서가 정확성 정책(13.3.5 prev-high 보장)에 맞는지 확인 및 필요 시 수정 (05-k)
- [ ] `backend/tests/backtest/test_cash_shortage_event.py` — buy_skipped_cash_shortage 시나리오 테스트 신규 작성
  - 예산 충분 → 정상 매수 (event_log 없음)
  - CashManager 강제 매도 후 예산 복구 성공 → 정상 매수
  - CashManager 강제 매도 후에도 여전히 부족 → EVENT_REASON_CASH_SHORTAGE event_log 추가
- [ ] ruff check → 0 errors / pytest backend/ -q → 기존 1210 PASS + 신규 PASS

## Execution

(작업 에이전트가 채움)

## Tests

(작업 에이전트가 채움)

## Issues

(작업 에이전트가 채움)

## Result

(작업 에이전트가 채움)

## Follow-ups

(작업 에이전트가 채움)

## 메인 세션 마무리 체크

- [ ] status를 completed로 변경
- [ ] 작업로그/README.md "최근 작업" 표에 1행 추가
- [ ] PM 에이전트 호출 → 로드맵.md 갱신 — "step 046 마무리" 지시
  - (a) Phase 15 로드맵 step 046 ⬜→✅
  - (b) 체크박스 05-j, 05-k [x] 갱신
  - (c) 진행률 표 손계산
- [ ] git commit (단일 커밋)
