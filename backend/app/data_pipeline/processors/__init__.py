"""data_pipeline.processors — raw 데이터 가공/검증 (14번 §5 / §7 / §9).

베이스(`BaseProcessor`) + 026 `AdjustedPriceProcessor` (수정주가 재계산) 제공.
027 MarketCapProcessor / DataValidator는 후속 step.

타 모듈 사용법:
    from app.data_pipeline.processors import (
        BaseProcessor,
        ProcessedResult,
        ValidationResult,
        ValidationIssue,
        AdjustedPriceProcessor,
        AdjustedPriceInput,
        CorporateActionEvent,
    )
"""

from app.data_pipeline.processors.adjusted_price import (
    AdjustedPriceInput,
    AdjustedPriceProcessor,
    CorporateActionEvent,
)
from app.data_pipeline.processors.base import (
    BaseProcessor,
    ProcessedResult,
    ValidationIssue,
    ValidationResult,
)

__all__ = [
    "AdjustedPriceInput",
    "AdjustedPriceProcessor",
    "BaseProcessor",
    "CorporateActionEvent",
    "ProcessedResult",
    "ValidationIssue",
    "ValidationResult",
]
