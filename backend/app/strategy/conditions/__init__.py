"""조건 함수 패키지.

이 패키지를 import하면 모든 조건 모듈이 로드되고,
각 모듈의 `@condition_registry.register(...)` 데코레이터가 실행되어
condition_registry에 자동 등록된다.

새 조건 모듈 추가 시 아래 import 목록에 추가할 것.
"""

# 조건 모듈 import (자동 등록 트리거)
from app.strategy.conditions import exit_position, moving_average, rsi, volume  # noqa: F401
