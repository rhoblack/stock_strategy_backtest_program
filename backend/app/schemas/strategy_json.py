"""Strategy JSON 검증 (02번 5절 + 03번 4절 + 10번 7.1 카탈로그).

라우트(strategies create/update + backtests create) 진입 직전에 호출되어
잘못된 strategy_json이 영속화되거나 백테스트 큐로 들어가는 것을 차단한다.

검증 항목 (02.15 + 본 작업 요건):
    [최상위/필수]
    - dict 타입
    - name 존재 (선택, 라우트 schema에서 또 검증되지만 here는 strategy_json 내
      "name" 없을 수도 있어 강요하지 않음)
    - entry.conditions 최소 1개
    - exit_signal 또는 exit_position 중 최소 하나 존재

    [조건 라우팅 — 가장 중요]
    - 모든 condition.type이 ConditionRegistry에 등록되어 있음
      → UNKNOWN_CONDITION_TYPE
    - requires_position=True 조건은 exit_position에만 허용
      → 다른 섹션에 들어오면 EXIT_POSITION_IN_EXIT_SIGNAL
    - requires_position=False 조건은 entry/exit_signal/filters에만 허용
      → exit_position에 들어오면 EXIT_SIGNAL_IN_EXIT_POSITION

    [logic / GROUP]
    - logic ∈ {"AND", "OR", "GROUP"}
    - GROUP은 1단계만 (그룹 안에 그룹 금지)
    - GROUP은 operator + groups 키 필요

    [position_sizing]
    - method ∈ {"fixed_amount", "fixed_ratio", "equal_weight", "daily_budget"}
    - method=fixed_amount면 amount > 0
    - max_positions >= 1 (있다면)
    - max_daily_entries >= 0 (있다면)
    - daily_buy_budget >= 0 (있다면)

    [execution]
    - fee_rate >= 0
    - tax_rate: float >=0 또는 [{from: ISO date, rate: >=0}] (from 오름차순)
    - slippage >= 0
    - tick_rounding ∈ {"buy_up_sell_down", "nearest"}
    - entry_price/exit_price ∈ {"open","close","next_open","next_close"}

    [priority]
    - method ∈ {"trading_value_desc","market_cap_desc","market_cap_asc",
                "volume_ratio_desc","price_change_desc","random"}
    - tie_breaker ∈ {"symbol_asc","symbol_desc"}

실패 시 AppError(또는 하위 클래스)를 raise하여 errors.py의
exception_handler가 표준 envelope 응답으로 변환하게 한다.

설계 원칙:
    - 결정론: 모든 검증은 명시적 순서로 수행하고, details도 결정론적 순서로 정렬.
    - 카탈로그: 새 코드 만들지 말고 10.7.1 카탈로그에서 선택.
    - registry 직접 import: ConditionRegistry는 이미 모듈 import 시점에
      모든 조건이 등록된 상태 (app.strategy.condition_definitions가 import 부수효과).
"""

from __future__ import annotations

from datetime import date as date_type
from typing import Any

from app.core.exceptions import (
    ExitPositionInExitSignalError,
    ExitSignalInExitPositionError,
    InvalidOperatorError,
    InvalidParameterValueError,
    InvalidStrategyJsonError,
    MissingRequiredParameterError,
    UnknownConditionTypeError,
)
from app.strategy.utils import ALLOWED_OPERATORS

# 02번 4절 + GROUP 1단계
ALLOWED_LOGIC = ("AND", "OR", "GROUP")
# GROUP의 operator (그룹들끼리의 결합)
ALLOWED_GROUP_OPERATORS = ("AND", "OR")
# 02번 8절 — MVP는 fixed_amount/daily_budget만 지원하지만 schema 검증은 전체 허용
ALLOWED_POSITION_SIZING_METHODS = (
    "fixed_amount",
    "fixed_ratio",
    "equal_weight",
    "daily_budget",
)
# 02번 7절
ALLOWED_PRIORITY_METHODS = (
    "trading_value_desc",
    "market_cap_desc",
    "market_cap_asc",
    "volume_ratio_desc",
    "price_change_desc",
    "random",
)
ALLOWED_PRIORITY_TIE_BREAKERS = ("symbol_asc", "symbol_desc")
# 02번 11절
ALLOWED_TICK_ROUNDING = ("buy_up_sell_down", "nearest")
ALLOWED_EXECUTION_PRICE = ("open", "close", "next_open", "next_close")
# entry/filters/exit_signal vs exit_position 라우팅
TIMESERIES_SECTIONS = ("entry", "exit_signal", "filters")
POSITION_SECTIONS = ("exit_position",)
ALL_CONDITION_SECTIONS = TIMESERIES_SECTIONS + POSITION_SECTIONS


def validate_strategy_json(payload: Any) -> None:
    """strategy_json 1건을 검증한다.

    실패하면 AppError 하위를 raise. 성공하면 None 반환.

    이 함수는 deepcopy하지 않고 읽기만 수행 — 호출자가 payload의 mutation을
    걱정할 필요 없다.
    """
    if not isinstance(payload, dict):
        raise InvalidStrategyJsonError(
            "strategy_json은 객체(dict)여야 합니다.",
            details=[{"field": "", "message": f"got {type(payload).__name__}"}],
        )

    # 1. entry 필수 (조건 1개 이상)
    entry = payload.get("entry")
    if not isinstance(entry, dict):
        raise InvalidStrategyJsonError(
            "entry 섹션이 필요합니다.",
            details=[{"field": "entry", "message": "객체로 정의되어야 합니다."}],
        )
    _validate_logic_section(entry, section="entry")

    # 2. exit_signal 또는 exit_position 중 최소 하나
    exit_signal = payload.get("exit_signal")
    exit_position = payload.get("exit_position")
    if exit_signal is None and exit_position is None:
        raise InvalidStrategyJsonError(
            "exit_signal 또는 exit_position 중 최소 하나가 필요합니다.",
            details=[{"field": "exit_signal|exit_position", "message": "둘 다 누락됨"}],
        )
    if exit_signal is not None:
        if not isinstance(exit_signal, dict):
            raise InvalidStrategyJsonError(
                "exit_signal은 객체여야 합니다.",
                details=[{"field": "exit_signal", "message": "객체 필요"}],
            )
        _validate_logic_section(exit_signal, section="exit_signal")
    if exit_position is not None:
        if not isinstance(exit_position, dict):
            raise InvalidStrategyJsonError(
                "exit_position은 객체여야 합니다.",
                details=[{"field": "exit_position", "message": "객체 필요"}],
            )
        _validate_logic_section(exit_position, section="exit_position")

    # 3. filters (선택)
    filters = payload.get("filters")
    if filters is not None:
        if not isinstance(filters, dict):
            raise InvalidStrategyJsonError(
                "filters는 객체여야 합니다.",
                details=[{"field": "filters", "message": "객체 필요"}],
            )
        _validate_logic_section(filters, section="filters")

    # 4. position_sizing (선택이지만 MVP에서는 사실상 필수 — 누락 시 엔진 실패)
    ps = payload.get("position_sizing")
    if ps is not None:
        _validate_position_sizing(ps)

    # 5. execution (선택)
    execution = payload.get("execution")
    if execution is not None:
        _validate_execution(execution)

    # 6. priority (선택)
    priority = payload.get("priority")
    if priority is not None:
        _validate_priority(priority)


# ============================================================================
# 내부 검증 함수 (각 섹션 단위)
# ============================================================================


def _validate_logic_section(section_obj: dict, *, section: str) -> None:
    """entry/exit_signal/exit_position/filters 섹션의 logic + conditions 검증.

    GROUP일 때만 conditions 대신 groups 검증.
    조건 라우팅(requires_position)도 여기서 검사.
    """
    logic = section_obj.get("logic")
    if logic is None:
        # entry는 필수, 다른 섹션은 conditions만 있어도 통과 — 02번 4절은
        # logic 없으면 AND로 간주하지 않으므로 명시 요구.
        raise InvalidStrategyJsonError(
            f"{section}.logic이 필요합니다.",
            details=[{"field": f"{section}.logic", "message": "AND/OR/GROUP 중 하나"}],
        )
    if logic not in ALLOWED_LOGIC:
        raise InvalidStrategyJsonError(
            f"{section}.logic 값이 올바르지 않습니다.",
            details=[
                {
                    "field": f"{section}.logic",
                    "message": f"허용: {', '.join(ALLOWED_LOGIC)}, got {logic!r}",
                }
            ],
        )

    if logic == "GROUP":
        operator = section_obj.get("operator")
        if operator not in ALLOWED_GROUP_OPERATORS:
            raise InvalidStrategyJsonError(
                f"{section} GROUP의 operator는 AND 또는 OR이어야 합니다.",
                details=[
                    {
                        "field": f"{section}.operator",
                        "message": f"허용: {', '.join(ALLOWED_GROUP_OPERATORS)}, got {operator!r}",
                    }
                ],
            )
        groups = section_obj.get("groups")
        if not isinstance(groups, list) or not groups:
            raise InvalidStrategyJsonError(
                f"{section} GROUP은 groups 배열이 1개 이상이어야 합니다.",
                details=[{"field": f"{section}.groups", "message": "비어있음"}],
            )
        for idx, sub in enumerate(groups):
            if not isinstance(sub, dict):
                raise InvalidStrategyJsonError(
                    f"{section}.groups[{idx}]는 객체여야 합니다.",
                    details=[{"field": f"{section}.groups[{idx}]", "message": "객체 필요"}],
                )
            sub_logic = sub.get("logic")
            if sub_logic == "GROUP":
                # 1단계 중첩만 (02번 4절)
                raise InvalidStrategyJsonError(
                    f"{section}.groups[{idx}]에 GROUP 중첩은 지원하지 않습니다.",
                    details=[
                        {
                            "field": f"{section}.groups[{idx}].logic",
                            "message": "GROUP 안에 GROUP은 1단계 중첩 정책 위반",
                        }
                    ],
                )
            sub_conditions = sub.get("conditions")
            if not isinstance(sub_conditions, list) or not sub_conditions:
                raise InvalidStrategyJsonError(
                    f"{section}.groups[{idx}].conditions가 비어있습니다.",
                    details=[
                        {
                            "field": f"{section}.groups[{idx}].conditions",
                            "message": "최소 1개 필요",
                        }
                    ],
                )
            if sub_logic not in ("AND", "OR"):
                raise InvalidStrategyJsonError(
                    f"{section}.groups[{idx}].logic은 AND 또는 OR이어야 합니다.",
                    details=[
                        {
                            "field": f"{section}.groups[{idx}].logic",
                            "message": f"got {sub_logic!r}",
                        }
                    ],
                )
            for c_idx, cond in enumerate(sub_conditions):
                _validate_condition(
                    cond,
                    section=section,
                    field_path=f"{section}.groups[{idx}].conditions[{c_idx}]",
                )
        return

    # AND/OR
    conditions = section_obj.get("conditions")
    if not isinstance(conditions, list) or not conditions:
        raise InvalidStrategyJsonError(
            f"{section}.conditions가 비어있습니다.",
            details=[{"field": f"{section}.conditions", "message": "최소 1개 필요"}],
        )
    for idx, cond in enumerate(conditions):
        _validate_condition(cond, section=section, field_path=f"{section}.conditions[{idx}]")


def _validate_condition(cond: Any, *, section: str, field_path: str) -> None:
    """단일 조건 dict 검증 — type 등록 + requires_position 라우팅 + operator 화이트리스트."""
    if not isinstance(cond, dict):
        raise InvalidStrategyJsonError(
            f"{field_path}는 객체여야 합니다.",
            details=[{"field": field_path, "message": "객체 필요"}],
        )
    cond_type = cond.get("type")
    if not isinstance(cond_type, str) or not cond_type:
        raise MissingRequiredParameterError(
            f"{field_path}.type이 필요합니다.",
            details=[{"field": f"{field_path}.type", "message": "문자열 type 필수"}],
        )

    # registry 등록 여부
    # 지연 import: validator 모듈 import만으로 strategy 도메인을 끌어오지 않게.
    from app.strategy.registry import condition_registry

    registered = set(condition_registry.list_condition_types())
    if cond_type not in registered:
        raise UnknownConditionTypeError(
            f"등록되지 않은 조건 type입니다: {cond_type!r}",
            details=[
                {
                    "field": f"{field_path}.type",
                    "message": f"허용: {', '.join(sorted(registered))}",
                }
            ],
        )

    requires_position = condition_registry.is_position_condition(cond_type)
    # 라우팅 검증
    if section in TIMESERIES_SECTIONS and requires_position:
        raise ExitPositionInExitSignalError(
            f"포지션 조건 {cond_type!r}은 {section}에 들어갈 수 없습니다.",
            details=[
                {
                    "field": f"{field_path}.type",
                    "message": (
                        f"{cond_type}은 requires_position=True (보유 상태 평가). "
                        "exit_position 섹션에만 허용됩니다."
                    ),
                }
            ],
        )
    if section in POSITION_SECTIONS and not requires_position:
        raise ExitSignalInExitPositionError(
            f"시계열 조건 {cond_type!r}은 exit_position에 들어갈 수 없습니다.",
            details=[
                {
                    "field": f"{field_path}.type",
                    "message": (
                        f"{cond_type}은 requires_position=False (시계열 평가). "
                        f"{', '.join(TIMESERIES_SECTIONS)} 섹션에서만 허용됩니다."
                    ),
                }
            ],
        )

    # operator 화이트리스트 (있는 경우만)
    if "operator" in cond:
        op = cond["operator"]
        if op not in ALLOWED_OPERATORS:
            raise InvalidOperatorError(
                f"{field_path}.operator 값이 올바르지 않습니다.",
                details=[
                    {
                        "field": f"{field_path}.operator",
                        "message": f"허용: {', '.join(ALLOWED_OPERATORS)}, got {op!r}",
                    }
                ],
            )


def _validate_position_sizing(ps: Any) -> None:
    if not isinstance(ps, dict):
        raise InvalidStrategyJsonError(
            "position_sizing은 객체여야 합니다.",
            details=[{"field": "position_sizing", "message": "객체 필요"}],
        )
    method = ps.get("method")
    if method not in ALLOWED_POSITION_SIZING_METHODS:
        raise InvalidParameterValueError(
            "position_sizing.method가 올바르지 않습니다.",
            details=[
                {
                    "field": "position_sizing.method",
                    "message": (
                        f"허용: {', '.join(ALLOWED_POSITION_SIZING_METHODS)}, "
                        f"got {method!r}"
                    ),
                }
            ],
        )

    if method == "fixed_amount":
        amount = ps.get("amount")
        if not _is_positive_number(amount):
            raise InvalidParameterValueError(
                "position_sizing.amount는 0보다 커야 합니다.",
                details=[
                    {
                        "field": "position_sizing.amount",
                        "message": f"got {amount!r}",
                    }
                ],
            )
    elif method == "fixed_ratio":
        ratio = ps.get("ratio")
        if not (isinstance(ratio, (int, float)) and 0 < float(ratio) <= 1):
            raise InvalidParameterValueError(
                "position_sizing.ratio는 (0, 1] 범위여야 합니다.",
                details=[{"field": "position_sizing.ratio", "message": f"got {ratio!r}"}],
            )

    max_positions = ps.get("max_positions")
    if max_positions is not None and not (isinstance(max_positions, int) and max_positions >= 1):
        raise InvalidParameterValueError(
            "position_sizing.max_positions는 1 이상의 정수여야 합니다.",
            details=[{"field": "position_sizing.max_positions", "message": f"got {max_positions!r}"}],
        )

    max_daily_entries = ps.get("max_daily_entries")
    if max_daily_entries is not None and not (
        isinstance(max_daily_entries, int) and max_daily_entries >= 0
    ):
        raise InvalidParameterValueError(
            "position_sizing.max_daily_entries는 0 이상의 정수여야 합니다.",
            details=[
                {
                    "field": "position_sizing.max_daily_entries",
                    "message": f"got {max_daily_entries!r}",
                }
            ],
        )

    daily_buy_budget = ps.get("daily_buy_budget")
    if daily_buy_budget is not None and not (
        isinstance(daily_buy_budget, (int, float)) and float(daily_buy_budget) >= 0
    ):
        raise InvalidParameterValueError(
            "position_sizing.daily_buy_budget은 0 이상이어야 합니다.",
            details=[
                {
                    "field": "position_sizing.daily_buy_budget",
                    "message": f"got {daily_buy_budget!r}",
                }
            ],
        )


def _validate_execution(execution: Any) -> None:
    if not isinstance(execution, dict):
        raise InvalidStrategyJsonError(
            "execution은 객체여야 합니다.",
            details=[{"field": "execution", "message": "객체 필요"}],
        )

    for field in ("entry_price", "exit_price"):
        value = execution.get(field)
        if value is not None and value not in ALLOWED_EXECUTION_PRICE:
            raise InvalidParameterValueError(
                f"execution.{field} 값이 올바르지 않습니다.",
                details=[
                    {
                        "field": f"execution.{field}",
                        "message": (
                            f"허용: {', '.join(ALLOWED_EXECUTION_PRICE)}, got {value!r}"
                        ),
                    }
                ],
            )

    fee_rate = execution.get("fee_rate")
    if fee_rate is not None and not _is_non_negative_number(fee_rate):
        raise InvalidParameterValueError(
            "execution.fee_rate는 0 이상이어야 합니다.",
            details=[{"field": "execution.fee_rate", "message": f"got {fee_rate!r}"}],
        )

    slippage = execution.get("slippage")
    if slippage is not None and not _is_non_negative_number(slippage):
        raise InvalidParameterValueError(
            "execution.slippage는 0 이상이어야 합니다.",
            details=[{"field": "execution.slippage", "message": f"got {slippage!r}"}],
        )

    tick_rounding = execution.get("tick_rounding")
    if tick_rounding is not None and tick_rounding not in ALLOWED_TICK_ROUNDING:
        raise InvalidParameterValueError(
            "execution.tick_rounding 값이 올바르지 않습니다.",
            details=[
                {
                    "field": "execution.tick_rounding",
                    "message": f"허용: {', '.join(ALLOWED_TICK_ROUNDING)}, got {tick_rounding!r}",
                }
            ],
        )

    tax_rate = execution.get("tax_rate")
    if tax_rate is not None:
        _validate_tax_rate(tax_rate, field="execution.tax_rate")


def _validate_priority(priority: Any) -> None:
    if not isinstance(priority, dict):
        raise InvalidStrategyJsonError(
            "priority는 객체여야 합니다.",
            details=[{"field": "priority", "message": "객체 필요"}],
        )
    method = priority.get("method")
    if method is not None and method not in ALLOWED_PRIORITY_METHODS:
        raise InvalidParameterValueError(
            "priority.method가 올바르지 않습니다.",
            details=[
                {
                    "field": "priority.method",
                    "message": (
                        f"허용: {', '.join(ALLOWED_PRIORITY_METHODS)}, got {method!r}"
                    ),
                }
            ],
        )
    tie_breaker = priority.get("tie_breaker")
    if tie_breaker is not None and tie_breaker not in ALLOWED_PRIORITY_TIE_BREAKERS:
        raise InvalidParameterValueError(
            "priority.tie_breaker가 올바르지 않습니다.",
            details=[
                {
                    "field": "priority.tie_breaker",
                    "message": (
                        f"허용: {', '.join(ALLOWED_PRIORITY_TIE_BREAKERS)}, got {tie_breaker!r}"
                    ),
                }
            ],
        )


def _validate_tax_rate(tax_rate: Any, *, field: str) -> None:
    """tax_rate: float 또는 [{from: ISO date, rate: float}] (from 오름차순)."""
    if isinstance(tax_rate, (int, float)) and not isinstance(tax_rate, bool):
        if float(tax_rate) < 0:
            raise InvalidParameterValueError(
                f"{field}는 0 이상이어야 합니다.",
                details=[{"field": field, "message": f"got {tax_rate!r}"}],
            )
        return

    if not isinstance(tax_rate, list) or not tax_rate:
        raise InvalidParameterValueError(
            f"{field}는 float 또는 [{{from, rate}}] 비어있지 않은 배열이어야 합니다.",
            details=[{"field": field, "message": f"got {type(tax_rate).__name__}"}],
        )

    parsed_dates: list[date_type] = []
    for idx, item in enumerate(tax_rate):
        if not isinstance(item, dict):
            raise InvalidParameterValueError(
                f"{field}[{idx}]는 객체여야 합니다.",
                details=[{"field": f"{field}[{idx}]", "message": "객체 필요"}],
            )
        raw_from = item.get("from")
        rate = item.get("rate")
        if not isinstance(raw_from, str):
            raise MissingRequiredParameterError(
                f"{field}[{idx}].from은 ISO 날짜 문자열이어야 합니다.",
                details=[{"field": f"{field}[{idx}].from", "message": f"got {raw_from!r}"}],
            )
        try:
            parsed = date_type.fromisoformat(raw_from)
        except ValueError as exc:
            raise InvalidParameterValueError(
                f"{field}[{idx}].from 날짜 형식이 올바르지 않습니다.",
                details=[
                    {
                        "field": f"{field}[{idx}].from",
                        "message": f"YYYY-MM-DD 형식 필요, got {raw_from!r}",
                    }
                ],
            ) from exc
        if not _is_non_negative_number(rate):
            raise InvalidParameterValueError(
                f"{field}[{idx}].rate는 0 이상이어야 합니다.",
                details=[{"field": f"{field}[{idx}].rate", "message": f"got {rate!r}"}],
            )
        parsed_dates.append(parsed)

    # from 오름차순 (02번 15절)
    if parsed_dates != sorted(parsed_dates):
        raise InvalidParameterValueError(
            f"{field}의 from 날짜는 오름차순이어야 합니다.",
            details=[{"field": field, "message": "from 정렬 위반"}],
        )


# ============================================================================
# 공통 헬퍼
# ============================================================================


def _is_positive_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    return isinstance(value, (int, float)) and float(value) > 0


def _is_non_negative_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    return isinstance(value, (int, float)) and float(value) >= 0
