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

# Phase 1 / Step 5 — StrategyEngine 구현

## Plan

설계서 03번 9절의 StrategyEngine을 구현. entry / exit_signal / filters 섹션을 시계열 단위로 평가하여 신호 시리즈를 생성. exit_position은 BacktestEngine 책임이므로 여기서는 처리하지 않음.

### 핵심 책임

```text
입력: strategy_json (dict) + 시장 데이터 df (pd.DataFrame, adj_* 컬럼 포함)
출력: df + entry_signal, exit_signal, filter_signal, final_entry_signal 컬럼
```

### Plan 항목

- [x] `app/strategy/engine.py` 작성 (StrategyEngine + AND/OR/GROUP)
- [x] registry 자동 차단으로 PositionConditionMisuseError 보장
- [x] `app/strategy/__init__.py`에 StrategyEngine 노출
- [x] `tests/strategy/test_strategy_engine.py` 작성 (17건)

### 검증

- pytest 97 + 신규 → 110+ 통과
- ruff All checks passed
- 정확성 정책 위반 없음 (StrategyEngine은 시계열 평가만 — 일중 처리/체결과 무관)

## Execution

```text
backend/app/strategy/engine.py            신규 (~115줄)
  - StrategyEngine 클래스
    - __init__(strategy_json)
    - generate_signals(df) → df + entry_signal/exit_signal/filter_signal/final_entry_signal
    - _build_section_signal(df, section) — AND/OR/GROUP 분기
    - _build_group_signal(df, section) — operator AND|OR + groups[]
backend/app/strategy/__init__.py          StrategyEngine 추가 노출

backend/tests/strategy/test_strategy_engine.py  신규 (17건)
```

설계 결정:
- **df는 항상 `df.copy()`** — 입력 보존. 호출자가 안전하게 다시 사용 가능. test로 보증.
- **exit_signal 섹션이 없으면 False 시리즈**, filters가 없으면 True 시리즈. 의미적으로 entry/filter는 "통과시키는" 디폴트, exit는 "발동 안 함"이 디폴트.
- **GROUP 1단계 중첩만**: 02번 4절 정책 그대로. group 안에 또 group 두면 무시 (현재 구현은 1단계만 처리). 향후 재귀 확장은 schema 갱신 후.
- **포지션 조건 차단은 registry가 처리**: StrategyEngine은 그대로 condition_registry.evaluate()를 호출하면 registry가 PositionConditionMisuseError를 발생시킴. StrategyEngine 자체에는 라우팅 검사 로직 불필요 (defense-in-depth는 registry에 위치).
- **결정론**: 함수형 스타일, 모든 작업이 pandas 연산. 외부 상태/난수 없음. 테스트로 5회 반복 동일성 검증.

## Tests

```text
============== 114 passed in 0.71s ==============
ruff: All checks passed
```

신규 17건 (test_strategy_engine.py):
- entry 단일/AND/OR/empty
- filters 결합 (filter 없을 때 default True)
- exit_signal 평가 + default False
- GROUP OR 조합 / 잘못된 operator / 빈 groups
- UnknownConditionTypeError 라우팅
- PositionConditionMisuseError (entry/exit_signal에 take_profit 시)
- 잘못된 logic
- 동일 입력 → 동일 출력 (결정론, 5회 반복)
- 입력 df 비변형

회귀: 기존 97건 그대로 통과.

## Issues

- 작은 ruff I001 import 정렬 1건 — 자동 수정.
- exit_signal default를 `pd.Series(False, ...)`로 했는데, BacktestEngine이 이걸 어떻게 활용할지는 Step 6에서 결정. 일단 의미는 "exit_signal 섹션 없으면 신호 발생 안 함"으로 해석.

## Result

- 추가/수정 파일: 3개 (engine.py, __init__.py, test_strategy_engine.py)
- StrategyEngine이 02번 schema의 entry/exit_signal/filters를 모두 처리
- AND/OR/GROUP 1단계 중첩 지원
- 입력 df 비변형 + 결정론 보장
- 정확성 정책 영향: 시계열 평가만 — 13.7(수정주가)는 조건 함수 차원, 13.3(일중)/13.5(호가)/13.8(priority)/13.6(세율) 모두 BacktestEngine 영역
- pytest 114/114, ruff 통과

## Follow-ups

- **Step 6 (다음)**: 단일 종목 BacktestEngine 골격 — 04번 5~6절 참조. 날짜별 루프, exit_position 평가 위임 흐름, EventLogger.
- **Step 7**: ExecutionModel + Portfolio + Position + TradeGroup. 정확성 정책 13.3 (일중 익절/손절), 13.5 (호가 단위), 13.6 (세율 시계열)을 처음 코드로 적용.
- **02 schema validator 별도 작업**: pydantic 모델로 strategy JSON 검증 — `app/schemas/strategy.py`에 작성. registry.is_position_condition()을 사용해 ExitPositionInExitSignal/ExitSignalInExitPosition을 schema 단계에서 차단.
- **GROUP 다단계 중첩**: schema 02번에 추가 시 engine도 재귀로 확장.

## 메인 세션 마무리 체크

- [x] status를 completed로 변경
- [x] 작업로그/README.md "최근 작업" 표에 1행 추가
- [x] Phase 상태가 변경되었으면 Phase 표 갱신
- [x] Follow-ups 중 다음 작업 후보로 옮길 항목 정리
