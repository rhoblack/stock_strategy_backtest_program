---
date: 2026-05-10
agent: backend-api-engineer
phase: 12
status: completed
roadmap_step: 031
roadmap_impact:
  - 08-l  # chart-data를 DB daily_prices + trade_executions + daily_equity 기반으로 전환
  - 10-l  # chart-data API + query option
related_docs:
  - 상세설계/08_backtest_result_chart_design.md
  - 상세설계/10_api_design.md
  - 상세설계/06_market_data_universe_design.md
  - 작업로그/2026-05-10-018-local-csv-provider-and-price-loader.md
---

# Step 031 — chart-data → daily_prices 기반 전환 (08-l + 10-l)

리뷰 011 H2 + 외부 4.8 — 현재 routes_backtests.py:139-200 chart-data API가 매 호출마다 synthetic_seed/synthetic_n으로 candles를 재생성. seed 동일해도 라이브러리 버전 차이로 marker mismatch 위험. 본 step에서 daily_prices + trade_executions + daily_equity DB 조회로 전환.

## Plan

### A) chart-data API 재작성 (08-l, 10-l)
- [ ] `상세설계/08_backtest_result_chart_design.md` chart-data 절 정독
- [ ] `상세설계/10_api_design.md` chart-data API 절 정독
- [ ] `backend/app/api/routes_backtests.py:139-200` chart-data 핸들러 재작성:
  - 입력: backtest_run_id, optional symbol (복수 종목 시), optional date range
  - 처리:
    1. `BacktestRun` 조회 (user_id scope)
    2. `daily_prices` 조회 (run.start_date ~ run.end_date, symbol 또는 universe)
    3. `trade_executions` 조회 → marker 변환 (BUY/SELL)
    4. `daily_equity` 조회 → equity_curve
  - synthetic 재생성 fallback은 dev 모드에만 (필요 시), 운영은 daily_prices 필수
- [ ] 출력 형식 (08번 §2 정합):
  - `candles`: [{date, open, high, low, close, volume}] (또는 adj_*)
  - `markers`: [{date, type: BUY|SELL, price, quantity, reason}]
  - `equity_curve`: [{date, total_equity, daily_return, cumulative_return, drawdown}]

### B) Query option (10-l)
- [ ] `backend/app/schemas/backtest.py`에 ChartDataQuery 추가:
  - `symbol: str | None` (복수 종목 시 종목 선택)
  - `start_date / end_date: date | None` (range filter)
  - `use_adjusted: bool = True` (adj_* vs 원 가격)
  - `downsample: int | None` (1MB 초과 시 자동 다운샘플링)
- [ ] 1MB 초과 시 응답에 `downsampled: true` 포함

### C) 데이터 소스 우선순위
- 운영: daily_prices DB 조회 필수 (없으면 404 또는 helpful 메시지)
- dev 모드: synthetic_data fallback 가능 (BacktestRun.universe_config.synthetic_seed 보존)
- 정책 결정: dev/운영 분기는 환경 변수 또는 BacktestRun에 기록된 fallback 플래그

### D) 테스트
- [ ] `backend/tests/api/test_routes_backtests.py`에 chart-data 테스트 추가:
  - daily_prices 기반 정상 응답
  - symbol query 작동
  - date range filter
  - use_adjusted toggle
  - downsample 1MB 초과 케이스
  - user_id scope (다른 사용자 backtest_run 접근 차단)
  - 빈 daily_prices 시 처리

### E) 회귀
- [ ] 전체 pytest (Phase 1~11 회귀)
- [ ] ruff
- [ ] frontend chart 컴포넌트 호환성 (응답 형식 변경 없으면 무영향)

### 절대 금지
- BacktestEngine / Portfolio / StrategyEngine / ExecutionModel / CashManager 절대 수정
- conditions/* / market_data/* / models/* 수정 금지 (활용만)
- 16/18/19 산출물 시그니처 변경 금지
- 신규 에러 코드 추가 금지 (10.7.1 외)
- 결정론 깨기

### 다음 step (032) 인계 정보
- chart-data API 응답 형식 (032에서 BacktestResultPage 탭 + 차트가 활용)
- query option (032 종목 선택 드롭다운이 활용)

## Execution

### 작성/수정 파일

1. `backend/app/schemas/backtest.py:55-80` — `ChartDataQuery` 추가 (symbol / start_date / end_date / use_adjusted / downsample).
2. `backend/app/services/backtest_service.py:15-16` — `os` import 추가.
3. `backend/app/services/backtest_service.py:30` — `from app.market_data import repositories as market_repos` 추가.
4. `backend/app/services/backtest_service.py:447-678` — chart-data 헬퍼 3종 신설:
   - `is_dev_mode()` — `APP_ENV` 환경변수로 dev/prod 판별.
   - `_resolve_chart_range()` — 요청 구간을 BacktestRun 기간으로 클램프.
   - `_stride_downsample()` — 결정적 stride 다운샘플.
   - `build_chart_data_from_db()` — daily_prices + trade_executions + daily_equity 조회.
   - `build_chart_data_synthetic_fallback()` — 기존 합성 fallback (운영 모드 차단).
5. `backend/app/api/routes_backtests.py:15-32` — Query / MarketDataNotFoundError / ChartDataQuery import 추가.
6. `backend/app/api/routes_backtests.py:163-258` — `get_chart_data` 핸들러 재작성 (DB 우선 → dev fallback → 운영 404).
7. `backend/tests/api/test_chart_data.py` — 신규 테스트 14건.

### 적용한 정책 절번호

- 10번 §4 (`GET /api/backtests/{run_id}/chart-data`) — symbol / start_date / end_date / include_adjusted (→ `use_adjusted`) / downsampled.
- 10번 §7 (표준 envelope) — InvalidParameterValueError / MarketDataNotFoundError.
- 10번 §9 (user_id scope) — 기존 `_get_run_or_raise` 그대로 재사용.
- 08번 §6 / §7 / §8 — candles + markers + equity_curve 의미 보존.
- 13번 §7 (수정주가 정책) — `use_adjusted=True` 기본, False 시 원 가격 분기.
- 14번 §10 (결손 봉) — daily_prices에 row 없으면 candles에서도 빠짐.
- CLAUDE.md #8 (결정론) — daily_prices (date ASC), trade_executions (execution_date ASC, id ASC), downsample stride 결정적.

### 신규 에러 코드

추가 없음. 기존 `INVALID_PARAMETER_VALUE` (400) / `MARKET_DATA_NOT_FOUND` (404) / `BACKTEST_RUN_NOT_FOUND` (404) 재사용.

## Tests

### 명령

```text
.venv/Scripts/python.exe -m pytest tests/api/test_chart_data.py --tb=short
.venv/Scripts/python.exe -m pytest --tb=short -q  (전체 회귀)
.venv/Scripts/python.exe -m ruff check app/api/routes_backtests.py app/schemas/backtest.py \
    app/services/backtest_service.py tests/api/test_chart_data.py
```

### 결과

- chart_data 테스트: **14 passed** in 5.91s
- 전체 회귀: **839 passed** in 29.66s (baseline 825 + 14 신규)
- ruff (변경 파일): **All checks passed**
- ruff 전체: 11건 사전부터 존재하는 alembic 자동생성 파일 lint (본 step 무관)

### 매핑 (정책 절번호 → 테스트)

| 검증 항목 | 테스트 |
|---|---|
| dev fallback (daily_prices 비어있음) | `test_chart_data_dev_fallback_when_daily_prices_empty` |
| daily_prices 우선 | `test_chart_data_uses_daily_prices_when_present` |
| symbol 쿼리 override | `test_chart_data_symbol_query_overrides_universe` |
| start/end_date 클램프 (10.4) | `test_chart_data_date_range_filter` |
| use_adjusted toggle (13.7) | `test_chart_data_use_adjusted_toggle` |
| downsample 명시 / =1 강제 | `test_chart_data_downsample_explicit`, `test_chart_data_downsample_one_means_no_downsample` |
| 1MB 자동 다운샘플 (10.4 후단) | `test_chart_data_downsample_auto_for_large_series` |
| 잘못된 range → 400 envelope | `test_chart_data_invalid_date_range_returns_400` |
| 운영 + 데이터 없음 → 404 envelope | `test_chart_data_production_mode_404_when_no_daily_prices` |
| equity_curve 시퀀스 | `test_chart_data_equity_curve_present` |
| markers symbol 필터 | `test_chart_data_markers_filtered_by_symbol` |
| user_id scope | `test_chart_data_other_user_run_returns_404` (조건부), `test_chart_data_unknown_run_returns_404` |

## Issues

### 정책 모호성 / 결정 사항

1. **dev/prod 판별 기준**: 기존 코드에 환경 모드 플래그가 없어 `APP_ENV` 환경변수 신규 도입 (`development|dev|test|testing|''` → dev, `production|prod` → prod). 10번 문서에 명시되지 않은 사항 — Follow-ups에서 10번 또는 별도 운영 가이드에 정책화 필요.
2. **downsample 알고리즘**: 10번 §4는 "일주일 단위" 다운샘플을 명시하지만 본 step은 LTTB가 아닌 단순 stride (`df[::stride]`)로 결정. 캔들 데이터의 high/low가 누락되어 시각적 왜곡 가능. LTTB 도입은 후속 step에서 (외부 패키지 또는 직접 구현 필요).
3. **markers 종목 필터**: trade_executions에 symbol 컬럼이 없어 trade_group을 통해 필터. N+1 쿼리 가능성 — 거래 수가 많은 운영 시나리오에서 join 최적화 필요 (Follow-up).
4. **equity_curve symbol 필터**: equity_curve는 포트폴리오 전체이므로 symbol과 무관하게 항상 run 단위 daily_equity 시퀀스. multi-symbol 백테스트에서 종목별 equity 분리 요구 시 별도 모델 필요.
5. **use_adjusted=False fallback**: synthetic fallback은 adj_*만 생성하므로 `use_adjusted=False`를 무시하고 동일 값 사용. dev 환경 한정 한계 — 운영에서는 daily_prices가 항상 있으므로 문제 없음.

### 마이그레이션 위험

없음 — DB 스키마 변경 없음, 기존 응답 키 모두 보존.

## Result

### 신규/변경

- 신규 schema: `ChartDataQuery`
- 신규 service 헬퍼: `is_dev_mode`, `build_chart_data_from_db`, `build_chart_data_synthetic_fallback`, `_resolve_chart_range`, `_stride_downsample`
- 변경 라우트: `GET /api/backtests/{run_id}/chart-data` — DB 우선 + 5개 query 옵션 추가
- 신규 에러 코드: 없음 (`MARKET_DATA_NOT_FOUND` 기존)

### chart-data 응답 형식

```json
{
  "candles": [
    {"time": "2024-01-02", "open": 9950.0, "high": 10100.0, "low": 9900.0, "close": 10000.0, "volume": 10000.0}
  ],
  "markers": [
    {"time": "2024-01-15", "type": "BUY", "price": 10500.0, "quantity": 100, "exit_reason": null}
  ],
  "equity_curve": [
    {"time": "2024-01-02", "value": 10000000.0, "drawdown": 0.0}
  ],
  "symbol": "DBONLY",
  "source": "daily_prices",
  "resolution": "1d",
  "downsampled": false,
  "downsample_stride": 1,
  "date_range": {"start": "2024-01-02", "end": "2024-01-31"},
  "use_adjusted": true
}
```

기존 frontend `CandleBar / ChartMarker / EquityPoint` 타입의 필수 키 (`time/open/high/low/close`, `time/type/price/quantity/exit_reason`, `time/value/drawdown`)는 모두 보존. 신규 키는 TypeScript optional로 무시 가능.

### 데이터 소스 우선순위

| 조건 | 결과 |
|---|---|
| daily_prices에 (symbol, range) 데이터 있음 | `source: "daily_prices"` |
| daily_prices 비어있음 + dev 모드 | `source: "synthetic"` (fallback) |
| daily_prices 비어있음 + 운영 모드 | 404 `MARKET_DATA_NOT_FOUND` |

### scope 매트릭스

| 케이스 | 동작 |
|---|---|
| 본인 run + 데이터 정상 | 200 + payload |
| 본인 run + 잘못된 range | 400 INVALID_PARAMETER_VALUE |
| 다른 user run | 404 BACKTEST_RUN_NOT_FOUND |
| 미존재 run_id | 404 BACKTEST_RUN_NOT_FOUND |

## Follow-ups

### 다음 step (032) 인계 정보

- **chart-data 응답 형식**: 위 JSON 참고. frontend `BacktestResultPage`/탭 구성에서 `source` / `downsampled` 표시 가능.
- **query option**: `?symbol=&start_date=&end_date=&use_adjusted=&downsample=` — 종목 선택 드롭다운 / 기간 슬라이더 / 봉 단위 토글 / "원본 보기" 버튼에 매핑 가능.
- **frontend 변경 권고**:
  - `frontend/src/api/chartData.ts`의 `ChartDataOut`에 신규 키 (symbol/source/downsampled 등) 추가 (선택 사항 — 표시 안 하면 그대로 둬도 됨).
  - `useChartData(runId)` 훅에 `query: ChartDataQuery` 인자 추가 검토.

### 후속 작업 후보 (32 이후 단계)

1. **LTTB 다운샘플**: 현재 stride는 high/low 손실 가능 — Largest-Triangle-Three-Buckets 도입.
2. **markers join 최적화**: `selectinload(TradeExecution.trade_group)` 또는 `query.join(TradeGroup).filter(TradeGroup.symbol == sym)` 로 N+1 제거.
3. **multi-symbol equity_curve**: 종목별 평가금액 분해 — 별도 API or 별도 daily_equity_per_symbol 모델 필요 (013/014 영역).
4. **APP_ENV 정책화**: 10번 또는 별도 운영 가이드 문서에 dev/prod 동작 차이 명시. `is_dev_mode()` 단일 함수로 응집했으니 이후 다른 라우트에서도 재사용 가능.
5. **resolution=1w/1mo**: 10번 §4의 weekly/monthly 다운샘플 추가 (현재는 1d 고정).
6. **caching layer**: chart-data는 read-heavy → ETag/Last-Modified 또는 Redis 캐시 검토.

### 정책 문서 갱신 필요

- 10번 §4 chart-data 절: `volume`, `symbol`, `source`, `downsample_stride`, `date_range`, `use_adjusted` 응답 키 명세 추가 (본 step 구현이 10번 명세와 정합되도록 보강).
- 별도 운영 가이드 (또는 10번 부록): `APP_ENV` 환경변수와 dev/prod 분기 동작.

## 메인 세션 마무리 체크
- [ ] status를 completed로 변경
- [ ] 작업로그/README.md 갱신
- [ ] PM 호출 → 로드맵 갱신 (08-l, 10-l [x] / Phase 12 step 031 ✅)
- [ ] git commit
