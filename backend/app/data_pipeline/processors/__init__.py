"""data_pipeline.processors — raw 데이터 가공/검증 (14번 §5 / §7 / §9).

본 패키지는 BaseProcessor 추상 베이스만 제공한다.
실제 AdjustedPriceProcessor / MarketCapProcessor / DataValidator는 026~ 후속 step.

타 모듈 사용법:
    from app.data_pipeline.processors import (
        BaseProcessor,
        ProcessedResult,
        ValidationResult,
        ValidationIssue,
    )
"""

from app.data_pipeline.processors.base import (
    BaseProcessor,
    ProcessedResult,
    ValidationIssue,
    ValidationResult,
)

__all__ = [
    "BaseProcessor",
    "ProcessedResult",
    "ValidationIssue",
    "ValidationResult",
]
