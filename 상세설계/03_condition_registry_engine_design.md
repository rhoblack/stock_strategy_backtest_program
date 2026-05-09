# 03. 조건 Registry 및 전략 실행 엔진 상세 설계서

## 1. 목적

조건 Registry와 StrategyEngine은 전략 JSON에 정의된 조건을 실제 pandas 시계열 연산으로 변환해 매수/필터 신호를 생성하는 핵심 모듈입니다.

이 모듈의 목표는 다음입니다.

```text
조건 타입을 플러그인처럼 추가할 수 있게 한다.
전략 JSON을 안전하게 실행한다.
GUI 조건 정의와 백엔드 실행 조건을 연결한다.
StrategyEngine 수정 없이 조건을 계속 확장할 수 있게 한다.
```

---

## 2. 핵심 구조

```text
Strategy JSON
    ↓
StrategyEngine
    ↓
ConditionRegistry
    ↓
Condition Function
    ↓
pandas Series[bool]
```

---

## 3. ConditionRegistry

조건 타입과 실행 함수, 메타데이터를 함께 등록합니다.

```python
from dataclasses import dataclass


@dataclass
class ConditionEntry:
    func: callable
    requires_position: bool
    category: str


class ConditionRegistry:
    def __init__(self):
        self._conditions: dict[str, ConditionEntry] = {}

    def register(self, condition_type: str, requires_position: bool = False, category: str = "general"):
        def decorator(func):
            self._conditions[condition_type] = ConditionEntry(
                func=func,
                requires_position=requires_position,
                category=category,
            )
            return func
        return decorator

    def evaluate(self, condition_type: str, df, condition: dict):
        entry = self._conditions.get(condition_type)
        if entry is None:
            raise ValueError(f"등록되지 않은 조건입니다: {condition_type}")
        if entry.requires_position:
            raise ValueError(
                f"{condition_type}은 포지션 조건입니다. "
                "StrategyEngine이 아니라 BacktestEngine/Portfolio가 처리해야 합니다."
            )
        return entry.func(df, condition)

    def evaluate_position(self, condition_type: str, position, market_row, condition: dict):
        entry = self._conditions.get(condition_type)
        if entry is None:
            raise ValueError(f"등록되지 않은 조건입니다: {condition_type}")
        if not entry.requires_position:
            raise ValueError(f"{condition_type}은 시계열 조건입니다.")
        return entry.func(position, market_row, condition)

    def is_position_condition(self, condition_type: str) -> bool:
        return self._conditions[condition_type].requires_position

    def list_conditions(self):
        return [
            {"type": t, "requires_position": e.requires_position, "category": e.category}
            for t, e in self._conditions.items()
        ]


condition_registry = ConditionRegistry()
```

---

## 4. 조건 함수 규칙

모든 조건 함수는 같은 인터페이스를 사용합니다.

```python
def condition_function(df: pd.DataFrame, condition: dict) -> pd.Series:
    ...
```

반환값은 반드시 `pd.Series[bool]`이어야 합니다.

```text
True:
해당 날짜에 조건 만족

False:
해당 날짜에 조건 불만족
```

---

## 5. 지표 함수와 조건 함수 분리

지표 계산과 조건 판단은 분리합니다.

```text
indicators.py:
이동평균, RSI, MACD, ATR 등 수치 계산

conditions/*.py:
계산된 지표를 기준으로 True/False 조건 판단
```

예:

```python
def moving_average(close, period):
    return close.rolling(period).mean()
```

```python
@condition_registry.register("price_vs_ma")
def price_vs_ma(df, condition):
    ma = moving_average(df[condition["price_field"]], condition["ma_period"])
    return df[condition["price_field"]] > ma
```

---

## 6. 주요 조건 타입

조건은 평가 주체에 따라 두 가지로 분류합니다.

### 6.1 시계열 조건 (requires_position = false)

`df` 시계열만으로 평가 가능. StrategyEngine이 처리. entry / exit_signal / filters에 사용.

```text
price_change_pct
price_vs_ma
ma_cross
ma_alignment
volume_ratio
avg_trading_value
rsi_level
rsi_cross
macd_cross
new_high_breakout
momentum_return
bullish_candle
gap_pct
market_index_filter
```

### 6.2 포지션 조건 (requires_position = true)

매수가 / 보유일 / 일중 high·low가 필요. BacktestEngine + Portfolio가 처리. exit_position에만 사용 가능.

```text
take_profit
stop_loss
max_holding_days
trailing_stop
```

### 6.3 라우팅 메커니즘

ConditionRegistry에 등록된 메타데이터의 `requires_position` 플래그가 라우팅을 결정합니다.

```text
strategy.exit_signal에 requires_position=true 조건이 들어가면 validation 에러
strategy.exit_position에 requires_position=false 조건이 들어가면 validation 에러
```

GUI는 두 영역을 분리하여 메뉴 노출 자체를 분리합니다 (BlockPalette 카테고리 분리).

---

## 7. 조건 구현 예시

### 7.0 가격 필드 기본값

모든 가격 기반 조건의 `price_field` 기본값은 **수정주가**입니다 (정확성 정책 13.7절).

```text
adj_close (기본)
adj_open
adj_high
adj_low
close      (원 가격, 거래대금 필터 등에서만 사용 권장)
```

### 7.1 price_vs_ma

```python
@condition_registry.register(
    "price_vs_ma",
    requires_position=False,
    category="moving_average",
)
def price_vs_ma(df, condition):
    price_field = condition.get("price_field", "adj_close")
    ma_period = condition["ma_period"]
    operator = condition["operator"]

    ma = df[price_field].rolling(ma_period).mean()

    return compare(df[price_field], operator, ma)
```

### 7.2 ma_cross

```python
@condition_registry.register("ma_cross")
def ma_cross(df, condition):
    short_period = condition["short_period"]
    long_period = condition["long_period"]
    direction = condition["direction"]

    short_ma = df["close"].rolling(short_period).mean()
    long_ma = df["close"].rolling(long_period).mean()

    if direction == "golden_cross":
        return (short_ma.shift(1) <= long_ma.shift(1)) & (short_ma > long_ma)

    if direction == "dead_cross":
        return (short_ma.shift(1) >= long_ma.shift(1)) & (short_ma < long_ma)

    raise ValueError(f"지원하지 않는 direction입니다: {direction}")
```

### 7.3 volume_ratio

```python
@condition_registry.register("volume_ratio")
def volume_ratio(df, condition):
    period = condition["period"]
    operator = condition["operator"]
    value = condition["value"]

    volume_ma = df["volume"].rolling(period).mean()
    ratio = df["volume"] / volume_ma

    return compare(ratio, operator, value)
```

### 7.4 new_high_breakout

look-ahead bias를 피하기 위해 오늘 값을 제외합니다.

```python
@condition_registry.register("new_high_breakout")
def new_high_breakout(df, condition):
    field = condition.get("field", "close")
    period = condition["period"]

    previous_high = df[field].shift(1).rolling(period).max()

    return df[field] > previous_high
```

---

## 8. compare 유틸리티

```python
def compare(left, operator: str, right):
    if operator == ">":
        return left > right
    if operator == ">=":
        return left >= right
    if operator == "<":
        return left < right
    if operator == "<=":
        return left <= right
    if operator == "==":
        return left == right

    raise ValueError(f"지원하지 않는 연산자입니다: {operator}")
```

---

## 9. StrategyEngine

StrategyEngine은 entry / exit_signal / filters만 처리합니다. exit_position은 BacktestEngine이 처리합니다.

```python
class StrategyEngine:
    def __init__(self, strategy_json: dict):
        self.strategy = strategy_json

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()

        entry = self.strategy.get("entry")
        exit_signal = self.strategy.get("exit_signal")
        filters = self.strategy.get("filters")

        df["entry_signal"] = self._build_section_signal(df, entry)
        df["exit_signal"] = self._build_section_signal(df, exit_signal) if exit_signal else False

        if filters:
            df["filter_signal"] = self._build_section_signal(df, filters)
            df["final_entry_signal"] = df["entry_signal"] & df["filter_signal"]
        else:
            df["filter_signal"] = True
            df["final_entry_signal"] = df["entry_signal"]

        return df

    def _build_section_signal(self, df, section):
        if section is None:
            return pd.Series(False, index=df.index)

        logic = section.get("logic", "AND")

        if logic == "GROUP":
            return self._build_group_signal(df, section)

        conditions = section.get("conditions", [])
        if not conditions:
            return pd.Series(True, index=df.index)

        signals = [
            condition_registry.evaluate(condition["type"], df, condition)
            for condition in conditions
        ]

        if logic == "AND":
            result = signals[0]
            for signal in signals[1:]:
                result = result & signal
            return result

        if logic == "OR":
            result = signals[0]
            for signal in signals[1:]:
                result = result | signal
            return result

        raise ValueError(f"지원하지 않는 logic입니다: {logic}")

    def _build_group_signal(self, df, section):
        operator = section.get("operator", "OR")
        group_signals = [
            self._build_section_signal(df, group)
            for group in section.get("groups", [])
        ]
        if not group_signals:
            return pd.Series(True, index=df.index)

        result = group_signals[0]
        if operator == "OR":
            for signal in group_signals[1:]:
                result = result | signal
        elif operator == "AND":
            for signal in group_signals[1:]:
                result = result & signal
        else:
            raise ValueError(f"지원하지 않는 GROUP operator입니다: {operator}")
        return result
```

---

## 10. 조건 메타데이터

GUI 블록 생성을 위해 조건 정의 메타데이터를 제공합니다.

```python
{
    "type": "volume_ratio",
    "category": "volume",
    "name": "거래량이 평균보다 N배 이상",
    "sentence_template": "거래량이 {period}일 평균 거래량의 {value}배 이상",
    "parameters": [
        {
            "name": "period",
            "label": "평균 기간",
            "input_type": "number",
            "default": 20
        },
        {
            "name": "value",
            "label": "배수",
            "input_type": "number",
            "default": 2.0
        }
    ]
}
```

---

## 11. API

조건 목록 조회 API:

```text
GET /api/conditions
```

응답:

```json
[
  {
    "type": "price_vs_ma",
    "category": "moving_average",
    "name": "가격과 이동평균 비교",
    "parameters": []
  }
]
```

---

## 12. 테스트 항목

```text
조건 함수가 pd.Series[bool]을 반환하는지
look-ahead bias가 없는지
operator 비교가 정확한지
rolling 기간이 올바른지
NaN 구간 처리 방식이 일관적인지
등록되지 않은 condition type에서 에러가 나는지
StrategyEngine AND/OR 조합이 정확한지
```

---

## 13. 확장 방식

새 조건 추가 절차:

```text
1. strategy/conditions/에 조건 함수 추가
2. @condition_registry.register("condition_type", requires_position=..., category=...) 등록
3. CONDITION_DEFINITIONS에 GUI 메타데이터 추가
4. 테스트 작성 (look-ahead bias 체크 필수)
5. API에서 조건 목록 노출 확인
6. 가격 기반 조건이면 기본 price_field를 adj_close로 설정했는지 확인
```

이 방식으로 조건 기능을 플러그인처럼 확장합니다.

---

## 14. 포지션 조건 함수 인터페이스

`requires_position=True` 조건의 인터페이스는 시계열 조건과 다릅니다.

```python
def position_condition_function(
    position,        # Portfolio.Position 인스턴스
    market_row,      # 당일 시장 데이터 row (open, high, low, close, adj_*)
    condition: dict,
) -> tuple[bool, str | None]:
    """
    return (triggered, exit_reason)
    triggered=True 시 exit_reason 문자열을 함께 반환.
    """
    ...
```

예: take_profit (정확성 정책 13.3절 참조)

```python
@condition_registry.register("take_profit", requires_position=True, category="exit_position")
def take_profit(position, market_row, condition):
    percent = condition["percent"]
    trigger = condition.get("trigger", "intraday_high")
    target_price = position.entry_price * (1 + percent / 100)

    if trigger == "intraday_high":
        if market_row["adj_high"] >= target_price:
            return True, "take_profit"
    elif trigger == "close":
        if market_row["adj_close"] >= target_price:
            return True, "take_profit"

    return False, None
```

BacktestEngine은 매일 보유 포지션마다 exit_position 조건들을 순회하며 위 함수를 호출합니다.

---

## 15. 조건 메타데이터 등록 규칙

GUI 자동화를 위해 메타데이터에는 다음을 반드시 포함합니다.

```text
type
category
requires_position
name (한국어)
sentence_template
parameters (각 파라미터의 input_type, default, min, max, options)
allowed_in: ["entry", "exit_signal", "exit_position", "filters"]
```

`allowed_in`은 GUI가 조건을 어느 섹션에 노출할지 결정합니다.
