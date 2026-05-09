---
date: 2026-05-09
agent: main (backtest-engine-developer 대행)
phase: 1
status: completed
related_docs:
  - 상세설계/04_backtest_engine_design.md
  - 상세설계/13_backtest_accuracy_policy_design.md
  - 상세설계/05_portfolio_cash_management_design.md
---

# Phase 1 / Step 7 — 단일 종목 BacktestEngine 골격

## Plan

설계서 04번 5~6절 + 정확성 정책 13.3 일중 익절/손절 처리 + 13.4 갭/거래정지를 처음으로 코드에 적용. 단일 종목 한정 — priority / 유니버스 / CashManager는 후속 단계.

### 핵심 흐름 (정확성 정책 13.16 이벤트 순서)

```text
for each row in df (날짜순):
    1. 보유 중이면 update_market_price(adj_close)
    2. 거래정지(volume=0)면 모든 처리 skip
    3. 보유 중이면 exit_position 평가:
       3-1. 갭 다운 손절 (open <= stop_price)
       3-2. 갭 업 익절 (open >= target_price)
       3-3. 일중 low <= stop_price → 손절가 체결
       3-4. 일중 high >= target_price → 익절가 체결
       3-5. 동시 도달 시 손절 우선 (정확성 정책 13.3.2)
       3-6. max_holding_days 도달 시 종가 청산
    4. 보유 중이고 exit_signal True → 다음 거래일 시가 매도 (FIFO)
    5. 보유 중이 아니고 final_entry_signal True →
       max_gap_pct_for_entry 체크 후 다음 거래일 시가 매수
    6. 일별 자산 기록 (cash, stock_value, total_equity, drawdown)
```

### 작성할 파일

- [x] `app/backtest/config.py`: `BacktestConfig` (frozen dataclass)
- [x] `app/backtest/result.py`: `DailyEquity`, `BacktestResult`
- [x] `app/backtest/engine.py`: `BacktestEngine`
- [x] `app/backtest/__init__.py`에 노출

### 테스트

- [x] tests/backtest/test_backtest_engine.py (13건)
  - 매수 신호 발생 → 다음 거래일 시가 매수
  - 익절 도달 → 익절가 체결 (intraday_high)
  - 손절 도달 → 손절가 체결 (intraday_low)
  - 동시 도달 → 손절 우선
  - 갭 다운 → 시가 손절 + exit_reason "gap_down_stop_loss"
  - 갭 업 → 시가 익절 + exit_reason "gap_up_take_profit"
  - max_gap_pct_for_entry 초과 → 매수 skip
  - 거래정지(volume=0) → 매수/매도 모두 skip
  - exit_signal 발동 → 다음 시가 매도
  - 일별 자산 기록 정합성
  - 결정론 (5회 동일 결과)

### 단순화 (이번 단계)

- 단일 종목만 (df 1개)
- allow_pyramiding=False
- PositionSizer 미사용 (config.position_size_amount로 직접 계산)
- CashManager 미사용 (예수금 부족 시 매수 skip)
- 상한가/하한가/listing_date 필터 미적용 (Follow-up)
- df에 next_open / next_close 컬럼이 미리 채워져 있다고 가정 (호출자가 PriceLoader 단계에서 처리)

### 정책 / 주의

- next_open이 NaN이면 매수/매도 skip (마지막 봉 또는 데이터 결손)
- ExecutionModel.apply_slippage_and_tick으로 매수/매도 가격 보정
- ExecutionModel.calculate_buy_cost / calculate_sell_proceeds로 비용 적용
- Portfolio.buy의 cost_override / sell_*의 proceeds_override 활용

## Execution

```text
backend/app/backtest/config.py           신규 BacktestConfig (frozen)
  - symbol/start_date/end_date/position_size_amount/initial_cash
  - max_gap_pct_for_entry=5.0, skip_no_volume=True

backend/app/backtest/result.py           신규 DailyEquity, BacktestResult
  - DailyEquity(date, cash, stock_value, total_equity, drawdown, positions_count)
  - BacktestResult.total_return_pct property
  - trade_count property (SELL/PARTIAL_SELL 카운트)

backend/app/backtest/engine.py           신규 BacktestEngine (~200줄)
  - run(df) → BacktestResult (단일 종목)
  - 흐름: 거래정지 skip → exit_position 평가 → exit_signal → 매수 후보 → daily_equity
  - _evaluate_exit_position: 정확성 정책 13.3 우선순위 그대로
    - 갭 다운 손절 → 갭 업 익절 → 일중 손절 → 일중 익절 → max_holding_days
  - _maybe_buy: 다음 거래일 거래정지 + 갭 +5% 초과 + 예수금 부족 시 skip
  - _process_sell_at_price: 슬리피지 + 호가 + 세금 처리 후 FIFO
  - _record_daily_equity: peak_equity 기준 drawdown

backend/app/backtest/__init__.py         BacktestConfig/BacktestEngine/BacktestResult/DailyEquity 추가 노출

backend/tests/backtest/test_backtest_engine.py  신규 13건
```

설계 결정:
- **단일 종목 한정**: priority/유니버스/CashManager 모두 후속 단계.
- **exit_position 평가는 BacktestEngine 직접**: 함수 분리 (_evaluate_exit_position). conditions/exit_position.py의 take_profit 함수는 사용 안 함 (BacktestEngine이 stop_loss/max_holding_days까지 묶어서 평가). 향후 리팩터: condition_registry.evaluate_position()으로 위임 + stop_loss/max_holding_days를 conditions/exit_position.py에 추가.
- **next_volume 컬럼 도입**: 다음 거래일 거래정지 체크용. PriceLoader 단계에서 채워야 함 (현재는 헬퍼/테스트가 직접 채움).
- **매수 처리는 신호일에 호출, 체결가는 next_open**: trade_logs의 date는 신호일이지만 가격은 next_open. 향후 trade execution date를 분리할지 검토 (Follow-up).
- **slippage/tick은 모든 매도에 적용 — 갭 손절/익절 포함**: 정확성 정책 13.3.3/13.3.4의 "시가 체결"은 시가 그대로 받고, 슬리피지/호가는 그 위에 추가. 실제 체결 시뮬레이션 모델로 일관.

## Tests

```text
============== 197 passed in 0.71s ==============
ruff: All checks passed
```

신규 13건:
- 매수 (next_open 체결)
- 일중 익절 (intraday_high 도달)
- 일중 손절 (intraday_low 도달)
- 동시 도달 시 손절 우선
- 갭 다운/업 → 시가 체결 + 별도 exit_reason
- max_gap_pct 초과 매수 skip
- 거래정지 매수/매도 skip
- max_holding_days 종가 청산
- exit_signal 다음 시가 매도
- 결정론 (5회 동일)
- 일별 자산 / drawdown 음수 검증

회귀: 기존 184건 모두 통과.

## Issues

- **테스트 4건 초기 fail → 수정**:
  1. take_profit 시나리오의 Day3 시가가 익절선 위 → 갭 업으로 처리됨. 시가 낮춰서 일중 익절로 분리.
  2. max_gap_skip 시나리오에서 후속 봉이 다시 entry True → 매수 발생. close 낮춰서 entry False 만듦.
  3. no_volume 시나리오: `_maybe_buy`가 next day volume 미체크. 엔진 수정 (next_volume 체크) + 헬퍼에 next_volume 컬럼 추가.
  4. 결정론 테스트: `pd.Timestamp + Timedelta`가 Timestamp 반환인데 `.date()` 호출은 OK이지만 list comprehension에서 Timestamp.date()를 두 번 호출하여 AttributeError. 수정.
- **ruff B905 zip strict 누락** + **I001 import 정렬** 자동 수정.

## Result

- 추가/수정 파일: 5개 (config.py, result.py, engine.py, __init__.py, test_backtest_engine.py)
- 정확성 정책 13.3 (일중 익절/손절) / 13.4 (갭/거래정지) / 13.16 (이벤트 우선순위) 첫 적용 + 검증
- 결정론: 5회 반복 동일 결과 검증 통과
- pytest 197/197, ruff All checks passed
- 단일 종목 백테스트가 end-to-end로 동작 가능 (StrategyEngine + ExecutionModel + Portfolio + BacktestEngine 조립)

## Follow-ups

- **Step 8 (다음)**: Metrics — 총수익률(이미 result에 있음)/MDD/승률/거래 횟수/평균 보유일/Profit Factor.
- **Step 9**: Phase 1 통합 / Golden test fixture (12번 15절). `tests/golden/`에 데이터 + 전략 + expected 결과를 두고 회귀 보증.
- **stop_loss/max_holding_days 조건 함수화 검토**: 현재 BacktestEngine이 직접 평가. 03번 메타데이터 패턴(condition_registry)으로 옮기면 GUI 노출 자동화 + 사용자 정의 가능. 단 시그니처 차이(exit reason 반환)로 인터페이스 정리 필요.
- **PriceLoader 작성 (Phase 2 데이터 파이프라인)**: next_open / next_volume / adj_* 컬럼 자동 채우기.
- **trade_executions의 date 의미 정의**: 신호일 vs 체결일을 분리할지 검토. CSV Export에서 사용자가 보는 거래내역의 매수일/매도일은 체결일이 자연스러움.
- **listing_date 필터 / 상한가 / 하한가 / 정확성 정책 13.4.3** 적용은 다종목 단계에서.

## 메인 세션 마무리 체크

- [x] status를 completed로 변경
- [x] 작업로그/README.md "최근 작업" 표에 1행 추가
- [x] Phase 상태가 변경되었으면 Phase 표 갱신
- [x] Follow-ups 중 다음 작업 후보로 옮길 항목 정리
