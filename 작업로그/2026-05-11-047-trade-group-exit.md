---
date: 2026-05-11
agent: backtest-engine-developer
phase: 15
status: completed
roadmap_step: "047"
roadmap_impact:
  - 05-l
  - 04-p
related_docs:
  - 상세설계/05_portfolio_cash_management_design.md
  - 상세설계/04_backtest_engine_design.md
  - 상세설계/13_backtest_accuracy_policy_design.md
---

# step 047 — trade_group별 익절/손절 평가 + trailing_stop 엔진 통합 시나리오 회귀

## Plan

> 영향 체크박스 (완료 시 [x] 갱신):
> - 05-l: trade_group별 익절/손절 (현재는 Position 단위)
> - 04-p: trailing_stop 엔진 통합 시나리오 회귀

- [ ] `backend/app/backtest/engine.py` — `_evaluate_exit_position`을 trade_group별로 반복 평가하도록 리팩토링 (각 trade_group의 entry_price 기준 익절/손절)
- [ ] `backend/app/portfolio/portfolio.py` — `evaluate_exit_position` API가 trade_group 단위로 동작하는지 확인 및 수정
- [ ] `backend/tests/backtest/test_trade_group_exit.py` — trade_group 단위 exit 시나리오 테스트 작성
  - 복수 trade_group 보유 시 일부 trade_group만 익절 조건 도달 → 해당 group만 청산
  - 복수 trade_group 보유 시 일부 trade_group만 손절 조건 도달 → 손절 우선 처리 (13.3.2)
  - 동일 봉 동시 익절/손절 도달 → 손절 우선 (보수적)
- [ ] trailing_stop 복수 trade_group 회귀 테스트 (04-p: trailing_stop 엔진 통합 시나리오)
  - update_peak_price 이후 trailing_stop 조건 평가 순서 검증
  - 복수 trade_group의 peak 가격이 각각 독립적으로 추적되는지 확인
- [ ] ruff check → 0 errors / pytest backend/ -q → 기존 1217 PASS + 신규 PASS

## Execution

### 수정/추가 파일

1. **`backend/app/backtest/engine.py`** (모듈 책임: BacktestEngine 오케스트레이터)
   - `101~142`: `_TradeGroupProxy` 클래스 추가 — TradeGroup을 condition_registry의 position 인터페이스로 노출하는 어댑터 (05-l). `entry_price` / `first_entry_date` / `peak_price` / `quantity` 프로퍼티 노출.
   - `484~533`: `_evaluate_held_symbol` 수정 — 기존 `exit_info: tuple | None` 단일 반환 패턴에서 `_evaluate_exit_position_per_tg` 호출로 교체. `sold_all: bool` 반환 기반으로 분기.
   - `976~1140`: `_evaluate_exit_position_per_tg` 신규 — trade_group별 독립 평가 (05-l 핵심). 갭 분기는 tg별 entry_price 기준, trailing_stop은 position 단위 유지, stop_loss / take_profit / max_holding_days는 _TradeGroupProxy 경유.
   - `1142~1175`: `_sell_trade_group_at_price` 신규 — 단일 trade_group 슬리피지/세금 처리 후 portfolio.sell_trade_group 호출.
   - `1177~1197`: `_compute_exit_price_for_tg` 신규 — tg.entry_price 기준 체결가 계산.
   - `1199~1291`: `_evaluate_exit_position` 유지 (하위 호환). 기존 테스트가 직접 호출하지 않으므로 안전. 주석에 NOTE 추가.
   - `1293~1308`: `_compute_exit_price` 유지 (하위 호환).

### 모듈 책임 분리 결정 근거

- `_TradeGroupProxy`는 engine.py 내 모듈 레벨 클래스로 배치 (BacktestEngine 내부 구현 세부사항 — portfolio나 position 모듈에 속하지 않음).
- `_evaluate_exit_position_per_tg`는 BacktestEngine이 오케스트레이터 역할로 적합. 가격 계산(ExecutionModel), 보유 상태(Portfolio.sell_trade_group)는 각 담당 모듈에 위임.
- trailing_stop은 Position.peak_price(공유)를 그대로 사용하므로 position 단위 청산 유지 → `_process_sell_at_price` → `portfolio.sell_symbol_fifo` 경로 재사용.

## Tests

```
backend/.venv/Scripts/python.exe -m ruff check backend/app backend/tests
→ All checks passed!

backend/.venv/Scripts/python.exe -m pytest backend/ -q
→ 1226 passed, 10 warnings (기존 1217 + 신규 9개)
```

### 신규 테스트 (`backend/tests/backtest/test_trade_group_exit.py`)

| 테스트 | 검증 항목 (정확성 정책) | 결과 |
|--------|------------------------|------|
| `test_take_profit_per_trade_group` | 05-l: tg1(100→120.0 target) 일중 익절 / tg2(120→144.0) 미달 | PASS |
| `test_stop_loss_per_trade_group` | 05-l + 13.3: tg1 갭 다운 손절(시가체결) / tg2 일중 손절(68.0) | PASS |
| `test_stop_loss_only_second_trade_group` | 05-l: tg1(stop=85)만 일중 손절, tg2(stop=68) 유지 | PASS |
| `test_trailing_stop_uses_position_peak` | 13.3.5 + 04-p: peak=150, trailing=10%, 2개 tg 동일 peak 공유 → 전체 청산 | PASS |
| `test_trailing_stop_not_triggered_below_peak` | 13.3.5: trailing 미달 시 포지션 유지 | PASS |
| `test_max_holding_days_per_trade_group` | 05-l: tg1(15일) 청산 / tg2(5일) 유지, entry_date 독립 기준 | PASS |
| `test_max_holding_days_both_groups` | 05-l: 두 tg 모두 초과 → 전량 청산 | PASS |
| `test_stop_before_take_profit_same_candle` | 13.3.2: 동일 봉 동시 도달 → 손절 우선(보수적) | PASS |
| `test_gap_down_only_first_trade_group` | 13.3 + 05-l: 갭 분기 trade_group별 독립 판정 | PASS |

## Issues

### 구현 전 확인된 현재 구조 분석

**현재 문제점 (05-l 위반):**
- `_evaluate_exit_position`은 `position.entry_price` (= `Position.avg_entry_price`, 가중평균)를 사용
- 분할 매수 시 각 trade_group의 실제 entry_price가 아닌 전체 평균으로 익절/손절 평가
- 예: tg1=100원, tg2=120원 보유 시 avg=108.57원 → tg1의 실제 익절선(120)이 아닌 평균 기반 익절선으로 평가

**해결 방법:**
- `_TradeGroupProxy` 어댑터로 각 trade_group을 position 인터페이스처럼 노출
- `_evaluate_exit_position_per_tg`에서 trade_group을 (entry_date, trade_group_id) ASC 순서로 순회
- trailing_stop은 position.peak_price 공유가 의미 있으므로 position 단위 유지

**기존 `_evaluate_exit_position` 유지 근거:**
- 기존 골든 테스트 / 단일 매수 시나리오는 avg_entry_price == entry_price이므로 동일 동작
- 단일 매수 시 tg1만 존재 → `_evaluate_exit_position_per_tg`도 동일 결과 (회귀 없음)

**테스트 데이터 설계 실수 2건 (수정 완료):**
1. `test_take_profit_per_trade_group`: adj_open=125 > tg1 target=120 → 갭 업 익절 트리거됨. adj_open=119로 수정.
2. `test_stop_loss_per_trade_group`: adj_low=70 > tg2 stop=68 → tg2 손절 미달. adj_low=60으로 수정.

## Result

- **05-l 해소**: trade_group별 entry_price 기준 익절/손절 평가 구현 완료. BacktestEngine._evaluate_exit_position_per_tg가 take_profit / stop_loss / max_holding_days를 각 tg.entry_price / tg.entry_date 기준으로 독립 평가.
- **04-p 해소**: trailing_stop 엔진 통합 시나리오 회귀 테스트 작성 및 PASS. Position.peak_price 공유 기준 전체 청산 동작 검증.
- **결정론 보장**: trade_group 순회 시 `(entry_date, trade_group_id) ASC` 명시 정렬. dict 순회 미의존.
- **look-ahead bias**: 기존 `update_peak_price` 타이밍(exit 평가 후) 유지. trailing_stop은 여전히 전일까지의 peak 기준.
- **정확성 정책 적용**: 13.3 (일중 익절/손절), 13.3.2 (동일 봉 손절 우선), 13.3.5 (trailing_stop peak), 13.9.3 (entry_price 불변), 05-l (tg별 평가).

## Follow-ups

- `_evaluate_exit_position` (구 메서드) 하위 호환 유지 중 — 향후 외부 호출자가 없으면 제거 가능 (현재는 안전을 위해 유지).
- BacktestConfig에 `allow_pyramiding` 필드가 없으므로 분할 매수 기능을 UI/백테스트 실행 경로에서 제공하려면 별도 step 필요.
- `_process_sell_at_price` (FIFO 경로) vs `_sell_trade_group_at_price` (tg 직접 경로) 두 경로가 공존 — trailing_stop은 FIFO 경로 유지(position 전체), 나머지는 tg 직접 경로. 이 분리가 명확하게 문서화되어 있는지 확인 권장.

## 메인 세션 마무리 체크

- [ ] status를 completed로 변경
- [ ] 작업로그/README.md "최근 작업" 표에 1행 추가
- [ ] Phase 상태가 변경되었으면 Phase 표 갱신
- [ ] Follow-ups 중 다음 작업 후보로 옮길 항목 정리
- [ ] **PM 에이전트 호출 → 로드맵.md 갱신** — "step 047 마무리" 지시. PM이 Phase 로드맵 step ✅ + 영향 체크박스 [x] (05-l, 04-p) + 진행률 표 손계산을 직접 Edit.
- [ ] `git commit` (단일 커밋)
- [ ] **Phase 15 마지막 step이므로**: test-engineer 호출 후 ship-go 시 `git push origin main` 자동 실행 (의무)
