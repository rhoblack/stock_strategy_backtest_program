---
date: 2026-05-11
agent: condition-author
phase: 21
status: completed
roadmap_step: "061"
roadmap_impact:
  - 03-o
  - 03-p
related_docs:
  - 상세설계/03_condition_registry_engine_design.md
  - 상세설계/13_backtest_accuracy_policy_design.md
---

# Phase 21 / step 061 — ma_alignment + rsi_cross 조건 구현

## Plan

- [ ] `backend/app/strategy/conditions/moving_average.py`에 `ma_alignment` 함수 추가
  - 삼선 정렬: 단기 MA > 중기 MA > 장기 MA (상승 정렬) 또는 반대 (하락 정렬)
  - 파라미터: short_period (기본 5), mid_period (기본 20), long_period (기본 60), price_field (기본 "adj_close"), direction ("bullish" / "bearish")
  - look-ahead bias 체크: rolling 은 당일까지 포함해도 무방 (비교는 당일 값 간 관계로 미래 참조 없음)
  - `MA_ALIGNMENT_META` 메타데이터 딕셔너리 작성 (allowed_in: entry, filters)
- [ ] `backend/app/strategy/conditions/rsi.py`에 `rsi_cross` 함수 추가
  - RSI가 기준선을 상향/하향 돌파한 날
  - 골든크로스: 전일 RSI < threshold 이고 당일 RSI >= threshold (과매도 탈출 — 매수 신호)
  - 데드크로스: 전일 RSI > threshold 이고 당일 RSI <= threshold (과매수 탈출 — 매도 신호)
  - 파라미터: period (기본 14), threshold (기본 30), direction ("cross_above" / "cross_below"), price_field (기본 "adj_close")
  - look-ahead bias 체크: rsi 계산 후 shift(1) 비교로 전일 값만 사용
  - `RSI_CROSS_META` 메타데이터 딕셔너리 작성 (allowed_in: entry, exit_signal)
- [ ] `backend/app/strategy/conditions/__init__.py` — 신규 모듈 import 불필요 (기존 moving_average, rsi 모듈에 추가되므로 자동 등록)
- [ ] CONDITION_DEFINITIONS 리스트에 `MA_ALIGNMENT_META`, `RSI_CROSS_META` 추가 (`backend/app/strategy/definitions.py` 또는 해당 위치)
- [ ] 단위 테스트 작성 (`backend/tests/strategy/test_ma_alignment.py` 또는 기존 파일에 클래스 추가)
  - ma_alignment 상승 정렬 True 케이스
  - ma_alignment 하락 정렬 True 케이스
  - ma_alignment: 정렬 불만족 → False
  - ma_alignment: 잘못된 direction → ValueError
  - ma_alignment: short_period >= mid_period → ValueError (방어 검증)
  - rsi_cross cross_above 케이스 (전일 below, 당일 above)
  - rsi_cross cross_below 케이스
  - rsi_cross: 크로스 없는 경우 → False
  - rsi_cross: 잘못된 direction → ValueError
  - look-ahead bias 회귀: rsi_cross가 shift(1) 사용하는지 확인
- [ ] 전체 pytest 회귀 실행 (1379 PASS 기준 유지)
- [ ] ruff 체크 통과 확인

## Execution

### 수정/추가 파일

1. `backend/app/strategy/conditions/moving_average.py:180-307`
   - `ma_alignment` 함수 추가 (`@condition_registry.register("ma_alignment", ...)` 데코레이터 포함)
   - `MA_ALIGNMENT_META` dict 추가 (allowed_in: ["entry", "filters"])
   - 모듈 docstring에 `ma_alignment` 항목 추가

2. `backend/app/strategy/conditions/rsi.py:1-9` (docstring 갱신), `rsi.py:82-191`
   - `rsi_cross` 함수 추가 (`@condition_registry.register("rsi_cross", ...)` 데코레이터 포함)
   - `RSI_CROSS_META` dict 추가 (allowed_in: ["entry", "exit_signal"])
   - 모듈 docstring에 `rsi_cross` 항목 및 look-ahead bias 검증 주석 추가

3. `backend/app/strategy/condition_definitions.py:29-30`
   - `ALL_DEFINITIONS`에 `MA_ALIGNMENT_META`, `RSI_CROSS_META` 2개 항목 추가

4. `backend/tests/strategy/conditions/test_moving_average.py`
   - import에 `MA_ALIGNMENT_META`, `ma_alignment` 추가
   - `ma_alignment` 테스트 10개 추가 (bullish/bearish 감지, False 케이스, NaN 초기화, 기본값, 파라미터 오류, look-ahead bias, META 필드)

5. `backend/tests/strategy/conditions/test_rsi.py`
   - import에 `RSI_CROSS_META`, `rsi_cross` 추가
   - `rsi_cross` 테스트 10개 추가 (cross_above/below 감지, False 케이스, NaN 초기화, 기본값, threshold/direction 오류, look-ahead bias, META 필드)

## Tests

```
# 신규 테스트만 (2개 파일)
backend/.venv/Scripts/python.exe -m pytest backend/tests/strategy/conditions/test_moving_average.py backend/tests/strategy/conditions/test_rsi.py -v
→ 39 passed in 0.42s

# 전체 회귀
backend/.venv/Scripts/python.exe -m pytest backend/ -q
→ 1399 passed, 10 warnings in 38.02s

# ruff lint
backend/.venv/Scripts/python.exe -m ruff check backend/app/ --select I --fix
backend/.venv/Scripts/python.exe -m ruff check backend/app/
→ All checks passed!
```

## Issues

없음.

## Result

| 항목 | ma_alignment | rsi_cross |
|------|-------------|-----------|
| condition_type | `ma_alignment` | `rsi_cross` |
| requires_position | False | False |
| category | moving_average | rsi |
| allowed_in | entry, filters | entry, exit_signal |
| look-ahead bias | 없음 (rolling은 당일까지만; MA 간 대소 비교는 미래 참조 없음) | 없음 (shift(1)으로 전일 RSI 참조) |
| sentence_template | "{short_period}일·{mid_period}일·{long_period}일 이동평균이 {direction_label} 정렬" | "RSI({period})가 {threshold}를 {direction_label}" |
| 방어 검증 | short<mid<long 순서 위반 시 ValueError, 잘못된 direction 시 ValueError | threshold 0~100 범위 위반 시 ValueError, 잘못된 direction 시 ValueError |

## Follow-ups

- step 062: 12-l Golden 실제 시세 fixture (samsung_5y_prices.csv 등) 구비

## 메인 세션 마무리 체크

- [ ] status를 completed로 변경
- [ ] 작업로그/README.md "최근 작업" 표에 1행 추가
- [ ] Phase 상태가 변경되었으면 Phase 표 갱신
- [ ] Follow-ups 중 다음 작업 후보로 옮길 항목 정리
- [ ] **PM 에이전트 호출 → 로드맵.md 갱신** — "step 061 마무리" 지시
- [ ] `git commit` (단일 커밋)
