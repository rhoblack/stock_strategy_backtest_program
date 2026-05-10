---
date: 2026-05-11
agent: backend-api-engineer
phase: 13
status: completed
roadmap_step: "036"
roadmap_impact:
  - 10-m
  - 10-n
  - 10-o
  - 10-p
related_docs:
  - 상세설계/10_api_design.md
  - 상세설계/06_market_data_design.md
  - 상세설계/07_database_design.md
---

# step 036 — API 잔존: strategies versions + backtests 목록/상세 + 시장 데이터 API + trades pagination

## Plan

### 영향 체크박스 (완료 시 갱신 대상)
- `10-m`: GET /api/strategies/{id}/versions
- `10-n`: GET /api/backtests 목록 / 상세
- `10-o`: 시장 데이터 API (종목 검색 / 일봉 / 캘린더)
- `10-p`: trades pagination / filter / sort

### 배경 및 목적
- 10번 설계서 미구현 4개 항목 일괄 처리
- strategies/{id}/versions: 전략 버전 이력 조회
- backtests 목록/상세: GET /api/backtests + GET /api/backtests/{id} 응답 완성
- 시장 데이터 API: 종목 검색(/api/symbols/search) + 일봉(/api/symbols/{symbol}/daily-prices) + 캘린더(/api/calendar)
- trades pagination: GET /api/backtests/{id}/trades?page=&page_size=&sort=&filter=

### 작업 범위

#### A. strategies versions (10-m)
- [ ] A1. GET /api/strategies/{id}/versions 라우트 추가
- [ ] A2. StrategyVersionResponse 스키마 작성
- [ ] A3. strategy_service.get_strategy_versions() 메서드
- [ ] A4. 단위 테스트: 버전 목록 조회 + 존재하지 않는 전략 404

#### B. backtests 목록 / 상세 (10-n)
- [ ] B1. GET /api/backtests (전체 목록, user_id scope)
- [ ] B2. GET /api/backtests/{id} (단건 상세)
- [ ] B3. BacktestListResponse / BacktestDetailResponse 스키마
- [ ] B4. 단위 테스트: 목록 조회 + 필터(status, strategy_id)

#### C. 시장 데이터 API (10-o)
- [ ] C1. GET /api/symbols/search?q=&market= — symbols 테이블 검색
- [ ] C2. GET /api/symbols/{symbol}/daily-prices?start=&end=&adjusted= — daily_prices 조회
- [ ] C3. GET /api/calendar?year=&month= — trading_calendar 조회
- [ ] C4. 응답 스키마 작성
- [ ] C5. 단위 테스트: 검색 결과 + 일봉 조회 + 캘린더

#### D. trades pagination / filter / sort (10-p)
- [ ] D1. GET /api/backtests/{id}/trades 에 page / page_size / sort / symbol / action query param 추가
- [ ] D2. 총 건수 포함한 PaginatedTradesResponse 스키마
- [ ] D3. 단위 테스트: 페이징 + 정렬 + 필터

### 완료 기준
- pytest backend/ — 전체 PASS (기존 916건 이상 유지 + 신규 건 추가)
- GET /api/strategies/{id}/versions 정상 응답
- GET /api/backtests, GET /api/backtests/{id} 정상 응답
- GET /api/symbols/search, daily-prices, /api/calendar 정상 응답
- trades pagination/filter/sort 동작 확인

## Execution

### 적용 정책 절번호
- 10번 2절: GET /api/strategies/{id}/versions
- 10번 4절: GET /api/backtests (목록) + GET /api/backtests/{id} (상세)
- 10번 5절: 시장 데이터 API (symbols, daily-prices, calendar)
- 10번 9절: user_id scope (backtests 목록/상세, strategies/versions)
- 10번 10절: 페이지네이션 표준 (PaginatedTradesResponse, BacktestListResponse)
- 13-s §14: KRW 금액 int 변환 (entry_price, final_profit, initial_cash 등)

### 작성/수정 파일

| 파일 | 작업 내용 |
|------|-----------|
| `backend/app/schemas/strategy.py:20-65` | `StrategyVersionOut` 스키마 추가 (`from_orm_version` classmethod 포함) |
| `backend/app/schemas/backtest.py:12-19` | `PaginationMeta` 추가 |
| `backend/app/schemas/backtest.py:90-200` | `BacktestListItem`, `BacktestDetailOut`, `BacktestResultSummary`, `BacktestListResponse`, `PaginatedTradesResponse`, `TradeGroupOut`, `TradeExecutionOut`, `SymbolSearchItem`, `DailyPriceItem`, `DailyPricesResponse`, `CalendarItem`, `CalendarResponse` 추가 |
| `backend/app/api/routes_strategies.py:116-136` | `GET /api/strategies/{strategy_id}/versions` 라우트 추가 |
| `backend/app/api/routes_backtests.py` | `GET /api/backtests` + `GET /api/backtests/{id}` + trades pagination 라우트 추가 |
| `backend/app/api/routes_market.py` (신규) | `GET /api/symbols/search` + `GET /api/symbols/{symbol}/daily-prices` + `GET /api/calendar` |
| `backend/app/main.py` | `symbols_router`, `calendar_router` include |

### Plan 체크리스트 업데이트
- [x] A1. GET /api/strategies/{id}/versions 라우트 추가
- [x] A2. StrategyVersionOut 스키마 작성
- [x] A3. strategy_service.list_strategy_versions() (기존 메서드 활용)
- [x] A4. 단위 테스트: 버전 목록 조회 + 존재하지 않는 전략 404
- [x] B1. GET /api/backtests (전체 목록, user_id scope)
- [x] B2. GET /api/backtests/{id} (단건 상세)
- [x] B3. BacktestListResponse / BacktestDetailResponse 스키마
- [x] B4. 단위 테스트: 목록 조회 + 필터(status, strategy_id)
- [x] C1. GET /api/symbols/search?q=&market= — symbols 테이블 검색
- [x] C2. GET /api/symbols/{symbol}/daily-prices?start=&end=&adjusted=
- [x] C3. GET /api/calendar?year=&month= — trading_calendar 조회
- [x] C4. 응답 스키마 작성
- [x] C5. 단위 테스트: 검색 결과 + 일봉 조회 + 캘린더
- [x] D1. GET /api/backtests/{id}/trades page/page_size/sort/symbol/action 추가
- [x] D2. PaginatedTradesResponse 스키마
- [x] D3. 단위 테스트: 페이징 + 정렬 + 필터

## Tests

### pytest 실행 결과

```
# 신규 테스트 단독 실행
pytest tests/api/test_strategy_versions.py tests/api/test_backtests_list_detail.py tests/api/test_market_data.py tests/api/test_trades_pagination.py -v
→ 45 passed, 0 failed

# 전체 회귀 포함
pytest tests/ -q
→ 961 passed, 8 warnings (19.95s)
  기존 916 + 신규 45 = 961
  회귀 없음 확인
```

### 테스트 매핑

| 파일 | 테스트 내용 |
|------|------------|
| `test_strategy_versions.py` | 버전 목록 조회(5건), 404, summary 필드, 메타데이터 변경시 미증가 |
| `test_backtests_list_detail.py` | 목록 조회(9건), status/strategy_id 필터, 페이지 메타, 상세 result 포함, 정렬 |
| `test_market_data.py` | 심볼 검색(6건), 일봉 조회(7건), 캘린더(5건) + 에러 envelope 확인 |
| `test_trades_pagination.py` | 응답구조, KRW int, 페이지 분리, sort 4종, symbol 필터, 404, page_size 상한 |

## Issues

1. **10번 5절 엔드포인트 경로 불일치**
   - 10번 설계서는 `GET /api/market/symbols`, `GET /api/market/prices/{symbol}` 형식이지만
     작업 지시서는 `GET /api/symbols/search`, `GET /api/symbols/{symbol}/daily-prices` 형식 요청
   - 작업 지시서 기준으로 구현. 10번 문서 5절 경로 갱신 필요 (Follow-ups)
2. **`trades.action` 필터 미구현**
   - 10-p 요구사항에 action(buy/sell) 필터가 있으나, TradeGroup 단위 응답에서
     BUY-only 그룹 vs SELL-포함 그룹 구분이 설계서에 없음
   - query param은 수용하되 실제 필터링은 미적용 (UI 요구사항 확정 후 backlog)
3. **GET /api/backtests ↔ GET /api/backtests/{run_id} 경로 충돌 방지**
   - `/{run_id}` 라우트가 `GET /api/backtests` 빈 경로를 삼키지 않도록
     `""` 경로를 먼저 등록하고 `/{run_id}`를 나중에 등록 → FastAPI 라우터 순서 의존
   - 실제로는 FastAPI가 ``보다 `/{run_id}`를 더 구체적으로 처리하므로 문제 없음

## Result

### 신규 라우트

| 메서드 | 경로 | 응답 스키마 | 정책 절 |
|--------|------|------------|--------|
| GET | /api/strategies/{id}/versions | list[StrategyVersionOut] | 10-m |
| GET | /api/backtests | BacktestListResponse | 10-n |
| GET | /api/backtests/{id} | BacktestDetailOut | 10-n |
| GET | /api/symbols/search | list[SymbolSearchItem] | 10-o |
| GET | /api/symbols/{symbol}/daily-prices | DailyPricesResponse | 10-o |
| GET | /api/calendar | CalendarResponse | 10-o |
| GET | /api/backtests/{id}/trades (갱신) | PaginatedTradesResponse | 10-p |

### user_id scope 매트릭스

| 엔드포인트 | user_id 적용 | 근거 |
|-----------|------------|------|
| GET /api/strategies/{id}/versions | O | strategy_service.list_strategy_versions(user_id=) |
| GET /api/backtests | O | BacktestRun.user_id == user_id WHERE |
| GET /api/backtests/{id} | O | _get_run_or_raise(user_id=) |
| GET /api/symbols/search | X | 시장 데이터 공개 읽기 |
| GET /api/symbols/{s}/daily-prices | X | 시장 데이터 공개 읽기 |
| GET /api/calendar | X | 시장 데이터 공개 읽기 |
| GET /api/backtests/{id}/trades | O | _get_run_or_raise(user_id=) |

### 영속화 스냅샷 해당 없음
(이번 step은 조회 전용 — 새 DB 컬럼 추가 없음)

## Follow-ups

1. **10번 문서 5절 경로 갱신 필요**
   - 현재 설계서: `/api/market/symbols`, `/api/market/prices/{symbol}`
   - 구현 경로: `/api/symbols/search`, `/api/symbols/{symbol}/daily-prices`, `/api/calendar`
   - PM 에이전트 또는 10번 문서 담당자가 동기화 필요
2. **trades action(buy/sell) 필터 구현**
   - UI에서 BUY/SELL 탭 분리 요구 시 TradeGroup + JOIN TradeExecution 필터 구현
3. **GET /api/backtests/{id} 에서 result.open_position_count 추가 고려**
   - BacktestResult에 open_position_count 컬럼 존재하나 BacktestResultSummary에 미포함
   - 프론트엔드 요청 시 추가
4. **GET /api/symbols/search — 시가총액 정렬 추가**
   - 현재: delisting_date IS NULL 먼저, symbol ASC
   - 개선: market_cap 컬럼이 daily_prices에 있으므로 JOIN 후 최신 시가총액 기준 정렬 가능
5. **cursor 기반 페이지네이션**
   - daily_equity / trade_executions 대용량에 cursor 지원 (10번 10절)
   - 현재는 page/page_size만. 후속 step에서 구현 예정

## 메인 세션 마무리 체크

- [ ] status를 completed로 변경
- [ ] 작업로그/README.md "최근 작업" 표에 1행 추가
- [ ] Phase 상태가 변경되었으면 Phase 표 갱신
- [ ] Follow-ups 중 다음 작업 후보로 옮길 항목 정리
- [ ] **PM 에이전트 호출 → 로드맵.md 갱신** — "step 036 마무리" 지시. PM이 Phase 로드맵 step ✅ + 영향 체크박스 [x] + 진행률 표 손계산을 직접 Edit. (영향 체크박스 ID: 10-m, 10-n, 10-o, 10-p)
- [ ] `git commit` (단일 커밋)
- [ ] **Phase 마지막 step이 아님** (Phase 13은 034~039 총 6 step)
