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
users
strategies
strategy_versions
backtest_runs
backtest_results
trade_groups          (신규: 매수 lot 단위)
trade_executions      (신규: 매수/매도 1건당 1행)
daily_equity
cash_events
symbols
daily_prices
trading_calendar      (신규: KRX 거래일/휴장일)
corporate_actions     (신규: 분할/배당/유증 이력)
watchlists
universe_history
```

기존 `trades` 테이블은 `trade_groups + trade_executions`로 분리되었습니다 (4.5절).

---

## 4. users

멀티유저 환경을 가정합니다 (단일 유저 데스크톱이라도 user_id=1 시스템 유저로 동일 스키마 유지).

```text
id
email
display_name
hashed_password
created_at
last_login_at
is_active
```

MVP에서는 인증 없이 user_id=1 단일 유저로 동작 가능. 모든 strategies / backtest_runs 테이블에 user_id FK를 두어 향후 멀티유저 전환을 무중단으로 지원.

---

## 5. strategies

전략 기본 정보를 저장합니다.

```text
id
user_id              (FK users.id)
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
GUI에서 만든 전략 JSON. 02 schema 문서 정의 따름.

tags:
거래량, 돌파, 스윙 등 태그

favorite:
즐겨찾기 여부
```

---

## 6. strategy_versions

전략 수정 이력을 저장합니다.

```text
id
strategy_id          (FK)
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

## 7. backtest_runs

백테스트 실행 기록입니다.

```text
id
user_id              (FK users.id)
strategy_id          (FK)
strategy_snapshot_json
run_name
universe_config_json
start_date
end_date
initial_cash
fee_rate
tax_rate_json        (시계열 세율 저장. 정확성 정책 13.6)
slippage
execution_price_type
use_adjusted_price
tick_rounding
priority_method
priority_tie_breaker
random_seed
status
progress_pct         (0~100, 진행률)
error_message
created_at
started_at
finished_at
```

### 중요 필드

```text
strategy_snapshot_json:
백테스트 실행 당시 전략 JSON. 재현성 보장 필수.

universe_config_json:
코스피 전체, 시가총액 상위 10종목 등 대상 종목 설정.

tax_rate_json:
시계열 세율 배열 또는 단일 float. 정확성 정책 13.6.

priority_method / priority_tie_breaker:
동시 매수 신호 처리 알고리즘. 결정론 보장에 필수.

random_seed:
priority.method=random일 때 결정론 보장.

progress_pct:
실행 중 백테스트 진행률 (10 API 문서 참조).
```

실행 상태:

```text
pending     (대기 중)
running     (실행 중)
cancelling  (취소 요청 수신, 엔진 중단 신호 전달 중 — step 037에서 추가)
completed   (완료)
failed      (오류 종료)
cancelled   (취소 완료)
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

## 9. trade_groups (신규)

매수 lot 하나를 표현합니다. 부분 매도는 trade_group의 remaining_quantity만 줄입니다 (05 portfolio 4절).

```text
id (= trade_group_id)
run_id               (FK backtest_runs.id)
symbol
name
entry_date
entry_price          (가중평균 평단가, 추가매수 시 갱신)
entry_quantity       (최초 매수 수량)
remaining_quantity   (현재 남은 수량)
fully_closed_at      (전량 청산 시점, NULL이면 보유 중)
final_profit         (전량 청산 시 총 실현 손익)
final_profit_rate
created_at
```

추가매수 시 정책에 따라 (정확성 정책 13.9):
- `weighted_average`: 기존 trade_group의 entry_price를 가중평균으로 갱신, entry_quantity와 remaining_quantity 증가
- `separate_group` (향후): 새 trade_group 생성

MVP는 `weighted_average`만 지원합니다.

---

## 10. trade_executions (신규)

매수/매도 1건의 실행 기록. 부분 매도는 여러 execution을 만듭니다.

```text
id
trade_group_id       (FK trade_groups.id)
run_id               (FK backtest_runs.id, 조회 편의)
execution_date
execution_type       (BUY, SELL, PARTIAL_SELL)
price
quantity
gross_amount
fee
tax
net_amount           (BUY: 매수 총 비용, SELL: 매도 순수익)
realized_profit      (SELL/PARTIAL_SELL만, BUY는 NULL)
realized_profit_rate
exit_reason          (take_profit, stop_loss, max_holding_days, exit_signal,
                      cash_shortage_partial_sell, gap_down_stop_loss, delisting 등)
created_at
```

### 9-10. 관계

```text
backtest_run 1:N trade_group
trade_group 1:N trade_execution

매수 1회 = trade_group 1개 + execution 1개 (BUY)
부분 매도 N회 = trade_group 1개 + execution N개 (SELL)
```

### 9-10. CSV 표현

기존 사용자 친화 CSV `trades.csv` 컬럼 (entry_*, exit_*)은 trade_group 단위로 집계해서 생성합니다 (09 CSV 문서 참조). 부분 매도 이력은 별도 `trade_executions.csv`로 제공.

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

종목 마스터입니다. 생존 편향 완화를 위해 `listing_date`와 `delisting_date`는 NOT NULL로 관리하는 것이 권장됩니다.

```text
symbol (PK)
name
market               (KOSPI, KOSDAQ, KONEX)
sector
listing_date         (NOT NULL 권장)
delisting_date       (NULL이면 현재 상장 중)
shares_outstanding   (상장주식수, 시가총액 계산용)
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

일봉 시세입니다. 정확성 정책 13.7에 따라 수정주가 필드를 모두 보유합니다.

```text
id
symbol               (FK symbols.symbol)
date
open, high, low, close          (원 가격)
adj_open, adj_high, adj_low, adj_close  (수정 가격)
volume                          (원 거래량)
adj_volume                      (수정 거래량)
trading_value                   (거래대금)
market_cap                      (시가총액 = 종가 × 상장주식수)
adjustment_factor               (누적 수정 계수)
created_at
updated_at
```

인덱스 (성능 핵심):

```text
PRIMARY (symbol, date)                       단일 종목 시계열 조회
INDEX (date)                                 특정 날짜 cross-section
INDEX (date, market_cap DESC)                시가총액 상위 N 쿼리 (정확성 정책 13.8 priority + 14.8.3)
INDEX (date, trading_value DESC)             거래대금 상위 N 쿼리
```

데이터 양 추정 (14 데이터 파이프라인 8.1절):

```text
약 2,800종목 × 2,450거래일(10년) ≈ 6.86M rows
SQLite로 5~10GB 예상
```

---

## 12-A. trading_calendar (신규)

KRX 거래일/휴장일 데이터입니다.

```text
id
date (PK)
market               (KOSPI, KOSDAQ)
is_trading_day
holiday_name
half_day             (단축거래일)
```

거래일 캘린더가 결손되면 백테스트 실행을 차단합니다 (14 데이터 파이프라인 11절).

---

## 12-B. corporate_actions (신규)

분할/병합/배당/유증 등 권리 이력입니다.

```text
id
symbol
event_date
event_type           (split, reverse_split, bonus_issue, rights_issue, dividend, delisting)
ratio
dividend_amount
price_before
price_after
adjustment_factor
source               (KRX, KIND, manual)
applied_at           (수정주가 재계산 완료 시각)
```

신규 corporate_action 수집 시 영향 종목의 수정주가를 재계산합니다 (14 데이터 파이프라인 9절).

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
users 1:N strategies
users 1:N backtest_runs
strategies 1:N strategy_versions
strategies 1:N backtest_runs
backtest_runs 1:1 backtest_results
backtest_runs 1:N trade_groups
backtest_runs 1:N daily_equity
backtest_runs 1:N cash_events
backtest_runs 1:N universe_history
trade_groups 1:N trade_executions
symbols 1:N daily_prices
symbols 1:N corporate_actions
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
backtest_runs.tax_rate_json
```

SQLite에서는 TEXT로 저장하고 `JSON_EXTRACT()` 함수를 사용. PostgreSQL에서는 JSONB 사용 + GIN 인덱스 권장.

### JSON 메타 검색 (선택)

"이동평균 사용한 전략만" 같은 메타 검색을 위해 별도 메타 테이블을 둘 수도 있습니다.

```text
strategy_condition_index:
  strategy_id, condition_type
```

매 strategy 저장 시 strategy_json을 파싱해 등록된 condition_type들을 추출해 갱신. MVP에서는 미구현, v2에서 도입.

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
users.email                                  (unique)
strategies.user_id
strategies.updated_at
backtest_runs.user_id
backtest_runs.strategy_id
backtest_runs.created_at
backtest_runs.status                         (실행 중/대기 큐 조회)
backtest_results.run_id                      (unique)
trade_groups.run_id
trade_groups.symbol
trade_groups.entry_date
trade_executions.trade_group_id
trade_executions.run_id
trade_executions.execution_date
trade_executions.exit_reason
daily_equity.run_id
daily_equity.(run_id, date)                  (시계열 조회)
cash_events.run_id
cash_events.(run_id, date)
symbols.market
symbols.is_active
daily_prices.(symbol, date)                  (PRIMARY)
daily_prices.(date, market_cap DESC)         (시가총액 상위 N)
daily_prices.(date, trading_value DESC)      (거래대금 상위 N)
trading_calendar.(date, market)              (PRIMARY)
corporate_actions.(symbol, event_date)
universe_history.(run_id, date)
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
