"""data_pipeline.utils — 파이프라인 공통 유틸리티.

현재 구성:
    RateLimiter: pykrx 요청 간격 제어 + 연속 실패 시 자동 일시정지 (14번 §6.4).
"""

from app.data_pipeline.utils.rate_limiter import RateLimiter

__all__ = ["RateLimiter"]
