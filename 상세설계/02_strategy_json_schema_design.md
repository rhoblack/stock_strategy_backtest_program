# 02. 전략 JSON 스키마 상세 설계서

## 1. 목적

전략 JSON은 GUI에서 조립한 매매 전략을 저장하고 실행 엔진에 전달하기 위한 표준 데이터 형식입니다.

이 프로그램에서는 전략을 Python 코드로 저장하지 않습니다.

```text
전략 = JSON 데이터
실행 = Python StrategyEngine
```

---

## 2. 설계 원칙

```text
JSON 안에는 실행 코드가 들어가면 안 된다.
모든 조건은 type + parameter 형태로 표현한다.
실행 가능한 type은 ConditionRegistry에 등록된 것만 허용한다.
전략 JSON은 저장, 복사, 버전관리, 백테스트 스냅샷에 사용된다.
backtest accuracy 정책(13 문서)에 명시된 모든 정책은 전략 JSON에서 명시 가능해야 한다.
```

나쁜 예:

```json
{
  "condition": "df['close'] > df['close'].rolling(20).mean()"
}
```

좋은 예:

```json
{
  "type": "price_vs_ma",
  "price_field": "adj_close",
  "ma_period": 20,
  "operator": ">"
}
```

---

## 3. 최상위 구조

```json
{
  "name": "거래량 돌파 스윙 전략",
  "version": "1.0",
  "description": "거래량 급증과 이동평균 추세 필터를 이용한 단기 스윙 전략",

  "entry": {},
  "exit_signal": {},
  "exit_position": {},
  "filters": {},
  "priority": {},
  "position_sizing": {},
  "cash_management": {},
  "risk_management": {},
  "execution": {},
  "metadata": {}
}
```

기존 설계의 `exit`은 `exit_signal`과 `exit_position`으로 분리됩니다 (이유는 5절 참조).

---

## 4. entry 구조

매수 조건입니다.

```json
{
  "entry": {
    "logic": "AND",
    "conditions": [
      {
        "type": "price_vs_ma",
        "price_field": "adj_close",
        "ma_period": 20,
        "operator": ">"
      },
      {
        "type": "volume_ratio",
        "period": 20,
        "operator": ">=",
        "value": 2.0
      }
    ]
  }
}
```

### 지원 logic

```text
AND
OR
GROUP
```

MVP에서는 `AND`, `OR`, 그리고 1단계 `GROUP`을 지원합니다.

### GROUP 표현 (1단계)

`(A AND B) OR (C AND D)` 같은 흔한 복합 조건을 표현할 수 있어야 합니다.

```json
{
  "entry": {
    "logic": "GROUP",
    "operator": "OR",
    "groups": [
      {
        "logic": "AND",
        "conditions": [
          { "type": "price_vs_ma", "price_field": "adj_close", "ma_period": 20, "operator": ">" },
          { "type": "volume_ratio", "period": 20, "operator": ">=", "value": 2.0 }
        ]
      },
      {
        "logic": "AND",
        "conditions": [
          { "type": "rsi_level", "period": 14, "operator": "<=", "value": 30 },
          { "type": "bullish_candle" }
        ]
      }
    ]
  }
}
```

GROUP은 1단계 중첩만 지원합니다 (그룹 안에 그룹은 향후 확장).

---

## 5. exit 분리: exit_signal vs exit_position

매도 조건은 처리 주체가 다른 두 가지로 명확히 분리합니다.

```text
exit_signal:
지표 기반 매도. df 시계열로 평가 가능.
StrategyEngine이 처리.
예) 이동평균선 이탈, MACD 데드크로스, RSI 과매수.

exit_position:
포지션 기반 매도. 매수가 / 보유일 / 일중 high·low가 필요.
BacktestEngine + Portfolio가 처리.
예) take_profit, stop_loss, max_holding_days, trailing_stop.
```

이 분리는 ConditionRegistry 메타데이터의 `requires_position` 플래그(03 문서)와 일치해야 합니다. GUI는 두 섹션을 별도 영역으로 표시합니다.

### 5.1 exit_signal 예시

```json
{
  "exit_signal": {
    "logic": "OR",
    "conditions": [
      {
        "type": "price_vs_ma",
        "price_field": "adj_close",
        "ma_period": 20,
        "operator": "<"
      },
      {
        "type": "macd_cross",
        "direction": "dead_cross"
      }
    ]
  }
}
```

### 5.2 exit_position 예시

```json
{
  "exit_position": {
    "logic": "OR",
    "conditions": [
      {
        "type": "take_profit",
        "percent": 7,
        "trigger": "intraday_high"
      },
      {
        "type": "stop_loss",
        "percent": 3,
        "trigger": "intraday_low"
      },
      {
        "type": "max_holding_days",
        "days": 10
      },
      {
        "type": "trailing_stop",
        "percent": 5,
        "peak_basis": "intraday_high"
      }
    ]
  }
}
```

`trigger` 필드는 일중 도달 vs 종가 기준을 명시합니다 (정확성 정책 13.3절 참조). 기본값은 `intraday_high` / `intraday_low`입니다.

---

## 6. filters 구조

필터 조건입니다.

```json
{
  "filters": {
    "logic": "AND",
    "conditions": [
      {
        "type": "avg_trading_value",
        "period": 20,
        "operator": ">=",
        "value": 5000000000
      },
      {
        "type": "market_index_filter",
        "index": "KOSDAQ",
        "condition": {
          "type": "price_vs_ma",
          "price_field": "close",
          "ma_period": 20,
          "operator": ">"
        }
      }
    ]
  }
}
```

`entry`와 분리하는 이유:

```text
entry:   어떤 종목을 살 것인가?
filters: 어떤 환경에서만 살 것인가?
```

거래대금 필터는 시장 유동성 기준이므로 `close` (수정 전 원 가격)를 사용하는 것이 일반적입니다.

---

## 7. priority 구조 (신규)

여러 종목이 동시에 매수 신호를 낼 때 우선순위를 결정합니다. 이 섹션이 없으면 결정론이 깨집니다 (정확성 정책 13.8절 참조).

```json
{
  "priority": {
    "method": "trading_value_desc",
    "tie_breaker": "symbol_asc"
  }
}
```

### 지원 method

```text
trading_value_desc:  20일 평균 거래대금 큰 순 (기본)
market_cap_desc:     시가총액 큰 순
market_cap_asc:      시가총액 작은 순
volume_ratio_desc:   거래량 급증 비율 큰 순
price_change_desc:   당일 등락률 큰 순
random:              random_seed로 결정론 보장
```

### tie_breaker

```text
symbol_asc:  종목코드 오름차순 (기본)
symbol_desc: 종목코드 내림차순
```

priority 섹션이 누락되면 기본값(`trading_value_desc` + `symbol_asc`)을 적용합니다.

---

## 8. position_sizing 구조

얼마나 매수할지를 결정합니다. **`max_positions`와 `daily_buy_budget` 같은 자금 관련 항목은 모두 이 섹션에 통합**합니다 (cash_management와의 중복 제거).

```json
{
  "position_sizing": {
    "method": "fixed_amount",
    "amount": 1000000,
    "max_positions": 10,
    "max_daily_entries": 3,
    "daily_buy_budget": 1000000,
    "allow_pyramiding": false
  }
}
```

### 지원 method

```text
fixed_amount:
종목당 고정 금액 매수

fixed_ratio:
총자산의 N% 매수

equal_weight:
보유 가능 종목 수 기준 균등 비중 매수

daily_budget:
1일 매수 예산 안에서 매수
```

MVP에서는 `fixed_amount`, `daily_budget`을 우선 지원합니다.

### 추가매수 (pyramiding)

```text
allow_pyramiding: false (기본)
이미 보유 중인 종목에서 신호가 발생해도 추가 매수하지 않음.

allow_pyramiding: true 시:
pyramiding_method: weighted_average (MVP 유일 지원)
max_pyramiding_count: 최대 N회 추가매수 (기본 3)
```

평단가는 정확성 정책 13.9절에 따라 가중평균 방식으로 갱신합니다.

---

## 9. cash_management 구조

예수금 부족 시 일부 매도 규칙을 정의합니다. 이 섹션은 **자금 확보 규칙만 다룹니다.** `daily_buy_budget` 같은 항목은 position_sizing으로 옮겼습니다.

```json
{
  "cash_management": {
    "enabled": true,
    "shortage_rule": {
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
}
```

### trigger.type

```text
cash_below_daily_buy_budget:
당일 매수 예산보다 예수금이 적을 때

cash_below_threshold:
예수금이 절대값 threshold 미만일 때 (값을 함께 지정)
```

### target_selection.method

```text
lowest_return:    수익률이 가장 낮은 종목부터
highest_return:   수익률이 가장 높은 종목부터
largest_value:    보유 평가금액이 가장 큰 종목부터
oldest_position:  가장 오래 보유한 종목부터
newest_position:  가장 최근 매수한 종목부터
```

MVP는 `lowest_return`, `highest_return`, `largest_value`만 지원합니다.

---

## 10. risk_management 구조

리스크 관리 설정입니다. **`max_positions`는 position_sizing으로 옮겼으므로 여기서는 손실 한도 / 거래 중단 등만 다룹니다.**

```json
{
  "risk_management": {
    "stop_trading_on_drawdown_pct": 20,
    "max_position_ratio": 0.2,
    "max_daily_loss_pct": 5
  }
}
```

```text
stop_trading_on_drawdown_pct:
누적 MDD가 N% 초과 시 신규 매수 중단 (보유는 유지)

max_position_ratio:
한 종목에 총자산 대비 최대 N% 한도

max_daily_loss_pct:
하루 손실이 N% 초과 시 당일 추가 매수 중단
```

MVP에서는 `stop_trading_on_drawdown_pct`만 우선 구현합니다.

---

## 11. execution 구조

체결 방식과 비용 설정입니다. 거래세는 시계열을 지원합니다 (정확성 정책 13.6절).

```json
{
  "execution": {
    "entry_price": "next_open",
    "exit_price": "next_open",
    "fee_rate": 0.00015,
    "tax_rate": [
      { "from": "2020-01-01", "rate": 0.0023 },
      { "from": "2023-01-01", "rate": 0.0020 },
      { "from": "2024-01-01", "rate": 0.0018 },
      { "from": "2025-01-01", "rate": 0.0015 }
    ],
    "slippage": 0.001,
    "use_adjusted_price": true,
    "max_gap_pct_for_entry": 5.0,
    "allow_buy_limit_up": false,
    "allow_sell_limit_down": false,
    "tick_rounding": "buy_up_sell_down"
  }
}
```

### entry_price / exit_price

```text
open
close
next_open
next_close
```

MVP 기본값은 `next_open`입니다.

### tax_rate

단일 float 또는 시계열 배열을 받습니다.

```text
단일 float: 전체 기간에 동일 세율
배열:       날짜별 세율 (정확성 정책 13.6.2절)
```

### use_adjusted_price

`true` (기본): 모든 가격 평가와 체결에 수정주가 사용 (정확성 정책 13.7절).

### tick_rounding

```text
buy_up_sell_down: 매수는 호가 단위 올림, 매도는 내림 (보수)
nearest:          반올림
```

---

## 12. metadata 구조

관리용 메타데이터입니다. `random_seed`는 결정론 보장을 위해 사용됩니다.

```json
{
  "metadata": {
    "created_by": "user",
    "created_at": "2026-05-09T10:00:00",
    "updated_at": "2026-05-09T11:00:00",
    "tags": ["거래량", "스윙", "돌파"],
    "favorite": true,
    "random_seed": 42
  }
}
```

---

## 13. trade_group 식별자

부분 매도가 핵심 기능이므로 schema에는 trade_group 개념이 직접 노출되지 않지만, **저장 시 백엔드가 매수마다 trade_group_id를 자동 생성**합니다 (07 DB 문서 참조).

전략 JSON 자체에는 trade_group 개념을 두지 않으며, 실행 시 자동 부여됩니다.

---

## 14. 전체 예시

```json
{
  "name": "거래량 돌파 스윙 전략",
  "version": "1.0",
  "description": "상승 추세와 거래량 급증을 이용한 단기 스윙 전략",

  "entry": {
    "logic": "AND",
    "conditions": [
      { "type": "price_vs_ma", "price_field": "adj_close", "ma_period": 20, "operator": ">" },
      { "type": "volume_ratio", "period": 20, "operator": ">=", "value": 2.0 },
      { "type": "rsi_level", "period": 14, "operator": "<=", "value": 70 }
    ]
  },

  "exit_signal": {
    "logic": "OR",
    "conditions": [
      { "type": "price_vs_ma", "price_field": "adj_close", "ma_period": 20, "operator": "<" }
    ]
  },

  "exit_position": {
    "logic": "OR",
    "conditions": [
      { "type": "take_profit", "percent": 7, "trigger": "intraday_high" },
      { "type": "stop_loss", "percent": 3, "trigger": "intraday_low" },
      { "type": "max_holding_days", "days": 10 }
    ]
  },

  "filters": {
    "logic": "AND",
    "conditions": [
      { "type": "avg_trading_value", "period": 20, "operator": ">=", "value": 5000000000 }
    ]
  },

  "priority": {
    "method": "trading_value_desc",
    "tie_breaker": "symbol_asc"
  },

  "position_sizing": {
    "method": "fixed_amount",
    "amount": 1000000,
    "max_positions": 10,
    "max_daily_entries": 3,
    "daily_buy_budget": 1000000,
    "allow_pyramiding": false
  },

  "cash_management": {
    "enabled": true,
    "shortage_rule": {
      "trigger": { "type": "cash_below_daily_buy_budget" },
      "action": { "type": "partial_sell", "sell_fraction": 0.25 },
      "target_selection": { "method": "lowest_return" },
      "repeat_until_cash_sufficient": true
    }
  },

  "risk_management": {
    "stop_trading_on_drawdown_pct": 20
  },

  "execution": {
    "entry_price": "next_open",
    "exit_price": "next_open",
    "fee_rate": 0.00015,
    "tax_rate": [
      { "from": "2020-01-01", "rate": 0.0023 },
      { "from": "2023-01-01", "rate": 0.0020 },
      { "from": "2024-01-01", "rate": 0.0018 },
      { "from": "2025-01-01", "rate": 0.0015 }
    ],
    "slippage": 0.001,
    "use_adjusted_price": true,
    "max_gap_pct_for_entry": 5.0,
    "allow_buy_limit_up": false,
    "tick_rounding": "buy_up_sell_down"
  },

  "metadata": {
    "tags": ["거래량", "스윙", "돌파"],
    "random_seed": 42
  }
}
```

---

## 15. Validation 규칙

저장 전 다음 검증을 수행합니다.

```text
[필수]
name 존재
entry.conditions 최소 1개
exit_signal 또는 exit_position 중 최소 하나 존재
모든 condition.type이 ConditionRegistry에 등록되어 있음
exit_signal에 requires_position=true 조건이 들어가지 않음
exit_position에 requires_position=false 조건이 들어가지 않음
각 condition 필수 파라미터 존재
operator 허용값 확인
percent, period, amount 값 범위 확인
position_sizing.amount > 0
position_sizing.max_positions >= 1

[자금 관리 일관성]
cash_management.enabled = true 시 shortage_rule 필수
position_sizing.daily_buy_budget이 cash_management의 trigger와 정합

[execution]
fee_rate, tax_rate, slippage 범위 0 이상
tax_rate가 배열이면 from 날짜가 오름차순
max_gap_pct_for_entry > 0

[priority]
method가 지원 목록에 포함

[경고 (저장 가능, 알림만)]
exit_position에 stop_loss 없음
filters에 거래대금 필터 없음
risk_management 미설정
random_seed 미설정 (random method 사용 시)
```

---

## 16. 스냅샷 저장 원칙

백테스트 실행 시 `strategy_snapshot_json`을 반드시 저장합니다.

```text
전략은 나중에 수정될 수 있다.
과거 백테스트 결과는 실행 당시 전략 조건을 기준으로 재현되어야 한다.
따라서 backtest_runs에 strategy_snapshot_json을 저장한다.

거래세 시계열, priority 알고리즘, tick_rounding 정책 등이 모두 포함되어야 결과가 재현된다.
```

---

## 17. schema 버전 관리

전략 JSON의 `version` 필드는 schema 자체의 버전이 아니라 사용자 전략의 버전입니다.

schema 버전은 `metadata.schema_version`으로 별도 관리합니다.

```json
{
  "metadata": {
    "schema_version": "2.0"
  }
}
```

schema 변경 시 마이그레이션 규칙은 별도 문서로 관리합니다.

---

## 18. 변경 이력 (이번 개정)

```text
exit를 exit_signal과 exit_position으로 분리
priority 섹션 신규 추가
position_sizing에 자금 관련 항목 통합
cash_management에서 daily_buy_budget 제거
risk_management에서 max_positions 제거
execution에 정확성 정책 관련 필드 추가 (max_gap_pct_for_entry, use_adjusted_price, tick_rounding)
tax_rate 시계열 지원
GROUP logic 1단계 도입
allow_pyramiding 추가
metadata.random_seed 추가
metadata.schema_version 추가
```
