# 레고형 주식 매매 전략 생성 및 백테스트 프로그램 소프트웨어 구조

## 1. 프로그램 목표

이 프로그램은 사용자가 코딩 없이 GUI에서 주식 매매 전략을 레고 블록처럼 조립하고, 저장한 전략을 Python 백테스트 엔진이 실행하여 결과를 차트와 리포트로 분석할 수 있게 하는 전략 연구 플랫폼입니다.

핵심 구조는 다음과 같습니다.

```text
React GUI
    ↓
FastAPI API
    ↓
Strategy JSON
    ↓
ConditionRegistry 기반 StrategyEngine
    ↓
BacktestEngine
    ↓
Portfolio / CashManager / ExecutionModel
    ↓
DB 저장
    ↓
Chart UI / CSV Export
```

가장 중요한 설계 원칙은 다음입니다.

```text
전략은 Python 코드가 아니라 JSON 데이터로 저장한다.
Python 엔진은 JSON을 읽고 조건대로 실행한다.
전략 조건은 플러그인처럼 확장한다.
백테스트 엔진은 여러 모듈을 조립해서 실행한다.
GUI는 사람이 이해하기 쉬운 문장형 블록으로 구성한다.
```

---

## 2. 전체 프로젝트 구조

추천하는 전체 폴더 구조는 다음과 같습니다.

```text
stock-strategy-lab/
├─ backend/
│  ├─ app/
│  │  ├─ main.py
│  │  ├─ core/
│  │  ├─ api/
│  │  ├─ db/
│  │  ├─ models/
│  │  ├─ schemas/
│  │  ├─ services/
│  │  ├─ strategy/
│  │  ├─ backtest/
│  │  ├─ market_data/
│  │  ├─ portfolio/
│  │  ├─ reports/
│  │  └─ exporters/
│  │
│  ├─ tests/
│  └─ pyproject.toml
│
├─ frontend/
│  ├─ src/
│  │  ├─ app/
│  │  ├─ api/
│  │  ├─ pages/
│  │  ├─ components/
│  │  ├─ features/
│  │  ├─ hooks/
│  │  ├─ types/
│  │  └─ utils/
│  │
│  └─ package.json
│
├─ docs/
├─ data/
│  ├─ raw/
│  ├─ cache/
│  └─ exports/
│
└─ README.md
```

역할은 다음과 같습니다.

```text
backend:
전략 실행, 백테스트, DB 저장, CSV Export 담당

frontend:
전략 생성 GUI, 차트, 결과 표시 담당

data:
시세 원본, 캐시, Export 파일 저장

docs:
전략 JSON 스펙, API 문서, 설계 문서 저장
```

---

## 3. 백엔드 구조

FastAPI 기반 백엔드는 다음 구조를 추천합니다.

```text
backend/app/
├─ main.py
│
├─ core/
│  ├─ config.py
│  ├─ logging.py
│  └─ exceptions.py
│
├─ api/
│  ├─ routes_strategies.py
│  ├─ routes_backtests.py
│  ├─ routes_market_data.py
│  ├─ routes_reports.py
│  └─ routes_conditions.py
│
├─ db/
│  ├─ session.py
│  ├─ base.py
│  └─ migrations/
│
├─ models/
│  ├─ strategy.py
│  ├─ backtest.py
│  ├─ trade.py
│  ├─ market.py
│  └─ user.py
│
├─ schemas/
│  ├─ strategy.py
│  ├─ backtest.py
│  ├─ condition.py
│  ├─ report.py
│  └─ common.py
│
├─ services/
│  ├─ strategy_service.py
│  ├─ backtest_service.py
│  ├─ market_data_service.py
│  └─ report_service.py
│
├─ strategy/
│  ├─ engine.py
│  ├─ registry.py
│  ├─ indicators.py
│  ├─ conditions/
│  │  ├─ price.py
│  │  ├─ moving_average.py
│  │  ├─ volume.py
│  │  ├─ rsi.py
│  │  ├─ macd.py
│  │  ├─ breakout.py
│  │  └─ candle.py
│  └─ validators.py
│
├─ backtest/
│  ├─ engine.py
│  ├─ execution.py
│  ├─ result.py
│  ├─ metrics.py
│  └─ event_log.py
│
├─ portfolio/
│  ├─ portfolio.py
│  ├─ position.py
│  ├─ cash_manager.py
│  └─ position_sizer.py
│
├─ market_data/
│  ├─ provider.py
│  ├─ krx_provider.py
│  ├─ cache.py
│  ├─ universe.py
│  └─ price_loader.py
│
├─ reports/
│  ├─ summary.py
│  ├─ chart_data.py
│  ├─ trade_report.py
│  └─ cash_report.py
│
└─ exporters/
   ├─ csv_exporter.py
   └─ zip_exporter.py
```

---

## 4. 핵심 백엔드 모듈

### 4.1 strategy 모듈

전략 JSON을 읽고 조건을 평가하는 영역입니다.

```text
strategy/
├─ engine.py
├─ registry.py
├─ indicators.py
├─ conditions/
└─ validators.py
```

역할은 다음과 같습니다.

```text
engine.py:
전략 JSON 실행, entry/filter 조건 평가, 신호 생성

registry.py:
조건 타입과 실행 함수를 연결

indicators.py:
이동평균, RSI, MACD, Bollinger Band, ATR 등 지표 계산

conditions/:
가격, 이동평균, 거래량, RSI, MACD, 돌파, 캔들 조건 구현

validators.py:
전략 JSON 유효성 검사
```

---

### 4.2 ConditionRegistry 패턴

조건을 쉽게 추가하기 위해 Registry 패턴을 사용합니다.

```python
# strategy/registry.py

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


condition_registry = ConditionRegistry()
```

조건 함수 예시는 다음과 같습니다.

```python
# strategy/conditions/moving_average.py

from app.strategy.registry import condition_registry


@condition_registry.register("price_vs_ma")
def price_vs_ma(df, condition: dict):
    price_field = condition["price_field"]
    ma_period = condition["ma_period"]
    operator = condition["operator"]

    ma = df[price_field].rolling(ma_period).mean()

    if operator == ">":
        return df[price_field] > ma

    if operator == "<":
        return df[price_field] < ma

    raise ValueError(f"지원하지 않는 연산자입니다: {operator}")
```

이 방식의 장점은 다음입니다.

```text
새로운 조건 추가 시 기존 StrategyEngine을 크게 수정하지 않아도 된다.
조건 함수 하나를 만들고 registry에 등록하면 된다.
조건 목록을 GUI에도 자동 제공할 수 있다.
```

---

## 5. 조건 메타데이터 구조

GUI에서 레고 블록을 자동으로 만들려면 조건마다 메타데이터가 있어야 합니다.

예시:

```python
CONDITION_DEFINITIONS = [
    {
        "type": "price_vs_ma",
        "category": "moving_average",
        "name": "가격과 이동평균 비교",
        "description": "종가가 N일 이동평균선보다 위/아래인지 판단합니다.",
        "sentence_template": "{price_field}가 {ma_period}일 이동평균선보다 {operator_label}",
        "parameters": [
            {
                "name": "price_field",
                "label": "가격 기준",
                "input_type": "select",
                "options": [
                    {"label": "종가", "value": "close"},
                    {"label": "시가", "value": "open"},
                    {"label": "고가", "value": "high"},
                    {"label": "저가", "value": "low"}
                ],
                "default": "close"
            },
            {
                "name": "ma_period",
                "label": "이동평균 기간",
                "input_type": "number",
                "default": 20,
                "min": 2,
                "max": 300
            },
            {
                "name": "operator",
                "label": "비교",
                "input_type": "select",
                "options": [
                    {"label": "위", "value": ">"},
                    {"label": "아래", "value": "<"}
                ],
                "default": ">"
            }
        ]
    }
]
```

백엔드는 다음 API를 제공합니다.

```text
GET /api/conditions
```

프론트엔드는 이 응답을 보고 조건 블록 목록과 입력 폼을 자동 생성합니다.

이 구조를 사용하면 조건 추가 시 프론트엔드 수정 범위를 크게 줄일 수 있습니다.

---

## 6. StrategyEngine 구조

`StrategyEngine`은 전략 JSON을 읽어서 매수 신호와 필터 신호를 생성합니다.

```python
# strategy/engine.py

import pandas as pd
from app.strategy.registry import condition_registry


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

    def _build_section_signal(self, df: pd.DataFrame, section: dict):
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

## 7. BacktestEngine 구조

백테스트 엔진은 전략 신호를 받아 실제 매수/매도 시뮬레이션을 수행합니다.

```text
backtest/
├─ engine.py
├─ execution.py
├─ metrics.py
├─ result.py
└─ event_log.py
```

역할은 다음과 같습니다.

```text
engine.py:
전체 백테스트 루프 실행

execution.py:
체결 가격, 수수료, 세금, 슬리피지 처리

metrics.py:
총수익률, MDD, 승률, 손익비, Sharpe Ratio 계산

result.py:
백테스트 결과 객체 생성

event_log.py:
매수, 매도, 예수금 이벤트 기록
```

백테스트 엔진의 기본 구조는 다음과 같습니다.

```python
class BacktestEngine:
    def __init__(
        self,
        strategy_engine,
        portfolio,
        execution_model,
        cash_manager,
        market_data,
        config,
    ):
        self.strategy_engine = strategy_engine
        self.portfolio = portfolio
        self.execution_model = execution_model
        self.cash_manager = cash_manager
        self.market_data = market_data
        self.config = config

    def run(self):
        # 1. 유니버스 생성
        # 2. 날짜별 루프
        # 3. 매도 처리
        # 4. 매수 후보 탐색
        # 5. 예수금 부족 처리
        # 6. 매수 처리
        # 7. 일별 자산 기록
        pass
```

중요한 원칙은 다음입니다.

```text
BacktestEngine 안에 모든 로직을 넣지 않는다.
BacktestEngine은 오케스트레이터 역할만 한다.
전략, 포트폴리오, 체결, 현금관리, 데이터 로드를 분리한다.
```

---

## 8. Portfolio 구조

포트폴리오 모듈은 현금, 보유 종목, 평가금액을 관리합니다.

```text
portfolio/
├─ portfolio.py
├─ position.py
├─ cash_manager.py
└─ position_sizer.py
```

### 8.1 Position

```python
from dataclasses import dataclass
from datetime import date


@dataclass
class Position:
    symbol: str
    quantity: int
    entry_price: float
    entry_date: date
    current_price: float = 0.0

    @property
    def market_value(self) -> float:
        return self.quantity * self.current_price

    @property
    def unrealized_return_pct(self) -> float:
        if self.entry_price == 0:
            return 0.0
        return (self.current_price - self.entry_price) / self.entry_price * 100
```

### 8.2 Portfolio

```python
class Portfolio:
    def __init__(self, initial_cash: float):
        self.cash = initial_cash
        self.positions: dict[str, Position] = {}
        self.trade_logs = []
        self.cash_events = []

    def buy(self, symbol: str, price: float, quantity: int, date, reason: str):
        amount = price * quantity

        if amount > self.cash:
            raise ValueError("예수금이 부족합니다.")

        self.cash -= amount

        self.positions[symbol] = Position(
            symbol=symbol,
            quantity=quantity,
            entry_price=price,
            entry_date=date,
            current_price=price,
        )

    def sell(self, symbol: str, price: float, quantity: int, date, reason: str):
        position = self.positions[symbol]

        sell_quantity = min(quantity, position.quantity)
        amount = price * sell_quantity

        self.cash += amount
        position.quantity -= sell_quantity

        if position.quantity <= 0:
            del self.positions[symbol]
```

---

## 9. CashManager 구조

예수금 부족 시 일부 매도 기능은 `CashManager`가 담당합니다.

```python
class CashManager:
    def __init__(self, rule: dict):
        self.rule = rule

    def handle_shortage(self, portfolio, required_cash: float, current_date, price_provider):
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
                "symbol": target.symbol,
                "sell_quantity": quantity_to_sell,
                "cash_after": portfolio.cash,
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

이렇게 분리하면 자금 관리 로직이 전략 엔진이나 백테스트 엔진에 섞이지 않습니다.

---

## 10. MarketData 구조

시세 데이터는 별도 계층으로 분리합니다.

```text
market_data/
├─ provider.py
├─ krx_provider.py
├─ cache.py
├─ universe.py
└─ price_loader.py
```

역할은 다음과 같습니다.

```text
provider.py:
모든 데이터 공급자의 공통 인터페이스

krx_provider.py:
KRX, KIND, pykrx, 공공데이터 등 한국 주식 데이터 수집

cache.py:
DB 또는 Parquet 캐시

universe.py:
코스피 전체, 코스닥 전체, 시가총액 상위 N종목, 관심종목 등 종목군 구성

price_loader.py:
백테스트에 필요한 OHLCV 데이터 로드
```

공통 인터페이스 예시는 다음과 같습니다.

```python
from abc import ABC, abstractmethod
import pandas as pd


class MarketDataProvider(ABC):
    @abstractmethod
    def get_symbols(self, market: str) -> pd.DataFrame:
        pass

    @abstractmethod
    def get_daily_prices(
        self,
        symbols: list[str],
        start_date: str,
        end_date: str
    ) -> dict[str, pd.DataFrame]:
        pass

    @abstractmethod
    def get_market_cap(self, date: str, market: str) -> pd.DataFrame:
        pass
```

나중에 데이터 공급자를 바꾸더라도 백테스트 엔진을 수정하지 않도록 합니다.

```text
KRXProvider
NaverProvider
KiwoomProvider
LocalCsvProvider
ParquetProvider
```

---

## 11. UniverseSelector 구조

백테스트 대상 종목군 선택은 별도 클래스로 분리합니다.

```python
class UniverseSelector:
    def __init__(self, market_data_provider):
        self.provider = market_data_provider

    def select(self, universe_config: dict, date: str) -> list[str]:
        method = universe_config["selection_method"]

        if method == "all":
            return self._select_all(universe_config)

        if method == "market_cap_top_n":
            return self._select_market_cap_top_n(universe_config, date)

        if method == "watchlist":
            return universe_config["symbols"]

        if method == "manual":
            return universe_config["symbols"]

        raise ValueError(f"지원하지 않는 유니버스 선택 방식입니다: {method}")

    def _select_market_cap_top_n(self, config: dict, date: str) -> list[str]:
        market = config["market"]
        top_n = config["top_n"]

        df = self.provider.get_market_cap(date=date, market=market)
        df = df.sort_values("market_cap", ascending=False)

        return df.head(top_n)["symbol"].tolist()
```

지원할 유니버스 선택 방식은 다음과 같습니다.

```text
코스피 전체
코스닥 전체
코스피 + 코스닥 전체
관심종목
직접 선택
시가총액 상위 N종목
거래대금 상위 N종목
```

---

## 12. DB 모델 구조

초기에는 SQLite, 이후 PostgreSQL로 확장할 수 있도록 SQLAlchemy 기반으로 설계합니다.

핵심 테이블은 다음과 같습니다.

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
```

### 12.1 strategies

```text
id
name
description
strategy_json
tags
favorite
created_at
updated_at
```

### 12.2 strategy_versions

```text
id
strategy_id
version
strategy_json
change_note
created_at
```

### 12.3 backtest_runs

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
status
created_at
```

### 12.4 backtest_results

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
profit_factor
sharpe_ratio
created_at
```

### 12.5 trades

```text
id
run_id
symbol
name
entry_date
entry_price
entry_quantity
exit_date
exit_price
exit_quantity
profit
profit_rate
holding_days
exit_reason
```

### 12.6 daily_equity

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
```

### 12.7 cash_events

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

중요 원칙은 다음입니다.

```text
백테스트 실행 당시의 전략 JSON을 backtest_runs.strategy_snapshot_json에 반드시 저장한다.
전략이 나중에 수정되어도 과거 백테스트 결과가 깨지면 안 된다.
```

---

## 13. API 구조

### 13.1 전략 API

```text
GET    /api/strategies
POST   /api/strategies
GET    /api/strategies/{strategy_id}
PUT    /api/strategies/{strategy_id}
DELETE /api/strategies/{strategy_id}
POST   /api/strategies/{strategy_id}/duplicate
GET    /api/strategies/{strategy_id}/versions
```

### 13.2 조건 블록 API

```text
GET /api/conditions
```

프론트엔드는 이 API를 보고 전략 생성 블록을 구성합니다.

### 13.3 백테스트 API

```text
POST /api/backtests
GET  /api/backtests
GET  /api/backtests/{run_id}
GET  /api/backtests/{run_id}/summary
GET  /api/backtests/{run_id}/trades
GET  /api/backtests/{run_id}/daily-equity
GET  /api/backtests/{run_id}/cash-events
GET  /api/backtests/{run_id}/chart-data
```

### 13.4 CSV Export API

```text
GET /api/backtests/{run_id}/export/summary
GET /api/backtests/{run_id}/export/trades
GET /api/backtests/{run_id}/export/daily-equity
GET /api/backtests/{run_id}/export/cash-events
GET /api/backtests/{run_id}/export/zip
```

### 13.5 시장 데이터 API

```text
GET /api/market/symbols
GET /api/market/universe/preview
GET /api/market/prices/{symbol}
GET /api/market/market-cap/top
```

특히 `GET /api/market/universe/preview`는 중요합니다.

사용자가 “코스피 시가총액 상위 10종목”을 선택하면 백테스트 실행 전에 어떤 종목이 선택되는지 미리 보여줄 수 있습니다.

---

## 14. 프론트엔드 구조

React + TypeScript 기준 추천 구조입니다.

```text
frontend/src/
├─ app/
│  ├─ App.tsx
│  ├─ router.tsx
│  └─ providers.tsx
│
├─ api/
│  ├─ client.ts
│  ├─ strategies.ts
│  ├─ backtests.ts
│  ├─ conditions.ts
│  └─ market.ts
│
├─ pages/
│  ├─ StrategyListPage.tsx
│  ├─ StrategyBuilderPage.tsx
│  ├─ BacktestRunPage.tsx
│  ├─ BacktestResultPage.tsx
│  └─ StrategyComparePage.tsx
│
├─ features/
│  ├─ strategy-builder/
│  │  ├─ components/
│  │  │  ├─ BlockPalette.tsx
│  │  │  ├─ StrategyCanvas.tsx
│  │  │  ├─ ConditionCard.tsx
│  │  │  ├─ ConditionEditor.tsx
│  │  │  └─ StrategyPreview.tsx
│  │  ├─ hooks/
│  │  └─ types.ts
│  │
│  ├─ backtest-result/
│  │  ├─ components/
│  │  │  ├─ SummaryCards.tsx
│  │  │  ├─ EquityCurveChart.tsx
│  │  │  ├─ CandleTradeChart.tsx
│  │  │  ├─ TradeTable.tsx
│  │  │  ├─ CashEventTable.tsx
│  │  │  └─ CsvExportPanel.tsx
│  │  └─ hooks/
│  │
│  └─ universe-selector/
│     ├─ components/
│     └─ hooks/
│
├─ components/
│  ├─ layout/
│  ├─ ui/
│  └─ charts/
│
├─ types/
│  ├─ strategy.ts
│  ├─ backtest.ts
│  └─ market.ts
│
└─ utils/
```

프론트엔드도 기능별로 분리합니다.

```text
strategy-builder:
전략 생성 기능

backtest-result:
결과 표시 기능

universe-selector:
백테스트 대상 종목군 선택 기능
```

---

## 15. Strategy Builder GUI 구조

전략 생성 화면은 다음 컴포넌트로 나눕니다.

```text
StrategyBuilderPage
├─ StrategyHeader
├─ BlockPalette
├─ StrategyCanvas
│  ├─ EntrySection
│  ├─ ExitSection
│  ├─ FilterSection
│  ├─ CashManagementSection
│  └─ BacktestDefaultSection
├─ ConditionEditorPanel
├─ StrategyPreviewPanel
└─ StrategyValidationPanel
```

역할은 다음과 같습니다.

```text
BlockPalette:
사용 가능한 조건 블록 목록

StrategyCanvas:
사용자가 만든 전략 조건 카드 표시

ConditionCard:
문장형 조건 카드 표시

ConditionEditorPanel:
선택한 조건의 파라미터 수정

StrategyPreviewPanel:
전략 자연어 설명 표시

StrategyValidationPanel:
손절 없음, 거래대금 필터 없음 같은 경고 표시
```

---

## 16. 차트 구조

결과 차트는 별도 컴포넌트로 분리합니다.

```text
charts/
├─ CandleTradeChart.tsx
├─ EquityCurveChart.tsx
├─ DrawdownChart.tsx
├─ VolumeChart.tsx
├─ CashChart.tsx
└─ BenchmarkCompareChart.tsx
```

종목별 상세 차트는 다음과 같이 구성합니다.

```text
CandleTradeChart:
봉차트, 이동평균선, 매수/매도 마커, 마우스 오버 툴팁

EquityCurveChart:
전략 누적 수익률, 종목 단순 보유 수익률, 벤치마크 수익률
```

차트 UX 원칙은 다음입니다.

```text
봉차트 위에 수익률 숫자를 계속 표시하지 않는다.
기본은 매수/매도 마커만 표시한다.
수익률은 6개월 또는 1년 단위로만 표시한다.
상세 정보는 마우스 오버 툴팁으로 보여준다.
```

---

## 17. CSV Export 구조

백테스트 결과는 DB에 저장하고, 사용자가 원할 때 CSV로 내보냅니다.

추천 Export 파일은 다음입니다.

```text
summary.csv:
백테스트 요약 결과

trades.csv:
매수/매도 거래 내역

daily_equity.csv:
일별 자산, 예수금, 누적수익률, MDD

symbol_performance.csv:
종목별 성과

cash_events.csv:
예수금 부족, 일부 매도 이벤트

universe_history.csv:
시가총액 상위 N종목 같은 유니버스 변경 이력

strategy_snapshot.json:
백테스트 실행 당시 전략 JSON
```

다운로드 방식은 다음과 같이 구성합니다.

```text
[CSV 다운로드]

☑ 요약 결과
☑ 거래 내역
☑ 일별 자산 변화
☑ 종목별 성과
☑ 예수금 이벤트
☑ 유니버스 이력
☑ 전략 JSON

[개별 다운로드] [ZIP으로 전체 다운로드]
```

---

## 18. 테스트 구조

금융 계산이 들어가므로 테스트가 매우 중요합니다.

### 18.1 백엔드 테스트

```text
tests/
├─ strategy/
│  ├─ test_price_conditions.py
│  ├─ test_ma_conditions.py
│  ├─ test_volume_conditions.py
│  └─ test_rsi_conditions.py
│
├─ backtest/
│  ├─ test_execution.py
│  ├─ test_portfolio.py
│  ├─ test_cash_manager.py
│  └─ test_metrics.py
│
├─ api/
│  ├─ test_strategies_api.py
│  └─ test_backtests_api.py
│
└─ fixtures/
   ├─ sample_prices.csv
   └─ sample_strategy.json
```

꼭 테스트해야 할 항목은 다음입니다.

```text
골든크로스 조건 계산
RSI 계산
다음날 시가 체결
수수료/세금 반영
손절/익절 조건
예수금 부족 시 일부 매도
MDD 계산
CSV Export 결과
```

### 18.2 프론트엔드 테스트

```text
StrategyBuilder:
조건 추가, 조건 삭제, 파라미터 수정, 전략 JSON 생성 테스트

BacktestResult:
요약 카드, 거래 내역, CSV 버튼 표시 테스트
```

---

## 19. 개발 순서

확장성 좋은 구조라도 처음부터 전부 만들면 안 됩니다.

### Phase 1. 백엔드 핵심 엔진

```text
1. 전략 JSON 스키마 정의
2. ConditionRegistry 구현
3. 기본 조건 5개 구현
   - price_vs_ma
   - ma_cross
   - volume_ratio
   - rsi_level
   - take_profit / stop_loss
4. StrategyEngine 구현
5. 단일 종목 BacktestEngine 구현
6. 결과 metrics 구현
```

### Phase 2. DB 저장

```text
1. SQLite 연결
2. strategies 테이블
3. backtest_runs 테이블
4. backtest_results 테이블
5. trades 테이블
6. daily_equity 테이블
```

### Phase 3. GUI 전략 빌더

```text
1. 조건 블록 목록 API
2. 전략 생성 화면
3. 조건 카드 추가/수정/삭제
4. 전략 미리보기
5. 전략 저장
```

### Phase 4. 백테스트 실행/결과

```text
1. 백테스트 실행 화면
2. 전략 선택
3. 기간/종목/초기자금 설정
4. 결과 요약 카드
5. 거래 내역 표
6. 누적 수익률 그래프
```

### Phase 5. 종목 봉차트

```text
1. 종목 선택
2. 봉차트 표시
3. 매수/매도 마커
4. 툴팁
5. 수익률 그래프
```

### Phase 6. 포트폴리오/예수금 관리

```text
1. Portfolio 클래스
2. CashManager 클래스
3. 예수금 부족 시 일부 매도
4. cash_events 저장
5. 예수금 그래프
```

### Phase 7. CSV Export

```text
1. summary.csv
2. trades.csv
3. daily_equity.csv
4. cash_events.csv
5. zip 다운로드
```

---

## 20. 가장 중요한 설계 원칙

### 원칙 1. 전략은 데이터다

```text
전략은 Python 코드가 아니라 JSON 데이터로 저장한다.
```

### 원칙 2. 조건은 플러그인처럼 추가한다

```text
조건 하나 추가할 때 기존 엔진 코드를 크게 수정하지 않는다.
ConditionRegistry에 등록하는 방식으로 확장한다.
```

### 원칙 3. 백테스트 엔진은 오케스트레이터다

```text
BacktestEngine 안에 모든 로직을 넣지 않는다.
전략, 포트폴리오, 체결, 현금관리, 데이터 로드를 분리한다.
```

### 원칙 4. GUI는 조건 메타데이터 기반으로 만든다

```text
프론트엔드가 조건 입력폼을 하드코딩하지 않는다.
백엔드 condition definitions를 보고 입력 UI를 만든다.
```

### 원칙 5. 실행 당시 스냅샷을 저장한다

```text
전략이 나중에 바뀌어도 과거 백테스트 결과는 깨지면 안 된다.
backtest_run에 strategy_snapshot_json을 저장한다.
```

### 원칙 6. 결과 저장과 Export를 분리한다

```text
DB는 내부 저장소다.
CSV는 사용자 내보내기다.
```

---

## 21. 향후 확장 기능

이 구조로 만들면 다음 기능을 추가하기 쉽습니다.

```text
새로운 기술적 조건 추가
새로운 매도 조건 추가
시가총액 상위 N종목 유니버스 추가
거래대금 상위 N종목 유니버스 추가
예수금 관리 규칙 추가
전략 비교 기능 추가
전략 버전 비교
여러 전략 일괄 백테스트
AI 전략 생성
AI 전략 개선 제안
자동매매 연동
Walk-forward 테스트
In-sample / Out-of-sample 테스트
파라미터 최적화
```

---

## 22. 최종 정리

이 소프트웨어는 다음 구조로 개발하는 것이 가장 좋습니다.

```text
strategy/
- 조건 판단

backtest/
- 백테스트 흐름

portfolio/
- 보유 종목, 예수금, 포지션 관리

market_data/
- 시세, 종목군, 시가총액 데이터

reports/
- 결과 요약, 차트 데이터

exporters/
- CSV, ZIP 내보내기

api/
- 프론트엔드와 연결
```

최종 한 문장 정리는 다음입니다.

```text
전략 조건은 플러그인처럼 추가하고,
전략은 JSON으로 저장하며,
백테스트 엔진은 여러 모듈을 조립해서 실행하는 구조가 가장 확장성 좋다.
```
