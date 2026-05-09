---
date: 2026-05-09
agent: main
phase: 1
status: completed
related_docs:
  - 상세설계/03_condition_registry_engine_design.md
  - 상세설계/13_backtest_accuracy_policy_design.md
---

# Phase 1 / Step 3 — indicators.py + compare 유틸리티

## Plan

설계서 03번 5절 "지표 함수와 조건 함수 분리" 원칙에 따라 지표 계산 함수와 조건 판단 함수를 별도 모듈로 둠. Step 4에서 사용할 조건 5개 (price_vs_ma / ma_cross / volume_ratio / rsi_level / take_profit)에 필요한 지표를 우선 구현.

look-ahead bias는 indicators 자체가 아니라 조건 함수 책임이므로 indicators는 당일 값 포함하는 표준 계산을 한다 (rolling, ewm 등). shift는 조건 함수가 적용.

- [x] **(환경 셋업)** backend/.venv 만들고 `pip install -e ".[dev]"` 실행 → pytest로 회귀 검증 가능 환경
- [x] backend/README.md 추가 (셋업/명령어 안내) — pyproject.toml의 readme 참조
- [x] `app/strategy/indicators.py` 작성
- [x] `app/strategy/utils.py` 작성
- [x] `app/strategy/__init__.py` 갱신 (compare 노출)
- [x] `tests/strategy/test_indicators.py` (15건)
- [x] `tests/strategy/test_utils.py` (16건, parametrize 포함)
- [x] `pytest -v`로 회귀 + 신규 검증 (53/53 통과)
- [x] ruff 린트 통과

## 환경 셋업 결과

```bash
cd backend
py -m venv .venv
./.venv/Scripts/python.exe -m pip install --upgrade pip
./.venv/Scripts/python.exe -m pip install -e ".[dev]"
```

설치된 주요 패키지: pandas-3.0.2, numpy-2.4.4, pydantic-2.13.4, pytest-9.0.3, pytest-cov-7.1.0, ruff-0.15.12

`./.venv/Scripts/python.exe -m pytest -v` → 21/21 통과 (Step 1·2 회귀 검증)
`./.venv/Scripts/python.exe -m pytest -v` (Step 3 후) → 53/53 통과
`./.venv/Scripts/python.exe -m ruff check app tests` → All checks passed

## Execution

```text
backend/README.md                         신규 (셋업 가이드, 디렉토리 구조, 자주 쓰는 명령)
backend/app/strategy/indicators.py        신규 (78줄)
  - moving_average(series, period) - SMA, period<1 ValueError
  - ema(series, period) - 표준 EMA (adjust=False, min_periods=period)
  - rsi(series, period=14) - Wilder RSI (ewm alpha=1/period)
  - macd(close, fast=12, slow=26, signal=9) - (macd_line, signal_line, histogram)
backend/app/strategy/utils.py             신규 (35줄)
  - compare(left, operator, right) - 5 operators, InvalidOperatorError
  - ALLOWED_OPERATORS 상수
backend/app/strategy/__init__.py          compare, ALLOWED_OPERATORS 추가 노출

backend/tests/strategy/test_indicators.py 신규 (15건)
  - moving_average: period=1 항등성, 초기 NaN, period 검증, index 보존
  - ema: 길이 보존, 단조 증가, 상수 입력 → 상수 (numpy assert_allclose로 수정)
  - rsi: 단조 상승 → 100 / 단조 하락 → 0 / first valid = period / 0~100 범위
  - macd: 3-tuple 반환, hist = macd - signal, 상승 추세에서 양수, fast >= slow ValueError

backend/tests/strategy/test_utils.py      신규 (16건, 5개 parametrize 포함)
  - scalar vs scalar 5개 연산자
  - Series vs scalar / Series vs Series
  - NaN 전파 (False)
  - InvalidOperatorError + 메시지에 허용 연산자 노출

backend/tests/strategy/test_registry.py   1건 수정 (Exception → AttributeError, ruff B017)
```

설계 결정:
- **RSI**: Wilder 방식 (`ewm(alpha=1/period, adjust=False, min_periods=period)`) 채택. 한국 HTS/키움 등 주요 차트와 동일한 결과.
- **EMA**: 표준 `span` 방식 (`adjust=False`). pandas 기본값보다 보수적인 평활화.
- **indicators.py는 look-ahead bias를 직접 방어하지 않음** — rolling/ewm은 당일 포함 계산. shift는 조건 함수 책임. 03번 7.4절의 new_high_breakout이 그 예시.
- **compare는 InvalidOperatorError 발생** — ValueError 대신 도메인 예외로 API 응답에 그대로 매핑 가능.
- **Bollinger Band, ATR**: Phase 1 조건 5개에 안 쓰여 보류. 향후 Step에서 필요 시 추가.

## Tests

```text
================== test session starts ==================
collected 53 items

tests/strategy/test_indicators.py    15 passed
tests/strategy/test_registry.py      16 passed
tests/strategy/test_utils.py         16 passed
tests/test_smoke.py                   5 passed

================== 53 passed in 0.52s ==================
```

ruff: All checks passed.

## Issues

- **EMA 상수 입력 테스트 초기 실수**: `(result == pytest.approx(10.0)).all()` 패턴은 동작하지 않음. pandas Series에 pytest.approx 비교는 element-wise가 아니라 series-wise라 실패. → `np.testing.assert_allclose(result.to_numpy(), 10.0, atol=1e-9)`로 수정.
- **ruff B017 (blanket Exception)**: test_condition_entry_is_frozen에서 `Exception`으로 잡던 것을 `AttributeError`로 좁힘. `dataclasses.FrozenInstanceError`가 `AttributeError`의 서브클래스라 정확.
- **ruff I001 import 정렬**: 자동 수정 (`--fix`)으로 처리.

## Result

- 추가/수정 파일: 7개 (indicators.py 신규, utils.py 신규, __init__.py 수정, README.md 신규, test_indicators.py 신규, test_utils.py 신규, test_registry.py 1건 수정)
- 31건 신규 테스트 + 22건 기존 회귀 = 53건 모두 통과
- 환경 셋업 완료 → 이후 단계는 venv pytest로 자동 회귀 가능
- look-ahead bias 검증: indicators 자체는 표준 계산, 조건 함수 단계에서 책임 (Step 4)
- 정확성 정책 13번 영향: 13.7 수정주가 사용은 조건 함수가 `adj_close`를 인자로 넘겨서 처리. indicators는 series만 받음 (소스 무관).

## Follow-ups

- **Step 4 (다음)**: 기본 조건 5개 작성 (price_vs_ma / ma_cross / volume_ratio / rsi_level / take_profit)
  - condition-author 에이전트 호출 후보. 다만 Step 4는 5개 조건을 한 번에 다루는 게 효율적이라 직접 진행할지 에이전트별로 분할할지 검토.
  - take_profit은 포지션 조건이라 별도 처리 (현재 Position/TradeGroup 미정 상태이므로 Step 7 직전에 추가하거나 mock으로 진행).
- **Bollinger Band, ATR, OBV** 등 추가 지표는 사용 시점에 추가 (over-engineering 회피).
- **macd 골든크로스 시점 검증 테스트** 추가 가능 (Step 4에서 macd_cross 조건 만들 때).
- **CI 셋업 (Phase 1 종료 시)**: GitHub Actions로 pytest + ruff 자동화.

## 메인 세션 마무리 체크

- [x] status를 completed로 변경
- [x] 작업로그/README.md "최근 작업" 표에 1행 추가
- [x] Phase 상태가 변경되었으면 Phase 표 갱신
- [x] Follow-ups 중 다음 작업 후보로 옮길 항목 정리
