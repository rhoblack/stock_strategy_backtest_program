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
  "price_field": "close",
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
  "exit": {},
  "filters": {},
  "position_sizing": {},
  "cash_management": {},
  "risk_management": {},
  "execution": {},
  "metadata": {}
}
```

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
        "price_field": "close",
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
```

MVP에서는 `AND`, `OR`만 지원합니다.

향후 고급 버전에서는 그룹 조건을 지원할 수 있습니다.

```json
{
  "logic": "GROUP",
  "expression": {
    "operator": "OR",
    "children": [
      {
        "operator": "AND",
        "conditions": ["cond_1", "cond_2"]
      },
      {
        "operator": "AND",
        "conditions": ["cond_3", "cond_4"]
      }
    ]
  }
}
```

---

## 5. exit 구조

매도 조건입니다.

```json
{
  "exit": {
    "logic": "OR",
    "conditions": [
      {
        "type": "take_profit",
        "percent": 7
      },
      {
        "type": "stop_loss",
        "percent": 3
      },
      {
        "type": "max_holding_days",
        "days": 10
      }
    ]
  }
}
```

매도 조건은 두 종류가 있습니다.

```text
지표 기반 매도:
이동평균선 이탈, MACD 데드크로스, RSI 과매수 등

포지션 기반 매도:
익절, 손절, 트레일링 스탑, 최대 보유일 등
```

포지션 기반 매도는 StrategyEngine보다 BacktestEngine/Portfolio 영역에서 처리하는 것이 좋습니다.

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

필터 조건은 매수 조건과 분리합니다.

```text
entry:
어떤 종목을 살 것인가?

filters:
어떤 환경에서만 살 것인가?
```

---

## 7. position_sizing 구조

얼마나 매수할지 결정합니다.

```json
{
  "position_sizing": {
    "method": "fixed_amount",
    "amount": 1000000,
    "max_positions": 10
  }
}
```

지원 방식 예시:

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

---

## 8. cash_management 구조

예수금 관리 규칙입니다.

```json
{
  "cash_management": {
    "enabled": true,
    "daily_buy_budget": 1000000,

    "cash_shortage_rule": {
      "trigger": {
        "type": "cash_below_daily_buy_budget"
      },
      "action": {
        "type": "partial_sell",
        "sell_fraction": 0.25,
        "sell_scope": "one_position"
      },
      "target_selection": {
        "method": "lowest_return"
      },
      "repeat_until_cash_sufficient": true
    }
  }
}
```

### target_selection method

```text
lowest_return
highest_return
largest_value
oldest_position
newest_position
equal_all_positions
```

MVP에서는 다음만 지원합니다.

```text
lowest_return
highest_return
largest_value
```

---

## 9. risk_management 구조

리스크 관리 설정입니다.

```json
{
  "risk_management": {
    "max_positions": 10,
    "max_daily_entries": 3,
    "max_position_ratio": 0.2,
    "stop_trading_on_drawdown": 20
  }
}
```

MVP에서는 `max_positions`, `max_daily_entries`를 우선 구현합니다.

---

## 10. execution 구조

체결 방식과 비용 설정입니다.

```json
{
  "execution": {
    "entry_price": "next_open",
    "exit_price": "next_open",
    "fee_rate": 0.00015,
    "tax_rate": 0.0018,
    "slippage": 0.001,
    "allow_buy_limit_up": false,
    "allow_sell_limit_down": false
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

---

## 11. metadata 구조

관리용 메타데이터입니다.

```json
{
  "metadata": {
    "created_by": "user",
    "created_at": "2026-05-09T10:00:00",
    "updated_at": "2026-05-09T11:00:00",
    "tags": ["거래량", "스윙", "돌파"],
    "favorite": true
  }
}
```

---

## 12. 전체 예시

```json
{
  "name": "거래량 돌파 스윙 전략",
  "version": "1.0",
  "description": "상승 추세와 거래량 급증을 이용한 단기 스윙 전략",

  "entry": {
    "logic": "AND",
    "conditions": [
      {
        "type": "price_vs_ma",
        "price_field": "close",
        "ma_period": 20,
        "operator": ">"
      },
      {
        "type": "volume_ratio",
        "period": 20,
        "operator": ">=",
        "value": 2.0
      },
      {
        "type": "rsi_level",
        "period": 14,
        "operator": "<=",
        "value": 70
      }
    ]
  },

  "exit": {
    "logic": "OR",
    "conditions": [
      {
        "type": "take_profit",
        "percent": 7
      },
      {
        "type": "stop_loss",
        "percent": 3
      },
      {
        "type": "max_holding_days",
        "days": 10
      }
    ]
  },

  "filters": {
    "logic": "AND",
    "conditions": [
      {
        "type": "avg_trading_value",
        "period": 20,
        "operator": ">=",
        "value": 5000000000
      }
    ]
  },

  "position_sizing": {
    "method": "fixed_amount",
    "amount": 1000000,
    "max_positions": 10
  },

  "cash_management": {
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
  },

  "execution": {
    "entry_price": "next_open",
    "exit_price": "next_open",
    "fee_rate": 0.00015,
    "tax_rate": 0.0018,
    "slippage": 0.001
  }
}
```

---

## 13. Validation 규칙

저장 전 다음 검증을 수행합니다.

```text
name 필수
entry.conditions 최소 1개
exit.conditions 최소 1개 권장
condition.type은 registry에 존재해야 함
각 condition 필수 파라미터 존재 여부 확인
operator 허용값 확인
percent, period, amount 값 범위 확인
cash_management enabled 시 shortage rule 필수
execution fee/tax/slippage 범위 확인
```

---

## 14. 스냅샷 저장 원칙

백테스트 실행 시 `strategy_snapshot_json`을 반드시 저장합니다.

```text
전략은 나중에 수정될 수 있다.
과거 백테스트 결과는 실행 당시 전략 조건을 기준으로 재현되어야 한다.
따라서 backtest_runs에 strategy_snapshot_json을 저장한다.
```
