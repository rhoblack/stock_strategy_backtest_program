# 05. 포트폴리오 및 예수금 관리 상세 설계서

## 1. 목적

포트폴리오 및 예수금 관리 모듈은 실제 계좌 운용에 가까운 백테스트를 구현하기 위한 핵심 기능입니다.

이 모듈은 다음을 관리합니다.

```text
초기 자금
현재 예수금
보유 종목
보유 수량
평가금액
수익률
매수 가능 금액
예수금 부족 처리
일부 매도
```

---

## 2. 핵심 설계 원칙

```text
전략 신호와 자금 관리는 분리한다.
매수/매도 판단은 StrategyEngine/BacktestEngine이 한다.
현금과 보유 종목 상태는 Portfolio가 관리한다.
예수금 부족 처리 규칙은 CashManager가 관리한다.
```

---

## 3. 주요 클래스

```text
Portfolio
Position
CashManager
PositionSizer
```

---

## 4. Position 설계

보유 종목 1개를 표현합니다.

```python
from dataclasses import dataclass
from datetime import date


@dataclass
class Position:
    symbol: str
    name: str
    quantity: int
    entry_price: float
    entry_date: date
    current_price: float = 0.0

    @property
    def market_value(self) -> float:
        return self.quantity * self.current_price

    @property
    def unrealized_profit(self) -> float:
        return (self.current_price - self.entry_price) * self.quantity

    @property
    def unrealized_return_pct(self) -> float:
        if self.entry_price == 0:
            return 0.0
        return (self.current_price - self.entry_price) / self.entry_price * 100
```

---

## 5. Portfolio 설계

Portfolio는 전체 계좌 상태를 관리합니다.

```python
class Portfolio:
    def __init__(self, initial_cash: float):
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.positions: dict[str, Position] = {}
        self.trade_logs = []
        self.cash_events = []

    def total_stock_value(self) -> float:
        return sum(position.market_value for position in self.positions.values())

    def total_equity(self) -> float:
        return self.cash + self.total_stock_value()

    def positions_count(self) -> int:
        return len(self.positions)
```

---

## 6. 매수 처리

```python
def buy(self, symbol, name, price, quantity, date, reason):
    amount = price * quantity

    if amount > self.cash:
        raise ValueError("예수금이 부족합니다.")

    self.cash -= amount

    if symbol in self.positions:
        # MVP에서는 추가매수 비활성화 가능
        pass
    else:
        self.positions[symbol] = Position(
            symbol=symbol,
            name=name,
            quantity=quantity,
            entry_price=price,
            entry_date=date,
            current_price=price,
        )

    self.trade_logs.append({
        "date": date,
        "symbol": symbol,
        "type": "BUY",
        "price": price,
        "quantity": quantity,
        "reason": reason,
    })
```

---

## 7. 매도 처리

```python
def sell(self, symbol, price, quantity, date, reason):
    position = self.positions[symbol]

    sell_quantity = min(quantity, position.quantity)
    amount = price * sell_quantity

    profit = (price - position.entry_price) * sell_quantity
    profit_rate = (price - position.entry_price) / position.entry_price * 100

    self.cash += amount
    position.quantity -= sell_quantity

    self.trade_logs.append({
        "date": date,
        "symbol": symbol,
        "type": "SELL",
        "price": price,
        "quantity": sell_quantity,
        "profit": profit,
        "profit_rate": profit_rate,
        "reason": reason,
    })

    if position.quantity <= 0:
        del self.positions[symbol]
```

실제 구현에서는 수수료, 세금, 슬리피지는 ExecutionModel에서 계산 후 Portfolio에 반영합니다.

---

## 8. PositionSizer 설계

얼마를 매수할지 결정합니다.

지원 방식:

```text
fixed_amount:
종목당 고정 금액 매수

fixed_ratio:
총자산의 N% 매수

daily_budget:
1일 매수 예산 안에서 매수

equal_weight:
최대 보유 종목 수 기준 균등 비중
```

MVP에서는 `fixed_amount`, `daily_budget`을 우선 지원합니다.

```python
class PositionSizer:
    def __init__(self, config):
        self.config = config

    def calculate_quantity(self, price, portfolio):
        method = self.config["method"]

        if method == "fixed_amount":
            amount = self.config["amount"]
            return int(amount // price)

        if method == "fixed_ratio":
            ratio = self.config["ratio"]
            amount = portfolio.total_equity() * ratio
            return int(amount // price)

        raise ValueError(f"지원하지 않는 position sizing 방식입니다: {method}")
```

---

## 9. CashManager 설계

예수금 부족 시 현금을 확보하는 규칙을 실행합니다.

예시 규칙:

```json
{
  "enabled": true,
  "daily_buy_budget": 1000000,
  "cash_shortage_rule": {
    "trigger": {
      "type": "cash_below_daily_buy_budget"
    },
    "action": {
      "type": "partial_sell",
      "sell_fraction": 0.25
    },
    "target_selection": {
      "method": "lowest_return"
    },
    "repeat_until_cash_sufficient": true
  }
}
```

---

## 10. 예수금 부족 처리 흐름

```text
1. 오늘 매수 후보가 있다.
2. 오늘 필요한 매수 예산을 계산한다.
3. 현재 예수금이 부족한지 확인한다.
4. 부족하면 CashManager를 실행한다.
5. 매도 대상 포지션을 선택한다.
6. 선택한 포지션의 일부를 매도한다.
7. 예수금이 충분해질 때까지 반복할지 확인한다.
8. 매수 가능하면 신규 매수를 실행한다.
9. cash_events에 기록한다.
```

---

## 11. 매도 대상 선택 기준

지원할 기준:

```text
lowest_return:
수익률이 가장 낮은 종목부터 매도

highest_return:
수익률이 가장 높은 종목부터 매도

largest_value:
보유 평가금액이 가장 큰 종목부터 매도

oldest_position:
가장 오래 보유한 종목부터 매도

newest_position:
가장 최근 매수한 종목부터 매도
```

MVP에서는 다음만 지원합니다.

```text
lowest_return
highest_return
largest_value
```

---

## 12. CashManager 예시 코드

```python
class CashManager:
    def __init__(self, rule: dict):
        self.rule = rule

    def handle_shortage(self, portfolio, required_cash, current_date, price_provider):
        if portfolio.cash >= required_cash:
            return []

        events = []
        repeat = self.rule.get("repeat_until_cash_sufficient", False)

        while portfolio.cash < required_cash:
            target = self._select_position(portfolio)

            if target is None:
                break

            sell_fraction = self.rule["action"]["sell_fraction"]
            quantity_to_sell = int(target.quantity * sell_fraction)

            if quantity_to_sell <= 0:
                break

            price = price_provider.get_price(target.symbol, current_date)
            cash_before = portfolio.cash

            portfolio.sell(
                symbol=target.symbol,
                price=price,
                quantity=quantity_to_sell,
                date=current_date,
                reason="cash_shortage_partial_sell",
            )

            events.append({
                "date": current_date,
                "event_type": "cash_shortage",
                "cash_before": cash_before,
                "required_cash": required_cash,
                "action": "partial_sell",
                "symbol": target.symbol,
                "sell_quantity": quantity_to_sell,
                "cash_after": portfolio.cash,
                "reason": "cash_shortage_partial_sell",
            })

            if not repeat:
                break

        return events

    def _select_position(self, portfolio):
        method = self.rule["target_selection"]["method"]
        positions = list(portfolio.positions.values())

        if not positions:
            return None

        if method == "lowest_return":
            return min(positions, key=lambda p: p.unrealized_return_pct)

        if method == "highest_return":
            return max(positions, key=lambda p: p.unrealized_return_pct)

        if method == "largest_value":
            return max(positions, key=lambda p: p.market_value)

        raise ValueError(f"지원하지 않는 선택 방식입니다: {method}")
```

---

## 13. cash_events 저장 항목

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
```

예시:

```text
2024-06-11
예수금 부족 발생
현금 620,000원
필요 현금 1,000,000원
삼성전자 5주 일부 매도
매도 후 현금 1,030,000원
```

---

## 14. 결과 화면 표시

자금 관리 탭에서 보여줄 내용:

```text
초기 자금
최종 자산
평균 예수금
최소 예수금
현금 부족 발생 횟수
현금 부족으로 매수 실패한 횟수
예수금 확보용 일부 매도 횟수
일부 매도로 확보한 총 현금
```

차트:

```text
예수금 변화 그래프
총자산 변화 그래프
보유 평가금액 그래프
현금 부족 이벤트 표시
일부 매도 이벤트 표시
```

---

## 15. 테스트 항목

```text
초기 현금 설정이 정확한지
매수 후 예수금 차감이 정확한지
매도 후 예수금 증가가 정확한지
부분 매도 후 보유 수량이 정확한지
수익률 낮은 종목 선택이 정확한지
수익률 높은 종목 선택이 정확한지
보유 금액 큰 종목 선택이 정확한지
예수금 충분 시 CashManager가 실행되지 않는지
반복 옵션이 정확히 작동하는지
현금 부족 이벤트가 기록되는지
```
