"""전략 도메인 — 조건 Registry, StrategyEngine, indicators.

조건 함수는 `app/strategy/conditions/`에 모듈별로 두고,
import 시점에 `condition_registry`에 자동 등록된다.

`app.strategy`를 import하는 것만으로 모든 조건이 등록된 상태가 된다
(condition_definitions를 import하기 때문).
"""

# condition_definitions를 import하면 conditions/* 모두 로드 + 자동 등록
from app.strategy.condition_definitions import ALL_DEFINITIONS, get_condition_catalog
from app.strategy.registry import ConditionEntry, ConditionRegistry, condition_registry
from app.strategy.utils import ALLOWED_OPERATORS, compare

__all__ = [
    "ALL_DEFINITIONS",
    "ALLOWED_OPERATORS",
    "ConditionEntry",
    "ConditionRegistry",
    "compare",
    "condition_registry",
    "get_condition_catalog",
]
