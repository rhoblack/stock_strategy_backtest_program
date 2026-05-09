---
date: 2026-05-09
agent: main (backtest-engine-developer 대행 — hot reload 미작동)
phase: 1
status: completed
related_docs:
  - 상세설계/04_backtest_engine_design.md
  - 상세설계/05_portfolio_cash_management_design.md
  - 상세설계/13_backtest_accuracy_policy_design.md
---

# Phase 1 / Step 6 — ExecutionModel + Portfolio (Position + TradeGroup)

## Plan

BacktestEngine이 조립할 의존 모듈을 먼저 작성. 정확성 정책 13.5(호가 단위) / 13.6(세율 시계열) / 13.9(추가매수 가중평균)를 처음으로 코드에 적용.

PositionSizer / CashManager는 이번 단계에선 제외 (Phase 6 또는 별도 단계). MVP의 단일 종목 백테스트는 fixed_amount + allow_pyramiding=False만으로 충분.

### 작성할 파일

- [x] `app/backtest/tick.py`
  - `tick_size_for(price, market="KOSPI") -> int` — 13.5.1 호가 단위 표
  - `round_to_tick(price, market, side, mode) -> int`
    - mode="buy_up_sell_down" (기본): 매수 올림, 매도 내림 (보수)
    - mode="nearest": 반올림

- [x] `app/backtest/execution.py`: `ExecutionModel`
  - 생성자: fee_rate, tax_rate, slippage, use_adjusted_price=True, tick_rounding="buy_up_sell_down"
  - `get_tax_rate(date) -> float` — float 또는 [{from, rate}] 시계열 검색
  - `get_entry_price(row, price_type) -> float` — adj_* 또는 raw 반환
  - `apply_slippage_and_tick(price, side, market) -> int`
  - `calculate_buy_cost(price, qty)` — gross + fee
  - `calculate_sell_proceeds(price, qty, date)` — gross - fee - tax

- [x] `app/portfolio/position.py`: `TradeGroup`, `Position`
  - TradeGroup: id, entry_date, entry_price, entry_quantity, remaining_quantity (frozen 아님 — remaining_quantity 변동)
  - Position: symbol, name, current_price, peak_price, trade_groups[]
    - quantity, avg_entry_price, market_value, unrealized_*, first_entry_date

- [x] `app/portfolio/portfolio.py`: `Portfolio`
  - cash, positions: dict[symbol, Position], _next_trade_group_id
  - buy(symbol, name, price, qty, date, reason, allow_pyramiding=False) → trade_group_id
    - 이미 보유 + allow_pyramiding=False → ValueError
    - allow_pyramiding=True → 기존 position에 새 trade_group 추가
  - sell_trade_group(symbol, tg_id, price, qty, date, reason) — 부분/전량
  - sell_symbol_fifo(symbol, price, qty, date, reason) — FIFO 순회
  - total_stock_value, total_equity, positions_count

- [x] `app/backtest/__init__.py`, `app/portfolio/__init__.py` 노출

### 테스트

- [x] tests/backtest/test_tick.py (24건, parametrize 14 포함)
- [x] tests/backtest/test_execution.py (15건)
- [x] tests/portfolio/test_position.py (8건)
- [x] tests/portfolio/test_portfolio.py (23건)

### 정책 / 주의

- 거래세 시계열은 02번 schema에 따라 [{from: ISO date or datetime.date, rate: float}]
- 추가매수 시 평단가는 가중평균 (정확성 정책 13.9.2)
- 부분 매도 후에도 trade_group의 entry_price는 절대 변경하지 않음 (남은 평단가 유지)
- 종목코드 결정론은 다음 단계 (BacktestEngine priority)에서 검증 — 이번엔 Portfolio 단위 검증만

## Execution

```text
backend/app/backtest/tick.py             신규 (~70줄)
  - tick_size_for(price, market) — 7구간 임계값 테이블
  - round_to_tick(price, market, side, mode)
    - mode="buy_up_sell_down" (기본): 매수 올림, 매도 내림 (보수)
    - mode="nearest"

backend/app/backtest/execution.py        신규 (~120줄)
  - TaxRateEntry (frozen) — 시계열 세율 한 항목
  - _normalize_tax_rate(): float | list[dict] | list[TaxRateEntry] → 정규화
  - ExecutionModel
    - get_tax_rate(date): 시계열에서 적용 세율 검색
    - get_entry_price(row, type): use_adjusted_price에 따라 adj_* 또는 raw
    - apply_slippage_and_tick(price, side, market): 슬리피지 + 호가 반올림
    - calculate_buy_cost / calculate_sell_proceeds (시계열 세율 적용)

backend/app/portfolio/position.py        신규 (~70줄)
  - TradeGroup (mutable, remaining_quantity 변동)
  - Position (symbol, current_price, peak_price, trade_groups[])
    - quantity, avg_entry_price (가중평균), market_value, unrealized_*, first_entry_date

backend/app/portfolio/portfolio.py       신규 (~190줄)
  - Portfolio
    - buy(symbol, price, qty, date, reason, allow_pyramiding=False, cost_override=None)
      - 자동 trade_group_id 발급
      - 추가매수 방지 또는 가중평균 추가
    - sell_trade_group(symbol, tg_id, ...): 부분/전량 매도, entry_price 절대 미변경
    - sell_symbol_fifo(symbol, ...): entry_date 오름차순 + tg_id tie-breaker (결정론)
      - proceeds_override 비례 분배
    - update_market_price(symbol, price): current_price + peak_price 갱신
    - total_stock_value / total_equity / positions_count

backend/app/backtest/__init__.py         ExecutionModel, TaxRateEntry, round_to_tick, tick_size_for 노출
backend/app/portfolio/__init__.py        Portfolio, Position, TradeGroup 노출

backend/tests/backtest/__init__.py       빈 파일
backend/tests/backtest/test_tick.py      신규 24건
backend/tests/backtest/test_execution.py 신규 15건
backend/tests/portfolio/__init__.py      이미 존재
backend/tests/portfolio/test_position.py 신규 8건
backend/tests/portfolio/test_portfolio.py 신규 23건
```

설계 결정:
- **호가 단위 mode "buy_up_sell_down" 기본**: 정확성 정책 13.5.2의 보수적 처리. 슬리피지 + 호가가 둘 다 사용자에게 불리한 방향으로 작동.
- **세율 시계열 정규화**: float, list[dict], list[TaxRateEntry] 셋 다 받음. 내부에서 list[TaxRateEntry]로 통일. 입력이 정렬돼 있지 않아도 from_date 기준 자동 정렬.
- **Portfolio.buy의 cost_override**: ExecutionModel.calculate_buy_cost 결과를 그대로 받아 차감. 이 패턴은 BacktestEngine이 ExecutionModel과 Portfolio를 조립할 때 자연스럽게 흐름 분리.
- **sell_trade_group의 proceeds_override**: 매도 시 sell_proceeds(수수료/세금 반영)를 따로 계산해 넘김. Portfolio는 가격*수량을 모름.
- **sell_symbol_fifo의 결정론**: entry_date 오름차순 + trade_group_id 오름차순 tie-breaker. dict 순서 의존 회피.
- **update_market_price**: peak_price는 current_price 갱신값보다 큰 경우만 갱신 → trailing_stop의 "전일까지의 high" 의미 보존.
- **TradeGroup은 frozen 아님**: remaining_quantity가 sell 시 줄어들어야 하므로 mutable. entry_price는 절대 변경되지 않는다는 정책은 코드/테스트로만 보장.

## Tests

```text
============== 184 passed in 0.85s ==============
ruff: All checks passed
```

신규 70건:
- test_tick (24): 7구간 임계값 + nearest/buy_up_sell_down 모드
- test_execution (15): 시계열 세율 4구간 + 가격 컬럼 + 슬리피지 + 비용
- test_position (8): TradeGroup 합산, 가중평균, 부분매도 후 평단가 유지
- test_portfolio (23): buy/sell_trade_group/sell_symbol_fifo/pyramiding/FIFO/평가 갱신

회귀: 기존 114건 모두 통과.

## Issues

- ruff I001 import 정렬 3건 — 자동 수정.
- volume_ratio Step 4 때 발견한 "rolling 평균 당일 포함" 의문은 그대로 보류 (정책 재검토 별도 작업).

## Result

- 추가/수정 파일: 11개 (소스 6, 테스트 4, __init__ 2)
- 정확성 정책 13.5 (호가) / 13.6 (세율 시계열) / 13.9 (가중평균 평단가) 코드로 첫 적용
- 부분매도 모델 (trade_groups + remaining_quantity)이 동작
- 결정론 보장: sell_symbol_fifo 정렬 키에 trade_group_id tie-breaker, peak_price는 max만 적용
- pytest 184/184, ruff 통과

## Follow-ups

- **Step 7 (다음)**: 단일 종목 BacktestEngine 골격 — 04번 5~6절. 날짜별 루프, exit_position 평가, ExecutionModel/Portfolio 조립.
  - PositionSizer가 필요 (fixed_amount 우선). 04번 11.1의 priority는 단일 종목 백테스트에선 적용 대상이 한 종목뿐이라 pass.
  - exit_position 평가는 04번 10.1의 evaluate_exit_position 알고리즘 그대로.
- **Step 8**: Metrics (총수익률, MDD, 승률, 거래 횟수, 평균 보유일).
- **Step 9**: Phase 1 통합/Golden 테스트 (12번 15절).
- **호가 단위 시기·시장 분기**: KRX 호가가 시기별로 변동되어 왔음. 향후 시계열 처리 검토 (현재는 2025년 기준 단일).
- **CashManager / PositionSizer / EventLogger**: Phase 6 또는 BacktestEngine 작성하면서 필요 최소만 추가 후 보강.

## 메인 세션 마무리 체크

- [x] status를 completed로 변경
- [x] 작업로그/README.md "최근 작업" 표에 1행 추가
- [x] Phase 상태가 변경되었으면 Phase 표 갱신
- [x] Follow-ups 중 다음 작업 후보로 옮길 항목 정리
