---
date: 2026-05-11
agent: market-data-engineer
phase: 16
status: completed
roadmap_step: "050"
roadmap_impact:
  - 06-j
related_docs:
  - 상세설계/06_market_data_universe_design.md
  - 상세설계/14_data_pipeline_design.md
---

# step 050 — PykrxProvider (BaseProvider 인터페이스 구현 + LocalCsvProvider와 교체 가능)

## Plan

> 영향 체크박스 (완료 시 PM이 [x] 갱신):
> - `06-j`: PykrxProvider

- [ ] `backend/app/market_data/providers/pykrx_provider.py` — PykrxProvider 완전 구현
  - BaseProvider (또는 MarketDataProvider ABC) 인터페이스 준수
  - get_symbols(market) — pykrx.stock.get_market_ticker_list() 래핑
  - get_daily_prices(symbols, start_date, end_date) — pykrx.stock.get_market_ohlcv_by_date() 래핑
  - get_market_cap(date, market) — pykrx.stock.get_market_cap_by_ticker() 래핑
  - get_trading_value_rank(date, market) — 거래대금 기준 정렬
  - lazy import (pykrx는 선택 의존성) — ImportError 시 명확한 에러
  - DB ingest_into 메서드: PriceLoader/BacktestEngine 호환 DataFrame 반환
  - LocalCsvProvider와 동일 인터페이스 — BacktestEngine에서 교체 가능 (duck typing)

- [ ] `backend/tests/market_data/test_pykrx_provider.py` 신규 작성
  - pykrx 모킹 (monkeypatch 또는 unittest.mock.patch) — 실제 네트워크 호출 없이
  - get_symbols 반환 형식 검증 (DataFrame 컬럼: symbol, name, market, listing_date 등)
  - get_daily_prices 반환 형식 검증 (dict[str, DataFrame], adj_* 컬럼 포함 여부)
  - get_market_cap 반환 형식 검증
  - lazy import 실패 시 ImportError 또는 DataPipelineError 발생 검증
  - LocalCsvProvider와 인터페이스 호환성 검증 (동일 메서드 서명)

- [ ] ruff 검사 통과
- [ ] pytest 전체 회귀 (목표: 1265 PASS 유지 이상)

## Execution

```text
backend/app/market_data/pykrx_provider.py (신규, 약 340줄)
    - PykrxProvider(BaseProvider) 구현
    - ingest_into(session, *, symbols, start_date, end_date) → IngestResult
        PykrxCollector → repositories.upsert_symbol / bulk_upsert_daily_prices / upsert_trading_day
    - get_price_df(symbol, start, end, adjusted=True) → pd.DataFrame
        PYKRX_PROVIDER_COLUMNS 순서, date ASC, adj_* 포함
    - get_symbols(market="KOSPI") → list[str]  (symbol ASC, today 기준)
    - get_trading_calendar(start, end, market) → list[date]  (date ASC)
    - _ensure_pykrx_available(): lazy import — 미설치 시 PykrxImportError
    - PykrxImportError(RuntimeError): 명확한 에러 타입 공개
    - PYKRX_PROVIDER_COLUMNS: DataFrame 컬럼 명세 상수 (조건-author 계약용)
    - _empty_price_df(): 빈 결과 시 컬럼 명세 유지

backend/app/market_data/__init__.py (갱신)
    - 4단계 주석을 "050: PykrxProvider" 로 갱신, 사용 예 docstring 추가

backend/tests/market_data/test_pykrx_provider.py (신규, 14개 테스트)
```

인터페이스 결정 근거:
- 06번 §4 → get_price_df / get_symbols / get_trading_calendar 매핑
- 06번 §5 → BaseProvider 상속으로 Provider 교체 가능 (duck typing)
- 13.7 → adj_open/adj_high/adj_low/adj_close/adj_volume 필수
- 14.10 → 빈 결과 시 빈 DataFrame (forward-fill 없음)
- 14.9 → start/end 범위 엄수, get_symbols today 고정
- CLAUDE.md #8 → sort_values("date") + sorted() 명시

설계 결정 — providers/ 서브디렉토리 미생성:
  현재 market_data/ 최상위에 provider.py / local_csv.py 존재.
  providers/ 서브디렉토리 생성은 기존 import 경로 대규모 변경 → 회귀 위험.
  pykrx_provider.py를 같은 레벨에 추가해 일관성 유지.

## Tests

```text
pytest backend/tests/market_data/test_pykrx_provider.py -v
→ 14 passed (0.36s)

pytest backend/ -q
→ 1279 passed (기존 1265 + 신규 14), 0 failed, 10 warnings

ruff check backend/app backend/tests
→ All checks passed!
```

정책 검증 항목 매핑:
- test_get_price_df_returns_correct_columns      → 13.7 수정주가 (adj_* 컬럼 존재)
- test_get_price_df_adj_close_differs_from_close → 13.7 수정주가 (close != adj_close 독립성)
- test_get_price_df_empty_when_no_data           → 14.10 결손 정책 (forward-fill 금지)
- test_get_price_df_start_gt_end_raises          → 14.9 look-ahead 차단
- test_get_price_df_date_asc_order               → CLAUDE.md #8 결정론
- test_lazy_import_error_on_get_price_df         → lazy import / PykrxImportError
- test_lazy_import_error_on_get_symbols          → lazy import / PykrxImportError
- test_both_providers_inherit_base_provider      → 06번 §5 Provider 호환성
- test_both_providers_have_ingest_into           → BaseProvider 인터페이스 호환

## Issues

1. providers/ 서브디렉토리 부재: 지시서에서 providers/ 서브디렉토리를 언급했으나
   현재 코드베이스에는 해당 디렉토리가 없음. import 경로 일관성을 위해 최상위 레벨 유지.

2. lazy import 충돌: 초기 구현에서 get_symbols 내부 `import datetime`이
   테스트의 `builtins.__import__` mock과 충돌해 RecursionError 발생.
   해결: datetime.date.today() → 모듈 레벨 import인 date_type.today()로 교체.
   get_symbols에서 _ensure_pykrx_available()을 첫 줄에 명시적으로 호출.

3. ruff SIM117: 중첩 with → 병렬 with 로 통합 (테스트 파일 전체 적용).
   ruff --fix로 I001 (import 정렬) 자동 수정.

## Result

```text
적용 정책:
    - 06번 §4 (MarketDataProvider 인터페이스 메서드)
    - 06번 §5 (Provider 종류 — PykrxProvider)
    - 13.7 (수정주가: close + adj_close 둘 다 독립 컬럼)
    - 14.10 (결손 정책: forward-fill 금지)
    - 14.9 (look-ahead 차단: start/end 엄수, get_symbols today 고정)
    - CLAUDE.md #8 (결정론: symbol ASC, date ASC)

신규 파일:
    - backend/app/market_data/pykrx_provider.py
    - backend/tests/market_data/test_pykrx_provider.py

수정 파일:
    - backend/app/market_data/__init__.py

인터페이스 시그니처:
    from app.market_data.pykrx_provider import PykrxProvider, PYKRX_PROVIDER_COLUMNS

    df = PykrxProvider().get_price_df("005930", date(2024,1,2), date(2024,1,31))
    # df.columns == ("date","open","high","low","close","volume",
    #                "adj_open","adj_high","adj_low","adj_close","adj_volume","market_cap")

    symbols: list[str] = PykrxProvider().get_symbols(market="KOSPI")
    calendar: list[date] = PykrxProvider().get_trading_calendar(start, end)
    result: IngestResult = PykrxProvider().ingest_into(session, ...)
    session.commit()

pytest 결과: 1279 passed (신규 14 + 기존 1265 회귀 없음)
ruff: All checks passed!
```

## Follow-ups

```text
- providers/ 서브디렉토리 리팩토링: local_csv.py / pykrx_provider.py를
  market_data/providers/ 패키지로 이동 (import 경로 변경 동반 — 별도 step 권장)
- BacktestEngine 연동: 현재 BacktestEngine은 PriceLoader(session).load()를 사용.
  PykrxProvider.get_price_df()를 MarketDataContext로 추상화해 엔진에 주입하는 패턴이
  필요하면 backtest-engine-developer와 협의 후 별도 step 분리.
- network 마커 통합 테스트: pykrx 실제 호출 테스트는 @pytest.mark.network 마커로 분리
  (현재 미작성 — 운용 환경에서 별도 실행).
- 14번 문서 갱신 불필요: PykrxProvider는 14번 §4.1 / §6 구조 내에서 완전히 동작.
```

## 메인 세션 마무리 체크

- [ ] status를 completed로 변경
- [ ] 작업로그/README.md "최근 작업" 표에 1행 추가
- [ ] Phase 상태가 변경되었으면 Phase 표 갱신
- [ ] Follow-ups 중 다음 작업 후보로 옮길 항목 정리
- [ ] **PM 에이전트 호출 → 로드맵.md 갱신** — "step 050 마무리" 지시. PM이 Phase 로드맵 step ✅ + 06-j [x] + 진행률 표 손계산 직접 Edit
- [ ] `git commit` (단일 커밋)
- [ ] step 051이 Phase 16 마지막이면 `git push origin main` 실행
