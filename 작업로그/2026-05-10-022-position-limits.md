---
date: 2026-05-10
agent: backtest-engine-developer
phase: 10
status: completed
roadmap_step: 022
roadmap_impact:
  - 04-l  # max_positions / max_daily_entries
  - 04-m  # daily_buy_budget
related_docs:
  - 상세설계/04_backtest_engine_design.md
  - 상세설계/05_portfolio_cash_management_design.md
  - 작업로그/2026-05-10-020-backtest-engine-multi-symbol.md
  - 작업로그/2026-05-10-021-priority-and-random-seed.md
---

# Step 022 — max_positions / max_daily_entries / daily_buy_budget (04-l + 04-m)

021의 priority 정렬 직후 자리에 포지션 한도 적용. priority가 정한 순서를 따라 매수 시도 → 한도 도달 시 그 이후 후보 skip.

## Plan

### A) BacktestConfig 확장 (021 패턴 따름)
- [ ] `backend/app/backtest/config.py`에 신규 필드:
  - `max_positions: int | None = None` — 동시 보유 종목 수 상한 (None이면 무제한)
  - `max_daily_entries: int | None = None` — 하루 신규 매수 종목 수 상한 (None이면 무제한)
  - `daily_buy_budget: float | None = None` — 하루 매수 가능 총 금액 상한 (None이면 무제한)
- 화이트리스트 검증 (정수 양수, float 양수)
- 021의 `__post_init__` 패턴 따름

### B) BacktestEngine — _apply_position_limits 헬퍼 신설
- [ ] `backend/app/backtest/engine.py`:
  - 021 `_apply_priority` 직후 `_apply_position_limits` 신설
  - 입력: priority 정렬된 후보 리스트 + 현재 portfolio 상태 + today
  - 처리:
    1. **max_positions**: 현재 보유 + 신규 매수 후보 합이 max_positions 초과 시 후보 잘라냄 (priority 순서 유지)
    2. **max_daily_entries**: 후보 리스트 길이가 max_daily_entries 초과 시 잘라냄
    3. **daily_buy_budget**: 매수 루프 진행 중 누적 매수 금액 추적, 초과 시 그 후보부터 skip
  - 결정론: priority 순서 유지 (잘라내기만)
- [ ] 매수 루프 (`engine.py:240-254` 근처)에서 daily_buy_budget 누적 추적

### C) 정책 결정 사항
- max_positions와 max_daily_entries는 사전 잘라내기 (priority 순서 유지)
- daily_buy_budget는 매수 루프 진행 중 동적 체크 (실 체결 비용 누적)
- 한도에 의해 skip된 후보는 cash_events 또는 event_log에 기록할지 결정 (event_log는 step 023 영역, 본 step에서는 단순 skip)

### D) 호환성
- 모든 한도 default=None → 020·021 동작 유지 → Phase 1 골든 frozen
- max_positions=1 시나리오는 단일 종목 백테스트 정합

### E) 테스트
- [ ] `backend/tests/backtest/test_position_limits.py` 신규:
  - max_positions=2 + 후보 4개 → 보유 가능한 만큼만 매수
  - max_positions 도달 후 후보 skip (priority 순서 유지)
  - max_daily_entries=1 + 후보 3개 → 첫 후보만 매수
  - daily_buy_budget=100,000원 + 후보 누적 비용 → 초과 후보 skip
  - 한도 default=None → 020·021 동작 유지
  - max_positions와 보유 포지션 매도 후 같은 today 재진입 가드 (held_at_open_set 기반 020 정책 유지)
  - 결정론: 동일 입력 5회 반복 동일

### F) 회귀
- [ ] 전체 pytest (Phase 1 골든 + 020·021 회귀)
- [ ] ruff
- [ ] 016 head 가드 1건 알려진 무관

### 절대 금지
- StrategyEngine, ExecutionModel, conditions/* / portfolio/* 절대 수정
- API / schemas / services / market_data/* / models/* 절대 수정
- BacktestEngine에 신호 생성 / 가격 계산 로직 직접 추가 금지
- **event_log / 거래정지·상한가·하한가·상장폐지 강제 매도 도입 금지** — step 023 영역
- 020·021 호환성 유지: 단일 df 자동 wrap, held_at_open_set 가드, priority
- 015 호환성 유지
- 결정론 깨기

### 다음 step (023) 인계 정보
- _apply_position_limits 위치 + 한도에 의해 skip된 후보 정보 (event_log 후보)
- 매수 루프 cash_events 기록 패턴

## Execution

### 작성/수정 파일

- `backend/app/backtest/config.py`
  - 모듈 docstring 갱신 (config.py:1-15) — 022 한도 3종 도입 명시
  - `BacktestConfig.max_positions: int | None = None` (config.py:64)
  - `BacktestConfig.max_daily_entries: int | None = None` (config.py:65)
  - `BacktestConfig.daily_buy_budget: float | None = None` (config.py:66)
  - `__post_init__` 한도 검증 (config.py:104-141) — int/float 양수 + bool 거부
    (True/False가 int 서브타입이지만 의미 모호 → 명시적 거부)

- `backend/app/backtest/engine.py`
  - 모듈 docstring 갱신 (engine.py:14-19) — 022 한도 흐름 명시
  - run() docstring 흐름 갱신 (engine.py:54-67) — 매수 후보 수집 → 정렬 → 한도 → 매수
  - 매수 루프 (engine.py:259-289) — `_apply_position_limits` 호출 + `cumulative_buy_cost` 누적
  - `_apply_position_limits` 신규 (engine.py:507-558) — max_positions / max_daily_entries
    사전 잘라내기 (priority 순서 유지, 앞에서부터)
  - `_maybe_buy` 시그니처 변경 (engine.py:730-841) — `cumulative_buy_cost: float = 0.0`
    keyword-only 인자, 반환 타입 `None → float`. 매수 성공 시 `execution.net_amount`,
    skip/실패 시 `0.0` 반환. 매수 직전 `daily_buy_budget` 동적 체크 추가.

- `backend/tests/backtest/test_position_limits.py` (신규, 22건)

### 모듈 책임 분리

- BacktestConfig: 한도 검증 (정수/양수 + bool 거부) — 엔진 도달 전 invalid 차단
- BacktestEngine:
  - 사전 한도(`max_positions`, `max_daily_entries`)는 `_apply_position_limits`로
    분리 — `_apply_priority` 다음 정렬-필터 단계로 깔끔히 격리
  - 동적 한도(`daily_buy_budget`)는 매수 루프 + `_maybe_buy` 내부 — 실 체결
    `net_amount`가 필요해 사전 차단 불가, 호출자가 누적값 추적
- StrategyEngine / Portfolio / ExecutionModel / conditions / portfolio/* / API / schemas
  / services / market_data/* / models/* 미수정

## Tests

```bash
cd backend && .venv/Scripts/pytest.exe tests/backtest/test_position_limits.py -v
# 22 passed in 0.58s

cd backend && .venv/Scripts/pytest.exe tests/integration/test_phase1_golden.py \
    tests/backtest/test_backtest_engine.py \
    tests/backtest/test_backtest_engine_multi_symbol.py \
    tests/backtest/test_priority.py -v
# 62 passed (Phase 1 골든 6건 + 015 단일 + 020 multi + 021 priority 모두 회귀 없음)

cd backend && .venv/Scripts/pytest.exe --tb=line -q
# 587 passed, 1 failed (016 alembic head 가드, 알려진 무관)
# = 565 baseline + 22 신규

cd backend && .venv/Scripts/python.exe -m ruff check \
    app/backtest/config.py app/backtest/engine.py tests/backtest/test_position_limits.py
# All checks passed!
```

### 정확성 정책 13.x 매핑

| 정책 절 | 검증 테스트 |
|---|---|
| 13.8 (priority + 한도 흐름) | `test_max_positions_respects_priority_order` / `test_daily_buy_budget_with_priority_respects_order` |
| 13.12 (결정론) | `test_position_limits_deterministic_across_5_runs` (5회 동일) |
| 13.12.1 (dict 순회 의존 금지) | priority 순서 유지하며 앞에서부터 자름 — 순회 의존 없음 |
| 13.17 (한도 검증) | A 그룹 (config 검증 7건) + B/C/D (한도 동작 11건) |

## Issues

### default=None vs 0 — None 채택 (021 패턴 정합)

3개 옵션 검토:
1. **None=무제한 (채택)** — 021의 `random_seed=None` 패턴과 정합. 0은 "한도가
   있는데 0개" → 매수 자체 차단으로 의미 있음 → 별도 ValueError로 거부.
2. 0=무제한 — 0이 "한도 없음"인지 "0개 한도"인지 모호. 023의 event_log 도입 시
   skip 사유 표기에서도 모호.
3. sentinel(`-1`) — Python 컨벤션 위반.

`__post_init__`이 0/음수를 ValueError로 거부 → "보이지 않는 차단" 방지.

### bool은 int 서브타입 → 명시적 거부

Python에서 `True == 1`, `False == 0`, `isinstance(True, int)`. 022의 한도 필드에
`max_positions=True`가 들어오면 isinstance 체크를 통과하지만 의미는 "1개" — 사용자
실수 가능성 높음. `isinstance(self.max_positions, bool)`로 명시 거부 (테스트:
`test_config_max_positions_bool_raises`).

### max_positions 산정 — held_at_open_set 기반 (같은 today 회전 매매 방지)

020의 `held_at_open_set` 가드는 "today 시작 시점 보유 종목은 같은 today에 청산되어도
매수 후보에서 제외". 022의 `_apply_position_limits`는 이 정합성을 그대로 따름:

- `len(held_at_open_set)`을 현재 보유 수로 사용
- 같은 today에 매도된 종목이 있어도 그 슬롯은 그날 새 매수에 즉시 재할당되지 않음
  (entry candidate 단계에서 이미 차단됨)
- 따라서 `available_slots = max(0, max_positions - len(held_at_open_set))`은
  실제 매수 가능 슬롯과 정확히 일치

향후 `allow_pyramiding=True` 도입 시 이 의미는 유지되어야 함 (같은 봉 회전 매매 방지).

### daily_buy_budget — 동적 체크가 결정적인 이유

`_apply_position_limits`에서 사전 차단할 수도 있지만 `position_size_amount`만 알고
실 `net_amount`(slippage + fee 적용 후)는 모름. 비용을 정확히 알려면 매수 루프에서
`execution.net_amount`를 봐야 함. 따라서:

- `_maybe_buy`가 `cumulative_buy_cost`를 키워드 인자로 받음
- 매수 성공 시 `execution.net_amount` 반환, skip 시 `0.0` 반환
- 호출자(매수 루프)가 누적 추적

결정론: priority 순서로 매수 시도 → 같은 입력이면 같은 cumulative 진행 → 같은 skip 결정.

### look-ahead bias 검증

- max_positions / max_daily_entries: today row 정보만 사용 (entry candidates는 today 신호)
- daily_buy_budget: today 매수의 누적 비용 — 다음 날 가격 미참조
- next_open / next_volume은 매수 체결 단계에서만 사용 (기존 흐름 유지)

### 결정론 보장 메커니즘

- `_apply_position_limits`는 `candidates[:cutoff]`로 앞에서부터 자름 → priority 순서 보존
- daily_buy_budget도 priority 순서대로 매수 시도, 누적이 초과하면 그 후보부터 skip
- 어떤 곳에서도 dict/set 순회 의존 없음 (021 동일 보장)
- 5회 반복 매수 순서 + final_equity 동일 검증 (`test_position_limits_deterministic_across_5_runs`)

## Result

### 적용 정확성 정책

- 13.8 (priority + max_daily_entries / max_positions / daily_buy_budget — 04 §11 흐름 7번)
- 13.12 (결정론 — priority 순서 유지하며 앞에서부터 자름, dict 순회 미사용)
- 13.17 (한도 검증 항목 — config 화이트리스트 + 동작 단위 테스트)
- 04 §6 step 6/7 (priority → max_daily_entries → max_positions → daily_buy_budget)
- 04 §11.1 처리 흐름 7번/8번 (한도 적용 자리)

### look-ahead bias 차단 검증

- 한도 체크는 today row + portfolio 현재 상태 기반 (next 가격/거래량 무관)
- daily_buy_budget 누적은 today 내 실 체결 비용 (미래 데이터 미사용)

### Phase 1 골든 fixture 9지표 frozen 회귀

`tests/integration/test_phase1_golden.py` 6건 PASS — 모든 한도 default=None →
021 동작 보존 → 020 동작 보존 → 015 baseline 유지. 587/588 전체 회귀에서 신규
22건만 추가, 기존 565건 변동 없음 (1 fail은 016 alembic head 가드 — 본 step 무관).

### 결정론 검증

- 모든 한도 활성화 (max_positions=3 + max_daily_entries=3 + daily_buy_budget=1.5M)
  + 5회 반복: 매수 순서 + final_equity 동일 (`test_position_limits_deterministic_across_5_runs`)
- 같은 trading_value 동점 시 symbol ASC tie-breaker 유지 (`test_max_positions_respects_priority_order`)

### 다음 step (023) 인계 정보

- **한도 skip된 후보 정보 위치**:
  - `_apply_position_limits` (engine.py:507-558) — `candidates[:cutoff]`로 잘라낸
    뒤의 `candidates[cutoff:]`가 사전 한도(max_positions / max_daily_entries) 사유로
    skip된 후보. 본 step에서는 단순 제거. 023이 event_log 도입 시 이 자리에서
    `skipped_reason="max_positions"` / `"max_daily_entries"`로 기록 가능.
  - `_maybe_buy` (engine.py:828-833) — daily_buy_budget 초과 시 `return 0.0` 직전.
    023에서 `event_log`에 `"skipped_daily_buy_budget"` 기록 자리.
- **현재 cash_events 패턴 참조**: `engine.py:711-715` (CashManager.handle_shortage 결과를
  `self.cash_events.extend(events)` — list 누적). event_log도 동일 패턴 권장.
- **023 추가 강제 매도** (거래정지 / 상장폐지 / 상한가 / 하한가):
  - 보유 평가 단계 (`_evaluate_held_symbol`)에서 분기 추가 자리
  - 거래정지 = `volume == 0`일 때 매도 시도 차단 (현재는 단순 skip — `engine.py:233`)
  - 022는 신규 매수 후보에만 영향, 강제 매도와 분리됨

### BacktestConfig 신규 필드 명세

| 필드 | 타입 | default | 검증 정책 |
|---|---|---|---|
| `max_positions` | `int \| None` | `None` (무제한) | int + 양수 (bool 거부) |
| `max_daily_entries` | `int \| None` | `None` (무제한) | int + 양수 (bool 거부) |
| `daily_buy_budget` | `float \| None` | `None` (무제한) | int/float + 양수 (bool 거부) |

### `_apply_position_limits` 시그니처 + 흐름

```python
def _apply_position_limits(
    self,
    *,
    candidates: list[tuple[str, pd.Series]],   # priority 정렬된 후보
    held_at_open_set: set[str],                 # today 시작 시점 보유
) -> list[tuple[str, pd.Series]]:               # 잘라낸 후보 (앞에서부터)
```

흐름:
1. 모든 한도 None → 입력 그대로 반환 (021 동작 보존)
2. `cutoff = len(candidates)` 시작
3. max_positions 활성화 → `available_slots = max(0, max_positions - len(held_at_open_set))`,
   `cutoff = min(cutoff, available_slots)`
4. max_daily_entries 활성화 → `cutoff = min(cutoff, max_daily_entries)`
5. `candidates[:cutoff]` 반환 (priority 순서 유지)

### 매수 루프 daily_buy_budget 누적 추적 방식

```python
cumulative_buy_cost = 0.0
for symbol, row in entry_candidates:
    ...  # held/이미 보유 중 차단
    cost = self._maybe_buy(symbol, row, today, result, cumulative_buy_cost=cumulative_buy_cost)
    cumulative_buy_cost += cost  # 매수 성공 → net_amount, skip → 0.0
```

`_maybe_buy` 내부에서 매수 직전 `cumulative + execution.net_amount > daily_buy_budget`
체크 → skip 시 `return 0.0` (호출자 누적값에 0 더해짐 = 무영향).

## Follow-ups

- **04번 문서 §11.1 흐름 7번/8번 갱신** — "max_daily_entries 만큼 상위 추출" / "daily_buy_budget
  한도 확인" / "max_positions 한도 확인" 명세는 이미 있으므로 본 step의 구현 정합성 OK. 다만:
  - "max_positions: 보유 + 신규 후보 합" 의미를 명시 (보유 슬롯 차감) — 현재 본문에 누락
  - "daily_buy_budget: 실 체결 net_amount 누적 vs position_size_amount 추정" 정책 명시
- **04번 §11.1 / 13.8 갱신** — 모든 한도 default=None 정책 + 0/음수 ValueError 정책 추가 권장
- **step 023** — `_apply_position_limits`의 `candidates[cutoff:]`(잘려나간 후보)와
  `_maybe_buy`의 `daily_buy_budget` skip 분기에서 `event_log` 기록 추가. 본 step의
  구조를 그대로 따라 (수집 → 정렬 → 한도 → 매수 루프 + event_log) 5단계로 확장.
- **step 023+** — 거래정지·상한·하한·상장폐지 강제 매도. `_evaluate_held_symbol` 보유
  평가 단계에 분기 추가. 022 한도와 분리됨.
- **PriceLoader / Phase 11+** — `position_size_amount` vs `daily_buy_budget`이
  position_sizing 정책 (fixed_amount / fixed_pct / volatility_target) 도입 시 어떻게
  연동될지 정책 결정 필요 (05번 문서 §position_sizing 절).

## 메인 세션 마무리 체크

- [ ] status를 completed로 변경
- [ ] 작업로그/README.md 갱신
- [ ] PM 호출 → 로드맵.md 갱신 (04-l, 04-m [x] / Phase 10 step 022 ✅)
- [ ] git commit (Phase 10 마지막 step 아니므로 push 보류)
