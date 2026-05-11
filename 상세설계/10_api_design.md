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

### 4.1 비동기 처리 정책 (MVP 포함)

코스피 전체 5년 백테스트는 분~시간 단위가 걸립니다. 모든 백테스트 API는 비동기로 동작합니다.

```text
POST /api/backtests              → run_id 즉시 반환, 백그라운드에서 실행
GET  /api/backtests/{id}/status  → 진행률 조회 (폴링)
POST /api/backtests/{id}/cancel  → 취소 요청
```

MVP에서는 백그라운드 작업을 단순 thread/process로 처리하고, 향후 Celery / RQ / arq 등 작업 큐로 전환합니다.

### 4.2 POST /api/backtests

백테스트 실행 요청 (즉시 반환).

요청:

```json
{
  "strategy_id": 1,
  "run_name": "코스닥 2020-2025 테스트",
  "universe_config": {
    "market": "KOSDAQ",
    "selection_method": "all",
    "exclude_etf": true,
    "exclude_spac": true,
    "min_listing_age_days": 60
  },
  "start_date": "2020-01-01",
  "end_date": "2025-12-31",
  "initial_cash": 10000000,
  "fee_rate": 0.00015,
  "tax_rate": [
    { "from": "2020-01-01", "rate": 0.0023 },
    { "from": "2023-01-01", "rate": 0.0020 },
    { "from": "2024-01-01", "rate": 0.0018 },
    { "from": "2025-01-01", "rate": 0.0015 }
  ],
  "slippage": 0.001,
  "use_adjusted_price": true,
  "tick_rounding": "buy_up_sell_down",
  "max_gap_pct_for_entry": 5.0
}
```

응답 (즉시):

```json
{
  "run_id": 100,
  "status": "pending",
  "queued_at": "2026-05-09T10:00:00Z"
}
```

`tax_rate`는 단일 float 또는 시계열 배열 모두 허용 (정확성 정책 13.6).

### 4.3 GET /api/backtests/{run_id}/status

진행률 조회. 프론트엔드는 1~3초 간격으로 폴링합니다.

응답:

```json
{
  "run_id": 100,
  "status": "running",
  "progress_pct": 42.5,
  "current_date": "2022-08-14",
  "started_at": "2026-05-09T10:00:05Z",
  "elapsed_seconds": 87,
  "eta_seconds": 120
}
```

`status`:
```text
pending     큐에 대기 중
running     실행 중
completed   완료
failed      실패 (error_message 포함)
cancelled   사용자 취소
```

### 4.4 POST /api/backtests/{run_id}/cancel

실행 중인 백테스트 취소.

응답:

```json
{
  "run_id": 100,
  "status": "cancelling"
}
```

다음 날짜 루프 시작 전에 취소 신호를 확인하고 정리 후 status를 `cancelled`로 갱신합니다. 부분 결과는 폐기.

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

거래 내역 조회. trade_groups 단위로 집계된 매수-매도 페어를 반환합니다 (07 DB 9~10절).

쿼리 옵션:

```text
symbol
start_date
end_date
exit_reason
profit_only
loss_only
include_executions   (true 시 부분 매도 이력 포함)
page                 (기본 1)
page_size            (기본 100, 최대 500)
sort                 (entry_date_desc | profit_rate_desc | profit_desc 등)
```

응답:

```json
{
  "items": [
    {
      "trade_group_id": 5001,
      "symbol": "005930",
      "name": "삼성전자",
      "entry_date": "2024-03-12",
      "entry_price": 72000,
      "entry_quantity": 13,
      "fully_closed_at": "2024-04-05",
      "final_profit": 80600,
      "final_profit_rate": 8.61,
      "executions": [
        { "execution_date": "2024-04-05", "execution_type": "SELL", "quantity": 13, "exit_reason": "take_profit" }
      ]
    }
  ],
  "page": 1,
  "page_size": 100,
  "total_count": 312
}
```

---

### GET /api/backtests/{run_id}/daily-equity

일별 자산 변화 조회

---

### GET /api/backtests/{run_id}/cash-events

예수금 이벤트 조회

---

### GET /api/backtests/{run_id}/chart-data

차트 데이터 조회. 5년치 봉 + 마커 + 자산곡선 등은 데이터양이 크므로 다운샘플링과 페이지네이션을 지원합니다.

쿼리 옵션:

```text
symbol               (지정 시 종목별 차트, 미지정 시 포트폴리오 전체)
start_date
end_date
resolution           (1d | 1w | 1mo, 기본 1d)
fields               (candles,markers,volume,equity_curve,cash_curve 중 콤마 구분, 기본 모두)
include_adjusted     (true 시 수정주가, false 시 원 가격, 기본 true)
```

응답:

```json
{
  "candles": [...],
  "markers": [...],
  "volume": [...],
  "equity_curve": [...],
  "benchmark_curve": [...],
  "cash_curve": [...],
  "resolution": "1d",
  "downsampled": false
}
```

응답 크기가 1MB를 초과하면 자동으로 일주일 단위로 다운샘플링하고 `downsampled: true`로 표시합니다.

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

## 5-s. 종목 검색 API (10-s, 06-k)

### GET /api/symbols

종목 검색 (기존 `/api/symbols/search` 와 별도로 쿼리 파라미터 방식 제공)

쿼리:

```text
q        — 종목코드 또는 종목명 (LIKE 검색, 선택)
market   — KOSPI | KOSDAQ | KONEX | ALL (기본 ALL)
limit    — 기본 20, 최대 100
```

응답:

```json
[
  {"symbol": "005930", "name": "삼성전자", "market": "KOSPI", "sector": "반도체"}
]
```

user_id 스코프 불필요 (공개 읽기 전용).

---

## 5-t. 관심종목 API (10-t, 07-q)

### POST /api/watchlists

관심종목 그룹 생성. user_id scope 필수.

요청:
```json
{"name": "기술주 관심종목", "description": ""}
```

응답: WatchlistOut (id, user_id, name, description, created_at, item_count)

---

### GET /api/watchlists

내 관심종목 그룹 목록. user_id scope 필수.

응답: list[WatchlistOut]

---

### GET /api/watchlists/{id}

그룹 상세 + 종목 목록. user_id scope 필수. 다른 user 소유 시 404.

응답: WatchlistDetailOut (id, name, description, created_at, items: list[WatchlistItemOut])

---

### POST /api/watchlists/{id}/symbols

종목 추가. user_id scope 필수.

요청:
```json
{"symbol": "005930"}
```

응답: WatchlistItemOut (id, watchlist_id, symbol, added_at)

중복 추가 시 409 WATCHLIST_ITEM_ALREADY_EXISTS.

---

### DELETE /api/watchlists/{id}/symbols/{symbol}

종목 제거. user_id scope 필수. 응답: 204 No Content.

---

### DELETE /api/watchlists/{id}

그룹 삭제 (cascade로 items도 삭제). user_id scope 필수. 응답: 204 No Content.

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

### 7.1 에러 코드 목록

전략 / 검증 관련:
```text
INVALID_STRATEGY_JSON
UNKNOWN_CONDITION_TYPE
EXIT_POSITION_IN_EXIT_SIGNAL       (포지션 조건이 exit_signal에 들어감)
EXIT_SIGNAL_IN_EXIT_POSITION       (시계열 조건이 exit_position에 들어감)
INVALID_OPERATOR
INVALID_PARAMETER_VALUE
MISSING_REQUIRED_PARAMETER
STRATEGY_NOT_FOUND
DUPLICATE_STRATEGY_NAME
```

백테스트 관련:
```text
BACKTEST_RUN_NOT_FOUND
BACKTEST_ALREADY_RUNNING
BACKTEST_NOT_RUNNING               (취소 불가)
BACKTEST_TIMEOUT
INVALID_DATE_RANGE
INSUFFICIENT_PRICE_DATA
TRADING_CALENDAR_MISSING
```

데이터 관련:
```text
MARKET_DATA_NOT_FOUND
SYMBOL_NOT_FOUND
UNIVERSE_EMPTY
UNIVERSE_PREVIEW_FAILED
```

관심종목 관련:
```text
WATCHLIST_NOT_FOUND              (404 — 해당 id의 watchlist가 없거나 다른 user 소유)
WATCHLIST_ITEM_ALREADY_EXISTS    (409 — 동일 그룹에 이미 추가된 종목)
```

권한 / 인증:
```text
UNAUTHORIZED
FORBIDDEN
RATE_LIMIT_EXCEEDED
```

Export:
```text
EXPORT_FAILED
EXPORT_TOO_LARGE
```

### 7.2 HTTP 상태 코드 매핑

```text
400  검증 실패 (INVALID_*, MISSING_*)
401  UNAUTHORIZED
403  FORBIDDEN
404  *_NOT_FOUND
409  BACKTEST_ALREADY_RUNNING, DUPLICATE_*
422  도메인 검증 실패 (EXIT_POSITION_IN_EXIT_SIGNAL 등)
429  RATE_LIMIT_EXCEEDED
500  내부 오류
```

---

## 8. API 설계 원칙

```text
프론트엔드는 전략 조건을 하드코딩하지 않는다.
조건 목록은 GET /api/conditions에서 받는다.
백테스트 결과는 run_id 기준으로 조회한다.
전략 수정 후에도 과거 backtest run은 strategy_snapshot_json으로 유지한다.
백테스트 실행은 항상 비동기. 진행률은 status API로 폴링.
대용량 결과는 페이지네이션 (page/page_size) 또는 cursor 지원.
차트 데이터는 1MB 초과 시 자동 다운샘플링.
CSV Export는 별도 API로 제공.
모든 응답에 X-Request-ID 헤더 포함.
모든 timestamp는 ISO 8601 UTC.
```

---

## 9. 인증 / 권한 (MVP 정책)

```text
MVP: API key 또는 세션 쿠키, 단일 시스템 유저 전제 가능
v2:  사용자 가입/로그인, 본인 strategy/backtest_run만 조회 가능
```

모든 list/get 엔드포인트는 user_id 스코프로 자동 필터.

---

## 10. 페이지네이션 표준

```text
요청:
  ?page=1&page_size=100  (기본 100, 최대 500)

응답:
  {
    "items": [...],
    "page": 1,
    "page_size": 100,
    "total_count": 312,
    "has_next": true
  }
```

대용량 daily_equity / trade_executions에는 cursor 기반도 지원합니다.

```text
?cursor=eyJk...&limit=200
```
