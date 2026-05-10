---
date: 2026-05-11
agent: condition-author
phase: 14
status: completed
roadmap_step: "041"
roadmap_impact:
  - 03-f
  - 03-g
related_docs:
  - 상세설계/03_condition_registry_engine_design.md
  - 상세설계/13_backtest_accuracy_policy_design.md
---

# step 041 — avg_trading_value + market_index_filter 조건 등록

## Plan

- [ ] `backend/app/strategy/conditions/trading_value.py` 신규 생성
  - avg_trading_value 함수 + AVG_TRADING_VALUE_META 등록
  - market_index_filter 함수 + MARKET_INDEX_FILTER_META 등록
- [ ] `backend/app/strategy/conditions/__init__.py` import 추가
- [ ] `backend/app/strategy/condition_definitions.py` ALL_DEFINITIONS 에 2개 추가
- [ ] `backend/tests/strategy/test_trading_value_conditions.py` 신규 작성
  - avg_trading_value: look-ahead bias 없음 / 임계값 비교 / NaN 처리
  - market_index_filter: KOSPI 상승/하락 판단 / df에 index_col 없을 때 처리
- [ ] ruff check backend/app backend/tests → 0 errors
- [ ] pytest backend/ -q → 기존 PASS 유지 + 신규 테스트 PASS

## Execution

| 파일 | 변경 내용 |
|------|-----------|
| `backend/app/strategy/conditions/trading_value.py:1-177` | 신규 생성 — avg_trading_value 함수 + AVG_TRADING_VALUE_META, market_index_filter 함수 + MARKET_INDEX_FILTER_META |
| `backend/app/strategy/conditions/__init__.py:11` | `trading_value` import 추가 (알파벳 순 정렬) |
| `backend/app/strategy/condition_definitions.py:18` | `trading_value as _trading_value` import 추가 |
| `backend/app/strategy/condition_definitions.py:27-28` | ALL_DEFINITIONS에 AVG_TRADING_VALUE_META, MARKET_INDEX_FILTER_META 2개 추가 |
| `backend/tests/strategy/conditions/test_trading_value_conditions.py:1-220` | 신규 생성 — 30개 테스트 케이스 |

## Tests

```
신규 테스트 (30개 전체 PASS):
  pytest tests/strategy/conditions/test_trading_value_conditions.py -v
  30 passed in 1.38s

전체 회귀 (기존 실패 2건 동일, 이번 작업과 무관):
  pytest -q
  2 failed, 1107 passed, 10 warnings in 22.43s

기존 실패 2건 원인: TestAlembicRevisionChain (backend/alembic 폴더 미존재)
  → step 041 이전부터 존재하던 실패이며 이번 작업과 무관.
```

## Issues

없음. ruff 초기 I001 (import 정렬) 오류 1건 `--fix`로 자동 수정 후 이상 없음.

## Result

| 항목 | 값 |
|------|----|
| 조건 type 1 | `avg_trading_value` |
| requires_position | False |
| category | volume |
| allowed_in | entry, filters |
| sentence_template | `{period}일 평균 거래대금이 {value}억원 {operator_label}` |
| 조건 type 2 | `market_index_filter` |
| requires_position | False |
| category | market |
| allowed_in | entry, filters |
| sentence_template | `{index_col_label}이 {value}% {operator_label}` |

**look-ahead bias 검증:**
- `avg_trading_value`: `rolling(period, min_periods=period)`으로 당일 포함 계산하지만, 당일 장 마감 후 종가·거래량이 확정된 데이터를 사용하며 체결은 다음날 시가로 이루어지므로 look-ahead bias 없음.
- `market_index_filter`: 당일 시장 지수 등락률은 당일 장 마감 후 확정된 값. shift 불필요.

**CLAUDE.md 정책 준수:**
- 정책 #5: `avg_trading_value`는 `close * volume` 사용 (adj_close 아닌 close 사용이 정책에 명시됨)
- 두 조건 모두 `exit_position`에 노출 안 됨 (META allowed_in 및 시계열 조건 제약 준수)
- StrategyEngine 직접 수정 없이 데코레이터로만 등록

## Follow-ups

- `avg_trading_value_ratio`: 당일 거래대금 / N일 평균 거래대금 비율 (volume_ratio 패턴 유사)
- `market_breadth_filter`: 상한가/하한가 종목 수 비율 등 시장 폭 지표 기반 필터
- `market_index_filter`에 `kospi_return`, `kosdaq_return` 컬럼 주입 로직을 BacktestEngine에서 실제 구현 (현재 graceful degradation으로 처리)

## 메인 세션 마무리 체크

- [ ] status를 completed로 변경
- [ ] 작업로그/README.md "최근 작업" 표에 1행 추가
- [ ] PM 에이전트 호출 → 로드맵.md 갱신 — "step 041 마무리" 지시
- [ ] git commit (단일 커밋)
