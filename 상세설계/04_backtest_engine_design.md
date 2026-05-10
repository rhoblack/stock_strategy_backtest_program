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
포지션 기반 매도 (exit_position) 평가는 BacktestEngine이 직접 담당한다.
일중 처리, 갭, 호가 단위, 거래세 시계열 등은 정확성 정책 (13 문서)을 따른다.
동시 매수 신호 우선순위는 strategy.priority 섹션을 따른다.
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

    def run(self, cancel_token=None):
        # cancel_token: CancellationToken | None
        # 날짜 루프 상단에서 cancel_token.check_cancelled() 호출 → BacktestCancelledError 발생
        # 1. 거래일 목록 생성
        # 2. 날짜별 루프 실행
        # 3. 일별 포트폴리오 상태 기록
        # 4. 결과 계산
        pass
```

---

## 6. 날짜별 루프 상세

이벤트 우선순위는 정확성 정책 13.16절을 따릅니다.

```text
for date in trading_dates:

    1. 현재 날짜의 유니버스 결정
       - listing_date <= date < delisting_date 인 종목만 편입 (생존편향 완화)
       - 시가총액 상위 N, 관심종목 등 universe_config 적용
       - 거래정지/관리종목 필터 적용

    2. 보유 종목 현재가 업데이트
       - adj_close 기준 평가
       - 거래정지 종목은 마지막 종가 유지

    3. 보유 포지션 매도 평가 (정확성 정책 우선순위 적용)
       3-1. 거래정지 종목 → 매도 보류
       3-2. 상장폐지 발생 → 강제 매도 (정확성 정책 13.4.5)
       3-3. exit_position 평가 (BacktestEngine 직접)
            - 갭 다운/업 우선 검사 (정확성 정책 13.3.3 / 13.3.4)
            - 일중 high/low 도달 검사 (intraday_high / intraday_low)
            - 동시 도달 시 손절 우선 (정확성 정책 13.3.2)
            - max_holding_days 검사
            - trailing_stop 검사 (전일까지의 peak 사용)
       3-4. exit_signal 평가 (StrategyEngine이 사전 생성한 신호 사용)

    4. 매도 주문 실행
       - 하한가 종목은 allow_sell_limit_down 확인 후 보류 가능
       - ExecutionModel로 체결가 계산 (호가 단위 반올림 포함)
       - 수수료, 거래세 (시계열 적용), 슬리피지 반영
       - Portfolio 업데이트 (trade_group 단위 처리)
       - trades / cash_events / event_log 기록

    5. 신규 매수 후보 계산
       - StrategyEngine이 final_entry_signal=True인 종목 추출
       - 이미 보유 중인 종목은 allow_pyramiding=false면 제외
       - max_gap_pct_for_entry 초과 갭 종목 제외
       - 상한가 종목은 allow_buy_limit_up 확인 후 제외 가능

    6. priority 적용 (정확성 정책 13.8절)
       - strategy.priority.method로 정렬
       - tie_breaker로 동순위 결정 (기본: symbol_asc)
       - max_daily_entries로 상한 적용

    7. 매수 예산 계산
       - position_sizing.method 적용
       - daily_buy_budget 한도 확인
       - max_positions 한도 확인
       - risk_management.stop_trading_on_drawdown_pct 확인

    8. 예수금 확인
       - 예수금 부족 시 CashManager 실행
       - cash_events 기록

    9. 매수 체결
       - ExecutionModel로 체결 가격 계산 (호가 단위 반올림)
       - Portfolio 업데이트 (새 trade_group 생성)
       - trades 기록

    10. 일별 자산 기록 (daily_equity)
```

---

## 7. 체결 모델

체결 관련 로직은 `ExecutionModel`로 분리합니다. 거래세 시계열, 호가 단위, 슬리피지 정책은 정확성 정책 13.5/13.6절을 따릅니다.

```python
class ExecutionModel:
    def __init__(
        self,
        fee_rate: float,
        tax_rate,                 # float | list[{"from": date, "rate": float}]
        slippage: float,
        use_adjusted_price: bool = True,
        tick_rounding: str = "buy_up_sell_down",
    ):
        self.fee_rate = fee_rate
        self.tax_rate = tax_rate
        self.slippage = slippage
        self.use_adjusted_price = use_adjusted_price
        self.tick_rounding = tick_rounding

    def get_tax_rate(self, date) -> float:
        if isinstance(self.tax_rate, (int, float)):
            return float(self.tax_rate)
        for entry in reversed(self.tax_rate):
            if date >= entry["from"]:
                return entry["rate"]
        return 0.0

    def get_entry_price(self, row, price_type: str):
        prefix = "adj_" if self.use_adjusted_price else ""
        if price_type == "open":
            return row[f"{prefix}open"]
        if price_type == "close":
            return row[f"{prefix}close"]
        if price_type == "next_open":
            return row[f"{prefix}next_open"]
        raise ValueError(f"지원하지 않는 entry price type: {price_type}")

    def apply_slippage_and_tick(self, price: float, side: str, market: str) -> int:
        # 슬리피지 적용 (매수는 위로, 매도는 아래로)
        if side == "buy":
            adjusted = price * (1 + self.slippage)
        else:
            adjusted = price * (1 - self.slippage)

        # 호가 단위 반올림 (정확성 정책 13.5절)
        return round_to_tick(adjusted, market, side, self.tick_rounding)

    def calculate_buy_cost(self, price, quantity):
        gross = price * quantity
        fee = gross * self.fee_rate
        return gross + fee

    def calculate_sell_proceeds(self, price, quantity, date):
        gross = price * quantity
        fee = gross * self.fee_rate
        tax = gross * self.get_tax_rate(date)
        return gross - fee - tax
```

`round_to_tick`은 정확성 정책 13.5.2절에 따라 가격대별 호가 단위로 반올림합니다.

`row["next_open"]`은 PriceLoader가 데이터 전처리 시 `df["next_open"] = df["open"].shift(-1)`로 미리 채워둡니다.

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

체결 결과는 `ExecutionResult` dataclass로 반환합니다 (step 013에서 도입):

```python
@dataclass
class ExecutionResult:
    price: int          # 호가 단위 보정된 체결가 (KRW 정수)
    quantity: int
    gross_amount: int   # 체결가 × 수량
    fee: int            # 수수료
    tax: int            # 거래세 (매도 시)
    net_amount: int     # gross ± fee ± tax
```

KRW 금액은 소수점 없는 정수로 처리합니다 (정확성 정책 13.14절).

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

매도 조건은 처리 주체가 다른 두 가지입니다 (02 schema 5절 참조).

```text
exit_position (포지션 기반):
익절, 손절, 최대 보유일, 트레일링 스탑.
BacktestEngine이 매일 보유 포지션마다 평가.

exit_signal (지표 기반):
이동평균선 이탈, MACD 데드크로스, RSI 기준값.
StrategyEngine이 시계열로 사전 평가.
```

### 10.1 exit_position 평가 (일중 처리)

정확성 정책 13.3절에 따라 일중 high/low로 평가합니다.

```python
def evaluate_exit_position(position, market_row, exit_rules, date):
    """
    return: (exit_price, exit_reason) | (None, None)
    여러 조건 동시 충족 시 손절 우선 (정확성 정책 13.3.2).
    """
    # 1. 갭 다운 손절 우선 검사
    for rule in exit_rules:
        if rule["type"] == "stop_loss":
            stop_price = position.entry_price * (1 - rule["percent"] / 100)
            if market_row["adj_open"] <= stop_price:
                return market_row["adj_open"], "gap_down_stop_loss"

    # 2. 갭 업 익절 검사
    for rule in exit_rules:
        if rule["type"] == "take_profit":
            target_price = position.entry_price * (1 + rule["percent"] / 100)
            if market_row["adj_open"] >= target_price:
                return market_row["adj_open"], "gap_up_take_profit"

    # 3. 일중 손절 (정확성 정책 13.3.1)
    for rule in exit_rules:
        if rule["type"] == "stop_loss":
            stop_price = position.entry_price * (1 - rule["percent"] / 100)
            if market_row["adj_low"] <= stop_price:
                return stop_price, "stop_loss"

    # 4. 일중 익절
    for rule in exit_rules:
        if rule["type"] == "take_profit":
            target_price = position.entry_price * (1 + rule["percent"] / 100)
            if market_row["adj_high"] >= target_price:
                return target_price, "take_profit"

    # 5. 트레일링 스탑 (전일까지 peak)
    for rule in exit_rules:
        if rule["type"] == "trailing_stop":
            trailing_stop_price = position.peak_price * (1 - rule["percent"] / 100)
            if market_row["adj_low"] <= trailing_stop_price:
                return trailing_stop_price, "trailing_stop"

    # 6. 최대 보유일
    holding_days = (date - position.entry_date).days
    for rule in exit_rules:
        if rule["type"] == "max_holding_days" and holding_days >= rule["days"]:
            return market_row["adj_close"], "max_holding_days"

    return None, None
```

### 10.2 exit_signal 평가

StrategyEngine이 사전 생성한 `df["exit_signal"]` 시리즈를 그대로 참조합니다. 신호가 발생한 다음 거래일 시가에 매도합니다.

### 10.3 매도 우선순위

같은 종목에 exit_position과 exit_signal이 동시 발생하면 exit_position이 우선합니다 (정확성 정책 13.16).

---

## 11. 매수 후보 처리 (priority 알고리즘)

여러 종목에서 동시에 매수 신호가 발생할 때 결정론적 우선순위를 적용합니다 (정확성 정책 13.8절).

### 11.1 처리 흐름

```text
1. 당일 final_entry_signal=True인 종목 집합 S 추출
2. allow_pyramiding=false면 보유 중 종목 제외
3. max_gap_pct_for_entry 초과 갭 종목 제외
4. 상한가/거래정지 종목 제외
5. strategy.priority.method로 정렬
6. tie_breaker 적용 (기본: symbol_asc)
7. max_daily_entries 만큼 상위 추출
8. 예수금/포지션 한도 내에서 차례로 매수 시도
9. CashManager 실행 후 추가 매수 가능 여부 재확인
```

### 11.2 priority 적용 예시

```python
def apply_priority(candidates: list[str], market_data: dict, priority: dict, seed: int):
    method = priority.get("method", "trading_value_desc")
    tie_breaker = priority.get("tie_breaker", "symbol_asc")

    if method == "trading_value_desc":
        scores = {s: market_data[s]["avg_trading_value_20d"] for s in candidates}
        sorted_symbols = sorted(candidates, key=lambda s: (-scores[s], s))
    elif method == "market_cap_desc":
        scores = {s: market_data[s]["market_cap"] for s in candidates}
        sorted_symbols = sorted(candidates, key=lambda s: (-scores[s], s))
    elif method == "random":
        rng = random.Random(seed)
        sorted_symbols = sorted(candidates, key=lambda s: (rng.random(), s))
    # ...

    if tie_breaker == "symbol_desc":
        sorted_symbols = list(reversed(sorted_symbols))

    return sorted_symbols
```

종목코드를 정렬 키의 두 번째 요소로 두는 것이 결정론을 보장합니다.

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
매도 수수료와 거래세가 반영되는지 (시계열 세율 적용 포함)
일중 high 도달 시 익절이 정확한지
일중 low 도달 시 손절이 정확한지
동일 봉 익절·손절 동시 도달 시 손절 우선
갭 다운 손절 시 시가 체결
갭 업 익절 시 시가 체결
트레일링 스탑이 전일까지의 peak 사용
최대 보유일 청산이 정확한지
거래정지 종목 매수/매도 차단
상한가 종목 매수 차단
호가 단위 반올림이 적용되는지
수정주가 사용 일관성
priority 알고리즘 결정론 (같은 입력 → 같은 결과)
random_seed 동일 시 동일 결과
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
호가 단위 반올림
수정주가 사용
일중 익절/손절 (intraday_high / intraday_low)
갭 처리
거래정지/상한가 처리
priority 알고리즘 (trading_value_desc 기본)
고정 금액 매수
최대 보유 종목 수
최대 보유일
수수료/거래세 시계열/슬리피지
일별 자산 기록
거래 내역 생성 (trade_group 단위)
event_log 기록
listing_date 기반 생존편향 완화
```

향후 확장:

```text
trailing_stop
allow_pyramiding (가중평균)
risk_management.stop_trading_on_drawdown_pct
시가총액 상위 N종목 (월별/분기별 재선정)
상장폐지 종목 데이터 통합
분봉 데이터 도입
```
