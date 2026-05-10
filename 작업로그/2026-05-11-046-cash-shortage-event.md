---
date: 2026-05-11
agent: backtest-engine-developer
phase: 15
status: completed
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

### 수정 파일

**`backend/app/backtest/engine.py:125`**
- `EVENT_REASON_CASH_SHORTAGE = "buy_skipped_cash_shortage"` 상수 추가 (기존 EVENT_REASON_* 블록 마지막에 추가)
- `_maybe_buy:1150` — `execution.net_amount > self.portfolio.cash` 분기에 `_log_event` 호출 추가
  - detail: `{"required_cash": int(...), "available_cash": int(...)}`
  - CashManager 유무 / enabled 여부와 무관하게 예산 부족이면 항상 기록 (05-j)

**`backend/tests/backtest/test_cash_shortage_event.py`** (신규)
- 7개 테스트 케이스 작성

### 모듈 책임 분리 결정

- `EVENT_REASON_CASH_SHORTAGE` 상수: `engine.py` 상단의 기존 `EVENT_REASON_*` 블록에 통합
  (event_log.py가 별도로 존재하지 않아 engine.py가 상수 보관소 역할)
- event_log 기록: `BacktestEngine._maybe_buy` 내에서 직접 `_log_event` 호출
  (Portfolio/CashManager는 skip 사유를 모름 — 오케스트레이터인 BacktestEngine이 판단)

### 05-k 검증 결과 (순서 정합성)

`_evaluate_held_symbol` 호출 순서 확인:
1. `portfolio.update_market_price(adj_close)` — current_price만 갱신, peak 미변경
2. `_evaluate_exit_position(...)` — trailing_stop 평가 시 peak = 전일까지의 high
3. exit_signal 평가 → next_open 매도
4. `portfolio.update_peak_price(adj_high)` — 평가 후 당일 high를 peak에 반영

정확성 정책 13.3.5 완전 준수. 수정 불필요 — **검증 완료**.

## Tests

### 실행 명령

```
backend/.venv/Scripts/python.exe -m ruff check backend/app backend/tests
→ All checks passed!

backend/.venv/Scripts/python.exe -m pytest backend/ -q
→ 1217 passed, 10 warnings in 21.31s
```

### 신규 테스트 파일: `backend/tests/backtest/test_cash_shortage_event.py`

| 테스트 | 정확성 정책 매핑 | 결과 |
|---|---|---|
| test_buy_skipped_event_logged_when_cash_insufficient | 05-j | PASS |
| test_buy_succeeds_after_cash_manager_no_event | 05-j (역검증) | PASS |
| test_buy_skipped_after_cash_manager_still_insufficient | 05-j | PASS |
| test_buy_skipped_no_cash_manager_logs_shortage | 05-j | PASS |
| test_update_peak_price_uses_daily_high | 13.3.5 + 05-k | PASS |
| test_trailing_stop_uses_prev_day_high_not_today | 13.3.5 + look-ahead bias | PASS |
| test_normal_buy_no_shortage_event | 05-j (역검증) | PASS |

기존 1210 PASS → 1217 PASS (7 신규, 0 회귀)

## Issues

### 발견된 문제 (수정 완료)

1. **테스트 설계 실수 — 갭 차단**: `test_trailing_stop_uses_prev_day_high_not_today` 첫 버전에서 Day3 open=200을 Day2 close=110 대비 +81.8% 갭으로 설계해 `max_gap_pct_for_entry=5.0` 기본 정책에 걸려 매수가 0건이 됨. 시나리오를 완만한 가격(Day2→Day3 갭 2.7%)으로 재설계해 해결.

### 정책 충돌 없음

- `EVENT_REASON_CASH_SHORTAGE`는 정확성 정책 문서에 명시적으로 없었으나, 05-j 요구사항에 따라 추가. 충돌 없음.
- CashManager disabled/None 상태에서도 동일하게 기록하는 것이 합리적 (skip 사유는 동일하므로). 정책 문서에 모호한 분기점이었으나 보수적으로 "항상 기록"으로 결정.

## Result

### 05-j 해소: buy_skipped_cash_shortage event_log 추가

- `EVENT_REASON_CASH_SHORTAGE = "buy_skipped_cash_shortage"` 상수 추가
- `BacktestEngine._maybe_buy`에서 `execution.net_amount > self.portfolio.cash` 분기에 event_log 기록
- CashManager enabled 여부와 무관하게 기록 (보수적)
- detail 포맷: `{"required_cash": int, "available_cash": int}`

### 05-k 해소: update_market_price / update_peak_price 호출 순서 검증

- 현재 `_evaluate_held_symbol`의 호출 순서 이미 정확성 정책 13.3.5 준수
- `update_market_price(adj_close)` → exit_position 평가 → `update_peak_price(adj_high)` 순서 정확
- 수정 불필요 — 검증 완료

### 적용 정확성 정책 절번호

- **13.3.5**: trailing_stop peak는 전일까지의 high (update_peak_price 호출 순서)
- **05-j**: buy_skipped_cash_shortage event_log (신규 정책 추가)

### 결정론 보장

- `EVENT_REASON_CASH_SHORTAGE` 기록 위치: priority 정렬 후 순차 매수 루프 내에서 기록되므로 결정론 유지
- 기존 결정론 (`sorted()` 기반 후보 정렬) 미변경

### look-ahead bias 검증

- `update_peak_price(adj_high)`가 항상 `_evaluate_exit_position` **이후** 호출됨을 확인
- 청산된 경우 `return`으로 step 4를 건너뛰어 청산 포지션의 peak 갱신이 불필요하게 발생하지 않음

## Follow-ups

- `EVENT_REASON_CASH_SHORTAGE`를 DB 영속화(backtest_event_logs 테이블) 대상에 포함시켜야 함 (후속 step 담당)
- 현재 `event_log.py` 파일이 존재하지 않음 — 모든 EVENT_* 상수가 `engine.py`에 있음. 향후 이벤트 종류가 늘어나면 별도 `event_log.py` 모듈로 분리 고려 (단, 현재 구조로도 동작에 문제 없음)
- 13/02번 문서 갱신 필요 여부: `EVENT_REASON_CASH_SHORTAGE`는 13번 문서에 명시되지 않은 새 상수이므로 필요 시 `13_backtest_accuracy_policy_design.md` §04-j 절에 추가 권고

## 메인 세션 마무리 체크

- [ ] status를 completed로 변경
- [ ] 작업로그/README.md "최근 작업" 표에 1행 추가
- [ ] PM 에이전트 호출 → 로드맵.md 갱신 — "step 046 마무리" 지시
  - (a) Phase 15 로드맵 step 046 ⬜→✅
  - (b) 체크박스 05-j, 05-k [x] 갱신
  - (c) 진행률 표 손계산
- [ ] git commit (단일 커밋)
