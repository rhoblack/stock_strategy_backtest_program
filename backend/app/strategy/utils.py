"""전략 도메인 유틸리티.

설계서 03번 8절: compare 유틸리티.
조건 함수가 operator 분기를 매번 작성하지 않도록 한 곳에 모음.
"""

from __future__ import annotations

from typing import Any

from app.core.exceptions import InvalidOperatorError

ALLOWED_OPERATORS = (">", ">=", "<", "<=", "==")


def compare(left: Any, operator: str, right: Any) -> Any:
    """비교 연산을 일관 처리.

    left, right는 scalar 또는 pandas Series. 결과는 입력에 따라 scalar 또는
    boolean Series. NaN은 pandas의 표준 비교 규칙(False 전파)을 따른다.
    """
    if operator == ">":
        return left > right
    if operator == ">=":
        return left >= right
    if operator == "<":
        return left < right
    if operator == "<=":
        return left <= right
    if operator == "==":
        return left == right
    raise InvalidOperatorError(
        f"지원하지 않는 연산자입니다: {operator!r} (허용: {', '.join(ALLOWED_OPERATORS)})"
    )
