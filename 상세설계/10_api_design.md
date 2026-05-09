# 10. 백엔드 API 상세 설계서

## 1. 목적

API는 프론트엔드 GUI와 백엔드 엔진/DB를 연결하는 인터페이스입니다.

주요 기능은 다음입니다.

```text
전략 저장/조회/수정/삭제
조건 블록 목록 제공
백테스트 실행
백테스트 결과 조회
시장 데이터 조회
유니버스 미리보기
CSV Export
```

---

## 2. 전략 API

### GET /api/strategies

전략 목록 조회

응답:

```json
[
  {
    "id": 1,
    "name": "거래량 돌파 전략",
    "description": "거래량 급증 종목 매수",
    "tags": ["거래량", "돌파"],
    "favorite": true,
    "updated_at": "2026-05-09T10:00:00",
    "last_backtest": {
      "total_return": 84.2,
      "mdd": -18.5,
      "win_rate": 47.8
    }
  }
]
```

---

### POST /api/strategies

전략 생성

요청:

```json
{
  "name": "거래량 돌파 전략",
  "description": "거래량 급증 종목 매수",
  "strategy_json": {},
  "tags": ["거래량", "돌파"]
}
```

---

### GET /api/strategies/{strategy_id}

전략 상세 조회

---

### PUT /api/strategies/{strategy_id}

전략 수정

수정 시 `strategy_versions`에 이력을 남길 수 있습니다.

---

### DELETE /api/strategies/{strategy_id}

전략 삭제

MVP에서는 soft delete 권장.

---

### POST /api/strategies/{strategy_id}/duplicate

전략 복사

---

### GET /api/strategies/{strategy_id}/versions

전략 버전 목록 조회

---

## 3. 조건 블록 API

### GET /api/conditions

GUI에서 사용할 조건 블록 목록을 반환합니다.

응답:

```json
[
  {
    "type": "price_vs_ma",
    "category": "moving_average",
    "name": "가격과 이동평균 비교",
    "description": "종가가 N일 이동평균선보다 위/아래인지 판단합니다.",
    "parameters": [
      {
        "name": "ma_period",
        "label": "이동평균 기간",
        "input_type": "number",
        "default": 20
      }
    ]
  }
]
```

---

## 4. 백테스트 API

### POST /api/backtests

백테스트 실행 요청

요청:

```json
{
  "strategy_id": 1,
  "run_name": "코스닥 2020-2025 테스트",
  "universe_config": {
    "market": "KOSDAQ",
    "selection_method": "all"
  },
  "start_date": "2020-01-01",
  "end_date": "2025-12-31",
  "initial_cash": 10000000,
  "fee_rate": 0.00015,
  "tax_rate": 0.0018,
  "slippage": 0.001
}
```

응답:

```json
{
  "run_id": 100,
  "status": "pending"
}
```

MVP에서는 동기 실행도 가능하지만, 장기적으로는 비동기 작업 큐가 좋습니다.

---

### GET /api/backtests

백테스트 실행 목록 조회

---

### GET /api/backtests/{run_id}

백테스트 실행 상세 조회

---

### GET /api/backtests/{run_id}/summary

요약 결과 조회

응답:

```json
{
  "total_return": 84.2,
  "annual_return": 13.1,
  "final_equity": 18420000,
  "mdd": -18.5,
  "win_rate": 47.8,
  "trade_count": 312,
  "avg_holding_days": 8.4
}
```

---

### GET /api/backtests/{run_id}/trades

거래 내역 조회

쿼리 옵션:

```text
symbol
start_date
end_date
exit_reason
profit_only
loss_only
page
page_size
```

---

### GET /api/backtests/{run_id}/daily-equity

일별 자산 변화 조회

---

### GET /api/backtests/{run_id}/cash-events

예수금 이벤트 조회

---

### GET /api/backtests/{run_id}/chart-data

차트 데이터 조회

쿼리 옵션:

```text
symbol
start_date
end_date
```

응답:

```json
{
  "candles": [],
  "markers": [],
  "volume": [],
  "equity_curve": [],
  "cash_curve": []
}
```

---

## 5. 시장 데이터 API

### GET /api/market/symbols

종목 목록 조회

쿼리:

```text
market
keyword
exclude_etf
exclude_spac
exclude_preferred
```

---

### POST /api/market/universe/preview

백테스트 실행 전 대상 종목 미리보기

요청:

```json
{
  "market": "KOSPI",
  "selection_method": "market_cap_top_n",
  "top_n": 10,
  "selection_timing": "backtest_start_date",
  "date": "2020-01-02"
}
```

응답:

```json
{
  "count": 10,
  "symbols": [
    {
      "rank": 1,
      "symbol": "005930",
      "name": "삼성전자",
      "market_cap": 300000000000000
    }
  ]
}
```

---

### GET /api/market/prices/{symbol}

특정 종목 일봉 조회

---

### GET /api/market/market-cap/top

시가총액 상위 종목 조회

쿼리:

```text
market
date
top_n
```

---

## 6. Export API

```text
GET /api/backtests/{run_id}/export/summary
GET /api/backtests/{run_id}/export/trades
GET /api/backtests/{run_id}/export/daily-equity
GET /api/backtests/{run_id}/export/symbol-performance
GET /api/backtests/{run_id}/export/cash-events
GET /api/backtests/{run_id}/export/universe-history
GET /api/backtests/{run_id}/export/strategy-snapshot
GET /api/backtests/{run_id}/export/zip
```

응답은 파일 다운로드입니다.

---

## 7. 에러 응답 형식

```json
{
  "error": {
    "code": "INVALID_STRATEGY_JSON",
    "message": "전략 JSON이 올바르지 않습니다.",
    "details": [
      {
        "field": "entry.conditions",
        "message": "매수 조건이 필요합니다."
      }
    ]
  }
}
```

주요 에러 코드:

```text
INVALID_STRATEGY_JSON
UNKNOWN_CONDITION_TYPE
MARKET_DATA_NOT_FOUND
BACKTEST_RUN_NOT_FOUND
INSUFFICIENT_PRICE_DATA
EXPORT_FAILED
```

---

## 8. API 설계 원칙

```text
프론트엔드는 전략 조건을 하드코딩하지 않는다.
조건 목록은 GET /api/conditions에서 받는다.
백테스트 결과는 run_id 기준으로 조회한다.
전략 수정 후에도 과거 backtest run은 strategy_snapshot_json으로 유지한다.
대용량 결과는 페이지네이션을 지원한다.
CSV Export는 별도 API로 제공한다.
```
