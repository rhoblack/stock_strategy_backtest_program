# 04. 백테스트 엔진 상세 설계서

## 1. 목적

백테스트 엔진은 전략 신호를 실제 매수/매도 시뮬레이션으로 변환하고, 거래 내역과 일별 자산 변화를 생성하는 핵심 모듈입니다.

백테스트 엔진은 모든 로직을 직접 갖지 않고, 여러 하위 모듈을 조립해 실행하는 오케스트레이터 역할을 합니다.

---

## 2. 핵심 설계 원칙

```text
BacktestEngine은 전체 흐름만 관리한다.
전략 신호 생성은 StrategyEngine이 담당한다.
체결 가격과 비용은 ExecutionModel이 담당한다.
현금과 보유 종목은 Portfolio가 담당한다.
예수금 부족 처리는 CashManager가 담당한다.
성과 지표 계산은 Metrics 모듈이 담당한다.
```

---

## 3. 전체 처리 흐름

```text
1. 백테스트 설정 로드
2. 전략 JSON 스냅샷 로드
3. 유니버스 생성
4. 시세 데이터 로드
5. 날짜별 루프 시작
6. 기존 보유 종목 가격 업데이트
7. 매도 조건 평가
8. 매도 체결
9. 신규 매수 후보 탐색
10. 예수금 부족 시 현금 확보 규칙 실행
11. 신규 매수 체결
12. 일별 자산 기록
13. 결과 지표 계산
14. DB 저장
```

---

## 4. 주요 클래스

```text
BacktestEngine
ExecutionModel
BacktestConfig
BacktestResult
MetricsCalculator
EventLogger
```

---

## 5. BacktestEngine 구조

```python
class BacktestEngine:
    def __init__(
        self,
        strategy_engine,
        portfolio,
        execution_model,
        cash_manager,
        market_data,
        universe_selector,
        config,
    ):
        self.strategy_engine = strategy_engine
        self.portfolio = portfolio
        self.execution_model = execution_model
        self.cash_manager = cash_manager
        self.market_data = market_data
        self.universe_selector = universe_selector
        self.config = config

    def run(self):
        # 1. 거래일 목록 생성
        # 2. 날짜별 루프 실행
        # 3. 일별 포트폴리오 상태 기록
        # 4. 결과 계산
        pass
```

---

## 6. 날짜별 루프 상세

```text
for date in trading_dates:

    1. 현재 날짜의 유니버스 결정
       - 전체 종목
       - 시가총액 상위 N종목
       - 관심종목 등

    2. 보유 종목 현재가 업데이트

    3. 기존 보유 종목 매도 조건 확인
       - 익절
       - 손절
       - 최대 보유일
       - 지표 기반 매도

    4. 매도 주문 실행
       - 체결 가격 계산
       - 수수료/세금/슬리피지 반영
       - Portfolio 업데이트
       - Trade/Event 기록

    5. 신규 매수 후보 계산
       - StrategyEngine이 final_entry_signal 생성
       - 해당 날짜 신호 종목 필터링

    6. 랭킹 또는 스코어링 적용
       - 여러 종목 동시 신호 발생 시 우선순위 결정

    7. 매수 예산 계산
       - position_sizing
       - daily_buy_budget
       - max_positions

    8. 예수금 확인
       - 예수금 부족 시 CashManager 실행

    9. 매수 체결
       - ExecutionModel로 체결 가격 계산
       - Portfolio 업데이트

    10. 일별 자산 기록
```

---

## 7. 체결 모델

체결 관련 로직은 `ExecutionModel`로 분리합니다.

```python
class ExecutionModel:
    def __init__(self, fee_rate, tax_rate, slippage):
        self.fee_rate = fee_rate
        self.tax_rate = tax_rate
        self.slippage = slippage

    def get_entry_price(self, row, price_type: str):
        if price_type == "open":
            return row["open"]
        if price_type == "close":
            return row["close"]
        if price_type == "next_open":
            return row["next_open"]
        raise ValueError(f"지원하지 않는 entry price type: {price_type}")

    def calculate_buy_cost(self, price, quantity):
        gross = price * quantity
        fee = gross * self.fee_rate
        return gross + fee

    def calculate_sell_proceeds(self, price, quantity):
        gross = price * quantity
        fee = gross * self.fee_rate
        tax = gross * self.tax_rate
        return gross - fee - tax
```

---

## 8. 체결 방식

MVP 지원:

```text
next_open:
신호 발생 다음 거래일 시가 체결

close:
신호 발생일 종가 체결
```

기본값은 `next_open`입니다.

향후 확장:

```text
next_close
limit_order
breakout_price
vwap
partial_fill
```

---

## 9. 비용 처리

한국 주식 기준으로 다음 비용을 반영합니다.

```text
매수 수수료
매도 수수료
거래세
슬리피지
```

설정 예시:

```json
{
  "fee_rate": 0.00015,
  "tax_rate": 0.0018,
  "slippage": 0.001
}
```

---

## 10. 매도 조건 처리

매도 조건은 두 가지로 나뉩니다.

```text
포지션 기반:
익절, 손절, 최대 보유일, 트레일링 스탑

지표 기반:
이동평균선 이탈, MACD 데드크로스, RSI 기준값
```

포지션 기반 조건은 Portfolio의 보유 상태가 필요합니다.

예:

```python
def check_position_exit(position, current_price, exit_rules):
    profit_rate = (current_price - position.entry_price) / position.entry_price * 100
    holding_days = position.holding_days

    for rule in exit_rules:
        if rule["type"] == "take_profit" and profit_rate >= rule["percent"]:
            return "take_profit"

        if rule["type"] == "stop_loss" and profit_rate <= -rule["percent"]:
            return "stop_loss"

        if rule["type"] == "max_holding_days" and holding_days >= rule["days"]:
            return "max_holding_days"

    return None
```

---

## 11. 매수 후보 처리

여러 종목에서 동시에 매수 신호가 발생할 수 있습니다.

처리 방식:

```text
1. final_entry_signal이 True인 종목 추출
2. 유동성 필터 적용
3. 이미 보유 중인 종목 제외 또는 추가매수 여부 판단
4. 랭킹/스코어링 적용
5. max_daily_entries 제한 적용
6. 예수금 범위 내 매수
```

---

## 12. 일별 자산 기록

매일 다음 정보를 기록합니다.

```text
date
cash
stock_value
total_equity
daily_return
cumulative_return
drawdown
positions_count
```

이 데이터는 다음에 사용됩니다.

```text
누적 수익률 그래프
MDD 그래프
예수금 그래프
보유 종목 수 그래프
CSV Export
```

---

## 13. 결과 지표

MVP에서 계산할 지표:

```text
총 수익률
최종 자산
연평균 수익률
MDD
승률
거래 횟수
평균 보유일
평균 수익률
평균 손실률
손익비
Profit Factor
```

향후 확장:

```text
Sharpe Ratio
Sortino Ratio
Calmar Ratio
월별 수익률
연도별 수익률
최대 연속 손실
```

---

## 14. 이벤트 로그

백테스트 중 발생하는 주요 이벤트를 기록합니다.

```text
BUY
SELL
PARTIAL_SELL
CASH_SHORTAGE
BUY_SKIPPED_CASH_SHORTAGE
UNIVERSE_CHANGED
```

예수금 이벤트는 cash_events 테이블에도 저장합니다.

---

## 15. DB 저장 결과

백테스트 완료 후 저장합니다.

```text
backtest_runs
backtest_results
trades
daily_equity
cash_events
universe_history
```

---

## 16. 테스트 항목

```text
다음날 시가 체결이 정확한지
매수 수수료가 반영되는지
매도 수수료와 거래세가 반영되는지
익절/손절 조건이 정확한지
최대 보유일 청산이 정확한지
현금 부족 시 매수가 차단되는지
CashManager 실행 후 매수가 가능한지
일별 자산 계산이 정확한지
MDD 계산이 정확한지
```

---

## 17. MVP 범위

MVP 백테스트 엔진은 다음을 지원합니다.

```text
단일 종목 백테스트
복수 종목 백테스트
next_open 체결
고정 금액 매수
최대 보유 종목 수
익절
손절
최대 보유일
수수료/세금/슬리피지
일별 자산 기록
거래 내역 생성
```
