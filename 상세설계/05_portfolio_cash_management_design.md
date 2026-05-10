# 05. 포트폴리오 및 예수금 관리 상세 설계서

## 1. 목적

포트폴리오 및 예수금 관리 모듈은 실제 계좌 운용에 가까운 백테스트를 구현하기 위한 핵심 기능입니다.

이 모듈은 다음을 관리합니다.

```text
초기 자금
현재 예수금
보유 종목 (trade_group 단위)
보유 수량
평가금액
수익률
매수 가능 금액
예수금 부족 처리
일부 매도 (trade_group을 쪼개서 매도)
추가매수 (가중평균 평단가)
```

핵심 차별 기능인 **부분 매도**가 동작하려면 한 종목 안에서도 매수 lot을 구분할 수 있어야 합니다. 이를 위해 `trade_group` 개념을 도입합니다 (07 DB 문서와 동일 모델).

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

보유 종목 1개를 표현합니다. 하나의 Position은 여러 trade_group을 가질 수 있고 (추가매수 시), 부분 매도 시 trade_group 단위로 처리됩니다.

```python
from dataclasses import dataclass, field
from datetime import date


@dataclass
class TradeGroup:
    """매수 lot 하나. 부분 매도가 진행되어도 entry 정보는 유지된다."""
    trade_group_id: int
    entry_date: date
    entry_price: float          # 가중평균 평단가
    entry_quantity: int         # 최초 매수 수량
    remaining_quantity: int     # 부분 매도 후 남은 수량


@dataclass
class Position:
    symbol: str
    name: str
    current_price: float = 0.0
    peak_price: float = 0.0     # trailing_stop용 (전일까지의 high 갱신값)
    trade_groups: list[TradeGroup] = field(default_factory=list)

    @property
    def quantity(self) -> int:
        return sum(tg.remaining_quantity for tg in self.trade_groups)

    @property
    def avg_entry_price(self) -> float:
        """전체 trade_group 가중평균"""
        total_qty = self.quantity
        if total_qty == 0:
            return 0.0
        return sum(tg.entry_price * tg.remaining_quantity for tg in self.trade_groups) / total_qty

    @property
    def market_value(self) -> float:
        return self.quantity * self.current_price

    @property
    def unrealized_profit(self) -> float:
        return (self.current_price - self.avg_entry_price) * self.quantity

    @property
    def unrealized_return_pct(self) -> float:
        if self.avg_entry_price == 0:
            return 0.0
        return (self.current_price - self.avg_entry_price) / self.avg_entry_price * 100

    @property
    def first_entry_date(self) -> date:
        return min(tg.entry_date for tg in self.trade_groups)
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

trade_group을 새로 발급합니다. 추가매수 시 정책에 따라 새 trade_group을 추가하거나 기존 trade_group의 평단가를 가중평균으로 갱신할 수 있습니다 (정확성 정책 13.9절).

```python
def buy(self, symbol, name, price, quantity, date, reason, allow_pyramiding=False):
    amount = price * quantity

    if amount > self.cash:
        raise ValueError("예수금이 부족합니다.")

    self.cash -= amount

    trade_group_id = self._next_trade_group_id()

    if symbol in self.positions:
        if not allow_pyramiding:
            raise ValueError(f"{symbol} 이미 보유 중이며 추가매수가 비활성화되어 있습니다.")
        position = self.positions[symbol]
        # 기존 trade_groups에 새 lot을 추가 (가중평균은 avg_entry_price에서 자동 계산)
        position.trade_groups.append(
            TradeGroup(
                trade_group_id=trade_group_id,
                entry_date=date,
                entry_price=price,
                entry_quantity=quantity,
                remaining_quantity=quantity,
            )
        )
    else:
        self.positions[symbol] = Position(
            symbol=symbol,
            name=name,
            current_price=price,
            peak_price=price,
            trade_groups=[
                TradeGroup(
                    trade_group_id=trade_group_id,
                    entry_date=date,
                    entry_price=price,
                    entry_quantity=quantity,
                    remaining_quantity=quantity,
                )
            ],
        )

    self.trade_logs.append({
        "date": date,
        "symbol": symbol,
        "trade_group_id": trade_group_id,
        "execution_type": "BUY",
        "price": price,
        "quantity": quantity,
        "reason": reason,
    })

    return trade_group_id
```

---

## 7. 매도 처리

매도는 항상 trade_group 단위로 일어납니다. 부분 매도 시 어느 trade_group에서 얼마나 빼낼지를 명시합니다.

### 7.1 전량 매도 (지정 trade_group)

```python
def sell_trade_group(self, symbol, trade_group_id, price, quantity, date, reason):
    position = self.positions[symbol]
    tg = next(t for t in position.trade_groups if t.trade_group_id == trade_group_id)

    sell_quantity = min(quantity, tg.remaining_quantity)
    amount = price * sell_quantity

    profit = (price - tg.entry_price) * sell_quantity
    profit_rate = (price - tg.entry_price) / tg.entry_price * 100

    self.cash += amount
    tg.remaining_quantity -= sell_quantity

    self.trade_logs.append({
        "date": date,
        "symbol": symbol,
        "trade_group_id": trade_group_id,
        "execution_type": "SELL",
        "price": price,
        "quantity": sell_quantity,
        "profit": profit,
        "profit_rate": profit_rate,
        "reason": reason,
        "is_partial": sell_quantity < tg.entry_quantity,
    })

    # trade_group이 비면 제거
    position.trade_groups = [t for t in position.trade_groups if t.remaining_quantity > 0]

    # position이 비면 제거
    if not position.trade_groups:
        del self.positions[symbol]
```

### 7.2 종목 단위 매도 (FIFO)

매도 대상 trade_group이 명시되지 않은 경우 (예: exit_signal로 종목 전체 매도) FIFO 순서로 처리합니다.

```python
def sell_symbol_fifo(self, symbol, price, quantity, date, reason):
    position = self.positions[symbol]
    remaining = quantity
    for tg in sorted(position.trade_groups, key=lambda t: t.entry_date):
        if remaining <= 0:
            break
        take = min(remaining, tg.remaining_quantity)
        self.sell_trade_group(symbol, tg.trade_group_id, price, take, date, reason)
        remaining -= take
```

### 7.3 비용 처리

수수료, 거래세, 슬리피지는 ExecutionModel에서 계산해서 `ExecutionResult` dataclass로 반환한 뒤 Portfolio에 전달합니다 (step 013에서 도입).

```text
체결가 (호가단위 보정) → ExecutionModel.calculate_sell_proceeds(price, qty, date)
                       → ExecutionResult(price, quantity, gross_amount, fee, tax, net_amount)
                       → Portfolio.cash += result.net_amount
                       → trade_executions에 gross_amount/fee/tax/net_amount 영속화
```

KRW 금액(gross_amount, fee, tax, net_amount)은 소수점 없는 정수로 처리합니다 (정확성 정책 13.14절).

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

CashManager는 강제 매도 체결 시 슬리피지/세금이 0이 되는 문제를 방지하기 위해 `ExecutionModel`을 주입받아 사용합니다 (step 013에서 수정):

```python
class CashManager:
    def __init__(self, rule: dict, execution_model):
        self.rule = rule
        self.execution_model = execution_model  # 강제 매도 체결가/비용 계산에 사용
```

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

CashManager가 실행하는 일부 매도는 trade_group의 일부 수량만 매도하므로 trade_group 자체는 유지됩니다 (남은 수량만 감소).

종목코드 정렬 tie-breaker는 결정론 보장을 위해 필수입니다 (정확성 정책 13.12).

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

            # FIFO로 trade_group을 순회하며 일부 매도
            portfolio.sell_symbol_fifo(
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

        # 결정론 보장: 동순위 시 종목코드 오름차순
        if method == "lowest_return":
            return min(positions, key=lambda p: (p.unrealized_return_pct, p.symbol))

        if method == "highest_return":
            return max(positions, key=lambda p: (p.unrealized_return_pct, _neg_symbol(p.symbol)))

        if method == "largest_value":
            return max(positions, key=lambda p: (p.market_value, _neg_symbol(p.symbol)))

        raise ValueError(f"지원하지 않는 선택 방식입니다: {method}")
```

`_neg_symbol`은 max 함수에서도 종목코드 오름차순 tie-breaker를 보장하기 위한 유틸입니다 (음수화 후 비교).

CashManager가 자금 확보 시도를 했는데 자금이 여전히 부족하면 매수는 건너뜁니다.

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
trade_group이 매수 시 정확히 발급되는지
부분 매도 후 trade_group의 remaining_quantity가 정확한지
부분 매도 후에도 trade_group의 entry_price가 유지되는지
allow_pyramiding=true 시 가중평균 평단가가 정확한지
allow_pyramiding=false 시 추가매수가 차단되는지
FIFO 매도가 가장 오래된 trade_group부터 처리되는지
수익률 낮은 종목 선택이 정확한지
수익률 높은 종목 선택이 정확한지
보유 금액 큰 종목 선택이 정확한지
같은 수익률 종목들 사이에 종목코드 오름차순 결정론이 보장되는지
예수금 충분 시 CashManager가 실행되지 않는지
반복 옵션이 정확히 작동하는지
일부 매도 후 자금이 여전히 부족하면 매수가 건너뛰어지는지
현금 부족 이벤트가 기록되는지
peak_price가 trailing_stop을 위해 정확히 갱신되는지
```
