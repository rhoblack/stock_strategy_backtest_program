---
date: 2026-05-11
agent: condition-author
phase: 14
status: completed
roadmap_step: "043"
roadmap_impact:
  - 03-j
  - 03-k
  - 03-l
related_docs:
  - 상세설계/03_condition_registry_engine_design.md
  - 상세설계/13_backtest_accuracy_policy_design.md
---

# step 043 — new_high_breakout + gap_pct + momentum_return 조건 등록

## Plan

- [ ] `backend/app/strategy/conditions/breakout.py` 신규 생성
  - new_high_breakout 함수 + NEW_HIGH_BREAKOUT_META 등록
  - gap_pct 함수 + GAP_PCT_META 등록
  - momentum_return 함수 + MOMENTUM_RETURN_META 등록
- [ ] `backend/app/strategy/conditions/__init__.py` breakout import 추가
- [ ] `backend/app/strategy/condition_definitions.py` ALL_DEFINITIONS에 3개 추가
- [ ] `backend/tests/strategy/conditions/test_breakout_conditions.py` 신규 작성
  - new_high_breakout: shift(1).rolling(period).max() look-ahead bias 없음 / 신고가 돌파 날만 True
  - gap_pct: 당일 시가 vs 전일 종가 갭률 / 상갭/하갭 임계값 비교
  - momentum_return: N일 전 종가 대비 수익률 / look-ahead bias 없음
- [ ] ruff check backend/app backend/tests → 0 errors
- [ ] pytest backend/ -q → 기존 PASS 유지 + 신규 테스트 PASS

## Execution

| 파일 | 변경 내용 |
|------|-----------|
| `backend/app/strategy/conditions/breakout.py` (신규) | `new_high_breakout`, `gap_pct`, `momentum_return` 함수 + 각 `*_META` dict 정의. `@condition_registry.register` 데코레이터로 자동 등록. |
| `backend/app/strategy/conditions/__init__.py:11` | `breakout` 모듈 import 추가 (알파벳 순, `exit_position` 앞) |
| `backend/app/strategy/condition_definitions.py:17` | `from app.strategy.conditions import breakout as _breakout` 추가 |
| `backend/app/strategy/condition_definitions.py:37-39` | `ALL_DEFINITIONS`에 `NEW_HIGH_BREAKOUT_META`, `GAP_PCT_META`, `MOMENTUM_RETURN_META` 3개 등록 |
| `backend/tests/strategy/conditions/test_breakout_conditions.py` (신규) | 28개 테스트 케이스 작성 |

## Tests

```
# 신규 테스트 (28건)
backend/.venv/Scripts/python.exe -m pytest backend/tests/strategy/conditions/test_breakout_conditions.py -v
→ 28 passed in 0.38s

# 전체 회귀 (기존 포함)
backend/.venv/Scripts/python.exe -m pytest backend/ -q
→ 1168 passed, 10 warnings in 21.44s  (기존 1140 → 신규 28건 추가, 회귀 없음)

# ruff lint
backend/.venv/Scripts/python.exe -m ruff check backend/app backend/tests
→ All checks passed!
```

**신규 테스트 항목 (28건)**:
- new_high_breakout (7건): 돌파 True, 미달 False, 같은 값 False, look-ahead bias 없음, period 미만 False, adj_close 필드, META 검증
- gap_pct (8건): 상갭 True, 하갭 True, 첫 행 False, 계산 정확성 (3.0%), 4가지 operator, 임계값 미만 False, 잘못된 operator, META 검증
- momentum_return (8건): 양수 수익률 True, 음수 수익률 True, period 미만 False, look-ahead bias 없음, 임계값 정확성 (10.0%), META 검증, adj_open 필드, 잘못된 operator
- condition_definitions (5건): ALL_DEFINITIONS 3개 등록, catalog 3개 포함, exit_position 비노출, exit_signal 포함, requires_position=False

## Issues

**발생한 문제**: 테스트에서 `assert result.iloc[N] is True` 패턴 사용 시 `np.True_ is True` → AssertionError (14건 실패)

**원인**: pandas Series에서 `.iloc[N]`으로 추출한 값은 `numpy.bool_` 타입이며, Python 내장 `bool` singleton과 `is` 연산자로 비교할 수 없음.

**해결**: 기존 `test_volume.py` 패턴(`== True  # noqa: E712`)을 따라 모두 `==` 비교로 변경. 함수 구현 코드는 수정 불필요 (조건 함수의 `.fillna(False)` 결과가 bool dtype임은 확인).

## Result

| 항목 | 내용 |
|------|------|
| **new_high_breakout** | type: `new_high_breakout`, requires_position: False, category: `breakout`, allowed_in: `["entry", "filters"]` |
| **gap_pct** | type: `gap_pct`, requires_position: False, category: `breakout`, allowed_in: `["entry", "filters"]` |
| **momentum_return** | type: `momentum_return`, requires_position: False, category: `momentum`, allowed_in: `["entry", "exit_signal", "filters"]` |

**look-ahead bias 검증 결과**:
- `new_high_breakout`: `df[field].shift(1).rolling(period, min_periods=period).max()` — 전일까지의 최고가와 당일 가격 비교. 미래 데이터 추가 후 과거 신호 불변 (test_new_high_breakout_no_lookahead_bias 통과)
- `gap_pct`: `df["adj_close"].shift(1)` — 전일 종가로 당일 시가와 비교. 과거 데이터만 사용
- `momentum_return`: `price.shift(period)` — N일 전 과거 데이터 참조. 미래 데이터 추가 후 과거 신호 불변 (test_momentum_return_no_lookahead_bias 통과)

**sentence_template**:
- new_high_breakout: `"{field_label}가 {period}일 신고가 돌파"`
- gap_pct: `"갭률이 {value}% {operator_label}"`
- momentum_return: `"{period}일 수익률이 {value}% {operator_label}"`

## Follow-ups

1. **`new_low_breakout`**: new_high_breakout의 대칭 조건 — N일 신저가 하향 돌파. `df[field].shift(1).rolling(period).min()` 패턴으로 동일하게 구현 가능. allowed_in: `["exit_signal", "filters"]` 쪽이 주 용도.
2. **`gap_direction` 파라미터화**: 현재 gap_pct는 operator와 value로 방향을 표현하지만, GUI UX 측면에서 "상갭"/"하갭" select 파라미터를 추가하면 사용자 혼란 감소. 단, 내부 로직은 동일.
3. **`momentum_rank`**: N일 수익률 순위 기반 필터 (유니버스 상위 K개 선택). 이는 여러 종목 간 비교가 필요하므로 ConditionRegistry 패턴이 아닌 별도 universe_filter 레이어 필요.
4. **`rate_of_change` (ROC)**: momentum_return과 유사하지만 % 대신 배수로 표현하거나 EMA 스무딩 추가. momentum_return에서 파생 가능.

## 메인 세션 마무리 체크

- [ ] status를 completed로 변경
- [ ] 작업로그/README.md "최근 작업" 표에 1행 추가
- [ ] PM 에이전트 호출 → 로드맵.md 갱신 — "step 043 마무리" 지시
- [ ] git commit (단일 커밋)
