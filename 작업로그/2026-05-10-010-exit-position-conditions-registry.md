---
date: 2026-05-10
agent: condition-author
phase: 8 (리뷰 011 후속)
status: completed
related_docs:
  - 상세설계/03_condition_registry_engine_design.md
  - 상세설계/02_strategy_json_schema_design.md
  - 상세설계/13_backtest_accuracy_policy_design.md
  - 리뷰/2026-05-10-011-설계서기반-PM주관-코드리뷰.md
---

# exit_position 조건 3종 Registry 등록 (stop_loss / max_holding_days / trailing_stop)

리뷰 011 C1·H5 해소의 선결조건. 현재 backend/app/backtest/engine.py가 stop_loss/max_holding_days를 if/elif 하드코딩으로 직접 평가하고 있고 take_profit은 Registry 메타로만 등록되어 있을 뿐 엔진이 함수를 호출하지 않는다. 본 작업에서 ConditionRegistry에 정식 등록하여 Wave B에서 engine.py가 registry.evaluate_position만 호출하도록 만든다.

## Plan

- [ ] `상세설계/03_condition_registry_engine_design.md` 4~5절 (포지션 조건 시그니처, requires_position 메타) 정독
- [ ] `상세설계/13_backtest_accuracy_policy_design.md` 13.3 (일중 익절/손절 우선순위), 13.3.5 (trailing_stop peak prev-high) 정독
- [ ] `상세설계/02_strategy_json_schema_design.md` 5.2 (exit_position 섹션 schema) 정독
- [ ] `backend/app/strategy/conditions/exit_position.py`에 다음 3개 함수 추가:
  - `stop_loss(position, market_row, condition) -> tuple[bool, str | None, float | None, int | None]`
  - `max_holding_days(position, market_row, condition) -> tuple[...]`
  - `trailing_stop(position, market_row, condition) -> tuple[...]` (peak_price는 position에서 읽음, 이번 작업에서 갱신 책임은 안 짐)
- [ ] `@condition_registry.register(type, requires_position=True, category="exit_position")` 데코레이터 적용
- [ ] `backend/app/strategy/condition_definitions.py`에 메타데이터 3건 추가 (sentence_template / parameters / allowed_in=["exit_position"])
- [ ] pytest 신규 테스트:
  - 정상 도달 케이스 / 미도달 케이스 / 경계값 / 갭 vs 일중
  - take_profit과의 우선순위(동일 봉 손절 우선 — 13.3 정책) 단위 테스트
- [ ] 회귀: 전체 pytest 통과 (300건 이상 유지) + ruff
- [ ] **engine.py / portfolio.py 절대 수정 금지** — Wave B의 backtest-engine-developer 영역

## Execution

### 수정 파일

- `backend/app/strategy/conditions/exit_position.py` — 기존 take_profit 외에 3개 조건 함수 + META 추가
  - `stop_loss(position, market_row, condition) -> tuple[bool, str | None]` (line 117~189)
    - `@condition_registry.register("stop_loss", requires_position=True, category="exit_position")`
    - `STOP_LOSS_META` (line 192~218)
  - `_row_date(market_row) -> date` 헬퍼 (line 226~256) — dict의 `"date"` 키 또는 pandas Series.name (Timestamp) 양쪽 지원
  - `max_holding_days(position, market_row, condition)` (line 259~298)
    - `MAX_HOLDING_DAYS_META` (line 301~317)
  - `trailing_stop(position, market_row, condition)` (line 325~377)
    - peak_price는 position에서 읽기만 하고 갱신 책임 없음 (look-ahead bias 방지 — 13.3.5)
    - `TRAILING_STOP_META` (line 380~407)
  - 모듈 docstring을 4개 조건 모두 설명하도록 갱신 (line 1~33)

- `backend/app/strategy/condition_definitions.py` — ALL_DEFINITIONS에 새 META 3건 추가 (line 29~31)

- `backend/tests/strategy/conditions/test_exit_position.py` — 35건 신규 테스트 추가
  - stop_loss 10건, max_holding_days 12건, trailing_stop 11건, stop+take 동시 도달 1건, 카탈로그 등록 1건
  - 기존 take_profit 테스트 10건은 그대로 유지

### 적용한 설계서 절번호

- 03번 §3 (ConditionRegistry), §4 (조건 함수 시그니처), §5 (지표/조건 분리), §13 (확장 절차), §14 (포지션 조건 인터페이스 — 2-tuple 반환), §15 (메타데이터 등록 규칙)
- 13번 §3.1 (일중 손절 판정), §3.2 (동일 봉 손절 우선 — 본 함수는 자기 평가만), §3.5 (trailing stop peak는 전일까지의 high), §7 (수정주가 사용 — adj_low/adj_high/adj_close), §15 (look-ahead bias 체크리스트)
- 02번 §5.2 (exit_position 섹션 schema — stop_loss는 trigger="intraday_low", trailing_stop은 percent + trigger)

### 시그니처 결정

작업 로그 Plan에는 4-tuple `(bool, str | None, float | None, int | None)`이 있었지만, 사용자가 명시적으로 "take_profit과 동일한 시그니처"를 요구했고 03번 §14도 2-tuple로 정의되어 있어 **2-tuple `(bool, str | None)`** 로 통일. exit_price/quantity 결정은 Wave B에서 BacktestEngine이 담당 (조건이 trigger 후 BacktestEngine이 stop_price/target_price/adj_close 등을 조건 dict와 position으로 재계산).

## Tests

```
$ .venv/Scripts/pytest.exe tests/strategy/conditions/test_exit_position.py -v
============================= 45 passed in 0.54s ==============================

$ .venv/Scripts/pytest.exe
============================= 335 passed in 9.23s =============================

$ .venv/Scripts/ruff.exe check app/ tests/
All checks passed!
```

- 신규 테스트: 35건 (stop_loss 10 + max_holding_days 12 + trailing_stop 11 + 동시 도달 1 + 카탈로그 1)
- 회귀: 기존 300건 → 전체 335건 모두 통과 (300 baseline 유지 + 35 신규)
- 기존 take_profit 테스트 10건도 함께 회귀 검증 (모듈 docstring/import 변경 없이 동작)
- ruff: app/ + tests/ 클린 (alembic/ 디렉토리의 13개 pre-existing 경고는 본 작업 무관)

### look-ahead bias 자가 검증

- **stop_loss**: 당일 high/low/close만 사용 — 미래 데이터 접근 없음. `position.entry_price`는 매수 시점에 확정된 값.
- **max_holding_days**: today와 first_entry_date의 단순 뺄셈만 — 미래 데이터 접근 없음.
- **trailing_stop**: `position.peak_price`만 읽고 갱신하지 않음. `test_trailing_stop_uses_position_peak_only_no_self_update`로 검증 — peak_price=12000인 상태에서 high=13000인 row를 입력해도 함수 호출 후 position.peak_price는 12000 그대로. peak 갱신 책임은 `Portfolio.update_market_price` (정확성 정책 13.3.5의 "전일까지의 high" 보장).

## Issues

### 시그니처 vs Plan 불일치

작업 로그 Plan의 4-tuple과 사용자 요구사항(2-tuple, take_profit 동형)이 충돌. 사용자 메시지를 우선해 2-tuple로 통일. Wave B의 backtest-engine-developer는 트리거 후 exit_price를 다음과 같이 재계산해야 함:
  - `stop_loss` 트리거 시: `exit_price = position.entry_price * (1 - condition["percent"]/100)`
  - `take_profit` 트리거 시: `exit_price = position.entry_price * (1 + condition["percent"]/100)`
  - `max_holding_days` 트리거 시: `exit_price = market_row["adj_close"]`
  - `trailing_stop` 트리거 시: `exit_price = position.peak_price * (1 - condition["percent"]/100)`
  - 갭 다운/업 (`gap_down_stop_loss`, `gap_up_take_profit`)은 BacktestEngine이 `market_row["adj_open"]` 검사 후 별도 처리 (조건 함수 호출 없이 시가 체결).

### Position 속성 호환성

- 본 작업의 함수들은 `position.entry_price`를 읽음 (take_profit 기존 패턴 따름).
- 하지만 실제 `Portfolio.Position` 모델은 `avg_entry_price`만 노출 (`portfolio/position.py`).
- 현재 engine.py는 `position.avg_entry_price`를 직접 사용 중 (engine.py:171).
- **Wave B에서 해결 필요**: backtest-engine-developer가 (a) Position에 `entry_price` 별칭 추가, (b) registry 호출 시 wrapper 객체로 전달, 또는 (c) 모든 조건 함수의 `position.entry_price` → `position.avg_entry_price` 일괄 변경 중 하나를 선택해야 함.
- Wave B 결정에 따라 본 파일의 `position.entry_price` 참조도 함께 수정될 수 있음.

### `max_holding_days` 정수 검증

JSON 라운드트립을 거치면 정수가 float로 들어올 수 있어, `10.0` 같이 정수값을 가진 float은 허용하고 `10.5` 같은 진짜 소수는 거부하는 정책을 추가. 03번/02번에 명시되어 있지 않은 결정이지만 사용자 친화성 + 결정론을 모두 만족.

## Result

| 항목 | 값 |
| --- | --- |
| 신규 조건 type | `stop_loss`, `max_holding_days`, `trailing_stop` |
| requires_position | True (3건 모두) |
| category | "exit_position" |
| allowed_in | ["exit_position"] |
| sentence_template | 한국어 (각 META 참조) |
| 반환 시그니처 | `tuple[bool, str | None]` — exit_reason은 "stop_loss" / "max_holding_days" / "trailing_stop" |
| look-ahead bias | 없음 (자가 검증 통과 — 위 Tests 섹션) |
| 정확성 정책 13.3.2 (동시 도달 손절 우선) | 본 함수들은 자기 평가만 — BacktestEngine 우선순위 정렬에서 처리 |
| 신규 테스트 / 전체 테스트 | 35건 신규 / 335건 전체 모두 PASS |
| ruff (app/ + tests/) | All checks passed |

### Wave B(012) BacktestEngine 호출 인터페이스

backtest-engine-developer가 engine.py를 리팩터할 때 사용해야 할 새 인터페이스:

```python
# 기존 (engine.py:_evaluate_exit_position의 if/elif 직접 평가) → 다음과 같이 변경
for rule in exit_position_rules:
    triggered, exit_reason = condition_registry.evaluate_position(
        rule["type"],          # "stop_loss" | "take_profit" | "max_holding_days" | "trailing_stop"
        position=position,     # Portfolio.Position 인스턴스 (또는 entry_price/peak_price/first_entry_date를 가진 wrapper)
        market_row=row,        # adj_open/adj_high/adj_low/adj_close + (max_holding_days엔 date 키 또는 DatetimeIndex .name)
        condition=rule,        # 전략 JSON의 조건 dict 그대로 전달 (percent / days / trigger)
    )
    if triggered:
        # exit_price 계산 (조건별):
        #   stop_loss:        entry * (1 - percent/100)
        #   take_profit:      entry * (1 + percent/100)
        #   max_holding_days: adj_close
        #   trailing_stop:    peak_price * (1 - percent/100)
        # 갭 다운/업은 위 호출 전에 adj_open 검사로 별도 분기 (gap_down_stop_loss / gap_up_take_profit).
        ...
```

정책 13.3.2(동시 도달 시 손절 우선)는 rules 순회 순서 또는 명시적 우선순위 정렬로 처리:
1. 갭 다운 stop_loss (adj_open <= stop_price)
2. 갭 업 take_profit (adj_open >= target_price)
3. 일중 stop_loss
4. 일중 take_profit
5. trailing_stop
6. max_holding_days

## Follow-ups

- **Wave B(012)**: backtest-engine-developer가 engine.py의 `_evaluate_exit_position` if/elif를 `condition_registry.evaluate_position` 호출 루프로 교체. Position의 `entry_price`/`avg_entry_price` alias 처리 결정 필요.
- **Position 모델 일관화**: `Portfolio.Position`에 `entry_price` 프로퍼티(= `avg_entry_price`)를 별칭 추가하면 본 조건 함수들과 실제 Portfolio 객체가 호환됨. take_profit도 동일 이슈.
- **TradeGroup 단위 평가 (옵션)**: 현재 조건은 Position 단위로 평가하지만, 추가매수 시 TradeGroup마다 entry_price가 다름. trade_group별 익절/손절을 지원하려면 함수 시그니처를 확장하거나 BacktestEngine이 trade_group 순회 시 임시 wrapper를 만들어 전달.
- **`max_holding_days`의 거래일 vs 달력일**: 현재 `(today - first_entry_date).days`는 달력일 기준. "거래일 N일"이 일반적인 기대치라면 trading_calendar 기반 계산으로 확장 필요. META 라벨에 "달력일" 명시.
- **trailing_stop의 `peak_basis` 파라미터**: 02번 §5.2 예시는 `peak_basis: "intraday_high"`를 보여주지만 본 구현은 무시 (peak 갱신은 Portfolio가 담당). 02번 schema와의 정합성 점검 후 schema에서 제거하거나 본 구현에 추가.
- **분봉 데이터 도입 (13.3 향후)**: 분봉 시 stop_loss/take_profit/trailing_stop 모두 시계열 순서로 처리하도록 함수 시그니처가 봉 단위 대신 분봉 슬라이스를 받도록 확장 가능.

## 메인 세션 마무리 체크

- [ ] status를 completed로 변경
- [ ] 작업로그/README.md "최근 작업" 표에 1행 추가
- [ ] B1(011)의 blockedBy 해제 확인
- [ ] `git commit`
