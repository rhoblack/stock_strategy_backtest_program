---
date: 2026-05-10
agent: backend-api-engineer
phase: 13
status: completed
roadmap_step: "035"
roadmap_impact:
  - 09-i
  - 09-j
  - 09-k
  - 09-l
related_docs:
  - 상세설계/09_csv_export_design.md
  - 상세설계/10_api_design.md
  - 상세설계/07_database_design.md
---

# step 035 — symbol_performance.csv + universe_history.csv + /export/* 분리 라우팅 + encoding 옵션

## Plan

### 영향 체크박스 (완료 시 갱신 대상)
- `09-i`: symbol_performance.csv
- `09-j`: universe_history.csv (Phase 11 universe_history 모델 후)
- `09-k`: /export/symbol-performance / universe-history / strategy-snapshot 분리 라우팅
- `09-l`: encoding 옵션 (UTF-8 / UTF-8 BOM / CP949)

### 배경 및 목적
- 09번 설계서 §5~8: symbol_performance.csv(종목별 집계), universe_history.csv(유니버스 스냅샷), 분리 라우팅, encoding 옵션
- Phase 11 step 027에서 universe_history 모델 완성 → 이제 universe_history.csv 구현 가능
- 현재 /export/{kind} 단일 라우트로 7종 파일을 처리 → 분리 라우팅으로 명확화

### 작업 범위

#### A. symbol_performance.csv 구현
- [ ] A1. 집계 로직: trade_groups를 symbol 기준으로 집계 (trades_count, win_count, total_profit, win_rate, avg_holding_days 등)
- [ ] A2. CsvExporter.export_symbol_performance() 메서드 추가
- [ ] A3. 단위 테스트: 집계 정확성 + 정렬(total_profit DESC)

#### B. universe_history.csv 구현
- [ ] B1. universe_history 테이블 조회 → symbols_json 언패킹 → 행 전개 (date, symbol, symbol_name)
- [ ] B2. CsvExporter.export_universe_history() 메서드 추가
- [ ] B3. 단위 테스트: rows × symbols 전개 정확성

#### C. /export/* 분리 라우팅
- [ ] C1. 기존 /api/backtests/{id}/export/{kind} 라우트 유지 (하위 호환)
- [ ] C2. 신규 라우트 추가:
  - GET /api/backtests/{id}/export/symbol-performance
  - GET /api/backtests/{id}/export/universe-history
  - GET /api/backtests/{id}/export/strategy-snapshot
- [ ] C3. 09번 설계서 §6 라우팅 매핑 확인

#### D. encoding 옵션
- [ ] D1. ?encoding=utf-8 / utf-8-bom / cp949 query param 추가
- [ ] D2. CsvExporter 생성자 또는 export 메서드에 encoding 파라미터 전달
- [ ] D3. UTF-8 BOM이 기본값 (한글 Excel 호환)
- [ ] D4. 단위 테스트: 각 encoding 옵션으로 출력된 bytes 첫 3바이트 검증

### 완료 기준
- `pytest backend/` — 전체 PASS (기존 885건 이상 유지 + 신규 건 추가)
- symbol_performance.csv / universe_history.csv 파일 생성 확인
- /export/symbol-performance, /export/universe-history, /export/strategy-snapshot 라우트 동작 확인
- encoding=utf-8-bom 기본값 확인

## Execution

### 적용 정책 절번호
- 09번 §7 (symbol_performance.csv 컬럼/정렬)
- 09번 §9 (universe_history.csv 컬럼/전개)
- 09번 §11 (Export API 라우팅)
- 09번 §13 (한글 CSV 인코딩 옵션)
- 10번 §7.1 (표준 에러 envelope, INVALID_PARAMETER_VALUE)
- 10번 §9 (user_id 스코프 강제 — 기존 `_get_run_or_raise` 재사용)

### 수정/작성 파일

| 파일 | 변경 내용 | 라인 수 |
|------|-----------|---------|
| `backend/app/services/csv_exporter.py` | `export_symbol_performance_csv`, `export_universe_history_csv`, `_to_bytes` 추가, encoding 타입/맵 정의, `export_zip` 업데이트 | ~280 |
| `backend/app/api/routes_backtests.py` | `/export/symbol-performance`, `/export/universe-history`, `/export/strategy-snapshot` 분리 라우팅 추가, `encoding` query param + `_parse_encoding` 검증, `/{kind}` 하위 호환 유지 | ~500 |
| `backend/tests/api/test_export.py` | 신규 14건 추가 (기존 8건 ZIP 업데이트 포함) | ~220 |
| `backend/tests/exporters/test_csv_exporter.py` | 신규 17건 단위 테스트 | ~220 |

### 구현 세부사항

**A. symbol_performance.csv (09-i)**
- `export_symbol_performance_csv(session, run, encoding)` → bytes
- `remaining_quantity == 0` 조건으로 완전 청산된 TradeGroup만 집계
- `fully_closed_at.date() - entry_date` 로 holding_days 산출
- total_profit → `int()` 강제 (KRW 소수점 없음)
- `rows.sort(key=lambda r: r["total_profit"], reverse=True)` — DESC 정렬
- 컬럼: symbol, name, trade_count, win_rate, total_profit, avg_profit_rate, max_profit_rate, max_loss_rate, avg_holding_days

**B. universe_history.csv (09-j)**
- `export_universe_history_csv(session, run, encoding)` → bytes
- `run_id` 기준 `UniverseHistory` 조회 → `symbols_json: list[str]` 언패킹
- `(date, market, selection_method, rank, symbol, name, market_cap, trading_value)` 행 전개
- rank: `enumerate(symbols_json, start=1)` — symbols_json이 ASC 정렬이므로 순서 기반
- name/market_cap/trading_value는 모델에 없어서 빈 문자열 ("") 출력

**C. 분리 라우팅 (09-k)**
- FastAPI 라우터에서 고정 경로를 `/{kind}` 앞에 등록 → 우선 매칭
- `/export/symbol-performance` → `export_symbol_performance`
- `/export/universe-history` → `export_universe_history`
- `/export/strategy-snapshot` → `export_strategy_snapshot`
- 기존 `/export/strategy`(kind="strategy")도 strategy-snapshot과 동일 동작으로 하위 호환
- `export_zip`에 `symbol_performance.csv` + `universe_history.csv` 추가

**D. encoding 옵션 (09-l)**
- `_ENCODING_MAP = {"utf-8-bom": ("utf-8", b"\xef\xbb\xbf"), "utf-8": ("utf-8", b""), "cp949": ("cp949", b"")}`
- `_to_bytes(rows, fieldnames, encoding)` → `bom + body.encode(codec)`
- query param 기본값 `"utf-8-bom"` (Excel 한글 호환)
- `_parse_encoding()` 검증 → 미허용 값이면 `InvalidParameterValueError` → 400 + 표준 envelope

## Tests

```
pytest backend/tests/api/test_export.py   → 22 passed
pytest backend/tests/exporters/test_csv_exporter.py → 17 passed
pytest backend/tests/ (전체)              → 916 passed (기존 885 + 신규 31)
```

### 테스트 매핑

| 테스트 | 검증 항목 |
|--------|-----------|
| `TestSymbolPerformanceCsv::test_aggregation_basic` | trade_count/win_count/total_profit 집계 정확성 |
| `TestSymbolPerformanceCsv::test_aggregation_multi_symbol` | total_profit DESC 정렬 |
| `TestSymbolPerformanceCsv::test_total_profit_is_int_no_decimal` | KRW 정수 (소수점 없음) |
| `TestSymbolPerformanceCsv::test_open_positions_excluded` | 미청산 제외 |
| `TestSymbolPerformanceCsv::test_avg_holding_days` | 보유일 평균 계산 |
| `TestUniverseHistoryCsv::test_expand_single_date` | 1날짜 × 3종목 → 3행 전개 |
| `TestUniverseHistoryCsv::test_expand_multi_date` | 2날짜 × 2,3종목 → 5행 |
| `TestUniverseHistoryCsv::test_rank_increments` | rank 1부터 순서대로 |
| `TestUniverseHistoryCsv::test_only_own_run_data` | user_id/run_id 스코프 |
| `TestEncodingOption::test_utf8_bom_first_3bytes` | EF BB BF (BOM) 첫 3바이트 |
| `TestEncodingOption::test_utf8_no_bom_first_3bytes` | BOM 없는 UTF-8 |
| `TestEncodingOption::test_cp949_no_bom_first_3bytes` | CP949 인코딩 |
| `test_export_encoding_invalid` (API) | 잘못된 encoding → 400 envelope |
| `test_export_strategy_snapshot_route` | /export/strategy-snapshot 분리 라우팅 |

## Issues

1. **universe_history 모델의 name/market_cap/trading_value 부재**:
   - 설계서 §9는 `name`, `market_cap`, `trading_value` 컬럼을 출력에 포함하도록 명시하나,
     현재 `UniverseHistory` 모델의 `symbols_json`은 종목 코드(`list[str]`)만 저장.
   - 현재 구현: 해당 컬럼 빈 문자열("") 출력.
   - 해소 방법: `UniverseHistory.symbols_json`을 `list[dict]`(`{symbol, name, market_cap}`)
     형식으로 확장하거나, 별도 `symbol_meta_json` 컬럼 추가 필요.
   - 요청 대상: market-data-engineer (UniverseSelector 결과 확장)

2. **하위 호환 라우트와 분리 라우트의 encoding 동작 차이**:
   - `/{kind}` 라우트에서 `symbol-performance` / `universe-history`는 `encoding` 파라미터 전달됨.
   - `summary`, `trades`, `daily-equity`, `cash-events`는 `_to_csv()`(str 반환, BOM 고정)를
     내부적으로 사용하므로 encoding 파라미터가 무시됨.
   - 향후 이 4개 함수도 `_to_bytes()` 기반으로 전환 권장.

## Result

### 신규 라우트
| 라우트 | 메서드 | 응답 |
|--------|--------|------|
| `/api/backtests/{id}/export/symbol-performance` | GET | text/csv (encoding 파라미터) |
| `/api/backtests/{id}/export/universe-history` | GET | text/csv (encoding 파라미터) |
| `/api/backtests/{id}/export/strategy-snapshot` | GET | application/json |

### 신규 서비스 함수
| 함수 | 위치 |
|------|------|
| `export_symbol_performance_csv(session, run, encoding)` | `services/csv_exporter.py:93` |
| `export_universe_history_csv(session, run, encoding)` | `services/csv_exporter.py:152` |
| `_to_bytes(rows, fieldnames, encoding)` | `services/csv_exporter.py:43` |

### encoding 지원
- `utf-8-bom` (기본값): `b"\xef\xbb\xbf"` + UTF-8 본문
- `utf-8`: BOM 없는 UTF-8
- `cp949`: EUC-KR 인코딩

### ZIP 내 파일 변화
- 기존: 5파일 (summary, trades, daily_equity, cash_events, strategy_snapshot.json)
- 신규: 7파일 (+ symbol_performance.csv, + universe_history.csv)

### 영속화 스냅샷
- 이 step에서 새 영속화 컬럼 추가 없음 (export 레이어만 변경)

### scope 매트릭스
| 엔드포인트 | user_id Depends | service user_id 강제 |
|----------|-----------------|----------------------|
| `/export/symbol-performance` | ✅ | ✅ (`_get_run_or_raise`) |
| `/export/universe-history` | ✅ | ✅ (`_get_run_or_raise`) |
| `/export/strategy-snapshot` | ✅ | ✅ (`_get_run_or_raise`) |

## Follow-ups

1. **universe_history 모델 확장** (market-data-engineer 협업):
   - `symbols_json`을 `list[dict]` 형식으로 확장하거나 `symbol_meta_json` 추가
   - CSV 출력에 `name`, `market_cap`, `trading_value` 채우기

2. **기존 4개 CSV 함수 encoding 파라미터 지원 전환**:
   - `export_summary_csv`, `export_trades_csv`, `export_daily_equity_csv`,
     `export_cash_events_csv`를 `_to_bytes()` 기반으로 리팩터링
   - /{kind} 라우트에서 encoding 파라미터가 일관되게 적용되도록

3. **10번 문서 갱신 여부**:
   - `/export/symbol-performance`, `/export/universe-history`, `/export/strategy-snapshot`
     분리 라우팅이 09번 §11에 이미 명시되어 있음 → 10번 문서 추가 갱신 불필요
   - encoding query param은 09번 §13에 명시 → 양 문서 일관성 있음

## 메인 세션 마무리 체크

- [ ] status를 completed로 변경
- [ ] 작업로그/README.md "최근 작업" 표에 1행 추가
- [ ] Phase 상태가 변경되었으면 Phase 표 갱신
- [ ] Follow-ups 중 다음 작업 후보로 옮길 항목 정리
- [ ] **PM 에이전트 호출 → 로드맵.md 갱신** — "step 035 마무리" 지시. PM이 Phase 로드맵 step ✅ + 영향 체크박스 [x] + 진행률 표 손계산을 직접 Edit. (영향 체크박스 ID: 09-i, 09-j, 09-k, 09-l)
- [ ] `git commit` (단일 커밋)
- [ ] **Phase 마지막 step이 아님** (Phase 13은 034~039 총 6 step)
