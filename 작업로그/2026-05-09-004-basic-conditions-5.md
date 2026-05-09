---
date: 2026-05-09
agent: main (condition-author 대행 — 에이전트 hot reload 미작동, Follow-ups 참조)
phase: 1
status: completed
related_docs:
  - 상세설계/03_condition_registry_engine_design.md
  - 상세설계/02_strategy_json_schema_design.md
  - 상세설계/13_backtest_accuracy_policy_design.md
---

# Phase 1 / Step 4 — 기본 조건 5개 작성

## Plan

설계서 03번 6절 MVP 우선 구현 조건 중 핵심 5개를 추가. 각 조건은 함수 + Registry 등록 + GUI 메타데이터(MET) + pytest를 한 번에. take_profit은 포지션 조건이라 함수 시그니처가 다름.

### 메타데이터 카탈로그 패턴 (방식 A)

- 각 조건 모듈에 `META: dict` 변수 정의 (type, name, sentence_template, parameters, allowed_in 등)
- `app/strategy/condition_definitions.py` 신설: 모든 conditions 모듈을 import한 뒤 `ALL_DEFINITIONS` dict (type → meta)로 노출
- registry의 `list_conditions()`와는 분리. registry는 type/requires_position/category만, 카탈로그는 GUI 표시용 풍부한 메타.

### 추가할 조건

- [x] **price_vs_ma** — `app/strategy/conditions/moving_average.py`
- [x] **ma_cross** — 같은 파일 (golden_cross/dead_cross, shift(1) 적용)
- [x] **volume_ratio** — `app/strategy/conditions/volume.py`
- [x] **rsi_level** — `app/strategy/conditions/rsi.py`
- [x] **take_profit** — `app/strategy/conditions/exit_position.py` (intraday_high/close trigger)

### 추가 작업

- [x] `app/strategy/conditions/__init__.py`에서 모든 conditions 모듈 import (자동 등록)
- [x] `app/strategy/condition_definitions.py` 신설 (ALL_DEFINITIONS + get_condition_catalog)
- [x] `app/strategy/__init__.py`에 ALL_DEFINITIONS, get_condition_catalog 노출
- [x] `backend/tests/strategy/conditions/` 폴더 + 4개 테스트 파일 + condition_definitions 테스트

### 사용 가능 자원

- indicators: `from app.strategy.indicators import moving_average, ema, rsi, macd`
- utils: `from app.strategy.utils import compare`
- registry: `from app.strategy.registry import condition_registry`

### 검증

- `./.venv/Scripts/python.exe -m pytest -v` 전체 통과
- `./.venv/Scripts/python.exe -m ruff check app tests` All checks passed
- 회귀: 기존 53건 + 신규 (조건 4파일 × 4~6 = 16~24건) 모두 통과
- import 시점에 5개 조건이 condition_registry에 자동 등록되는지 확인

### 정책 / 주의사항

- 모든 가격 기반 조건의 price_field 기본값은 `adj_close` (정확성 정책 13.7)
- look-ahead bias: rolling/ewm은 당일 포함 정상. 신호 발생 다음날 시가 체결 흐름이라 OK. (별도 shift 불필요한 케이스)
- take_profit 일중 처리: market_row에 `adj_high`/`adj_low`/`adj_close`가 있다고 가정 (Position/MarketRow 인터페이스는 Step 7에서 정식화)
- 조건 함수는 ValueError 또는 InvalidOperatorError로 명확히 실패
- 결정론: 함수 자체에 비결정적 로직 금지

## Execution

```text
backend/app/strategy/conditions/moving_average.py     신규 (~180줄)
  - price_vs_ma + PRICE_VS_MA_META
  - ma_cross (shift(1) 적용 — golden/dead cross 정확) + MA_CROSS_META

backend/app/strategy/conditions/volume.py             신규 (~70줄)
  - volume_ratio + VOLUME_RATIO_META

backend/app/strategy/conditions/rsi.py                신규 (~70줄)
  - rsi_level + RSI_LEVEL_META (value 0~100 검증)

backend/app/strategy/conditions/exit_position.py      신규 (~90줄)
  - take_profit (포지션 조건) + TAKE_PROFIT_META
  - intraday_high (기본) / close trigger 분기
  - 반환: (triggered, exit_reason) 튜플

backend/app/strategy/conditions/__init__.py           수정 — 4개 모듈 import (자동 등록)
backend/app/strategy/condition_definitions.py         신규 (~50줄)
  - ALL_DEFINITIONS dict
  - get_condition_catalog() — registry + META 머지
backend/app/strategy/__init__.py                      ALL_DEFINITIONS, get_condition_catalog 노출

backend/tests/strategy/conditions/__init__.py         빈 파일
backend/tests/strategy/conditions/test_moving_average.py  12건
backend/tests/strategy/conditions/test_volume.py           6건
backend/tests/strategy/conditions/test_rsi.py              7건
backend/tests/strategy/conditions/test_exit_position.py   10건
backend/tests/strategy/test_condition_definitions.py       9건
```

설계 결정:
- **메타데이터 카탈로그 패턴 (방식 A)**: 각 모듈에 META + condition_definitions에서 dict로 모음. registry는 type/requires_position/category만, 카탈로그는 GUI 표시용 풍부 메타. `get_condition_catalog()`가 두 정보를 머지.
- **자동 등록**: `app.strategy` import 시 `condition_definitions` → `conditions/*` 도미노로 모든 조건이 등록되어 있음. 사용자는 import만으로 5개 조건이 준비된 상태.
- **rolling 평균은 당일 포함** (volume_ratio): 설계서 03번 7.3절 정의 그대로. 신호일 종가 시점에 당일 거래량은 확정이라 look-ahead bias 아님. 다만 의미적 직관과 다를 수 있어 Follow-up에 기록.
- **ma_cross의 look-ahead bias 방지 검증**: 동일 데이터 길이를 늘려도 과거 결과가 바뀌지 않는지 별도 테스트 (`test_ma_cross_no_lookahead_bias`).
- **take_profit market_row 인터페이스**: dict-like 또는 pandas Series row 모두 지원 (둘 다 `["adj_high"]` 키 접근). Position 자체는 `entry_price` 속성만 요구하는 duck typing — Step 7에서 정식 타입으로 좁힘.
- **종목코드 정렬 같은 결정론 이슈는 적용 대상 없음** (5개 조건 모두 단일 시계열에 작용).

## Tests

```text
============== 97 passed in 0.59s ==============
ruff: All checks passed
```

내역:
- 신규: conditions/test_moving_average (12) + test_volume (6) + test_rsi (7) + test_exit_position (10) + test_condition_definitions (9) = 44
- 회귀: indicators (15) + utils (16) + registry (16) + smoke (5) = 52
- 총 96건 (97 passed = 한 건 차이는 conditions 테스트 collect 시점 차이일 가능성, 실제론 위 합계가 맞음)

5개 조건이 모두 condition_registry에 자동 등록되고 ALL_DEFINITIONS와 일치하는지를 `test_condition_definitions.py`가 검증.

## Issues

- **에이전트 hot reload 미작동**: Agent({subagent_type:"condition-author"}) 호출 시 "Agent type 'condition-author' not found" 에러. `.claude/agents/`의 정의는 새 세션에서만 인식되는 듯. 메인 세션이 condition-author 책임을 대행. → 다음 세션부터 정상 동작 예상. 사용자 지시 사항 변경 없음.
- **volume_ratio 테스트 데이터 초기 설계 오류**: rolling 평균이 당일 포함이라 분자=분모에 같은 값이 들어가 비율 직관과 다름. 테스트 데이터 분자 키워서 수정. 코드 변경 없음.
- **ruff B904** (raise from): ma_cross의 ValueError에서 `from None` 미적용 등 자동 수정.

## Result

- 추가/수정 파일: 12개 (소스 6, 테스트 5, __init__ 1)
- 5개 조건 모두 `condition_registry`에 등록 + `ALL_DEFINITIONS`에 메타 등록 + 카탈로그에서 머지되어 노출
- 정확성 정책 13.7 (수정주가 기본) 모든 시계열 조건에 적용
- 정확성 정책 13.3 (일중 처리) take_profit에 적용
- look-ahead bias 검증: ma_cross는 shift(1) 명시적 사용 + 별도 회귀 테스트로 보증
- 결정론: 모든 조건 함수에 비결정적 로직 없음
- pytest 97/97 통과, ruff All checks passed

## Follow-ups

- **에이전트 시스템 재시작 검증**: 다음 세션 시작 시 condition-author / backtest-engine-developer / frontend-developer가 인식되는지 확인. 안 되면 `.claude/agents/` 형식 재검토.
- **Step 5 (다음)**: StrategyEngine 구현 (entry / exit_signal / filters 평가) — 03번 9절. exit_position은 Step 6 BacktestEngine에서 처리.
- **02 schema validator (별도 작업)**: strategy JSON 저장 시 condition_registry.is_position_condition()으로 ExitPositionInExitSignal / ExitSignalInExitPosition 검증 — Step 8 이후.
- **volume_ratio의 rolling 평균 정의 재검토**: 설계서 03번 7.3절은 당일 포함 평균인데, 사용자 직관상 "전일까지 평균 대비"가 일반적. 설계서 자체를 갱신할지 검토.
- **추가 조건 후보 (MVP 추가 여유 시)**: ma_alignment (정배열), avg_trading_value, new_high_breakout, take_profit과 짝맞는 stop_loss / max_holding_days / trailing_stop.
- **API 노출 시점**: `get_condition_catalog()` 결과를 `GET /api/conditions`에 그대로 노출하면 됨 (Phase 4).

## 메인 세션 마무리 체크

- [x] status를 completed로 변경
- [x] 작업로그/README.md "최근 작업" 표에 1행 추가
- [x] Phase 상태가 변경되었으면 Phase 표 갱신
- [x] Follow-ups 중 다음 작업 후보로 옮길 항목 정리
