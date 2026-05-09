# 07. DB 상세 설계서

## 1. 목적

DB는 전략, 백테스트 실행 기록, 결과 요약, 거래 내역, 일별 자산, 예수금 이벤트, 종목 정보를 저장합니다.

이 프로그램은 전략과 결과가 계속 쌓이는 구조이므로 DB가 필수입니다.

---

## 2. DB 선택

MVP:

```text
SQLite
```

실사용/웹서비스:

```text
PostgreSQL
```

대용량 시세:

```text
PostgreSQL + Parquet 조합
```

---

## 3. 핵심 테이블

```text
strategies
strategy_versions
backtest_runs
backtest_results
trades
daily_equity
cash_events
symbols
daily_prices
watchlists
universe_history
```

---

## 4. strategies

전략 기본 정보를 저장합니다.

```text
id
name
description
strategy_json
tags
favorite
created_at
updated_at
deleted_at
```

### 설명

```text
strategy_json:
GUI에서 만든 전략 JSON

tags:
거래량, 돌파, 스윙 등 태그

favorite:
즐겨찾기 여부
```

---

## 5. strategy_versions

전략 수정 이력을 저장합니다.

```text
id
strategy_id
version
strategy_json
change_note
created_at
```

### 사용 목적

```text
전략 조건 변경 이력 확인
과거 버전 복원
전략 버전별 백테스트 비교
```

---

## 6. backtest_runs

백테스트 실행 기록입니다.

```text
id
strategy_id
strategy_snapshot_json
run_name
universe_config_json
start_date
end_date
initial_cash
fee_rate
tax_rate
slippage
execution_price_type
status
error_message
created_at
started_at
finished_at
```

### 중요 필드

```text
strategy_snapshot_json:
백테스트 실행 당시 전략 JSON

universe_config_json:
코스피 전체, 시가총액 상위 10종목 등 대상 종목 설정
```

실행 상태:

```text
pending
running
completed
failed
cancelled
```

---

## 7. backtest_results

백테스트 요약 결과입니다.

```text
id
run_id
total_return
annual_return
final_equity
mdd
win_rate
trade_count
avg_holding_days
avg_profit_rate
avg_loss_rate
profit_factor
sharpe_ratio
created_at
```

이 테이블은 전략 목록과 전략 비교 화면에서 빠르게 사용됩니다.

---

## 8. trades

거래 내역입니다.

```text
id
run_id
symbol
name
entry_date
entry_price
entry_quantity
entry_amount
exit_date
exit_price
exit_quantity
exit_amount
profit
profit_rate
holding_days
exit_reason
created_at
```

부분 매도 처리를 위해 향후 trade group 개념을 추가할 수 있습니다.

```text
trade_group_id
order_type
is_partial
```

---

## 9. daily_equity

일별 자산 변화를 저장합니다.

```text
id
run_id
date
cash
stock_value
total_equity
daily_return
cumulative_return
drawdown
positions_count
created_at
```

사용처:

```text
누적 수익률 그래프
MDD 그래프
예수금 그래프
CSV Export
```

---

## 10. cash_events

예수금 부족, 일부 매도 같은 이벤트를 저장합니다.

```text
id
run_id
date
event_type
cash_before
required_cash
action
symbol
sell_quantity
sell_amount
cash_after
reason
created_at
```

event_type 예시:

```text
cash_shortage
partial_sell
buy_skipped_cash_shortage
```

---

## 11. symbols

종목 마스터입니다.

```text
symbol
name
market
sector
listing_date
delisting_date
is_etf
is_etn
is_spac
is_preferred
is_active
is_managed
is_halted
updated_at
```

---

## 12. daily_prices

일봉 시세입니다.

```text
id
symbol
date
open
high
low
close
volume
trading_value
adjusted_close
market_cap
created_at
```

인덱스:

```text
(symbol, date)
date
symbol
```

---

## 13. watchlists

관심종목 목록입니다.

```text
id
name
description
created_at
updated_at
```

watchlist_items:

```text
id
watchlist_id
symbol
added_at
```

---

## 14. universe_history

백테스트 대상 종목군 이력입니다.

```text
id
run_id
date
market
selection_method
rank
symbol
name
market_cap
trading_value
created_at
```

시가총액 상위 N종목이나 월별 재선정 기능에 필요합니다.

---

## 15. 관계 구조

```text
strategies 1:N strategy_versions
strategies 1:N backtest_runs
backtest_runs 1:1 backtest_results
backtest_runs 1:N trades
backtest_runs 1:N daily_equity
backtest_runs 1:N cash_events
backtest_runs 1:N universe_history
symbols 1:N daily_prices
watchlists 1:N watchlist_items
```

---

## 16. JSON 컬럼 사용

다음 필드는 JSON 컬럼으로 저장합니다.

```text
strategies.strategy_json
strategy_versions.strategy_json
backtest_runs.strategy_snapshot_json
backtest_runs.universe_config_json
```

SQLite에서는 TEXT로 저장하고, PostgreSQL에서는 JSONB 사용을 권장합니다.

---

## 17. 저장 원칙

```text
전략은 strategies에 저장한다.
전략 수정 시 strategy_versions에 이력을 남긴다.
백테스트 실행 시 backtest_runs에 실행 조건을 저장한다.
실행 당시 전략 JSON은 반드시 strategy_snapshot_json에 저장한다.
요약 결과는 backtest_results에 저장한다.
상세 거래는 trades에 저장한다.
차트용 일별 데이터는 daily_equity에 저장한다.
예수금 이벤트는 cash_events에 저장한다.
```

---

## 18. 인덱스 설계

필수 인덱스:

```text
strategies.updated_at
backtest_runs.strategy_id
backtest_runs.created_at
backtest_results.run_id
trades.run_id
trades.symbol
daily_equity.run_id
daily_equity.date
cash_events.run_id
symbols.market
daily_prices.symbol_date
```

---

## 19. 데이터 보존 정책

MVP에서는 모든 결과를 보존합니다.

향후에는 다음 정책을 둘 수 있습니다.

```text
사용자가 삭제한 백테스트 결과 soft delete
오래된 daily_equity 압축 저장
CSV Export 파일은 일정 기간 후 삭제
대용량 price cache는 재생성 가능하도록 관리
```

---

## 20. 테스트 항목

```text
전략 저장/조회/수정/삭제
전략 버전 생성
백테스트 run 생성
strategy_snapshot_json 저장 확인
결과 요약 저장
거래 내역 저장
daily_equity 저장
cash_events 저장
전략 삭제 시 결과 보존 정책
CSV Export용 데이터 조회
```
