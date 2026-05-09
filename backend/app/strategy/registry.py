"""ConditionRegistry — 조건 함수 등록 및 라우팅.

설계서 03번 문서 3~5절의 Registry 패턴 구현.

핵심 책임:
    1. 조건 type → 함수 매핑 (등록)
    2. 시계열 조건과 포지션 조건의 라우팅 분리 (requires_position 메타)
    3. GUI/API용 조건 메타데이터 노출

이 모듈은 pandas를 런타임 import하지 않는다. 조건 함수가 자신의 모듈에서
pandas를 사용하지만, registry는 함수를 등록/호출만 하므로 pandas에
의존하지 않는다. 타입 힌트는 TYPE_CHECKING 안에서만 사용.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.core.exceptions import (
    PositionConditionMisuseError,
    TimeseriesConditionMisuseError,
    UnknownConditionTypeError,
)

if TYPE_CHECKING:
    import pandas as pd


# 조건 함수 타입 힌트 (참고용 — 런타임 검증은 하지 않음)
TimeseriesConditionFunc = Callable[["pd.DataFrame", dict], "pd.Series"]
PositionConditionFunc = Callable[[Any, Any, dict], tuple[bool, "str | None"]]


@dataclass(frozen=True)
class ConditionEntry:
    """등록된 조건 1개의 메타데이터와 실행 함수."""

    func: Callable
    requires_position: bool
    category: str


class ConditionRegistry:
    """조건 함수 레지스트리.

    `register` 데코레이터로 조건 함수를 등록하고,
    `evaluate` (시계열) 또는 `evaluate_position` (포지션 기반)으로 평가한다.

    한 condition_type을 두 번 register하면 나중 등록이 이전 것을 덮어쓴다 (테스트 편의).
    """

    def __init__(self) -> None:
        self._conditions: dict[str, ConditionEntry] = {}

    def register(
        self,
        condition_type: str,
        *,
        requires_position: bool = False,
        category: str = "general",
    ) -> Callable[[Callable], Callable]:
        """조건 함수 등록 데코레이터.

        시계열 조건 (df 기반):
            @condition_registry.register("price_vs_ma", category="moving_average")
            def price_vs_ma(df, condition): ...

        포지션 조건 (보유 상태 기반):
            @condition_registry.register("take_profit", requires_position=True, category="exit_position")
            def take_profit(position, market_row, condition): ...
        """

        def decorator(func: Callable) -> Callable:
            self._conditions[condition_type] = ConditionEntry(
                func=func,
                requires_position=requires_position,
                category=category,
            )
            return func

        return decorator

    def evaluate(self, condition_type: str, df: "pd.DataFrame", condition: dict) -> "pd.Series":
        """시계열 조건 평가. StrategyEngine이 호출.

        반환값은 boolean pandas Series여야 한다 (각 함수 책임).
        """
        entry = self._get_entry(condition_type)
        if entry.requires_position:
            raise PositionConditionMisuseError(
                f"{condition_type}은 포지션 조건입니다. "
                "StrategyEngine.evaluate가 아니라 BacktestEngine.evaluate_position이 처리해야 합니다."
            )
        return entry.func(df, condition)

    def evaluate_position(
        self,
        condition_type: str,
        position: Any,
        market_row: Any,
        condition: dict,
    ) -> tuple[bool, str | None]:
        """포지션 기반 조건 평가. BacktestEngine이 호출.

        반환값은 (triggered: bool, exit_reason: str | None) 튜플.
        """
        entry = self._get_entry(condition_type)
        if not entry.requires_position:
            raise TimeseriesConditionMisuseError(
                f"{condition_type}은 시계열 조건입니다. "
                "BacktestEngine.evaluate_position이 아니라 StrategyEngine.evaluate가 처리해야 합니다."
            )
        return entry.func(position, market_row, condition)

    def is_position_condition(self, condition_type: str) -> bool:
        return self._get_entry(condition_type).requires_position

    def get_category(self, condition_type: str) -> str:
        return self._get_entry(condition_type).category

    def list_conditions(self) -> list[dict]:
        """GUI/API 노출용. `GET /api/conditions`에서 사용.

        실제 GUI에는 sentence_template, parameters 등 추가 메타데이터가 필요한데,
        그것은 별도 CONDITION_DEFINITIONS 카탈로그에서 합쳐서 노출한다 (03번 15절).
        """
        return [
            {
                "type": condition_type,
                "requires_position": entry.requires_position,
                "category": entry.category,
            }
            for condition_type, entry in self._conditions.items()
        ]

    def list_condition_types(self) -> list[str]:
        return list(self._conditions.keys())

    # === 내부 헬퍼 ===

    def _get_entry(self, condition_type: str) -> ConditionEntry:
        entry = self._conditions.get(condition_type)
        if entry is None:
            raise UnknownConditionTypeError(f"등록되지 않은 조건입니다: {condition_type}")
        return entry


# 모듈 레벨 싱글턴. 모든 조건 함수는 이 인스턴스에 등록된다.
condition_registry = ConditionRegistry()
