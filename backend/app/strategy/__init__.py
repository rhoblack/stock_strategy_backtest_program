"""전략 도메인 — 조건 Registry, StrategyEngine, indicators.

조건 함수는 `app/strategy/conditions/`에 모듈별로 두고,
import 시점에 `condition_registry`에 자동 등록된다.
"""

from app.strategy.registry import ConditionEntry, ConditionRegistry, condition_registry
from app.strategy.utils import ALLOWED_OPERATORS, compare

__all__ = [
    "ALLOWED_OPERATORS",
    "ConditionEntry",
    "ConditionRegistry",
    "compare",
    "condition_registry",
]
