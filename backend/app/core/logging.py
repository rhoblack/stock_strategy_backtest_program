"""기본 로깅 설정.

표준 logging 모듈 기반. Phase 2~4에서 구조화 로깅으로 확장 가능.
"""

import logging
import sys

from app.core.config import settings


def setup_logging(level: str | None = None) -> None:
    """애플리케이션 시작 시 한 번만 호출."""
    log_level = level or settings.log_level
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
