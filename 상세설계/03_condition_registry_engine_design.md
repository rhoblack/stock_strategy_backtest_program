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

조건 타입과 실행 함수를 연결합니다.

```python
class ConditionRegistry:
    def __init__(self):
        self._conditions = {}

    def register(self, condition_type: str):
        def decorator(func):
            self._conditions[condition_type] = func
            return func
        return decorator

    def evaluate(self, condition_type: str, df, condition: dict):
        if condition_type not in self._conditions:
            raise ValueError(f"등록되지 않은 조건입니다: {condition_type}")

        return self._conditions[condition_type](df, condition)

    def list_condition_types(self):
        return list(self._conditions.keys())


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

MVP에서 우선 구현할 조건입니다.

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
take_profit
stop_loss
max_holding_days
```

단, `take_profit`, `stop_loss`, `max_holding_days`는 포지션 상태가 필요하므로 BacktestEngine/Portfolio에서 처리합니다.

---

## 7. 조건 구현 예시

### 7.1 price_vs_ma

```python
@condition_registry.register("price_vs_ma")
def price_vs_ma(df, condition):
    price_field = condition["price_field"]
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

```python
class StrategyEngine:
    def __init__(self, strategy_json: dict):
        self.strategy = strategy_json

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()

        entry = self.strategy.get("entry")
        filters = self.strategy.get("filters")

        df["entry_signal"] = self._build_section_signal(df, entry)

        if filters:
            df["filter_signal"] = self._build_section_signal(df, filters)
            df["final_entry_signal"] = df["entry_signal"] & df["filter_signal"]
        else:
            df["filter_signal"] = True
            df["final_entry_signal"] = df["entry_signal"]

        return df

    def _build_section_signal(self, df, section):
        conditions = section.get("conditions", [])
        logic = section.get("logic", "AND")

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
2. @condition_registry.register("condition_type") 등록
3. CONDITION_DEFINITIONS에 GUI 메타데이터 추가
4. 테스트 작성
5. API에서 조건 목록 노출 확인
```

이 방식으로 조건 기능을 플러그인처럼 확장합니다.
