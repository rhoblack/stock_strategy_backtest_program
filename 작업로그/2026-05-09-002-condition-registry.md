---
date: 2026-05-09
agent: main
phase: 1
status: completed
related_docs:
  - 상세설계/03_condition_registry_engine_design.md
  - 상세설계/02_strategy_json_schema_design.md
  - 상세설계/13_backtest_accuracy_policy_design.md
---

# Phase 1 / Step 2 — ConditionRegistry 코어 구현

## Plan

03번 condition_registry 문서 3절의 패턴을 그대로 구현. 시계열 조건과 포지션 조건의 라우팅을 `requires_position` 메타데이터로 분기하는 것이 핵심.

- [x] `app/core/exceptions.py`에 PositionConditionMisuseError, TimeseriesConditionMisuseError 추가
- [x] `app/strategy/registry.py` 구현
  - [x] `ConditionEntry` dataclass (func, requires_position, category) — frozen
  - [x] `ConditionRegistry` 클래스
    - [x] `register(condition_type, *, requires_position, category)` 데코레이터
    - [x] `evaluate(condition_type, df, condition)` — 시계열용
    - [x] `evaluate_position(condition_type, position, market_row, condition)` — 포지션용
    - [x] `is_position_condition(condition_type)` + `get_category()`
    - [x] `list_conditions()` + `list_condition_types()`
  - [x] 모듈 레벨 `condition_registry` 인스턴스
- [x] `app/strategy/__init__.py`에 `condition_registry` 노출
- [x] `tests/strategy/test_registry.py` 작성 (16건)
- [x] manual test runner로 검증 (pytest 미설치 환경)

## 환경 제약 노트

시스템 환경에 pandas/numpy/pydantic 모두 미설치. registry.py는 pandas를 런타임 import하지 않고 `TYPE_CHECKING`으로만 사용하여 환경 무관하게 동작 가능하게 함. 테스트도 pandas 없이 dummy 함수(list/tuple 반환)로 동작 검증.

## Execution

```text
backend/app/core/exceptions.py:53     PositionConditionMisuseError 추가 (code: POSITION_CONDITION_MISUSE)
backend/app/core/exceptions.py:62     TimeseriesConditionMisuseError 추가 (code: TIMESERIES_CONDITION_MISUSE)
                                       → 도메인 예외 13개 → 15개

backend/app/strategy/registry.py      신규 (137줄)
  - ConditionEntry (frozen dataclass)
  - ConditionRegistry 클래스
    - register(): keyword-only requires_position/category로 디자인
    - evaluate() / evaluate_position() / is_position_condition() / get_category()
    - list_conditions() / list_condition_types()
    - _get_entry() 내부 헬퍼로 미등록 type 검사 일원화
  - 모듈 싱글턴: condition_registry

backend/app/strategy/__init__.py      ConditionEntry, ConditionRegistry, condition_registry 노출

backend/tests/strategy/test_registry.py  신규 (16건 테스트)
```

설계 결정:
- `register()`의 requires_position/category를 **keyword-only** 인자로 만들어 호출 시점 의도를 명확히
  (예: `@registry.register("take_profit", requires_position=True, category="exit_position")`)
- 미등록 type 검사를 `_get_entry()` 헬퍼로 일원화 — evaluate / evaluate_position / is_position_condition / get_category 모두 일관 동작
- TYPE_CHECKING으로 pandas import를 런타임에 회피 → 인프라 레이어가 데이터 라이브러리에 비종속
- `re-register`는 의도적으로 허용 (나중에 등록한 함수가 덮어씀). 테스트 편의 + 향후 동적 재등록 시나리오 대비
- `evaluate_position` 반환은 `(triggered: bool, exit_reason: str | None)` 튜플로 03번 14절 인터페이스 따름

## Tests

환경 제약: pytest 미설치. 동일 검증을 manual runner로 수행 (test_registry.py에 pytest 형식 테스트도 함께 작성해 venv 셋업 후 그대로 동작).

```text
PASS: test_register_and_evaluate_timeseries_condition
PASS: test_evaluate_passes_df_and_condition_arguments
PASS: test_register_and_evaluate_position_condition
PASS: test_evaluate_position_passes_three_arguments
PASS: test_position_condition_via_evaluate_raises
PASS: test_timeseries_condition_via_evaluate_position_raises
PASS: test_unknown_type_in_evaluate_raises
PASS: test_unknown_type_in_evaluate_position_raises
PASS: test_unknown_type_in_is_position_condition_raises
PASS: test_is_position_condition_returns_correct_flag
PASS: test_get_category_returns_registered_value
PASS: test_list_conditions_returns_metadata_dicts
PASS: test_list_condition_types_returns_names
PASS: test_re_registering_overwrites_previous
PASS: test_condition_entry_is_frozen
PASS: test_module_level_condition_registry_exists

--- Smoke regression ---
PASS: app_importable
PASS: core_importable
PASS: exception_codes_unique_and_grew (13 → 15)

총 19개 / 통과 19 / 실패 0
```

## Issues

- 환경에 pytest/pandas 미설치 — manual runner로 우회. test_registry.py 자체는 pytest 형식.
- `expect_raises` 래퍼를 manual runner에 만들어 `pytest.raises` 대체.

## Result

- 추가/수정 파일: 4개 (exceptions.py 수정, registry.py 신규, strategy/__init__.py 신규, test_registry.py 신규)
- 03번 문서 라우팅 메커니즘 100% 구현 (시계열/포지션 분기 + 오류 명확)
- 02번 문서 schema validation 시점에 잡혀야 할 정책 위반을 런타임에서도 방어 (defense-in-depth)
- 16건의 unit test로 라우팅/오류/메타데이터/싱글턴 검증
- look-ahead bias 검증 항목 없음 (조건 함수가 아닌 라우팅 인프라)
- 결정론 영향 없음 (dict 순서에 의존하는 코드 없음)

## Follow-ups

- **Step 3 (다음)**: `app/strategy/indicators.py` (이동평균/RSI/MACD/ATR 등 지표 함수) + compare 유틸리티
  - 이 단계부터는 pandas 의존 → venv 셋업이 강하게 권장됨
- 02번 schema validator 구현 시 `condition_registry.is_position_condition()`을 사용해 ExitPositionInExitSignalError / ExitSignalInExitPositionError를 발생시키도록 연결
- 03번 문서 15절의 `CONDITION_DEFINITIONS` 카탈로그 (sentence_template, parameters)는 별도 정의로 두고 list_conditions와 머지하는 패턴 — Step 4에서 첫 적용
- pytest 환경 구축 후 `pytest backend/tests/strategy/test_registry.py -v`로 자동 회귀 검증

## 메인 세션 마무리 체크

- [x] status를 completed로 변경
- [x] 작업로그/README.md "최근 작업" 표에 1행 추가
- [x] Phase 상태가 변경되었으면 Phase 표 갱신
- [x] Follow-ups 중 다음 작업 후보로 옮길 항목 정리
