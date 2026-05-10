---
date: 2026-05-11
agent: condition-author
phase: 14
status: completed
roadmap_step: "044"
roadmap_impact:
  - 03-m
  - 03-n
related_docs:
  - 상세설계/03_condition_registry_engine_design.md
  - 상세설계/13_backtest_accuracy_policy_design.md
---

# step 044 — bullish_candle + 기타 조건 등록

## Plan

- [ ] `backend/app/strategy/conditions/candle.py` 신규 생성
  - bullish_candle 함수 + BULLISH_CANDLE_META 등록
  - price_change_pct 함수 + PRICE_CHANGE_PCT_META 등록 (기타 조건 — 등락률 필터)
- [ ] `backend/app/strategy/conditions/__init__.py` candle import 추가
- [ ] `backend/app/strategy/condition_definitions.py` ALL_DEFINITIONS에 2개 추가
- [ ] `backend/tests/strategy/conditions/test_candle_conditions.py` 신규 작성
  - bullish_candle: 양봉(종가 > 시가) + 몸통 비율 필터 / 도지봉 처리
  - price_change_pct: N일 등락률 임계값 비교 / look-ahead bias 없음
- [ ] ruff check backend/app backend/tests → 0 errors
- [ ] pytest backend/ -q → 기존 PASS 유지 + 신규 테스트 PASS

## Execution

### 신규 파일

- `backend/app/strategy/conditions/candle.py` (신규)
  - L1~L26: 모듈 docstring (look-ahead bias 방지 정책 명시)
  - L29~L57: `bullish_candle()` 함수 (양봉 + 몸통 비율 필터)
  - L60~L93: `BULLISH_CANDLE_META` dict
  - L96~L130: `price_change_pct()` 함수 (전일 대비 등락률 비교)
  - L133~L172: `PRICE_CHANGE_PCT_META` dict
- `backend/tests/strategy/conditions/test_candle_conditions.py` (신규)
  - 24개 테스트 케이스

### 수정 파일

- `backend/app/strategy/conditions/__init__.py:11`
  - `candle` import 추가 (알파벳 순 — breakout과 exit_position 사이)
- `backend/app/strategy/condition_definitions.py:20`
  - `from app.strategy.conditions import candle as _candle` 추가
- `backend/app/strategy/condition_definitions.py:38~39`
  - `ALL_DEFINITIONS`에 `BULLISH_CANDLE_META`, `PRICE_CHANGE_PCT_META` 2개 등록

## Tests

```
backend/.venv/Scripts/python.exe -m ruff check backend/app backend/tests
→ All checks passed!

backend/.venv/Scripts/python.exe -m pytest backend/tests/strategy/conditions/test_candle_conditions.py -v
→ 24 passed in 0.36s

backend/.venv/Scripts/python.exe -m pytest backend/ -q
→ 1192 passed, 10 warnings in 21.45s (회귀 없음)
```

신규 테스트 24개 상세:
- bullish_candle: 9건 (정상/음봉/도지봉2/min_body_pct=0/비율미달/look-ahead/타입검증/임계값경계)
- price_change_pct: 8건 (양수/음수/첫행NaN/계산정확성/연산자/look-ahead/adj_open/잘못된연산자)
- condition_definitions: 7건 (등록확인/requires_position/allowed_in/exit포함여부/카탈로그/메타필드2건)

## Issues

없음.

## Result

| 항목 | bullish_candle | price_change_pct |
|------|---------------|-----------------|
| type | `bullish_candle` | `price_change_pct` |
| category | `candle` | `price` |
| requires_position | False | False |
| allowed_in | entry, filters | entry, exit_signal, filters |
| look-ahead bias | 없음 (당일 OHLC만 사용) | 없음 (shift(1) 전일 종가 사용) |
| price_field 기본값 | adj_open/adj_close (OHLC 비교) | adj_close (정확성 정책 13.7) |

**look-ahead bias 검증 결과:**
- `bullish_candle`: 당일 OHLC 4개 컬럼만 참조. rolling/shift 없음. 미래 행 추가 시 과거 결과 완전 불변 (테스트 `test_bullish_candle_no_lookahead_bias` 확인).
- `price_change_pct`: `price.shift(1)`로 전일 데이터 참조. 첫 행은 NaN → False. 미래 행 추가 시 과거 결과 완전 불변 (테스트 `test_price_change_pct_no_lookahead_bias` 확인).

**sentence_template:**
- bullish_candle: `"양봉이고 몸통이 전체 범위의 {min_body_pct}% 이상"`
- price_change_pct: `"{price_field_label}의 당일 등락률이 {value}% {operator_label}"`

## Follow-ups

1. **bearish_candle** — 음봉 + 몸통 비율 필터. `bullish_candle`과 대칭 패턴. `exit_signal` 섹션에서 매도 신호로 활용 가능.
2. **hammer / shooting_star** — 위/아래 꼬리 비율 기반 반전 캔들 조건. 현재 `bullish_candle`의 범위 계산 로직을 재사용.
3. **price_change_pct의 N일 집계** — 당일 등락률 대신 N일 중 최대/최소 등락률 비교. `rolling().max()` 패턴 적용.
4. **price_vs_prev_day** — 당일 가격이 전일 고가/저가 대비 돌파하는 조건. `shift(1)` + 특정 필드 비교 패턴 재사용.

## 메인 세션 마무리 체크

- [ ] status를 completed로 변경
- [ ] 작업로그/README.md "최근 작업" 표에 1행 추가
- [ ] PM 에이전트 호출 → 로드맵.md 갱신 — "step 044 마무리" 지시
- [ ] git commit (단일 커밋)
- [ ] Phase 14 마지막 step → git push origin main (Phase 완료 후)
