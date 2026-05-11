---
date: 2026-05-11
agent: backend-api-engineer
phase: 17
status: completed
roadmap_step: "052"
roadmap_impact:
  - 09-h
  - 09-m
related_docs:
  - 상세설계/09_csv_export_design.md
  - 상세설계/10_api_design.md
---

# step 052 — trades.csv 컬럼 정합화 + ZIP 파일명 형식

## Plan

### 영향 체크박스 (완료 시 갱신 대상)
- `09-h`: trades.csv 컬럼 정합화 (entry_amount, exit_quantity, exit_amount, holding_days, signal_date)
- `09-m`: ZIP 파일명 형식 backtest_{strategy_name}_{run_id}.zip

### 배경 및 목적
- 09번 설계서 §5: trades.csv는 entry_amount / exit_quantity / exit_amount / holding_days / signal_date 컬럼 포함해야 함
- 현재 trades.csv에는 entry_amount, exit_quantity, exit_amount, holding_days, signal_date 중 일부가 누락된 상태
- 09번 설계서 §3: ZIP 파일명 형식 = `backtest_{strategy_name}_{run_id}.zip` 이어야 함 (현재 고정값이거나 run_id만 포함)
- Phase 17 목표: 09번 85% → 100%, 10번 83% → 92%

### 작업 범위

#### A. trades.csv 컬럼 정합화 (09-h)
- [ ] A1. 현재 export_trades_csv 구현 확인 — 어떤 컬럼이 빠져 있는지 파악
- [ ] A2. 09번 설계서 §5 컬럼 목록과 비교:
  - symbol, name, entry_date, entry_price, entry_quantity, **entry_amount** (누락 여부)
  - exit_date, exit_price, **exit_quantity** (누락 여부), **exit_amount** (누락 여부)
  - profit, profit_rate, **holding_days** (누락 여부), exit_reason
  - **signal_date** (누락 여부 — step 017에서 TradeExecution.signal_date 추가됨)
- [ ] A3. TradeGroup / TradeExecution DB 모델에서 필요한 데이터 확인
  - entry_amount = entry_price * entry_quantity (직접 계산 또는 컬럼 존재 여부)
  - exit_quantity = 매도 수량 (trade_executions 집계 필요)
  - exit_amount = exit_price * exit_quantity (직접 계산 또는 컬럼 존재 여부)
  - holding_days = fully_closed_at - entry_date (trade_group 단위)
  - signal_date = TradeExecution.signal_date (BUY 체결의 signal_date)
- [ ] A4. CsvExporter.export_trades_csv() 수정 — 누락 컬럼 추가
- [ ] A5. 단위 테스트: 컬럼 존재 여부 + 값 정확성 (entry_amount = price × qty 등)

#### B. ZIP 파일명 형식 변경 (09-m)
- [ ] B1. 현재 ZIP 파일명 확인 — 어떻게 생성되고 있는지 파악
- [ ] B2. 09번 설계서 §3: `backtest_{strategy_name}_{run_id}.zip` 형식으로 변경
  - strategy_name은 URL-safe하게 처리 (공백→_, 특수문자 제거)
  - run_id는 int 형식
- [ ] B3. FastAPI 라우트에서 Content-Disposition 헤더 갱신
- [ ] B4. 단위 테스트: 파일명 형식 검증 (특수문자 포함 전략명 처리 포함)

### 완료 기준
- `pytest backend/` — 전체 PASS (기존 1330건 이상 유지 + 신규 건 추가)
- trades.csv에 entry_amount / exit_quantity / exit_amount / holding_days / signal_date 컬럼 포함 확인
- ZIP 다운로드 응답의 Content-Disposition이 `attachment; filename="backtest_거래량돌파전략_100.zip"` 형식 확인

## Execution

### 적용 정책 절번호
- 09-h: trades.csv 컬럼 정합화
- 09-m: ZIP 파일명 형식 변경

### 수정 파일

#### `backend/app/services/csv_exporter.py` (주요 변경)
- `import re`, `from urllib.parse import quote` 추가
- `export_trades_csv()` 전면 재작성 (줄 93~166):
  - 컬럼 추가: `entry_amount`, `exit_quantity`, `exit_amount`, `holding_days`, `signal_date`
  - 컬럼 제거: `trade_group_id`, `remaining_quantity`, `realized_profit`, `realized_profit_pct`
  - 컬럼 이름 변경: `realized_profit` → `profit`, `realized_profit_pct` → `profit_rate`
  - BUY execution에서 `signal_date` 추출 (NULL이면 빈 문자열)
  - SELL/PARTIAL_SELL execution 집계: `exit_quantity` = 수량 합계, `exit_amount` = net_amount 합계
  - `holding_days` = `fully_closed_at.date() - entry_date` (미청산이면 빈 문자열)
- `sanitize_filename(name: str) -> str` 신규 추가 (줄 ~):
  - 공백→_, 특수문자 제거, 연속 _ 단일화, 앞뒤 _ 제거, 빈값 → "strategy"
- `make_zip_filename(strategy_name, run_id) -> str` 신규 추가:
  - `backtest_{sanitized_name}_{run_id}.zip` 형식 반환
- `make_content_disposition(filename: str) -> str` 신규 추가:
  - ASCII 안전 시 `attachment; filename="..."` 단순 형식
  - non-ASCII(한글 등) 포함 시 RFC 5987 형식 `filename*=UTF-8''<percent-encoded>` + ASCII 폴백 병행

#### `backend/app/api/routes_backtests.py` (ZIP 파일명 섹션)
- `kind == "zip"` 분기 (줄 ~643):
  - `run.strategy.name` 으로 strategy_name 획득
  - `csv_exporter.make_zip_filename(strategy_name, run.id)` 로 파일명 생성
  - `csv_exporter.make_content_disposition(filename)` 로 헤더 설정 (한글 RFC 5987 대응)

#### `backend/tests/exporters/test_csv_exporter.py` (테스트 추가)
- 헤더에 `TradeExecution`, `TradeExecutionType`, `export_trades_csv`, `make_zip_filename`, `sanitize_filename` import 추가
- `TestTradesCsvColumns` 클래스 추가 (10개 테스트):
  - `test_required_columns_exist`: 09번 §5 정의 컬럼 15개 전부 헤더에 존재
  - `test_entry_amount_equals_price_times_qty`: entry_amount = price × qty
  - `test_exit_quantity_sum_of_sell_executions`: exit_quantity = SELL 수량 합계
  - `test_exit_amount_sum_of_sell_net_amounts`: exit_amount = SELL net_amount 합계
  - `test_holding_days_fully_closed`: 완전 청산 시 일수 정확성
  - `test_holding_days_empty_for_open_position`: 미청산 시 빈 문자열
  - `test_signal_date_from_buy_execution`: signal_date 값 전달
  - `test_signal_date_empty_when_null`: signal_date NULL → 빈 문자열
  - `test_partial_sell_exit_quantity_aggregated`: 부분 매도 2회 집계
  - `test_no_legacy_columns`: 구 컬럼(trade_group_id 등) 제거 확인
- `TestSanitizeFilename` 클래스 추가 (12개 테스트):
  - 공백, 특수문자, 연속_언더스코어, 앞뒤제거, 빈값, 한글보존
  - `make_zip_filename` 형식, 특수문자, 공백, 빈값 케이스

#### `backend/tests/api/test_export.py` (테스트 추가)
- `test_export_trades_csv_required_columns`: 09번 §5 컬럼 헤더 확인 (API 레벨)
- `test_export_trades_csv_no_legacy_columns`: 구 컬럼 제거 확인 (API 레벨)
- `test_export_zip_filename_format`: Content-Disposition에 `backtest_`와 run_id 포함 확인
- `test_export_zip_filename_no_run_prefix`: 구 형식 `backtest_run_` 미포함 확인

## Tests

```
backend/.venv/Scripts/python.exe -m pytest backend/tests/exporters/test_csv_exporter.py -v
→ 39 passed (신규 22건 포함)

backend/.venv/Scripts/python.exe -m pytest backend/tests/api/test_export.py -v
→ 26 passed (신규 4건 포함)

backend/.venv/Scripts/python.exe -m pytest backend/ -q
→ 1356 passed (기존 1330 + 신규 26건)
```

### 테스트 항목 매핑

| 테스트 | 정책 | 커버 내용 |
|--------|------|-----------|
| `TestTradesCsvColumns::test_required_columns_exist` | 09-h | 15개 컬럼 전부 헤더 존재 |
| `TestTradesCsvColumns::test_entry_amount_equals_price_times_qty` | 09-h | entry_amount = price × qty |
| `TestTradesCsvColumns::test_exit_quantity_sum_of_sell_executions` | 09-h | exit_quantity 집계 |
| `TestTradesCsvColumns::test_exit_amount_sum_of_sell_net_amounts` | 09-h | exit_amount 집계 |
| `TestTradesCsvColumns::test_holding_days_fully_closed` | 09-h | 보유일 계산 |
| `TestTradesCsvColumns::test_holding_days_empty_for_open_position` | 09-h | 미청산 → 빈값 |
| `TestTradesCsvColumns::test_signal_date_from_buy_execution` | 09-h + 017 | signal_date 연동 |
| `TestTradesCsvColumns::test_partial_sell_exit_quantity_aggregated` | 09-h | 부분매도 집계 |
| `TestTradesCsvColumns::test_no_legacy_columns` | 09-h | 구 컬럼 제거 |
| `TestSanitizeFilename::*` (12건) | 09-m | 파일명 sanitize 로직 |
| `test_export_zip_filename_format` | 09-m | API 레벨 파일명 형식 |
| `test_export_zip_filename_no_run_prefix` | 09-m | 구 형식 미포함 |

## Issues

### 발견된 이슈: HTTP 헤더 한글 인코딩 문제
- 전략명에 한글이 포함되면 Content-Disposition 헤더 설정 시 `UnicodeEncodeError` 발생
- HTTP 헤더는 latin-1만 허용하므로 단순 `f'attachment; filename="{filename}"'` 방식 불가
- 해결: `make_content_disposition()` 헬퍼 추가하여 RFC 5987 percent-encoding 적용
  - ASCII 파일명: 단순 `filename="..."` 형식
  - non-ASCII 파일명: `filename="ascii_fallback"; filename*=UTF-8''<encoded>` 형식

### 구 컬럼 제거로 인한 호환성 변경 사항
- trades.csv에서 `trade_group_id`, `remaining_quantity`, `realized_profit_pct` 컬럼이 제거됨
- 기존 trades.csv를 파싱하던 외부 스크립트가 있으면 영향받을 수 있음
- 기존 API 테스트(`test_export_trades_csv`)는 컬럼 순서/이름을 가정하지 않아 영향 없음

### 설계서 09번 §5 컬럼 명칭 불일치
- 설계서 예시는 `profit_rate`이지만 `profit_rate`로 정합화 (기존 `realized_profit_pct` 대신)
- 09번 §5 명세(컬럼 목록)와 일치 확인 완료

## Result

### 신규/변경 함수 목록

| 파일 | 함수 | 변경 |
|------|------|------|
| `csv_exporter.py` | `export_trades_csv()` | 전면 재작성 — 09번 §5 컬럼 정합 |
| `csv_exporter.py` | `sanitize_filename()` | 신규 — URL-safe 변환 |
| `csv_exporter.py` | `make_zip_filename()` | 신규 — `backtest_{name}_{id}.zip` |
| `csv_exporter.py` | `make_content_disposition()` | 신규 — RFC 5987 헤더 |
| `routes_backtests.py` | `export()` (kind=zip) | 수정 — 신규 파일명/헤더 함수 사용 |

### trades.csv 최종 컬럼 순서 (09번 §5 준수)
```
symbol, name,
entry_date, entry_price, entry_quantity, entry_amount,
exit_date, exit_price, exit_quantity, exit_amount,
profit, profit_rate, holding_days, exit_reason, signal_date
```

### ZIP 파일명 형식
- 이전: `backtest_run_{run_id}.zip`
- 이후: `backtest_{strategy_name}_{run_id}.zip`
- 한글 전략명: RFC 5987 방식으로 Content-Disposition 헤더에 인코딩

## Follow-ups

- 현재 `export_trades_csv()`는 str 반환 (UTF-8 BOM 포함). 다른 export 함수(`export_symbol_performance_csv` 등)처럼 `encoding` 파라미터를 받아 bytes를 반환하는 형식으로 통일하는 리팩토링 고려 (현재는 기존 API 호환 유지)
- `make_content_disposition()`은 현재 ZIP 전용이나, 장기적으로 모든 파일 다운로드 응답(summary.csv 등)에 동일하게 적용하면 한글 파일명 일관성 확보 가능

## 메인 세션 마무리 체크

- [ ] status를 completed로 변경
- [ ] 작업로그/README.md "최근 작업" 표에 1행 추가
- [ ] Phase 상태가 변경되었으면 Phase 표 갱신
- [ ] Follow-ups 중 다음 작업 후보로 옮길 항목 정리
- [ ] **PM 에이전트 호출 → 로드맵.md 갱신** — "step 052 마무리" 지시. PM이 Phase 로드맵 step ✅ + 영향 체크박스 [x] + 진행률 표 손계산을 직접 Edit. (영향 체크박스 ID: 09-h, 09-m)
- [ ] `git commit` (단일 커밋)
- [ ] **Phase 17에 step이 하나 더 있음 (step 053)** — Phase 완료가 아님
