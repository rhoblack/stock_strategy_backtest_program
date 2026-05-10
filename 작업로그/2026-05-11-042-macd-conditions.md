---
date: 2026-05-11
agent: condition-author
phase: 14
status: completed
roadmap_step: "042"
roadmap_impact:
  - 03-h
  - 03-i
related_docs:
  - 상세설계/03_condition_registry_engine_design.md
  - 상세설계/13_backtest_accuracy_policy_design.md
---

# step 042 — macd_cross + macd_histogram 조건 등록

## Plan

- [x] `backend/app/strategy/conditions/macd.py` 신규 생성
  - macd_cross 함수 + MACD_CROSS_META 등록
  - macd_histogram 함수 + MACD_HISTOGRAM_META 등록
- [x] `backend/app/strategy/conditions/__init__.py` macd import 추가
- [x] `backend/app/strategy/condition_definitions.py` ALL_DEFINITIONS에 2개 추가
- [x] `backend/tests/strategy/conditions/test_macd_conditions.py` 신규 작성
  - macd_cross: 골든크로스 / 데드크로스 / look-ahead bias 없음
  - macd_histogram: 양수/음수 임계값 비교 / NaN 처리
- [x] ruff check backend/app backend/tests → 0 errors
- [x] pytest backend/ -q → 기존 PASS 유지 + 신규 테스트 PASS

## Execution

### 신규 생성
- `backend/app/strategy/conditions/macd.py` (전체)
  - `macd_cross()` 함수 + `MACD_CROSS_META` dict
  - `macd_histogram()` 함수 + `MACD_HISTOGRAM_META` dict
  - `@condition_registry.register("macd_cross", requires_position=False, category="macd")`
  - `@condition_registry.register("macd_histogram", requires_position=False, category="macd")`
- `backend/tests/strategy/conditions/test_macd_conditions.py` (전체, 26개 테스트)

### 수정
- `backend/app/strategy/conditions/__init__.py:11` — `macd` import 알파벳 순 추가
- `backend/app/strategy/condition_definitions.py:18` — `from app.strategy.conditions import macd as _macd` 추가
- `backend/app/strategy/condition_definitions.py:32-33` — `ALL_DEFINITIONS`에 `MACD_CROSS_META`, `MACD_HISTOGRAM_META` 추가
- `backend/tests/api/test_conditions.py:52-80` — HTTP 레벨 MACD API 테스트 5건 추가

## Tests

### 신규 테스트 실행
```
backend/.venv/Scripts/python.exe -m pytest backend/tests/strategy/conditions/test_macd_conditions.py -v
```
결과: **26 passed in 0.37s**

### 전체 회귀 검증
```
backend/.venv/Scripts/python.exe -m pytest backend/ -q
```
결과: **1140 passed, 10 warnings in 21.46s** (기존 1114 + 신규 26)

### ruff 검사
```
backend/.venv/Scripts/python.exe -m ruff check backend/app backend/tests
```
결과: **All checks passed!** (auto-fix 1건: import 정렬)

## Issues

### 1. fixture 데이터가 크로스를 발생시키지 않음
- 초기 fixture `_trending_up` (완만 상승 후 급등)은 MACD가 처음부터 시그널 위에 위치해 골든크로스가 발생하지 않았음
- 진단: 크로스는 MACD가 시그널 아래 → 위로 전환할 때 발생. 단순 상승 데이터에서는 MACD가 이미 위에 있어서 크로스 없음.
- 해결: `_golden_cross_data` — 먼저 40봉 하락으로 MACD를 시그널 아래로 내린 뒤 급등 패턴으로 교체. 실제 크로스 발생 위치 인덱스 41 확인.
- 같은 이유로 `_trending_down` → `_dead_cross_data` (상승 후 급락) 패턴으로 교체.

### 2. client fixture 스코프 불일치
- `client` fixture가 `tests/api/conftest.py`에만 정의되어 있어 `tests/strategy/conditions/` 폴더에서 사용 불가
- 해결: API 테스트를 `get_condition_catalog()` 직접 호출 방식으로 교체 (HTTP 레벨 검증은 `tests/api/test_conditions.py`에 추가). 기존 패턴(다른 조건 테스트 파일도 client fixture 미사용)과 일관성 유지.

## Result

| 항목 | 값 |
|---|---|
| 조건 type (1) | `macd_cross` |
| requires_position | False |
| category | macd |
| allowed_in | ["entry", "exit_signal"] |
| sentence_template | "MACD({fast},{slow},{signal})가 시그널 라인을 {direction_label}" |
| look-ahead bias | 없음 — shift(1)으로 전일 macd/signal 비교, 당일 크로스만 감지 |
| 조건 type (2) | `macd_histogram` |
| requires_position | False |
| category | macd |
| allowed_in | ["entry", "exit_signal", "filters"] |
| sentence_template | "MACD({fast},{slow},{signal}) 히스토그램이 {value} {operator_label}" |
| look-ahead bias | 없음 — EMA 누적 계산으로 당일까지 데이터만 사용 |
| 기본 price_field | adj_close (정확성 정책 13.7 준수) |
| 테스트 | 26 PASS / 회귀 1140 PASS |

## Follow-ups

- **macd_divergence** (03-j 후보): 가격과 MACD 히스토그램의 다이버전스 감지 조건. `macd_histogram`의 확장 패턴이며 복잡도는 중간.
- **macd_histogram_slope**: 히스토그램의 기울기(전일 대비 증감 방향)로 모멘텀 가속/감속 판단. `histogram.diff() > 0` 패턴으로 구현 가능.
- **rsi_cross**: RSI가 기준값(예: 30, 70)을 상향/하향 돌파하는 시점 감지. `macd_cross`와 동일한 shift(1) 패턴 적용 가능.
- **테스트 fixture 공유 모듈**: `tests/strategy/conditions/fixtures.py`에 `_golden_cross_data()`, `_dead_cross_data()` 같은 범용 시장 패턴 데이터 헬퍼를 모아두면 이후 조건 테스트 작성 효율 향상.

## 메인 세션 마무리 체크

- [ ] status를 completed로 변경
- [ ] 작업로그/README.md "최근 작업" 표에 1행 추가
- [ ] PM 에이전트 호출 → 로드맵.md 갱신 — "step 042 마무리" 지시
- [ ] git commit (단일 커밋)
